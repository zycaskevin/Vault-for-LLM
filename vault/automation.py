"""Policy-based memory automation workflows.

Automation is intentionally reversible by default. Agents should do the daily
maintenance labor, while humans keep policy ownership and rollback paths.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

from .db import VaultDB
from .dream import run_dream
from .importance import MODEL_ID as IMPORTANCE_MODEL_ID
from .importance import compute_memory_importance
from .automation_reports import (
    _automation_report_files,
    _read_report,
    _relative_to_project,
    _report_summary,
    _resolve_report_path,
    _write_brief,
    _write_brief_markdown,
    _write_cycle_workspace_markdown,
    _write_fleet_health,
    _write_fleet_health_markdown,
    _write_learning_health,
    _write_learning_health_markdown,
    _write_report,
    _write_review_summary,
    _write_review_summary_markdown,
)
from .automation_learning import (
    LEARNING_POLICY_FILE,
    _apply_learning_priority,
    _feedback_learning_policy,
    _learning_health_cards,
    _learning_health_next_action,
    _learning_health_rule_counts,
    _learning_health_status,
    _learning_health_top_rules,
    _load_automation_learning_policy,
    _write_learning_policy,
)
from .automation_cycle import (
    _capture_transcript_candidates_for_cycle,
    _cycle_principle,
    _cycle_workspace,
    _write_cycle_workspace,
)
from .automation_inbox import automation_inbox
from .automation_policy import (
    DEFAULT_MODE,
    POLICY_FILE,
    default_policy,
    load_policy,
    normalize_mode as _normalize_mode,
    policy_float as _policy_float,
    policy_int as _policy_int,
    policy_list as _policy_list,
    write_policy,
)
from .automation_review import (
    apply_review_card_learning,
    find_review_summary_card,
    int_or_none,
    load_review_summary,
    review_card_title,
    review_feedback_score,
    review_feedback_source_ref,
)


def automation_plan(
    project_dir: str | Path,
    *,
    mode: str | None = None,
    limit: int = 50,
    write_policy_file: bool = False,
    overwrite_policy: bool = False,
) -> dict[str, Any]:
    project = Path(project_dir)
    policy = load_policy(project, mode=mode)
    mode_name = _normalize_mode(str(policy.get("mode") or DEFAULT_MODE))
    usage: dict[str, Any] = {}
    candidate_count = 0
    db_exists = (project / "vault.db").exists()
    if db_exists:
        with VaultDB(project / "vault.db") as db:
            usage = db.usage_stats(limit=limit)
            archive_preview = db.archive_expired_knowledge(
                limit=limit,
                dry_run=True,
                skip_used=bool(policy.get("protect_used_expired", True)),
                protected_scopes=_policy_list(policy, "protected_scopes"),
                protected_sensitivities=_policy_list(policy, "protected_sensitivities"),
            )
            candidate_count = len(db.list_memory_candidates(status="candidate", limit=1000))
    else:
        archive_preview = {}
    actions = _planned_actions(project, policy, usage, candidate_count)
    usage_review = _usage_review(policy, usage, archive_preview)
    policy_path = ""
    if write_policy_file:
        policy_path = write_policy(project, mode=mode_name, overwrite=overwrite_policy)
    return {
        "action": "plan",
        "mode": mode_name,
        "generated_at": _now(),
        "project_dir": str(project),
        "policy_path": policy_path or (POLICY_FILE if (project / POLICY_FILE).exists() else ""),
        "db_exists": db_exists,
        "usage": usage,
        "usage_review": usage_review,
        "candidate_count": candidate_count,
        "planned_actions": actions,
        "human_review": _review_summary(policy, usage, candidate_count, {}, usage_review),
    }


def automation_run(
    project_dir: str | Path,
    *,
    mode: str | None = None,
    apply: bool = False,
    limit: int = 50,
    write_reports: bool | None = None,
) -> dict[str, Any]:
    project = Path(project_dir)
    policy = load_policy(project, mode=mode)
    mode_name = _normalize_mode(str(policy.get("mode") or DEFAULT_MODE))
    report_enabled = bool(policy.get("write_reports", True)) if write_reports is None else bool(write_reports)
    db_path = project / "vault.db"
    if not db_path.exists():
        payload = {
            "action": "run",
            "mode": mode_name,
            "generated_at": _now(),
            "project_dir": str(project),
            "apply": bool(apply),
            "status": "blocked",
            "reason": "vault.db missing",
            "next_action": "Run vault init and vault compile before automation run.",
        }
        if report_enabled:
            payload["report_path"] = _write_report(project, payload)
        return payload

    with VaultDB(db_path) as db:
        before_usage = db.usage_stats(limit=limit)
        candidates = db.list_memory_candidates(status="candidate", limit=1000)
        candidate_count_before = len(candidates)
        archive_allowed = bool(policy.get("auto_archive_expired", False))
        archive_apply = bool(apply and archive_allowed)
        archive_result = db.archive_expired_knowledge(
            limit=limit,
            dry_run=not archive_apply,
            skip_used=bool(policy.get("protect_used_expired", True)),
            protected_scopes=_policy_list(policy, "protected_scopes"),
            protected_sensitivities=_policy_list(policy, "protected_sensitivities"),
        )
        cold_store_allowed = bool(policy.get("cold_store_used_expired", False))
        cold_store_apply = bool(apply and cold_store_allowed)
        cold_store_result = db.cold_store_expired_knowledge(
            limit=limit,
            dry_run=not cold_store_apply,
            min_usage=_policy_int(policy, "cold_store_min_usage", 1),
            summary_max_chars=_policy_int(policy, "cold_store_summary_max_chars", 360),
            protected_scopes=_policy_list(policy, "protected_scopes"),
            protected_sensitivities=_policy_list(policy, "protected_sensitivities"),
            protected_layers=_policy_list(policy, "cold_store_protected_layers") or ["L0", "L1"],
            target_layer=str(policy.get("cold_store_target_layer") or "L3"),
        )
        usage_review_before = _usage_review(policy, before_usage, archive_result)
        archive_ledger = _archive_action_ledger(archive_result, applied=archive_apply)
        cold_store_ledger = _cold_store_action_ledger(cold_store_result, applied=cold_store_apply)
        action_ledger = [*archive_ledger, *cold_store_ledger]
        dry_run_diff = _dry_run_diff(action_ledger, apply_requested=bool(apply), archive_allowed=archive_allowed)
        dry_run_diff["would_cold_store_count"] = int(cold_store_result.get("eligible_count") or 0)
        dry_run_diff["cold_store_applied_count"] = int(cold_store_result.get("applied_count") or 0)
        forgetting_results = (
            _write_forgetting_candidates(db, usage_review_before)
            if bool(apply and policy.get("forgetting_write_candidates", False))
            else []
        )

    dream = run_dream(
        project,
        mode="report",
        checks=policy.get("dream_checks") or None,
        limit=limit,
        write_report=report_enabled,
        write_candidates=bool(apply and policy.get("dream_write_candidates", False)),
        backup=False,
    )
    with VaultDB(db_path) as db:
        auto_promote = _auto_promote_low_risk_candidates(
            db,
            project=project,
            policy=policy,
            apply=apply,
        )
        after_usage = db.usage_stats(limit=limit)
        candidate_count_after = len(db.list_memory_candidates(status="candidate", limit=1000))

    forgetting = _forgetting_summary(forgetting_results)
    dry_run_diff["promote_candidates"] = bool(auto_promote.get("would_promote_count") or auto_promote.get("promoted_count"))
    if auto_promote.get("promoted_count"):
        dry_run_diff["applied_promotions_count"] = int(auto_promote.get("promoted_count") or 0)
    payload = {
        "action": "run",
        "mode": mode_name,
        "generated_at": _now(),
        "project_dir": str(project),
        "apply": bool(apply),
        "status": "completed",
        "policy": {
            "auto_archive_expired": archive_allowed,
            "cold_store_used_expired": cold_store_allowed,
            "cold_store_requires_apply": True,
            "cold_store_min_usage": _policy_int(policy, "cold_store_min_usage", 1),
            "cold_store_target_layer": str(policy.get("cold_store_target_layer") or "L3"),
            "protect_used_expired": bool(policy.get("protect_used_expired", True)),
            "protected_scopes": _policy_list(policy, "protected_scopes"),
            "protected_sensitivities": _policy_list(policy, "protected_sensitivities"),
            "auto_apply_safe_metadata": bool(policy.get("auto_apply_safe_metadata", False)),
            "dream_write_candidates": bool(policy.get("dream_write_candidates", False)),
            "dream_write_candidates_requires_apply": True,
            "forgetting_write_candidates": bool(policy.get("forgetting_write_candidates", False)),
            "forgetting_write_candidates_requires_apply": True,
            "auto_promote_low_risk_candidates": bool(policy.get("auto_promote_low_risk_candidates", False)),
            "auto_promote_requires_apply": True,
            "auto_promote_allowed_sources": _policy_list(policy, "auto_promote_allowed_sources"),
            "auto_promote_allowed_memory_types": _policy_list(policy, "auto_promote_allowed_memory_types"),
            "auto_promote_allowed_scopes": _policy_list(policy, "auto_promote_allowed_scopes"),
            "auto_promote_allowed_sensitivities": _policy_list(policy, "auto_promote_allowed_sensitivities"),
            "auto_promote_min_trust": _policy_float(policy, "auto_promote_min_trust", 0.65),
        },
        "usage_before": before_usage,
        "usage_after": after_usage,
        "usage_review": usage_review_before,
        "candidate_count": candidate_count_after,
        "candidate_count_before": candidate_count_before,
        "candidate_count_after": candidate_count_after,
        "archive_expired": archive_result,
        "cold_store_expired": cold_store_result,
        "action_ledger": action_ledger,
        "dry_run_diff": dry_run_diff,
        "forgetting": forgetting,
        "forgetting_results": forgetting_results,
        "auto_promote": auto_promote,
        "dream": dream,
        "human_review": _review_summary(
            policy,
            after_usage,
            candidate_count_after,
            dream,
            usage_review_before,
            forgetting,
            cold_store_result,
            auto_promote,
        ),
        "next_action": "Review human_review and report_path; adjust automation_policy.yaml before stronger autonomy.",
    }
    if apply and not archive_allowed:
        payload["warning"] = "apply requested, but policy auto_archive_expired is false"
    if apply and not cold_store_allowed and int(cold_store_result.get("eligible_count") or 0):
        payload["cold_store_warning"] = "apply requested, but policy cold_store_used_expired is false"
    if report_enabled:
        payload["report_path"] = _write_report(project, payload)
    return payload


def automation_cycle(
    project_dir: str | Path,
    *,
    mode: str | None = None,
    apply: bool = False,
    limit: int = 50,
    min_events: int = 5,
    write_reports: bool | None = None,
    write_workspace: bool = False,
    workspace_path: str | Path = "",
    inbox_limit: int = 5,
    include_transcripts: bool = False,
    transcript_limit: int = 5,
    capture_transcripts: bool = False,
    capture_transcript_limit: int = 3,
    capture_max_candidates_per_transcript: int = 5,
    capture_min_score: float = 0.55,
) -> dict[str, Any]:
    """Run one closed automation learning cycle.

    The cycle is intentionally composed from existing safe phases:
    feedback evaluation writes a bounded learning-policy handoff, then the
    normal automation run consumes that handoff through Dream. It never promotes
    candidates, hard-deletes memory, or bypasses access/privacy policy.
    """
    project = Path(project_dir)
    generated_at = _now()
    evaluation = automation_eval(
        project,
        limit=max(int(limit or 50), int(min_events or 1), 1),
        min_events=min_events,
        write_learning_policy=True,
    )
    if evaluation.get("status") == "blocked":
        return {
            "action": "cycle",
            "generated_at": generated_at,
            "project_dir": str(project),
            "status": "blocked",
            "phase": "eval",
            "eval": evaluation,
            "run": {},
            "summary": {
                "feedback_events": int(evaluation.get("event_count") or 0),
                "learning_rules": 0,
                "learning_policy_path": "",
                "dream_learning_policy_status": "",
                "dream_learning_policy_applied_rules": 0,
                "candidate_count_before": 0,
                "candidate_count_after": 0,
                "candidates_written": 0,
            },
            "principle": _cycle_principle(),
            "next_action": evaluation.get("next_action", "Initialize the vault before running automation cycle."),
        }

    policy = load_policy(project, mode=mode)
    transcript_capture = _capture_transcript_candidates_for_cycle(
        project,
        apply=apply,
        enabled=bool(capture_transcripts or policy.get("session_capture_write_candidates", False)),
        limit=capture_transcript_limit,
        max_candidates_per_transcript=capture_max_candidates_per_transcript,
        min_score=capture_min_score,
    )

    run = automation_run(
        project,
        mode=mode,
        apply=apply,
        limit=limit,
        write_reports=write_reports,
    )
    dream = run.get("dream") or {}
    dream_learning = dream.get("learning_policy") or {}
    dream_summary = dream.get("summary") or {}
    auto_promote = run.get("auto_promote") or {}
    learning_policy = evaluation.get("learning_policy") or {}
    summary = {
        "feedback_events": int(evaluation.get("event_count") or 0),
        "learning_rules": len(learning_policy.get("rules") or []),
        "learning_readiness": evaluation.get("readiness", ""),
        "learning_policy_path": evaluation.get("learning_policy_path", ""),
        "dream_learning_policy_status": dream_learning.get("status", ""),
        "dream_learning_policy_applied_rules": int(dream_learning.get("applied_rules") or 0),
        "candidate_count_before": int(run.get("candidate_count_before") or 0),
        "candidate_count_after": int(run.get("candidate_count_after") or 0),
        "candidates_written": int(dream_summary.get("candidates_written") or 0)
        + int((run.get("forgetting") or {}).get("candidates_written") or 0)
        + int((transcript_capture.get("summary") or {}).get("candidates_written") or 0),
        "automation_report_path": run.get("report_path", ""),
        "transcript_capture_status": transcript_capture.get("status", ""),
        "transcript_capture_candidates_written": int(
            (transcript_capture.get("summary") or {}).get("candidates_written") or 0
        ),
        "auto_promote_enabled": bool(auto_promote.get("enabled", False)),
        "auto_promote_would_promote_count": int(auto_promote.get("would_promote_count") or 0),
        "auto_promote_promoted_count": int(auto_promote.get("promoted_count") or 0),
    }
    workspace = _cycle_workspace(
        project,
        generated_at=generated_at,
        summary=summary,
        evaluation=evaluation,
        run=run,
        transcript_capture=transcript_capture,
        inbox_limit=inbox_limit,
        include_transcripts=include_transcripts,
        transcript_limit=transcript_limit,
    )
    payload = {
        "action": "cycle",
        "generated_at": generated_at,
        "project_dir": str(project),
        "status": run.get("status", "completed"),
        "mode": run.get("mode", ""),
        "apply": bool(apply),
        "eval": evaluation,
        "run": run,
        "transcript_capture": transcript_capture,
        "summary": summary,
        "workspace": workspace,
        "workspace_path": "",
        "human_review": run.get("human_review", {}),
        "principle": _cycle_principle(),
        "next_action": "Review candidate queue and automation report before approving stronger memory changes.",
    }
    if write_workspace:
        payload["workspace_path"] = _write_cycle_workspace(project, workspace, workspace_path=workspace_path)
        workspace["workspace_path"] = payload["workspace_path"]
        payload["workspace_markdown_path"] = _write_cycle_workspace_markdown(
            project,
            workspace,
            workspace_path=payload["workspace_path"],
        )
        workspace["workspace_markdown_path"] = payload["workspace_markdown_path"]
        _write_cycle_workspace(project, workspace, workspace_path=payload["workspace_path"])
        payload["summary"]["cycle_workspace_path"] = payload["workspace_path"]
        payload["summary"]["cycle_workspace_markdown_path"] = payload["workspace_markdown_path"]
    return payload


def automation_report(
    project_dir: str | Path,
    *,
    limit: int = 5,
    latest: bool = False,
    detail: bool = False,
    report_path: str | Path = "",
) -> dict[str, Any]:
    project = Path(project_dir)
    report_dir = project / "reports" / "automation"
    if report_path or latest or detail:
        path = _resolve_report_path(project, report_dir, report_path=report_path, latest=latest or detail)
        if path is None:
            return {
                "action": "report",
                "generated_at": _now(),
                "project_dir": str(project),
                "report_count": 0,
                "report": {},
                "detail": {},
                "status": "missing",
            }
        data = _read_report(path)
        summary = _report_summary(project, path, data)
        return {
            "action": "report",
            "generated_at": _now(),
            "project_dir": str(project),
            "report_count": 1,
            "report": summary,
            "detail": data if detail else {},
            "status": "completed" if data else "unreadable",
        }

    reports = _automation_report_files(report_dir)[: max(1, int(limit or 5))]
    items = []
    for path in reports:
        items.append(_report_summary(project, path, _read_report(path)))
    return {
        "action": "report",
        "generated_at": _now(),
        "project_dir": str(project),
        "report_count": len(items),
        "reports": items,
    }


def automation_activity(
    project_dir: str | Path,
    *,
    limit: int = 5,
    event_limit: int = 20,
) -> dict[str, Any]:
    """Return a compact, read-only automation activity feed.

    This is intended for agent startup and operator dashboards. It exposes
    decisions, reasons, and ids, but never raw candidate content.
    """
    project = Path(project_dir)
    report_dir = project / "reports" / "automation"
    reports = _automation_report_files(report_dir)[: max(1, int(limit or 5))]
    max_events = max(1, min(int(event_limit or 20), 100))
    events: list[dict[str, Any]] = []
    totals = {
        "reports_scanned": len(reports),
        "auto_promote_enabled_runs": 0,
        "would_promote_count": 0,
        "promoted_count": 0,
        "skipped_count": 0,
        "archive_applied_count": 0,
        "archive_skipped_count": 0,
        "cold_store_applied_count": 0,
        "cold_store_preview_count": 0,
        "cold_store_skipped_count": 0,
    }

    for path in reports:
        data = _read_report(path)
        report_path = str(path.relative_to(project))
        auto_promote = data.get("auto_promote") or {}
        if auto_promote.get("enabled"):
            totals["auto_promote_enabled_runs"] += 1
        totals["would_promote_count"] += int(auto_promote.get("would_promote_count") or 0)
        totals["promoted_count"] += int(auto_promote.get("promoted_count") or 0)
        totals["skipped_count"] += int(auto_promote.get("skipped_count") or 0)

        for item in auto_promote.get("items") or []:
            if len(events) >= max_events:
                break
            events.append(_auto_promote_activity_event(report_path, data, item))

        for item in data.get("action_ledger") or []:
            status = str(item.get("status") or "")
            operation = str(item.get("operation") or "")
            if operation == "cold_store_expired" and status == "applied":
                totals["cold_store_applied_count"] += 1
            elif operation == "cold_store_expired" and status == "preview":
                totals["cold_store_preview_count"] += 1
            elif operation == "cold_store_expired" and status:
                totals["cold_store_skipped_count"] += 1
            elif status == "applied":
                totals["archive_applied_count"] += 1
            elif status:
                totals["archive_skipped_count"] += 1
            if len(events) >= max_events:
                continue
            events.append(_ledger_activity_event(report_path, data, item))

    return {
        "action": "activity",
        "generated_at": _now(),
        "project_dir": str(project),
        "status": "completed" if reports else "missing",
        "report_count": len(reports),
        "totals": totals,
        "events": events[:max_events],
        "safety": {
            "read_only": True,
            "includes_raw_candidate_content": False,
            "writes_active_memory": False,
            "hard_delete": False,
        },
        "next_action": (
            "Review skipped reasons before widening automation policy."
            if reports
            else "Run `vault automation cycle --write-workspace` or `vault automation run` first."
        ),
    }


def automation_brief(
    project_dir: str | Path,
    *,
    limit: int = 5,
    review_limit: int = 5,
    min_events: int = 5,
    write_brief: bool = False,
    brief_path: str | Path = "",
) -> dict[str, Any]:
    """Build a compact automation intelligence brief.

    The brief joins the main closed-loop signals into one startup-safe payload:
    learning rules, usage weights, forgetting pressure, agent registry health,
    and the smallest useful human review list.
    """
    project = Path(project_dir)
    generated_at = _now()
    activity = automation_activity(project, limit=limit, event_limit=max(5, review_limit * 2))
    inbox = automation_inbox(project, limit=review_limit, include_content=False)
    evaluation = automation_eval(project, limit=1000, min_events=min_events)
    policy = load_policy(project)
    usage: dict[str, Any] = {}
    forgetting_strategy: dict[str, Any] = _empty_forgetting_strategy()
    db_path = project / "vault.db"
    if db_path.exists():
        with VaultDB(db_path) as db:
            usage = db.usage_stats(limit=max(1, min(int(limit or 5), 50)))
            archive_preview = db.archive_expired_knowledge(
                limit=max(1, min(int(limit or 5) * 5, 100)),
                dry_run=True,
                skip_used=bool(policy.get("protect_used_expired", True)),
                protected_scopes=_policy_list(policy, "protected_scopes"),
                protected_sensitivities=_policy_list(policy, "protected_sensitivities"),
            )
        forgetting_strategy = _brief_forgetting_strategy(usage, archive_preview)

    payload = {
        "action": "brief",
        "generated_at": generated_at,
        "project_dir": str(project),
        "status": "completed" if db_path.exists() else "blocked",
        "summary": _brief_summary(activity, inbox, evaluation, usage, forgetting_strategy),
        "learning": _brief_learning(evaluation, limit=limit),
        "memory_weights": _brief_memory_weights(usage, limit=limit),
        "forgetting_strategy": forgetting_strategy,
        "agent_health": _brief_agent_health(project),
        "human_review_5_percent": _brief_human_review(inbox, activity, limit=review_limit),
        "activity": {
            "totals": activity.get("totals", {}),
            "events": (activity.get("events") or [])[: max(1, min(int(review_limit or 5), 20))],
        },
        "safety": {
            "read_only": True,
            "writes_active_memory": False,
            "writes_candidates": False,
            "hard_delete": False,
            "includes_raw_candidate_content": False,
            "learning_is_ranking_hint_only": True,
            "forgetting_is_strategy_only": True,
        },
        "brief_path": "",
        "brief_markdown_path": "",
        "next_action": "Review human_review_5_percent first; keep automation policy narrow until repeated outcomes support widening.",
    }
    if write_brief:
        payload["brief_path"] = _write_brief(project, payload, brief_path=brief_path)
        payload["brief_markdown_path"] = _write_brief_markdown(project, payload, brief_path=payload["brief_path"])
        _write_brief(project, payload, brief_path=payload["brief_path"])
    return payload


def automation_review_summary(
    project_dir: str | Path,
    *,
    limit: int = 5,
    min_events: int = 5,
    write_summary: bool = False,
    summary_path: str | Path = "",
) -> dict[str, Any]:
    """Build the shortest human approval surface for automation.

    This is intentionally derived and read-only. It hides candidate content and
    compresses the existing brief/inbox/report signals into a few approval
    cards that a person can quickly accept, reject, or defer.
    """
    project = Path(project_dir)
    limit_i = max(1, min(int(limit or 5), 20))
    brief = automation_brief(project, limit=limit_i, review_limit=limit_i, min_events=min_events, write_brief=False)
    cards = _review_summary_cards(brief, limit=limit_i)
    required = any(card.get("requires_human_decision") for card in cards)
    payload = {
        "action": "review-summary",
        "generated_at": _now(),
        "project_dir": str(project),
        "status": brief.get("status", "completed"),
        "summary": {
            "cards": len(cards),
            "requires_human_decision": required,
            "pending_candidates": int((brief.get("summary") or {}).get("pending_candidates") or 0),
            "needs_review": int((brief.get("summary") or {}).get("needs_review") or 0),
            "expired_active": int((brief.get("summary") or {}).get("expired_active") or 0),
            "cold_store_preview": int((brief.get("summary") or {}).get("cold_store_preview") or 0),
            "cold_store_applied": int((brief.get("summary") or {}).get("cold_store_applied") or 0),
            "top_importance_score": max([float(card.get("importance_score") or 0.0) for card in cards], default=0.0),
        },
        "cards": cards,
        "safety": {
            "read_only": True,
            "writes_active_memory": False,
            "writes_candidates": False,
            "hard_delete": False,
            "includes_raw_candidate_content": False,
            "importance_is_ranking_hint_only": True,
            "learning_is_ranking_hint_only": True,
        },
        "review_summary_path": "",
        "review_summary_markdown_path": "",
        "next_action": (
            "Read only these cards first. Approve lifecycle changes only after checking "
            "bounded evidence or the compact automation report."
        ),
    }
    if write_summary:
        payload["review_summary_path"] = _write_review_summary(project, payload, summary_path=summary_path)
        payload["review_summary_markdown_path"] = _write_review_summary_markdown(
            project,
            payload,
            summary_path=payload["review_summary_path"],
        )
        _write_review_summary(project, payload, summary_path=payload["review_summary_path"])
    return payload


def automation_review_feedback(
    project_dir: str | Path,
    *,
    card_kind: str,
    card_id: str = "",
    decision: str,
    reason: str,
    recommended_action: str = "",
    score: float | None = None,
    summary_path: str | Path = "",
    min_events: int = 5,
    write_learning_policy: bool = False,
) -> dict[str, Any]:
    """Record a human/agent decision about a review-summary card.

    This is a feedback-only path. It never applies the card's recommended
    lifecycle action and never changes active memory.
    """
    project = Path(project_dir)
    db_path = project / "vault.db"
    generated_at = _now()
    if not db_path.exists():
        return {
            "action": "review-feedback",
            "generated_at": generated_at,
            "project_dir": str(project),
            "status": "blocked",
            "reason": "vault.db missing",
            "next_action": "Run vault init before recording automation review feedback.",
        }

    decision_norm = str(decision or "").strip().lower().replace("-", "_")
    if decision_norm not in {"accept", "reject", "defer"}:
        raise ValueError("review feedback decision must be accept, reject, or defer")
    reason_text = str(reason or "").strip()
    if not reason_text:
        raise ValueError("review feedback reason is required")
    kind = str(card_kind or "").strip()
    if not kind:
        raise ValueError("review feedback card_kind is required")
    card_id_s = str(card_id or "").strip()
    summary = load_review_summary(project, summary_path=summary_path)
    card = find_review_summary_card(summary, card_kind=kind, card_id=card_id_s)
    card_action = str(recommended_action or card.get("recommended_action") or decision_norm).strip()
    outcome = {"accept": "accepted", "reject": "rejected", "defer": "deferred"}[decision_norm]
    score_f = review_feedback_score(decision_norm, score)
    source_ref = review_feedback_source_ref(summary, card, kind, card_id_s)
    event = {
        "event_type": "review_card_outcome",
        "candidate_id": f"review:{kind}:{card_id_s or card_action}",
        "knowledge_id": int_or_none(card_id_s) if kind == "memory_importance" else None,
        "source": "review-summary",
        "source_ref": source_ref,
        "memory_type": kind,
        "category": card_action,
        "outcome": outcome,
        "score": score_f,
        "reason": reason_text,
        "payload_json": {
            "card_kind": kind,
            "card_id": card_id_s,
            "decision": decision_norm,
            "recommended_action": card_action,
            "card_found": bool(card),
            "card_title": card.get("title", ""),
            "importance_score": card.get("importance_score"),
            "summary_path": summary.get("review_summary_path", ""),
        },
    }
    with VaultDB(db_path) as db:
        event_id = db.record_memory_feedback(event)

    evaluation = automation_eval(
        project,
        limit=1000,
        min_events=max(1, int(min_events or 1)),
        write_learning_policy=write_learning_policy,
    )
    closed_loop: dict[str, Any] = {
        "learning_policy_written": bool(evaluation.get("learning_policy_path")),
        "review_summary_path": "",
        "review_summary_markdown_path": "",
        "learning_health_path": "",
        "learning_health_markdown_path": "",
        "review_cards": 0,
        "health_status": "",
        "top_learning_action": "",
    }
    if write_learning_policy:
        refreshed_summary = automation_review_summary(
            project,
            limit=5,
            min_events=max(1, int(min_events or 1)),
            write_summary=True,
        )
        refreshed_health = automation_learning_health(
            project,
            limit=5,
            min_events=max(1, int(min_events or 1)),
            write_health=True,
        )
        top_rules = (evaluation.get("learning_policy") or {}).get("rules", [])
        closed_loop.update(
            {
                "review_summary_path": refreshed_summary.get("review_summary_path", ""),
                "review_summary_markdown_path": refreshed_summary.get("review_summary_markdown_path", ""),
                "learning_health_path": refreshed_health.get("health_path", ""),
                "learning_health_markdown_path": refreshed_health.get("health_markdown_path", ""),
                "review_cards": int((refreshed_summary.get("summary") or {}).get("review_cards") or 0),
                "health_status": refreshed_health.get("status", ""),
                "top_learning_action": str((top_rules[0] or {}).get("action", "")) if top_rules else "",
            }
        )
    return {
        "action": "review-feedback",
        "generated_at": generated_at,
        "project_dir": str(project),
        "status": "completed",
        "event_id": event_id,
        "card": {
            "kind": kind,
            "id": card_id_s,
            "found_in_summary": bool(card),
            "title": card.get("title", ""),
            "recommended_action": card_action,
        },
        "feedback": {
            "decision": decision_norm,
            "outcome": outcome,
            "score": score_f,
            "reason": reason_text,
        },
        "learning": {
            "readiness": evaluation.get("readiness", ""),
            "event_count": int(evaluation.get("event_count") or 0),
            "learning_policy_path": evaluation.get("learning_policy_path", ""),
            "rules": (evaluation.get("learning_policy") or {}).get("rules", []),
        },
        "closed_loop": closed_loop,
        "safety": {
            "feedback_only": True,
            "writes_active_memory": False,
            "writes_candidates": False,
            "applies_recommended_action": False,
            "hard_delete": False,
            "learning_is_ranking_hint_only": True,
        },
        "next_action": (
            "Open review-summary-latest.md first; learning-health shows whether "
            "the feedback loop is healthy."
        ),
    }


def automation_handoff(
    project_dir: str | Path,
    *,
    source: str = "auto",
    handoff_path: str | Path = "",
) -> dict[str, Any]:
    from .automation_handoff import automation_handoff as _automation_handoff

    return _automation_handoff(project_dir, source=source, handoff_path=handoff_path)


def automation_eval(
    project_dir: str | Path,
    *,
    limit: int = 1000,
    min_events: int = 5,
    write_learning_policy: bool = False,
) -> dict[str, Any]:
    """Evaluate automation feedback so curation can improve over time."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    generated_at = _now()
    if not db_path.exists():
        return {
            "action": "eval",
            "generated_at": generated_at,
            "project_dir": str(project),
            "status": "blocked",
            "reason": "vault.db missing",
            "next_action": "Run vault init and create or import memory before automation eval.",
        }

    with VaultDB(db_path) as db:
        summary = db.memory_feedback_summary(limit=limit)
        pending = db.list_memory_candidates(status="candidate", limit=1000)

    groups = []
    for group in summary.get("groups", []):
        total = int(group.get("total") or 0)
        acceptance = float(group.get("acceptance_rate") or 0.0)
        if total < min_events:
            recommendation = "collect_more_feedback"
        elif acceptance >= 0.75:
            recommendation = "prefer"
        elif acceptance <= 0.25:
            recommendation = "downgrade_or_review_policy"
        else:
            recommendation = "keep_observing"
        groups.append({**group, "recommendation": recommendation})

    pending_by_type: dict[str, int] = {}
    pending_by_source: dict[str, int] = {}
    for row in pending:
        memory_type = str(row.get("memory_type") or "knowledge")
        source = str(row.get("source") or "")
        pending_by_type[memory_type] = pending_by_type.get(memory_type, 0) + 1
        pending_by_source[source] = pending_by_source.get(source, 0) + 1

    event_count = int(summary.get("event_count") or 0)
    readiness = "learning" if event_count >= min_events else "cold_start"
    learning_policy = _feedback_learning_policy(
        groups,
        generated_at=generated_at,
        event_count=event_count,
        min_events=max(1, int(min_events or 1)),
        readiness=readiness,
    )
    learning_policy_path = ""
    if write_learning_policy:
        learning_policy_path = _write_learning_policy(project, learning_policy)

    return {
        "action": "eval",
        "generated_at": generated_at,
        "project_dir": str(project),
        "status": "completed",
        "readiness": readiness,
        "event_count": event_count,
        "min_events": max(1, int(min_events or 1)),
        "outcome_counts": summary.get("outcome_counts", {}),
        "source_memory_type_scores": groups,
        "learning_policy": learning_policy,
        "learning_policy_path": learning_policy_path,
        "pending_candidates": {
            "count": len(pending),
            "by_memory_type": pending_by_type,
            "by_source": pending_by_source,
        },
        "recent_events": summary.get("recent_events", []),
        "principle": (
            "feedback guides future curation priority; it does not auto-promote, "
            "auto-delete, or override privacy/access policy"
        ),
        "next_action": "Review low-acceptance groups before allowing stronger automation policies.",
    }


