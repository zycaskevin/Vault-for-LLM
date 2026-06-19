import json

from vault.db import VaultDB
from vault.mcp import TOOLS, _set_project_dir, handle_tool_call


def _payload(result):
    assert "result" in result, result
    return json.loads(result["result"])


def test_mcp_memory_tools_are_advertised():
    names = {tool["name"] for tool in TOOLS}
    assert {"vault_memory_propose", "vault_memory_promote", "vault_dream_run"}.issubset(names)
    add_tool = next(tool for tool in TOOLS if tool["name"] == "vault_add")
    assert "Prefer vault_memory_propose" in add_tool["description"]
    search_tool = next(tool for tool in TOOLS if tool["name"] == "vault_search")
    assert "semantic" in search_tool["inputSchema"]["properties"]["mode"]["enum"]


def test_mcp_search_respects_fields_and_snippet(tmp_path):
    _set_project_dir(tmp_path)
    with VaultDB(tmp_path / "vault.db") as db:
        db.add_knowledge(
            "Python Cache Note",
            "Python cache keys should include provider metadata for semantic search.",
            category="search",
        )

    payload = _payload(
        handle_tool_call(
            "vault_search",
            {
                "query": "provider metadata",
                "include_snippet": True,
                "fields": ["id", "title", "_score", "_snippet"],
            },
        )
    )

    assert payload
    assert set(payload[0]).issubset({"id", "title", "_score", "_snippet"})
    assert payload[0]["title"] == "Python Cache Note"
    assert "provider" in payload[0]["_snippet"].lower()


def test_mcp_search_clamps_limit_offset_and_field_allowlist(tmp_path):
    _set_project_dir(tmp_path)
    with VaultDB(tmp_path / "vault.db") as db:
        for index in range(60):
            db.add_knowledge(
                f"Clamp Note {index:02d}",
                "MCP search clamp regression note.",
                category="search",
            )

    payload = _payload(
        handle_tool_call(
            "vault_search",
            {
                "query": "clamp regression",
                "limit": 5000,
                "offset": -20,
                "fields": ["id", "title", "content_raw", "__class__"],
            },
        )
    )

    assert len(payload) == 50
    assert set(payload[0]).issubset({"id", "title"})

    invalid_only = _payload(
        handle_tool_call(
            "vault_search",
            {
                "query": "clamp regression",
                "fields": ["content_raw", "__class__"],
            },
        )
    )
    assert invalid_only
    assert invalid_only[0] == {}


def test_mcp_memory_propose_candidate_does_not_add_active_knowledge(tmp_path):
    _set_project_dir(tmp_path)
    result = handle_tool_call(
        "vault_memory_propose",
        {
            "title": "MCP candidate",
            "content": "Agents should propose memory before direct durable writes.",
            "reason": "MCP candidate workflow test",
            "source": "test",
        },
    )
    payload = _payload(result)
    assert payload["status"] == "candidate_created"
    assert payload["gates"]["privacy"] == "pass"
    assert payload["candidate_id"].startswith("mem_")

    with VaultDB(tmp_path / "vault.db") as db:
        assert db.get_memory_candidate(payload["candidate_id"])["title"] == "MCP candidate"
        assert db.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"] == 0


def test_mcp_memory_promote_writes_active_knowledge(tmp_path):
    _set_project_dir(tmp_path)
    proposed = _payload(handle_tool_call(
        "vault_memory_propose",
        {
            "title": "MCP promote",
            "content": "Promotion through MCP writes active knowledge and a raw note.",
            "reason": "Exercise MCP promotion",
            "source": "test",
            "trust": 0.8,
        },
    ))
    promoted = _payload(handle_tool_call(
        "vault_memory_promote",
        {
            "candidate_id": proposed["candidate_id"],
            "confirm": True,
            "compile": False,
            "build_map": True,
        },
    ))
    assert promoted["status"] == "promoted"
    assert promoted["knowledge_id"]
    assert (tmp_path / "raw" / "mcp-promote.md").exists()

    with VaultDB(tmp_path / "vault.db") as db:
        knowledge = db.get_knowledge(promoted["knowledge_id"])
        assert knowledge["title"] == "MCP promote"
        nodes = db.conn.execute(
            "SELECT COUNT(*) AS n FROM knowledge_nodes WHERE knowledge_id=?",
            (promoted["knowledge_id"],),
        ).fetchone()["n"]
        assert nodes >= 1


def test_mcp_vault_add_warns_and_builds_document_map(tmp_path):
    _set_project_dir(tmp_path)
    payload = _payload(handle_tool_call(
        "vault_add",
        {
            "title": "Direct add compatibility",
            "content": "Direct MCP add is a compatibility path; agents should prefer candidate memory.",
            "tags": "mcp,direct",
        },
    ))
    assert payload["success"] is True
    assert "warning" in payload
    assert payload["document_map_built"] is True
    with VaultDB(tmp_path / "vault.db") as db:
        nodes = db.conn.execute(
            "SELECT COUNT(*) AS n FROM knowledge_nodes WHERE knowledge_id=?",
            (payload["id"],),
        ).fetchone()["n"]
        assert nodes >= 1


def test_mcp_vault_add_blocks_privacy_fail_content(tmp_path):
    _set_project_dir(tmp_path)
    key_name = "api" + "_key"
    raw_key = "abcdefghijklmnop"
    payload = _payload(handle_tool_call(
        "vault_add",
        {
            "title": "Direct secret",
            "content": f"Do not store {key_name}={raw_key} through direct add.",
        },
    ))
    assert payload["success"] is False
    assert payload["error"] == "privacy_gate_failed"
    with VaultDB(tmp_path / "vault.db") as db:
        assert db.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"] == 0


def test_mcp_vault_add_blocks_privacy_fail_metadata(tmp_path):
    _set_project_dir(tmp_path)
    token = "ghp_" + "A" * 36
    payload = _payload(handle_tool_call(
        "vault_add",
        {
            "title": "Direct metadata secret",
            "content": "Safe body should not override unsafe metadata.",
            "tags": token,
        },
    ))
    assert payload["success"] is False
    assert payload["error"] == "privacy_gate_failed"
    with VaultDB(tmp_path / "vault.db") as db:
        assert db.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"] == 0


def test_mcp_dream_run_report_only(tmp_path):
    _set_project_dir(tmp_path)
    with VaultDB(tmp_path / "vault.db") as db:
        db.add_knowledge(
            title="Dream weak metadata",
            content_raw="Report-only dream should inspect but not mutate active knowledge.",
            source="test",
            category="general",
            tags="",
            trust=0.3,
        )
        before = db.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"]

    payload = _payload(handle_tool_call(
        "vault_dream_run",
        {"mode": "report", "checks": ["metadata", "dedup"], "limit": 10, "write_report": True},
    ))
    assert payload["summary"]["metadata"] == 1
    assert payload["summary"]["actions_applied"] == 0
    assert payload["report_path"].startswith("reports/dream/")
    assert (tmp_path / payload["report_path"]).exists()

    with VaultDB(tmp_path / "vault.db") as db:
        after = db.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"]
    assert after == before
