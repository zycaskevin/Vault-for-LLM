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
        "vault_capture_discover",
        "vault_capture_session",
        "vault_automation_inbox",
        "vault_automation_activity",
        "vault_automation_brief",
        "vault_automation_handoff",
        "vault_cold_store_expired",
        "vault_memory_pipeline",
        "vault_memory_temporal_status",
        "vault_memory_reflection",
        "vault_update_status",
        "vault_dream_run",
    }.issubset(names)
    add_tool = next(tool for tool in TOOLS if tool["name"] == "vault_add")
    assert "Prefer vault_memory_propose" in add_tool["description"]
    search_tool = next(tool for tool in TOOLS if tool["name"] == "vault_search")
    assert "semantic" in search_tool["inputSchema"]["properties"]["mode"]["enum"]
    update_tool = next(tool for tool in TOOLS if tool["name"] == "vault_update_status")
    assert "doctor" in update_tool["inputSchema"]["properties"]
    assert "max_status_age_minutes" in update_tool["inputSchema"]["properties"]


def test_mcp_tool_profiles_reduce_visible_tool_schemas():
    from vault.mcp import select_tools

    core_names = [tool["name"] for tool in select_tools("core")]
    assert core_names == [
        "vault_search",
        "vault_read_range",
        "vault_memory_propose",
        "vault_stats",
        "vault_update_status",
        "vault_automation_activity",
        "vault_automation_brief",
        "vault_automation_handoff",
    ]
    assert "vault_memory_candidates" not in core_names

    review_names = [tool["name"] for tool in select_tools("review")]
    assert "vault_update_status" in review_names
    assert "vault_automation_activity" in review_names
    assert "vault_automation_brief" in review_names
    assert "vault_automation_handoff" in review_names
    assert "vault_memory_candidates" in review_names
    assert "vault_memory_review" in review_names
    assert "vault_capture_discover" in review_names
    assert "vault_capture_session" in review_names
    assert "vault_automation_inbox" in review_names
    assert "vault_memory_pipeline" in review_names
    assert "vault_memory_temporal_status" in review_names
    assert "vault_memory_reflection" in review_names
    assert "vault_capture_discover" not in core_names
    assert "vault_capture_session" not in core_names
    assert "vault_automation_inbox" not in core_names
    assert "vault_cold_store_expired" not in core_names
    assert "vault_memory_pipeline" not in core_names
    assert "vault_memory_temporal_status" not in core_names
    assert "vault_memory_reflection" not in core_names
    assert "vault_memory_review" not in core_names

    maintenance_names = {tool["name"] for tool in select_tools("maintenance")}
    assert "vault_cold_store_expired" in maintenance_names
    assert "vault_memory_pipeline" in maintenance_names
    assert "vault_memory_temporal_status" in maintenance_names
    assert "vault_memory_reflection" in maintenance_names

    full_names = {tool["name"] for tool in select_tools("full")}
    assert "vault_add" in full_names
    assert "vault_memory_review" in full_names
    assert "vault_update_status" in full_names
    assert "vault_automation_brief" in full_names
    assert "vault_automation_handoff" in full_names
    assert "vault_cold_store_expired" in full_names
    assert "vault_memory_pipeline" in full_names
    assert "vault_memory_temporal_status" in full_names
    assert "vault_memory_reflection" in full_names
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


def test_mcp_update_status_reports_agent_registry(tmp_path, monkeypatch):
    from vault import __version__
    from vault.agent_registry import register_agent

    monkeypatch.setenv("VAULT_AGENT_REGISTRY_DIR", str(tmp_path / "registry"))
    project = tmp_path / "shared-project"
    private_project = tmp_path / "private-project"
    project.mkdir()

    register_agent(
        agent="codex",
        project_dir=project,
        scope="shared",
        features=["core", "mcp"],
        memory_layout="hybrid",
        private_project_dir=private_project,
    )

    payload = _payload(
        handle_tool_call(
            "vault_update_status",
            {
                "latest_version": "9.9.9",
                "write_status": True,
            },
        )
    )

    assert payload["installed_version"] == __version__
    assert payload["latest_version"] == "9.9.9"
    assert payload["update_available"] is True
    assert payload["agent_count"] == 1
    assert payload["agents"][0]["agent_id"] == "codex"
    assert payload["private_projects"] == [str(private_project.resolve())]
    assert f"vault automation handoff --project-dir {project.resolve()}" in payload["startup_commands"]
    assert payload["agent_update_notice_count"] == 1
    assert payload["agent_update_notices"][0]["agent_id"] == "codex"
    assert payload["agent_update_notices"][0]["behind_latest_known"] is True
    assert "9.9.9" in payload["agent_update_notices"][0]["recommended_action"]
    assert (tmp_path / "registry" / "update-status.json").exists()

    read_payload = _payload(
        handle_tool_call(
            "vault_update_status",
            {
                "read_status": True,
                "agent_id": "codex",
            },
        )
    )
    assert read_payload["ok"] is True
    assert read_payload["action"] == "read_status"
    assert read_payload["agent_update_notices"][0]["latest_known_version"] == "9.9.9"
    assert read_payload["startup_agent_id"] == "codex"
    assert read_payload["startup_agent_registered"] is True
    assert read_payload["current_agent_needs_attention"] is True
    assert any("vault automation handoff" in step for step in read_payload["startup_checklist"])

    conflict_payload = _payload(
        handle_tool_call(
            "vault_update_status",
            {
                "read_status": True,
                "write_status": True,
            },
        )
    )
    assert conflict_payload["ok"] is False
    assert "cannot be combined" in conflict_payload["error"]