def automation_learning_health(
    project_dir: str | Path,
    *,
    limit: int = 5,
    min_events: int = 5,
    write_health: bool = False,
    health_path: str | Path = "",
) -> dict[str, Any]:
    """Return a short health panel for automation feedback learning."""
    project = Path(project_dir)
    generated_at = _now()
    evaluation = automation_eval(
        project,
        limit=1000,
        min_events=max(1, int(min_events or 1)),
        write_learning_policy=False,
    )
    if evaluation.get("status") == "blocked":
        return {
            "action": "learning-health",
            "generated_at": generated_at,
            "project_dir": str(project),
            "status": "blocked",
            "reason": evaluation.get("reason", "automation eval blocked"),
            "health_path": "",
            "health_markdown_path": "",
            "next_action": evaluation.get("next_action", "Initialize the vault before checking learning health."),
        }

    limit_i = max(1, min(int(limit or 5), 20))
    learning_policy = evaluation.get("learning_policy") or {}
    rules = learning_policy.get("rules") or []
    outcome_counts = evaluation.get("outcome_counts") or {}
    event_count = int(evaluation.get("event_count") or 0)
    accepted_count = int(outcome_counts.get("accepted") or 0) + int(outcome_counts.get("promoted") or 0)
    rejected_count = int(outcome_counts.get("rejected") or 0) + int(outcome_counts.get("blocked") or 0)
    deferred_count = int(outcome_counts.get("deferred") or 0)
    positive_rate = accepted_count / event_count if event_count else 0.0
    rule_counts = _learning_health_rule_counts(rules)
    status = _learning_health_status(
        readiness=str(evaluation.get("readiness") or ""),
        event_count=event_count,
        min_events=max(1, int(min_events or 1)),
        rule_counts=rule_counts,
    )
    payload = {
        "action": "learning-health",
        "generated_at": generated_at,
        "project_dir": str(project),
        "status": status,
        "summary": {
            "readiness": evaluation.get("readiness", ""),
            "event_count": event_count,
            "min_events": max(1, int(min_events or 1)),
            "positive_rate": round(positive_rate, 4),
            "accepted_or_promoted": accepted_count,
            "rejected_or_blocked": rejected_count,
            "deferred": deferred_count,
            "active_rules": len(rules),
            "prefer_rules": rule_counts["prefer"],
            "downgrade_rules": rule_counts["downgrade"],
            "observe_rules": rule_counts["observe"],
        },
        "outcome_counts": outcome_counts,
        "cards": _learning_health_cards(evaluation, rules, limit=limit_i),
        "top_rules": _learning_health_top_rules(rules, limit=limit_i),
        "safety": {
            "read_only": True,
            "writes_active_memory": False,
            "writes_candidates": False,
            "hard_delete": False,
            "applies_learning_policy": False,
            "includes_raw_feedback_reasons": False,
            "learning_is_ranking_hint_only": True,
        },
        "health_path": "",
        "health_markdown_path": "",
        "next_action": _learning_health_next_action(status),
    }
    if write_health:
        payload["health_path"] = _write_learning_health(project, payload, health_path=health_path)
        payload["health_markdown_path"] = _write_learning_health_markdown(
            project,
            payload,
            health_path=payload["health_path"],
        )
        _write_learning_health(project, payload, health_path=payload["health_path"])
    return payload


