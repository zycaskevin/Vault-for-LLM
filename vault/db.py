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
from typing import Optional, Any

from .diagnostics import embedding_stats
from .db_fts import delete_fts_row as db_fts_delete_fts_row
from .db_fts import init_fts_table as db_fts_init_fts_table
from .db_fts import quote_fts_token as db_fts_quote_fts_token
from .db_fts import rebuild_fts_index_if_empty as db_fts_rebuild_fts_index_if_empty
from .db_fts import search_fts_keyword as db_fts_search_fts_keyword
from .db_fts import sync_fts_row as db_fts_sync_fts_row
from .db_graph import add_edge as db_graph_add_edge
from .db_graph import add_entity as db_graph_add_entity
from .db_graph import delete_edge as db_graph_delete_edge
from .db_graph import get_edges as db_graph_get_edges
from .db_graph import get_entities_for_knowledge as db_graph_get_entities_for_knowledge
from .db_graph import get_knowledge_for_entity as db_graph_get_knowledge_for_entity
from .db_graph import get_neighbors as db_graph_get_neighbors
from .db_graph import link_entity_knowledge as db_graph_link_entity_knowledge
from .db_lifecycle import archive_expired_knowledge as db_lifecycle_archive_expired_knowledge
from .db_lifecycle import cold_store_expired_knowledge as db_lifecycle_cold_store_expired_knowledge
from .db_lifecycle import cold_store_preview_row as db_lifecycle_cold_store_preview_row
from .db_lifecycle import cold_store_safety as db_lifecycle_cold_store_safety
from .db_lifecycle import build_cold_store_summary as db_lifecycle_build_cold_store_summary
from .db_lifecycle import parse_timestamp as db_lifecycle_parse_timestamp
from .db_lifecycle import record_knowledge_access as db_lifecycle_record_knowledge_access
from .db_lifecycle import top_used_knowledge as db_lifecycle_top_used_knowledge
from .db_lifecycle import usage_stats as db_lifecycle_usage_stats
from .db_memory import add_memory_candidate as db_memory_add_memory_candidate
from .db_memory import get_memory_candidate as db_memory_get_memory_candidate
from .db_memory import list_memory_candidates as db_memory_list_memory_candidates
from .db_memory import list_memory_feedback as db_memory_list_memory_feedback
from .db_memory import memory_feedback_summary as db_memory_memory_feedback_summary
from .db_memory import record_memory_feedback as db_memory_record_memory_feedback
from .db_memory import update_memory_candidate as db_memory_update_memory_candidate
from .db_schema import (
    KNOWLEDGE_UPDATE_COLUMNS as DB_KNOWLEDGE_UPDATE_COLUMNS,
    MEMORY_CANDIDATE_UPDATE_COLUMNS as DB_MEMORY_CANDIDATE_UPDATE_COLUMNS,
    MIGRATIONS as DB_MIGRATIONS,
    SCHEMA_VERSION as DB_SCHEMA_VERSION,
    SKILL_UPDATE_COLUMNS as DB_SKILL_UPDATE_COLUMNS,
)
from .db_skills import add_skill as db_skills_add_skill
from .db_skills import delete_skill as db_skills_delete_skill
from .db_skills import get_skill as db_skills_get_skill
from .db_skills import list_skills as db_skills_list_skills
from .db_skills import mark_skill_synced as db_skills_mark_skill_synced
from .db_skills import search_skills as db_skills_search_skills
from .db_skills import update_skill as db_skills_update_skill
from .db_vector import add_embedding as db_vector_add_embedding
from .db_vector import init_vec_table as db_vector_init_vec_table
from .db_vector import search_vector as db_vector_search_vector
from .governance import normalize_allowed_agents, normalize_governance_metadata

# sqlite-vec 是可選依賴
_VEC_AVAILABLE = False
try:
    import sqlite_vec
    _VEC_AVAILABLE = True
except ImportError:
    pass


