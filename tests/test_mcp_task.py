import json

from vault.mcp import _set_project_dir, handle_tool_call


def _payload(result):
    assert "result" in result, result
    return json.loads(result["result"])


def test_mcp_task_ledger_lifecycle(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _set_project_dir(project)

    started = _payload(handle_tool_call(
        "vault_task_start",
        {
            "task_id": "task-mcp",
            "goal": "Wire Task Ledger into MCP",
            "title": "MCP Task Ledger",
            "current_plan": ["add task tools"],
            "next_actions": ["run tests"],
            "evidence_refs": ["pr:229"],
            "owner_agent": "codex",
        },
    ))
    assert started["ok"] is True
    assert started["task"]["id"] == "task-mcp"
    assert started["task"]["source"] == "mcp"

    listed = _payload(handle_tool_call("vault_task_status", {"status": "active", "limit": -10}))
    assert listed["ok"] is True
    assert [task["id"] for task in listed["tasks"]] == ["task-mcp"]

    updated = _payload(handle_tool_call(
        "vault_task_update",
        {
            "task_id": "task-mcp",
            "completed": ["dispatcher wired"],
            "hard_decisions": ["keep task tools outside core profile"],
            "blockers": ["none"],
            "open_questions": ["add GUI task panel later?"],
            "next_actions": ["document MCP tools"],
            "evidence_refs": ["file:tests/test_mcp_task.py"],
            "continuation_note": "Use vault_task_handoff before switching agents.",
            "agent_id": "codex",
            "source_ref": "test",
        },
    ))
    task = updated["task"]
    assert task["completed"] == ["dispatcher wired"]
    assert task["hard_decisions"] == ["keep task tools outside core profile"]
    assert task["continuation_note"] == "Use vault_task_handoff before switching agents."

    status = _payload(handle_tool_call(
        "vault_task_status",
        {"task_id": "task-mcp", "include_events": True},
    ))
    assert status["task"]["events"][-1]["agent_id"] == "codex"

    handoff = _payload(handle_tool_call("vault_task_handoff", {"task_id": "task-mcp"}))
    assert "Task Handoff: MCP Task Ledger" in handoff["markdown"]
    assert "keep task tools outside core profile" in handoff["markdown"]

    completed = _payload(handle_tool_call(
        "vault_task_complete",
        {"task_id": "task-mcp", "summary": "MCP tools ready", "agent_id": "codex"},
    ))
    assert completed["task"]["status"] == "completed"
    assert completed["task"]["completed_at"]


def test_mcp_task_errors_are_structured(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _set_project_dir(project)

    missing = _payload(handle_tool_call("vault_task_handoff", {"task_id": "missing"}))
    assert missing["ok"] is False
    assert "task not found" in missing["error"]
    assert missing["next_action"]["tool"] == "vault_task_status"
