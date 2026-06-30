import pytest

from vault.db import VaultDB
from vault.db_skills import escape_like_pattern


def test_skill_helper_add_update_and_sync(tmp_path):
    db = VaultDB(tmp_path / "vault.db").connect()
    try:
        skill_id = db.add_skill(
            name="review-helper",
            content_raw="Review repository changes.",
            capabilities="review,testing",
            category="engineering",
            trust=0.8,
            description="Review helper",
        )
        assert skill_id > 0
        assert db.add_skill(name="review-helper", content_raw="duplicate") == -1

        skill = db.get_skill("review-helper")
        old_hash = skill["content_hash"]

        assert db.update_skill("review-helper", content_raw="Updated review workflow.") is True
        updated = db.get_skill("review-helper")
        assert updated["content_hash"] != old_hash

        db.mark_skill_synced("review-helper")
        synced = db.get_skill("review-helper")
        assert synced["last_synced"]

        newer_id = db.add_skill(
            name="review-helper",
            version="1.1.0",
            content_raw="Updated review workflow with version history.",
            capabilities="review,testing",
            category="engineering",
            trust=0.85,
            description="Review helper v1.1",
        )
        assert newer_id == skill_id
        latest = db.get_skill("review-helper")
        assert latest["version"] == "1.1.0"
        versions = db.list_skill_versions("review-helper")
        assert [row["version"] for row in versions] == ["1.1.0", "1.0.0"]
        diff = db.diff_skill_versions("review-helper", "1.0.0", "1.1.0")
        assert diff["ok"] is True
        assert diff["content_changed"] is True

        plan = db.skill_upgrade_plan(installed={"review-helper": "1.0.0"})
        assert plan["upgrade_count"] == 1
        assert plan["skills"][0]["status"] == "upgrade_available"
        assert plan["skills"][0]["recommended_action"] == "upgrade"
    finally:
        db.close()


def test_skill_upgrade_plan_detects_hash_drift_and_local_newer(tmp_path):
    db = VaultDB(tmp_path / "vault.db").connect()
    try:
        db.add_skill(name="drift-helper", version="1.0.0", content_raw="Registry content")
        db.add_skill(name="local-helper", version="1.0.0", content_raw="Registry content")

        plan = db.skill_upgrade_plan(
            installed={
                "drift-helper": {"version": "1.0.0", "content_hash": "differenthash"},
                "local-helper": {"version": "2.0.0", "content_hash": "localhash"},
            }
        )
        by_name = {row["name"]: row for row in plan["skills"]}
        assert by_name["drift-helper"]["status"] == "drift"
        assert by_name["drift-helper"]["recommended_action"] == "inspect_diff"
        assert by_name["local-helper"]["status"] == "local_newer"
        assert by_name["local-helper"]["recommended_action"] == "publish_or_keep_local"
        assert plan["status_counts"]["drift"] == 1
        assert plan["status_counts"]["local_newer"] == 1
        assert "operator-approved sync step" in plan["next_action"]
    finally:
        db.close()


def test_skill_helper_rejects_unknown_update_columns(tmp_path):
    db = VaultDB(tmp_path / "vault.db").connect()
    try:
        db.add_skill(name="safe-skill", content_raw="Safe content")

        with pytest.raises(ValueError, match="invalid skill update field"):
            db.update_skill("safe-skill", **{"description = 'x', trust": 1.0})
    finally:
        db.close()


def test_skill_helper_search_escapes_like_wildcards(tmp_path):
    db = VaultDB(tmp_path / "vault.db").connect()
    try:
        db.add_skill(name="literal_percent", content_raw="Use 100% literal matching.")
        db.add_skill(name="literal_plain", content_raw="Use 100x literal matching.")

        results = db.search_skills("100%")
        assert [row["name"] for row in results] == ["literal_percent"]
        assert escape_like_pattern(r"100%_x") == r"100\%\_x"
    finally:
        db.close()


def test_skill_helper_list_omits_raw_content(tmp_path):
    db = VaultDB(tmp_path / "vault.db").connect()
    try:
        db.add_skill(name="listed-skill", content_raw="Internal implementation detail.")

        rows = db.list_skills(limit=10)
        assert rows[0]["name"] == "listed-skill"
        assert "content_raw" not in rows[0]
    finally:
        db.close()
