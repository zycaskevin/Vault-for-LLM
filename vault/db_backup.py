"""SQLite backup, verification, and restore helpers for Vault-for-LLM.

The helpers in this module are intentionally local-file only. They use SQLite's
online backup API so backups remain consistent when the source database is in
WAL mode.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vault.db import VaultDB


_TABLES_FOR_COUNTS = (
    "knowledge",
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
    "schema_migrations",
)


class BackupError(RuntimeError):
    """Raised when a backup/verify/restore operation cannot complete safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_path(path: Path) -> Path:
    """Return path or a numbered sibling that does not exist yet."""
    if not path.exists():
        return path
    for index in range(1, 1000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise BackupError(f"unable to find available backup path near: {path}")


def default_backup_path(db_path: str | Path, *, prefix: str = "vault") -> Path:
    db_path = Path(db_path)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    return _unique_path(db_path.parent / "backups" / f"{prefix}-{timestamp}.db")


def _readonly_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro"


def _connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise BackupError(f"SQLite database not found: {path}")
    try:
        conn = sqlite3.connect(_readonly_uri(path), uri=True)
    except sqlite3.Error as exc:
        raise BackupError(f"unable to open SQLite database read-only: {path}: {exc}") from exc
    conn.row_factory = sqlite3.Row
    return conn


def _sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise BackupError(f"backup destination already exists: {destination}")

    try:
        source_conn = sqlite3.connect(str(source))
        try:
            dest_conn = sqlite3.connect(str(destination))
            try:
                source_conn.backup(dest_conn)
            finally:
                dest_conn.close()
        finally:
            source_conn.close()
    except sqlite3.Error as exc:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise BackupError(f"SQLite backup failed: {exc}") from exc


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        """SELECT name FROM sqlite_master
           WHERE type IN ('table', 'virtual table') AND name NOT LIKE 'sqlite_%'"""
    ).fetchall()
    return {str(row["name"]) for row in rows}


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.Error:
        return set()
    return {str(row["name"]) for row in rows}


def _vault_schema_validation(conn: sqlite3.Connection, schema_status: dict[str, Any]) -> dict[str, Any]:
    """Return strict Vault schema validation for restore safety."""
    required_columns = {
        "config": {"key", "value"},
        "knowledge": {"id", "title", "content_raw", "content_aaak", "category", "trust"},
        "schema_migrations": {"version", "name", "applied_at"},
        "knowledge_nodes": {"id", "knowledge_id", "node_uid", "line_start", "line_end"},
        "knowledge_claims": {"id", "knowledge_id", "claim_uid", "claim", "line_start", "line_end"},
        "semantic_vectors": {"knowledge_id", "vector_kind", "item_uid", "provider_id", "dimension", "vector"},
        "embedding_cache": {"provider_id", "dimension", "text_hash", "vector"},
        "memory_candidates": {"id", "title", "content", "status", "gate_payload_json"},
        "memory_feedback_events": {"id", "created_at", "outcome", "payload_json"},
        "task_ledger": {"id", "goal", "status", "current_plan_json", "next_actions_json"},
        "task_events": {"id", "task_id", "event_type", "content", "payload_json"},
        "task_evidence_refs": {"id", "task_id", "ref_type", "ref", "metadata_json"},
        "task_handoffs": {"id", "task_id", "status", "from_agent", "to_agent", "markdown"},
        "memory_revisions": {"id", "created_at", "revision_hash", "operation", "status", "payload_json"},
        "memory_conflicts": {"id", "created_at", "status", "conflict_type", "reason", "resolution_json"},
        "memory_audit_log": {"id", "created_at", "actor_agent", "action", "target_type", "target_id"},
        "content_log": {"id", "platform", "topic", "title", "body_hash", "status", "created_at"},
        "skills": {"id", "name", "version", "agent_source", "category"},
        "lint_cache": {"id", "knowledge_id", "check_type", "result", "checked_at"},
        "edges": {"id", "source_id", "target_id", "relation", "weight"},
        "entities": {"id", "name", "entity_type", "created_at"},
        "entity_knowledge": {"id", "entity_id", "knowledge_id"},
    }
    column_errors: dict[str, list[str]] = {}
    for table, columns in required_columns.items():
        present = _table_columns(conn, table)
        missing = sorted(columns - present)
        if missing:
            column_errors[table] = missing

    version_ok = (
        int(schema_status["current_version"]) >= VaultDB.SCHEMA_VERSION
        and int(schema_status["config_schema_version"]) >= VaultDB.SCHEMA_VERSION
        and int(schema_status["pragma_user_version"]) >= VaultDB.SCHEMA_VERSION
    )
    migration_errors: list[str] = []
    migrations: set[int] = set()
    for row in schema_status["applied_migrations"]:
        try:
            migrations.add(int(row["version"]))
        except (TypeError, ValueError):
            migration_errors.append(str(row.get("version", "")))
    migrations_ok = not migration_errors and set(range(1, VaultDB.SCHEMA_VERSION + 1)).issubset(migrations)
    ok = (
        not schema_status["needs_migration"]
        and not column_errors
        and version_ok
        and migrations_ok
    )
    return {
        "ok": ok,
        "version_ok": version_ok,
        "migrations_ok": migrations_ok,
        "migration_errors": migration_errors,
        "column_errors": column_errors,
    }


