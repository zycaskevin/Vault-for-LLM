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
                "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"], "default": "P2"},
                "due_at": {"type": "string", "default": ""},
                "scope": {"type": "string", "enum": ["private", "project", "shared", "public"], "default": "project"},
                "sensitivity": {"type": "string", "enum": ["low", "medium", "high", "restricted"], "default": "low"},
                "owner_agent": {"type": "string", "default": ""},
                "allowed_agents": {"type": "array", "items": {"type": "string"}, "default": []},
                "allow_shared": {"type": "boolean", "default": False},
                "allow_private": {"type": "boolean", "default": False},
                "allow_high_sensitivity": {"type": "boolean", "default": False},
                "allow_restricted": {"type": "boolean", "default": False},
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
                "agent_id": {"type": "string", "default": ""},
                "include_private": {"type": "boolean", "default": False},
                "max_sensitivity": {"type": "string", "enum": ["low", "medium", "high", "restricted"], "default": "medium"},
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
                "priority": {"type": "string", "enum": ["", "P0", "P1", "P2", "P3"], "default": ""},
                "due_at": {"type": "string", "default": ""},
                "status": {"type": "string", "enum": ["active", "blocked", "completed", "archived", ""], "default": ""},
                "agent_id": {"type": "string", "default": ""},
                "source_ref": {"type": "string", "default": ""},
                "allow_shared": {"type": "boolean", "default": False},
                "allow_private": {"type": "boolean", "default": False},
                "allow_high_sensitivity": {"type": "boolean", "default": False},
                "allow_restricted": {"type": "boolean", "default": False},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "vault_task_handoff",
        "description": "Render a compact Markdown handoff for another agent or future session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "agent_id": {"type": "string", "default": ""},
                "include_private": {"type": "boolean", "default": False},
                "max_sensitivity": {"type": "string", "enum": ["low", "medium", "high", "restricted"], "default": "medium"},
            },
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
                "allow_shared": {"type": "boolean", "default": False},
                "allow_private": {"type": "boolean", "default": False},
                "allow_high_sensitivity": {"type": "boolean", "default": False},
                "allow_restricted": {"type": "boolean", "default": False},
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


def _task_lookup_next_action(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments or {}
    return {
        "tool": "vault_task_status",
        "arguments": {"status": "active", "limit": 10, "agent_id": arguments.get("agent_id", "")},
        "instruction": "List active tasks, then retry with a valid task_id.",
    }


def _read_policy(arguments: dict[str, Any]):
    from vault.access_policy import normalize_read_policy

    return normalize_read_policy(
        agent_id=arguments.get("agent_id", ""),
        include_private=bool(arguments.get("include_private", False)),
        max_sensitivity=arguments.get("max_sensitivity") or "medium",
    )


def _write_policy(arguments: dict[str, Any]):
    from vault.access_policy import normalize_write_policy

    return normalize_write_policy(
        agent_id=arguments.get("agent_id", ""),
        allow_shared=bool(arguments.get("allow_shared", False)),
        allow_private=bool(arguments.get("allow_private", False)),
        allow_high_sensitivity=bool(arguments.get("allow_high_sensitivity", False)),
        allow_restricted=bool(arguments.get("allow_restricted", False)),
    )


def _can_read_task(task: dict[str, Any] | None, arguments: dict[str, Any]) -> bool:
    if not task:
        return False
    from vault.access_policy import can_read_memory

    return can_read_memory(task, _read_policy(arguments))


def _write_denied(task_or_metadata: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any] | None:
    from vault.access_policy import can_write_memory

    ok, reason = can_write_memory(task_or_metadata, _write_policy(arguments))
    if ok:
        return None
    return _error_payload(
        f"access_denied: {reason}",
        next_action={
            "tool": "vault_task_status",
            "arguments": {"status": "active", "limit": 10, "agent_id": arguments.get("agent_id", "")},
            "instruction": "Retry with an authorized agent_id and the required allow_* capability flag.",
        },
    )


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
                denied = _write_denied(
                    {
                        "scope": arguments.get("scope", "project"),
                        "sensitivity": arguments.get("sensitivity", "low"),
                        "owner_agent": arguments.get("owner_agent", ""),
                        "allowed_agents": arguments.get("allowed_agents", []),
                    },
                    arguments,
                )
                if denied is not None:
                    return _json_result(denied)
                payload = start_task(
                    db,
                    str(arguments.get("goal") or ""),
                    task_id=str(arguments.get("task_id") or ""),
                    title=str(arguments.get("title") or ""),
                    current_plan=_as_list(arguments.get("current_plan")),
                    next_actions=_as_list(arguments.get("next_actions")),
                    evidence_refs=_as_list(arguments.get("evidence_refs")),
                    continuation_note=str(arguments.get("continuation_note") or ""),
                    priority=str(arguments.get("priority") or "P2"),
                    due_at=str(arguments.get("due_at") or ""),
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
                        return _json_result(
                            _error_payload(
                                f"task not found: {task_id}",
                                next_action=_task_lookup_next_action(arguments),
                            )
                        )
                    if not _can_read_task(task, arguments):
                        return _json_result(_error_payload("access_denied: task is not readable for this agent"))
                    return _json_result({"ok": True, "action": "status", "task": task})
                tasks = [
                    task
                    for task in list_tasks(
                        db,
                        status=str(arguments.get("status") or "active"),
                        limit=_clamp_int(arguments.get("limit"), default=20, minimum=1, maximum=100),
                    )
                    if _can_read_task(task, arguments)
                ]
                payload = {
                    "ok": True,
                    "action": "status",
                    "tasks": tasks,
                }
                return _json_result(payload)

            if name == "vault_task_update":
                task_id = str(arguments.get("task_id") or "").strip()
                if not task_id:
                    return _json_result(_error_payload("task_id is required"))
                existing = get_task(db, task_id, include_events=False)
                if not existing:
                    return _json_result(
                        _error_payload(
                            f"task not found: {task_id}",
                            next_action=_task_lookup_next_action(arguments),
                        )
                    )
                denied = _write_denied(existing, arguments)
                if denied is not None:
                    return _json_result(denied)
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
                    priority=(str(arguments.get("priority") or "") or None),
                    due_at=(str(arguments.get("due_at") or "") if "due_at" in arguments else None),
                    status=str(arguments.get("status") or "") or None,
                    agent_id=str(arguments.get("agent_id") or ""),
                    source_ref=str(arguments.get("source_ref") or ""),
                )
                return _json_result(payload)

            if name == "vault_task_handoff":
                task_id = str(arguments.get("task_id") or "").strip()
                if not task_id:
                    return _json_result(_error_payload("task_id is required"))
                task = get_task(db, task_id, include_events=False)
                if not task:
                    return _json_result(
                        _error_payload(
                            f"task not found: {task_id}",
                            next_action=_task_lookup_next_action(arguments),
                        )
                    )
                if not _can_read_task(task, arguments):
                    return _json_result(_error_payload("access_denied: task is not readable for this agent"))
                return _json_result(task_handoff(db, task_id))

            if name == "vault_task_complete":
                task_id = str(arguments.get("task_id") or "").strip()
                if not task_id:
                    return _json_result(_error_payload("task_id is required"))
                existing = get_task(db, task_id, include_events=False)
                if not existing:
                    return _json_result(
                        _error_payload(
                            f"task not found: {task_id}",
                            next_action=_task_lookup_next_action(arguments),
                        )
                    )
                denied = _write_denied(existing, arguments)
                if denied is not None:
                    return _json_result(denied)
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
