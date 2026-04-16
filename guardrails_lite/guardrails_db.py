"""
Guardrails Lite — SQLite + sqlite-vec 資料庫抽象層。

設計原則：
- 一個 .db 檔案搞定所有資料
- sqlite-vec 虛擬表處理向量搜尋
- metadata 放普通表，JOIN 搜尋
- 支援降級：沒裝 sqlite-vec 時退回純關鍵字
"""

import json
import hashlib
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
    """Guardrails Lite 資料庫層。"""

    SCHEMA_VERSION = 1

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
                updated_at   TEXT  NOT NULL DEFAULT ''
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

    # ── 統計 ────────────────────────────────────────────────

    def stats(self) -> dict:
        k_count = self.conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
        vec_count = 0
        if self._vec_available:
            try:
                vec_count = self.conn.execute("SELECT COUNT(*) FROM knowledge_vec").fetchone()[0]
            except Exception:
                pass
        return {
            "knowledge_count": k_count,
            "embedding_count": vec_count,
            "vec_available": self._vec_available,
            "db_path": str(self.db_path),
            "db_size_mb": round(self.db_path.stat().st_size / 1024 / 1024, 2)
                if self.db_path.exists() else 0,
        }