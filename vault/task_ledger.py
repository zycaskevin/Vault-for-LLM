"""Task Ledger runtime working-set helpers.

Task Ledger is intentionally separate from L0-L3 active knowledge. It stores
the current state of one task so agents can resume work without turning every
temporary step into long-term memory.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import uuid
from typing import Any

from .db import VaultDB, normalize_governance_metadata


VALID_TASK_STATUSES = {"active", "blocked", "completed", "archived"}
LIST_FIELDS = {
    "current_plan": "current_plan_json",
    "completed": "completed_json",
    "hard_decisions": "hard_decisions_json",
    "blockers": "blockers_json",
    "open_questions": "open_questions_json",
    "next_actions": "next_actions_json",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slug(text: str) -> str:
    slug = re.sub(r"[^\w.-]+", "-", str(text or "").strip().lower(), flags=re.UNICODE)
    return slug.strip("-._") or "task"


def _new_task_id(goal: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"task_{stamp}_{_slug(goal)[:36]}_{uuid.uuid4().hex[:8]}"


def _json_list(value: Any = None) -> str:
    if value is None or value == "":
        return "[]"
    if isinstance(value, str):
        items = [value.strip()] if value.strip() else []
    else:
        items = [str(item).strip() for item in value if str(item).strip()]
    return json.dumps(items, ensure_ascii=False)


def _read_json_list(value: Any) -> list[str]:
    if not value:
        return []
    try:
        loaded = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    return [str(item) for item in loaded if str(item).strip()]


def _append_items(existing_json: str, additions: list[str] | tuple[str, ...] | None) -> str:
    items = _read_json_list(existing_json)
    for item in additions or []:
        text = str(item or "").strip()
        if text:
            items.append(text)
    return json.dumps(items, ensure_ascii=False)


def _row_to_task(row: Any) -> dict[str, Any]:
    task = dict(row)
    for field, column in LIST_FIELDS.items():
        task[field] = _read_json_list(task.pop(column, "[]"))
    return task


def _task_events(db: VaultDB, task_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = db.conn.execute(
        """SELECT id, task_id, created_at, event_type, content, agent_id, source_ref, payload_json
           FROM task_events
           WHERE task_id=?
           ORDER BY id DESC
           LIMIT ?""",
        (task_id, max(1, int(limit))),
    ).fetchall()
    events = []
    for row in rows:
        event = dict(row)
        try:
            event["payload"] = json.loads(event.pop("payload_json") or "{}")
        except json.JSONDecodeError:
            event["payload"] = {}
        events.append(event)
    return list(reversed(events))


def _task_evidence_refs(db: VaultDB, task_id: str) -> list[dict[str, Any]]:
    rows = db.conn.execute(
        """SELECT id, task_id, created_at, ref_type, ref, label, metadata_json
           FROM task_evidence_refs
           WHERE task_id=?
           ORDER BY id""",
        (task_id,),
    ).fetchall()
    refs = []
    for row in rows:
        ref = dict(row)
        try:
            ref["metadata"] = json.loads(ref.pop("metadata_json") or "{}")
        except json.JSONDecodeError:
            ref["metadata"] = {}
        refs.append(ref)
    return refs


def get_task(db: VaultDB, task_id: str, *, include_events: bool = True) -> dict[str, Any] | None:
    row = db.conn.execute(
        """SELECT id, created_at, updated_at, completed_at, status, title, goal,
                  current_plan_json, completed_json, hard_decisions_json, blockers_json,
                  open_questions_json, next_actions_json, continuation_note,
                  scope, sensitivity, owner_agent, allowed_agents, source
           FROM task_ledger
           WHERE id=?""",
        (task_id,),
    ).fetchone()
    if not row:
        return None
    task = _row_to_task(row)
    task["evidence_refs"] = _task_evidence_refs(db, task_id)
    if include_events:
        task["events"] = _task_events(db, task_id)
    return task


def list_tasks(db: VaultDB, *, status: str | None = "active", limit: int = 50) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    if status and status != "all":
        where = "WHERE status=?"
        params.append(status)
    params.append(max(1, int(limit)))
    rows = db.conn.execute(
        f"""SELECT id, created_at, updated_at, completed_at, status, title, goal,
                   current_plan_json, completed_json, hard_decisions_json, blockers_json,
                   open_questions_json, next_actions_json, continuation_note,
                   scope, sensitivity, owner_agent, allowed_agents, source
            FROM task_ledger
            {where}
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ?""",
        params,
    ).fetchall()
    return [_row_to_task(row) for row in rows]


def _insert_event(
    db: VaultDB,
    task_id: str,
    event_type: str,
    content: str = "",
    *,
    agent_id: str = "",
    source_ref: str = "",
    payload: dict[str, Any] | None = None,
) -> int:
    cur = db.conn.execute(
        """INSERT INTO task_events(
               task_id, created_at, event_type, content, agent_id, source_ref, payload_json
           ) VALUES(?, ?, ?, ?, ?, ?, ?)""",
        (
            task_id,
            _now(),
            event_type,
            str(content or "").strip(),
            str(agent_id or "").strip(),
            str(source_ref or "").strip(),
            json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
        ),
    )
    return int(cur.lastrowid)


def _insert_evidence_ref(
    db: VaultDB,
    task_id: str,
    ref: str,
    *,
    ref_type: str = "text",
    label: str = "",
    metadata: dict[str, Any] | None = None,
) -> int:
    cur = db.conn.execute(
        """INSERT INTO task_evidence_refs(
               task_id, created_at, ref_type, ref, label, metadata_json
           ) VALUES(?, ?, ?, ?, ?, ?)""",
        (
            task_id,
            _now(),
            str(ref_type or "text").strip() or "text",
            str(ref or "").strip(),
            str(label or "").strip(),
            json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
        ),
    )
    return int(cur.lastrowid)


def start_task(
    db: VaultDB,
    goal: str,
    *,
    task_id: str = "",
    title: str = "",
    current_plan: list[str] | None = None,
    next_actions: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    continuation_note: str = "",
    scope: str = "project",
    sensitivity: str = "low",
    owner_agent: str = "",
    allowed_agents: Any = None,
    source: str = "cli",
) -> dict[str, Any]:
    goal_text = str(goal or "").strip()
    if not goal_text:
        raise ValueError("goal is required")
    task_id = str(task_id or "").strip() or _new_task_id(goal_text)
    title_text = str(title or "").strip() or task_id
    governance = normalize_governance_metadata(
        scope=scope,
        sensitivity=sensitivity,
        owner_agent=owner_agent,
        allowed_agents=allowed_agents,
    )
    now = _now()
    db.conn.execute(
        """INSERT INTO task_ledger(
               id, created_at, updated_at, status, title, goal, current_plan_json,
               next_actions_json, continuation_note, scope, sensitivity, owner_agent,
               allowed_agents, source
           ) VALUES(?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            task_id,
            now,
            now,
            title_text,
            goal_text,
            _json_list(current_plan),
            _json_list(next_actions),
            str(continuation_note or "").strip(),
            governance["scope"],
            governance["sensitivity"],
            governance["owner_agent"],
            governance["allowed_agents"],
            str(source or "cli").strip() or "cli",
        ),
    )
    _insert_event(
        db,
        task_id,
        "started",
        goal_text,
        payload={"title": title_text, "source": str(source or "cli").strip() or "cli"},
    )
    for ref in evidence_refs or []:
        if str(ref or "").strip():
            _insert_evidence_ref(db, task_id, ref)
    db.conn.commit()
    task = get_task(db, task_id) or {}
    return {"ok": True, "action": "start", "task": task}


