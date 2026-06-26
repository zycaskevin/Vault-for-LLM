import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from vault.db import VaultDB
from vault import db_schema


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_vaultdb_schema_constants_match_schema_module():
    assert VaultDB.SCHEMA_VERSION == db_schema.SCHEMA_VERSION
    assert VaultDB.MIGRATIONS == db_schema.MIGRATIONS
    assert VaultDB.KNOWLEDGE_UPDATE_COLUMNS == db_schema.KNOWLEDGE_UPDATE_COLUMNS
    assert VaultDB.MEMORY_CANDIDATE_UPDATE_COLUMNS == db_schema.MEMORY_CANDIDATE_UPDATE_COLUMNS
    assert VaultDB.SKILL_UPDATE_COLUMNS == db_schema.SKILL_UPDATE_COLUMNS


def test_fresh_db_status_is_current(tmp_path):
    db_path = tmp_path / "vault.db"
    with VaultDB(db_path) as db:
        status = db.schema_status()
        assert status["current_version"] == VaultDB.SCHEMA_VERSION
        assert status["target_version"] == VaultDB.SCHEMA_VERSION
        assert status["needs_migration"] is False
        assert len(status["applied_migrations"]) == VaultDB.SCHEMA_VERSION
        assert db.get_config("schema_version") == str(VaultDB.SCHEMA_VERSION)
        assert "memory_candidates" in status["tables_present"]


def test_old_pre_v3_db_migrates_to_current(tmp_path):
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO config(key, value) VALUES('schema_version', '2')")
    conn.execute(
        """CREATE TABLE knowledge (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           title TEXT NOT NULL,
           content_raw TEXT NOT NULL DEFAULT ''
        )"""
    )
    conn.execute("INSERT INTO knowledge(title, content_raw) VALUES('legacy', 'body')")
    conn.commit()
    conn.close()

    with VaultDB(db_path) as db:
        summary = db.migrate()
        status = db.schema_status()
        cols = {row["name"] for row in db.conn.execute("PRAGMA table_info(knowledge)")}
        assert summary["ok"] is True
        assert status["current_version"] == VaultDB.SCHEMA_VERSION
        assert status["needs_migration"] is False
        assert db.get_config("schema_version") == str(VaultDB.SCHEMA_VERSION)
        assert "schema_migrations" in status["tables_present"]
        assert {"content_aaak", "convergence_status", "summary"}.issubset(cols)
        assert db.conn.execute("SELECT title FROM knowledge WHERE id=1").fetchone()["title"] == "legacy"


def test_migrate_is_idempotent_no_duplicate_migration_rows(tmp_path):
    db_path = tmp_path / "vault.db"
    with VaultDB(db_path) as db:
        first = db.migrate()
        second = db.migrate()
        versions = [row["version"] for row in db.applied_migrations()]
        assert first["ok"] is True
        assert second["ok"] is True
        assert versions == list(range(1, VaultDB.SCHEMA_VERSION + 1))
        assert len(versions) == len(set(versions))


def test_schema_status_requires_memory_candidates_table(tmp_path):
    db_path = tmp_path / "missing_candidate.db"
    with VaultDB(db_path) as db:
        assert db.conn is not None
        db.conn.execute("DROP TABLE memory_candidates")
        db.conn.commit()
        status = db.schema_status()

        assert status["needs_migration"] is True
        assert "memory_candidates" in status["tables_missing"]


def test_db_status_and_migrate_cli_pretty(tmp_path):
    db_path = tmp_path / "cli.db"

    status_run = subprocess.run(
        [sys.executable, "-m", "vault.cli", "db", "status", "--db-path", str(db_path), "--pretty"],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=True,
    )
    assert "\n  " in status_run.stdout
    status = json.loads(status_run.stdout)
    assert status["current_version"] == VaultDB.SCHEMA_VERSION
    assert status["needs_migration"] is False

    migrate_run = subprocess.run(
        [sys.executable, "-m", "vault.cli", "db", "migrate", "--db-path", str(db_path), "--pretty"],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=True,
    )
    assert "\n  " in migrate_run.stdout
    summary = json.loads(migrate_run.stdout)
    assert summary["ok"] is True
    assert summary["to_version"] == VaultDB.SCHEMA_VERSION