def test_mcp_update_status_doctor_handles_multi_agent_shared_vault(tmp_path, monkeypatch):
    from vault.agent_registry import register_agent

    monkeypatch.setenv("VAULT_AGENT_REGISTRY_DIR", str(tmp_path / "registry"))
    project = tmp_path / "shared-project"
    project.mkdir()
    for agent_id in ["codex", "claude-code", "openclaw", "hermes"]:
        register_agent(
            agent=agent_id,
            project_dir=project,
            scope="shared",
            features=["core", "mcp"],
            memory_layout="shared",
        )

    write_payload = _payload(handle_tool_call("vault_update_status", {"write_status": True}))
    assert write_payload["agent_count"] == 4

    doctor_payload = _payload(
        handle_tool_call(
            "vault_update_status",
            {
                "doctor": True,
                "agent_id": "openclaw",
            },
        )
    )
    assert doctor_payload["ok"] is True
    assert doctor_payload["status_exists"] is True
    assert doctor_payload["status_current_runtime_mismatch"] is False
    assert doctor_payload["agent_count"] == 4
    assert doctor_payload["agents_missing_from_status"] == []
    assert doctor_payload["agents_needing_attention"] == []
    assert doctor_payload["startup_agent_id"] == "openclaw"
    assert doctor_payload["startup_agent_registered"] is True
    assert doctor_payload["current_agent_needs_attention"] is False
    assert any("handoff" in step for step in doctor_payload["startup_checklist"])

    stored = json.loads((tmp_path / "registry" / "update-status.json").read_text(encoding="utf-8"))
    stored["installed_version"] = "0.0.1"
    (tmp_path / "registry" / "update-status.json").write_text(json.dumps(stored), encoding="utf-8")
    stale_payload = _payload(handle_tool_call("vault_update_status", {"doctor": True}))
    assert stale_payload["ok"] is False
    assert stale_payload["status_current_runtime_mismatch"] is True
    assert any("0.0.1" in action for action in stale_payload["recommended_actions"])


def test_mcp_automation_handoff_reads_existing_compact_handoff(tmp_path):
    _set_project_dir(tmp_path)
    report_dir = tmp_path / "reports" / "automation"
    report_dir.mkdir(parents=True)
    (report_dir / "cycle-latest.md").write_text(
        "# Daily handoff\n\n- Suggested next task: run bounded search before edits.\n",
        encoding="utf-8",
    )

    payload = _payload(handle_tool_call("vault_automation_handoff", {}))

    assert payload["action"] == "handoff"
    assert payload["status"] == "completed"
    assert payload["handoff_path"] == "reports/automation/cycle-latest.md"
    assert payload["content_type"] == "markdown"
    assert "bounded search" in payload["content"]
    assert payload["safety"]["read_only"] is True
    assert payload["safety"]["uses_existing_handoff_only"] is True


