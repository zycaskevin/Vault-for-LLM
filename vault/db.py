"""
Vault-for-LLM — SQLite + sqlite-vec 資料庫抽象層。

設計原則：
- 一個 .db 檔案搞定所有資料
- sqlite-vec 虛擬表處理向量搜尋
- metadata 放普通表，JOIN 搜尋
- 支援降級：沒裝 sqlite-vec 時退回純關鍵字
"""

import hashlib
import json
import sqlite3
import sys
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Any

from .diagnostics import embedding_stats
from .importance import compute_memory_importance

# sqlite-vec 是可選依賴
_VEC_AVAILABLE = False
try:
    import sqlite_vec
    _VEC_AVAILABLE = True
except ImportError:
    pass


_VALID_SCOPES = {"private", "project", "shared", "public"}
_VALID_SENSITIVITIES = {"low", "medium", "high", "restricted"}


def normalize_allowed_agents(value: Any = None) -> str:
    """Return allowed agent names as a compact JSON array string."""
    if value is None or value == "":
        return "[]"
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value if str(item).strip()]
        return json.dumps(items, ensure_ascii=False)
    text = str(value).strip()
    if not text:
        return "[]"
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            items = [str(item).strip() for item in parsed if str(item).strip()]
            return json.dumps(items, ensure_ascii=False)
    items = [part.strip() for part in text.split(",") if part.strip()]
    return json.dumps(items, ensure_ascii=False)


def normalize_governance_metadata(
    *,
    scope: str = "project",
    sensitivity: str = "low",
    owner_agent: str = "",
    allowed_agents: Any = None,
    memory_type: str = "knowledge",
    expires_at: str = "",
) -> dict[str, str]:
    """Normalize memory-governance fields shared by DB, CLI, MCP, and sync."""
    norm_scope = str(scope or "project").strip().lower()
    if norm_scope not in _VALID_SCOPES:
        norm_scope = "project"
    norm_sensitivity = str(sensitivity or "low").strip().lower()
    if norm_sensitivity not in _VALID_SENSITIVITIES:
        norm_sensitivity = "low"
    norm_memory_type = str(memory_type or "knowledge").strip() or "knowledge"
    if hasattr(expires_at, "isoformat"):
        norm_expires_at = expires_at.isoformat()
    else:
        norm_expires_at = str(expires_at or "").strip()
    return {
        "scope": norm_scope,
        "sensitivity": norm_sensitivity,
        "owner_agent": str(owner_agent or "").strip(),
        "allowed_agents": normalize_allowed_agents(allowed_agents),
        "memory_type": norm_memory_type,
        "expires_at": norm_expires_at,
    }


