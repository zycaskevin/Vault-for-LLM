import pytest

from vault.db import VaultDB
from vault.db_knowledge import escape_like_pattern


def test_knowledge_helper_adds_governance_and_summary_metadata(tmp_path):
    db = VaultDB(tmp_path / "vault.db").connect()
    try:
        kid = db.add_knowledge(
            title="Governed memory",
            content_raw="governed content",
            summary="short summary",
            scope="shared",
            sensitivity="low",
            owner_agent="codex",
            allowed_agents=["codex", "reviewer"],
            memory_type="decision",
        )

        row = db.get_knowledge(kid)
        assert row["scope"] == "shared"
        assert row["owner_agent"] == "codex"
        assert row["allowed_agents"] == '["codex", "reviewer"]'
        assert row["memory_type"] == "decision"
        assert row["summary_generated_at"]
    finally:
        db.close()


def test_knowledge_helper_update_rehashes_and_rejects_unknown_columns(tmp_path):
    db = VaultDB(tmp_path / "vault.db").connect()
    try:
        kid = db.add_knowledge(title="Hash me", content_raw="old")
        old_hash = db.get_knowledge(kid)["content_hash"]

        assert db.update_knowledge(kid, content_raw="new") is True
        assert db.get_knowledge(kid)["content_hash"] != old_hash

        with pytest.raises(ValueError, match="invalid knowledge update field"):
            db.update_knowledge(kid, **{"title = 'x' --": "bad"})
    finally:
        db.close()


def test_knowledge_helper_delete_cleans_dependent_rows(tmp_path):
    db = VaultDB(tmp_path / "vault.db").connect()
    try:
        kid1 = db.add_knowledge(title="Source", content_raw="source")
        kid2 = db.add_knowledge(title="Target", content_raw="target")
        entity_id = db.add_entity("Vault")
        db.add_edge(kid1, kid2)
        db.link_entity_knowledge(entity_id, kid1)
        db.add_lint_result(kid1, "check", "ok")

        assert db.delete_knowledge(kid1) is True
        assert db.get_knowledge(kid1) is None
        assert db.get_edges(node_id=kid1) == []
        assert db.get_entities_for_knowledge(kid1) == []
        assert db.get_lint_results(kid1) == []
        assert db.delete_knowledge(kid1) is False
    finally:
        db.close()


def test_knowledge_helper_like_search_escapes_wildcards(tmp_path):
    db = VaultDB(tmp_path / "vault.db").connect()
    try:
        db.add_knowledge(title="Literal percent", content_raw="100% precise", trust=0.9)
        db.add_knowledge(title="Loose text", content_raw="100x precise", trust=0.8)

        rows = db.search_keyword("100%")
        assert [row["title"] for row in rows] == ["Literal percent"]
        assert db.search_keyword(None) == []
        assert escape_like_pattern(r"100%_x") == r"100\%\_x"
    finally:
        db.close()
