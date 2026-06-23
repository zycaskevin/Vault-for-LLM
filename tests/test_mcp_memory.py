import json

import pytest

from vault.db import VaultDB
from vault.mcp import TOOLS, _set_project_dir, handle_tool_call


def _payload(result):
    assert "result" in result, result
    return json.loads(result["result"])


def test_mcp_memory_tools_are_advertised():
    names = {tool["name"] for tool in TOOLS}
    assert {
        "vault_memory_propose",
        "vault_memory_promote",
        "vault_memory_review",
        "vault_memory_candidates",
        "vault_capture_session",
        "vault_automation_inbox",
        "vault_dream_run",
    }.issubset(names)
    add_tool = next(tool for tool in TOOLS if tool["name"] == "vault_add")
    assert "Prefer vault_memory_propose" in add_tool["description"]
    search_tool = next(tool for tool in TOOLS if tool["name"] == "vault_search")
    assert "semantic" in search_tool["inputSchema"]["properties"]["mode"]["enum"]


def test_mcp_tool_profiles_reduce_visible_tool_schemas():
    from vault.mcp import select_tools

    core_names = [tool["name"] for tool in select_tools("core")]
    assert core_names == [
        "vault_search",
        "vault_read_range",
        "vault_memory_propose",
        "vault_stats",
    ]
    assert "vault_memory_candidates" not in core_names

    review_names = [tool["name"] for tool in select_tools("review")]
    assert "vault_memory_candidates" in review_names
    assert "vault_memory_review" in review_names
    assert "vault_capture_session" in review_names
    assert "vault_automation_inbox" in review_names
    assert "vault_capture_session" not in core_names
    assert "vault_automation_inbox" not in core_names
    assert "vault_memory_review" not in core_names

    full_names = {tool["name"] for tool in select_tools("full")}
    assert "vault_add" in full_names
    assert "vault_memory_review" in full_names
    assert "vault_remote_read_range" in full_names
    assert len(full_names) > len(core_names)


def test_mcp_custom_tool_allowlist_overrides_profile():
    from vault.mcp import select_tools

    names = [tool["name"] for tool in select_tools("full", "vault_search,vault_stats")]
    assert names == ["vault_search", "vault_stats"]


def test_mcp_custom_tool_allowlist_rejects_unknown_tool():
    from vault.mcp import select_tools

    with pytest.raises(ValueError, match="Unknown MCP tool"):
        select_tools("full", "vault_search,vault_nope")


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


def test_mcp_memory_review_records_rejection_feedback(tmp_path):
    _set_project_dir(tmp_path)
    proposed = _payload(handle_tool_call(
        "vault_memory_propose",
        {
            "title": "MCP review candidate",
            "content": "MCP review should record rejected feedback without promoting active knowledge.",
            "reason": "Exercise explicit MCP review feedback.",
            "source": "test",
            "tags": "mcp,review",
        },
    ))

    reviewed = _payload(handle_tool_call(
        "vault_memory_review",
        {
            "candidate_id": proposed["candidate_id"],
            "outcome": "rejected",
            "reason": "Too vague for durable memory.",
        },
    ))

    assert reviewed["status"] == "rejected"
    assert reviewed["score"] == 0.0
    with VaultDB(tmp_path / "vault.db") as db:
        candidate = db.get_memory_candidate(proposed["candidate_id"])
        feedback = db.list_memory_feedback(limit=10)
        active = db.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"]
    assert candidate["status"] == "rejected"
    assert active == 0
    assert feedback[0]["candidate_id"] == proposed["candidate_id"]
    assert feedback[0]["outcome"] == "rejected"
    assert feedback[0]["reason"] == "Too vague for durable memory."


def test_mcp_memory_candidates_lists_review_queue_without_full_payload(tmp_path):
    _set_project_dir(tmp_path)
    proposed = _payload(handle_tool_call(
        "vault_memory_propose",
        {
            "title": "MCP candidate queue",
            "content": "MCP candidate queue entries should be visible before promotion.",
            "reason": "Review agents need a small candidate queue payload.",
            "source": "test",
            "tags": "mcp,candidate",
        },
    ))

    listed = _payload(handle_tool_call(
        "vault_memory_candidates",
        {
            "limit": 10,
        },
    ))

    assert listed["count"] == 1
    assert listed["status"] == "candidate"
    item = listed["candidates"][0]
    assert item["id"] == proposed["candidate_id"]
    assert item["title"] == "MCP candidate queue"
    assert item["status"] == "candidate"
    assert item["privacy_status"] == "pass"
    assert "content_preview" in item
    assert "content" not in item
    assert "gates" not in item

    detailed = _payload(handle_tool_call(
        "vault_memory_candidates",
        {
            "include_content": True,
            "include_gates": True,
        },
    ))

    detailed_item = detailed["candidates"][0]
    assert detailed_item["content"].startswith("MCP candidate queue entries")
    assert detailed_item["gates"]["privacy"]["status"] == "pass"