def test_mcp_automation_handoff_exposes_fleet_health_preface(tmp_path):
    _set_project_dir(tmp_path)
    report_dir = tmp_path / "reports" / "automation"
    report_dir.mkdir(parents=True)
    (report_dir / "fleet-health-latest.md").write_text(
        "# Fleet Health\n\n- Shared health panel is ready.\n",
        encoding="utf-8",
    )
    (report_dir / "cycle-latest.md").write_text(
        "# Daily handoff\n\n- Continue the cycle task.\n",
        encoding="utf-8",
    )
    (report_dir / "review-summary-latest.md").write_text(
        "# Review Summary\n\n- Human card is ready.\n",
        encoding="utf-8",
    )
    (report_dir / "learning-health-latest.md").write_text(
        "# Learning Health\n\n- Feedback loop is healthy.\n",
        encoding="utf-8",
    )

    payload = _payload(handle_tool_call("vault_automation_handoff", {}))

    assert payload["action"] == "handoff"
    assert payload["handoff_path"] == "reports/automation/cycle-latest.md"
    assert payload["fleet_health_path"] == "reports/automation/fleet-health-latest.md"
    assert payload["review_summary_path"] == "reports/automation/review-summary-latest.md"
    assert payload["learning_health_path"] == "reports/automation/learning-health-latest.md"
    assert "Shared health panel" in payload["fleet_health_content"]
    assert "Human card is ready" in payload["review_summary_content"]
    assert "Feedback loop is healthy" in payload["learning_health_content"]
    assert "Continue the cycle task" in payload["content"]
    assert "Shared health panel" not in payload["content"]
    assert "Human card is ready" not in payload["content"]
    assert "Feedback loop is healthy" not in payload["content"]


def test_mcp_automation_handoff_missing_is_bounded(tmp_path):
    _set_project_dir(tmp_path)

    payload = _payload(handle_tool_call("vault_automation_handoff", {}))

    assert payload["action"] == "handoff"
    assert payload["status"] == "missing"
    assert payload["content"] == ""
    assert payload["safety"]["read_only"] is True
    assert payload["next_action"].startswith("Run `vault automation cycle")


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


def test_mcp_capture_discover_lists_project_transcripts_without_content(tmp_path):
    _set_project_dir(tmp_path)
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    token = "FAKE_OPENAI_KEY_FOR_DISCOVERY_TEST"
    transcript = sessions / "codex-session.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "role": "assistant",
                "content": f"Decision: discovery must not expose {token} from transcript content.",
            }
        ),
        encoding="utf-8",
    )

    discovered = _payload(handle_tool_call("vault_capture_discover", {"limit": 5}))
    rendered = json.dumps(discovered, ensure_ascii=False)

    assert discovered["action"] == "discover_session_transcripts"
    assert discovered["read_contents"] is False
    assert discovered["count"] == 1
    assert discovered["transcripts"][0]["capture_path"] == "sessions/codex-session.jsonl"
    assert discovered["transcripts"][0]["source_system"] == "codex"
    assert token not in rendered


def test_mcp_capture_discover_result_can_feed_capture_session(tmp_path):
    _set_project_dir(tmp_path)
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "codex-session.md").write_text(
        "Decision: discovered capture paths should feed MCP session capture because agents need a two-step loop.",
        encoding="utf-8",
    )

    discovered = _payload(handle_tool_call("vault_capture_discover", {}))
    capture_path = discovered["transcripts"][0]["capture_path"]
    captured = _payload(handle_tool_call(
        "vault_capture_session",
        {
            "transcript_path": capture_path,
            "source_system": "codex",
        },
    ))

    assert captured["status"] == "completed"
    assert captured["write_candidates"] is False
    assert captured["extracted"] == 1
    assert captured["candidates"][0]["status"] == "preview"


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


def test_mcp_automation_inbox_can_include_transcript_hints(tmp_path):
    _set_project_dir(tmp_path)
    with VaultDB(tmp_path / "vault.db"):
        pass
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    token = "FAKE_OPENAI_KEY_FOR_INBOX_TEST"
    (sessions / "codex-session.md").write_text(
        f"Decision: MCP automation inbox discovery must not expose {token} from transcript content.",
        encoding="utf-8",
    )

    inbox = _payload(handle_tool_call(
        "vault_automation_inbox",
        {
            "include_transcripts": True,
            "transcript_limit": 2,
        },
    ))
    rendered = json.dumps(inbox, ensure_ascii=False)

    assert inbox["summary"]["uncaptured_transcripts"] == 1
    assert inbox["transcript_discovery"]["read_contents"] is False
    assert inbox["transcript_discovery"]["transcripts"][0]["capture_path"] == "sessions/codex-session.md"
    assert token not in rendered


