"""
Extended tests for vault.db_backup module to boost coverage.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from vault.db import VaultDB
from vault.db_backup import (
    BackupError,
    _applied_migrations,
    _connect_readonly,
    _json_safe_sqlite_value,
    _sqlite_backup,
    _table_columns,
    _table_names,
    _unique_path,
    backup_database,
    default_backup_path,
    restore_database,
    verify_backup,
)


class TestUniquePath:
    def test_unique_path_when_not_exists(self, tmp_path):
        path = tmp_path / "backup.db"
        result = _unique_path(path)
        assert result == path

    def test_unique_path_with_existing_file(self, tmp_path):
        path = tmp_path / "backup.db"
        path.touch()
        result = _unique_path(path)
        assert result != path
        assert result.name == "backup-1.db"
        assert not result.exists()

    def test_unique_path_multiple_existing(self, tmp_path):
        base = tmp_path / "backup.db"
        base.touch()
        (tmp_path / "backup-1.db").touch()
        (tmp_path / "backup-2.db").touch()
        result = _unique_path(base)
        assert result.name == "backup-3.db"

    def test_unique_path_with_suffix(self, tmp_path):
        path = tmp_path / "archive.db"
        path.touch()
        result = _unique_path(path)
        assert result.suffix == ".db"
        assert result.stem == "archive-1"


class TestDefaultBackupPath:
    def test_default_backup_path_creates_backups_dir(self, tmp_path):
        db_path = tmp_path / "vault.db"
        db_path.touch()
        result = default_backup_path(db_path)
        assert result.parent == db_path.parent / "backups"
        assert result.name.startswith("vault-")
        assert result.suffix == ".db"

    def test_default_backup_path_with_prefix(self, tmp_path):
        db_path = tmp_path / "test.db"
        db_path.touch()
        result = default_backup_path(db_path, prefix="mybackup")
        assert result.name.startswith("mybackup-")


class TestConnectReadonly:
    def test_connect_readonly_nonexistent_raises(self, tmp_path):
        path = tmp_path / "nonexistent.db"
        with pytest.raises(BackupError, match="not found"):
            _connect_readonly(path)

    def test_connect_readonly_success(self, tmp_path):
        path = tmp_path / "test.db"
        conn = sqlite3.connect(str(path))
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.commit()
        conn.close()
        result = _connect_readonly(path)
        try:
            assert result is not None
            rows = result.execute("SELECT * FROM test").fetchall()
            assert rows == []
        finally:
            result.close()


class TestSqliteBackup:
    def test_sqlite_backup_success(self, tmp_path):
        src = tmp_path / "source.db"
        dst = tmp_path / "dest.db"
        conn = sqlite3.connect(str(src))
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val TEXT)")
        conn.execute("INSERT INTO test VALUES (1, 'hello')")
        conn.commit()
        conn.close()
        _sqlite_backup(src, dst)
        assert dst.exists()
        # Verify content
        conn2 = sqlite3.connect(str(dst))
        row = conn2.execute("SELECT * FROM test WHERE id=1").fetchone()
        assert row[1] == "hello"
        conn2.close()

    def test_sqlite_backup_destination_exists_raises(self, tmp_path):
        src = tmp_path / "source.db"
        dst = tmp_path / "dest.db"
        sqlite3.connect(str(src)).close()
        dst.touch()
        with pytest.raises(BackupError, match="already exists"):
            _sqlite_backup(src, dst)

    def test_sqlite_backup_creates_parent_dir(self, tmp_path):
        src = tmp_path / "source.db"
        dst = tmp_path / "nested" / "sub" / "dest.db"
        sqlite3.connect(str(src)).close()
        _sqlite_backup(src, dst)
        assert dst.exists()


class TestTableNamesAndColumns:
    def test_table_names_empty_db(self, tmp_path):
        path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            tables = _table_names(conn)
            assert isinstance(tables, set)
        finally:
            conn.close()

    def test_table_names_with_tables(self, tmp_path):
        path = tmp_path / "test.db"
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
            conn.execute("CREATE TABLE posts (id INTEGER, title TEXT)")
            conn.commit()
            tables = _table_names(conn)
            assert "users" in tables
            assert "posts" in tables
        finally:
            conn.close()

    def test_table_columns_existing(self, tmp_path):
        path = tmp_path / "test.db"
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("CREATE TABLE users (id INTEGER, name TEXT, email TEXT)")
            conn.commit()
            cols = _table_columns(conn, "users")
            assert cols == {"id", "name", "email"}
        finally:
            conn.close()

    def test_table_columns_nonexistent(self, tmp_path):
        path = tmp_path / "test.db"
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            cols = _table_columns(conn, "nonexistent")
            assert cols == set()
        finally:
            conn.close()


class TestAppliedMigrations:
    def test_applied_migrations_no_table(self, tmp_path):
        path = tmp_path / "test.db"
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            result = _applied_migrations(conn)
            assert result == []
        finally:
            conn.close()

    def test_applied_migrations_wrong_columns(self, tmp_path):
        path = tmp_path / "test.db"
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("CREATE TABLE schema_migrations (id INTEGER, name TEXT)")
            conn.commit()
            result = _applied_migrations(conn)
            assert result == []
        finally:
            conn.close()

    def test_applied_migrations_with_data(self, tmp_path):
        path = tmp_path / "test.db"
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                "CREATE TABLE schema_migrations (version INTEGER, name TEXT, applied_at TEXT)"
            )
            conn.execute(
                "INSERT INTO schema_migrations VALUES (1, 'initial', '2024-01-01T00:00:00Z')"
            )
            conn.execute(
                "INSERT INTO schema_migrations VALUES (2, 'add_users', '2024-01-02T00:00:00Z')"
            )
            conn.commit()
            result = _applied_migrations(conn)
            assert len(result) == 2
            assert result[0]["version"] == 1
            assert result[0]["name"] == "initial"
            assert result[1]["version"] == 2
        finally:
            conn.close()


class TestJsonSafeSqliteValue:
    def test_json_safe_str(self):
        assert _json_safe_sqlite_value("hello") == "hello"

    def test_json_safe_int(self):
        assert _json_safe_sqlite_value(42) == 42

    def test_json_safe_float(self):
        assert _json_safe_sqlite_value(3.14) == 3.14

    def test_json_safe_none(self):
        assert _json_safe_sqlite_value(None) is None

    def test_json_safe_bool(self):
        assert _json_safe_sqlite_value(True) is True
        assert _json_safe_sqlite_value(False) is False

    def test_json_safe_bytes(self):
        result = _json_safe_sqlite_value(b"hello")
        assert isinstance(result, str)
        assert result == "68656c6c6f"

    def test_json_safe_other(self):
        result = _json_safe_sqlite_value([1, 2, 3])
        assert isinstance(result, str)


class TestBackupDatabase:
    def test_backup_database_nonexistent_source_raises(self, tmp_path):
        with pytest.raises(BackupError, match="not found"):
            backup_database(tmp_path / "nonexistent.db")

    def test_backup_database_with_verify(self, tmp_path):
        db_path = tmp_path / "vault.db"
        db = VaultDB(str(db_path))
        db.connect()
        db.add_knowledge(title="Test", content_raw="test content", trust=0.9)
        db.close()
        result = backup_database(db_path, verify=True)
        assert result["ok"] is True
        assert result["source"] == str(db_path)
        assert "backup_path" in result
        assert "sha256" in result
        assert "size_bytes" in result

    def test_backup_database_with_custom_output(self, tmp_path):
        db_path = tmp_path / "vault.db"
        db = VaultDB(str(db_path))
        db.connect()
        db.add_knowledge(title="Test", content_raw="test")
        db.close()
        out_path = tmp_path / "custom_backup.db"
        result = backup_database(db_path, output_path=str(out_path))
        assert result["ok"] is True
        assert Path(result["backup_path"]) == out_path

    def test_backup_database_default_output(self, tmp_path):
        db_path = tmp_path / "vault.db"
        db = VaultDB(str(db_path))
        db.connect()
        db.add_knowledge(title="Test", content_raw="test")
        db.close()
        result = backup_database(db_path)
        assert result["ok"] is True
        assert "backups" in result["backup_path"]


class TestVerifyBackup:
    def test_verify_backup_valid_vault(self, tmp_path):
        db_path = tmp_path / "vault.db"
        db = VaultDB(str(db_path))
        db.connect()
        db.add_knowledge(title="Test", content_raw="test")
        db.close()
        result = verify_backup(db_path)
        assert result["ok"] is True
        assert result["vault_schema_ok"] is True
        assert "schema_status" in result
        assert "table_counts" in result

    def test_verify_backup_integrity_check_present(self, tmp_path):
        db_path = tmp_path / "vault.db"
        db = VaultDB(str(db_path))
        db.connect()
        db.close()
        result = verify_backup(db_path)
        assert "integrity_check" in result

    def test_verify_backup_nonexistent(self, tmp_path):
        with pytest.raises(BackupError):
            verify_backup(tmp_path / "nonexistent.db")


class TestRestoreDatabase:
    def test_restore_database_nonexistent_backup(self, tmp_path):
        with pytest.raises(BackupError, match="not found"):
            restore_database(tmp_path / "nobackup.db", tmp_path / "target.db")

    def test_restore_database_no_force_existing_target(self, tmp_path):
        backup = tmp_path / "backup.db"
        db = VaultDB(str(backup))
        db.connect()
        db.add_knowledge(title="Backup", content_raw="backup content")
        db.close()
        target = tmp_path / "target.db"
        target.touch()
        with pytest.raises(BackupError, match="already exists"):
            restore_database(backup, target, force=False)

    def test_restore_database_force_overwrite(self, tmp_path):
        backup = tmp_path / "backup.db"
        db = VaultDB(str(backup))
        db.connect()
        db.add_knowledge(title="FromBackup", content_raw="restored content")
        db.close()
        target = tmp_path / "target.db"
        target_db = VaultDB(str(target))
        target_db.connect()
        target_db.add_knowledge(title="Old", content_raw="old content")
        target_db.close()
        result = restore_database(backup, target, force=True)
        assert result["ok"] is True
        verify = VaultDB(str(target))
        verify.connect()
        rows = verify.list_knowledge()
        assert len(rows) >= 1
        assert any(r["title"] == "FromBackup" for r in rows)
        verify.close()

    def test_restore_database_to_new_location(self, tmp_path):
        backup = tmp_path / "backup.db"
        db = VaultDB(str(backup))
        db.connect()
        db.add_knowledge(title="NewRestore", content_raw="new restore")
        db.close()
        target = tmp_path / "new_target.db"
        result = restore_database(backup, target)
        assert result["ok"] is True
        assert target.exists()

    def test_restore_verifies_integrity(self, tmp_path):
        backup = tmp_path / "backup.db"
        db = VaultDB(str(backup))
        db.connect()
        db.add_knowledge(title="Restore Test", content_raw="test restore")
        db.close()
        target = tmp_path / "restored.db"
        result = restore_database(backup, target)
        assert result["ok"] is True
        # Verify we got some useful info back
        assert "backup_path" in result or "source" in result


