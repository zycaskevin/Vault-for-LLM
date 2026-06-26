"""Automation lifecycle, ledger, and policy-gated mutation helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

from .automation_policy import (
    DEFAULT_MODE,
    POLICY_FILE,
    load_policy,
    normalize_mode as _normalize_mode,
    policy_float as _policy_float,
    policy_int as _policy_int,
    policy_list as _policy_list,
)
from .db import VaultDB
from .importance import MODEL_ID as IMPORTANCE_MODEL_ID
from .importance import compute_memory_importance


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