def automation_fleet_health(
    project_dir: str | Path,
    *,
    limit: int = 5,
    min_events: int = 5,
    max_status_age_minutes: int = 24 * 60,
    write_health: bool = False,
    health_path: str | Path = "",
) -> dict[str, Any]:
    """Return a read-only multi-Agent automation health summary."""
    project = Path(project_dir)
    generated_at = _now()
    learning = automation_learning_health(
        project,
        limit=limit,
        min_events=min_events,
        write_health=False,
    )
    agent_health = _brief_agent_health(project)
    update_health = _automation_update_distribution_health(
        max_status_age_minutes=max_status_age_minutes,
    )
    agents = agent_health.get("agents") or []
    project_agents = [agent for agent in agents if agent.get("uses_this_project")]
    status = _fleet_health_status(
        learning_status=str(learning.get("status") or ""),
        agent_count=int(agent_health.get("agent_count") or 0),
        project_agent_count=len(project_agents),
        update_ok=bool(update_health.get("ok", False)),
        update_status_exists=bool(update_health.get("status_exists", False)),
    )
    payload = {
        "action": "fleet-health",
        "generated_at": generated_at,
        "project_dir": str(project),
        "status": status,
        "summary": {
            "registered_agents": int(agent_health.get("agent_count") or 0),
            "agents_for_project": len(project_agents),
            "learning_status": learning.get("status", ""),
            "learning_readiness": (learning.get("summary") or {}).get("readiness", ""),
            "learning_events": int((learning.get("summary") or {}).get("event_count") or 0),
            "learning_rules": int((learning.get("summary") or {}).get("active_rules") or 0),
            "update_status_exists": bool(update_health.get("status_exists", False)),
            "update_distribution_ok": bool(update_health.get("ok", False)),
            "agents_needing_attention": len(update_health.get("agents_needing_attention") or []),
            "agents_missing_from_status": len(update_health.get("agents_missing_from_status") or []),
        },
        "agents": project_agents[: max(1, min(int(limit or 5), 50))],
        "learning_health": {
            "status": learning.get("status", ""),
            "summary": learning.get("summary", {}),
            "cards": (learning.get("cards") or [])[: max(1, min(int(limit or 5), 20))],
            "top_rules": (learning.get("top_rules") or [])[: max(1, min(int(limit or 5), 20))],
        },
        "update_distribution": {
            "ok": bool(update_health.get("ok", False)),
            "status_exists": bool(update_health.get("status_exists", False)),
            "status_stale": bool(update_health.get("status_stale", False)),
            "status_current_runtime_mismatch": bool(update_health.get("status_current_runtime_mismatch", False)),
            "agents_needing_attention": update_health.get("agents_needing_attention") or [],
            "agents_missing_from_status": update_health.get("agents_missing_from_status") or [],
            "recommended_actions": (update_health.get("recommended_actions") or [])[: max(1, min(int(limit or 5), 20))],
        },
        "cards": _fleet_health_cards(
            learning=learning,
            agent_health=agent_health,
            update_health=update_health,
            project_agent_count=len(project_agents),
            limit=limit,
        ),
        "safety": {
            "read_only": True,
            "writes_active_memory": False,
            "writes_candidates": False,
            "hard_delete": False,
            "includes_raw_candidate_content": False,
            "includes_raw_feedback_reasons": False,
            "reads_private_memory": False,
            "registry_metadata_only": True,
        },
        "fleet_health_path": "",
        "fleet_health_markdown_path": "",
        "next_action": _fleet_health_next_action(status),
    }
    if write_health:
        payload["fleet_health_path"] = _write_fleet_health(project, payload, health_path=health_path)
        payload["fleet_health_markdown_path"] = _write_fleet_health_markdown(
            project,
            payload,
            health_path=payload["fleet_health_path"],
        )
        _write_fleet_health(project, payload, health_path=payload["fleet_health_path"])
    return payload



