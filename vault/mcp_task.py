"""MCP handlers and schemas for Task Ledger runtime working sets."""

from __future__ import annotations

import json
from typing import Any


MCP_TASK_TOOL_NAMES = [
    "vault_task_start",
    "vault_task_status",
    "vault_task_update",
    "vault_task_handoff",
    "vault_task_complete",
]

MCP_TASK_TOOLS = [
    {
        "name": "vault_task_start",
        "description": "Start a Task Ledger working set. This is runtime task state, not long-term L0-L3 memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "Concrete task goal."},
                "task_id": {"type": "string", "description": "Optional stable task id.", "default": ""},
                "title": {"type": "string", "description": "Short display title.", "default": ""},
                "current_plan": {"type": "array", "items": {"type": "string"}, "default": []},
                "next_actions": {"type": "array", "items": {"type": "string"}, "default": []},
                "evidence_refs": {"type": "array", "items": {"type": "string"}, "default": []},
                "continuation_note": {"type": "string", "default": ""},
                "scope": {"type": "string", "enum": ["private", "project", "shared", "public"], "default": "project"},
                "sensitivity": {"type": "string", "enum": ["low", "medium", "high", "restricted"], "default": "low"},
                "owner_agent": {"type": "string", "default": ""},
                "allowed_agents": {"type": "array", "items": {"type": "string"}, "default": []},
            },
            "required": ["goal"],
        },
    },
    {
        "name": "vault_task_status",
        "description": "Read one Task Ledger item or list active working sets for task resume.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Optional task id. If omitted, lists tasks.", "default": ""},
                "status": {
                    "type": "string",
                    "enum": ["active", "blocked", "completed", "archived", "all"],
                    "description": "List filter when task_id is omitted.",
                    "default": "active",
                },
                "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
                "include_events": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "vault_task_update",
        "description": "Append progress, decisions, blockers, questions, evidence, or a continuation note to a Task Ledger item.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "current_plan": {"type": "array", "items": {"type": "string"}, "default": []},
                "completed": {"type": "array", "items": {"type": "string"}, "default": []},
                "hard_decisions": {"type": "array", "items": {"type": "string"}, "default": []},
                "blockers": {"type": "array", "items": {"type": "string"}, "default": []},
                "open_questions": {"type": "array", "items": {"type": "string"}, "default": []},
                "next_actions": {"type": "array", "items": {"type": "string"}, "default": []},
                "evidence_refs": {"type": "array", "items": {"type": "string"}, "default": []},
                "continuation_note": {"type": "string", "default": ""},
                "status": {"type": "string", "enum": ["active", "blocked", "completed", "archived", ""], "default": ""},
                "agent_id": {"type": "string", "default": ""},
                "source_ref": {"type": "string", "default": ""},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "vault_task_handoff",
        "description": "Render a compact Markdown handoff for another agent or future session.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "vault_task_complete",
        "description": "Mark a Task Ledger item completed and record a short closeout summary.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "summary": {"type": "string", "default": ""},
                "next_actions": {"type": "array", "items": {"type": "string"}, "default": []},
                "agent_id": {"type": "string", "default": ""},
            },
            "required": ["task_id"],
        },
    },
]


def _json_result(payload: dict[str, Any] | list[dict[str, Any]]) -> dict[str, str]:
    return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}


def _as_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _error_payload(message: str, *, next_action: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "error": message}
    if next_action:
        payload["next_action"] = next_action
    return payload


def handle_task_tool_call(name: str, arguments: dict[str, Any], *, db_path: str) -> dict[str, str] | None:
    """Handle MCP Task Ledger calls, or return ``None`` if unknown."""
    if name not in MCP_TASK_TOOL_NAMES:
        return None

    from vault.db import VaultDB
    from vault.task_ledger import complete_task, get_task, list_tasks, start_task, task_handoff, update_task

    arguments = arguments or {}
    try:
        with VaultDB(db_path) as db:
            if name == "vault_task_start":
                payload = start_task(
                    db,
                    str(arguments.get("goal") or ""),
                    task_id=str(arguments.get("task_id") or ""),
                    title=str(arguments.get("title") or ""),
                    current_plan=_as_list(arguments.get("current_plan")),
                    next_actions=_as_list(arguments.get("next_actions")),
                    evidence_refs=_as_list(arguments.get("evidence_refs")),
                    continuation_note=str(arguments.get("continuation_note") or ""),
                    scope=str(arguments.get("scope") or "project"),
                    sensitivity=str(arguments.get("sensitivity") or "low"),
                    owner_agent=str(arguments.get("owner_agent") or ""),
                    allowed_agents=_as_list(arguments.get("allowed_agents")),
                    source="mcp",
                )
                return _json_result(payload)

            if name == "vault_task_status":
                task_id = str(arguments.get("task_id") or "").strip()
                include_events = bool(arguments.get("include_events", False))
                if task_id:
                    task = get_task(db, task_id, include_events=include_events)
                    if not task:
                        return _json_result(_error_payload(f"task not found: {task_id}"))
                    return _json_result({"ok": True, "action": "status", "task": task})
                payload = {
                    "ok": True,
                    "action": "status",
                    "tasks": list_tasks(
                        db,
                        status=str(arguments.get("status") or "active"),
                        limit=_clamp_int(arguments.get("limit"), default=20, minimum=1, maximum=100),
                    ),
                }
                return _json_result(payload)

            if name == "vault_task_update":
                task_id = str(arguments.get("task_id") or "").strip()
                if not task_id:
                    return _json_result(_error_payload("task_id is required"))
                payload = update_task(
                    db,
                    task_id,
                    current_plan=_as_list(arguments.get("current_plan")),
                    completed=_as_list(arguments.get("completed")),
                    hard_decisions=_as_list(arguments.get("hard_decisions")),
                    blockers=_as_list(arguments.get("blockers")),
                    open_questions=_as_list(arguments.get("open_questions")),
                    next_actions=_as_list(arguments.get("next_actions")),
                    evidence_refs=_as_list(arguments.get("evidence_refs")),
                    continuation_note=(
                        str(arguments.get("continuation_note") or "")
                        if "continuation_note" in arguments
                        else None
                    ),
                    status=str(arguments.get("status") or "") or None,
                    agent_id=str(arguments.get("agent_id") or ""),
                    source_ref=str(arguments.get("source_ref") or ""),
                )
                return _json_result(payload)

            if name == "vault_task_handoff":
                task_id = str(arguments.get("task_id") or "").strip()
                if not task_id:
                    return _json_result(_error_payload("task_id is required"))
                return _json_result(task_handoff(db, task_id))

            if name == "vault_task_complete":
                task_id = str(arguments.get("task_id") or "").strip()
                if not task_id:
                    return _json_result(_error_payload("task_id is required"))
                return _json_result(
                    complete_task(
                        db,
                        task_id,
                        summary=str(arguments.get("summary") or ""),
                        next_actions=_as_list(arguments.get("next_actions")),
                        agent_id=str(arguments.get("agent_id") or ""),
                    )
                )
    except (KeyError, ValueError) as exc:
        return _json_result(
            _error_payload(
                str(exc),
                next_action={
                    "tool": "vault_task_status",
                    "arguments": {"status": "active", "limit": 10},
                    "instruction": "List active tasks, then retry with a valid task_id.",
                },
            )
        )

    return None
