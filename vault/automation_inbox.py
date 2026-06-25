"""Automation inbox and review-digest helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .automation_learning import _apply_learning_priority, _load_automation_learning_policy
from .automation_reports import _read_report, _relative_to_project, _report_summary, _resolve_report_path
from .db import VaultDB
from .privacy import redact_secrets


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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
    learning_policy = _load_automation_learning_policy(project)
    with VaultDB(db_path) as db:
        candidates = db.list_memory_candidates(status=None, limit=scan_limit)

    candidate_items = [
        _candidate_inbox_item(row, include_content=include_content, learning_policy=learning_policy)
        for row in candidates
    ]
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
    summary["learning_policy_status"] = learning_policy.get("status", "missing")
    summary["learning_policy_applied_rules"] = int(learning_policy.get("applied_rules") or 0)
    payload = {
        "action": "inbox",
        "generated_at": generated_at,
        "project_dir": str(project),
        "status": "completed",
        "summary": summary,
        "review_queue": candidate_items[:limit_i],
        "review_digest": review_digest,
        "learning_policy": {
            "status": learning_policy.get("status", "missing"),
            "path": learning_policy.get("path", ""),
            "applied_rules": int(learning_policy.get("applied_rules") or 0),
            "readiness": learning_policy.get("readiness", ""),
        },
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



def _candidate_inbox_item(
    row: dict[str, Any],
    *,
    include_content: bool = False,
    learning_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        "base_priority": priority,
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
    _apply_learning_priority(item, learning_policy or {})
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
        "base_priority": int(item.get("base_priority") or item.get("priority") or 0),
        "learning_multiplier": float(item.get("learning_multiplier") or 1.0),
        "learning_action": item.get("learning_action", ""),
        "learning_reason": item.get("learning_reason", ""),
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
