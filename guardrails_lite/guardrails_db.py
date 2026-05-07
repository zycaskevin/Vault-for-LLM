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
import sqlite3
import sys
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

    SCHEMA_VERSION = 5

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
                convergence_status TEXT NOT NULL DEFAULT 'unknown',
                convergence_score  REAL  DEFAULT NULL,
                convergence_checked_at TEXT NOT NULL DEFAULT '',
                last_verified       TEXT NOT NULL DEFAULT '',
                freshness          REAL  NOT NULL DEFAULT 1.0
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_layer ON knowledge(layer)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_category ON knowledge(category)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_trust ON knowledge(trust)")

        # ── Schema v3 migration：為現有資料庫加新欄位 ──
        existing_cols = {r[1] for r in c.execute("PRAGMA table_info(knowledge)").fetchall()}
        new_cols_v3 = {
            "convergence_status": "TEXT NOT NULL DEFAULT 'unknown'",
            "convergence_score": "REAL DEFAULT NULL",
            "convergence_checked_at": "TEXT NOT NULL DEFAULT ''",
            "last_verified": "TEXT NOT NULL DEFAULT ''",
            "freshness": "REAL NOT NULL DEFAULT 1.0",
        }
        for col_name, col_def in new_cols_v3.items():
            if col_name not in existing_cols:
                c.execute(f"ALTER TABLE knowledge ADD COLUMN {col_name} {col_def}")

        # ── Schema v4 migration：summary 欄位 ──
        new_cols_v4 = {
            "summary": "TEXT NOT NULL DEFAULT ''",
            "summary_generated_at": "TEXT NOT NULL DEFAULT ''",
        }
        for col_name, col_def in new_cols_v4.items():
            if col_name not in existing_cols:
                c.execute(f"ALTER TABLE knowledge ADD COLUMN {col_name} {col_def}")
        c.commit()

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

        # 技能共享表 — 跨 Agent 技能註冊與同步
        c.execute("""
            CREATE TABLE IF NOT EXISTS skills (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL UNIQUE,
                version       TEXT NOT NULL DEFAULT '1.0.0',
                agent_source  TEXT NOT NULL DEFAULT '',
                category      TEXT NOT NULL DEFAULT 'general',
                capabilities  TEXT NOT NULL DEFAULT '',
                dependencies  TEXT NOT NULL DEFAULT '',
                trust         REAL  NOT NULL DEFAULT 0.5,
                content_raw   TEXT NOT NULL DEFAULT '',
                content_hash  TEXT NOT NULL DEFAULT '',
                description   TEXT NOT NULL DEFAULT '',
                created_at    TEXT NOT NULL DEFAULT '',
                updated_at    TEXT NOT NULL DEFAULT '',
                last_synced   TEXT NOT NULL DEFAULT ''
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_skills_agent ON skills(agent_source)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_skills_category ON skills(category)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_skills_trust ON skills(trust)")

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

        # 寫入 schema 版本
        c.execute(
            "INSERT OR REPLACE INTO config(key, value) VALUES(?, ?)",
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
                print(f"[guardrails-lite] ⚠️ 向量表維度不匹配，重建中（舊向量會遺失）: {e}", file=sys.stderr)
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
        summary: str = "",
    ) -> int:
        """新增一筆知識，回傳 id。"""
        now = datetime.now(timezone.utc).isoformat()
        content_hash = hashlib.sha256(content_raw.encode()).hexdigest()[:16]

        cursor = self.conn.execute(
            """INSERT INTO knowledge
               (title, layer, category, tags, trust,
                content_raw, content_aaak, content_hash, source,
                summary, summary_generated_at,
                created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (title, layer, category, tags, trust,
             content_raw, content_aaak, content_hash, source,
             summary, now if summary else '',
             now, now),
        )
        self.conn.commit()
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
        vals = list(fields.values()) + [id]
        self.conn.execute(f"UPDATE knowledge SET {sets} WHERE id=?", vals)
        self.conn.commit()
        return True

    def get_knowledge(self, id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM knowledge WHERE id=?", (id,)
        ).fetchone()
        return dict(row) if row else None

    def delete_knowledge(self, id: int) -> bool:
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
                results.append(d)

        return results

    # ── 關鍵字搜尋 ──────────────────────────────────────────

    def search_keyword(
        self,
        query: str,
        limit: int = 10,
        min_trust: float = 0.0,
    ) -> list[dict]:
        """純關鍵字搜尋（LIKE匹配），降級方案。"""
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

    # ── 收斂驗證 ──────────────────────────────────────────

    def update_convergence(self, kid: int, status: str, score: float):
        """更新條目的收斂狀態。status: unknown/partial/complete, score: 0.0~1.0"""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE knowledge SET convergence_status=?, convergence_score=?, "
            "convergence_checked_at=? WHERE id=?",
            (status, score, now, kid),
        )
        self.conn.commit()

    def update_freshness(self, kid: int, freshness: float, last_verified: str = ""):
        """更新條目的新鮮度。freshness: 0.0~1.0"""
        if not last_verified:
            last_verified = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE knowledge SET freshness=?, last_verified=? WHERE id=?",
            (freshness, last_verified, kid),
        )
        self.conn.commit()

    # ── 技能 CRUD ──────────────────────────────────────────

    def add_skill(
        self,
        name: str,
        content_raw: str,
        version: str = "1.0.0",
        agent_source: str = "",
        category: str = "general",
        capabilities: str = "",
        dependencies: str = "",
        trust: float = 0.5,
        description: str = "",
    ) -> int:
        """註冊一個技能，回傳 id。已有同名技能則回傳 -1。"""
        now = datetime.now(timezone.utc).isoformat()
        content_hash = hashlib.sha256(content_raw.encode()).hexdigest()[:16]

        # 檢查是否已存在
        existing = self.conn.execute(
            "SELECT id FROM skills WHERE name=?", (name,)
        ).fetchone()
        if existing:
            return -1

        cursor = self.conn.execute(
            """INSERT INTO skills
               (name, version, agent_source, category, capabilities, dependencies,
                trust, content_raw, content_hash, description,
                created_at, updated_at, last_synced)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (name, version, agent_source, category, capabilities, dependencies,
             trust, content_raw, content_hash, description,
             now, now, ""),
        )
        self.conn.commit()
        return cursor.lastrowid

    def update_skill(self, name: str, **fields) -> bool:
        """更新技能欄位（以 name 為 key）。"""
        if not fields:
            return False
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        if "content_raw" in fields:
            fields["content_hash"] = hashlib.sha256(
                fields["content_raw"].encode()
            ).hexdigest()[:16]

        sets = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [name]
        self.conn.execute(f"UPDATE skills SET {sets} WHERE name=?", vals)
        self.conn.commit()
        return self.conn.total_changes > 0

    def get_skill(self, name: str) -> Optional[dict]:
        """取得單一技能。"""
        row = self.conn.execute(
            "SELECT * FROM skills WHERE name=?", (name,)
        ).fetchone()
        return dict(row) if row else None

    def delete_skill(self, name: str) -> bool:
        """刪除技能。"""
        self.conn.execute("DELETE FROM skills WHERE name=?", (name,))
        self.conn.commit()
        return self.conn.total_changes > 0

    def search_skills(
        self,
        query: str,
        capabilities: Optional[str] = None,
        category: Optional[str] = None,
        min_trust: float = 0.0,
        agent_source: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        """搜尋技能：關鍵字 + 可選過濾。"""
        conditions = ["trust >= ?"]
        params: list = [min_trust]

        if query:
            conditions.append(
                "(name LIKE ? OR description LIKE ? OR capabilities LIKE ? "
                "OR content_raw LIKE ?)"
            )
            pattern = f"%{query}%"
            params.extend([pattern, pattern, pattern, pattern])

        if capabilities:
            conditions.append("capabilities LIKE ?")
            params.append(f"%{capabilities}%")

        if category:
            conditions.append("category=?")
            params.append(category)

        if agent_source:
            conditions.append("agent_source=?")
            params.append(agent_source)

        where = " AND ".join(conditions)
        rows = self.conn.execute(
            f"SELECT * FROM skills WHERE {where} "
            "ORDER BY trust DESC, updated_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]

    def list_skills(
        self,
        agent_source: Optional[str] = None,
        category: Optional[str] = None,
        min_trust: float = 0.0,
        limit: int = 100,
    ) -> list[dict]:
        """列出全部技能（不含 content_raw，輕量）。"""
        conditions = ["trust >= ?"]
        params: list = [min_trust]

        if agent_source:
            conditions.append("agent_source=?")
            params.append(agent_source)
        if category:
            conditions.append("category=?")
            params.append(category)

        where = " AND ".join(conditions)
        rows = self.conn.execute(
            f"SELECT id, name, version, agent_source, category, capabilities, "
            f"dependencies, trust, description, updated_at FROM skills "
            f"WHERE {where} ORDER BY trust DESC, updated_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_skill_synced(self, name: str):
        """標記技能已同步到 Supabase。"""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE skills SET last_synced=? WHERE name=?",
            (now, name),
        )
        self.conn.commit()

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

        # 收斂統計
        conv_stats = {}
        try:
            for row in self.conn.execute(
                "SELECT convergence_status, COUNT(*) FROM knowledge GROUP BY convergence_status"
            ).fetchall():
                conv_stats[row[0]] = row[1]
        except Exception:
            pass

        # 新鮮度統計
        avg_freshness = 0.0
        try:
            row = self.conn.execute("SELECT AVG(freshness) FROM knowledge").fetchone()
            avg_freshness = round(row[0], 3) if row[0] else 0.0
        except Exception:
            pass

        # 技能統計
        skill_count = 0
        try:
            skill_count = self.conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
        except Exception:
            pass

        return {
            "knowledge_count": k_count,
            "embedding_count": vec_count,
            "edge_count": edge_count,
            "entity_count": entity_count,
            "skill_count": skill_count,
            "vec_available": self._vec_available,
            "db_path": str(self.db_path),
            "db_size_mb": round(self.db_path.stat().st_size / 1024 / 1024, 2)
                if self.db_path.exists() else 0,
            "convergence": conv_stats,
            "avg_freshness": avg_freshness,
        }