def test_mcp_memory_pipeline_temporal_and_reflection(tmp_path):
    _set_project_dir(tmp_path)
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "codex-session.md").write_text(
        "Decision: MCP memory pipeline should write review candidates before active memory.\n"
        "Bug fix: Reflection should stay report-first and candidate-first.\n",
        encoding="utf-8",
    )
    with VaultDB(tmp_path / "vault.db") as db:
        db.add_knowledge(
            title="Current location",
            content_raw="The office is now in City B.",
            valid_from="2026-06-25T00:00:00Z",
        )
        db.add_knowledge(
            title="Past location",
            content_raw="The office used to be in City A.",
            valid_until="2026-06-24T00:00:00Z",
        )

    pipeline = _payload(handle_tool_call(
        "vault_memory_pipeline",
        {
            "search_dirs": ["sessions"],
            "write_candidates": True,
            "write_report": True,
            "transcript_limit": 2,
            "source_system": "codex",
        },
    ))
    temporal = _payload(handle_tool_call("vault_memory_temporal_status", {}))
    past = _payload(handle_tool_call("vault_memory_temporal_status", {"state": "past"}))
    reflection = _payload(handle_tool_call("vault_memory_reflection", {"write_candidates": True, "limit": 5}))

    assert pipeline["action"] == "memory_pipeline_run"
    assert pipeline["candidate_count"] == 2
    assert pipeline["report_path"] == "reports/automation/pipeline-latest.json"
    assert (tmp_path / pipeline["report_markdown_path"]).exists()
    assert temporal["counts"]["current"] == 1
    assert temporal["counts"]["past"] == 1
    assert past["items"][0]["title"] == "Past location"
    assert reflection["action"] == "memory_reflection_run"
    assert reflection["safety"]["candidate_first"] is True


def test_mcp_automation_activity_reads_closed_loop_events_without_content(tmp_path):
    from vault.automation import automation_run

    _set_project_dir(tmp_path)
    (tmp_path / "automation_policy.yaml").write_text(
        "\n".join(
            [
                "mode: balanced",
                "auto_promote_low_risk_candidates: true",
                "auto_promote_max_per_run: 5",
                "",
            ]
        ),
        encoding="utf-8",
    )
    content = (
        "Decision: MCP automation activity should explain auto-promote results "
        "without exposing candidate content."
    )
    proposed = _payload(handle_tool_call(
        "vault_memory_propose",
        {
            "title": "MCP automation activity",
            "content": content,
            "reason": "Exercise activity feed.",
            "source": "session_capture",
            "source_ref": "mcp:activity:1",
            "tags": "mcp,activity",
            "memory_type": "session_lesson",
            "trust": 0.82,
            "scope": "project",
            "sensitivity": "low",
        },
    ))
    automation_run(tmp_path, mode="balanced", apply=True, write_reports=True)

    activity = _payload(handle_tool_call("vault_automation_activity", {"limit": 2, "event_limit": 5}))
    rendered = json.dumps(activity, ensure_ascii=False)

    assert activity["action"] == "activity"
    assert activity["totals"]["promoted_count"] == 1
    assert activity["events"][0]["kind"] == "auto_promoted_low_risk"
    assert activity["events"][0]["candidate_id"] == proposed["candidate_id"]
    assert activity["safety"]["read_only"] is True
    assert "without exposing candidate content" not in rendered


def test_mcp_automation_brief_returns_intelligence_without_raw_content(tmp_path):
    _set_project_dir(tmp_path)
    expired = "2000-01-01T00:00:00+00:00"
    with VaultDB(tmp_path / "vault.db") as db:
        used_id = db.add_knowledge(
            "MCP brief cited SOP",
            "MCP brief should expose usage weights without dumping raw content.",
            expires_at=expired,
            category="workflow",
            tags="mcp,brief",
        )
        db.record_knowledge_access([used_id], cited=True)
    content = (
        "Decision: MCP brief should show a short review queue while keeping "
        "candidate content outside the payload."
    )
    proposed = _payload(handle_tool_call(
        "vault_memory_propose",
        {
            "title": "MCP brief review lesson",
            "content": content,
            "reason": "Exercise automation brief.",
            "source": "session_capture",
            "source_ref": "mcp:brief:1",
            "tags": "mcp,brief",
            "memory_type": "session_lesson",
            "trust": 0.82,
            "scope": "project",
            "sensitivity": "low",
        },
    ))

    brief = _payload(handle_tool_call("vault_automation_brief", {"limit": 5, "review_limit": 5, "min_events": 1}))
    rendered = json.dumps(brief, ensure_ascii=False)

    assert brief["action"] == "brief"
    assert brief["safety"]["read_only"] is True
    assert brief["safety"]["includes_raw_candidate_content"] is False
    assert brief["memory_weights"]["top_used"][0]["knowledge_id"] == used_id
    assert brief["forgetting_strategy"]["used_expired_count"] == 1
    assert any(item["id"] == proposed["candidate_id"] for item in brief["human_review_5_percent"]["items"])
    assert "candidate content outside the payload" not in rendered


