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

import yaml

from .db import VaultDB
from .dream import run_dream
from .privacy import redact_secrets

AUTOMATION_MODES = {"conservative", "balanced", "autonomous"}
DEFAULT_MODE = "balanced"
POLICY_FILE = "automation_policy.yaml"


DEFAULT_POLICIES: dict[str, dict[str, Any]] = {
    "conservative": {
        "mode": "conservative",
        "auto_archive_expired": False,
        "cold_store_used_expired": False,
        "protect_used_expired": True,
        "protected_scopes": ["private"],
        "protected_sensitivities": ["high", "restricted"],
        "auto_apply_safe_metadata": False,
        "dream_write_candidates": False,
        "forgetting_write_candidates": False,
        "session_capture_write_candidates": False,
        "auto_promote_low_risk_candidates": False,
        "auto_promote_allowed_sources": ["session_capture"],
        "auto_promote_allowed_memory_types": ["session_lesson"],
        "auto_promote_allowed_scopes": ["project", "shared", "public"],
        "auto_promote_allowed_sensitivities": ["low"],
        "auto_promote_min_trust": 0.65,
        "auto_promote_max_per_run": 3,
        "auto_promote_requires_source_ref": True,
        "write_reports": True,
        "dream_checks": ["freshness", "dedup", "convergence", "metadata", "orphans"],
        "review_thresholds": {
            "expired_active": 1,
            "used_expired": 1,
            "pending_candidates": 1,
            "duplicate_groups": 1,
            "weak_metadata": 1,
        },
    },
    "balanced": {
        "mode": "balanced",
        "auto_archive_expired": True,
        "cold_store_used_expired": True,
        "protect_used_expired": True,
        "protected_scopes": ["private"],
        "protected_sensitivities": ["high", "restricted"],
        "auto_apply_safe_metadata": False,
        "dream_write_candidates": True,
        "forgetting_write_candidates": True,
        "session_capture_write_candidates": False,
        "auto_promote_low_risk_candidates": False,
        "auto_promote_allowed_sources": ["session_capture"],
        "auto_promote_allowed_memory_types": ["session_lesson"],
        "auto_promote_allowed_scopes": ["project", "shared", "public"],
        "auto_promote_allowed_sensitivities": ["low"],
        "auto_promote_min_trust": 0.65,
        "auto_promote_max_per_run": 3,
        "auto_promote_requires_source_ref": True,
        "write_reports": True,
        "dream_checks": ["freshness", "dedup", "convergence", "metadata", "orphans"],
        "review_thresholds": {
            "expired_active": 5,
            "used_expired": 1,
            "pending_candidates": 10,
            "duplicate_groups": 1,
            "weak_metadata": 10,
        },
    },
    "autonomous": {
        "mode": "autonomous",
        "auto_archive_expired": True,
        "cold_store_used_expired": True,
        "protect_used_expired": True,
        "protected_scopes": ["private"],
        "protected_sensitivities": ["high", "restricted"],
        "auto_apply_safe_metadata": False,
        "dream_write_candidates": True,
        "forgetting_write_candidates": True,
        "session_capture_write_candidates": False,
        "auto_promote_low_risk_candidates": False,
        "auto_promote_allowed_sources": ["session_capture"],
        "auto_promote_allowed_memory_types": ["session_lesson"],
        "auto_promote_allowed_scopes": ["project", "shared", "public"],
        "auto_promote_allowed_sensitivities": ["low"],
        "auto_promote_min_trust": 0.65,
        "auto_promote_max_per_run": 3,
        "auto_promote_requires_source_ref": True,
        "write_reports": True,
        "dream_checks": ["freshness", "dedup", "convergence", "metadata", "orphans"],
        "review_thresholds": {
            "expired_active": 20,
            "used_expired": 5,
            "pending_candidates": 50,
            "duplicate_groups": 5,
            "weak_metadata": 25,
        },
    },
}


def default_policy(mode: str = DEFAULT_MODE) -> dict[str, Any]:
    mode = _normalize_mode(mode)
    return json.loads(json.dumps(DEFAULT_POLICIES[mode]))


def load_policy(project_dir: str | Path, *, mode: str | None = None) -> dict[str, Any]:
    project = Path(project_dir)
    base = default_policy(mode or DEFAULT_MODE)
    path = project / POLICY_FILE
    if not path.exists():
        return base
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{POLICY_FILE} must contain a YAML object")
    loaded_mode = loaded.get("mode") or mode or DEFAULT_MODE
    base = default_policy(str(loaded_mode))
    return _deep_merge(base, loaded)


def write_policy(project_dir: str | Path, *, mode: str = DEFAULT_MODE, overwrite: bool = False) -> str:
    project = Path(project_dir)
    path = project / POLICY_FILE
    if path.exists() and not overwrite:
        return str(path.relative_to(project))
    payload = default_policy(mode)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return str(path.relative_to(project))


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


def automation_handoff(
    project_dir: str | Path,
    *,
    source: str = "auto",
    handoff_path: str | Path = "",
) -> dict[str, Any]:
    """Read the latest compact automation handoff for the next agent.

    This is intentionally read-only. It does not generate, mutate, promote, or
    inspect raw transcript content; it only returns an existing handoff artifact
    under reports/automation.
    """
    project = Path(project_dir)
    report_dir = project / "reports" / "automation"
    selected = _resolve_handoff_read_path(project, report_dir, source=source, handoff_path=handoff_path)
    if selected is None:
        return {
            "action": "handoff",
            "generated_at": _now(),
            "project_dir": str(project),
            "status": "missing",
            "source": source,
            "handoff_path": "",
            "content_type": "",
            "content": "",
            "summary": {},
            "safety": {
                "read_only": True,
                "writes_active_memory": False,
                "transcript_discovery_reads_contents": False,
            },
            "next_action": "Run `vault automation cycle --write-workspace` to create a daily handoff.",
        }
    content = selected.read_text(encoding="utf-8")
    parsed: dict[str, Any] = {}
    if selected.suffix.lower() == ".json":
        try:
            loaded = json.loads(content)
            if isinstance(loaded, dict):
                parsed = loaded
        except Exception:
            parsed = {}
    return {
        "action": "handoff",
        "generated_at": _now(),
        "project_dir": str(project),
        "status": "completed",
        "source": source,
        "handoff_path": _relative_to_project(project, selected),
        "content_type": "markdown" if selected.suffix.lower() == ".md" else "json",
        "content": content,
        "summary": parsed.get("summary", {}) if parsed else {},
        "agent_start_prompt": parsed.get("agent_start_prompt", "") if parsed else "",
        "safety": {
            "read_only": True,
            "writes_active_memory": False,
            "transcript_discovery_reads_contents": False,
            "uses_existing_handoff_only": True,
        },
        "next_action": (
            "Read this handoff first, then use the listed suggested_next_tasks without "
            "auto-promoting candidates or reading transcript contents by default."
        ),
    }


