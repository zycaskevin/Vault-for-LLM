from datetime import datetime, timedelta, timezone
from argparse import Namespace

from vault.db import VaultDB
from vault.search import VaultSearch


def test_memory_usage_columns_exist_on_fresh_db(tmp_path):
    with VaultDB(tmp_path / "vault.db") as db:
        cols = {row["name"] for row in db.conn.execute("PRAGMA table_info(knowledge)")}

    assert {
        "status",
        "archived_at",
        "last_accessed_at",
        "access_count",
        "citation_count",
    }.issubset(cols)


def test_search_records_access_counts(tmp_path):
    with VaultDB(tmp_path / "vault.db") as db:
        kid = db.add_knowledge("Deploy SOP", "Cloudflare deployment command")
        results = VaultSearch(db).search("Cloudflare", mode="keyword", limit=5)

        assert [row["id"] for row in results] == [kid]
        row = db.get_knowledge(kid)
        assert row["access_count"] == 1
        assert row["last_accessed_at"]


def test_archived_knowledge_is_hidden_from_search_and_list(tmp_path):
    with VaultDB(tmp_path / "vault.db") as db:
        active_id = db.add_knowledge("Active SOP", "Cloudflare deployment command")
        archived_id = db.add_knowledge("Archived SOP", "Cloudflare deployment command")
        db.update_knowledge(archived_id, status="archived", archived_at=datetime.now(timezone.utc).isoformat())

        results = VaultSearch(db).search("Cloudflare", mode="keyword", limit=10)
        listed = db.list_knowledge(limit=10)

        assert [row["id"] for row in results] == [active_id]
        assert [row["id"] for row in listed] == [active_id]


def test_archive_expired_knowledge_dry_run_then_apply(tmp_path):
    now = datetime.now(timezone.utc)
    expired = (now - timedelta(days=1)).isoformat()
    future = (now + timedelta(days=1)).isoformat()

    with VaultDB(tmp_path / "vault.db") as db:
        expired_id = db.add_knowledge("Temporary status", "Short lived", expires_at=expired)
        future_id = db.add_knowledge("Future status", "Still valid", expires_at=future)

        preview = db.archive_expired_knowledge(now=now, dry_run=True)
        assert preview["eligible_count"] == 1
        assert preview["archived_count"] == 0
        assert db.get_knowledge(expired_id)["status"] == "active"

        applied = db.archive_expired_knowledge(now=now, dry_run=False)
        assert applied["archived_count"] == 1
        assert db.get_knowledge(expired_id)["status"] == "archived"
        assert db.get_knowledge(future_id)["status"] == "active"


def test_usage_cli_archive_expired(tmp_path, monkeypatch, capsys):
    from vault.cli import cmd_usage

    monkeypatch.chdir(tmp_path)
    with VaultDB(tmp_path / "vault.db") as db:
        db.add_knowledge(
            "Expired memo",
            "TTL test",
            expires_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        )

    cmd_usage(Namespace(usage_action="archive-expired", limit=10, apply=True, json=True, pretty=False))
    payload = capsys.readouterr().out
    assert '"archived_count": 1' in payload