def update_task(
    db: VaultDB,
    task_id: str,
    *,
    current_plan: list[str] | None = None,
    completed: list[str] | None = None,
    hard_decisions: list[str] | None = None,
    blockers: list[str] | None = None,
    open_questions: list[str] | None = None,
    next_actions: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    continuation_note: str | None = None,
    status: str | None = None,
    agent_id: str = "",
    source_ref: str = "",
) -> dict[str, Any]:
    row = db.conn.execute("SELECT * FROM task_ledger WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise KeyError(f"task not found: {task_id}")
    updates: dict[str, Any] = {"updated_at": _now()}
    event_payload: dict[str, Any] = {}
    list_updates = {
        "current_plan": current_plan,
        "completed": completed,
        "hard_decisions": hard_decisions,
        "blockers": blockers,
        "open_questions": open_questions,
        "next_actions": next_actions,
    }
    for field, additions in list_updates.items():
        if additions:
            column = LIST_FIELDS[field]
            updates[column] = _append_items(row[column], additions)
            event_payload[field] = [str(item).strip() for item in additions if str(item).strip()]
    if continuation_note is not None:
        updates["continuation_note"] = str(continuation_note or "").strip()
        event_payload["continuation_note"] = updates["continuation_note"]
    if status:
        norm_status = str(status).strip().lower()
        if norm_status not in VALID_TASK_STATUSES:
            raise ValueError(f"invalid task status: {status}")
        updates["status"] = norm_status
        if norm_status == "completed":
            updates["completed_at"] = _now()
        event_payload["status"] = norm_status
    assignments = ", ".join(f"{column}=?" for column in updates)
    db.conn.execute(
        f"UPDATE task_ledger SET {assignments} WHERE id=?",
        [*updates.values(), task_id],
    )
    for ref in evidence_refs or []:
        if str(ref or "").strip():
            _insert_evidence_ref(db, task_id, ref)
    _insert_event(
        db,
        task_id,
        "updated",
        "; ".join(
            str(item)
            for values in event_payload.values()
            for item in (values if isinstance(values, list) else [values])
            if str(item).strip()
        ),
        agent_id=agent_id,
        source_ref=source_ref,
        payload=event_payload,
    )
    db.conn.commit()
    return {"ok": True, "action": "update", "task": get_task(db, task_id)}


def complete_task(
    db: VaultDB,
    task_id: str,
    *,
    summary: str = "",
    next_actions: list[str] | None = None,
    agent_id: str = "",
) -> dict[str, Any]:
    updates = {"status": "completed", "completed_at": _now()}
    payload: dict[str, Any] = {"summary": str(summary or "").strip()}
    row = db.conn.execute("SELECT * FROM task_ledger WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise KeyError(f"task not found: {task_id}")
    if next_actions:
        updates["next_actions_json"] = _append_items(row["next_actions_json"], next_actions)
        payload["next_actions"] = [str(item).strip() for item in next_actions if str(item).strip()]
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{column}=?" for column in updates)
    db.conn.execute(f"UPDATE task_ledger SET {assignments} WHERE id=?", [*updates.values(), task_id])
    _insert_event(db, task_id, "completed", str(summary or "").strip(), agent_id=agent_id, payload=payload)
    db.conn.commit()
    return {"ok": True, "action": "complete", "task": get_task(db, task_id)}


def task_handoff(db: VaultDB, task_id: str) -> dict[str, Any]:
    task = get_task(db, task_id)
    if not task:
        raise KeyError(f"task not found: {task_id}")
    title = task.get("title") or task.get("id")
    lines = [
        f"# Task Handoff: {title}",
        "",
        f"- task_id: {task.get('id')}",
        f"- status: {task.get('status')}",
        f"- goal: {task.get('goal')}",
        "",
    ]
    for heading, key in [
        ("Current Plan", "current_plan"),
        ("Completed", "completed"),
        ("Hard Decisions", "hard_decisions"),
        ("Blockers", "blockers"),
        ("Open Questions", "open_questions"),
        ("Next Actions", "next_actions"),
    ]:
        values = task.get(key) or []
        if values:
            lines.append(f"## {heading}")
            lines.extend(f"- {value}" for value in values)
            lines.append("")
    if task.get("evidence_refs"):
        lines.append("## Evidence Refs")
        for ref in task["evidence_refs"]:
            label = f" ({ref.get('label')})" if ref.get("label") else ""
            lines.append(f"- {ref.get('ref_type')}: {ref.get('ref')}{label}")
        lines.append("")
    if task.get("continuation_note"):
        lines.extend(["## Continuation Note", task["continuation_note"], ""])
    markdown = "\n".join(lines).rstrip() + "\n"
    return {"ok": True, "action": "handoff", "task": task, "markdown": markdown}