def automation_inbox(
    project_dir: str | Path,
    *,
    limit: int = 5,
    candidate_scan_limit: int = 1000,
    include_content: bool = False,
    include_transcripts: bool = False,
    transcript_limit: int = 5,
    write_handoff: bool = False,
    handoff_path: str | Path = "",
) -> dict[str, Any]:
    """Build a compact review inbox for the memory automation loop.

    The inbox is intentionally read-only. It helps humans and agents review the
    smallest useful set of memory decisions without exposing raw candidate
    content unless explicitly requested.
    """
    project = Path(project_dir)
    generated_at = _now()
    db_path = project / "vault.db"
    if not db_path.exists():
        payload = {
            "action": "inbox",
            "generated_at": generated_at,
            "project_dir": str(project),
            "status": "blocked",
            "reason": "vault.db missing",
            "summary": {
                "pending_candidates": 0,
                "rejected_candidates": 0,
                "privacy_blocked": 0,
                "needs_review": 0,
            "review_budget": max(1, int(limit or 5)),
            "uncaptured_transcripts": 0,
            },
            "review_queue": [],
            "review_digest": _empty_review_digest(max(1, int(limit or 5))),
            "transcript_discovery": {},
            "latest_report": {},
            "inbox_handoff_path": "",
            "next_action": "Run vault init and capture/import memory before checking the automation inbox.",
        }
        if write_handoff:
            payload["inbox_handoff_path"] = _write_inbox_handoff(project, payload, handoff_path=handoff_path)
        return payload

    limit_i = max(1, min(int(limit or 5), 50))
    scan_limit = max(limit_i, min(int(candidate_scan_limit or 1000), 5000))
    with VaultDB(db_path) as db:
        candidates = db.list_memory_candidates(status=None, limit=scan_limit)

    candidate_items = [_candidate_inbox_item(row, include_content=include_content) for row in candidates]
    candidate_items.sort(key=lambda item: (-int(item["priority"]), item["created_at"], item["id"]), reverse=False)
    # The reverse=False ordering above keeps high priority first because the key
    # negates priority, then keeps older unresolved items ahead within a tie.

    latest_path = _resolve_report_path(project, project / "reports" / "automation", latest=True)
    latest_report = {}
    if latest_path is not None:
        latest_report = _report_summary(project, latest_path, _read_report(latest_path))

    transcript_discovery = {}
    if include_transcripts:
        from vault.session_capture import discover_session_transcripts

        transcript_discovery = discover_session_transcripts(
            project,
            limit=max(1, min(int(transcript_limit or 5), 20)),
        )

    summary = _inbox_summary(
        candidate_items,
        latest_report,
        transcript_discovery=transcript_discovery,
        review_budget=limit_i,
    )
    review_digest = _inbox_review_digest(candidate_items, latest_report, limit=limit_i)
    summary["review_digest_items"] = len(review_digest["items"])
    summary["report_review_items"] = int(review_digest.get("report_item_count") or 0)
    summary["candidate_digest_items"] = int(review_digest.get("candidate_item_count") or 0)
    payload = {
        "action": "inbox",
        "generated_at": generated_at,
        "project_dir": str(project),
        "status": "completed",
        "summary": summary,
        "review_queue": candidate_items[:limit_i],
        "review_digest": review_digest,
        "transcript_discovery": transcript_discovery,
        "latest_report": latest_report,
        "inbox_handoff_path": "",
        "safety": {
            "read_only": True,
            "auto_promote": False,
            "hard_delete": False,
            "content_hidden_by_default": not include_content,
            "transcript_discovery_reads_contents": False,
        },
        "next_action": (
            "Review the top queue items. Use `vault promote` for approved candidates "
            "or `vault candidate-review` for rejected/blocked feedback."
        ),
    }
    if write_handoff:
        payload["inbox_handoff_path"] = _write_inbox_handoff(project, payload, handoff_path=handoff_path)
    return payload


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


def _feedback_learning_policy(
    groups: list[dict[str, Any]],
    *,
    generated_at: str,
    event_count: int,
    min_events: int,
    readiness: str,
) -> dict[str, Any]:
    """Convert feedback aggregates into bounded, auditable curation hints."""
    rules = []
    for group in groups:
        total = int(group.get("total") or 0)
        acceptance = float(group.get("acceptance_rate") or 0.0)
        average_score = float(group.get("average_score") or 0.0)
        recommendation = str(group.get("recommendation") or "collect_more_feedback")
        enough_events = total >= min_events

        if not enough_events:
            priority_multiplier = 1.0
            confidence = round(min(0.49, total / max(1, min_events) * 0.49), 3)
            action = "observe"
            reason = "Not enough reviewed outcomes for this source/type/category group."
        elif recommendation == "prefer":
            priority_multiplier = 1.15
            confidence = _learning_confidence(total, min_events, acceptance)
            action = "prefer_candidates"
            reason = "This group has earned a high promotion rate in reviewed outcomes."
        elif recommendation == "downgrade_or_review_policy":
            priority_multiplier = 0.85
            confidence = _learning_confidence(total, min_events, 1.0 - acceptance)
            action = "downgrade_or_require_review"
            reason = "This group has a low promotion rate and should stay under review."
        else:
            priority_multiplier = 1.0
            confidence = _learning_confidence(total, min_events, 0.5)
            action = "keep_observing"
            reason = "This group has mixed outcomes; keep collecting feedback."

        rules.append(
            {
                "selector": {
                    "source": group.get("source") or "",
                    "memory_type": group.get("memory_type") or "",
                    "category": group.get("category") or "",
                },
                "total": total,
                "acceptance_rate": round(acceptance, 4),
                "average_score": round(average_score, 4),
                "recommendation": recommendation,
                "action": action,
                "priority_multiplier": priority_multiplier,
                "confidence": confidence,
                "reason": reason,
            }
        )

    rules.sort(key=lambda item: (item["confidence"], item["total"]), reverse=True)
    return {
        "version": 1,
        "generated_at": generated_at,
        "readiness": readiness,
        "event_count": int(event_count),
        "min_events": int(min_events),
        "rules": rules,
        "bounds": {
            "priority_multiplier_min": 0.85,
            "priority_multiplier_max": 1.15,
            "no_auto_promote": True,
            "no_auto_delete": True,
            "respect_privacy_and_access_policy": True,
        },
        "principle": (
            "Learning policy is a ranking and review hint for future curation; "
            "it is not an authorization policy."
        ),
    }