class VaultDB:
    """Vault-for-LLM 資料庫層。"""

    SCHEMA_VERSION = 10
    KNOWLEDGE_UPDATE_COLUMNS = {
        "title",
        "layer",
        "category",
        "tags",
        "trust",
        "content_raw",
        "content_aaak",
        "content_hash",
        "source",
        "convergence_status",
        "convergence_score",
        "convergence_checked_at",
        "last_verified",
        "freshness",
        "summary",
        "summary_generated_at",
        "scope",
        "sensitivity",
        "owner_agent",
        "allowed_agents",
        "memory_type",
        "expires_at",
        "status",
        "archived_at",
        "last_accessed_at",
        "access_count",
        "citation_count",
        "updated_at",
    }
    MEMORY_CANDIDATE_UPDATE_COLUMNS = {
        "updated_at",
        "title",
        "content",
        "layer",
        "category",
        "tags",
        "trust",
        "source",
        "source_ref",
        "reason",
        "status",
        "privacy_status",
        "duplicate_status",
        "quality_status",
        "gate_payload_json",
        "promoted_knowledge_id",
        "scope",
        "sensitivity",
        "owner_agent",
        "allowed_agents",
        "memory_type",
        "expires_at",
    }
    SKILL_UPDATE_COLUMNS = {
        "name",
        "version",
        "agent_source",
        "category",
        "capabilities",
        "dependencies",
        "trust",
        "content_raw",
        "content_hash",
        "description",
        "updated_at",
        "last_synced",
    }
    MIGRATIONS = {
        1: "initial_core_tables",
        2: "graph_and_skill_tables",
        3: "convergence_freshness_columns",
        4: "knowledge_summary_columns",
        5: "document_map_semantic_tables",
        6: "memory_candidate_table",
        7: "memory_candidate_quality_status",
        8: "governance_metadata_columns",
        9: "memory_usage_and_archive_columns",
        10: "memory_feedback_events",
    }

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
            },
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_candidates_quality ON memory_candidates(quality_status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_candidates_scope ON memory_candidates(scope)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_candidates_sensitivity ON memory_candidates(sensitivity)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_candidates_owner_agent ON memory_candidates(owner_agent)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memory_candidates_memory_type ON memory_candidates(memory_type)")

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
        # 防範超長 token 導致 FTS5 解析問題
        if len(token) > 100:
            token = token[:100]
        # 雙引號包裹 + 轉義雙引號，確保作為字面量處理
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
            raise RuntimeError("全文搜尋功能未啟用")
        # 安全上限：FTS5 查詢術語數量限制，避免過多 OR 術語導致性能問題
        MAX_FTS_TERMS = 50
        filtered_terms = [term for term in terms if term]
        if len(filtered_terms) > MAX_FTS_TERMS:
            filtered_terms = filtered_terms[:MAX_FTS_TERMS]
        match_query = " OR ".join(self._quote_fts_token(term) for term in filtered_terms)
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
                 AND COALESCE(k.status, 'active') != 'archived'
               ORDER BY _bm25 ASC, k.trust DESC
               LIMIT ?""",
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def _init_vec_table(self):
        """建立 sqlite-vec 向量虛擬表。"""
        # 取得嵌入維度（預設 384）
        dim_str = self._get_config("embedding_dim", "384")
        # 安全驗證：確保維度是正整數且在合理範圍內，防止 SQL 注入
        try:
            dim = int(dim_str)
            if dim < 64 or dim > 4096:
                raise ValueError(f"embedding_dim out of range: {dim}")
        except (ValueError, TypeError):
            dim = 384  # 安全預設值
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
                print("[vault-mcp] ⚠️ 向量表初始化異常，正在重建", file=sys.stderr)
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
        scope: str = "project",
        sensitivity: str = "low",
        owner_agent: str = "",
        allowed_agents: Any = None,
        memory_type: str = "knowledge",
        expires_at: str = "",
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
        )

        cursor = self.conn.execute(
            """INSERT INTO knowledge
               (title, layer, category, tags, trust,
                content_raw, content_aaak, content_hash, source,
                summary, summary_generated_at,
                scope, sensitivity, owner_agent, allowed_agents, memory_type, expires_at,
                created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (title, layer, category, tags, trust,
             content_raw, content_aaak, content_hash, source,
             summary, now if summary else '',
             governance["scope"], governance["sensitivity"], governance["owner_agent"],
             governance["allowed_agents"], governance["memory_type"], governance["expires_at"],
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
        text = str(value or "").strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = datetime.fromisoformat(f"{text}T00:00:00+00:00")
            except ValueError:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

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
        ids = sorted({int(kid) for kid in knowledge_ids if kid})
        if not ids:
            return 0
        now = accessed_at or datetime.now(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in ids)
        citation_sql = ", citation_count = citation_count + 1" if cited else ""
        cur = self.conn.execute(
            f"""UPDATE knowledge
                   SET access_count = access_count + 1,
                       last_accessed_at = ?
                       {citation_sql}
                 WHERE id IN ({placeholders})
                   AND COALESCE(status, 'active') != 'archived'""",
            [now, *ids],
        )
        self.conn.commit()
        return int(cur.rowcount or 0)

    def top_used_knowledge(self, limit: int = 10, *, include_archived: bool = False) -> list[dict]:
        """Return the most frequently retrieved memories."""
        limit_i = max(1, min(int(limit or 10), 1000))
        where = ""
        if not include_archived:
            where = "WHERE COALESCE(status, 'active') != 'archived'"
        rows = self.conn.execute(
            f"""SELECT id, title, layer, category, trust, freshness,
                       scope, sensitivity, memory_type, expires_at, status,
                       access_count, citation_count, last_accessed_at, updated_at
                  FROM knowledge
                  {where}
                 ORDER BY access_count DESC, citation_count DESC, last_accessed_at DESC, updated_at DESC
                 LIMIT ?""",
            (limit_i,),
        ).fetchall()
        return [dict(row) for row in rows]

    def usage_stats(self, limit: int = 10) -> dict:
        """Return memory usage and lifecycle counters for operators/agents."""
        now = datetime.now(timezone.utc)
        rows = self.conn.execute(
            """SELECT status, expires_at, access_count, citation_count
                 FROM knowledge"""
        ).fetchall()
        status_counts: dict[str, int] = {}
        expired_active = 0
        total_accesses = 0
        total_citations = 0
        for row in rows:
            status = str(row["status"] or "active")
            status_counts[status] = status_counts.get(status, 0) + 1
            total_accesses += int(row["access_count"] or 0)
            total_citations += int(row["citation_count"] or 0)
            expires_at = self._parse_timestamp(row["expires_at"])
            if status != "archived" and expires_at is not None and expires_at <= now:
                expired_active += 1
        return {
            "knowledge_count": len(rows),
            "status_counts": status_counts,
            "expired_active_count": expired_active,
            "total_accesses": total_accesses,
            "total_citations": total_citations,
            "top_used": self.top_used_knowledge(limit=limit),
        }

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
        if isinstance(now, datetime):
            now_dt = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
            now_text = now_dt.isoformat()
        elif now:
            parsed = self._parse_timestamp(str(now))
            now_dt = parsed or datetime.now(timezone.utc)
            now_text = now_dt.isoformat()
        else:
            now_dt = datetime.now(timezone.utc)
            now_text = now_dt.isoformat()

        limit_i = max(1, min(int(limit or 100), 10000))
        rows = self.conn.execute(
            """SELECT id, title, layer, category, trust, freshness,
                      memory_type, scope, sensitivity, status, expires_at,
                      access_count, citation_count, last_accessed_at
                 FROM knowledge
                WHERE COALESCE(status, 'active') != 'archived'
                  AND COALESCE(expires_at, '') != ''
                ORDER BY expires_at ASC, id ASC
                LIMIT ?""",
            (limit_i,),
        ).fetchall()
        expired = []
        for row in rows:
            expires_at = self._parse_timestamp(row["expires_at"])
            if expires_at is not None and expires_at <= now_dt:
                expired.append(dict(row))
        protected_scope_set = {str(value).strip().lower() for value in (protected_scopes or []) if str(value).strip()}
        protected_sensitivity_set = {
            str(value).strip().lower() for value in (protected_sensitivities or []) if str(value).strip()
        }
        skipped_used = []
        skipped_protected = []
        archiveable = []
        for row in expired:
            scope = str(row.get("scope") or "").strip().lower()
            sensitivity = str(row.get("sensitivity") or "").strip().lower()
            if scope in protected_scope_set or sensitivity in protected_sensitivity_set:
                skipped_protected.append(row)
                continue
            usage_count = int(row.get("access_count") or 0) + int(row.get("citation_count") or 0)
            if skip_used and usage_count > 0:
                skipped_used.append(row)
            else:
                archiveable.append(row)

        if dry_run or not archiveable:
            return {
                "action": "archive-expired",
                "dry_run": bool(dry_run),
                "archived_count": 0,
                "eligible_count": len(expired),
                "skipped_used_count": len(skipped_used),
                "skipped_protected_count": len(skipped_protected),
                "now": now_text,
                "items": archiveable,
                "skipped_used": skipped_used,
                "skipped_protected": skipped_protected,
            }

        ids = [int(row["id"]) for row in archiveable]
        placeholders = ",".join("?" for _ in ids)
        self.conn.execute(
            f"""UPDATE knowledge
                   SET status='archived',
                       archived_at=?,
                       updated_at=?
                 WHERE id IN ({placeholders})""",
            [now_text, now_text, *ids],
        )
        self.conn.commit()
        return {
            "action": "archive-expired",
            "dry_run": False,
            "archived_count": len(ids),
            "eligible_count": len(expired),
            "skipped_used_count": len(skipped_used),
            "skipped_protected_count": len(skipped_protected),
            "now": now_text,
            "items": archiveable,
            "skipped_used": skipped_used,
            "skipped_protected": skipped_protected,
        }

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
        if isinstance(now, datetime):
            now_dt = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
            now_text = now_dt.isoformat()
        elif now:
            parsed = self._parse_timestamp(str(now))
            now_dt = parsed or datetime.now(timezone.utc)
            now_text = now_dt.isoformat()
        else:
            now_dt = datetime.now(timezone.utc)
            now_text = now_dt.isoformat()

        limit_i = max(1, min(int(limit or 100), 10000))
        min_usage_i = max(1, int(min_usage or 1))
        summary_chars = max(80, min(int(summary_max_chars or 360), 2000))
        target_layer_text = str(target_layer or "L3").strip() or "L3"
        protected_scope_set = {str(value).strip().lower() for value in (protected_scopes or ["private"]) if str(value).strip()}
        protected_sensitivity_set = {
            str(value).strip().lower()
            for value in (protected_sensitivities or ["high", "restricted"])
            if str(value).strip()
        }
        protected_layer_set = {str(value).strip().upper() for value in (protected_layers or ["L0", "L1"]) if str(value).strip()}

        rows = self.conn.execute(
            """SELECT id, title, layer, category, tags, trust, freshness,
                      content_raw, summary, last_accessed_at,
                      memory_type, scope, sensitivity, status, expires_at,
                      access_count, citation_count
                 FROM knowledge
                WHERE COALESCE(status, 'active') != 'archived'
                  AND COALESCE(expires_at, '') != ''
                ORDER BY expires_at ASC, id ASC
                LIMIT ?""",
            (limit_i,),
        ).fetchall()

        candidates: list[dict[str, Any]] = []
        skipped_low_usage: list[dict[str, Any]] = []
        skipped_protected: list[dict[str, Any]] = []
        for row_obj in rows:
            row = dict(row_obj)
            expires_at = self._parse_timestamp(row["expires_at"])
            if expires_at is None or expires_at > now_dt:
                continue
            usage_count = int(row.get("access_count") or 0) + int(row.get("citation_count") or 0)
            compact = self._cold_store_preview_row(row, now_text=now_text, summary_max_chars=summary_chars, target_layer=target_layer_text)
            if str(row.get("layer") or "").strip().upper() in protected_layer_set:
                compact["skip_reason"] = "protected_layer"
                skipped_protected.append(compact)
                continue
            if str(row.get("scope") or "").strip().lower() in protected_scope_set:
                compact["skip_reason"] = "protected_scope"
                skipped_protected.append(compact)
                continue
            if str(row.get("sensitivity") or "").strip().lower() in protected_sensitivity_set:
                compact["skip_reason"] = "protected_sensitivity"
                skipped_protected.append(compact)
                continue
            if usage_count < min_usage_i:
                compact["skip_reason"] = "usage_below_threshold"
                skipped_low_usage.append(compact)
                continue
            candidates.append(compact)
        candidates.sort(
            key=lambda item: (
                float(item.get("importance_score") or 0.0),
                int(item.get("citation_count") or 0),
                int(item.get("access_count") or 0),
                int(item.get("id") or 0),
            ),
            reverse=True,
        )
        skipped_low_usage.sort(key=lambda item: (float(item.get("importance_score") or 0.0), int(item.get("id") or 0)), reverse=True)
        skipped_protected.sort(key=lambda item: (float(item.get("importance_score") or 0.0), int(item.get("id") or 0)), reverse=True)

        if dry_run or not candidates:
            return {
                "action": "cold-store-expired",
                "dry_run": bool(dry_run),
                "applied_count": 0,
                "eligible_count": len(candidates),
                "skipped_low_usage_count": len(skipped_low_usage),
                "skipped_protected_count": len(skipped_protected),
                "min_usage": min_usage_i,
                "target_layer": target_layer_text,
                "now": now_text,
                "items": candidates,
                "skipped_low_usage": skipped_low_usage,
                "skipped_protected": skipped_protected,
                "safety": self._cold_store_safety(),
            }

        applied = []
        demoted_count = 0
        for item in candidates:
            kid = int(item["id"])
            before_layer = str(item.get("layer") or "")
            after_layer = str(item.get("target_layer") or target_layer_text)
            if before_layer != after_layer:
                demoted_count += 1
            self.update_knowledge(
                kid,
                status="archived",
                archived_at=now_text,
                summary=item["summary"],
                summary_generated_at=now_text,
                layer=after_layer,
                freshness=0.0,
            )
            applied.append({**item, "status_after": "archived"})

        return {
            "action": "cold-store-expired",
            "dry_run": False,
            "applied_count": len(applied),
            "summary_count": len(applied),
            "demoted_count": demoted_count,
            "eligible_count": len(candidates),
            "skipped_low_usage_count": len(skipped_low_usage),
            "skipped_protected_count": len(skipped_protected),
            "min_usage": min_usage_i,
            "target_layer": target_layer_text,
            "now": now_text,
            "items": applied,
            "skipped_low_usage": skipped_low_usage,
            "skipped_protected": skipped_protected,
            "safety": self._cold_store_safety(),
        }

    def _cold_store_preview_row(
        self,
        row: dict[str, Any],
        *,
        now_text: str,
        summary_max_chars: int,
        target_layer: str,
    ) -> dict[str, Any]:
        access = int(row.get("access_count") or 0)
        citations = int(row.get("citation_count") or 0)
        importance = compute_memory_importance(row, now=self._parse_timestamp(now_text) or datetime.now(timezone.utc))
        summary = self._build_cold_store_summary(row, max_chars=summary_max_chars, now_text=now_text)
        return {
            "id": int(row.get("id") or 0),
            "title": row.get("title", ""),
            "layer": row.get("layer", ""),
            "target_layer": target_layer,
            "category": row.get("category", ""),
            "memory_type": row.get("memory_type", ""),
            "scope": row.get("scope", ""),
            "sensitivity": row.get("sensitivity", ""),
            "expires_at": row.get("expires_at", ""),
            "access_count": access,
            "citation_count": citations,
            "usage_count": access + citations,
            "importance_score": importance["importance_score"],
            "importance_components": importance["importance_components"],
            "importance_signals": importance["signals"],
            "importance_recommendation": importance["recommendation"],
            "summary": summary,
            "operation": "summarize_then_cold_store",
        }

    def _build_cold_store_summary(self, row: dict[str, Any], *, max_chars: int, now_text: str) -> str:
        title = str(row.get("title") or "").strip()
        existing = str(row.get("summary") or "").strip()
        content = existing or str(row.get("content_raw") or "").strip()
        content = re.sub(r"\s+", " ", content)
        try:
            from .privacy import redact_secrets

            content = redact_secrets(content)
            title = redact_secrets(title)
        except Exception:
            pass
        if len(content) > max_chars:
            content = content[: max_chars - 1].rstrip() + "…"
        access = int(row.get("access_count") or 0)
        citations = int(row.get("citation_count") or 0)
        prefix = f"Cold-store summary for '{title}'"
        return (
            f"{prefix}: {content} "
            f"(archived_at={now_text}; previous_usage access={access}, citations={citations}; "
            "original content retained in vault.db for audit/restore)."
        )

    @staticmethod
    def _cold_store_safety() -> dict[str, bool]:
        return {
            "hard_delete": False,
            "original_content_retained": True,
            "normal_recall_removed": True,
            "summary_written": True,
            "protected_private_high_restricted_skipped": True,
        }

    # ── Memory candidate CRUD ───────────────────────────────

    def add_memory_candidate(self, candidate: dict) -> str:
        """Insert a memory candidate and return its id."""
        now = datetime.now(timezone.utc).isoformat()
        values = dict(candidate)
        values.setdefault("created_at", now)
        values.setdefault("updated_at", now)
        values.setdefault("promoted_knowledge_id", None)
        governance = normalize_governance_metadata(
            scope=values.get("scope", "project"),
            sensitivity=values.get("sensitivity", "low"),
            owner_agent=values.get("owner_agent", ""),
            allowed_agents=values.get("allowed_agents"),
            memory_type=values.get("memory_type", "knowledge"),
            expires_at=values.get("expires_at", ""),
        )
        values.update(governance)
        self.conn.execute(
            """INSERT INTO memory_candidates
               (id, created_at, updated_at, title, content, layer, category,
                tags, trust, source, source_ref, reason, status,
                privacy_status, duplicate_status, quality_status, gate_payload_json,
                promoted_knowledge_id,
                scope, sensitivity, owner_agent, allowed_agents, memory_type, expires_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                values["id"], values["created_at"], values["updated_at"],
                values["title"], values["content"], values["layer"],
                values["category"], values["tags"], values["trust"],
                values["source"], values["source_ref"], values["reason"],
                values["status"], values["privacy_status"],
                values["duplicate_status"], values.get("quality_status", "pass"),
                values["gate_payload_json"],
                values.get("promoted_knowledge_id"),
                values["scope"], values["sensitivity"], values["owner_agent"],
                values["allowed_agents"], values["memory_type"], values["expires_at"],
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
        invalid = set(fields) - self.MEMORY_CANDIDATE_UPDATE_COLUMNS
        if invalid:
            raise ValueError(f"invalid memory candidate update field(s): {sorted(invalid)}")
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

    # ── Memory feedback / automation learning ──────────────

    def record_memory_feedback(self, event: dict) -> int:
        """Record a candidate outcome event for automation evaluation."""
        now = datetime.now(timezone.utc).isoformat()
        values = dict(event)
        values.setdefault("created_at", now)
        values.setdefault("event_type", "candidate_outcome")
        values.setdefault("candidate_id", "")
        values.setdefault("knowledge_id", None)
        values.setdefault("source", "")
        values.setdefault("source_ref", "")
        values.setdefault("memory_type", "")
        values.setdefault("category", "")
        values.setdefault("outcome", "")
        values.setdefault("score", 0.0)
        values.setdefault("reason", "")
        payload = values.get("payload_json", "{}")
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        values["payload_json"] = str(payload or "{}")
        cur = self.conn.execute(
            """INSERT INTO memory_feedback_events
               (created_at, event_type, candidate_id, knowledge_id, source, source_ref,
                memory_type, category, outcome, score, reason, payload_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                values["created_at"],
                values["event_type"],
                values["candidate_id"],
                values.get("knowledge_id"),
                values["source"],
                values["source_ref"],
                values["memory_type"],
                values["category"],
                values["outcome"],
                float(values.get("score") or 0.0),
                values["reason"],
                values["payload_json"],
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_memory_feedback(
        self,
        *,
        limit: int = 100,
        source: str = "",
        memory_type: str = "",
        outcome: str = "",
    ) -> list[dict]:
        query = "SELECT * FROM memory_feedback_events"
        clauses = []
        params: list[Any] = []
        if source:
            clauses.append("source = ?")
            params.append(source)
        if memory_type:
            clauses.append("memory_type = ?")
            params.append(memory_type)
        if outcome:
            clauses.append("outcome = ?")
            params.append(outcome)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(max(1, min(int(limit or 100), 1000)))
        rows = self.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def memory_feedback_summary(self, *, limit: int = 1000) -> dict:
        """Return JSON-safe feedback aggregates for automation evaluation."""
        limit_i = max(1, min(int(limit or 1000), 10000))
        rows = self.conn.execute(
            """SELECT * FROM memory_feedback_events
               ORDER BY created_at DESC, id DESC
               LIMIT ?""",
            (limit_i,),
        ).fetchall()
        events = [dict(row) for row in rows]
        outcome_counts: dict[str, int] = {}
        groups: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in events:
            outcome = str(row.get("outcome") or "unknown")
            outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
            key = (
                str(row.get("source") or ""),
                str(row.get("memory_type") or ""),
                str(row.get("category") or ""),
            )
            group = groups.setdefault(
                key,
                {
                    "source": key[0],
                    "memory_type": key[1],
                    "category": key[2],
                    "total": 0,
                    "accepted": 0,
                    "promoted": 0,
                    "rejected": 0,
                    "blocked": 0,
                    "deferred": 0,
                    "score_sum": 0.0,
                },
            )
            group["total"] += 1
            group["score_sum"] += float(row.get("score") or 0.0)
            if outcome in {"accepted", "promoted", "rejected", "blocked", "deferred"}:
                group[outcome] += 1

        grouped = []
        for group in groups.values():
            total = int(group["total"] or 0)
            accepted = int(group["accepted"] or 0)
            promoted = int(group["promoted"] or 0)
            score_sum = float(group.pop("score_sum", 0.0))
            group["positive_outcomes"] = accepted + promoted
            group["acceptance_rate"] = (accepted + promoted) / total if total else 0.0
            group["average_score"] = score_sum / total if total else 0.0
            grouped.append(group)
        grouped.sort(key=lambda item: (item["acceptance_rate"], item["total"]), reverse=True)
        return {
            "event_count": len(events),
            "outcome_counts": outcome_counts,
            "groups": grouped,
            "recent_events": events[: min(20, limit_i)],
        }

    # ── 向量操作 ────────────────────────────────────────────

    def add_embedding(self, knowledge_id: int, embedding: list[float]):
        """插入向量到 vec0 表。"""
        if not self._vec_available:
            raise RuntimeError("向量功能未啟用")
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
            raise RuntimeError("向量搜尋功能未啟用")

        # None 或空向量直接返回空結果
        if query_embedding is None or not isinstance(query_embedding, (list, tuple)) or len(query_embedding) == 0:
            return []

        # 驗證向量維度
        try:
            expected_dim = int(self._get_config("embedding_dim", "384"))
        except (ValueError, TypeError):
            expected_dim = 384
        if len(query_embedding) != expected_dim:
            raise ValueError(
                f"向量維度不匹配：預期 {expected_dim} 維，實際 {len(query_embedding)} 維"
            )

        # 安全上限
        MAX_LIMIT = 500
        if limit > MAX_LIMIT:
            limit = MAX_LIMIT

        import struct
        emb_bytes = struct.pack(f"{len(query_embedding)}f", *query_embedding)

        # Step 1: 從 vec 表取得相似的 knowledge_id + distance
        # 放大查詢量（limit * 5），緩解權限過濾帶來的側信道洩露
        # 同時設置合理上限，避免查詢過多向量影響性能
        VEC_SEARCH_MULTIPLIER = 5
        vec_limit = min(limit * VEC_SEARCH_MULTIPLIER, MAX_LIMIT)
        vec_rows = self.conn.execute(
            "SELECT knowledge_id, distance FROM knowledge_vec "
            "WHERE embedding MATCH ? ORDER BY distance ASC LIMIT ?",
            (emb_bytes, vec_limit),
        ).fetchall()

        if not vec_rows:
            return []

        # Step 2: 單次 IN 查詢取得所有符合權限的知識資料
        knowledge_ids = [row["knowledge_id"] for row in vec_rows]
        id_to_dist: dict[int, float] = {}
        for row in vec_rows:
            kid = int(row["knowledge_id"])
            dist = row["distance"]
            if isinstance(dist, bytes):
                dist = struct.unpack("f", dist)[0]
            id_to_dist[kid] = float(dist)

        where_conditions = [
            "id IN ({})".format(",".join("?" * len(knowledge_ids))),
            "trust >= ?",
            "COALESCE(status, 'active') != 'archived'",
        ]
        params: list = list(knowledge_ids)
        params.append(min_trust)

        if layer is not None:
            where_conditions.append("layer = ?")
            params.append(layer)
        if category is not None:
            where_conditions.append("category = ?")
            params.append(category)

        where_clause = " AND ".join(where_conditions)
        sql = f"SELECT * FROM knowledge WHERE {where_clause}"
        k_rows = self.conn.execute(sql, params).fetchall()

        # 組合結果，保持向量排序順序
        results = []
        for k_row in k_rows:
            kid = int(k_row["id"])
            if kid in id_to_dist:
                d = dict(k_row)
                d["_distance"] = id_to_dist[kid]
                results.append(d)

        # 按距離排序（保證順序正確）
        results.sort(key=lambda x: x["_distance"])
        return results

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
        # 參數驗證
        if node_id is None or not isinstance(node_id, (int, float)):
            return []
        node_id = int(node_id)

        MAX_DEPTH = 10
        MAX_NEIGHBORS = 200  # 最大返回鄰居數量
        MAX_VISITED = 500    # 最大遍歷節點數，防止密集圖 DoS
        if max_depth > MAX_DEPTH:
            max_depth = MAX_DEPTH
        if max_depth < 0:
            max_depth = 0

        # min_weight 與 min_trust 範圍保護
        if min_weight < 0:
            min_weight = 0.0
        if min_trust < 0:
            min_trust = 0.0
        if min_trust > 1:
            min_trust = 1.0

        # 是否需要權限過濾
        need_perm_check = min_trust > 0.0 or layer is not None or category is not None

        visited = {node_id}
        frontier = {node_id}
        # 存儲所有發現的鄰居及其屬性（id -> {distance, relation, weight}）
        all_neighbors: dict[int, dict] = {}

        for depth in range(1, max_depth + 1):
            next_frontier = set()
            # 收集本層所有原始鄰居（未經權限檢查
            layer_neighbors: dict[int, dict] = {}

            for nid in frontier:
                if len(visited) >= MAX_VISITED:
                    break
                rows = self.conn.execute(
                    "SELECT source_id, target_id, relation, weight FROM edges "
                    "WHERE (source_id=? OR target_id=?) AND weight >= ?",
                    (nid, nid, min_weight),
                ).fetchall()
                for row in rows:
                    if len(visited) >= MAX_VISITED:
                        break
                    neighbor = row["target_id"] if row["source_id"] == nid else row["source_id"]
                    if neighbor not in visited and neighbor not in layer_neighbors:
                        layer_neighbors[neighbor] = {
                            "id": neighbor,
                            "distance": depth,
                            "relation": row["relation"],
                            "weight": row["weight"],
                        }

            # 批量權限檢查（SQL 層級過濾，緩解側信道風險）
            if need_perm_check and layer_neighbors:
                neighbor_ids = list(layer_neighbors.keys())
                placeholders = ",".join("?" * len(neighbor_ids))

                where_conditions = [f"id IN ({placeholders})", "trust >= ?"]
                params: list = neighbor_ids + [min_trust]

                if layer is not None:
                    where_conditions.append("layer = ?")
                    params.append(layer)
                if category is not None:
                    where_conditions.append("category = ?")
                    params.append(category)

                where_clause = " AND ".join(where_conditions)
                sql = f"SELECT id, trust, layer, category FROM knowledge WHERE {where_clause}"

                valid_rows = self.conn.execute(sql, params).fetchall()
                valid_ids = {row["id"] for row in valid_rows}

                # 只保留有權限的節點
                for nid in valid_ids:
                    if nid not in visited:
                        visited.add(nid)
                        next_frontier.add(nid)
                        all_neighbors[nid] = layer_neighbors[nid]
            else:
                # 不需要權限檢查，直接加入
                for nid, info in layer_neighbors.items():
                    if nid not in visited:
                        visited.add(nid)
                        next_frontier.add(nid)
                        all_neighbors[nid] = info

            if len(visited) >= MAX_VISITED:
                break
            frontier = next_frontier
            if not frontier:
                break

        # 返回結果
        results = list(all_neighbors.values())[:MAX_NEIGHBORS]
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
        invalid = set(fields) - self.SKILL_UPDATE_COLUMNS
        if invalid:
            raise ValueError(f"invalid skill update field(s): {sorted(invalid)}")
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
                "(name LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' "
                "OR capabilities LIKE ? ESCAPE '\\' OR content_raw LIKE ? ESCAPE '\\')"
            )
            escaped = self._escape_like_pattern(query)
            pattern = f"%{escaped}%"
            params.extend([pattern, pattern, pattern, pattern])

        if capabilities:
            conditions.append("capabilities LIKE ? ESCAPE '\\'")
            escaped_cap = self._escape_like_pattern(capabilities)
            params.append(f"%{escaped_cap}%")

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