def _json_safe_sqlite_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.hex()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _applied_migrations(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if "schema_migrations" not in _table_names(conn):
        return []
    if not {"version", "name", "applied_at"}.issubset(_table_columns(conn, "schema_migrations")):
        return []
    rows = conn.execute(
        "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
    ).fetchall()
    return [
        {
            "version": _json_safe_sqlite_value(row["version"]),
            "name": _json_safe_sqlite_value(row["name"]),
            "applied_at": _json_safe_sqlite_value(row["applied_at"]),
        }
        for row in rows
    ]


def _schema_status_readonly(conn: sqlite3.Connection, db_path: Path) -> dict[str, Any]:
    tables = _table_names(conn)
    config_version = 0
    if "config" in tables and {"key", "value"}.issubset(_table_columns(conn, "config")):
        row = conn.execute("SELECT value FROM config WHERE key='schema_version'").fetchone()
        if row:
            try:
                config_version = int(row["value"] or 0)
            except (TypeError, ValueError):
                config_version = 0
    user_version = int(conn.execute("PRAGMA user_version").fetchone()[0] or 0)
    migrations = _applied_migrations(conn)
    migration_versions = []
    for row in migrations:
        try:
            migration_versions.append(int(row["version"]))
        except (TypeError, ValueError):
            continue
    current_version = max([config_version, user_version, *migration_versions, 0])
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
        "target_version": VaultDB.SCHEMA_VERSION,
        "config_schema_version": config_version,
        "pragma_user_version": user_version,
        "needs_migration": current_version < VaultDB.SCHEMA_VERSION or bool(missing),
        "applied_migrations": migrations,
        "db_path": str(db_path),
        "table_count": len(tables),
        "tables_present": sorted(tables & required_tables),
        "tables_missing": missing,
    }


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = _table_names(conn)
    counts: dict[str, int] = {}
    for table in _TABLES_FOR_COUNTS:
        if table not in tables:
            continue
        try:
            counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        except sqlite3.Error:
            counts[table] = -1
    return counts