def _auto_promote_activity_event(
    report_path: str,
    data: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, Any]:
    promoted = str(item.get("promotion_status") or "") == "promoted"
    eligible = bool(item.get("eligible", False))
    if promoted:
        kind = "auto_promoted_low_risk"
    elif eligible:
        kind = "auto_promote_preview"
    else:
        kind = "auto_promote_skipped"
    sensitivity = str(item.get("sensitivity") or "")
    scope = str(item.get("scope") or "")
    hide_title = scope == "private" or sensitivity in {"high", "restricted"}
    return {
        "kind": kind,
        "report_path": report_path,
        "generated_at": data.get("generated_at", ""),
        "apply": bool(data.get("apply", False)),
        "candidate_id": item.get("candidate_id", ""),
        "knowledge_id": item.get("knowledge_id"),
        "title": "" if hide_title else item.get("title", ""),
        "title_hidden": hide_title,
        "source": item.get("source", ""),
        "source_ref": item.get("source_ref", ""),
        "memory_type": item.get("memory_type", ""),
        "scope": scope,
        "sensitivity": sensitivity,
        "trust": float(item.get("trust") or 0.0),
        "reason": item.get("reason", ""),
        "gate_statuses": item.get("gate_statuses", {}),
    }


def _ledger_activity_event(report_path: str, data: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    status = str(item.get("status") or "")
    operation = str(item.get("operation") or "")
    return {
        "kind": (
            "cold_store_applied"
            if operation == "cold_store_expired" and status == "applied"
            else "cold_store_preview"
            if operation == "cold_store_expired" and status == "preview"
            else "cold_store_skipped"
            if operation == "cold_store_expired"
            else "archive_applied"
            if status == "applied"
            else "archive_skipped"
        ),
        "report_path": report_path,
        "generated_at": data.get("generated_at", ""),
        "apply": bool(data.get("apply", False)),
        "knowledge_id": item.get("knowledge_id"),
        "operation": operation,
        "status": status,
        "reason": item.get("reason", ""),
        "risk": item.get("risk", ""),
    }


def _brief_summary(
    activity: dict[str, Any],
    inbox: dict[str, Any],
    evaluation: dict[str, Any],
    usage: dict[str, Any],
    forgetting_strategy: dict[str, Any],
) -> dict[str, Any]:
    activity_totals = activity.get("totals") or {}
    inbox_summary = inbox.get("summary") or {}
    return {
        "pending_candidates": int(inbox_summary.get("pending_candidates") or 0),
        "needs_review": int(inbox_summary.get("needs_review") or 0),
        "human_review_items": len(inbox.get("review_queue") or []),
        "learning_readiness": evaluation.get("readiness", "blocked"),
        "feedback_events": int(evaluation.get("event_count") or 0),
        "learning_rules": len((evaluation.get("learning_policy") or {}).get("rules") or []),
        "top_used_memories": len(usage.get("top_used") or []),
        "expired_active": int(usage.get("expired_active_count") or 0),
        "archiveable_expired": int(forgetting_strategy.get("archiveable_count") or 0),
        "used_expired": int(forgetting_strategy.get("used_expired_count") or 0),
        "auto_promote_promoted": int(activity_totals.get("promoted_count") or 0),
        "auto_promote_skipped": int(activity_totals.get("skipped_count") or 0),
        "cold_store_applied": int(activity_totals.get("cold_store_applied_count") or 0),
        "cold_store_preview": int(activity_totals.get("cold_store_preview_count") or 0),
    }


def _brief_learning(evaluation: dict[str, Any], *, limit: int = 5) -> dict[str, Any]:
    policy = evaluation.get("learning_policy") or {}
    rules = []
    for item in policy.get("rules") or []:
        if not isinstance(item, dict):
            continue
        rules.append(
            {
                "selector": item.get("selector", {}),
                "action": item.get("action", ""),
                "confidence": float(item.get("confidence") or 0.0),
                "priority_multiplier": float(item.get("priority_multiplier") or 1.0),
                "reason": item.get("reason", ""),
            }
        )
    rules.sort(key=lambda item: item["confidence"], reverse=True)
    return {
        "readiness": evaluation.get("readiness", ""),
        "event_count": int(evaluation.get("event_count") or 0),
        "outcome_counts": evaluation.get("outcome_counts", {}),
        "top_rules": rules[: max(1, min(int(limit or 5), 20))],
        "principle": "Learning rules sort future review work; they are not permission to auto-promote.",
    }


def _brief_memory_weights(usage: dict[str, Any], *, limit: int = 5) -> dict[str, Any]:
    items = []
    now = datetime.now(timezone.utc)
    for row in usage.get("top_used") or []:
        access = int(row.get("access_count") or 0)
        citations = int(row.get("citation_count") or 0)
        trust = max(0.0, min(float(row.get("trust") or 0.0), 1.0))
        freshness = max(0.0, min(float(row.get("freshness") or 0.0), 1.0))
        importance = compute_memory_importance(row, now=now)
        score = float(importance["importance_score"])
        items.append(
            {
                "knowledge_id": row.get("id"),
                "title": row.get("title", ""),
                "layer": row.get("layer", ""),
                "category": row.get("category", ""),
                "memory_type": row.get("memory_type", ""),
                "scope": row.get("scope", ""),
                "sensitivity": row.get("sensitivity", ""),
                "trust": trust,
                "freshness": freshness,
                "status": row.get("status", ""),
                "access_count": access,
                "citation_count": citations,
                "last_accessed_at": row.get("last_accessed_at", ""),
                "expires_at": row.get("expires_at", ""),
                "importance_score": score,
                "importance_components": importance["importance_components"],
                "signals": importance["signals"],
                "weight_score": score,
                "recommendation": importance["recommendation"],
            }
        )
    items.sort(
        key=lambda item: (
            float(item["importance_score"]),
            int(item["citation_count"]),
            int(item["access_count"]),
            float(item["trust"]),
        ),
        reverse=True,
    )
    return {
        "model": IMPORTANCE_MODEL_ID,
        "knowledge_count": int(usage.get("knowledge_count") or 0),
        "total_accesses": int(usage.get("total_accesses") or 0),
        "total_citations": int(usage.get("total_citations") or 0),
        "top_used": items[: max(1, min(int(limit or 5), 20))],
        "principle": "Importance is a small protection and ranking signal, not a source-of-truth override.",
    }


def _empty_forgetting_strategy() -> dict[str, Any]:
    return {
        "expired_active_count": 0,
        "archiveable_count": 0,
        "used_expired_count": 0,
        "protected_expired_count": 0,
        "strategy": "initialize_vault_first",
        "recommendations": [],
    }


def _brief_forgetting_strategy(usage: dict[str, Any], archive_preview: dict[str, Any]) -> dict[str, Any]:
    archiveable = int(len(archive_preview.get("items") or []))
    used_expired = int(len(archive_preview.get("skipped_used") or []))
    protected_expired = int(len(archive_preview.get("skipped_protected") or []))
    recommendations = []
    if archiveable:
        recommendations.append(
            {
                "action": "archive_candidate_or_apply_policy",
                "count": archiveable,
                "reason": "Expired memories have no usage/protection signal in the current policy preview.",
            }
        )
    if used_expired:
        recommendations.append(
            {
                "action": "summarize_then_cold_store",
                "count": used_expired,
                "reason": "Expired memories are still used; compress or summarize before removing from daily recall.",
            }
        )
    if protected_expired:
        recommendations.append(
            {
                "action": "human_review_required",
                "count": protected_expired,
                "reason": "Protected scope or sensitivity should not be automatically archived.",
            }
        )
    if not recommendations:
        recommendations.append(
            {
                "action": "keep_observing",
                "count": 0,
                "reason": "No urgent forgetting pressure was found.",
            }
        )
    return {
        "expired_active_count": int(usage.get("expired_active_count") or 0),
        "archiveable_count": archiveable,
        "used_expired_count": used_expired,
        "protected_expired_count": protected_expired,
        "strategy": "archive_unused_summarize_used_review_protected",
        "recommendations": recommendations,
    }


def _brief_agent_health(project: Path) -> dict[str, Any]:
    try:
        from vault.agent_registry import list_agents

        registry = list_agents()
    except Exception as exc:
        return {
            "status": "unavailable",
            "agent_count": 0,
            "agents": [],
            "reason": str(exc),
        }
    agents = []
    project_resolved = str(project.expanduser().resolve())
    for item in registry.get("agents") or []:
        project_dir = str(item.get("project_dir") or "")
        agents.append(
            {
                "agent_id": item.get("agent_id", ""),
                "scope": item.get("scope", ""),
                "tool_profile": item.get("tool_profile", ""),
                "memory_layout": item.get("memory_layout", ""),
                "vault_version": item.get("vault_version", ""),
                "last_seen_at": item.get("last_seen_at", ""),
                "uses_this_project": project_dir == project_resolved,
            }
        )
    return {
        "status": "completed",
        "registry_path": registry.get("registry_path", ""),
        "agent_count": int(registry.get("agent_count") or 0),
        "agents": agents,
        "principle": "Shared health is local registry metadata only; it does not expose private memories.",
    }


def _automation_update_distribution_health(*, max_status_age_minutes: int = 24 * 60) -> dict[str, Any]:
    try:
        from vault.agent_registry import build_update_distribution_health

        return build_update_distribution_health(max_age_minutes=max_status_age_minutes)
    except Exception as exc:
        return {
            "ok": False,
            "status_exists": False,
            "status_stale": True,
            "agents_needing_attention": [],
            "agents_missing_from_status": [],
            "recommended_actions": ["Unable to read update-distribution health; run `vault agent doctor` for details."],
            "error_type": type(exc).__name__,
        }


def _fleet_health_status(
    *,
    learning_status: str,
    agent_count: int,
    project_agent_count: int,
    update_ok: bool,
    update_status_exists: bool,
) -> str:
    if learning_status == "blocked":
        return "blocked"
    if agent_count <= 0 or project_agent_count <= 0:
        return "needs_review"
    if learning_status == "needs_review":
        return "needs_review"
    if not update_status_exists or not update_ok:
        return "watch"
    if learning_status in {"cold_start", "watch"}:
        return learning_status
    return "healthy"


def _fleet_health_cards(
    *,
    learning: dict[str, Any],
    agent_health: dict[str, Any],
    update_health: dict[str, Any],
    project_agent_count: int,
    limit: int = 5,
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    agent_count = int(agent_health.get("agent_count") or 0)
    if agent_count <= 0:
        cards.append(
            {
                "kind": "no_registered_agents",
                "priority": 95,
                "title": "No registered Agent runtimes",
                "reason": "No local runtimes are registered, so shared automation health cannot be distributed.",
                "safe_action": "Run `vault setup-agent` or `vault agent register` from each runtime that should share this vault.",
            }
        )
    elif project_agent_count <= 0:
        cards.append(
            {
                "kind": "no_project_agents",
                "priority": 88,
                "title": "No registered Agent points at this project vault",
                "reason": "The registry exists, but none of the registered runtimes use this project directory.",
                "safe_action": "Re-run setup-agent with the intended shared project directory.",
            }
        )
    learning_status = str(learning.get("status") or "")
    if learning_status in {"cold_start", "watch", "needs_review", "blocked"}:
        cards.append(
            {
                "kind": "learning_health",
                "priority": 84 if learning_status == "needs_review" else 70,
                "title": f"Learning health is {learning_status}",
                "reason": learning.get("next_action", ""),
                "safe_action": "Use review-summary and review-feedback to add explicit outcomes before widening automation.",
            }
        )
    if not bool(update_health.get("status_exists", False)):
        cards.append(
            {
                "kind": "missing_update_status",
                "priority": 78,
                "title": "Shared update-status file is missing",
                "reason": "Registered agents may not see the same version/update notice state.",
                "safe_action": "Run `vault update-status --write-status` from the shared runtime environment.",
            }
        )
    elif not bool(update_health.get("ok", False)):
        cards.append(
            {
                "kind": "update_distribution",
                "priority": 76,
                "title": "Update distribution needs attention",
                "reason": "; ".join(str(item) for item in (update_health.get("recommended_actions") or [])[:2]),
                "safe_action": "Refresh update status and restart or re-register only the listed runtimes.",
            }
        )
    cards.sort(key=lambda item: int(item.get("priority") or 0), reverse=True)
    return cards[: max(1, min(int(limit or 5), 20))]


def _fleet_health_next_action(status: str) -> str:
    if status == "healthy":
        return "Keep scheduled automation running and review only the short health reports first."
    if status == "cold_start":
        return "Collect more review feedback before trusting learned ranking hints."
    if status == "watch":
        return "Refresh update status and inspect learning-health cards before widening automation."
    if status == "blocked":
        return "Initialize the project vault before checking fleet health."
    return "Register project runtimes and review the highest-priority fleet health cards."


def _brief_human_review(inbox: dict[str, Any], activity: dict[str, Any], *, limit: int = 5) -> dict[str, Any]:
    max_items = max(1, min(int(limit or 5), 20))
    items = []
    digest = inbox.get("review_digest") or {}
    for row in digest.get("items") or []:
        items.append(
            {
                "kind": row.get("kind", ""),
                "id": row.get("id", ""),
                "title": row.get("title", ""),
                "priority": row.get("priority", 0),
                "reason": row.get("reason", ""),
                "recommended_action": row.get("recommended_action", ""),
            }
        )
        if len(items) >= max_items:
            break
    if len(items) >= max_items:
        return {
            "budget": max_items,
            "items": items[:max_items],
            "principle": "Show the smallest set of decisions a human should inspect; keep everything else agent-handled.",
        }
    for row in inbox.get("review_queue") or []:
        items.append(
            {
                "kind": "candidate_review",
                "id": row.get("id", ""),
                "title": row.get("title", ""),
                "priority": row.get("priority", 0),
                "reason": row.get("reason", ""),
                "recommended_action": row.get("recommended_action", ""),
            }
        )
        if len(items) >= max_items:
            break
    if len(items) < max_items:
        for event in activity.get("events") or []:
            if event.get("kind") not in {"auto_promote_skipped", "archive_skipped"}:
                continue
            items.append(
                {
                    "kind": event.get("kind", ""),
                    "id": event.get("candidate_id") or event.get("knowledge_id") or "",
                    "title": "" if event.get("title_hidden") else event.get("title", ""),
                    "priority": 70,
                    "reason": event.get("reason", ""),
                    "recommended_action": "review_policy_or_gate_reason",
                }
            )
            if len(items) >= max_items:
                break
    return {
        "budget": max_items,
        "items": items[:max_items],
        "principle": "Show the smallest set of decisions a human should inspect; keep everything else agent-handled.",
    }


def _review_summary_cards(brief: dict[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    budget = max(1, min(int(limit or 5), 20))
    learning_rules = ((brief.get("learning") or {}).get("top_rules") or [])
    review = brief.get("human_review_5_percent") or {}
    for item in review.get("items") or []:
        cards.append(
            {
                "kind": item.get("kind", "review"),
                "id": item.get("id", ""),
                "title": item.get("title") or item.get("id") or item.get("kind", "Review item"),
                "priority": int(item.get("priority") or 80),
                "count": int(item.get("count") or 1),
                "reason": item.get("reason", ""),
                "recommended_action": item.get("recommended_action", "review"),
                "safe_action": item.get("safe_action", "Inspect compact report before changing memory or policy."),
                "requires_human_decision": True,
                "source": "human_review_5_percent",
            }
        )

    forgetting = brief.get("forgetting_strategy") or {}
    for item in forgetting.get("recommendations") or []:
        cards.append(
            {
                "kind": "forgetting_strategy",
                "id": item.get("action", "forgetting_strategy"),
                "title": review_card_title(item.get("action", "forgetting strategy")),
                "priority": 78 if item.get("action") == "human_review_required" else 62,
                "count": int(item.get("count") or 1),
                "reason": item.get("reason", ""),
                "recommended_action": item.get("action", "review"),
                "safe_action": "Prefer refresh or summarize-then-cold-store before removing daily recall.",
                "requires_human_decision": item.get("action") == "human_review_required",
                "source": "forgetting_strategy",
            }
        )

    weights = brief.get("memory_weights") or {}
    for item in weights.get("top_used") or []:
        recommendation = str(item.get("recommendation") or "")
        score = float(item.get("importance_score") or item.get("weight_score") or 0.0)
        if recommendation in {"observe", "keep_available"} and score < 20:
            continue
        cards.append(
            {
                "kind": "memory_importance",
                "id": item.get("knowledge_id", ""),
                "title": item.get("title", ""),
                "priority": min(92, 50 + int(score)),
                "count": 1,
                "reason": _importance_reason(item),
                "recommended_action": recommendation or "review_memory_importance",
                "safe_action": "Use bounded read and citations before refreshing, summarizing, or changing TTL.",
                "requires_human_decision": recommendation in {
                    "refresh_or_cold_store_before_forgetting",
                    "review_ttl_before_expiry",
                    "protect_or_summarize_before_forgetting",
                },
                "importance_score": score,
                "importance_components": item.get("importance_components", {}),
                "importance_signals": item.get("signals", []),
                "source": "memory_weights",
            }
        )

    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for card in cards:
        apply_review_card_learning(card, learning_rules)
        key = (str(card.get("kind") or ""), str(card.get("id") or card.get("title") or ""))
        existing = unique.get(key)
        if existing is None or int(card.get("priority") or 0) > int(existing.get("priority") or 0):
            unique[key] = card
    ordered = sorted(
        unique.values(),
        key=lambda card: (
            -int(card.get("priority") or 0),
            -float(card.get("importance_score") or 0.0),
            str(card.get("title") or ""),
        ),
    )
    return ordered[:budget]


def _importance_reason(item: dict[str, Any]) -> str:
    components = item.get("importance_components") or {}
    signals = item.get("signals") or []
    bits = []
    if "cited" in signals:
        bits.append("it has citation usage")
    if "expired_but_used" in signals:
        bits.append("it is expired but still used")
    if components.get("recency", 0) >= 10:
        bits.append("it was accessed recently")
    if components.get("protection", 0) > 0:
        bits.append("governance protection is involved")
    if not bits:
        bits.append("its importance score is elevated")
    return "; ".join(bits) + "."



def automation_doctor(project_dir: str | Path, *, mode: str | None = None) -> dict[str, Any]:
    project = Path(project_dir)
    policy = load_policy(project, mode=mode)
    checks = []

    checks.append(_check("project_dir_exists", project.exists(), str(project)))
    checks.append(_check("project_dir_not_tmp", not _is_tmp_path(project), "stable path recommended"))
    checks.append(_check("vault_db_exists", (project / "vault.db").exists(), "run vault init/compile first"))
    checks.append(_check("raw_dir_exists", (project / "raw").is_dir(), "raw/ stores Markdown source notes"))
    checks.append(_check("policy_file_exists", (project / POLICY_FILE).exists(), "optional: vault automation plan --write-policy"))
    checks.append(_check("python_version_supported", sys.version_info >= (3, 10), sys.version.split()[0]))
    checks.append(_check("venv_not_tmp", not _is_tmp_path(Path(sys.prefix)), "scheduled jobs should use stable venv"))

    if (project / "vault.db").exists():
        try:
            with VaultDB(project / "vault.db") as db:
                schema = db.schema_status()
                schema_ok = not bool(schema.get("needs_migration")) and not bool(schema.get("tables_missing"))
                checks.append(
                    _check(
                        "schema_ok",
                        schema_ok,
                        f"version={schema.get('current_version')} missing={len(schema.get('tables_missing', []))}",
                    )
                )
                provider = db.get_config("embedding_provider", "auto")
                checks.append(_check("embedding_provider_configured", bool(provider), provider))
        except Exception as exc:
            checks.append(_check("db_open", False, str(exc)))

    supabase_selected = any(
        os.environ.get(name)
        for name in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY")
    )
    checks.append(_check("supabase_env_optional", True, "configured" if supabase_selected else "not configured"))

    ok = all(item["ok"] for item in checks if item["name"] not in {"policy_file_exists"})
    return {
        "action": "doctor",
        "generated_at": _now(),
        "project_dir": str(project),
        "mode": _normalize_mode(str(policy.get("mode") or DEFAULT_MODE)),
        "ok": ok,
        "checks": checks,
    }


def _planned_actions(
    project: Path,
    policy: dict[str, Any],
    usage: dict[str, Any],
    candidate_count: int,
) -> list[dict[str, Any]]:
    expired = int(usage.get("expired_active_count", 0) or 0)
    mode = _normalize_mode(str(policy.get("mode") or DEFAULT_MODE))
    return [
        {
            "id": "usage_stats",
            "risk": "low",
            "autonomy": "automatic",
            "command": "vault usage stats --json",
            "reason": "Collect coarse retrieval and lifecycle counters.",
        },
        {
            "id": "ttl_archive_preview",
            "risk": "low",
            "autonomy": "automatic-preview",
            "command": "vault usage archive-expired --json",
            "reason": f"{expired} active memories are past expires_at.",
        },
        {
            "id": "ttl_archive_apply",
            "risk": "medium",
            "autonomy": "policy-gated",
            "enabled": bool(policy.get("auto_archive_expired", False)),
            "command": "vault usage archive-expired --apply --json",
            "reason": "Archival is reversible and never hard-deletes rows; automation protects expired memories that still show usage.",
        },
        {
            "id": "cold_store_used_expired",
            "risk": "medium",
            "autonomy": "policy-gated",
            "enabled": bool(policy.get("cold_store_used_expired", False)),
            "command": "vault usage cold-store-expired --apply --json",
            "reason": "Summarize expired-but-used memories, archive them out of normal recall, and retain original content for audit/restore.",
        },
        {
            "id": "dream_report",
            "risk": "low",
            "autonomy": "automatic-report",
            "command": "vault dream --mode report --write-report --pretty",
            "reason": "Find stale, duplicate, weak, and orphaned knowledge without mutation.",
        },
        {
            "id": "dream_candidate_suggestions",
            "risk": "low",
            "autonomy": "policy-gated-candidate-write",
            "enabled": bool(policy.get("dream_write_candidates", False)),
            "command": "vault dream --mode report --write-candidates --write-report --pretty",
            "reason": "Pre-fill the review queue with Dream suggestions. This creates candidates only and never promotes active knowledge.",
        },
        {
            "id": "forgetting_candidate_suggestions",
            "risk": "low",
            "autonomy": "policy-gated-candidate-write",
            "enabled": bool(policy.get("forgetting_write_candidates", False)),
            "command": "vault automation run --apply --pretty",
            "reason": "Pre-fill review candidates for expired memories that policy skipped because they are still used or protected.",
        },
        {
            "id": "candidate_review_digest",
            "risk": "low",
            "autonomy": "digest-only",
            "command": "vault candidates --status candidate --json",
            "reason": f"{candidate_count} candidate memories are waiting for policy or review.",
        },
        {
            "id": "semantic_incremental",
            "risk": "medium",
            "autonomy": "operator-triggered",
            "command": "vault semantic rebuild --changed-only --persist-cache --pretty",
            "reason": "Useful after semantic provider setup; not run automatically by phase 1.",
        },
        {
            "id": "backup_verify",
            "risk": "low",
            "autonomy": "recommended",
            "command": "vault db backup --verify",
            "reason": f"{mode} mode should keep a recent verified backup before stronger automation.",
        },
    ]


def _compact_memory_item(row: dict[str, Any]) -> dict[str, Any]:
    importance = (
        {}
        if "importance_score" in row
        else compute_memory_importance(row) if ("access_count" in row or "citation_count" in row) else {}
    )
    item = {
        "id": row.get("id"),
        "title": row.get("title", ""),
        "layer": row.get("layer", ""),
        "category": row.get("category", ""),
        "scope": row.get("scope", ""),
        "sensitivity": row.get("sensitivity", ""),
        "status": row.get("status", "active"),
        "memory_type": row.get("memory_type", ""),
        "expires_at": row.get("expires_at", ""),
        "access_count": int(row.get("access_count") or 0),
        "citation_count": int(row.get("citation_count") or 0),
    }
    if "importance_score" in row or importance:
        item["importance_score"] = float(row.get("importance_score") or importance.get("importance_score") or 0.0)
    if "importance_components" in row or importance:
        item["importance_components"] = row.get("importance_components") or importance.get("importance_components") or {}
    if "importance_signals" in row or importance:
        item["importance_signals"] = row.get("importance_signals") or importance.get("signals") or []
    elif "signals" in row:
        item["importance_signals"] = row.get("signals") or []
    if "importance_recommendation" in row or importance:
        item["importance_recommendation"] = row.get("importance_recommendation") or importance.get("recommendation", "")
    elif "recommendation" in row:
        item["importance_recommendation"] = row.get("recommendation", "")
    return item


def _usage_review(
    policy: dict[str, Any],
    usage: dict[str, Any],
    archive_preview: dict[str, Any],
) -> dict[str, Any]:
    """Summarize usage-aware maintenance suggestions for agents/operators."""
    archive_items = [_compact_memory_item(row) for row in archive_preview.get("items", [])]
    skipped_used = [_compact_memory_item(row) for row in archive_preview.get("skipped_used", [])]
    skipped_protected = [_compact_memory_item(row) for row in archive_preview.get("skipped_protected", [])]
    top_used = [_compact_memory_item(row) for row in usage.get("top_used", [])[:5]]
    skipped_used.sort(
        key=lambda item: (
            float(item.get("importance_score") or 0.0),
            int(item.get("citation_count") or 0),
            int(item.get("access_count") or 0),
            int(item.get("id") or 0),
        ),
        reverse=True,
    )

    suggestions = []
    if archive_items:
        suggestions.append(
            {
                "kind": "archive_expired_unused",
                "count": len(archive_items),
                "autonomy": "policy-gated",
                "reason": "Expired memories with no protected usage signal can be archived when policy and --apply allow it.",
            }
        )
    if skipped_used:
        suggestions.append(
            {
                "kind": "review_expired_but_used",
                "count": len(skipped_used),
                "autonomy": "human-review",
                "top_importance_score": float(skipped_used[0].get("importance_score") or 0.0),
                "reason": "These memories are expired but still retrieved or cited; review TTL before archiving.",
            }
        )
    if skipped_protected:
        suggestions.append(
            {
                "kind": "protected_expired_not_touched",
                "count": len(skipped_protected),
                "autonomy": "policy-blocked",
                "reason": "Private or high-sensitivity memories require an explicit human decision before lifecycle changes.",
            }
        )
    if top_used:
        suggestions.append(
            {
                "kind": "protect_top_used",
                "count": len(top_used),
                "autonomy": "ranking-signal",
                "top_importance_score": float(top_used[0].get("importance_score") or 0.0) if top_used else 0.0,
                "reason": "Frequently retrieved memories should stay source-checked and may deserve stronger summaries or citations.",
            }
        )

    return {
        "action": "usage-review",
        "protect_used_expired": bool(policy.get("protect_used_expired", True)),
        "expired_archiveable_count": len(archive_items),
        "expired_used_review_count": len(skipped_used),
        "expired_protected_count": len(skipped_protected),
        "top_used_count": len(top_used),
        "archiveable_expired": archive_items,
        "expired_but_used": skipped_used,
        "expired_protected": skipped_protected,
        "top_used": top_used,
        "suggestions": suggestions,
        "importance_model": IMPORTANCE_MODEL_ID,
        "principle": "importance helps agents prioritize maintenance; it does not override access policy or source quality",
    }


def _forgetting_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "candidate_suggestions": len(results),
        "candidates_written": len([item for item in results if item.get("status") != "skipped_existing"]),
        "candidates_skipped_existing": len([item for item in results if item.get("status") == "skipped_existing"]),
    }


def _write_forgetting_candidates(db: VaultDB, usage_review: dict[str, Any]) -> list[dict[str, Any]]:
    """Write candidate-only forgetting suggestions for skipped lifecycle items."""
    from .memory import create_candidate

    suggestions: list[dict[str, Any]] = []

    def add(row: dict[str, Any], *, kind: str, reason: str, tags: list[str]) -> None:
        kid = int(row.get("id") or 0)
        if kid <= 0:
            return
        title = str(row.get("title") or f"knowledge:{kid}").strip() or f"knowledge:{kid}"
        suggestions.append(
            {
                "kind": kind,
                "title": f"Review forgetting policy: {title}"[:140],
                "content": (
                    f"Forgetting automation skipped knowledge #{kid} because {reason}. "
                    f"Review whether to extend expires_at, summarize it, lower recall priority, or archive it manually. "
                    f"Current scope={row.get('scope', '')}, sensitivity={row.get('sensitivity', '')}, "
                    f"access_count={row.get('access_count', 0)}, citation_count={row.get('citation_count', 0)}."
                ),
                "layer": "L3",
                "category": "forgetting-review",
                "tags": ["forgetting", "review", *tags],
                "trust": 0.45,
                "source": "automation",
                "source_ref": f"forgetting:{kind}:knowledge:{kid}",
                "reason": reason,
                "scope": "project",
                "sensitivity": "low",
                "owner_agent": "vault-forgetting",
                "allowed_agents": "",
                "memory_type": "forgetting_suggestion",
                "expires_at": "",
            }
        )

    for row in usage_review.get("expired_but_used", []) or []:
        add(
            row,
            kind="expired_but_used",
            reason="it is expired but still has retrieval or citation usage",
            tags=["expired", "used"],
        )
    for row in usage_review.get("expired_protected", []) or []:
        add(
            row,
            kind="expired_protected",
            reason="its scope or sensitivity is protected by automation_policy.yaml",
            tags=["expired", "protected"],
        )

    results: list[dict[str, Any]] = []
    for suggestion in suggestions:
        existing = db.conn.execute(
            """SELECT id, status FROM memory_candidates
               WHERE source = 'automation'
                 AND source_ref = ?
                 AND memory_type = 'forgetting_suggestion'
                 AND status IN ('candidate', 'approved')
               ORDER BY created_at DESC
               LIMIT 1""",
            (suggestion["source_ref"],),
        ).fetchone()
        if existing:
            results.append({
                "title": suggestion["title"],
                "kind": suggestion["kind"],
                "status": "skipped_existing",
                "candidate_id": existing["id"],
                "existing_status": existing["status"],
            })
            continue
        meta = dict(suggestion)
        kind = meta.pop("kind")
        result = create_candidate(db, **meta)
        results.append({
            "title": suggestion["title"],
            "kind": kind,
            **result,
        })
    return results


def _auto_promote_low_risk_candidates(
    db: VaultDB,
    *,
    project: Path,
    policy: dict[str, Any],
    apply: bool,
) -> dict[str, Any]:
    """Preview or apply policy-gated promotion for the lowest-risk candidates."""
    enabled = bool(policy.get("auto_promote_low_risk_candidates", False))
    max_per_run = max(0, min(_policy_int(policy, "auto_promote_max_per_run", 3), 20))
    payload = {
        "action": "auto_promote_low_risk_candidates",
        "enabled": enabled,
        "apply": bool(apply),
        "status": "disabled" if not enabled else "dry_run",
        "would_promote_count": 0,
        "promoted_count": 0,
        "skipped_count": 0,
        "items": [],
        "safety": {
            "policy_gated": True,
            "requires_apply": True,
            "privacy_gate_required": True,
            "duplicate_gate_required": True,
            "quality_gate_required": True,
            "metadata_gate_required": True,
            "hard_delete": False,
        },
        "next_action": "Review auto-promote policy before enabling candidate promotion.",
    }
    if not enabled or max_per_run <= 0:
        return payload

    rows = db.list_memory_candidates(status="candidate", limit=1000)
    eligible: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in rows:
        decision = _auto_promote_candidate_decision(row, policy)
        item = {
            "candidate_id": row.get("id", ""),
            "title": row.get("title", ""),
            "source": row.get("source", ""),
            "source_ref": row.get("source_ref", ""),
            "memory_type": row.get("memory_type", ""),
            "scope": row.get("scope", ""),
            "sensitivity": row.get("sensitivity", ""),
            "trust": float(row.get("trust") or 0.0),
            **decision,
        }
        if decision["eligible"] and len(eligible) < max_per_run:
            eligible.append(item)
        else:
            if decision["eligible"]:
                item["eligible"] = False
                item["reason"] = "auto_promote_max_per_run reached"
            skipped.append(item)

    payload["would_promote_count"] = len(eligible)
    payload["skipped_count"] = len(skipped)
    payload["status"] = "preview" if not apply else "completed"
    payload["items"] = eligible + skipped[: max(0, 20 - len(eligible))]
    payload["next_action"] = (
        "Re-run with --apply to promote eligible low-risk candidates."
        if not apply
        else "Review promoted knowledge ids and automation feedback before widening policy."
    )
    if not apply:
        return payload

    from .memory import promote_candidate

    promoted_items: list[dict[str, Any]] = []
    for item in eligible:
        result = promote_candidate(
            db,
            str(item.get("candidate_id", "")),
            confirm=True,
            project_dir=project,
            compile=True,
            build_map=True,
        )
        promoted_items.append(
            {
                **item,
                "promotion_status": result.get("status", ""),
                "knowledge_id": result.get("knowledge_id"),
                "raw_path": result.get("raw_path", ""),
                "gates": result.get("gates", {}),
            }
        )
    payload["promoted_count"] = len([item for item in promoted_items if item.get("promotion_status") == "promoted"])
    payload["items"] = promoted_items + skipped[: max(0, 20 - len(promoted_items))]
    return payload


def _auto_promote_candidate_decision(row: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    gate_payload = _candidate_gate_payload(row)
    metadata_status = str((gate_payload.get("metadata") or {}).get("status") or "")
    required_statuses = {
        "privacy": str(row.get("privacy_status") or ""),
        "duplicate": str(row.get("duplicate_status") or ""),
        "quality": str(row.get("quality_status") or ""),
        "metadata": metadata_status,
    }
    for name, status in required_statuses.items():
        if status != "pass":
            reasons.append(f"{name}_gate_not_pass:{status or 'unknown'}")

    source = str(row.get("source") or "").strip().lower()
    memory_type = str(row.get("memory_type") or "").strip().lower()
    scope = str(row.get("scope") or "").strip().lower()
    sensitivity = str(row.get("sensitivity") or "").strip().lower()
    source_ref = str(row.get("source_ref") or "").strip()
    trust = float(row.get("trust") or 0.0)
    if source not in set(_policy_list(policy, "auto_promote_allowed_sources")):
        reasons.append(f"source_not_allowed:{source or 'empty'}")
    if memory_type not in set(_policy_list(policy, "auto_promote_allowed_memory_types")):
        reasons.append(f"memory_type_not_allowed:{memory_type or 'empty'}")
    if scope not in set(_policy_list(policy, "auto_promote_allowed_scopes")):
        reasons.append(f"scope_not_allowed:{scope or 'empty'}")
    if sensitivity not in set(_policy_list(policy, "auto_promote_allowed_sensitivities")):
        reasons.append(f"sensitivity_not_allowed:{sensitivity or 'empty'}")
    if trust < _policy_float(policy, "auto_promote_min_trust", 0.65):
        reasons.append("trust_below_threshold")
    if bool(policy.get("auto_promote_requires_source_ref", True)) and not source_ref:
        reasons.append("missing_source_ref")
    return {
        "eligible": not reasons,
        "reason": "eligible low-risk candidate" if not reasons else "; ".join(reasons),
        "gate_statuses": required_statuses,
    }


def _candidate_gate_payload(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("gate_payload_json") or "{}"
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _review_summary(
    policy: dict[str, Any],
    usage: dict[str, Any],
    candidate_count: int,
    dream: dict[str, Any],
    usage_review: dict[str, Any] | None = None,
    forgetting: dict[str, Any] | None = None,
    cold_store: dict[str, Any] | None = None,
    auto_promote: dict[str, Any] | None = None,
) -> dict[str, Any]:
    thresholds = policy.get("review_thresholds") or {}
    dream_summary = dream.get("summary", {}) if isinstance(dream, dict) else {}
    items = []
    expired = int(usage.get("expired_active_count", 0) or 0)
    if expired >= int(thresholds.get("expired_active", 1)):
        items.append({"kind": "expired_active", "count": expired})
    used_expired = int((usage_review or {}).get("expired_used_review_count", 0) or 0)
    if used_expired >= int(thresholds.get("used_expired", 1)):
        items.append({"kind": "expired_but_used", "count": used_expired})
    protected_expired = int((usage_review or {}).get("expired_protected_count", 0) or 0)
    if protected_expired:
        items.append({"kind": "protected_expired", "count": protected_expired})
    if candidate_count >= int(thresholds.get("pending_candidates", 1)):
        items.append({"kind": "pending_candidates", "count": candidate_count})
    duplicates = int(dream_summary.get("duplicates", 0) or 0)
    if duplicates >= int(thresholds.get("duplicate_groups", 1)):
        items.append({"kind": "duplicate_groups", "count": duplicates})
    weak_metadata = int(dream_summary.get("metadata", 0) or 0)
    if weak_metadata >= int(thresholds.get("weak_metadata", 1)):
        items.append({"kind": "weak_metadata", "count": weak_metadata})
    candidate_suggestions = int(dream_summary.get("candidate_suggestions", 0) or 0)
    if candidate_suggestions:
        items.append({"kind": "dream_candidate_suggestions", "count": candidate_suggestions})
    forgetting_suggestions = int((forgetting or {}).get("candidate_suggestions", 0) or 0)
    if forgetting_suggestions:
        items.append({"kind": "forgetting_candidate_suggestions", "count": forgetting_suggestions})
    cold_store_preview = int((cold_store or {}).get("eligible_count") or 0)
    cold_store_applied = int((cold_store or {}).get("applied_count") or 0)
    if cold_store_applied:
        items.append({"kind": "cold_stored_expired", "count": cold_store_applied})
    elif cold_store_preview:
        items.append({"kind": "cold_store_expired_preview", "count": cold_store_preview})
    auto_promote_preview = int((auto_promote or {}).get("would_promote_count") or 0)
    auto_promoted = int((auto_promote or {}).get("promoted_count") or 0)
    if auto_promote_preview:
        items.append({"kind": "auto_promote_low_risk_preview", "count": auto_promote_preview})
    if auto_promoted:
        items.append({"kind": "auto_promoted_low_risk", "count": auto_promoted})
    return {
        "required": bool(items),
        "items": items,
        "principle": "humans approve policy and high-impact changes; agents handle routine reports and reversible cleanup",
    }


def _archive_action_ledger(archive_result: dict[str, Any], *, applied: bool) -> list[dict[str, Any]]:
    ledger: list[dict[str, Any]] = []
    for row in archive_result.get("items", []) or []:
        item = _compact_memory_item(row)
        ledger.append(
            {
                "operation": "archive_expired",
                "knowledge_id": item["id"],
                "title": item["title"],
                "status": "applied" if applied else "preview",
                "before": {"status": item.get("status") or "active"},
                "after": {"status": "archived"} if applied else {"status": item.get("status") or "active"},
                "reason": "expires_at is in the past and policy allows reversible archival.",
                "risk": "medium",
                "scope": item.get("scope", ""),
                "sensitivity": item.get("sensitivity", ""),
                "importance_score": item.get("importance_score", 0.0),
                "importance_recommendation": item.get("importance_recommendation", ""),
            }
        )
    for row in archive_result.get("skipped_used", []) or []:
        item = _compact_memory_item(row)
        ledger.append(
            {
                "operation": "archive_expired",
                "knowledge_id": item["id"],
                "title": item["title"],
                "status": "skipped_usage",
                "before": {"status": item.get("status") or "active"},
                "after": {"status": item.get("status") or "active"},
                "reason": "memory is expired but still has access or citation usage.",
                "risk": "human-review",
                "scope": item.get("scope", ""),
                "sensitivity": item.get("sensitivity", ""),
                "importance_score": item.get("importance_score", 0.0),
                "importance_recommendation": item.get("importance_recommendation", ""),
            }
        )
    for row in archive_result.get("skipped_protected", []) or []:
        item = _compact_memory_item(row)
        ledger.append(
            {
                "operation": "archive_expired",
                "knowledge_id": item["id"],
                "title": item["title"],
                "status": "skipped_policy",
                "before": {"status": item.get("status") or "active"},
                "after": {"status": item.get("status") or "active"},
                "reason": "memory scope or sensitivity is protected by automation_policy.yaml.",
                "risk": "policy-blocked",
                "scope": item.get("scope", ""),
                "sensitivity": item.get("sensitivity", ""),
                "importance_score": item.get("importance_score", 0.0),
                "importance_recommendation": item.get("importance_recommendation", ""),
            }
        )
    return ledger


def _cold_store_action_ledger(cold_store_result: dict[str, Any], *, applied: bool) -> list[dict[str, Any]]:
    ledger: list[dict[str, Any]] = []
    for row in cold_store_result.get("items", []) or []:
        item = _compact_memory_item(row)
        ledger.append(
            {
                "operation": "cold_store_expired",
                "knowledge_id": item["id"],
                "title": item["title"],
                "status": "applied" if applied else "preview",
                "before": {"status": item.get("status") or "active", "layer": item.get("layer", "")},
                "after": (
                    {"status": "archived", "layer": row.get("target_layer", "L3"), "summary": "written"}
                    if applied
                    else {"status": item.get("status") or "active", "layer": item.get("layer", "")}
                ),
                "reason": "memory is expired but still used; summarize before moving it out of normal recall.",
                "risk": "medium",
                "scope": item.get("scope", ""),
                "sensitivity": item.get("sensitivity", ""),
                "importance_score": item.get("importance_score", 0.0),
                "importance_recommendation": item.get("importance_recommendation", ""),
            }
        )
    for row in cold_store_result.get("skipped_low_usage", []) or []:
        item = _compact_memory_item(row)
        ledger.append(
            {
                "operation": "cold_store_expired",
                "knowledge_id": item["id"],
                "title": item["title"],
                "status": "skipped_usage",
                "before": {"status": item.get("status") or "active"},
                "after": {"status": item.get("status") or "active"},
                "reason": "memory is expired but does not meet the cold-store usage threshold.",
                "risk": "low",
                "scope": item.get("scope", ""),
                "sensitivity": item.get("sensitivity", ""),
                "importance_score": item.get("importance_score", 0.0),
                "importance_recommendation": item.get("importance_recommendation", ""),
            }
        )
    for row in cold_store_result.get("skipped_protected", []) or []:
        item = _compact_memory_item(row)
        ledger.append(
            {
                "operation": "cold_store_expired",
                "knowledge_id": item["id"],
                "title": item["title"],
                "status": "skipped_policy",
                "before": {"status": item.get("status") or "active"},
                "after": {"status": item.get("status") or "active"},
                "reason": "memory layer, scope, or sensitivity is protected from cold-store automation.",
                "risk": "policy-blocked",
                "scope": item.get("scope", ""),
                "sensitivity": item.get("sensitivity", ""),
                "importance_score": item.get("importance_score", 0.0),
                "importance_recommendation": item.get("importance_recommendation", ""),
            }
        )
    return ledger


def _dry_run_diff(
    ledger: list[dict[str, Any]],
    *,
    apply_requested: bool,
    archive_allowed: bool,
) -> dict[str, Any]:
    would_archive = [
        item for item in ledger
        if item.get("operation") == "archive_expired" and item.get("status") in {"preview", "applied"}
    ]
    skipped_usage = [
        item for item in ledger
        if item.get("operation") == "archive_expired" and item.get("status") == "skipped_usage"
    ]
    skipped_policy = [
        item for item in ledger
        if item.get("operation") == "archive_expired" and item.get("status") == "skipped_policy"
    ]
    cold_store_skipped_usage = [
        item for item in ledger
        if item.get("operation") == "cold_store_expired" and item.get("status") == "skipped_usage"
    ]
    cold_store_skipped_policy = [
        item for item in ledger
        if item.get("operation") == "cold_store_expired" and item.get("status") == "skipped_policy"
    ]
    cold_store_items = [
        item for item in ledger
        if item.get("operation") == "cold_store_expired" and item.get("status") in {"preview", "applied"}
    ]
    return {
        "apply_requested": bool(apply_requested),
        "policy_allows_archive": bool(archive_allowed),
        "would_archive_count": len(would_archive),
        "applied_count": len([item for item in would_archive if item.get("status") == "applied"]),
        "skipped_usage_count": len(skipped_usage),
        "skipped_policy_count": len(skipped_policy),
        "cold_store_skipped_usage_count": len(cold_store_skipped_usage),
        "cold_store_skipped_policy_count": len(cold_store_skipped_policy),
        "highest_cold_store_importance": max(
            [float(item.get("importance_score") or 0.0) for item in cold_store_items],
            default=0.0,
        ),
        "fields_changed": ["status", "archived_at", "updated_at"] if would_archive else [],
        "hard_delete": False,
        "promote_candidates": False,
        "permission_changes": False,
    }


def _check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _is_tmp_path(path: Path) -> bool:
    try:
        resolved = path.expanduser().resolve()
    except Exception:
        resolved = path.expanduser()
    return str(resolved).startswith(("/tmp/", "/private/tmp/", "/var/folders/"))


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
