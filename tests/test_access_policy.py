import json

from vault.access_policy import can_read_memory, normalize_read_policy
from vault.db import VaultDB
from vault.search import VaultSearch
from vault import mcp as vault_mcp


def test_read_policy_preserves_legacy_visibility_without_agent():
    policy = normalize_read_policy()
    assert can_read_memory(
        {
            "scope": "private",
            "sensitivity": "restricted",
            "owner_agent": "nancy",
            "allowed_agents": "[]",
        },
        policy,
    )


def test_read_policy_private_and_restricted_rules():
    private_row = {
        "scope": "private",
        "sensitivity": "high",
        "owner_agent": "nancy",
        "allowed_agents": '["mori"]',
    }
    restricted_row = {
        "scope": "shared",
        "sensitivity": "restricted",
        "owner_agent": "nancy",
        "allowed_agents": '["mori"]',
    }

    mori_default = normalize_read_policy(agent_id="mori")
    mori_private = normalize_read_policy(agent_id="mori", include_private=True)
    aiko_private = normalize_read_policy(agent_id="aiko", include_private=True)

    assert can_read_memory(private_row, mori_default) is False
    assert can_read_memory(private_row, mori_private) is True
    assert can_read_memory(private_row, aiko_private) is False
    assert can_read_memory(restricted_row, mori_default) is True
    assert can_read_memory(restricted_row, aiko_private) is False


def test_search_applies_governance_read_filter(tmp_path):
    with VaultDB(tmp_path / "vault.db") as db:
        db.add_knowledge(
            title="Shared deployment note",
            content_raw="Governance search smoke deployment note.",
            source="test",
            scope="shared",
            sensitivity="low",
        )
        db.add_knowledge(
            title="Nancy private note",
            content_raw="Governance search smoke private note.",
            source="test",
            scope="private",
            sensitivity="high",
            owner_agent="nancy",
            allowed_agents=["mori"],
        )
        db.add_knowledge(
            title="Restricted project note",
            content_raw="Governance search smoke restricted note.",
            source="test",
            scope="shared",
            sensitivity="restricted",
            owner_agent="nancy",
            allowed_agents=["mori"],
        )
        search = VaultSearch(db)

        legacy = search.search("governance search smoke", mode="keyword", limit=10)
        mori = search.search("governance search smoke", mode="keyword", limit=10, agent_id="mori")
        mori_private = search.search(
            "governance search smoke",
            mode="keyword",
            limit=10,
            agent_id="mori",
            include_private=True,
        )
        aiko = search.search("governance search smoke", mode="keyword", limit=10, agent_id="aiko")
        capped = search.search(
            "governance search smoke",
            mode="keyword",
            limit=10,
            agent_id="mori",
            include_private=True,
            max_sensitivity="medium",
        )

    assert {row["title"] for row in legacy} == {
        "Shared deployment note",
        "Nancy private note",
        "Restricted project note",
    }
    assert {row["title"] for row in mori} == {
        "Shared deployment note",
        "Restricted project note",
    }
    assert {row["title"] for row in mori_private} == {
        "Shared deployment note",
        "Nancy private note",
        "Restricted project note",
    }
    assert {row["title"] for row in aiko} == {"Shared deployment note"}
    assert {row["title"] for row in capped} == {"Shared deployment note"}


def test_mcp_search_and_read_range_apply_governance_policy(tmp_path, monkeypatch):
    db_path = tmp_path / "vault.db"
    with VaultDB(db_path) as db:
        shared_id = db.add_knowledge(
            title="Shared MCP note",
            content_raw="# Shared MCP note\n\nReadable by project agents.",
            source="test",
            scope="shared",
            sensitivity="low",
        )
        private_id = db.add_knowledge(
            title="Nancy MCP private note",
            content_raw="# Nancy MCP private note\n\nPrivate line for Nancy only.",
            source="test",
            scope="private",
            sensitivity="high",
            owner_agent="nancy",
            allowed_agents=["mori"],
        )

    monkeypatch.setattr(vault_mcp, "DB_PATH", str(db_path))

    search_payload = json.loads(
        vault_mcp.handle_tool_call(
            "vault_search",
            {
                "query": "MCP note",
                "mode": "keyword",
                "limit": 10,
                "agent_id": "aiko",
            },
        )["result"]
    )
    assert [row["id"] for row in search_payload] == [shared_id]

    denied = vault_mcp._vault_read_range_payload(
        private_id,
        line_start=1,
        line_end=2,
        db_path=str(db_path),
        agent_id="aiko",
    )
    allowed = vault_mcp._vault_read_range_payload(
        private_id,
        line_start=1,
        line_end=3,
        db_path=str(db_path),
        agent_id="mori",
        include_private=True,
    )
    map_denied = vault_mcp._vault_map_show_payload(
        private_id,
        db_path=str(db_path),
        agent_id="aiko",
    )

    assert denied["error"] == "access_denied"
    assert map_denied["error"] == "access_denied"
    assert allowed["entry_id"] == private_id
    assert "Private line for Nancy only" in allowed["content"]