class VaultDB:
    """Vault-for-LLM 資料庫層。"""

    SCHEMA_VERSION = DB_SCHEMA_VERSION
    KNOWLEDGE_UPDATE_COLUMNS = DB_KNOWLEDGE_UPDATE_COLUMNS
    MEMORY_CANDIDATE_UPDATE_COLUMNS = DB_MEMORY_CANDIDATE_UPDATE_COLUMNS
    SKILL_UPDATE_COLUMNS = DB_SKILL_UPDATE_COLUMNS
    MIGRATIONS = DB_MIGRATIONS

    @staticmethod
    def _escape_like_pattern(term: str) -> str:
        """轉義 LIKE 模式中的特殊字符，防止通配符注入。"""
        return term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

    def __init__(self, db_path: str | Path = "vault.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn: Optional[sqlite3.Connection] = None
        self._vec_available = _VEC_AVAILABLE
        self._vec_load_error = "" if _VEC_AVAILABLE else "sqlite_vec package is not installed"
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
                self._vec_load_error = "Python sqlite3 build does not expose enable_load_extension"
            else:
                try:
                    self.conn.enable_load_extension(True)
                    sqlite_vec.load(self.conn)
                    self._vec_load_error = ""
                except Exception:
                    self._vec_available = False
                    self._vec_load_error = f"sqlite-vec extension could not be loaded: {sys.exc_info()[1]}"
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
                freshness          REAL  NOT NULL DEFAULT 1.0,
                scope              TEXT NOT NULL DEFAULT 'project',
                sensitivity        TEXT NOT NULL DEFAULT 'low',
                owner_agent        TEXT NOT NULL DEFAULT '',
                allowed_agents     TEXT NOT NULL DEFAULT '[]',
                memory_type        TEXT NOT NULL DEFAULT 'knowledge',
                expires_at         TEXT NOT NULL DEFAULT '',
                valid_from         TEXT NOT NULL DEFAULT '',
                valid_until        TEXT NOT NULL DEFAULT '',
                supersedes_id      INTEGER DEFAULT NULL,
                status             TEXT NOT NULL DEFAULT 'active',
                archived_at        TEXT NOT NULL DEFAULT '',
                last_accessed_at   TEXT NOT NULL DEFAULT '',
                access_count       INTEGER NOT NULL DEFAULT 0,
                citation_count     INTEGER NOT NULL DEFAULT 0
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
                "scope": "TEXT NOT NULL DEFAULT 'project'",
                "sensitivity": "TEXT NOT NULL DEFAULT 'low'",
                "owner_agent": "TEXT NOT NULL DEFAULT ''",
                "allowed_agents": "TEXT NOT NULL DEFAULT '[]'",
                "memory_type": "TEXT NOT NULL DEFAULT 'knowledge'",
                "expires_at": "TEXT NOT NULL DEFAULT ''",
                "valid_from": "TEXT NOT NULL DEFAULT ''",
                "valid_until": "TEXT NOT NULL DEFAULT ''",
                "supersedes_id": "INTEGER DEFAULT NULL",
                "status": "TEXT NOT NULL DEFAULT 'active'",
                "archived_at": "TEXT NOT NULL DEFAULT ''",
                "last_accessed_at": "TEXT NOT NULL DEFAULT ''",
                "access_count": "INTEGER NOT NULL DEFAULT 0",
                "citation_count": "INTEGER NOT NULL DEFAULT 0",
            },
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_layer ON knowledge(layer)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_category ON knowledge(category)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_trust ON knowledge(trust)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_scope ON knowledge(scope)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_sensitivity ON knowledge(sensitivity)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_owner_agent ON knowledge(owner_agent)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_memory_type ON knowledge(memory_type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_expires_at ON knowledge(expires_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_valid_window ON knowledge(valid_from, valid_until)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_supersedes ON knowledge(supersedes_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_status ON knowledge(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_last_accessed ON knowledge(last_accessed_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_access_count ON knowledge(access_count)")

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
                scope TEXT NOT NULL DEFAULT 'project',
                sensitivity TEXT NOT NULL DEFAULT 'low',
                owner_agent TEXT NOT NULL DEFAULT '',
                allowed_agents TEXT NOT NULL DEFAULT '[]',
                memory_type TEXT NOT NULL DEFAULT 'knowledge',
                expires_at TEXT NOT NULL DEFAULT '',
                valid_from TEXT NOT NULL DEFAULT '',
                valid_until TEXT NOT NULL DEFAULT '',
                supersedes_id INTEGER DEFAULT NULL,
                FOREIGN KEY (promoted_knowledge_id) REFERENCES knowledge(id)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_candidates_status ON memory_candidates(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_candidates_privacy ON memory_candidates(privacy_status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_candidates_duplicate ON memory_candidates(duplicate_status)")
        self._ensure_table_columns(
            "memory_candidates",
            {
                "quality_status": "TEXT NOT NULL DEFAULT 'pass'",
                "scope": "TEXT NOT NULL DEFAULT 'project'",
                "sensitivity": "TEXT NOT NULL DEFAULT 'low'",
                "owner_agent": "TEXT NOT NULL DEFAULT ''",
                "allowed_agents": "TEXT NOT NULL DEFAULT '[]'",
                "memory_type": "TEXT NOT NULL DEFAULT 'knowledge'",
                "expires_at": "TEXT NOT NULL DEFAULT ''",
                "valid_from": "TEXT NOT NULL DEFAULT ''",
                "valid_until": "TEXT NOT NULL DEFAULT ''",
                "supersedes_id": "INTEGER DEFAULT NULL",
            },
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_candidates_quality ON memory_candidates(quality_status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_candidates_scope ON memory_candidates(scope)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_candidates_sensitivity ON memory_candidates(sensitivity)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_candidates_owner_agent ON memory_candidates(owner_agent)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_candidates_memory_type ON memory_candidates(memory_type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_candidates_valid_window ON memory_candidates(valid_from, valid_until)")

        # Feedback events give automation a learning loop without letting it
        # silently rewrite policy. They record outcomes such as promoted,
        # rejected, or blocked candidate suggestions for later evaluation.
        c.execute("""
            CREATE TABLE IF NOT EXISTS memory_feedback_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                event_type TEXT NOT NULL DEFAULT 'candidate_outcome',
                candidate_id TEXT NOT NULL DEFAULT '',
                knowledge_id INTEGER,
                source TEXT NOT NULL DEFAULT '',
                source_ref TEXT NOT NULL DEFAULT '',
                memory_type TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT '',
                outcome TEXT NOT NULL,
                score REAL NOT NULL DEFAULT 0.0,
                reason TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}'
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_feedback_candidate ON memory_feedback_events(candidate_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_feedback_outcome ON memory_feedback_events(outcome)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_feedback_source ON memory_feedback_events(source)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_feedback_memory_type ON memory_feedback_events(memory_type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_feedback_category ON memory_feedback_events(category)")

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
            "memory_feedback_events",
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
        self._fts_available = db_fts_init_fts_table(self.conn)

    def _rebuild_fts_index_if_empty(self) -> None:
        """Backfill FTS rows for existing databases without rebuilding every connect."""
        db_fts_rebuild_fts_index_if_empty(self.conn, fts_available=self._fts_available)

    def _sync_fts_row(self, knowledge_id: int) -> None:
        """Synchronize one knowledge row into the optional FTS5 index."""
        db_fts_sync_fts_row(self.conn, knowledge_id, fts_available=self._fts_available)

    def _delete_fts_row(self, knowledge_id: int) -> None:
        """Remove one knowledge row from the optional FTS5 index."""
        db_fts_delete_fts_row(self.conn, knowledge_id, fts_available=self._fts_available)

    @staticmethod
    def _quote_fts_token(token: str) -> str:
        return db_fts_quote_fts_token(token)

    def search_fts_keyword(
        self,
        terms: list[str],
        limit: int = 10,
        min_trust: float = 0.0,
        layer: Optional[str] = None,
        category: Optional[str] = None,
    ) -> list[dict]:
        """Keyword search using optional FTS5 + BM25. Raises if unavailable/bad query."""
        return db_fts_search_fts_keyword(
            self.conn,
            fts_available=self._fts_available,
            terms=terms,
            limit=limit,
            min_trust=min_trust,
            layer=layer,
            category=category,
        )

    def _init_vec_table(self):
        """建立 sqlite-vec 向量虛擬表。"""
        db_vector_init_vec_table(self.conn, embedding_dim=self._get_config("embedding_dim", "384"))

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
        scope: str = "project",
        sensitivity: str = "low",
        owner_agent: str = "",
        allowed_agents: Any = None,
        memory_type: str = "knowledge",
        expires_at: str = "",
        valid_from: str = "",
        valid_until: str = "",
        supersedes_id: int | str | None = None,
    ) -> int:
        """新增一筆知識，回傳 id。"""
        now = datetime.now(timezone.utc).isoformat()
        content_hash = hashlib.sha256(content_raw.encode()).hexdigest()[:16]
        governance = normalize_governance_metadata(
            scope=scope,
            sensitivity=sensitivity,
            owner_agent=owner_agent,
            allowed_agents=allowed_agents,
            memory_type=memory_type,
            expires_at=expires_at,
            valid_from=valid_from,
            valid_until=valid_until,
            supersedes_id=supersedes_id,
        )

        cursor = self.conn.execute(
            """INSERT INTO knowledge
               (title, layer, category, tags, trust,
                content_raw, content_aaak, content_hash, source,
                summary, summary_generated_at,
                scope, sensitivity, owner_agent, allowed_agents, memory_type, expires_at,
                valid_from, valid_until, supersedes_id,
                created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (title, layer, category, tags, trust,
             content_raw, content_aaak, content_hash, source,
             summary, now if summary else '',
             governance["scope"], governance["sensitivity"], governance["owner_agent"],
             governance["allowed_agents"], governance["memory_type"], governance["expires_at"],
             governance["valid_from"], governance["valid_until"], governance["supersedes_id"],
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
        invalid = set(fields) - self.KNOWLEDGE_UPDATE_COLUMNS
        if invalid:
            raise ValueError(f"invalid knowledge update field(s): {sorted(invalid)}")
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
        exists = self.get_knowledge(id) is not None
        if not exists:
            return False
        self.conn.execute("DELETE FROM semantic_vectors WHERE knowledge_id=?", (id,))
        self.conn.execute("DELETE FROM knowledge_claims WHERE knowledge_id=?", (id,))
        self.conn.execute("DELETE FROM knowledge_nodes WHERE knowledge_id=?", (id,))
        self.conn.execute("DELETE FROM lint_cache WHERE knowledge_id=?", (id,))
        self.conn.execute("DELETE FROM entity_knowledge WHERE knowledge_id=?", (id,))
        self.conn.execute("DELETE FROM edges WHERE source_id=? OR target_id=?", (id, id))
        self._delete_fts_row(id)
        if self._vec_available:
            self.conn.execute(
                "DELETE FROM knowledge_vec WHERE knowledge_id=?", (id,)
            )
        self.conn.execute("DELETE FROM knowledge WHERE id=?", (id,))
        self.conn.commit()
        return True

    def list_knowledge(
        self,
        layer: Optional[str] = None,
        category: Optional[str] = None,
        min_trust: float = 0.0,
        limit: int = 100,
        include_archived: bool = False,
    ) -> list[dict]:
        """列出知識，支援分層/分類/信任篩選。"""
        query = "SELECT * FROM knowledge WHERE trust >= ?"
        params: list = [min_trust]
        if not include_archived:
            query += " AND COALESCE(status, 'active') != 'archived'"

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

    @staticmethod
    def _parse_timestamp(value: str) -> datetime | None:
        """Parse ISO-like timestamps stored in governance metadata."""
        return db_lifecycle_parse_timestamp(value)

    def record_knowledge_access(
        self,
        knowledge_ids: list[int] | tuple[int, ...] | set[int],
        *,
        cited: bool = False,
        accessed_at: str | None = None,
    ) -> int:
        """Record retrieval/citation usage counters for active knowledge rows.

        Usage tracking is intentionally lightweight and lossy: failures should not
        break search. Callers can use it for ranking, dream reports, and archive
        decisions without making telemetry a hard runtime dependency.
        """
        return db_lifecycle_record_knowledge_access(
            self.conn,
            knowledge_ids,
            cited=cited,
            accessed_at=accessed_at,
        )

    def top_used_knowledge(self, limit: int = 10, *, include_archived: bool = False) -> list[dict]:
        """Return the most frequently retrieved memories."""
        return db_lifecycle_top_used_knowledge(self.conn, limit=limit, include_archived=include_archived)

    def usage_stats(self, limit: int = 10) -> dict:
        """Return memory usage and lifecycle counters for operators/agents."""
        return db_lifecycle_usage_stats(self.conn, limit=limit)

    def archive_expired_knowledge(
        self,
        *,
        now: str | datetime | None = None,
        limit: int = 100,
        dry_run: bool = False,
        skip_used: bool = False,
        protected_scopes: list[str] | tuple[str, ...] | None = None,
        protected_sensitivities: list[str] | tuple[str, ...] | None = None,
    ) -> dict:
        """Archive active memories whose `expires_at` timestamp is in the past."""
        return db_lifecycle_archive_expired_knowledge(
            self.conn,
            now=now,
            limit=limit,
            dry_run=dry_run,
            skip_used=skip_used,
            protected_scopes=protected_scopes,
            protected_sensitivities=protected_sensitivities,
        )

    def cold_store_expired_knowledge(
        self,
        *,
        now: str | datetime | None = None,
        limit: int = 100,
        dry_run: bool = True,
        min_usage: int = 1,
        summary_max_chars: int = 360,
        protected_scopes: list[str] | tuple[str, ...] | None = None,
        protected_sensitivities: list[str] | tuple[str, ...] | None = None,
        protected_layers: list[str] | tuple[str, ...] | None = None,
        target_layer: str = "L3",
    ) -> dict:
        """Summarize and archive expired-but-used memories into cold storage.

        Cold storage is intentionally reversible: the original content stays in
        the row for audit/restore, while `status=archived` removes it from normal
        recall and `summary` keeps a compact review surface.
        """
        return db_lifecycle_cold_store_expired_knowledge(
            self.conn,
            update_knowledge=self.update_knowledge,
            now=now,
            limit=limit,
            dry_run=dry_run,
            min_usage=min_usage,
            summary_max_chars=summary_max_chars,
            protected_scopes=protected_scopes,
            protected_sensitivities=protected_sensitivities,
            protected_layers=protected_layers,
            target_layer=target_layer,
        )

    def _cold_store_preview_row(
        self,
        row: dict[str, Any],
        *,
        now_text: str,
        summary_max_chars: int,
        target_layer: str,
    ) -> dict[str, Any]:
        return db_lifecycle_cold_store_preview_row(
            row,
            now_text=now_text,
            summary_max_chars=summary_max_chars,
            target_layer=target_layer,
        )

    def _build_cold_store_summary(self, row: dict[str, Any], *, max_chars: int, now_text: str) -> str:
        return db_lifecycle_build_cold_store_summary(row, max_chars=max_chars, now_text=now_text)

    @staticmethod
    def _cold_store_safety() -> dict[str, bool]:
        return db_lifecycle_cold_store_safety()

    # ── Memory candidate CRUD ───────────────────────────────

    def add_memory_candidate(self, candidate: dict) -> str:
        """Insert a memory candidate and return its id."""
        return db_memory_add_memory_candidate(self.conn, candidate)

    def get_memory_candidate(self, candidate_id: str) -> Optional[dict]:
        return db_memory_get_memory_candidate(self.conn, candidate_id)

    def update_memory_candidate(self, candidate_id: str, **fields) -> bool:
        return db_memory_update_memory_candidate(
            self.conn,
            candidate_id,
            self.MEMORY_CANDIDATE_UPDATE_COLUMNS,
            **fields,
        )

    def list_memory_candidates(self, status: Optional[str] = None, limit: int = 100) -> list[dict]:
        return db_memory_list_memory_candidates(self.conn, status=status, limit=limit)

    # ── Memory feedback / automation learning ──────────────

    def record_memory_feedback(self, event: dict) -> int:
        """Record a candidate outcome event for automation evaluation."""
        return db_memory_record_memory_feedback(self.conn, event)

    def list_memory_feedback(
        self,
        *,
        limit: int = 100,
        source: str = "",
        memory_type: str = "",
        outcome: str = "",
    ) -> list[dict]:
        return db_memory_list_memory_feedback(
            self.conn,
            limit=limit,
            source=source,
            memory_type=memory_type,
            outcome=outcome,
        )

    def memory_feedback_summary(self, *, limit: int = 1000) -> dict:
        """Return JSON-safe feedback aggregates for automation evaluation."""
        return db_memory_memory_feedback_summary(self.conn, limit=limit)

    # ── 向量操作 ────────────────────────────────────────────

    def add_embedding(self, knowledge_id: int, embedding: list[float]):
        """插入向量到 vec0 表。"""
        db_vector_add_embedding(
            self.conn,
            vec_available=self._vec_available,
            knowledge_id=knowledge_id,
            embedding=embedding,
        )

    def search_vector(
        self,
        query_embedding: list[float],
        limit: int = 10,
        min_trust: float = 0.0,
        layer: Optional[str] = None,
        category: Optional[str] = None,
    ) -> list[dict]:
        """向量語意搜尋，回傳知識列表。"""
        return db_vector_search_vector(
            self.conn,
            vec_available=self._vec_available,
            embedding_dim=self._get_config("embedding_dim", "384"),
            query_embedding=query_embedding,
            limit=limit,
            min_trust=min_trust,
            layer=layer,
            category=category,
        )

    # ── 關鍵字搜尋 ──────────────────────────────────────────

    def search_keyword(
        self,
        query: str,
        limit: int = 10,
        min_trust: float = 0.0,
    ) -> list[dict]:
        """純關鍵字搜尋（LIKE匹配），降級方案。"""
        # None 查詢直接返回空結果
        if query is None:
            return []

        escaped = self._escape_like_pattern(query)
        pattern = f"%{escaped}%"

        sql = """
            SELECT *, 0.0 AS _score
            FROM knowledge
            WHERE trust >= ?
              AND COALESCE(status, 'active') != 'archived'
              AND (title LIKE ? ESCAPE '\\' OR content_raw LIKE ? ESCAPE '\\'
                   OR content_aaak LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\'
                   OR category LIKE ? ESCAPE '\\')
            ORDER BY trust DESC
            LIMIT ?
        """
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
        return db_graph_add_edge(
            self.conn,
            source_id,
            target_id,
            relation=relation,
            weight=weight,
            auto_inferred=auto_inferred,
        )

    def delete_edge(self, edge_id: int) -> bool:
        return db_graph_delete_edge(self.conn, edge_id)

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
        return db_graph_get_edges(self.conn, node_id=node_id, relation=relation, direction=direction)

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
        return db_graph_get_neighbors(
            self.conn,
            node_id,
            max_depth=max_depth,
            min_weight=min_weight,
            min_trust=min_trust,
            layer=layer,
            category=category,
        )

    # ── 實體操作 ────────────────────────────────────────────

    def add_entity(self, name: str, entity_type: str = "concept") -> int:
        """新增實體，回傳 entity id（已存在則回傳現有 id）。"""
        return db_graph_add_entity(self.conn, name, entity_type=entity_type)

    def link_entity_knowledge(self, entity_id: int, knowledge_id: int):
        """連結實體和知識條目。"""
        db_graph_link_entity_knowledge(self.conn, entity_id, knowledge_id)

    def get_entities_for_knowledge(self, knowledge_id: int) -> list[dict]:
        """取得知識條目關聯的所有實體。"""
        return db_graph_get_entities_for_knowledge(self.conn, knowledge_id)

    def get_knowledge_for_entity(self, entity_name: str) -> list[int]:
        """取得實體關聯的所有知識條目 ID（用於圖譜擴展搜尋）。"""
        return db_graph_get_knowledge_for_entity(self.conn, entity_name)

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
        return db_skills_add_skill(
            self.conn,
            name=name,
            content_raw=content_raw,
            version=version,
            agent_source=agent_source,
            category=category,
            capabilities=capabilities,
            dependencies=dependencies,
            trust=trust,
            description=description,
        )

    def update_skill(self, name: str, **fields) -> bool:
        """更新技能欄位（以 name 為 key）。"""
        return db_skills_update_skill(self.conn, name, self.SKILL_UPDATE_COLUMNS, **fields)

    def get_skill(self, name: str) -> Optional[dict]:
        """取得單一技能。"""
        return db_skills_get_skill(self.conn, name)

    def delete_skill(self, name: str) -> bool:
        """刪除技能。"""
        return db_skills_delete_skill(self.conn, name)

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
        return db_skills_search_skills(
            self.conn,
            query=query,
            capabilities=capabilities,
            category=category,
            min_trust=min_trust,
            agent_source=agent_source,
            limit=limit,
        )

    def list_skills(
        self,
        agent_source: Optional[str] = None,
        category: Optional[str] = None,
        min_trust: float = 0.0,
        limit: int = 100,
    ) -> list[dict]:
        """列出全部技能（不含 content_raw，輕量）。"""
        return db_skills_list_skills(
            self.conn,
            agent_source=agent_source,
            category=category,
            min_trust=min_trust,
            limit=limit,
        )

    def mark_skill_synced(self, name: str):
        """標記技能已同步到 Supabase。"""
        db_skills_mark_skill_synced(self.conn, name)

    # ── 統計 ────────────────────────────────────────────────

    def stats(self) -> dict:
        k_count = self.conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
        vector_stats = embedding_stats(self.conn, vec_available=self._vec_available)
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
        usage = self.usage_stats(limit=5)

        return {
            "knowledge_count": k_count,
            "active_count": int(usage.get("status_counts", {}).get("active", 0)),
            "archived_count": int(usage.get("status_counts", {}).get("archived", 0)),
            "expired_active_count": int(usage.get("expired_active_count", 0)),
            "total_accesses": int(usage.get("total_accesses", 0)),
            "total_citations": int(usage.get("total_citations", 0)),
            **vector_stats,
            "edge_count": edge_count,
            "entity_count": entity_count,
            "skill_count": skill_count,
            "vec_available": self._vec_available,
            "vec_load_error": self._vec_load_error,
            "db_path": str(self.db_path),
            "db_size_mb": round(self.db_path.stat().st_size / 1024 / 1024, 2) if self.db_path.exists() else 0,
            "convergence": conv_stats,
            "avg_freshness": avg_freshness,
        }