def _learning_confidence(total: int, min_events: int, signal_strength: float) -> float:
    sample = min(1.0, total / max(1, min_events * 3))
    signal = max(0.0, min(1.0, signal_strength))
    return round(0.35 + sample * 0.45 + signal * 0.2, 3)


def _write_learning_policy(project: Path, learning_policy: dict[str, Any]) -> str:
    report_dir = project / "reports" / "automation"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "learning_policy.json"
    path.write_text(json.dumps(learning_policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path.relative_to(project))


def _write_inbox_handoff(project: Path, payload: dict[str, Any], *, handoff_path: str | Path = "") -> str:
    report_dir = project / "reports" / "automation"
    report_dir.mkdir(parents=True, exist_ok=True)
    if handoff_path:
        raw = Path(handoff_path)
        candidate = raw if raw.is_absolute() else project / raw
        try:
            resolved = candidate.expanduser().resolve()
            allowed = report_dir.expanduser().resolve()
        except Exception as exc:
            raise ValueError(f"unable to resolve automation inbox handoff path: {exc}") from exc
        if allowed != resolved and allowed not in resolved.parents:
            raise ValueError("automation inbox handoff path must stay under reports/automation")
        path = resolved
    else:
        path = report_dir / "inbox-latest.json"
    data = dict(payload)
    data["inbox_handoff_path"] = _relative_to_project(project, path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return _relative_to_project(project, path)


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


def _relative_to_project(project: Path, path: Path) -> str:
    try:
        return str(path.relative_to(project))
    except ValueError:
        return str(path.expanduser().resolve().relative_to(project.expanduser().resolve()))


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
    for row in usage.get("top_used") or []:
        access = int(row.get("access_count") or 0)
        citations = int(row.get("citation_count") or 0)
        score = access + citations * 2
        items.append(
            {
                "knowledge_id": row.get("id"),
                "title": row.get("title", ""),
                "layer": row.get("layer", ""),
                "category": row.get("category", ""),
                "trust": float(row.get("trust") or 0.0),
                "status": row.get("status", ""),
                "access_count": access,
                "citation_count": citations,
                "last_accessed_at": row.get("last_accessed_at", ""),
                "weight_score": score,
                "recommendation": "protect_or_summarize_before_forgetting" if score > 0 else "observe",
            }
        )
    items.sort(key=lambda item: (item["weight_score"], item["trust"]), reverse=True)
    return {
        "knowledge_count": int(usage.get("knowledge_count") or 0),
        "total_accesses": int(usage.get("total_accesses") or 0),
        "total_citations": int(usage.get("total_citations") or 0),
        "top_used": items[: max(1, min(int(limit or 5), 20))],
        "principle": "Usage weight is a small protection and ranking signal, not a source-of-truth override.",
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


def _write_brief(project: Path, payload: dict[str, Any], *, brief_path: str | Path = "") -> str:
    report_dir = project / "reports" / "automation"
    report_dir.mkdir(parents=True, exist_ok=True)
    if brief_path:
        raw = Path(brief_path)
        candidate = raw if raw.is_absolute() else project / raw
        try:
            resolved = candidate.expanduser().resolve()
            allowed = report_dir.expanduser().resolve()
        except Exception as exc:
            raise ValueError(f"unable to resolve automation brief path: {exc}") from exc
        if allowed != resolved and allowed not in resolved.parents:
            raise ValueError("automation brief path must stay under reports/automation")
        path = resolved
    else:
        path = report_dir / "brief-latest.json"
    data = dict(payload)
    data["brief_path"] = _relative_to_project(project, path)
    data["brief_markdown_path"] = str(data.get("brief_markdown_path") or "")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return _relative_to_project(project, path)


def _write_brief_markdown(project: Path, payload: dict[str, Any], *, brief_path: str | Path) -> str:
    json_path = project / brief_path if not Path(brief_path).is_absolute() else Path(brief_path)
    path = json_path.with_suffix(".md")
    summary = payload.get("summary") or {}
    review = payload.get("human_review_5_percent") or {}
    learning = payload.get("learning") or {}
    weights = payload.get("memory_weights") or {}
    forgetting = payload.get("forgetting_strategy") or {}
    agent_health = payload.get("agent_health") or {}
    lines = [
        "# Vault Automation Intelligence Brief",
        "",
        f"- generated_at: `{_md_text(payload.get('generated_at', ''))}`",
        f"- status: `{_md_text(payload.get('status', ''))}`",
        f"- pending candidates: `{int(summary.get('pending_candidates') or 0)}`",
        f"- needs review: `{int(summary.get('needs_review') or 0)}`",
        f"- auto-promoted: `{int(summary.get('auto_promote_promoted') or 0)}`",
        f"- auto-promote skipped: `{int(summary.get('auto_promote_skipped') or 0)}`",
        f"- learning readiness: `{_md_text(summary.get('learning_readiness', ''))}`",
        f"- expired active: `{int(summary.get('expired_active') or 0)}`",
        f"- cold-store preview: `{int(summary.get('cold_store_preview') or 0)}`",
        f"- cold-store applied: `{int(summary.get('cold_store_applied') or 0)}`",
        "",
        "## Human Review 5%",
        "",
    ]
    items = review.get("items") or []
    if items:
        lines += [_md_row(["kind", "id", "title", "action", "reason"]), _md_row(["---", "---", "---", "---", "---"])]
        for item in items:
            lines.append(
                _md_row(
                    [
                        item.get("kind", ""),
                        item.get("id", ""),
                        item.get("title", ""),
                        item.get("recommended_action", ""),
                        item.get("reason", ""),
                    ]
                )
            )
    else:
        lines.append("No urgent human-review items.")
    lines += [
        "",
        "## Learning",
        "",
        f"- readiness: `{_md_text(learning.get('readiness', ''))}`",
        f"- feedback events: `{int(learning.get('event_count') or 0)}`",
        f"- top rules: `{len(learning.get('top_rules') or [])}`",
        "",
        "## Memory Weights",
        "",
    ]
    top_used = weights.get("top_used") or []
    if top_used:
        lines += [_md_row(["id", "title", "weight", "access", "citations"]), _md_row(["---", "---", "---", "---", "---"])]
        for item in top_used[:10]:
            lines.append(
                _md_row(
                    [
                        item.get("knowledge_id", ""),
                        item.get("title", ""),
                        item.get("weight_score", 0),
                        item.get("access_count", 0),
                        item.get("citation_count", 0),
                    ]
                )
            )
    else:
        lines.append("No usage-weight signal yet.")
    lines += [
        "",
        "## Forgetting Strategy",
        "",
        f"- archiveable expired: `{int(forgetting.get('archiveable_count') or 0)}`",
        f"- used expired: `{int(forgetting.get('used_expired_count') or 0)}`",
        f"- protected expired: `{int(forgetting.get('protected_expired_count') or 0)}`",
        "",
        "## Agent Health",
        "",
        f"- registered agents: `{int(agent_health.get('agent_count') or 0)}`",
        "",
        "## Safety",
        "",
        "- read-only brief",
        "- no raw candidate content",
        "- no auto-promote policy widening",
        "- forgetting strategy only; no compression or cold-store mutation",
    ]
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return _relative_to_project(project, path)


def _write_cycle_workspace_markdown(
    project: Path,
    workspace: dict[str, Any],
    *,
    workspace_path: str | Path = "",
) -> str:
    report_dir = project / "reports" / "automation"
    report_dir.mkdir(parents=True, exist_ok=True)
    if workspace_path:
        raw = Path(workspace_path)
        raw = raw.with_suffix(".md")
        candidate = raw if raw.is_absolute() else project / raw
        try:
            resolved = candidate.expanduser().resolve()
            allowed = report_dir.expanduser().resolve()
        except Exception as exc:
            raise ValueError(f"unable to resolve automation cycle workspace Markdown path: {exc}") from exc
        if allowed != resolved and allowed not in resolved.parents:
            raise ValueError("automation cycle workspace Markdown path must stay under reports/automation")
        path = resolved
    else:
        path = report_dir / "cycle-latest.md"
    path.write_text(_render_cycle_workspace_markdown(workspace), encoding="utf-8")
    return _relative_to_project(project, path)


def _md_text(value: Any) -> str:
    text = str(value if value is not None else "").replace("\r", " ").replace("\n", " ").strip()
    return text.replace("|", "\\|")


def _md_row(values: list[Any]) -> str:
    return "| " + " | ".join(_md_text(value) for value in values) + " |"


def _render_cycle_workspace_markdown(workspace: dict[str, Any]) -> str:
    summary = workspace.get("summary") or {}
    candidate_review = workspace.get("candidate_review") or {}
    queue = candidate_review.get("queue") or []
    transcripts = workspace.get("transcripts_to_capture") or {}
    transcript_summary = transcripts.get("summary") or {}
    transcript_items = transcripts.get("items") or []
    transcript_capture = workspace.get("transcript_capture") or {}
    capture_summary = transcript_capture.get("summary") or {}
    capture_items = transcript_capture.get("items") or []
    curation = workspace.get("curation_policy") or {}
    rules = curation.get("rules") or []
    safety = workspace.get("safety") or {}
    priority_brief = workspace.get("priority_brief") or []
    suggested_tasks = workspace.get("suggested_next_tasks") or []
    lines: list[str] = [
        "# Vault Automation Cycle Workspace",
        "",
        f"- generated_at: `{_md_text(workspace.get('generated_at', ''))}`",
        f"- status: `{_md_text(workspace.get('status', ''))}`",
        f"- project_dir: `{_md_text(workspace.get('project_dir', ''))}`",
        f"- json: `{_md_text(workspace.get('workspace_path', 'reports/automation/cycle-latest.json'))}`",
        "",
        "## Summary",
        "",
        f"- candidate queue items: `{int(summary.get('candidate_queue_items') or 0)}`",
        f"- pending candidates: `{int(summary.get('pending_candidates') or 0)}`",
        f"- needs review: `{int(summary.get('needs_review') or 0)}`",
        f"- uncaptured transcripts: `{int(summary.get('uncaptured_transcripts') or 0)}`",
        f"- transcript capture status: `{_md_text(summary.get('transcript_capture_status', ''))}`",
        f"- transcript candidates written: `{int(summary.get('transcript_capture_candidates_written') or 0)}`",
        f"- auto-promote enabled: `{str(bool(summary.get('auto_promote_enabled', False))).lower()}`",
        f"- auto-promote would promote: `{int(summary.get('auto_promote_would_promote_count') or 0)}`",
        f"- auto-promote promoted: `{int(summary.get('auto_promote_promoted_count') or 0)}`",
        f"- learning rules: `{int(summary.get('learning_rules') or 0)}`",
        f"- learning readiness: `{_md_text(summary.get('learning_readiness', ''))}`",
        f"- automation report: `{_md_text(summary.get('automation_report_path', ''))}`",
        f"- learning policy: `{_md_text(summary.get('learning_policy_path', ''))}`",
        "",
        "## Priority Brief",
        "",
    ]
    if priority_brief:
        lines += [
            _md_row(["priority", "title", "count", "safe action"]),
            _md_row(["---", "---", "---", "---"]),
        ]
        for item in priority_brief[:8]:
            if not isinstance(item, dict):
                continue
            lines.append(
                _md_row(
                    [
                        item.get("priority", ""),
                        item.get("title", ""),
                        item.get("count", ""),
                        item.get("safe_action", ""),
                    ]
                )
            )
    else:
        lines.append("No urgent automation handoff items.")

    lines += [
        "",
        "## Candidate Review",
        "",
        f"- content hidden: `{str(bool(candidate_review.get('content_hidden', True))).lower()}`",
    ]
    if queue:
        lines += [
            "",
            _md_row(["id", "title", "source", "type", "priority", "action"]),
            _md_row(["---", "---", "---", "---", "---", "---"]),
        ]
        for item in queue[:10]:
            if not isinstance(item, dict):
                continue
            lines.append(
                _md_row(
                    [
                        item.get("candidate_id", item.get("id", "")),
                        item.get("title", ""),
                        item.get("source", ""),
                        item.get("memory_type", item.get("type", "")),
                        item.get("priority", ""),
                        item.get("recommended_action", item.get("action", "")),
                    ]
                )
            )
    else:
        lines += ["", "No pending candidate review items."]

    lines += [
        "",
        "## Transcripts To Capture",
        "",
        f"- count: `{int(transcript_summary.get('count') or 0)}`",
        f"- include transcripts: `{str(bool(transcript_summary.get('include_transcripts'))).lower()}`",
        f"- read contents: `{str(bool(transcript_summary.get('read_contents'))).lower()}`",
    ]
    if transcript_items:
        lines += [
            "",
            _md_row(["capture_path", "source_system", "format", "size_bytes"]),
            _md_row(["---", "---", "---", "---"]),
        ]
        for item in transcript_items[:10]:
            if not isinstance(item, dict):
                continue
            lines.append(
                _md_row(
                    [
                        item.get("capture_path", item.get("path", "")),
                        item.get("source_system", ""),
                        item.get("format", ""),
                        item.get("size_bytes", ""),
                    ]
                )
            )

    lines += [
        "",
        "## Transcript Capture",
        "",
        f"- status: `{_md_text(transcript_capture.get('status', ''))}`",
        f"- enabled: `{str(bool(transcript_capture.get('enabled'))).lower()}`",
        f"- reads contents: `{str(bool(transcript_capture.get('reads_contents'))).lower()}`",
        f"- content hidden: `{str(bool(transcript_capture.get('content_hidden', True))).lower()}`",
        f"- transcripts captured: `{int(capture_summary.get('transcripts_captured') or 0)}`",
        f"- candidates written: `{int(capture_summary.get('candidates_written') or 0)}`",
        f"- candidates rejected: `{int(capture_summary.get('candidates_rejected') or 0)}`",
    ]
    if capture_items:
        lines += [
            "",
            _md_row(["capture_path", "written", "rejected", "candidate ids"]),
            _md_row(["---", "---", "---", "---"]),
        ]
        for item in capture_items[:10]:
            if not isinstance(item, dict):
                continue
            ids = ", ".join(
                str(candidate.get("candidate_id", ""))
                for candidate in item.get("candidates", [])[:5]
                if isinstance(candidate, dict) and candidate.get("candidate_id")
            )
            lines.append(
                _md_row(
                    [
                        item.get("capture_path", ""),
                        item.get("written", 0),
                        item.get("rejected", 0),
                        ids,
                    ]
                )
            )

    lines += [
        "",
        "## Curation Policy",
        "",
        f"- path: `{_md_text(curation.get('path', ''))}`",
        f"- readiness: `{_md_text(curation.get('readiness', ''))}`",
        f"- feedback events: `{int(curation.get('event_count') or 0)}`",
        f"- rule count: `{len(rules)}`",
    ]
    if rules:
        lines += [
            "",
            _md_row(["source", "type", "action", "priority_multiplier"]),
            _md_row(["---", "---", "---", "---"]),
        ]
        for rule in rules[:10]:
            if not isinstance(rule, dict):
                continue
            lines.append(
                _md_row(
                    [
                        rule.get("source", ""),
                        rule.get("memory_type", ""),
                        rule.get("action", ""),
                        rule.get("priority_multiplier", ""),
                    ]
                )
            )

    lines += [
        "",
        "## Safety",
        "",
        f"- read only: `{str(bool(safety.get('read_only', True))).lower()}`",
        f"- auto promote: `{str(bool(safety.get('auto_promote', False))).lower()}`",
        f"- hard delete: `{str(bool(safety.get('hard_delete', False))).lower()}`",
        f"- candidate content hidden: `{str(bool(safety.get('candidate_content_hidden', True))).lower()}`",
        f"- transcript discovery reads contents: `{str(bool(safety.get('transcript_discovery_reads_contents', False))).lower()}`",
        f"- transcript capture reads contents: `{str(bool(safety.get('transcript_capture_reads_contents', False))).lower()}`",
        f"- writes active memory: `{str(bool(safety.get('writes_active_memory', False))).lower()}`",
        "",
        "## Suggested Next Tasks",
        "",
    ]
    if suggested_tasks:
        lines += [
            _md_row(["step", "task", "command", "approval"]),
            _md_row(["---", "---", "---", "---"]),
        ]
        for item in suggested_tasks[:8]:
            if not isinstance(item, dict):
                continue
            lines.append(
                _md_row(
                    [
                        item.get("step", ""),
                        item.get("task", ""),
                        item.get("command", ""),
                        "yes" if item.get("requires_human_approval") else "no",
                    ]
                )
            )

    lines += [
        "",
        "## Agent Start Prompt",
        "",
        "```text",
        str(workspace.get("agent_start_prompt", "")).strip()
        or "Read this workspace handoff first, then review candidates without promoting memory automatically.",
        "```",
        "",
        "## Next Action",
        "",
        _md_text(workspace.get("next_action", "")) or "Review candidate queue before changing active memory.",
        "",
    ]
    return "\n".join(lines)


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
        "safety": {
            "read_only": True,
            "auto_promote": auto_promote_enabled,
            "hard_delete": False,
            "candidate_content_hidden": True,
            "transcript_discovery_reads_contents": False,
            "transcript_capture_reads_contents": bool((capture.get("safety") or {}).get("reads_transcript_contents", False)),
            "writes_active_memory": auto_promote_promoted > 0,
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
    tasks: list[dict[str, Any]] = []
    step = 1
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
    return "\n".join(
        [
            "You are continuing a Vault-for-LLM memory automation cycle.",
            f"Project: {workspace.get('project_dir', '')}",
            "Start from this handoff, not the full raw reports.",
            (
                f"Candidate queue items: {queue_count}; uncaptured transcripts: {transcript_count}; "
                f"auto-captured candidates: {captured_candidates}; auto-promoted: {auto_promoted}; "
                f"learning rules: {learning_rules}."
            ),
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


def _candidate_inbox_item(row: dict[str, Any], *, include_content: bool = False) -> dict[str, Any]:
    status = str(row.get("status") or "")
    privacy = str(row.get("privacy_status") or "")
    duplicate = str(row.get("duplicate_status") or "")
    quality = str(row.get("quality_status") or "")
    sensitivity = str(row.get("sensitivity") or "")
    scope = str(row.get("scope") or "")
    source = str(row.get("source") or "")
    memory_type = str(row.get("memory_type") or "")
    priority = _candidate_review_priority(
        status=status,
        privacy=privacy,
        duplicate=duplicate,
        quality=quality,
        sensitivity=sensitivity,
        scope=scope,
        source=source,
        memory_type=memory_type,
    )
    item = {
        "id": row.get("id", ""),
        "title": row.get("title", ""),
        "status": status,
        "priority": priority,
        "recommended_action": _candidate_recommended_action(
            status=status,
            privacy=privacy,
            duplicate=duplicate,
            quality=quality,
            sensitivity=sensitivity,
        ),
        "reason": _candidate_review_reason(
            status=status,
            privacy=privacy,
            duplicate=duplicate,
            quality=quality,
            sensitivity=sensitivity,
            source=source,
            memory_type=memory_type,
        ),
        "source": source,
        "source_ref": row.get("source_ref", ""),
        "memory_type": memory_type,
        "category": row.get("category", ""),
        "layer": row.get("layer", ""),
        "trust": float(row.get("trust") or 0.0),
        "scope": scope,
        "sensitivity": sensitivity,
        "owner_agent": row.get("owner_agent", ""),
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
        "gates": {
            "privacy": privacy,
            "duplicate": duplicate,
            "quality": quality,
        },
    }
    if include_content:
        item["content"] = redact_secrets(str(row.get("content") or ""))
    return item


def _candidate_review_priority(
    *,
    status: str,
    privacy: str,
    duplicate: str,
    quality: str,
    sensitivity: str,
    scope: str,
    source: str,
    memory_type: str,
) -> int:
    priority = 0
    if privacy == "fail":
        priority += 100
    if status in {"candidate", "rejected", "blocked"}:
        priority += 30
    if sensitivity in {"high", "restricted"} or scope == "private":
        priority += 20
    if duplicate and duplicate not in {"pass", "unique"}:
        priority += 18
    if quality and quality != "pass":
        priority += 12
    if source in {"session_capture", "automation", "dream"}:
        priority += 8
    if memory_type in {"forgetting_suggestion", "consolidation_suggestion", "dream_suggestion"}:
        priority += 5
    return priority


def _candidate_recommended_action(
    *,
    status: str,
    privacy: str,
    duplicate: str,
    quality: str,
    sensitivity: str,
) -> str:
    if privacy == "fail":
        return "block_or_redact"
    if sensitivity in {"high", "restricted"}:
        return "manual_review"
    if duplicate and duplicate not in {"pass", "unique"}:
        return "merge_or_reject_duplicate"
    if quality and quality != "pass":
        return "clarify_or_reject"
    if status == "candidate":
        return "review_for_promotion"
    if status in {"rejected", "blocked"}:
        return "feedback_recorded"
    return "inspect"


def _candidate_review_reason(
    *,
    status: str,
    privacy: str,
    duplicate: str,
    quality: str,
    sensitivity: str,
    source: str,
    memory_type: str,
) -> str:
    if privacy == "fail":
        return "Privacy gate failed; keep this out of active memory unless redacted and re-submitted."
    if sensitivity in {"high", "restricted"}:
        return "Sensitive candidate; require explicit review before promotion."
    if duplicate and duplicate not in {"pass", "unique"}:
        return "Duplicate gate suggests this should be merged or rejected instead of promoted as-is."
    if quality and quality != "pass":
        return "Quality gate suggests the candidate is too weak, vague, or underspecified."
    if source == "session_capture":
        return "Captured from an agent session; promote only if it is reusable project knowledge."
    if memory_type.endswith("_suggestion"):
        return "Automation suggestion; use it as review guidance, not as a direct memory mutation."
    if status == "candidate":
        return "Pending candidate with passing gates."
    return "Candidate outcome is already recorded; use it as automation feedback."


def _empty_review_digest(limit: int) -> dict[str, Any]:
    return {
        "budget": max(1, int(limit or 5)),
        "items": [],
        "report_item_count": 0,
        "candidate_item_count": 0,
        "principle": "show report-level decisions first, then only the smallest candidate queue",
    }


def _inbox_review_digest(
    candidate_items: list[dict[str, Any]],
    latest_report: dict[str, Any],
    *,
    limit: int,
) -> dict[str, Any]:
    budget = max(1, min(int(limit or 5), 50))
    report_items = _report_review_digest_items(latest_report)
    candidate_digest = [_candidate_review_digest_item(item) for item in candidate_items]
    combined = [*report_items, *candidate_digest]
    combined.sort(key=lambda item: (-int(item.get("priority") or 0), str(item.get("created_at") or ""), str(item.get("id") or "")))
    return {
        "budget": budget,
        "items": combined[:budget],
        "report_item_count": len(report_items),
        "candidate_item_count": len(candidate_digest),
        "principle": "show report-level decisions first, then only the smallest candidate queue",
    }


def _candidate_review_digest_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "candidate_review",
        "id": item.get("id", ""),
        "title": item.get("title", ""),
        "priority": int(item.get("priority") or 0),
        "count": 1,
        "reason": item.get("reason", ""),
        "recommended_action": item.get("recommended_action", ""),
        "safe_action": "Use vault promote only after approval, or vault candidate-review to record reject/block feedback.",
        "source": item.get("source", ""),
        "source_ref": item.get("source_ref", ""),
        "created_at": item.get("created_at", ""),
    }


def _report_review_digest_items(latest_report: dict[str, Any]) -> list[dict[str, Any]]:
    human_review = latest_report.get("human_review") or {}
    report_path = str(latest_report.get("path") or latest_report.get("report_path") or "")
    items: list[dict[str, Any]] = []
    for raw in human_review.get("items") or []:
        kind = str(raw.get("kind") or "")
        count = int(raw.get("count") or 0)
        if not kind or count <= 0:
            continue
        meta = _report_review_kind_meta(kind)
        items.append(
            {
                "kind": "report_review",
                "id": kind,
                "title": meta["title"],
                "priority": meta["priority"],
                "count": count,
                "reason": meta["reason"],
                "recommended_action": meta["recommended_action"],
                "safe_action": meta["safe_action"],
                "report_path": report_path,
            }
        )
    return items


def _report_review_kind_meta(kind: str) -> dict[str, Any]:
    meta = {
        "protected_expired": {
            "title": "Protected expired memories",
            "priority": 95,
            "reason": "Private, high-sensitivity, restricted, or protected-layer memory reached TTL but policy blocked automation.",
            "recommended_action": "approve_keep_extend_or_redact",
            "safe_action": "Inspect bounded metadata first; do not widen policy until sensitivity and ownership are clear.",
        },
        "expired_but_used": {
            "title": "Expired but still used memories",
            "priority": 90,
            "reason": "These memories are past TTL but still retrieved or cited, so the system needs a keep/cold-store decision.",
            "recommended_action": "decide_keep_refresh_or_cold_store",
            "safe_action": "Prefer refresh or cold-store over deletion; check citations before changing TTL.",
        },
        "cold_stored_expired": {
            "title": "Cold-stored used memories",
            "priority": 82,
            "reason": "Automation summarized and archived expired-but-used memory under reversible cold-store policy.",
            "recommended_action": "spot_check_cold_store_summary",
            "safe_action": "Spot-check summaries before making cold-store policy broader.",
        },
        "cold_store_expired_preview": {
            "title": "Cold-store preview",
            "priority": 78,
            "reason": "Automation found expired-but-used memory that would be summarized and archived if apply is enabled.",
            "recommended_action": "review_before_apply",
            "safe_action": "Run a dry-run report first; apply only after policy is reviewed.",
        },
        "auto_promoted_low_risk": {
            "title": "Auto-promoted low-risk memories",
            "priority": 88,
            "reason": "Policy allowed low-risk candidates to enter active memory automatically.",
            "recommended_action": "spot_check_auto_promotions",
            "safe_action": "Inspect promoted ids and keep promotion rules narrow.",
        },
        "auto_promote_low_risk_preview": {
            "title": "Auto-promote preview",
            "priority": 76,
            "reason": "Automation found candidates that would be promoted if apply is enabled.",
            "recommended_action": "review_gates_before_apply",
            "safe_action": "Check source_ref, scope, sensitivity, and gate status before applying.",
        },
        "dream_candidate_suggestions": {
            "title": "Dream candidate suggestions",
            "priority": 65,
            "reason": "Dream found possible cleanup or consolidation candidates; these remain review-only.",
            "recommended_action": "review_or_ignore_suggestions",
            "safe_action": "Treat suggestions as queue ordering hints, not active memory changes.",
        },
        "forgetting_candidate_suggestions": {
            "title": "Forgetting candidate suggestions",
            "priority": 72,
            "reason": "Lifecycle review proposed candidate records for expired, protected, or still-used memory.",
            "recommended_action": "review_lifecycle_candidates",
            "safe_action": "Promote only reusable conclusions; reject vague or overly private suggestions.",
        },
        "pending_candidates": {
            "title": "Pending candidate queue",
            "priority": 70,
            "reason": "Candidate memory is waiting for explicit promote, reject, or block decisions.",
            "recommended_action": "review_candidate_queue",
            "safe_action": "Use the compact inbox first; open raw content only when needed.",
        },
        "duplicate_groups": {
            "title": "Duplicate memory groups",
            "priority": 68,
            "reason": "Dream detected likely duplicated memory that may need merge or rejection.",
            "recommended_action": "merge_or_reject_duplicates",
            "safe_action": "Prefer source-preserving merge decisions over blind deletion.",
        },
        "weak_metadata": {
            "title": "Weak metadata",
            "priority": 55,
            "reason": "Some memory items lack enough metadata for reliable retrieval or governance.",
            "recommended_action": "clarify_metadata",
            "safe_action": "Patch title, source, category, or tags without changing factual content.",
        },
        "expired_active": {
            "title": "Expired active memories",
            "priority": 60,
            "reason": "Active memory is past TTL and should be archived, refreshed, or deliberately kept.",
            "recommended_action": "review_ttl_policy",
            "safe_action": "Archive only reversible, non-protected rows under reviewed policy.",
        },
    }
    fallback = {
        "title": kind.replace("_", " ").strip().title() or "Automation review item",
        "priority": 50,
        "reason": "Automation surfaced this report item for human review.",
        "recommended_action": "inspect_report_item",
        "safe_action": "Read the compact report before changing policy or memory.",
    }
    return meta.get(kind, fallback)


def _inbox_summary(
    items: list[dict[str, Any]],
    latest_report: dict[str, Any],
    *,
    transcript_discovery: dict[str, Any] | None = None,
    review_budget: int,
) -> dict[str, Any]:
    pending = [item for item in items if item.get("status") == "candidate"]
    rejected = [item for item in items if item.get("status") == "rejected"]
    privacy_blocked = [item for item in items if (item.get("gates") or {}).get("privacy") == "fail"]
    duplicate_review = [
        item for item in items
        if (item.get("gates") or {}).get("duplicate") not in {"", "pass", "unique"}
    ]
    quality_review = [
        item for item in items
        if (item.get("gates") or {}).get("quality") not in {"", "pass"}
    ]
    needs_review = [
        item for item in items
        if item.get("status") == "candidate" or item.get("recommended_action") not in {"feedback_recorded"}
    ]
    by_source: dict[str, int] = {}
    by_action: dict[str, int] = {}
    for item in items:
        source = str(item.get("source") or "unknown")
        action = str(item.get("recommended_action") or "inspect")
        by_source[source] = by_source.get(source, 0) + 1
        by_action[action] = by_action.get(action, 0) + 1
    discovery = transcript_discovery or {}
    return {
        "pending_candidates": len(pending),
        "rejected_candidates": len(rejected),
        "privacy_blocked": len(privacy_blocked),
        "duplicate_review": len(duplicate_review),
        "quality_review": len(quality_review),
        "needs_review": len(needs_review),
        "review_budget": int(review_budget),
        "shown": min(len(items), int(review_budget)),
        "by_source": by_source,
        "by_recommended_action": by_action,
        "latest_report_path": latest_report.get("path", ""),
        "latest_report_review_required": bool((latest_report.get("human_review") or {}).get("required")),
        "latest_report_items": (latest_report.get("human_review") or {}).get("items", []),
        "uncaptured_transcripts": int(discovery.get("count") or 0),
        "transcript_discovery_reads_contents": bool(discovery.get("read_contents", False)),
        "principle": "show the smallest review queue first; do not expose raw content or mutate memory by default",
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
    return {
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
        "principle": "usage helps agents prioritize maintenance; it does not override access policy or source quality",
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


def _write_report(project: Path, payload: dict[str, Any]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    path = project / "reports" / "automation" / f"{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path.relative_to(project))


def _read_report(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _report_summary(project: Path, path: Path, data: dict[str, Any]) -> dict[str, Any]:
    diff = data.get("dry_run_diff") or {}
    ledger = data.get("action_ledger") or []
    archive = data.get("archive_expired") or {}
    cold_store = data.get("cold_store_expired") or {}
    forgetting = data.get("forgetting") or {}
    auto_promote = data.get("auto_promote") or {}
    dream = data.get("dream") or {}
    dream_learning = dream.get("learning_policy") or {}
    return {
        "path": str(path.relative_to(project)),
        "generated_at": data.get("generated_at", ""),
        "mode": data.get("mode", ""),
        "status": data.get("status", ""),
        "apply": bool(data.get("apply", False)),
        "human_review": data.get("human_review", {}),
        "report_path": data.get("report_path", ""),
        "dream_report_path": dream.get("report_path", ""),
        "dream_candidate_suggestions": int((dream.get("summary") or {}).get("candidate_suggestions") or 0),
        "dream_candidates_written": int((dream.get("summary") or {}).get("candidates_written") or 0),
        "dream_candidates_skipped_existing": int((dream.get("summary") or {}).get("candidates_skipped_existing") or 0),
        "dream_learning_policy_status": dream_learning.get("status", ""),
        "dream_learning_policy_applied_rules": int(dream_learning.get("applied_rules") or 0),
        "forgetting_candidate_suggestions": int(forgetting.get("candidate_suggestions") or 0),
        "forgetting_candidates_written": int(forgetting.get("candidates_written") or 0),
        "forgetting_candidates_skipped_existing": int(forgetting.get("candidates_skipped_existing") or 0),
        "cold_store_eligible_count": int(cold_store.get("eligible_count") or 0),
        "cold_store_applied_count": int(cold_store.get("applied_count") or 0),
        "cold_store_skipped_protected_count": int(cold_store.get("skipped_protected_count") or 0),
        "auto_promote_enabled": bool(auto_promote.get("enabled", False)),
        "auto_promote_would_promote_count": int(auto_promote.get("would_promote_count") or 0),
        "auto_promote_promoted_count": int(auto_promote.get("promoted_count") or 0),
        "archived_count": int(archive.get("archived_count") or 0),
        "eligible_count": int(archive.get("eligible_count") or 0),
        "skipped_used_count": int(archive.get("skipped_used_count") or 0),
        "skipped_policy_count": int(archive.get("skipped_protected_count") or 0),
        "dry_run_diff": {
            "would_archive_count": int(diff.get("would_archive_count") or 0),
            "applied_count": int(diff.get("applied_count") or 0),
            "skipped_usage_count": int(diff.get("skipped_usage_count") or 0),
            "skipped_policy_count": int(diff.get("skipped_policy_count") or 0),
            "would_cold_store_count": int(diff.get("would_cold_store_count") or 0),
            "cold_store_applied_count": int(diff.get("cold_store_applied_count") or 0),
            "cold_store_skipped_usage_count": int(diff.get("cold_store_skipped_usage_count") or 0),
            "cold_store_skipped_policy_count": int(diff.get("cold_store_skipped_policy_count") or 0),
            "hard_delete": bool(diff.get("hard_delete", False)),
            "promote_candidates": bool(diff.get("promote_candidates", False)),
            "permission_changes": bool(diff.get("permission_changes", False)),
        },
        "ledger_count": len(ledger) if isinstance(ledger, list) else 0,
    }


def _resolve_report_path(
    project: Path,
    report_dir: Path,
    *,
    report_path: str | Path = "",
    latest: bool = False,
) -> Path | None:
    if report_path:
        raw = Path(report_path)
        candidate = raw if raw.is_absolute() else project / raw
        try:
            resolved = candidate.expanduser().resolve()
            allowed = report_dir.expanduser().resolve()
        except Exception as exc:
            raise ValueError(f"unable to resolve automation report path: {exc}") from exc
        if allowed != resolved and allowed not in resolved.parents:
            raise ValueError("automation report path must stay under reports/automation")
        if not resolved.exists():
            raise FileNotFoundError(str(resolved))
        return resolved
    if latest:
        reports = _automation_report_files(report_dir)
        return reports[0] if reports else None
    return None


def _resolve_handoff_read_path(
    project: Path,
    report_dir: Path,
    *,
    source: str = "auto",
    handoff_path: str | Path = "",
) -> Path | None:
    if source not in {"auto", "cycle", "inbox"}:
        raise ValueError("handoff source must be one of: auto, cycle, inbox")
    if handoff_path:
        raw = Path(handoff_path)
        candidate = raw if raw.is_absolute() else project / raw
        try:
            resolved = candidate.expanduser().resolve()
            allowed = report_dir.expanduser().resolve()
        except Exception as exc:
            raise ValueError(f"unable to resolve automation handoff path: {exc}") from exc
        if allowed != resolved and allowed not in resolved.parents:
            raise ValueError("automation handoff path must stay under reports/automation")
        if resolved.suffix.lower() not in {".md", ".json"}:
            raise ValueError("automation handoff path must be a Markdown or JSON file")
        if not resolved.exists():
            raise FileNotFoundError(str(resolved))
        return resolved
    names_by_source = {
        "cycle": ["cycle-latest.md", "cycle-latest.json"],
        "inbox": ["inbox-latest.json"],
        "auto": ["cycle-latest.md", "cycle-latest.json", "inbox-latest.json"],
    }
    for name in names_by_source[source]:
        candidate = report_dir / name
        if candidate.exists():
            return candidate
    return None


def _automation_report_files(report_dir: Path) -> list[Path]:
    """Return timestamped automation run reports, excluding handoff artifacts."""
    return sorted(
        (path for path in report_dir.glob("*.json") if path.name != "learning_policy.json"),
        reverse=True,
    )


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
    return {
        "apply_requested": bool(apply_requested),
        "policy_allows_archive": bool(archive_allowed),
        "would_archive_count": len(would_archive),
        "applied_count": len([item for item in would_archive if item.get("status") == "applied"]),
        "skipped_usage_count": len(skipped_usage),
        "skipped_policy_count": len(skipped_policy),
        "cold_store_skipped_usage_count": len(cold_store_skipped_usage),
        "cold_store_skipped_policy_count": len(cold_store_skipped_policy),
        "fields_changed": ["status", "archived_at", "updated_at"] if would_archive else [],
        "hard_delete": False,
        "promote_candidates": False,
        "permission_changes": False,
    }


def _normalize_mode(mode: str) -> str:
    value = str(mode or DEFAULT_MODE).strip().lower()
    if value not in AUTOMATION_MODES:
        raise ValueError(f"automation mode must be one of: {', '.join(sorted(AUTOMATION_MODES))}")
    return value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    out["mode"] = _normalize_mode(str(out.get("mode") or DEFAULT_MODE))
    return out


def _policy_list(policy: dict[str, Any], key: str) -> list[str]:
    value = policy.get(key, [])
    if isinstance(value, str):
        values = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        values = [str(part).strip() for part in value]
    else:
        values = []
    return [part.lower() for part in values if part]


def _policy_float(policy: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(policy.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def _policy_int(policy: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(policy.get(key, default))
    except (TypeError, ValueError):
        return int(default)


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
