import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from vault.db import VaultDB
from vault.db_backup import BackupError, backup_database, restore_database, verify_backup


REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_db(path: Path, title: str = "alpha") -> None:
    with VaultDB(path) as db:
        db.add_knowledge(title=title, content_raw=f"body for {title}", source="test")


def _knowledge_titles(path: Path) -> list[str]:
    conn = sqlite3.connect(path)
    try:
        return [row[0] for row in conn.execute("SELECT title FROM knowledge ORDER BY id")]
    finally:
        conn.close()


def test_backup_creates_file_and_verify_reports_ok(tmp_path):
    db_path = tmp_path / "vault.db"
    backup_path = tmp_path / "backups" / "manual.db"
    _make_db(db_path)

    summary = backup_database(db_path, backup_path, verify=True)
    verification = verify_backup(backup_path)

    assert backup_path.exists()
    assert summary["ok"] is True
    assert summary["verified"] is True
    assert summary["sha256"] == verification["sha256"]
    assert verification["ok"] is True
    assert verification["integrity_check"] == "ok"
    assert len(verification["sha256"]) == 64
    assert verification["table_counts"]["knowledge"] == 1


def test_restore_refuses_overwrite_without_force(tmp_path):
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "target.db"
    _make_db(source_db, "source")
    _make_db(target_db, "target")
    backup = tmp_path / "source-backup.db"
    backup_database(source_db, backup)

    with pytest.raises(BackupError, match="--force"):
        restore_database(backup, target_db, force=False)

    assert _knowledge_titles(target_db) == ["target"]


def test_restore_force_preserves_existing_target_and_restores_source(tmp_path):
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "target.db"
    _make_db(source_db, "source")
    _make_db(target_db, "target")
    backup = tmp_path / "source-backup.db"
    backup_database(source_db, backup, verify=True)

    summary = restore_database(backup, target_db, force=True)

    assert summary["ok"] is True
    assert summary["pre_restore_backup"] is not None
    pre_restore_path = Path(summary["pre_restore_backup"]["backup_path"])
    assert pre_restore_path.exists()
    assert _knowledge_titles(pre_restore_path) == ["target"]
    assert _knowledge_titles(target_db) == ["source"]
    assert summary["table_counts"]["knowledge"] == 1


def test_backup_is_wal_safe_and_restored_counts_match(tmp_path):
    db_path = tmp_path / "wal.db"
    backup_path = tmp_path / "wal-backup.db"
    restore_path = tmp_path / "restored.db"
    with VaultDB(db_path) as db:
        assert db.conn is not None
        db.conn.execute("PRAGMA journal_mode=WAL")
        for idx in range(5):
            db.add_knowledge(title=f"row-{idx}", content_raw=f"body {idx}")
        assert Path(str(db_path) + "-wal").exists()
        summary = backup_database(db_path, backup_path, verify=True)

    assert summary["verification"]["table_counts"]["knowledge"] == 5
    restore_summary = restore_database(backup_path, restore_path)
    assert restore_summary["table_counts"]["knowledge"] == 5
    assert _knowledge_titles(restore_path) == [f"row-{idx}" for idx in range(5)]