def test_mcp_cold_store_expired_defaults_to_dry_run_and_can_apply(tmp_path):
    _set_project_dir(tmp_path)
    expired = "2000-01-01T00:00:00+00:00"
    with VaultDB(tmp_path / "vault.db") as db:
        used_id = db.add_knowledge(
            "MCP cold-store used SOP",
            "MCP cold-store keeps original content for audit while archiving daily recall.",
            expires_at=expired,
        )
        db.record_knowledge_access([used_id], cited=True)

    preview = _payload(handle_tool_call("vault_cold_store_expired", {"limit": 10}))
    with VaultDB(tmp_path / "vault.db") as db:
        assert db.get_knowledge(used_id)["status"] == "active"

    assert preview["action"] == "cold-store-expired"
    assert preview["dry_run"] is True
    assert preview["eligible_count"] == 1
    assert preview["safety"]["hard_delete"] is False

    applied = _payload(handle_tool_call("vault_cold_store_expired", {"limit": 10, "apply": True}))
    with VaultDB(tmp_path / "vault.db") as db:
        row = db.get_knowledge(used_id)

    assert applied["dry_run"] is False
    assert applied["applied_count"] == 1
    assert row["status"] == "archived"
    assert "Cold-store summary" in row["summary"]
    assert row["content_raw"].startswith("MCP cold-store keeps original content")


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


def test_mcp_vault_add_requires_explicit_shared_write_permission(tmp_path):
    _set_project_dir(tmp_path)
    denied = _payload(handle_tool_call(
        "vault_add",
        {
            "title": "Shared direct write",
            "content": "Shared writes need an explicit agent write grant.",
            "scope": "shared",
            "sensitivity": "low",
        },
    ))
    assert denied["success"] is False
    assert denied["error"] == "write_access_denied"
    assert "allow_shared" in denied["message"]

    allowed = _payload(handle_tool_call(
        "vault_add",
        {
            "title": "Shared direct write",
            "content": "Shared writes need an explicit agent write grant.",
            "scope": "shared",
            "sensitivity": "low",
            "agent_id": "work-agent",
            "owner_agent": "work-agent",
            "allow_shared": True,
        },
    ))
    assert allowed["success"] is True
    with VaultDB(tmp_path / "vault.db") as db:
        assert db.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"] == 1


def test_mcp_memory_promote_requires_shared_write_permission(tmp_path):
    _set_project_dir(tmp_path)
    proposed = _payload(handle_tool_call(
        "vault_memory_propose",
        {
            "title": "Shared promote guard",
            "content": "Decision: shared memory promotion needs an explicit write grant.",
            "scope": "shared",
            "sensitivity": "low",
            "agent_id": "work-agent",
            "owner_agent": "work-agent",
            "allow_shared": True,
        },
    ))
    assert proposed["status"] == "candidate_created"

    denied = _payload(handle_tool_call(
        "vault_memory_promote",
        {
            "candidate_id": proposed["candidate_id"],
            "confirm": True,
            "agent_id": "work-agent",
        },
    ))
    assert denied["success"] is False
    assert denied["error"] == "write_access_denied"

    promoted = _payload(handle_tool_call(
        "vault_memory_promote",
        {
            "candidate_id": proposed["candidate_id"],
            "confirm": True,
            "agent_id": "work-agent",
            "allow_shared": True,
        },
    ))
    assert promoted["status"] == "promoted"


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


def test_mcp_rate_limiter_returns_retry_payload(tmp_path, monkeypatch):
    from vault import mcp as vault_mcp

    _set_project_dir(tmp_path)
    vault_mcp._reset_rate_limiter()
    monkeypatch.setenv("VAULT_MCP_RATE_LIMIT_PER_MINUTE", "1")
    monkeypatch.setenv("VAULT_MCP_RATE_LIMIT_BURST", "1")

    first = _payload(handle_tool_call("vault_stats", {"agent_id": "rate-agent"}))
    second = _payload(handle_tool_call("vault_stats", {"agent_id": "rate-agent"}))

    assert "knowledge_count" in first
    assert second["error"] == "rate_limited"
    assert second["failure_mode"] == "mcp_rate_limited"
    assert second["retry_after_seconds"] >= 1
    vault_mcp._reset_rate_limiter()


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
