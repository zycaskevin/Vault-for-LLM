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