def test_db_backup_verify_restore_cli_smoke(tmp_path):
    db_path = tmp_path / "cli.db"
    backup_path = tmp_path / "cli-backup.db"
    restore_path = tmp_path / "cli-restored.db"
    _make_db(db_path, "cli-source")

    backup_run = subprocess.run(
        [
            sys.executable,
            "-m",
            "vault.cli",
            "db",
            "backup",
            "--db-path",
            str(db_path),
            "--output",
            str(backup_path),
            "--verify",
            "--pretty",
        ],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=True,
    )
    backup_payload = json.loads(backup_run.stdout)
    assert backup_payload["ok"] is True
    assert backup_payload["backup_path"] == str(backup_path)
    assert backup_payload["verification"]["integrity_check"] == "ok"

    verify_run = subprocess.run(
        [sys.executable, "-m", "vault.cli", "db", "verify-backup", str(backup_path), "--pretty"],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=True,
    )
    verify_payload = json.loads(verify_run.stdout)
    assert verify_payload["ok"] is True
    assert verify_payload["vault_schema_ok"] is True
    assert verify_payload["table_counts"]["knowledge"] == 1

    restore_run = subprocess.run(
        [
            sys.executable,
            "-m",
            "vault.cli",
            "db",
            "restore",
            str(backup_path),
            "--db-path",
            str(restore_path),
            "--pretty",
        ],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=True,
    )
    restore_payload = json.loads(restore_run.stdout)
    assert restore_payload["ok"] is True
    assert restore_payload["pre_restore_backup"] is None
    assert _knowledge_titles(restore_path) == ["cli-source"]

    refused = subprocess.run(
        [
            sys.executable,
            "-m",
            "vault.cli",
            "db",
            "restore",
            str(backup_path),
            "--db-path",
            str(restore_path),
        ],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    assert refused.returncode == 2
    assert "--force" in refused.stderr


def test_verify_and_restore_reject_non_vault_sqlite(tmp_path):
    not_vault = tmp_path / "not-vault.db"
    target = tmp_path / "target.db"
    conn = sqlite3.connect(not_vault)
    conn.execute("CREATE TABLE t(x TEXT)")
    conn.execute("INSERT INTO t(x) VALUES('not vault')")
    conn.commit()
    conn.close()

    verification = verify_backup(not_vault)
    assert verification["integrity_check"] == "ok"
    assert verification["ok"] is False
    assert verification["vault_schema_ok"] is False
    assert "knowledge" in verification["schema_status"]["tables_missing"]

    with pytest.raises(BackupError, match="vault_schema_ok=False"):
        restore_database(not_vault, target)


def test_default_backup_paths_do_not_collide(tmp_path):
    db_path = tmp_path / "vault.db"
    _make_db(db_path)

    first = backup_database(db_path)
    second = backup_database(db_path)

    assert first["backup_path"] != second["backup_path"]
    assert Path(first["backup_path"]).exists()
    assert Path(second["backup_path"]).exists()


def test_verify_rejects_fake_vault_table_names_with_invalid_columns(tmp_path):
    fake = tmp_path / "fake-vault.db"
    target = tmp_path / "target.db"
    required_tables = [
        "config",
        "knowledge",
        "schema_migrations",
        "knowledge_nodes",
        "knowledge_claims",
        "semantic_vectors",
        "embedding_cache",
        "content_log",
        "skills",
        "lint_cache",
        "edges",
        "entities",
        "entity_knowledge",
    ]
    conn = sqlite3.connect(fake)
    for table in required_tables:
        conn.execute(f"CREATE TABLE {table}(dummy TEXT)")
    conn.execute("PRAGMA user_version=5")
    conn.commit()
    conn.close()

    verification = verify_backup(fake)
    assert verification["integrity_check"] == "ok"
    assert verification["schema_status"]["tables_missing"] == []
    assert verification["ok"] is False
    assert verification["vault_schema_ok"] is False
    assert "knowledge" in verification["schema_validation"]["column_errors"]

    with pytest.raises(BackupError, match="vault_schema_ok=False"):
        restore_database(fake, target)


def test_verify_rejects_malformed_migration_metadata_without_crashing(tmp_path):
    fake = tmp_path / "fake-migration.db"
    target = tmp_path / "target.db"
    conn = sqlite3.connect(fake)
    conn.execute("CREATE TABLE config(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO config(key, value) VALUES('schema_version', '5')")
    conn.execute(
        """CREATE TABLE knowledge(
            id INTEGER, title TEXT, content_raw TEXT, content_aaak TEXT,
            category TEXT, trust REAL
        )"""
    )
    conn.execute("CREATE TABLE schema_migrations(version TEXT, name TEXT, applied_at TEXT)")
    conn.execute("INSERT INTO schema_migrations(version, name, applied_at) VALUES('bad', 'broken', '')")
    conn.execute(
        """CREATE TABLE knowledge_nodes(
            id INTEGER, knowledge_id INTEGER, node_uid TEXT, line_start INTEGER, line_end INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE knowledge_claims(
            id INTEGER, knowledge_id INTEGER, claim_uid TEXT, claim TEXT, line_start INTEGER, line_end INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE semantic_vectors(
            knowledge_id INTEGER, vector_kind TEXT, item_uid TEXT, provider_id TEXT,
            dimension INTEGER, vector TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE embedding_cache(
            provider_id TEXT, dimension INTEGER, text_hash TEXT, vector TEXT
        )"""
    )
    for table in ["content_log", "skills", "lint_cache", "edges", "entities", "entity_knowledge"]:
        conn.execute(f"CREATE TABLE {table}(id INTEGER)")
    conn.execute("PRAGMA user_version=5")
    conn.commit()
    conn.close()

    verification = verify_backup(fake)
    assert verification["integrity_check"] == "ok"
    assert verification["ok"] is False
    assert verification["vault_schema_ok"] is False
    assert verification["schema_validation"]["migration_errors"] == ["bad"]

    with pytest.raises(BackupError, match="vault_schema_ok=False"):
        restore_database(fake, target)


def test_verify_rejects_malformed_auxiliary_vault_tables(tmp_path):
    fake = tmp_path / "fake-auxiliary.db"
    target = tmp_path / "target.db"
    conn = sqlite3.connect(fake)
    conn.execute("CREATE TABLE config(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO config(key, value) VALUES('schema_version', '6')")
    conn.execute(
        """CREATE TABLE knowledge(
            id INTEGER, title TEXT, content_raw TEXT, content_aaak TEXT,
            category TEXT, trust REAL
        )"""
    )
    conn.execute("CREATE TABLE schema_migrations(version INTEGER, name TEXT, applied_at TEXT)")
    for version in range(1, 7):
        conn.execute(
            "INSERT INTO schema_migrations(version, name, applied_at) VALUES(?, ?, '')",
            (version, f"v{version}"),
        )
    conn.execute(
        """CREATE TABLE knowledge_nodes(
            id INTEGER, knowledge_id INTEGER, node_uid TEXT, line_start INTEGER, line_end INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE knowledge_claims(
            id INTEGER, knowledge_id INTEGER, claim_uid TEXT, claim TEXT, line_start INTEGER, line_end INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE semantic_vectors(
            knowledge_id INTEGER, vector_kind TEXT, item_uid TEXT, provider_id TEXT,
            dimension INTEGER, vector TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE embedding_cache(
            provider_id TEXT, dimension INTEGER, text_hash TEXT, vector TEXT
        )"""
    )
    for table in ["content_log", "skills", "lint_cache", "edges", "entities", "entity_knowledge"]:
        conn.execute(f"CREATE TABLE {table}(id INTEGER)")
    conn.execute("PRAGMA user_version=6")
    conn.commit()
    conn.close()

    verification = verify_backup(fake)
    assert verification["schema_status"]["tables_missing"] == []
    assert verification["schema_validation"]["version_ok"] is True
    assert verification["schema_validation"]["migrations_ok"] is True
    assert verification["ok"] is False
    assert verification["vault_schema_ok"] is False
    assert "content_log" in verification["schema_validation"]["column_errors"]

    with pytest.raises(BackupError, match="vault_schema_ok=False"):
        restore_database(fake, target)


def test_forced_restore_pre_restore_backups_do_not_collide(tmp_path):
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "target.db"
    _make_db(source_db, "source")
    _make_db(target_db, "target")
    backup = tmp_path / "source-backup.db"
    backup_database(source_db, backup, verify=True)

    first = restore_database(backup, target_db, force=True)
    with VaultDB(target_db) as db:
        db.add_knowledge(title="target-second", content_raw="body")
    second = restore_database(backup, target_db, force=True)

    first_pre = Path(first["pre_restore_backup"]["backup_path"])
    second_pre = Path(second["pre_restore_backup"]["backup_path"])
    assert first_pre != second_pre
    assert first_pre.exists()
    assert second_pre.exists()
