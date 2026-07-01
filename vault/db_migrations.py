"""Schema migration and status helpers for VaultDB."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import sqlite3


InitTables = Callable[[], None]


def ensure_schema_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
    """)


def record_migrations_through(
    conn: sqlite3.Connection,
    target_version: int,
    migrations: dict[int, str],
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for version in range(1, target_version + 1):
        name = migrations.get(version, f"schema_v{version}")
        conn.execute(
            """INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
               VALUES(?, ?, ?)""",
            (version, name, now),
        )


def applied_migrations(conn: sqlite3.Connection) -> list[dict]:
    ensure_schema_migrations_table(conn)
    rows = conn.execute(
        "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
    ).fetchall()
    return [dict(row) for row in rows]


def table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        """SELECT name FROM sqlite_master
           WHERE type IN ('table', 'virtual table') AND name NOT LIKE 'sqlite_%'"""
    ).fetchall()
    return {row["name"] for row in rows}


def config_schema_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT value FROM config WHERE key=?", ("schema_version",)).fetchone()
        return int((row["value"] if row else "0") or 0)
    except (TypeError, ValueError, sqlite3.OperationalError):
        return 0


def schema_status(conn: sqlite3.Connection, *, db_path: str | Path, schema_version: int) -> dict:
    ensure_schema_migrations_table(conn)
    config_version = config_schema_version(conn)
    user_version = int(conn.execute("PRAGMA user_version").fetchone()[0] or 0)
    migration_versions = [int(row["version"]) for row in applied_migrations(conn)]
    current_version = max([config_version, user_version, *migration_versions, 0])
    tables = table_names(conn)
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
        "task_ledger",
        "task_events",
        "task_evidence_refs",
        "task_handoffs",
        "memory_revisions",
        "memory_conflicts",
        "memory_audit_log",
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
        "target_version": schema_version,
        "config_schema_version": config_version,
        "pragma_user_version": user_version,
        "needs_migration": current_version < schema_version or bool(missing),
        "applied_migrations": applied_migrations(conn),
        "db_path": str(db_path),
        "table_count": len(tables),
        "tables_present": sorted(tables & required_tables),
        "tables_missing": missing,
    }


def migrate(
    conn: sqlite3.Connection,
    *,
    db_path: str | Path,
    schema_version: int,
    target_version: int | None = None,
    init_tables: InitTables,
) -> dict:
    target = schema_version if target_version is None else int(target_version)
    if target != schema_version:
        raise ValueError(f"unsupported target schema version: {target}")
    before = schema_status(conn, db_path=db_path, schema_version=schema_version)
    before_versions = {row["version"] for row in before["applied_migrations"]}
    init_tables()
    after = schema_status(conn, db_path=db_path, schema_version=schema_version)
    after_versions = {row["version"] for row in after["applied_migrations"]}
    return {
        "ok": not after["needs_migration"],
        "db_path": str(db_path),
        "from_version": before["current_version"],
        "to_version": after["current_version"],
        "target_version": schema_version,
        "applied_versions": sorted(after_versions - before_versions),
        "before": before,
        "after": after,
    }


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def ensure_table_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing_cols = table_columns(conn, table)
    for column_name, column_def in columns.items():
        if column_name not in existing_cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_def}")


def backfill_claim_uids(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
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
        conn.execute(
            "UPDATE knowledge_claims SET claim_uid=? WHERE id=?",
            (claim_uid, row["id"]),
        )
