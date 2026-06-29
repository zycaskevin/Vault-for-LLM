"""Automation cycle workspace and transcript-capture helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .automation_inbox import automation_inbox
from .automation_reports import _relative_to_project
from .db import VaultDB
from .task_ledger import list_tasks


def _write_cycle_workspace(project: Path, workspace: dict[str, Any], *, workspace_path: str | Path = "") -> str:
    report_dir = project / "reports" / "automation"
    report_dir.mkdir(parents=True, exist_ok=True)
    if workspace_path:
        raw = Path(workspace_path)
        candidate = raw if raw.is_absolute() else project / raw
        try:
            resolved = candidate.expanduser().resolve()
            allowed = report_dir.expanduser().resolve()
        except Exception as exc:
            raise ValueError(f"unable to resolve automation cycle workspace path: {exc}") from exc
        if allowed != resolved and allowed not in resolved.parents:
            raise ValueError("automation cycle workspace path must stay under reports/automation")
        path = resolved
    else:
        path = report_dir / "cycle-latest.json"
    data = dict(workspace)
    data["workspace_path"] = _relative_to_project(project, path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return _relative_to_project(project, path)


def _cycle_workspace(
    project: Path,
    *,
    generated_at: str,
    summary: dict[str, Any],
    evaluation: dict[str, Any],
    run: dict[str, Any],
    transcript_capture: dict[str, Any] | None = None,
    inbox_limit: int = 5,
    include_transcripts: bool = False,
    transcript_limit: int = 5,
) -> dict[str, Any]:
    inbox = automation_inbox(
        project,
        limit=max(1, min(int(inbox_limit or 5), 50)),
        include_content=False,
        include_transcripts=include_transcripts,
        transcript_limit=transcript_limit,
        write_handoff=False,
    )
    learning_policy = evaluation.get("learning_policy") or {}
    rules = learning_policy.get("rules") or []
    compact_rules = []
    for rule in rules[:10]:
        if not isinstance(rule, dict):
            continue
        compact_rules.append(
            {
                "source": rule.get("source", ""),
                "memory_type": rule.get("memory_type", ""),
                "action": rule.get("action", ""),
                "priority_multiplier": rule.get("priority_multiplier", 1.0),
                "evidence": rule.get("evidence", {}),
            }
        )
    inbox_summary = inbox.get("summary") or {}
    transcript_discovery = inbox.get("transcript_discovery") or {}
    capture = transcript_capture or _empty_transcript_capture(project, enabled=False, apply=False)
    capture_summary = capture.get("summary") or {}
    auto_promote_enabled = bool(summary.get("auto_promote_enabled", False))
    auto_promote_promoted = int(summary.get("auto_promote_promoted_count") or 0)
    task_snapshot = _active_task_snapshot(project)
    task_summary = task_snapshot.get("summary") or {}
    workspace = {
        "action": "cycle_workspace",
        "generated_at": generated_at,
        "project_dir": str(project),
        "status": run.get("status", "completed"),
        "summary": {
            "candidate_queue_items": len(inbox.get("review_queue") or []),
            "pending_candidates": int(inbox_summary.get("pending_candidates") or 0),
            "needs_review": int(inbox_summary.get("needs_review") or 0),
            "uncaptured_transcripts": int(inbox_summary.get("uncaptured_transcripts") or 0),
            "learning_rules": int(summary.get("learning_rules") or 0),
            "learning_readiness": summary.get("learning_readiness", ""),
            "automation_report_path": summary.get("automation_report_path", ""),
            "learning_policy_path": summary.get("learning_policy_path", ""),
            "transcript_capture_status": capture.get("status", ""),
            "transcript_capture_candidates_written": int(capture_summary.get("candidates_written") or 0),
            "auto_promote_enabled": auto_promote_enabled,
            "auto_promote_would_promote_count": int(summary.get("auto_promote_would_promote_count") or 0),
            "auto_promote_promoted_count": auto_promote_promoted,
            "active_tasks": int(task_summary.get("active") or 0),
            "blocked_tasks": int(task_summary.get("blocked") or 0),
        },
        "candidate_review": {
            "summary": inbox_summary,
            "queue": inbox.get("review_queue") or [],
            "content_hidden": True,
        },
        "transcripts_to_capture": {
            "summary": {
                "count": int(transcript_discovery.get("count") or 0),
                "read_contents": bool(transcript_discovery.get("read_contents", False)),
                "include_transcripts": bool(include_transcripts),
            },
            "items": transcript_discovery.get("transcripts") or [],
        },
        "transcript_capture": {
            "summary": capture_summary,
            "items": capture.get("items", []),
            "content_hidden": True,
            "reads_contents": bool((capture.get("safety") or {}).get("reads_transcript_contents", False)),
        },
        "curation_policy": {
            "path": evaluation.get("learning_policy_path", ""),
            "readiness": evaluation.get("readiness", ""),
            "event_count": int(evaluation.get("event_count") or 0),
            "bounds": learning_policy.get("bounds") or {},
            "rules": compact_rules,
        },
        "task_ledger": task_snapshot,
        "safety": {
            "read_only": True,
            "auto_promote": auto_promote_enabled,
            "hard_delete": False,
            "candidate_content_hidden": True,
            "transcript_discovery_reads_contents": False,
            "transcript_capture_reads_contents": bool((capture.get("safety") or {}).get("reads_transcript_contents", False)),
            "writes_active_memory": auto_promote_promoted > 0,
            "mutates_task_ledger": False,
        },
        "next_action": (
            "Review candidate_review.queue, auto-promote summary, and selected transcript paths; "
            "keep promotion policy narrow unless the user explicitly widens it."
        ),
        "workspace_path": "",
    }
    workspace["priority_brief"] = _cycle_priority_brief(workspace)
    workspace["suggested_next_tasks"] = _cycle_suggested_next_tasks(workspace)
    workspace["agent_start_prompt"] = _cycle_agent_start_prompt(workspace)
    return workspace


def _active_task_snapshot(project: Path, *, limit: int = 5) -> dict[str, Any]:
    db_path = project / "vault.db"
    if not db_path.exists():
        return {
            "summary": {"active": 0, "blocked": 0, "visible": 0},
            "tasks": [],
            "content_hidden": True,
        }
    with VaultDB(db_path) as db:
        active = list_tasks(db, status="active", limit=limit)
        blocked = list_tasks(db, status="blocked", limit=limit)
    tasks = [_compact_cycle_task(row) for row in [*blocked, *active][:limit]]
    return {
        "summary": {
            "active": len(active),
            "blocked": len(blocked),
            "visible": len(tasks),
        },
        "tasks": tasks,
        "content_hidden": True,
    }


def _compact_cycle_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task.get("id", ""),
        "title": task.get("title", "") or task.get("id", ""),
        "goal": task.get("goal", ""),
        "status": task.get("status", ""),
        "priority": task.get("priority", "P2"),
        "due_at": task.get("due_at", ""),
        "next_actions": (task.get("next_actions") or [])[:5],
        "blockers": (task.get("blockers") or [])[:5],
        "continuation_note": task.get("continuation_note", ""),
        "updated_at": task.get("updated_at", ""),
        "scope": task.get("scope", "project"),
        "sensitivity": task.get("sensitivity", "low"),
    }


def _empty_transcript_capture(project: Path, *, enabled: bool, apply: bool) -> dict[str, Any]:
    return {
        "action": "cycle_transcript_capture",
        "status": "disabled" if not enabled else "dry_run",
        "project_dir": str(project),
        "enabled": bool(enabled),
        "apply": bool(apply),
        "summary": {
            "transcripts_seen": 0,
            "transcripts_captured": 0,
            "candidates_extracted": 0,
            "candidates_written": 0,
            "candidates_rejected": 0,
        },
        "items": [],
        "safety": {
            "candidate_first": True,
            "auto_promote": False,
            "hard_delete": False,
            "reads_transcript_contents": False,
            "content_hidden": True,
        },
        "next_action": (
            "Pass --capture-transcripts with --apply, or enable session_capture_write_candidates "
            "in automation_policy.yaml, to turn discovered transcripts into review candidates."
        ),
    }


def _capture_transcript_candidates_for_cycle(
    project: Path,
    *,
    apply: bool,
    enabled: bool,
    limit: int,
    max_candidates_per_transcript: int,
    min_score: float,
) -> dict[str, Any]:
    """Optionally convert discovered session transcripts into candidates.

    This is deliberately opt-in and candidate-only. The cycle may read selected
    transcript contents only when both ``apply`` and ``enabled`` are true, and
    the returned payload strips candidate content previews before reports or
    handoffs can persist it.
    """
    if not enabled or not apply:
        return _empty_transcript_capture(project, enabled=enabled, apply=apply)

    db_path = project / "vault.db"
    if not db_path.exists():
        payload = _empty_transcript_capture(project, enabled=enabled, apply=apply)
        payload.update({
            "status": "blocked",
            "reason": "vault.db missing",
            "next_action": "Run vault init and compile before transcript capture automation.",
        })
        return payload

    from vault.session_capture import capture_session_candidates, discover_session_transcripts

    transcript_limit = max(1, min(int(limit or 3), 20))
    max_candidates = max(1, min(int(max_candidates_per_transcript or 5), 50))
    discovery = discover_session_transcripts(project, limit=transcript_limit)
    transcripts = discovery.get("transcripts") or []
    items: list[dict[str, Any]] = []
    extracted = 0
    written = 0
    rejected = 0

    with VaultDB(db_path) as db:
        for transcript in transcripts[:transcript_limit]:
            capture_path = str(transcript.get("capture_path") or "")
            if not capture_path:
                continue
            payload = capture_session_candidates(
                db,
                project / capture_path,
                input_format=str(transcript.get("format") or "auto"),
                source_system=str(transcript.get("source_system") or "auto"),
                agent_id="automation-cycle",
                write_candidates=True,
                max_candidates=max_candidates,
                min_score=min_score,
                scope="project",
                sensitivity="low",
                owner_agent="vault-automation",
                allowed_agents="",
                include_content=False,
            )
            extracted += int(payload.get("extracted") or 0)
            written += int(payload.get("written") or 0)
            rejected += int(payload.get("rejected") or 0)
            items.append(_compact_capture_result(capture_path, payload))

    return {
        "action": "cycle_transcript_capture",
        "status": "completed",
        "project_dir": str(project),
        "enabled": True,
        "apply": True,
        "summary": {
            "transcripts_seen": int(discovery.get("count") or 0),
            "transcripts_captured": len(items),
            "candidates_extracted": extracted,
            "candidates_written": written,
            "candidates_rejected": rejected,
        },
        "items": items,
        "safety": {
            "candidate_first": True,
            "auto_promote": False,
            "hard_delete": False,
            "reads_transcript_contents": bool(items),
            "content_hidden": True,
        },
        "next_action": "Review captured session candidates through automation inbox before promotion.",
    }


def _compact_capture_result(capture_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    candidates = []
    for item in payload.get("candidates") or []:
        if not isinstance(item, dict):
            continue
        candidates.append(
            {
                "candidate_id": item.get("candidate_id", ""),
                "title": item.get("title", ""),
                "status": item.get("status", ""),
                "rule": item.get("rule", ""),
                "score": item.get("score", 0),
                "source_ref": item.get("source_ref", ""),
                "gates": item.get("gates", {}),
            }
        )
    return {
        "capture_path": capture_path,
        "source_system": payload.get("source_system", ""),
        "input_format": payload.get("input_format", ""),
        "units_scanned": int(payload.get("units_scanned") or 0),
        "extracted": int(payload.get("extracted") or 0),
        "written": int(payload.get("written") or 0),
        "rejected": int(payload.get("rejected") or 0),
        "candidates": candidates,
        "content_hidden": True,
    }


def _cycle_priority_brief(workspace: dict[str, Any]) -> list[dict[str, Any]]:
    summary = workspace.get("summary") or {}
    curation = workspace.get("curation_policy") or {}
    items: list[dict[str, Any]] = []
    queue_count = int(summary.get("candidate_queue_items") or 0)
    needs_review = int(summary.get("needs_review") or 0)
    transcript_count = int(summary.get("uncaptured_transcripts") or 0)
    captured_candidates = int(summary.get("transcript_capture_candidates_written") or 0)
    auto_promoted = int(summary.get("auto_promote_promoted_count") or 0)
    auto_promote_preview = int(summary.get("auto_promote_would_promote_count") or 0)
    learning_rules = int(summary.get("learning_rules") or 0)
    if queue_count or needs_review:
        items.append(
            {
                "priority": "P1",
                "title": "Review candidate memory queue",
                "count": max(queue_count, needs_review),
                "reason": "Candidates need explicit promote/reject decisions before active memory changes.",
                "safe_action": "Review candidate ids and gates; keep raw content hidden until needed.",
            }
        )
    task_count = int(summary.get("active_tasks") or 0) + int(summary.get("blocked_tasks") or 0)
    if task_count:
        items.append(
            {
                "priority": "P1" if int(summary.get("blocked_tasks") or 0) else "P2",
                "title": "Resume active Task Ledger items",
                "count": task_count,
                "reason": "Task Ledger holds the current working set so agents can continue without promoting temporary state into memory.",
                "safe_action": "Read task handoff first, then update the task instead of writing active memory.",
            }
        )
    if transcript_count:
        items.append(
            {
                "priority": "P2",
                "title": "Capture selected transcript exports",
                "count": transcript_count,
                "reason": "Uncaptured transcript files may contain decisions or pitfalls not yet proposed as candidates.",
                "safe_action": "Inspect paths first; capture only selected files after confirming scope.",
            }
        )
    if captured_candidates:
        items.append(
            {
                "priority": "P1",
                "title": "Review auto-captured session candidates",
                "count": captured_candidates,
                "reason": "Transcript capture wrote candidates only; they need explicit review before active memory changes.",
                "safe_action": "Open automation inbox, inspect gates, then promote/reject/block deliberately.",
            }
        )
    if auto_promoted:
        items.append(
            {
                "priority": "P1",
                "title": "Review auto-promoted low-risk memories",
                "count": auto_promoted,
                "reason": "Policy allowed low-risk candidates to enter active memory automatically.",
                "safe_action": "Inspect promoted knowledge ids and feedback events before widening policy.",
            }
        )
    elif auto_promote_preview:
        items.append(
            {
                "priority": "P2",
                "title": "Review auto-promote preview",
                "count": auto_promote_preview,
                "reason": "Policy found candidates that would be auto-promoted if --apply is used.",
                "safe_action": "Verify gates, source_ref, sensitivity, and scope before applying.",
            }
        )
    if learning_rules:
        items.append(
            {
                "priority": "P2",
                "title": "Inspect curation learning rules",
                "count": learning_rules,
                "reason": "Reviewed candidate outcomes produced bounded sorting hints for the next Dream/curation pass.",
                "safe_action": "Use rules for ordering only; do not auto-promote or bypass privacy gates.",
            }
        )
    if curation.get("path") or summary.get("automation_report_path"):
        items.append(
            {
                "priority": "P3",
                "title": "Skim automation report and policy files",
                "count": 1,
                "reason": "The detailed ledger remains the source of truth for automation changes.",
                "safe_action": "Read bounded report sections before changing policy or archive behavior.",
            }
        )
    if not items:
        items.append(
            {
                "priority": "P3",
                "title": "No urgent review queue",
                "count": 0,
                "reason": "The latest cycle did not surface review pressure.",
                "safe_action": "Run a normal search or report review before making memory changes.",
            }
        )
    return items


def _cycle_suggested_next_tasks(workspace: dict[str, Any]) -> list[dict[str, Any]]:
    summary = workspace.get("summary") or {}
    task_ledger = workspace.get("task_ledger") or {}
    task_items = task_ledger.get("tasks") or []
    tasks: list[dict[str, Any]] = []
    step = 1
    if int(summary.get("active_tasks") or 0) or int(summary.get("blocked_tasks") or 0):
        task_id = str((task_items[0] or {}).get("id", "")) if task_items else ""
        tasks.append(
            {
                "step": step,
                "task": "Resume the current Task Ledger working set before opening broad memory.",
                "command": f"vault task handoff {task_id}" if task_id else "vault task status --status active --json",
                "requires_human_approval": False,
            }
        )
        step += 1
    if int(summary.get("candidate_queue_items") or 0) or int(summary.get("needs_review") or 0):
        tasks.append(
            {
                "step": step,
                "task": "Open the compact candidate queue and decide promote/reject/block explicitly.",
                "command": "vault automation inbox --limit 10",
                "requires_human_approval": True,
            }
        )
        step += 1
    if int(summary.get("uncaptured_transcripts") or 0):
        tasks.append(
            {
                "step": step,
                "task": "Review uncaptured transcript paths before selecting files to capture.",
                "command": "vault capture discover",
                "requires_human_approval": True,
            }
        )
        step += 1
    if int(summary.get("transcript_capture_candidates_written") or 0):
        tasks.append(
            {
                "step": step,
                "task": "Review newly captured session candidates; they are not active memory yet.",
                "command": "vault automation inbox --limit 10",
                "requires_human_approval": True,
            }
        )
        step += 1
    if int(summary.get("auto_promote_promoted_count") or 0):
        tasks.append(
            {
                "step": step,
                "task": "Review auto-promoted knowledge and keep the policy narrow.",
                "command": "vault automation report --latest --detail",
                "requires_human_approval": False,
            }
        )
        step += 1
    if summary.get("learning_policy_path"):
        tasks.append(
            {
                "step": step,
                "task": "Inspect bounded learning-policy hints before changing automation behavior.",
                "command": f"vault automation report --report-path {summary.get('learning_policy_path')}",
                "requires_human_approval": False,
            }
        )
        step += 1
    if summary.get("automation_report_path"):
        tasks.append(
            {
                "step": step,
                "task": "Read the detailed automation ledger if any archive or candidate action looks surprising.",
                "command": "vault automation report --latest --detail",
                "requires_human_approval": False,
            }
        )
    if not tasks:
        tasks.append(
            {
                "step": 1,
                "task": "No immediate queue pressure; run a normal bounded search before editing memory.",
                "command": "vault search \"current project memory\" --limit 5",
                "requires_human_approval": False,
            }
        )
    return tasks


def _cycle_agent_start_prompt(workspace: dict[str, Any]) -> str:
    summary = workspace.get("summary") or {}
    queue_count = int(summary.get("candidate_queue_items") or 0)
    transcript_count = int(summary.get("uncaptured_transcripts") or 0)
    learning_rules = int(summary.get("learning_rules") or 0)
    captured_candidates = int(summary.get("transcript_capture_candidates_written") or 0)
    auto_promoted = int(summary.get("auto_promote_promoted_count") or 0)
    active_tasks = int(summary.get("active_tasks") or 0)
    blocked_tasks = int(summary.get("blocked_tasks") or 0)
    return "\n".join(
        [
            "You are continuing a Vault-for-LLM memory automation cycle.",
            f"Project: {workspace.get('project_dir', '')}",
            "Start from this handoff, not the full raw reports.",
            (
                f"Candidate queue items: {queue_count}; uncaptured transcripts: {transcript_count}; "
                f"auto-captured candidates: {captured_candidates}; auto-promoted: {auto_promoted}; "
                f"learning rules: {learning_rules}; active tasks: {active_tasks}; blocked tasks: {blocked_tasks}."
            ),
            "If task_ledger.tasks is non-empty, resume from the task handoff before searching broad memory.",
            "Do not widen auto-promote policy, hard-delete memory, or read transcript contents just because a path is listed.",
            "Review priority_brief first, then use suggested_next_tasks one step at a time.",
            "Ask for approval before promoting/rejecting sensitive candidates or capturing private transcripts.",
        ]
    )


def _cycle_principle() -> str:
    return (
        "cycle updates bounded curation hints and candidate ordering only; "
        "it does not auto-promote by default, hard-delete memory, or override privacy/access policy; "
        "low-risk promotion requires explicit policy opt-in and --apply"
    )
