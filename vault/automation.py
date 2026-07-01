"""Policy-based memory automation workflows.

Automation is intentionally reversible by default. Agents should do the daily
maintenance labor, while humans keep policy ownership and rollback paths.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .db import VaultDB
from .dream import run_dream
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
    find_review_summary_card,
    int_or_none,
    load_review_summary,
    review_feedback_score,
    review_feedback_source_ref,
)
from .automation_briefing import (
    _auto_promote_activity_event,
    _automation_update_distribution_health,
    _brief_agent_health,
    _brief_forgetting_strategy,
    _brief_human_review,
    _brief_learning,
    _brief_memory_weights,
    _brief_summary,
    _empty_forgetting_strategy,
    _fleet_health_cards,
    _fleet_health_next_action,
    _fleet_health_status,
    _ledger_activity_event,
    _review_summary_cards,
    _sync_review_items,
    _sync_summary,
)
from .automation_lifecycle import (
    automation_doctor,
    _archive_action_ledger,
    _auto_promote_low_risk_candidates,
    _cold_store_action_ledger,
    _dry_run_diff,
    _forgetting_summary,
    _now,
    _planned_actions,
    _review_summary,
    _usage_review,
    _write_forgetting_candidates,
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
    sync_health: dict[str, Any] = {}
    db_path = project / "vault.db"
    if db_path.exists():
        from .multi_host import sync_status

        with VaultDB(db_path) as db:
            usage = db.usage_stats(limit=max(1, min(int(limit or 5), 50)))
            archive_preview = db.archive_expired_knowledge(
                limit=max(1, min(int(limit or 5) * 5, 100)),
                dry_run=True,
                skip_used=bool(policy.get("protect_used_expired", True)),
                protected_scopes=_policy_list(policy, "protected_scopes"),
                protected_sensitivities=_policy_list(policy, "protected_sensitivities"),
            )
            sync_health = sync_status(db, limit=review_limit)
        forgetting_strategy = _brief_forgetting_strategy(usage, archive_preview)
    summary = _brief_summary(activity, inbox, evaluation, usage, forgetting_strategy)
    summary.update(_sync_summary(sync_health))
    human_review = _brief_human_review(inbox, activity, limit=review_limit)
    sync_items = _sync_review_items(sync_health, limit=review_limit)
    if sync_items:
        merged_items = [*sync_items, *(human_review.get("items") or [])]
        human_review = {
            **human_review,
            "items": merged_items[: max(1, min(int(review_limit or 5), 20))],
            "principle": (
                "Show remote sync conflicts and the smallest set of memory decisions a human should inspect; "
                "keep everything else agent-handled."
            ),
        }

    payload = {
        "action": "brief",
        "generated_at": generated_at,
        "project_dir": str(project),
        "status": "completed" if db_path.exists() else "blocked",
        "summary": summary,
        "learning": _brief_learning(evaluation, limit=limit),
        "memory_weights": _brief_memory_weights(usage, limit=limit),
        "forgetting_strategy": forgetting_strategy,
        "sync_health": sync_health,
        "agent_health": _brief_agent_health(project),
        "human_review_5_percent": human_review,
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
    precomputed_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the shortest human approval surface for automation.

    This is intentionally derived and read-only. It hides candidate content and
    compresses the existing brief/inbox/report signals into a few approval
    cards that a person can quickly accept, reject, or defer.
    """
    project = Path(project_dir)
    limit_i = max(1, min(int(limit or 5), 20))
    brief = precomputed_brief or automation_brief(
        project,
        limit=limit_i,
        review_limit=limit_i,
        min_events=min_events,
        write_brief=False,
    )
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
    sync_health: dict[str, Any] = {}
    db_path = project / "vault.db"
    if db_path.exists():
        from .multi_host import sync_status

        with VaultDB(db_path) as db:
            sync_health = sync_status(db, limit=limit)
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
        open_sync_conflicts=int((sync_health.get("counts") or {}).get("open_conflicts") or 0),
    )
    sync_counts = sync_health.get("counts") or {}
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
            "sync_status": sync_health.get("status", "idle"),
            "open_sync_conflicts": int(sync_counts.get("open_conflicts") or 0),
            "sync_revisions": int(sync_counts.get("revisions") or 0),
            "sync_audit_events": int(sync_counts.get("audit_events") or 0),
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
        "sync_health": sync_health,
        "cards": _fleet_health_cards(
            learning=learning,
            agent_health=agent_health,
            update_health=update_health,
            sync_health=sync_health,
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