def verify_backup(backup_path: str | Path) -> dict[str, Any]:
    """Verify a SQLite backup and return a JSON-safe summary."""
    backup_path = Path(backup_path)
    conn = _connect_readonly(backup_path)
    try:
        integrity_check = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        schema_status = _schema_status_readonly(conn, backup_path)
        schema_validation = _vault_schema_validation(conn, schema_status)
        table_counts = _table_counts(conn)
    except sqlite3.Error as exc:
        raise BackupError(f"backup verification failed: {backup_path}: {exc}") from exc
    finally:
        conn.close()

    vault_schema_ok = bool(schema_validation["ok"])
    return {
        "ok": integrity_check.lower() == "ok" and vault_schema_ok,
        "vault_schema_ok": vault_schema_ok,
        "schema_validation": schema_validation,
        "backup_path": str(backup_path),
        "size_bytes": backup_path.stat().st_size,
        "sha256": sha256_file(backup_path),
        "verified_at": utc_now(),
        "integrity_check": integrity_check,
        "schema_status": schema_status,
        "table_counts": table_counts,
    }


def backup_database(
    db_path: str | Path,
    output_path: str | Path | None = None,
    *,
    verify: bool = False,
) -> dict[str, Any]:
    """Create a consistent SQLite backup using the online backup API."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise BackupError(f"SQLite database not found: {db_path}")
    backup_path = Path(output_path) if output_path else default_backup_path(db_path)
    _sqlite_backup(db_path, backup_path)

    verification = verify_backup(backup_path)
    payload = {
        "ok": True,
        "source": str(db_path),
        "backup_path": str(backup_path),
        "size_bytes": backup_path.stat().st_size,
        "sha256": verification["sha256"],
        "created_at": utc_now(),
        "schema_status": verification["schema_status"],
        "verified": bool(verify),
    }
    if verify:
        payload["verification"] = verification
        payload["ok"] = bool(verification["ok"])
    return payload


def _backup_pre_restore(target_path: Path) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    output = _unique_path(target_path.parent / "backups" / f"pre-restore-{target_path.stem}-{timestamp}.db")
    return backup_database(target_path, output, verify=True)


def _remove_sqlite_sidecars(db_path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(db_path) + suffix)
        try:
            sidecar.unlink(missing_ok=True)
        except OSError as exc:
            raise BackupError(f"unable to remove SQLite sidecar {sidecar}: {exc}") from exc


def restore_database(
    backup_path: str | Path,
    db_path: str | Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Restore a verified backup to db_path, refusing overwrite unless forced."""
    backup_path = Path(backup_path)
    target_path = Path(db_path)
    if target_path.exists() and not force:
        raise BackupError(f"target database already exists; pass --force to overwrite: {target_path}")

    source_verification = verify_backup(backup_path)
    if not source_verification["ok"]:
        raise BackupError(
            "refusing to restore backup that failed verification: "
            f"integrity_check={source_verification['integrity_check']} "
            f"vault_schema_ok={source_verification['vault_schema_ok']}"
        )

    pre_restore_backup = None
    if target_path.exists():
        pre_restore_backup = _backup_pre_restore(target_path)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile(
        prefix=f".{target_path.name}.restore-",
        suffix=".tmp",
        dir=str(target_path.parent),
        delete=False,
    )
    temp_path = Path(temp_file.name)
    temp_file.close()
    temp_path.unlink(missing_ok=True)

    try:
        shutil.copy2(backup_path, temp_path)
        temp_verification = verify_backup(temp_path)
        if not temp_verification["ok"]:
            raise BackupError(
                f"temporary restore copy failed integrity_check: {temp_verification['integrity_check']}"
            )
        _remove_sqlite_sidecars(target_path)
        os.replace(temp_path, target_path)
        _remove_sqlite_sidecars(target_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    restored_verification = verify_backup(target_path)
    return {
        "ok": bool(restored_verification["ok"]),
        "backup_path": str(backup_path),
        "target": str(target_path),
        "restored_at": utc_now(),
        "forced": bool(force),
        "pre_restore_backup": pre_restore_backup,
        "source_verification": source_verification,
        "restored_verification": restored_verification,
        "sha256": restored_verification["sha256"],
        "size_bytes": restored_verification["size_bytes"],
        "schema_status": restored_verification["schema_status"],
        "table_counts": restored_verification["table_counts"],
    }