def test_mcp_capture_session_previews_without_writing_candidates(tmp_path):
    _set_project_dir(tmp_path)
    transcript = tmp_path / "codex-session.md"
    transcript.write_text(
        "\n".join(
            [
                "Decision: MCP session capture should dry-run by default because active memory needs review.",
                "Workflow: Always use the review profile before writing session candidates through MCP.",
            ]
        ),
        encoding="utf-8",
    )

    payload = _payload(handle_tool_call(
        "vault_capture_session",
        {
            "transcript_path": "codex-session.md",
            "source_system": "codex",
            "agent_id": "codex",
        },
    ))

    assert payload["status"] == "completed"
    assert payload["write_candidates"] is False
    assert payload["written"] == 0
    assert payload["extracted"] == 2
    assert payload["candidates"][0]["status"] == "preview"
    assert "content" not in payload["candidates"][0]
    with VaultDB(tmp_path / "vault.db") as db:
        assert db.list_memory_candidates() == []


def test_mcp_capture_session_writes_candidates_when_explicit(tmp_path):
    _set_project_dir(tmp_path)
    transcript = tmp_path / "hermes-session.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "role": "assistant",
                "content": "Decision: Session capture through MCP must remain candidate-first because reviewers need a queue.",
            }
        ),
        encoding="utf-8",
    )

    payload = _payload(handle_tool_call(
        "vault_capture_session",
        {
            "transcript_path": "hermes-session.jsonl",
            "format": "jsonl",
            "source_system": "hermes",
            "agent_id": "review-agent",
            "write_candidates": True,
        },
    ))

    assert payload["write_candidates"] is True
    assert payload["written"] == 1
    assert payload["candidates"][0]["candidate_id"].startswith("mem_")
    with VaultDB(tmp_path / "vault.db") as db:
        rows = db.list_memory_candidates(limit=10)
    assert len(rows) == 1
    assert rows[0]["source"] == "session_capture"
    assert rows[0]["owner_agent"] == "review-agent"


def test_mcp_capture_session_blocks_absolute_paths_by_default(tmp_path):
    _set_project_dir(tmp_path)
    transcript = tmp_path.parent / "external-session.md"
    transcript.write_text(
        "Decision: External transcript paths should require explicit MCP permission.",
        encoding="utf-8",
    )

    payload = handle_tool_call(
        "vault_capture_session",
        {
            "transcript_path": str(transcript),
        },
    )

    assert "absolute transcript paths require allow_absolute_path=true" in payload["error"]


def test_mcp_automation_inbox_reads_short_queue_without_content(tmp_path):
    _set_project_dir(tmp_path)
    proposed = _payload(handle_tool_call(
        "vault_memory_propose",
        {
            "title": "MCP automation inbox",
            "content": "Decision: MCP automation inbox should expose short review queues because agents need bounded handoffs.",
            "reason": "Review agents need automation inbox access.",
            "source": "session_capture",
            "source_ref": "mcp:inbox:1",
            "tags": "mcp,inbox",
            "memory_type": "session_lesson",
        },
    ))

    inbox = _payload(handle_tool_call("vault_automation_inbox", {"limit": 5}))

    assert inbox["action"] == "inbox"
    assert inbox["summary"]["pending_candidates"] == 1
    assert inbox["review_queue"][0]["id"] == proposed["candidate_id"]
    assert inbox["review_queue"][0]["recommended_action"] == "review_for_promotion"
    assert "content" not in inbox["review_queue"][0]
    assert inbox["safety"]["read_only"] is True


def test_mcp_automation_inbox_can_write_handoff(tmp_path):
    _set_project_dir(tmp_path)
    _payload(handle_tool_call(
        "vault_memory_propose",
        {
            "title": "MCP inbox handoff",
            "content": "Workflow: MCP automation inbox can write handoff JSON because scheduled agents need a stable file.",
            "reason": "Agent handoff workflow.",
            "source": "session_capture",
            "source_ref": "mcp:inbox:handoff",
            "tags": "mcp,inbox,handoff",
            "memory_type": "session_lesson",
        },
    ))

    inbox = _payload(handle_tool_call("vault_automation_inbox", {"write_handoff": True}))

    assert inbox["inbox_handoff_path"] == "reports/automation/inbox-latest.json"
    assert (tmp_path / inbox["inbox_handoff_path"]).exists()


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


def test_mcp_dream_write_candidates_keeps_active_knowledge_unchanged(tmp_path):
    _set_project_dir(tmp_path)
    with VaultDB(tmp_path / "vault.db") as db:
        db.add_knowledge(
            title="MCP Dream candidate",
            content_raw="MCP dream should create a review candidate because metadata needs cleanup.",
            source="test",
            category="general",
            tags="",
            trust=0.3,
        )
        before = db.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"]

    payload = _payload(handle_tool_call(
        "vault_dream_run",
        {"mode": "report", "checks": ["metadata"], "limit": 10, "write_candidates": True},
    ))
    assert payload["summary"]["candidate_suggestions"] == 1
    assert payload["summary"]["candidates_written"] == 1
    assert payload["candidate_results"][0]["status"] == "candidate_created"

    with VaultDB(tmp_path / "vault.db") as db:
        after = db.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"]
        candidates = db.list_memory_candidates()
    assert after == before
    assert len(candidates) == 1
    assert candidates[0]["source"] == "dream"
    assert candidates[0]["memory_type"] == "dream_suggestion"
