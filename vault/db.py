"""
Vault-for-LLM — SQLite + sqlite-vec 資料庫抽象層。

設計原則：
- 一個 .db 檔案搞定所有資料
- sqlite-vec 虛擬表處理向量搜尋
- metadata 放普通表，JOIN 搜尋
- 支援降級：沒裝 sqlite-vec 時退回純關鍵字
"""

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


class VaultDB:
    """Vault-for-LLM 資料庫層。"""

    SCHEMA_VERSION = 7
    MIGRATIONS = {
        1: "initial_core_tables",
        2: "graph_and_skill_tables",
        3: "convergence_freshness_columns",
        4: "knowledge_summary_columns",
        5: "document_map_semantic_tables",
        6: "memory_candidate_table",
        7: "memory_candidate_quality_status",
    }

    def __init__(self, db_path: str | Path = "vault.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn: Optional[sqlite3.Connection] = None
        self._vec_available = _VEC_AVAILABLE
        self._fts_available = False

    # ── 連線 ──────────────────────────────────────────────

    def connect(self) -> "VaultDB":
        """開啟資料庫連線，註冊 sqlite-vec 擴展。"""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

        # 註冊 sqlite-vec 擴展. Some Python sqlite builds (including many
        # restricted or system builds) expose the sqlite module without loadable
        # extension support. In that case vector search must degrade instead of
        # blocking the local keyword/memory workflow.
        if self._vec_available:
            if not hasattr(self.conn, "enable_load_extension"):
                self._vec_available = False
            else:
                try:
                    self.conn.enable_load_extension(True)
                    sqlite_vec.load(self.conn)
                except Exception:
                    self._vec_available = False
                finally:
                    try:
                        self.conn.enable_load_extension(False)
                    except Exception:
                        pass

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
        self._ensure_schema_migrations_table()

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
        self._ensure_table_columns(
            "knowledge",
            {
                "title": "TEXT NOT NULL DEFAULT ''",
                "layer": "TEXT NOT NULL DEFAULT 'L3'",
                "category": "TEXT NOT NULL DEFAULT 'general'",
                "tags": "TEXT NOT NULL DEFAULT ''",
                "trust": "REAL NOT NULL DEFAULT 0.5",
                "content_raw": "TEXT NOT NULL DEFAULT ''",
                "content_aaak": "TEXT NOT NULL DEFAULT ''",
                "content_hash": "TEXT NOT NULL DEFAULT ''",
                "source": "TEXT NOT NULL DEFAULT ''",
                "created_at": "TEXT NOT NULL DEFAULT ''",
                "updated_at": "TEXT NOT NULL DEFAULT ''",
            },
        )
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
        self._init_fts_table()
        # ── Document Map tables ─────────────────────────────
        # Markdown section nodes for future A2 parser.
        c.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_nodes (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                knowledge_id   INTEGER NOT NULL,
                node_uid       TEXT NOT NULL,
                parent_uid     TEXT NOT NULL DEFAULT '',
                level          INTEGER NOT NULL DEFAULT 0,
                heading        TEXT NOT NULL DEFAULT '',
                path           TEXT NOT NULL DEFAULT '',
                summary        TEXT NOT NULL DEFAULT '',
                line_start     INTEGER NOT NULL,
                line_end       INTEGER NOT NULL,
                token_estimate INTEGER NOT NULL DEFAULT 0,
                content_hash   TEXT NOT NULL DEFAULT '',
                created_at     TEXT NOT NULL DEFAULT '',
                updated_at     TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (knowledge_id) REFERENCES knowledge(id),
                UNIQUE(knowledge_id, node_uid)
            )
        """)
        self._ensure_table_columns(
            "knowledge_nodes",
            {
                "summary": "TEXT NOT NULL DEFAULT ''",
                "token_estimate": "INTEGER NOT NULL DEFAULT 0",
            },
        )
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_nodes_uid ON knowledge_nodes(knowledge_id, node_uid)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_knowledge_id ON knowledge_nodes(knowledge_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_node_uid ON knowledge_nodes(node_uid)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_path ON knowledge_nodes(path)")

        # Atomic claims extracted from nodes for future A3 backfill.
        c.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_claims (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                knowledge_id INTEGER NOT NULL,
                node_uid     TEXT NOT NULL DEFAULT '',
                claim_uid    TEXT NOT NULL,
                claim        TEXT NOT NULL,
                claim_type   TEXT NOT NULL DEFAULT 'claim',
                line_start   INTEGER NOT NULL DEFAULT 0,
                line_end     INTEGER NOT NULL DEFAULT 0,
                confidence   REAL NOT NULL DEFAULT 0.7,
                source       TEXT NOT NULL DEFAULT 'aaak',
                content_hash TEXT NOT NULL DEFAULT '',
                created_at   TEXT NOT NULL DEFAULT '',
                updated_at   TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (knowledge_id) REFERENCES knowledge(id),
                UNIQUE(knowledge_id, node_uid, claim)
            )
        """)
        claim_cols_before = self._table_columns("knowledge_claims")
        self._ensure_table_columns(
            "knowledge_claims",
            {
                "claim_uid": "TEXT NOT NULL DEFAULT ''",
                "confidence": "REAL NOT NULL DEFAULT 0.7",
            },
        )
        if "claim_uid" not in claim_cols_before:
            self._backfill_claim_uids()
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_claims_uid ON knowledge_claims(knowledge_id, claim_uid)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_claims_knowledge_id ON knowledge_claims(knowledge_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_claims_node_uid ON knowledge_claims(node_uid)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_claims_claim_type ON knowledge_claims(claim_type)")

        # Deterministic semantic-index plumbing for node/claim vectors.
        # Vectors are stored as JSON so tests and base installs do not require sqlite-vec.
        c.execute("""
            CREATE TABLE IF NOT EXISTS semantic_vectors (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                knowledge_id INTEGER NOT NULL,
                vector_kind  TEXT NOT NULL,
                item_uid     TEXT NOT NULL,
                provider_id  TEXT NOT NULL,
                dimension    INTEGER NOT NULL,
                vector       TEXT NOT NULL,
                source_text  TEXT NOT NULL DEFAULT '',
                content_hash TEXT NOT NULL DEFAULT '',
                line_start   INTEGER NOT NULL DEFAULT 0,
                line_end     INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT NOT NULL DEFAULT '',
                updated_at   TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (knowledge_id) REFERENCES knowledge(id),
                UNIQUE(provider_id, dimension, vector_kind, knowledge_id, item_uid)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_semantic_vectors_provider ON semantic_vectors(provider_id, dimension)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_semantic_vectors_knowledge_id ON semantic_vectors(knowledge_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_semantic_vectors_kind ON semantic_vectors(vector_kind)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_semantic_vectors_item_uid ON semantic_vectors(item_uid)")

        # Durable embedding cache used by semantic workflow providers. Vectors are
        # stored as JSON to keep base installs independent from sqlite-vec.
        c.execute("""
            CREATE TABLE IF NOT EXISTS embedding_cache (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id  TEXT NOT NULL,
                text_hash    TEXT NOT NULL,
                dimension    INTEGER NOT NULL,
                vector       TEXT NOT NULL,
                text         TEXT NOT NULL DEFAULT '',
                created_at   TEXT NOT NULL,
                last_used_at TEXT NOT NULL,
                hit_count    INTEGER NOT NULL DEFAULT 0,
                UNIQUE(provider_id, dimension, text_hash)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_embedding_cache_provider_dim ON embedding_cache(provider_id, dimension)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_embedding_cache_last_used ON embedding_cache(last_used_at)")

        # Memory curator candidate queue. Candidates are intentionally separate
        # from active knowledge until explicitly promoted.
        c.execute("""
            CREATE TABLE IF NOT EXISTS memory_candidates (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                layer TEXT NOT NULL,
                category TEXT NOT NULL,
                tags TEXT NOT NULL,
                trust REAL NOT NULL,
                source TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL,
                privacy_status TEXT NOT NULL,
                duplicate_status TEXT NOT NULL,
                quality_status TEXT NOT NULL DEFAULT 'pass',
                gate_payload_json TEXT NOT NULL,
                promoted_knowledge_id INTEGER,
                FOREIGN KEY (promoted_knowledge_id) REFERENCES knowledge(id)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_candidates_status ON memory_candidates(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_candidates_privacy ON memory_candidates(privacy_status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_candidates_duplicate ON memory_candidates(duplicate_status)")
        self._ensure_table_columns(
            "memory_candidates",
            {"quality_status": "TEXT NOT NULL DEFAULT 'pass'"},
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_candidates_quality ON memory_candidates(quality_status)")

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

        # 本機技能登錄表 — 跨 Agent 技能註冊與同步
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
        c.execute(f"PRAGMA user_version={self.SCHEMA_VERSION}")
        self._record_migrations_through(self.SCHEMA_VERSION)
        c.commit()

    def _ensure_schema_migrations_table(self) -> None:
        """Create explicit schema migration metadata table."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    INTEGER PRIMARY KEY,
                name       TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
        """)

    def _record_migrations_through(self, target_version: int) -> None:
        """Record known migrations up to target_version without duplicating rows."""
        now = datetime.now(timezone.utc).isoformat()
        for version in range(1, target_version + 1):
            name = self.MIGRATIONS.get(version, f"schema_v{version}")
            self.conn.execute(
                """INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
                   VALUES(?, ?, ?)""",
                (version, name, now),
            )

    def applied_migrations(self) -> list[dict]:
        """Return applied schema migration metadata rows."""
        self._ensure_schema_migrations_table()
        rows = self.conn.execute(
            "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()
        return [dict(row) for row in rows]

    def _table_names(self) -> set[str]:
        rows = self.conn.execute(
            """SELECT name FROM sqlite_master
               WHERE type IN ('table', 'virtual table') AND name NOT LIKE 'sqlite_%'"""
        ).fetchall()
        return {row["name"] for row in rows}

    def _config_schema_version(self) -> int:
        try:
            value = self._get_config("schema_version", "0")
            return int(value or 0)
        except (TypeError, ValueError, sqlite3.OperationalError):
            return 0

    def schema_status(self) -> dict:
        """Return a JSON-safe schema status summary for operators and tests."""
        self._ensure_schema_migrations_table()
        config_version = self._config_schema_version()
        user_version = int(self.conn.execute("PRAGMA user_version").fetchone()[0] or 0)
        migration_versions = [int(row["version"]) for row in self.applied_migrations()]
        current_version = max([config_version, user_version, *migration_versions, 0])
        tables = self._table_names()
        required_tables = {
            "config",
            "knowledge",
            "schema_migrations",
            "knowledge_nodes",
            "knowledge_claims",
            "semantic_vectors",
            "embedding_cache",
            "memory_candidates",
            "content_log",
            "skills",
            "lint_cache",
            "edges",
            "entities",
            "entity_knowledge",
        }
        missing = sorted(required_tables - tables)
        return {
            "current_version": current_version,
            "target_version": self.SCHEMA_VERSION,
            "config_schema_version": config_version,
            "pragma_user_version": user_version,
            "needs_migration": current_version < self.SCHEMA_VERSION or bool(missing),
            "applied_migrations": self.applied_migrations(),
            "db_path": str(self.db_path),
            "table_count": len(tables),
            "tables_present": sorted(tables & required_tables),
            "tables_missing": missing,
        }

    def migrate(self, target_version: int | None = None) -> dict:
        """Run idempotent schema migrations and return a JSON-safe summary."""
        target = self.SCHEMA_VERSION if target_version is None else int(target_version)
        if target != self.SCHEMA_VERSION:
            raise ValueError(f"unsupported target schema version: {target}")
        before = self.schema_status()
        before_versions = {row["version"] for row in before["applied_migrations"]}
        self._init_tables()
        after = self.schema_status()
        after_versions = {row["version"] for row in after["applied_migrations"]}
        return {
            "ok": not after["needs_migration"],
            "db_path": str(self.db_path),
            "from_version": before["current_version"],
            "to_version": after["current_version"],
            "target_version": self.SCHEMA_VERSION,
            "applied_versions": sorted(after_versions - before_versions),
            "before": before,
            "after": after,
        }

    def _table_columns(self, table: str) -> set[str]:
        """Return existing column names for a SQLite table."""
        return {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}

    def _ensure_table_columns(self, table: str, columns: dict[str, str]) -> None:
        """Add missing columns to an existing table without bumping schema_version."""
        existing_cols = self._table_columns(table)
        for column_name, column_def in columns.items():
            if column_name not in existing_cols:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_def}")

    def _backfill_claim_uids(self) -> None:
        """Populate canonical claim_uid for rows migrated from the pre-canonical table."""
        rows = self.conn.execute(
            """SELECT id, claim, line_start, line_end
               FROM knowledge_claims
               WHERE claim_uid IS NULL OR claim_uid=''"""
        ).fetchall()
        for row in rows:
            line_start = int(row["line_start"] or 0)
            line_end = int(row["line_end"] or line_start)
            claim = row["claim"] or ""
            digest = hashlib.sha256(f"{line_start}:{line_end}:{claim}".encode()).hexdigest()[:16]
            claim_uid = f"c-{line_start}-{digest}"
            self.conn.execute(
                "UPDATE knowledge_claims SET claim_uid=? WHERE id=?",
                (claim_uid, row["id"]),
            )

    def _init_fts_table(self) -> None:
        """Create and backfill the optional FTS5 keyword index."""
        self._fts_available = False
        try:
            self.conn.execute(
                """CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
                    title,
                    content_raw,
                    content_aaak,
                    tags,
                    category,
                    tokenize='unicode61'
                )"""
            )
            self._fts_available = True
            self._rebuild_fts_index_if_empty()
        except sqlite3.OperationalError:
            self._fts_available = False

    def _rebuild_fts_index_if_empty(self) -> None:
        """Backfill FTS rows for existing databases without rebuilding every connect."""
        if not self._fts_available:
            return
        row = self.conn.execute("SELECT count(*) AS count FROM knowledge_fts").fetchone()
        if row and int(row["count"]) > 0:
            return
        self.conn.execute(
            """INSERT INTO knowledge_fts(rowid, title, content_raw, content_aaak, tags, category)
               SELECT id, title, content_raw, content_aaak, tags, category FROM knowledge"""
        )

    def _sync_fts_row(self, knowledge_id: int) -> None:
        """Synchronize one knowledge row into the optional FTS5 index."""
        if not self._fts_available:
            return
        row = self.conn.execute(
            "SELECT id, title, content_raw, content_aaak, tags, category FROM knowledge WHERE id=?",
            (knowledge_id,),
        ).fetchone()
        if not row:
            return
        self.conn.execute("DELETE FROM knowledge_fts WHERE rowid=?", (knowledge_id,))
        self.conn.execute(
            """INSERT INTO knowledge_fts(rowid, title, content_raw, content_aaak, tags, category)
               VALUES(?,?,?,?,?,?)""",
            (
                row["id"],
                row["title"],
                row["content_raw"],
                row["content_aaak"],
                row["tags"],
                row["category"],
            ),
        )

    def _delete_fts_row(self, knowledge_id: int) -> None:
        """Remove one knowledge row from the optional FTS5 index."""
        if self._fts_available:
            self.conn.execute("DELETE FROM knowledge_fts WHERE rowid=?", (knowledge_id,))

    @staticmethod
    def _quote_fts_token(token: str) -> str:
        return '"' + token.replace('"', '""') + '"'

    def search_fts_keyword(
        self,
        terms: list[str],
        limit: int = 10,
        min_trust: float = 0.0,
        layer: Optional[str] = None,
        category: Optional[str] = None,
    ) -> list[dict]:
        """Keyword search using optional FTS5 + BM25. Raises if unavailable/bad query."""
        if not self._fts_available:
            raise RuntimeError("SQLite FTS5 is unavailable")
        match_query = " OR ".join(self._quote_fts_token(term) for term in terms if term)
        if not match_query:
            return []

        filters = ["k.trust >= ?"]
        params: list = [match_query, min_trust]
        if layer:
            filters.append("k.layer=?")
            params.append(layer)
        if category:
            filters.append("k.category=?")
            params.append(category)
        where = " AND ".join(filters)
        params.append(limit)

        rows = self.conn.execute(
            f"""SELECT k.*, bm25(knowledge_fts) AS _bm25
                FROM knowledge_fts
                JOIN knowledge k ON k.id = knowledge_fts.rowid
               WHERE knowledge_fts MATCH ? AND {where}
               ORDER BY _bm25 ASC, k.trust DESC
               LIMIT ?""",
            params,
        ).fetchall()
        return [dict(row) for row in rows]

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
                print(f"[vault-mcp] ⚠️ 向量表維度不匹配，重建中（舊向量會遺失）: {e}", file=sys.stderr)
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
        knowledge_id = int(cursor.lastrowid)
        self._sync_fts_row(knowledge_id)
        self.conn.commit()
        return knowledge_id

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
        self._sync_fts_row(id)
        self.conn.commit()
        return True

    def get_knowledge(self, id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM knowledge WHERE id=?", (id,)
        ).fetchone()
        return dict(row) if row else None

    def delete_knowledge(self, id: int) -> bool:
        self._delete_fts_row(id)
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

    # ── Memory candidate CRUD ───────────────────────────────

    def add_memory_candidate(self, candidate: dict) -> str:
        """Insert a memory candidate and return its id."""
        now = datetime.now(timezone.utc).isoformat()
        values = dict(candidate)
        values.setdefault("created_at", now)
        values.setdefault("updated_at", now)
        values.setdefault("promoted_knowledge_id", None)
        self.conn.execute(
            """INSERT INTO memory_candidates
               (id, created_at, updated_at, title, content, layer, category,
                tags, trust, source, source_ref, reason, status,
                privacy_status, duplicate_status, quality_status, gate_payload_json,
                promoted_knowledge_id)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                values["id"], values["created_at"], values["updated_at"],
                values["title"], values["content"], values["layer"],
                values["category"], values["tags"], values["trust"],
                values["source"], values["source_ref"], values["reason"],
                values["status"], values["privacy_status"],
                values["duplicate_status"], values.get("quality_status", "pass"),
                values["gate_payload_json"],
                values.get("promoted_knowledge_id"),
            ),
        )
        self.conn.commit()
        return str(values["id"])

    def get_memory_candidate(self, candidate_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM memory_candidates WHERE id=?", (candidate_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_memory_candidate(self, candidate_id: str, **fields) -> bool:
        if not fields:
            return False
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        sets = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [candidate_id]
        cur = self.conn.execute(f"UPDATE memory_candidates SET {sets} WHERE id=?", vals)
        self.conn.commit()
        return cur.rowcount > 0

    def list_memory_candidates(self, status: Optional[str] = None, limit: int = 100) -> list[dict]:
        query = "SELECT * FROM memory_candidates"
        params: list = []
        if status:
            query += " WHERE status=?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
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
        layer: Optional[str] = None,
        category: Optional[str] = None,
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

        # Step 2: 取得知識詳細資料（帶權限過濾）
        results = []
        # 建構 WHERE 條件
        where_conditions = ["id=?", "trust >= ?"]
        params: list = [0, min_trust]  # id 會在每個迭代中替換

        if layer is not None:
            where_conditions.append("layer = ?")
            params.append(layer)
        if category is not None:
            where_conditions.append("category = ?")
            params.append(category)

        where_clause = " AND ".join(where_conditions)
        sql = f"SELECT * FROM knowledge WHERE {where_clause}"

        for row in vec_rows:
            kid = row["knowledge_id"]
            dist = row["distance"]
            # dist 可能是 bytes 或 float
            if isinstance(dist, bytes):
                dist = struct.unpack("f", dist)[0]
            dist = float(dist)

            params[0] = kid  # 替換成當前 knowledge_id
            k_row = self.conn.execute(sql, params).fetchone()
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
        self,
        node_id: int,
        max_depth: int = 2,
        min_weight: float = 0.0,
        min_trust: float = 0.0,
        layer: Optional[str] = None,
        category: Optional[str] = None,
    ) -> list[dict]:
        """
        BFS 遍歷鄰居，回傳 (node_id, distance, path) 列表。
        max_depth: 最大跳數（預設 2）
        min_weight: 最小邊權重（過濾弱關聯）
        min_trust: 最小信任級別過濾
        layer: 分層過濾
        category: 分類過濾
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

        # 權限過濾：如果有設定 min_trust、layer 或 category，從 knowledge 表過濾
        if min_trust > 0.0 or layer is not None or category is not None:
            if not results:
                return results

            # 收集所有鄰居 ID
            neighbor_ids = [r["id"] for r in results]
            placeholders = ",".join("?" * len(neighbor_ids))

            # 建構 WHERE 條件
            where_conditions = [f"id IN ({placeholders})", "trust >= ?"]
            params: list = list(neighbor_ids) + [min_trust]

            if layer is not None:
                where_conditions.append("layer = ?")
                params.append(layer)
            if category is not None:
                where_conditions.append("category = ?")
                params.append(category)

            where_clause = " AND ".join(where_conditions)
            sql = f"SELECT id FROM knowledge WHERE {where_clause}"

            # 查詢符合條件的節點 ID
            valid_rows = self.conn.execute(sql, params).fetchall()
            valid_ids = {row["id"] for row in valid_rows}

            # 只保留符合條件的結果
            results = [r for r in results if r["id"] in valid_ids]

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
