"""Read-only automation brief and fleet-health helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .automation_review import apply_review_card_learning, review_card_title
from .importance import MODEL_ID as IMPORTANCE_MODEL_ID
from .importance import compute_memory_importance


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


def _sync_summary(sync_health: dict[str, Any]) -> dict[str, Any]:
    if not sync_health:
        return {
            "sync_status": "unavailable",
            "open_sync_conflicts": 0,
            "sync_revisions": 0,
            "sync_audit_events": 0,
        }
    counts = sync_health.get("counts") or {}
    return {
        "sync_status": sync_health.get("status", "idle"),
        "open_sync_conflicts": int(counts.get("open_conflicts") or 0),
        "sync_revisions": int(counts.get("revisions") or 0),
        "sync_audit_events": int(counts.get("audit_events") or 0),
    }


def _sync_review_items(sync_health: dict[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    """Turn sync conflicts into compact human-review cards without exposing content."""
    counts = sync_health.get("counts") or {}
    open_count = int(counts.get("open_conflicts") or 0)
    if not sync_health or open_count <= 0:
        return []
    max_items = max(1, min(int(limit or 5), 20))
    items = []
    for conflict in (sync_health.get("open_conflicts") or [])[:max_items]:
        conflict_id = str(conflict.get("id") or "")
        remote_candidate_id = str(conflict.get("remote_candidate_id") or conflict.get("candidate_id") or "")
        local_knowledge_id = conflict.get("local_knowledge_id")
        items.append(
            {
                "kind": "sync_conflict_review",
                "id": conflict_id,
                "title": "Remote memory candidate conflicts with local knowledge",
                "priority": 92,
                "reason": (
                    f"Remote candidate {remote_candidate_id or '(unknown)'} conflicts with "
                    f"local knowledge #{local_knowledge_id or '(unknown)'}."
                ),
                "recommended_action": "review_remote_conflict",
                "safe_action": (
                    "Use `vault sync conflicts` and resolve only after checking bounded evidence; "
                    "active memory is not changed automatically."
                ),
                "remote_candidate_id": remote_candidate_id,
                "local_knowledge_id": local_knowledge_id,
            }
        )
    if not items:
        items.append(
            {
                "kind": "sync_conflict_review",
                "id": "open-conflicts",
                "title": "Remote memory conflicts need review",
                "priority": 92,
                "reason": f"{open_count} open remote sync conflicts need a local decision.",
                "recommended_action": "review_remote_conflict",
                "safe_action": "Run `vault sync conflicts` before accepting any remote candidate into active memory.",
            }
        )
    return items


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
                "weight_tier": importance["weight_tier"],
                "lifecycle_action": importance["lifecycle_action"],
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
    open_sync_conflicts: int = 0,
) -> str:
    if learning_status == "blocked":
        return "blocked"
    if open_sync_conflicts > 0:
        return "needs_review"
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
    sync_health: dict[str, Any] | None = None,
    project_agent_count: int,
    limit: int = 5,
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    agent_count = int(agent_health.get("agent_count") or 0)
    sync = sync_health or {}
    counts = sync.get("counts") or {}
    open_sync_conflicts = int(counts.get("open_conflicts") or 0)
    if open_sync_conflicts > 0:
        cards.append(
            {
                "kind": "sync_conflicts",
                "priority": 92,
                "title": "Remote memory sync has open conflicts",
                "reason": f"{open_sync_conflicts} remote candidate conflict(s) need review before they can affect active memory.",
                "safe_action": "Run `vault sync conflicts` or check the GUI Sync Health card; keep active knowledge local until resolved.",
            }
        )
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
    seen: set[tuple[str, str]] = set()

    def add_item(item: dict[str, Any]) -> None:
        kind = str(item.get("kind") or "")
        item_id = str(item.get("id") or "")
        dedupe_key = (kind, item_id) if item_id else (kind, str(item))
        if dedupe_key in seen:
            return
        seen.add(dedupe_key)
        items.append(item)

    digest = inbox.get("review_digest") or {}
    for row in digest.get("items") or []:
        add_item(
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
        add_item(
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
            add_item(
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
