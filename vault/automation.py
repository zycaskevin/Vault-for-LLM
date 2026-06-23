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

AUTOMATION_MODES = {"conservative", "balanced", "autonomous"}
DEFAULT_MODE = "balanced"
POLICY_FILE = "automation_policy.yaml"


DEFAULT_POLICIES: dict[str, dict[str, Any]] = {
    "conservative": {
        "mode": "conservative",
        "auto_archive_expired": False,
        "protect_used_expired": True,
        "protected_scopes": ["private"],
        "protected_sensitivities": ["high", "restricted"],
        "auto_apply_safe_metadata": False,
        "dream_write_candidates": False,
        "forgetting_write_candidates": False,
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
        "protect_used_expired": True,
        "protected_scopes": ["private"],
        "protected_sensitivities": ["high", "restricted"],
        "auto_apply_safe_metadata": False,
        "dream_write_candidates": True,
        "forgetting_write_candidates": True,
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
        "protect_used_expired": True,
        "protected_scopes": ["private"],
        "protected_sensitivities": ["high", "restricted"],
        "auto_apply_safe_metadata": False,
        "dream_write_candidates": True,
        "forgetting_write_candidates": True,
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
        usage_review_before = _usage_review(policy, before_usage, archive_result)
        archive_ledger = _archive_action_ledger(archive_result, applied=archive_apply)
        dry_run_diff = _dry_run_diff(archive_ledger, apply_requested=bool(apply), archive_allowed=archive_allowed)
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
        after_usage = db.usage_stats(limit=limit)
        candidate_count_after = len(db.list_memory_candidates(status="candidate", limit=1000))

    forgetting = _forgetting_summary(forgetting_results)
    payload = {
        "action": "run",
        "mode": mode_name,
        "generated_at": _now(),
        "project_dir": str(project),
        "apply": bool(apply),
        "status": "completed",
        "policy": {
            "auto_archive_expired": archive_allowed,
            "protect_used_expired": bool(policy.get("protect_used_expired", True)),
            "protected_scopes": _policy_list(policy, "protected_scopes"),
            "protected_sensitivities": _policy_list(policy, "protected_sensitivities"),
            "auto_apply_safe_metadata": bool(policy.get("auto_apply_safe_metadata", False)),
            "dream_write_candidates": bool(policy.get("dream_write_candidates", False)),
            "dream_write_candidates_requires_apply": True,
            "forgetting_write_candidates": bool(policy.get("forgetting_write_candidates", False)),
            "forgetting_write_candidates_requires_apply": True,
        },
        "usage_before": before_usage,
        "usage_after": after_usage,
        "usage_review": usage_review_before,
        "candidate_count": candidate_count_after,
        "candidate_count_before": candidate_count_before,
        "candidate_count_after": candidate_count_after,
        "archive_expired": archive_result,
        "action_ledger": archive_ledger,
        "dry_run_diff": dry_run_diff,
        "forgetting": forgetting,
        "forgetting_results": forgetting_results,
        "dream": dream,
        "human_review": _review_summary(policy, after_usage, candidate_count_after, dream, usage_review_before, forgetting),
        "next_action": "Review human_review and report_path; adjust automation_policy.yaml before stronger autonomy.",
    }
    if apply and not archive_allowed:
        payload["warning"] = "apply requested, but policy auto_archive_expired is false"
    if report_enabled:
        payload["report_path"] = _write_report(project, payload)
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

    reports = sorted(report_dir.glob("*.json"), reverse=True)[: max(1, int(limit or 5))]
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


def _review_summary(
    policy: dict[str, Any],
    usage: dict[str, Any],
    candidate_count: int,
    dream: dict[str, Any],
    usage_review: dict[str, Any] | None = None,
    forgetting: dict[str, Any] | None = None,
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
    forgetting = data.get("forgetting") or {}
    return {
        "path": str(path.relative_to(project)),
        "generated_at": data.get("generated_at", ""),
        "mode": data.get("mode", ""),
        "status": data.get("status", ""),
        "apply": bool(data.get("apply", False)),
        "human_review": data.get("human_review", {}),
        "report_path": data.get("report_path", ""),
        "dream_report_path": (data.get("dream") or {}).get("report_path", ""),
        "dream_candidate_suggestions": int(((data.get("dream") or {}).get("summary") or {}).get("candidate_suggestions") or 0),
        "dream_candidates_written": int(((data.get("dream") or {}).get("summary") or {}).get("candidates_written") or 0),
        "dream_candidates_skipped_existing": int(((data.get("dream") or {}).get("summary") or {}).get("candidates_skipped_existing") or 0),
        "forgetting_candidate_suggestions": int(forgetting.get("candidate_suggestions") or 0),
        "forgetting_candidates_written": int(forgetting.get("candidates_written") or 0),
        "forgetting_candidates_skipped_existing": int(forgetting.get("candidates_skipped_existing") or 0),
        "archived_count": int(archive.get("archived_count") or 0),
        "eligible_count": int(archive.get("eligible_count") or 0),
        "skipped_used_count": int(archive.get("skipped_used_count") or 0),
        "skipped_policy_count": int(archive.get("skipped_protected_count") or 0),
        "dry_run_diff": {
            "would_archive_count": int(diff.get("would_archive_count") or 0),
            "applied_count": int(diff.get("applied_count") or 0),
            "skipped_usage_count": int(diff.get("skipped_usage_count") or 0),
            "skipped_policy_count": int(diff.get("skipped_policy_count") or 0),
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
        reports = sorted(report_dir.glob("*.json"), reverse=True)
        return reports[0] if reports else None
    return None


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


def _dry_run_diff(
    ledger: list[dict[str, Any]],
    *,
    apply_requested: bool,
    archive_allowed: bool,
) -> dict[str, Any]:
    would_archive = [item for item in ledger if item.get("status") in {"preview", "applied"}]
    skipped_usage = [item for item in ledger if item.get("status") == "skipped_usage"]
    skipped_policy = [item for item in ledger if item.get("status") == "skipped_policy"]
    return {
        "apply_requested": bool(apply_requested),
        "policy_allows_archive": bool(archive_allowed),
        "would_archive_count": len(would_archive),
        "applied_count": len([item for item in would_archive if item.get("status") == "applied"]),
        "skipped_usage_count": len(skipped_usage),
        "skipped_policy_count": len(skipped_policy),
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
