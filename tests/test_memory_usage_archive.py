from datetime import datetime, timedelta, timezone
from argparse import Namespace
import json

from vault.db import VaultDB
from vault.search import VaultSearch, calc_usage_boost


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


def test_usage_boost_is_small_and_saturated():
    recent = datetime.now(timezone.utc).isoformat()

    low = calc_usage_boost({"access_count": 1, "citation_count": 0, "last_accessed_at": recent})
    high = calc_usage_boost({"access_count": 10000, "citation_count": 10000, "last_accessed_at": recent})

    assert low > 0
    assert high <= 0.18
    assert high > low


def test_usage_boost_breaks_ties_in_lightweight_rerank(tmp_path):
    with VaultDB(tmp_path / "vault.db") as db:
        cold_id = db.add_knowledge("Deploy rollback SOP", "Cloudflare rollback deployment steps")
        hot_id = db.add_knowledge("Deploy rollback SOP", "Cloudflare rollback deployment steps")
        for _ in range(8):
            db.record_knowledge_access([hot_id])

        results = VaultSearch(db).search("Cloudflare rollback", mode="keyword", limit=5)

        assert {row["id"] for row in results[:2]} == {cold_id, hot_id}
        assert results[0]["id"] == hot_id
        assert results[0]["_rerank_score"] > results[1]["_rerank_score"]


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


def test_archive_expired_can_skip_used_rows(tmp_path):
    now = datetime.now(timezone.utc)
    expired = (now - timedelta(days=1)).isoformat()

    with VaultDB(tmp_path / "vault.db") as db:
        unused_id = db.add_knowledge("Unused expired", "Short lived", expires_at=expired)
        used_id = db.add_knowledge("Used expired", "Still useful", expires_at=expired)
        db.record_knowledge_access([used_id])

        applied = db.archive_expired_knowledge(now=now, dry_run=False, skip_used=True)

        assert applied["archived_count"] == 1
        assert applied["skipped_used_count"] == 1
        assert db.get_knowledge(unused_id)["status"] == "archived"
        assert db.get_knowledge(used_id)["status"] == "active"


def test_cold_store_expired_summarizes_used_rows_without_deleting(tmp_path):
    now = datetime.now(timezone.utc)
    expired = (now - timedelta(days=1)).isoformat()

    with VaultDB(tmp_path / "vault.db") as db:
        used_id = db.add_knowledge(
            "Used expired deployment SOP",
            "Rollback by checking the current deployment, selecting the prior build, and verifying traffic.",
            layer="L2",
            expires_at=expired,
        )
        low_usage_id = db.add_knowledge("Unused expired note", "Short lived", expires_at=expired)
        private_id = db.add_knowledge(
            "Private expired note",
            "Private content should not be cold-stored automatically.",
            scope="private",
            expires_at=expired,
        )
        l0_id = db.add_knowledge(
            "Core identity expired",
            "Core identity should be protected from cold-store automation.",
            layer="L0",
            expires_at=expired,
        )
        db.record_knowledge_access([used_id], cited=True)

        preview = db.cold_store_expired_knowledge(now=now, dry_run=True)
        assert preview["applied_count"] == 0
        assert preview["eligible_count"] == 1
        assert preview["skipped_low_usage_count"] == 1
        assert preview["skipped_protected_count"] == 2
        assert preview["items"][0]["id"] == used_id
        assert db.get_knowledge(used_id)["status"] == "active"

        applied = db.cold_store_expired_knowledge(now=now, dry_run=False)
        assert applied["applied_count"] == 1
        assert applied["summary_count"] == 1
        assert applied["demoted_count"] == 1
        assert applied["safety"]["hard_delete"] is False
        row = db.get_knowledge(used_id)
        assert row["status"] == "archived"
        assert row["layer"] == "L3"
        assert row["content_raw"].startswith("Rollback by checking")
        assert "Cold-store summary" in row["summary"]
        assert row["summary_generated_at"]
        assert db.get_knowledge(low_usage_id)["status"] == "active"
        assert db.get_knowledge(private_id)["status"] == "active"
        assert db.get_knowledge(l0_id)["status"] == "active"


def test_cold_store_summary_redacts_secret_shapes(tmp_path):
    now = datetime.now(timezone.utc)
    expired = (now - timedelta(days=1)).isoformat()
    token = "sk-proj-1234567890abcdefghij1234567890"

    with VaultDB(tmp_path / "vault.db") as db:
        used_id = db.add_knowledge(
            "Expired low sensitivity token lesson",
            f"Do not store this fake token in summaries: {token}",
            expires_at=expired,
        )
        db.record_knowledge_access([used_id], cited=True)
        applied = db.cold_store_expired_knowledge(now=now, dry_run=False)
        rendered = json.dumps(applied, ensure_ascii=False)
        row = db.get_knowledge(used_id)

    assert token not in rendered
    assert token not in row["summary"]


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


def test_usage_cli_cold_store_expired(tmp_path, monkeypatch, capsys):
    from vault.cli import cmd_usage

    monkeypatch.chdir(tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with VaultDB(tmp_path / "vault.db") as db:
        used_id = db.add_knowledge("CLI cold-store memo", "TTL cold-store test", expires_at=expired)
        db.record_knowledge_access([used_id], cited=True)

    cmd_usage(
        Namespace(
            usage_action="cold-store-expired",
            limit=10,
            min_usage=1,
            summary_max_chars=120,
            apply=True,
            json=True,
            pretty=False,
        )
    )
    payload = capsys.readouterr().out
    assert '"applied_count": 1' in payload
    assert '"action": "cold-store-expired"' in payload
