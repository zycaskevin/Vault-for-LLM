"""
Vault for LLM — SQLite + sqlite-vec 資料庫抽象層。

設計原則：
- 一個 .db 檔案搞定所有資料
- sqlite-vec 虛擬表處理向量搜尋
- metadata 放普通表，JOIN 搜尋
- 支援降級：沒裝 sqlite-vec 時退回純關鍵字
"""

import json
import hashlib
import re
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# sqlite-vec 是可選依賴
_VEC_AVAILABLE = False
try:
    import sqlite_vec
    _VEC_AVAILABLE = True
except ImportError:
    pass


class GuardrailsDB:
    """Vault for LLM 資料庫層。"""

    SCHEMA_VERSION = 3  # 每次結構有破壞性變更時 +1

    # 從舊版本到新版本的 migration SQL
    # 格式：{from_version: [(sql, description), ...]}
    _MIGRATIONS: dict = {
        2: [
            # v2 → v3：加入存取頻率追蹤欄位
            (
                "ALTER TABLE knowledge ADD COLUMN access_count INTEGER NOT NULL DEFAULT 0",
                "新增 access_count 欄位",
            ),
            (
                "ALTER TABLE knowledge ADD COLUMN last_accessed_at TEXT NOT NULL DEFAULT ''",
                "新增 last_accessed_at 欄位",
            ),
        ],
    }

    def __init__(self, db_path: str | Path = "guardrails.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn: Optional[sqlite3.Connection] = None
        self._vec_available = _VEC_AVAILABLE

    # ── 連線 ──────────────────────────────────────────────

    def connect(self) -> "GuardrailsDB":
        """開啟資料庫連線，註冊 sqlite-vec 擴展。"""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

        # 註冊 sqlite-vec 擴展
        if self._vec_available:
            self.conn.enable_load_extension(True)
            sqlite_vec.load(self.conn)
            self.conn.enable_load_extension(False)

        self._init_tables()
        self._run_migrations()
        return self

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exc):
        self.close()

    # ── 建表 ──────────────────────────────────────────────

    def _init_tables(self):
        """建立所有必要的表。"""
        c = self.conn

        # 配置表
        c.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # 知識主表
        c.execute("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                title        TEXT NOT NULL,
                layer        TEXT NOT NULL DEFAULT 'L3',
                category     TEXT NOT NULL DEFAULT 'general',
                tags         TEXT NOT NULL DEFAULT '',
                trust        REAL  NOT NULL DEFAULT 0.5,
                content_raw  TEXT NOT NULL DEFAULT '',
                content_aaak TEXT NOT NULL DEFAULT '',
                content_hash TEXT NOT NULL DEFAULT '',
                source       TEXT NOT NULL DEFAULT '',
                created_at   TEXT  NOT NULL DEFAULT '',
                updated_at   TEXT  NOT NULL DEFAULT '',
                access_count      INTEGER NOT NULL DEFAULT 0,
                last_accessed_at  TEXT    NOT NULL DEFAULT ''
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_layer ON knowledge(layer)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_category ON knowledge(category)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_trust ON knowledge(trust)")

        # 文章追蹤表
        c.execute("""
            CREATE TABLE IF NOT EXISTS content_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                platform    TEXT NOT NULL DEFAULT '',
                topic       TEXT NOT NULL DEFAULT '',
                title       TEXT NOT NULL DEFAULT '',
                body_hash   TEXT NOT NULL DEFAULT '',
                status      TEXT NOT NULL DEFAULT 'draft',
                published_at TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL DEFAULT ''
            )
        """)

        # Lint 快取表
        c.execute("""
            CREATE TABLE IF NOT EXISTS lint_cache (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                knowledge_id INTEGER NOT NULL,
                check_type  TEXT NOT NULL,
                result      TEXT NOT NULL DEFAULT '',
                checked_at  TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (knowledge_id) REFERENCES knowledge(id)
            )
        """)

        # ── 圖譜_edges 表 ────────────────────────────────────
        # 輕量知識圖譜：節點 = knowledge 表的條目，邊 = 這裡的關聯
        c.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id   INTEGER NOT NULL,
                target_id   INTEGER NOT NULL,
                relation    TEXT NOT NULL DEFAULT 'related_to',
                weight      REAL  NOT NULL DEFAULT 1.0,
                auto_inferred INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT  NOT NULL DEFAULT '',
                FOREIGN KEY (source_id) REFERENCES knowledge(id),
                FOREIGN KEY (target_id) REFERENCES knowledge(id)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation)")

        # 圖譜實體表（自動從 tags/title 推斷的實體）
        c.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                entity_type TEXT NOT NULL DEFAULT 'concept',
                created_at  TEXT  NOT NULL DEFAULT ''
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name)")

        # 實體↔知識條目的對應
        c.execute("""
            CREATE TABLE IF NOT EXISTS entity_knowledge (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id   INTEGER NOT NULL,
                knowledge_id INTEGER NOT NULL,
                FOREIGN KEY (entity_id) REFERENCES entities(id),
                FOREIGN KEY (knowledge_id) REFERENCES knowledge(id)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_ek_entity ON entity_knowledge(entity_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ek_knowledge ON entity_knowledge(knowledge_id)")

        # 向量虛擬表（只有 sqlite-vec 可用時才建）
        if self._vec_available:
            self._init_vec_table()

        # 寫入 schema 版本（INSERT OR IGNORE：只在全新 DB 寫入，舊 DB 保留原版本號讓 migration 判斷）
        c.execute(
            "INSERT OR IGNORE INTO config(key, value) VALUES(?, ?)",
            ("schema_version", str(self.SCHEMA_VERSION)),
        )
        c.commit()

    def _init_vec_table(self):
        """建立 sqlite-vec 向量虛擬表。"""
        # 取得嵌入維度（預設 384）
        dim = self._get_config("embedding_dim", "384")
        # 不 DROP！如果表已存在就不重建，保留向量資料
        # 只有表不存在時才建
        try:
            self.conn.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_vec USING vec0("
                f"  knowledge_id INTEGER PRIMARY KEY, "
                f"  embedding float[{dim}]"
                f")"
            )
            self.conn.commit()
        except Exception as e:
            # 維度變了需要重建
            if "already exists" in str(e).lower() or "different" in str(e).lower():
                print(f"[guardrails-lite] ⚠️ 向量表維度不匹配，重建中（舊向量會遺失）: {e}")
                self.conn.execute("DROP TABLE IF EXISTS knowledge_vec")
                self.conn.execute(
                    f"CREATE VIRTUAL TABLE knowledge_vec USING vec0("
                    f"  knowledge_id INTEGER PRIMARY KEY, "
                    f"  embedding float[{dim}]"
                    f")"
                )
                self.conn.commit()
            else:
                raise

    def _run_migrations(self):
        """依序執行尚未套用的 schema migration。"""
        current = int(self._get_config("schema_version", "1"))
        if current >= self.SCHEMA_VERSION:
            return

        for from_ver in range(current, self.SCHEMA_VERSION):
            steps = self._MIGRATIONS.get(from_ver, [])
            for sql, desc in steps:
                try:
                    self.conn.execute(sql)
                    self.conn.commit()
                    print(f"[guardrails-lite] ✅ migration v{from_ver}→v{from_ver+1}: {desc}")
                except Exception as e:
                    # 欄位已存在（重複執行）→ 忽略
                    if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                        pass
                    else:
                        print(f"[guardrails-lite] ⚠️ migration 失敗: {desc}: {e}")

        # 更新版本號
        self.conn.execute(
            "INSERT OR REPLACE INTO config(key, value) VALUES(?, ?)",
            ("schema_version", str(self.SCHEMA_VERSION)),
        )
        self.conn.commit()

    # ── Config ─────────────────────────────────────────────

    def set_config(self, key: str, value: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO config(key, value) VALUES(?, ?)",
            (key, value),
        )
        self.conn.commit()

    def get_config(self, key: str, default: str = "") -> str:
        return self._get_config(key, default)

    def _get_config(self, key: str, default: str = "") -> str:
        row = self.conn.execute(
            "SELECT value FROM config WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else default

    # ── 知識 CRUD ──────────────────────────────────────────

    def add_knowledge(
        self,
        title: str,
        content_raw: str,
        layer: str = "L3",
        category: str = "general",
        tags: str = "",
        trust: float = 0.5,
        source: str = "",
        content_aaak: str = "",
    ) -> int:
        """新增一筆知識，回傳 id。"""
        now = datetime.now(timezone.utc).isoformat()
        content_hash = hashlib.sha256(content_raw.encode()).hexdigest()[:16]

        cursor = self.conn.execute(
            """INSERT INTO knowledge
               (title, layer, category, tags, trust,
                content_raw, content_aaak, content_hash, source,
                created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (title, layer, category, tags, trust,
             content_raw, content_aaak, content_hash, source,
             now, now),
        )
        self.conn.commit()
        # 同步到 FTS5
        self._fts5_insert(cursor.lastrowid, title, content_raw, content_aaak, tags, category)
        return cursor.lastrowid

    def update_knowledge(self, id: int, **fields) -> bool:
        """更新知識欄位。"""
        if not fields:
            return False
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        # 如果更新了 content_raw，自動重算 hash
        if "content_raw" in fields:
            fields["content_hash"] = hashlib.sha256(
                fields["content_raw"].encode()
            ).hexdigest()[:16]

        sets = ", ".join(f"{k}=?" for k in fields)
        vals = [fields[k] for k in fields] + [id]
        self.conn.execute(f"UPDATE knowledge SET {sets} WHERE id=?", vals)
        self.conn.commit()

        # 同步 FTS5：先刪再重建該筆的索引
        if getattr(self, '_fts5_ready', False):
            k = self.get_knowledge(id)
            if k:
                self._fts5_delete(id)
                self._fts5_insert(id, k['title'], k['content_raw'],
                                  k['content_aaak'], k['tags'], k['category'])

        return True

    def get_knowledge(self, id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM knowledge WHERE id=?", (id,)
        ).fetchone()
        return dict(row) if row else None

    def record_access(self, id: int):
        """記錄一次存取（用於 trust decay 計算）。"""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE knowledge SET access_count = access_count + 1, last_accessed_at = ? WHERE id = ?",
            (now, id),
        )
        self.conn.commit()

    def delete_knowledge(self, id: int) -> bool:
        # 先刪 FTS5（再刪主表，避免孤立 FTS 記錄）
        self._fts5_delete(id)
        self.conn.execute("DELETE FROM knowledge WHERE id=?", (id,))
        if self._vec_available:
            self.conn.execute(
                "DELETE FROM knowledge_vec WHERE knowledge_id=?", (id,)
            )
        self.conn.commit()
        return self.conn.total_changes > 0

    def list_knowledge(
        self,
        layer: Optional[str] = None,
        category: Optional[str] = None,
        min_trust: float = 0.0,
        limit: int = 100,
    ) -> list[dict]:
        """列出知識，支援分層/分類/信任篩選。"""
        query = "SELECT * FROM knowledge WHERE trust >= ?"
        params: list = [min_trust]

        if layer:
            query += " AND layer=?"
            params.append(layer)
        if category:
            query += " AND category=?"
            params.append(category)

        query += " ORDER BY trust DESC, updated_at DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    # ── 向量操作 ────────────────────────────────────────────

    def add_embedding(self, knowledge_id: int, embedding: list[float]):
        """插入向量到 vec0 表。"""
        if not self._vec_available:
            raise RuntimeError("sqlite-vec 未安裝，無法使用向量功能")
        import struct
        emb_bytes = struct.pack(f"{len(embedding)}f", *embedding)
        self.conn.execute(
            "INSERT OR REPLACE INTO knowledge_vec(knowledge_id, embedding) VALUES(?, ?)",
            (knowledge_id, emb_bytes),
        )
        self.conn.commit()

    def search_vector(
        self,
        query_embedding: list[float],
        limit: int = 10,
        min_trust: float = 0.0,
    ) -> list[dict]:
        """向量語意搜尋，回傳知識列表。"""
        if not self._vec_available:
            raise RuntimeError("sqlite-vec 未安裝，無法使用向量搜尋")

        import struct
        emb_bytes = struct.pack(f"{len(query_embedding)}f", *query_embedding)

        # Step 1: 從 vec 表取得相似的 knowledge_id + distance
        vec_rows = self.conn.execute(
            "SELECT knowledge_id, distance FROM knowledge_vec "
            "WHERE embedding MATCH ? ORDER BY distance ASC LIMIT ?",
            (emb_bytes, limit),
        ).fetchall()

        if not vec_rows:
            return []

        # Step 2: 取得知識詳細資料
        results = []
        for row in vec_rows:
            kid = row["knowledge_id"]
            dist = row["distance"]
            # dist 可能是 bytes 或 float
            if isinstance(dist, bytes):
                dist = struct.unpack("f", dist)[0]
            dist = float(dist)

            k_row = self.conn.execute(
                "SELECT * FROM knowledge WHERE id=? AND trust >= ?",
                (kid, min_trust),
            ).fetchone()
            if k_row:
                d = dict(k_row)
                d["_distance"] = dist
                # Trust 加權：高品質知識排在前面
                # score = (1 - dist/2) * (0.7 + 0.3 * trust)
                d["_score"] = max(0.0, 1.0 - dist / 2) * (0.7 + 0.3 * d.get("trust", 0.5))
                results.append(d)

        return results

    # ── 關鍵字搜尋 ──────────────────────────────────────────

    def search_keyword(
        self,
        query: str,
        limit: int = 10,
        min_trust: float = 0.0,
    ) -> list[dict]:
        """
        關鍵字搜尋，優先使用 FTS5 + BM25，降級回 LIKE。
        FTS5 效能比 LIKE 快 10-100x，且支援詞頻加權。
        """
        # 嘗試 FTS5（trigram 最少 3 字元，短查詢降級到 LIKE）
        cjk_chars = len(re.findall(r'[\u4e00-\u9fff]', query))
        if cjk_chars >= 3 or (cjk_chars == 0 and len(query) >= 3):
            fts_results = self._search_fts5(query, limit, min_trust)
            if fts_results is not None and len(fts_results) > 0:
                return fts_results

        # 降級：LIKE 匹配
        sql = """
            SELECT *, 0.0 AS _score
            FROM knowledge
            WHERE trust >= ?
              AND (title LIKE ? OR content_raw LIKE ? OR content_aaak LIKE ?
                   OR tags LIKE ? OR category LIKE ?)
            ORDER BY trust DESC
            LIMIT ?
        """
        pattern = f"%{query}%"
        rows = self.conn.execute(
            sql, (min_trust, pattern, pattern, pattern, pattern, pattern, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def _search_fts5(
        self,
        query: str,
        limit: int = 10,
        min_trust: float = 0.0,
    ) -> Optional[list[dict]]:
        """
        FTS5 + BM25 搜尋。回傳 None 表示 FTS5 不可用（需降級）。
        自動建立 FTS5 虛擬表（如果不存在），並同步資料。
        """
        # 確保 FTS5 表存在
        if not self._ensure_fts5():
            return None

        # 搜尋
        try:
            # FTS5 MATCH：trigram tokenizer 直接用子串匹配
            # trigram 支援中文 n-gram 索引，直接查整個詞即可
            match_expr = f'"{query}"'

            # BM25 評分 + Trust 加權
            sql = """
                SELECT k.*, -ft.rank AS _bm25_score
                FROM knowledge_fts ft
                JOIN knowledge k ON k.id = ft.rowid
                WHERE k.trust >= ? AND knowledge_fts MATCH ?
                ORDER BY -ft.rank * (0.7 + 0.3 * k.trust) DESC
                LIMIT ?
            """
            rows = self.conn.execute(sql, (min_trust, match_expr, limit)).fetchall()

            results = []
            for row in rows:
                d = dict(row)
                # 標準化 BM25 分數到 0~1
                bm25 = d.pop("_bm25_score", 0)
                d["_score"] = min(1.0, bm25 / 10.0) if bm25 > 0 else 0.0
                d["_mode"] = "fts5"
                results.append(d)

            return results

        except Exception as e:
            # FTS5 查詢失敗 → 靜默降級
            print(f"[guardrails-lite] ⚠️ FTS5 搜尋失敗，降級 LIKE: {e}")
            return None

    def _ensure_fts5(self) -> bool:
        """確保 FTS5 虛擬表存在且已同步。回傳 False 表示不可用。"""
        # 檢查是否已初始化過
        if getattr(self, '_fts5_ready', False):
            return True

        try:
            # 檢查表是否已存在
            exists = self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_fts'"
            ).fetchone()

            if not exists:
                # 建立 FTS5 虛擬表（用 trigram tokenizer 支援中文）
                # trigram 對 CJK 字元做 3-gram 索引，中文搜尋最精準
                self.conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
                    USING fts5(
                        title, content_raw, content_aaak, tags, category,
                        tokenize="trigram"
                    )
                """)
                self.conn.commit()

            self._fts5_ready = True

            # 同步現有資料（包括 FTS5 建立前已寫入的）
            self._sync_fts5()

            return True

        except Exception as e:
            # FTS5 不可用（舊版 SQLite 或編譯時未啟用）
            return False

    def _sync_fts5(self):
        """同步 knowledge 表資料到 FTS5。"""
        try:
            self.conn.execute("""
                INSERT INTO knowledge_fts(rowid, title, content_raw, content_aaak, tags, category)
                SELECT id, title, content_raw, content_aaak, tags, category
                FROM knowledge
            """)
            self.conn.commit()
        except Exception as e:
            print(f"[guardrails-lite] ⚠️ FTS5 同步失敗: {e}")

    def _fts5_insert(self, kid: int, title: str, content_raw: str,
                     content_aaak: str, tags: str, category: str):
        """新増知識時同步到 FTS5（失敗靜默）。"""
        try:
            # 確保 FTS5 已初始化
            if not getattr(self, '_fts5_ready', False):
                self._ensure_fts5()
            if getattr(self, '_fts5_ready', False):
                self.conn.execute(
                    "INSERT INTO knowledge_fts(rowid, title, content_raw, content_aaak, tags, category) "
                    "VALUES(?,?,?,?,?,?)",
                    (kid, title, content_raw, content_aaak, tags, category),
                )
                self.conn.commit()
        except Exception:
            pass

    def _fts5_delete(self, kid: int):
        """刪除知識時同步從 FTS5 移除（失敗靜默）。"""
        try:
            if getattr(self, '_fts5_ready', False):
                self.conn.execute(
                    "DELETE FROM knowledge_fts WHERE rowid=?", (kid,)
                )
                self.conn.commit()
        except Exception:
            pass

    # ── Lint 快取 ───────────────────────────────────────────

    def add_lint_result(self, knowledge_id: int, check_type: str, result: str):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT INTO lint_cache(knowledge_id, check_type, result, checked_at) VALUES(?,?,?,?)",
            (knowledge_id, check_type, result, now),
        )
        self.conn.commit()

    def get_lint_results(self, knowledge_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM lint_cache WHERE knowledge_id=?", (knowledge_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── 圖譜操作 ────────────────────────────────────────────

    def add_edge(
        self,
        source_id: int,
        target_id: int,
        relation: str = "related_to",
        weight: float = 1.0,
        auto_inferred: bool = False,
    ) -> int:
        """新增一條邊，回傳 edge id。"""
        now = datetime.now(timezone.utc).isoformat()
        # 避免重複（同方向同關係）
        existing = self.conn.execute(
            "SELECT id FROM edges WHERE source_id=? AND target_id=? AND relation=?",
            (source_id, target_id, relation),
        ).fetchone()
        if existing:
            return existing[0]
        cursor = self.conn.execute(
            "INSERT INTO edges(source_id, target_id, relation, weight, auto_inferred, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (source_id, target_id, relation, weight, int(auto_inferred), now),
        )
        self.conn.commit()
        return cursor.lastrowid

    def delete_edge(self, edge_id: int) -> bool:
        self.conn.execute("DELETE FROM edges WHERE id=?", (edge_id,))
        self.conn.commit()
        return self.conn.total_changes > 0

    def get_edges(
        self,
        node_id: Optional[int] = None,
        relation: Optional[str] = None,
        direction: str = "both",
    ) -> list[dict]:
        """
        查詢邊。
        - node_id: 指定節點（可選，None = 全部）
        - relation: 指定關係類型（可選）
        - direction: 'outgoing', 'incoming', 'both'
        """
        conditions = []
        params: list = []

        if node_id is not None:
            if direction in ("outgoing", "both"):
                conditions.append("source_id=?")
                params.append(node_id)
            if direction in ("incoming", "both"):
                conditions.append("target_id=?")
                params.append(node_id)
            if direction == "both":
                where = f"({' OR '.join(conditions)})"
            else:
                where = conditions[0] if conditions else "1=1"
        else:
            where = "1=1"

        if relation:
            where += " AND relation=?"
            params.append(relation)

        rows = self.conn.execute(
            f"SELECT * FROM edges WHERE {where} ORDER BY weight DESC", params
        ).fetchall()
        return [dict(r) for r in rows]

    def get_neighbors(
        self, node_id: int, max_depth: int = 2, min_weight: float = 0.0
    ) -> list[dict]:
        """
        BFS 遍歷鄰居，回傳 (node_id, distance, path) 列表。
        max_depth: 最大跳數（預設 2）
        min_weight: 最小邊權重（過濾弱關聯）
        """
        visited = {node_id}
        frontier = {node_id}
        results = []

        for depth in range(1, max_depth + 1):
            next_frontier = set()
            for nid in frontier:
                rows = self.conn.execute(
                    "SELECT source_id, target_id, relation, weight FROM edges "
                    "WHERE (source_id=? OR target_id=?) AND weight >= ?",
                    (nid, nid, min_weight),
                ).fetchall()
                for row in rows:
                    neighbor = row["target_id"] if row["source_id"] == nid else row["source_id"]
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.add(neighbor)
                        results.append({
                            "id": neighbor,
                            "distance": depth,
                            "relation": row["relation"],
                            "weight": row["weight"],
                        })
            frontier = next_frontier
            if not frontier:
                break

        return results

    # ── 實體操作 ────────────────────────────────────────────

    def add_entity(self, name: str, entity_type: str = "concept") -> int:
        """新增實體，回傳 entity id（已存在則回傳現有 id）。"""
        existing = self.conn.execute(
            "SELECT id FROM entities WHERE name=?", (name,)
        ).fetchone()
        if existing:
            return existing[0]
        now = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.execute(
            "INSERT INTO entities(name, entity_type, created_at) VALUES(?,?,?)",
            (name, entity_type, now),
        )
        self.conn.commit()
        return cursor.lastrowid

    def link_entity_knowledge(self, entity_id: int, knowledge_id: int):
        """連結實體和知識條目。"""
        existing = self.conn.execute(
            "SELECT id FROM entity_knowledge WHERE entity_id=? AND knowledge_id=?",
            (entity_id, knowledge_id),
        ).fetchone()
        if not existing:
            self.conn.execute(
                "INSERT INTO entity_knowledge(entity_id, knowledge_id) VALUES(?,?)",
                (entity_id, knowledge_id),
            )
            self.conn.commit()

    def get_entities_for_knowledge(self, knowledge_id: int) -> list[dict]:
        """取得知識條目關聯的所有實體。"""
        rows = self.conn.execute(
            "SELECT e.* FROM entities e "
            "JOIN entity_knowledge ek ON e.id = ek.entity_id "
            "WHERE ek.knowledge_id=?",
            (knowledge_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_knowledge_for_entity(self, entity_name: str) -> list[int]:
        """取得實體關聯的所有知識條目 ID（用於圖譜擴展搜尋）。"""
        rows = self.conn.execute(
            "SELECT ek.knowledge_id FROM entities e "
            "JOIN entity_knowledge ek ON e.id = ek.entity_id "
            "WHERE e.name=?",
            (entity_name,),
        ).fetchall()
        return [r[0] for r in rows]

    # ── 統計 ────────────────────────────────────────────────

    def stats(self) -> dict:
        k_count = self.conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
        vec_count = 0
        if self._vec_available:
            try:
                vec_count = self.conn.execute("SELECT COUNT(*) FROM knowledge_vec").fetchone()[0]
            except Exception:
                pass
        # 圖譜統計
        edge_count = self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        entity_count = self.conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]

        return {
            "knowledge_count": k_count,
            "embedding_count": vec_count,
            "edge_count": edge_count,
            "entity_count": entity_count,
            "vec_available": self._vec_available,
            "db_path": str(self.db_path),
            "db_size_mb": round(self.db_path.stat().st_size / 1024 / 1024, 2)
                if self.db_path.exists() else 0,
        }