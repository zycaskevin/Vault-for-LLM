"""Read and review API helpers for the local Vault GUI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent_registry import list_agents
from .automation import automation_brief, automation_review_summary
from .automation_inbox import automation_inbox
from .daily_report import build_daily_report
from .db import VaultDB
from .db_knowledge import escape_like_pattern
from .gateway_audit import gateway_audit_report
from .memory import promote_candidate, review_candidate
from .memory_migration import migrate_memory_source
from .multi_host import resolve_conflict, sync_status
from .search import VaultSearch
from .search_utils import normalize_search_limit
from .gui_format import (
    compact_brief,
    compact_candidate,
    compact_inbox,
    compact_knowledge,
    compact_task,
    compact_review_result,
    confirmation_token,
    governance_for,
    graph_edges_for_entry,
    timeline_for,
    usage_for,
)
from .gui_obsidian import list_obsidian_conflicts
from .task_ledger import claim_task_handoff, get_task, get_task_handoff, list_task_handoffs, list_tasks, task_handoff


def _clean_filter(value: str | None) -> str:
    cleaned = str(value or "").strip()
    return "" if cleaned.lower() in {"", "all", "any", "*"} else cleaned


_FACET_EXPRESSIONS = {
    "layers": "layer",
    "categories": "category",
    "scopes": "COALESCE(scope, 'project')",
    "sensitivities": "COALESCE(sensitivity, 'low')",
}


def _file_updated_at(path: Path) -> str:
    if not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _project_matches_agent(agent: dict[str, Any], project: Path) -> bool:
    project_resolved = project.expanduser().resolve()
    for key in ("project_dir", "private_project_dir"):
        value = str(agent.get(key) or "").strip()
        if not value:
            continue
        try:
            if Path(value).expanduser().resolve() == project_resolved:
                return True
        except OSError:
            continue
    return False


def _compact_agent(agent: dict[str, Any], project: Path) -> dict[str, Any]:
    return {
        "agent_id": agent.get("agent_id", ""),
        "scope": agent.get("scope", ""),
        "tool_profile": agent.get("tool_profile", ""),
        "memory_layout": agent.get("memory_layout", ""),
        "features": agent.get("features", []),
        "skills": agent.get("skills", []),
        "vault_version": agent.get("vault_version", ""),
        "last_seen_at": agent.get("last_seen_at", ""),
        "project_dir": agent.get("project_dir", ""),
        "private_project_dir": agent.get("private_project_dir", ""),
        "connected_to_project": _project_matches_agent(agent, project),
    }


def _obsidian_sync_item(project: Path) -> dict[str, Any]:
    manifest_path = project / ".vault" / "obsidian-import-manifest.json"
    manifest = _load_json_file(manifest_path)
    notes = manifest.get("notes") if isinstance(manifest.get("notes"), dict) else {}
    missing = [
        key for key, value in notes.items()
        if isinstance(value, dict) and value.get("status") == "missing"
    ]
    conflicts = [
        key for key, value in notes.items()
        if isinstance(value, dict) and value.get("status") == "conflict"
    ]
    conflict_items = list_obsidian_conflicts(project, limit=5)
    return {
        "kind": "obsidian",
        "label": "Obsidian incremental import",
        "status": "needs_review" if conflicts else ("ok" if manifest else "not_configured"),
        "updated_at": manifest.get("updated_at", "") or _file_updated_at(manifest_path),
        "path": str(manifest_path),
        "next_action": (
            "Open each note conflict and choose Accept Obsidian, Accept Vault, or Keep both."
            if conflicts
            else "No Obsidian note conflict needs human review."
        ),
        "summary": {
            "active_notes": max(0, len(notes) - len(missing) - len(conflicts)),
            "missing_notes": len(missing),
            "conflict_notes": len(conflicts),
            "conflict_paths": conflicts[:5],
            "conflict_items": conflict_items,
            "review_label": (
                f"{len(conflicts)} notes changed in both Obsidian and Vault"
                if conflicts
                else ""
            ),
            "raw_subdir": manifest.get("raw_subdir", ""),
        },
    }


def _gateway_sync_item(project: Path) -> dict[str, Any]:
    audit = gateway_audit_report(project, limit=5)
    summary = audit.get("summary") if isinstance(audit.get("summary"), dict) else {}
    blocked = int(summary.get("blocked_or_failed_events") or 0)
    total = int(summary.get("total_events") or 0)
    status = "needs_review" if blocked else ("ok" if total else "idle")
    return {
        "kind": "gateway",
        "label": "Gateway / Remote access",
        "status": status,
        "updated_at": (audit.get("recent_events") or [{}])[-1].get("created_at", "") if audit.get("recent_events") else "",
        "path": str(audit.get("audit_path") or ""),
        "next_action": str(audit.get("next_action") or "No Gateway audit events yet."),
        "summary": {
            "total_events": total,
            "blocked_or_failed_events": blocked,
            "unique_client_ips": int(summary.get("unique_client_ips") or 0),
            "rotated_log_count": int(((audit.get("rotation") or {}).get("rotated_log_count")) or 0),
            "security_label": "review blocked access" if blocked else ("gateway quiet" if not total else "gateway healthy"),
        },
        "safety": {
            "token_required_by_default": True,
            "rate_limit_supported": True,
            "tls_supported": True,
            "audit_log_supported": True,
        },
    }


def _report_sync_items(project: Path) -> list[dict[str, Any]]:
    report_dir = project / "reports"
    candidates = [
        ("automation_cycle", "Automation cycle", report_dir / "automation" / "cycle-latest.json"),
        ("automation_inbox", "Automation inbox", report_dir / "automation" / "inbox-latest.json"),
        ("review_summary", "Review summary", report_dir / "automation" / "review-summary-latest.json"),
        ("fleet_health", "Fleet health", report_dir / "automation" / "fleet-health-latest.json"),
        ("daily_report", "Daily report", report_dir / "daily" / "daily-report-latest.json"),
    ]
    items: list[dict[str, Any]] = []
    for kind, label, path in candidates:
        payload = _load_json_file(path)
        if not payload and not path.exists():
            continue
        items.append(
            {
                "kind": kind,
                "label": label,
                "status": payload.get("status", "ok") if payload else "present",
                "updated_at": (
                    payload.get("generated_at")
                    or payload.get("created_at")
                    or payload.get("checked_at")
                    or _file_updated_at(path)
                ),
                "path": str(path),
                "summary": payload.get("summary", {}),
            }
        )
    return items


def _dashboard_activity_health(
    *,
    connected_agents: list[dict[str, Any]],
    all_agents: list[dict[str, Any]],
    recent_candidates: list[dict[str, Any]],
    sync_health: dict[str, Any],
    sync_items: list[dict[str, Any]],
    review_inbox: dict[str, Any],
) -> dict[str, Any]:
    """Return one compact status card for humans and dashboard agents."""
    sync_counts = sync_health.get("counts") or {}
    open_sync_conflicts = int(sync_counts.get("open_conflicts") or 0)
    obsidian_conflicts = 0
    stale_sync_items = 0
    for item in sync_items:
        if item.get("status") in {"needs_review", "warning"}:
            stale_sync_items += 1
        if item.get("kind") == "obsidian":
            obsidian_conflicts = int((item.get("summary") or {}).get("conflict_notes") or 0)

    review_count = int((review_inbox.get("summary") or {}).get("total") or 0)
    if obsidian_conflicts and not open_sync_conflicts:
        status = "needs_review"
        next_action = "Open the Obsidian note review and choose which version to keep."
    elif open_sync_conflicts or obsidian_conflicts:
        status = "needs_review"
        next_action = "Review sync conflicts before changing shared memory."
    elif review_count:
        status = "review"
        next_action = "Open the smallest human review queue; keep routine work agent-handled."
    elif stale_sync_items:
        status = "warning"
        next_action = "Check sync/report freshness before trusting the dashboard."
    else:
        status = "ok"
        next_action = "No urgent memory control action is needed."

    return {
        "status": status,
        "connected_agents": len(connected_agents),
        "registered_agents": len(all_agents),
        "pending_candidates": len(recent_candidates),
        "human_review_items": review_count,
        "open_sync_conflicts": open_sync_conflicts,
        "obsidian_conflicts": obsidian_conflicts,
        "sync_report_warnings": stale_sync_items,
        "review_breakdown": {
            "memory_candidates": len(recent_candidates),
            "remote_sync_conflicts": open_sync_conflicts,
            "obsidian_note_conflicts": obsidian_conflicts,
        },
        "next_action": next_action,
        "safety": {
            "read_only": True,
            "content_hidden_by_default": True,
            "writes_active_memory": False,
        },
    }


def _review_item(
    *,
    kind: str,
    item_id: str,
    title: str,
    reason: str = "",
    status: str = "review",
    action: str = "open",
    target_id: str = "",
    target_kind: str = "",
    sensitivity: str = "low",
    source: str = "",
) -> dict[str, Any]:
    return {
        "kind": kind,
        "id": item_id,
        "title": title,
        "reason": reason,
        "status": status,
        "safe_action": action,
        "target_id": target_id,
        "target_kind": target_kind or kind,
        "sensitivity": sensitivity or "low",
        "source": source,
    }


def _compact_handoff(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id", ""),
        "task_id": row.get("task_id", ""),
        "status": row.get("status", ""),
        "from_agent": row.get("from_agent", ""),
        "to_agent": row.get("to_agent", ""),
        "message": row.get("message", ""),
        "source_ref": row.get("source_ref", ""),
        "scope": row.get("scope", "project"),
        "sensitivity": row.get("sensitivity", "low"),
        "updated_at": row.get("updated_at", ""),
        "confirmation": {"claim": confirmation_token(str(row.get("id") or ""), "claim")},
    }


def _build_gui_review_inbox(
    *,
    review: dict[str, Any],
    recent_candidates: list[dict[str, Any]],
    sync_health: dict[str, Any],
    obsidian_conflicts: list[dict[str, Any]],
    handoffs: list[dict[str, Any]],
    limit: int,
) -> dict[str, Any]:
    """Return the consumer 5% review inbox without raw memory content."""
    items: list[dict[str, Any]] = []
    for card in (review.get("cards") or [])[:limit]:
        cid = str(card.get("id") or "")
        items.append(_review_item(
            kind=str(card.get("kind") or "daily_card"),
            item_id=cid,
            title=str(card.get("title") or card.get("kind") or "Review item"),
            reason=str(card.get("reason") or card.get("safe_action") or ""),
            action=str(card.get("suggested_decision") or card.get("recommended_action") or "review"),
            target_id=cid,
            sensitivity=str(card.get("sensitivity") or "low"),
            source="daily_report",
        ))
    for candidate in recent_candidates[:limit]:
        cid = str(candidate.get("id") or "")
        items.append(_review_item(
            kind="candidate",
            item_id=cid,
            title=str(candidate.get("title") or "Candidate memory"),
            reason=str(candidate.get("reason") or candidate.get("source_ref") or "Review candidate memory."),
            action="review_candidate",
            target_id=cid,
            sensitivity=str(candidate.get("sensitivity") or "low"),
            source=str(candidate.get("source") or "candidate"),
        ))
    for conflict in (sync_health.get("open_conflicts") or [])[:limit]:
        cid = str(conflict.get("id") or "")
        items.append(_review_item(
            kind="sync_conflict",
            item_id=cid,
            title="Remote memory candidate needs review",
            reason=str(conflict.get("reason") or conflict.get("conflict_type") or "Resolve sync conflict."),
            action="resolve_sync_conflict",
            target_id=cid,
            sensitivity="low",
            source="multi_host_sync",
        ))
    for conflict in obsidian_conflicts[:limit]:
        source_path = str(conflict.get("source_path") or conflict.get("id") or "")
        items.append(_review_item(
            kind="obsidian_conflict",
            item_id=source_path,
            title=str(conflict.get("title") or f"筆記兩邊都改過：{source_path}"),
            reason=str(conflict.get("reason") or "請打開詳情後選擇要保留哪一邊。"),
            action="resolve_obsidian_conflict",
            target_id=source_path,
            target_kind="obsidian_note",
            sensitivity="low",
            source="obsidian_sync",
        ))
    for handoff in handoffs[:limit]:
        hid = str(handoff.get("id") or "")
        agent = str(handoff.get("to_agent") or handoff.get("from_agent") or "agent")
        items.append(_review_item(
            kind="task_handoff",
            item_id=hid,
            title=f"Task handoff for {agent}",
            reason=str(handoff.get("message") or "Review task handoff."),
            status=str(handoff.get("status") or "pending"),
            action="open_task",
            target_id=str(handoff.get("task_id") or ""),
            target_kind="task",
            sensitivity=str(handoff.get("sensitivity") or "low"),
            source="task_ledger",
        ))
    summary = {
        "total": len(items),
        "daily_cards": min(len(review.get("cards") or []), limit),
        "candidates": min(len(recent_candidates), limit),
        "sync_conflicts": min(len(sync_health.get("open_conflicts") or []), limit),
        "obsidian_conflicts": min(len(obsidian_conflicts), limit),
        "task_handoffs": min(len(handoffs), limit),
    }
    return {
        "status": "ok",
        "summary": summary,
        "items": items[:limit],
        "safety": {"content_hidden_by_default": True, "open_details_before_decision": True},
        "next_action": "Open the top review item only when a human decision is needed.",
    }


def gui_agent_dashboard(
    project_dir: str | Path,
    *,
    limit: int = 5,
    language: str = "en",
    precomputed_brief: dict[str, Any] | None = None,
    precomputed_review: dict[str, Any] | None = None,
    precomputed_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the multi-agent dashboard payload for the local GUI."""
    project = Path(project_dir)
    limit_i = max(1, min(int(limit or 5), 20))
    db_path = project / "vault.db"
    if not db_path.exists():
        return {
            "status": "blocked",
            "project_dir": str(project),
            "reason": "vault.db missing",
            "agents": {"count": 0, "connected_count": 0, "items": []},
            "recent_sync": [],
            "recent_candidates": [],
            "human_review": {"items": []},
        }

    try:
        registry = list_agents()
        all_agents = [_compact_agent(agent, project) for agent in registry.get("agents", [])]
        agent_error = ""
    except (OSError, ValueError) as exc:
        registry = {"registry_path": "", "updated_at": "", "agents": []}
        all_agents = []
        agent_error = str(exc)
    connected_agents = [agent for agent in all_agents if agent.get("connected_to_project")]

    if precomputed_candidates is None:
        with VaultDB(db_path) as db:
            candidate_rows = db.list_memory_candidates(status="candidate", limit=limit_i)
        recent_candidates = [compact_candidate(row) for row in candidate_rows]
    else:
        recent_candidates = precomputed_candidates[:limit_i]
    brief = precomputed_brief or automation_brief(project, limit=limit_i, review_limit=limit_i)
    review = precomputed_review or automation_review_summary(
        project,
        limit=limit_i,
        precomputed_brief=brief,
    )

    with VaultDB(db_path) as db:
        sync_health = sync_status(db, limit=limit_i)
        handoffs = list_task_handoffs(db, status="pending", limit=limit_i)
    obsidian_conflicts = list_obsidian_conflicts(project, limit=limit_i)
    review_inbox = _build_gui_review_inbox(
        review=review,
        recent_candidates=recent_candidates,
        sync_health=sync_health,
        obsidian_conflicts=obsidian_conflicts,
        handoffs=handoffs,
        limit=limit_i,
    )

    sync_items = [
        {
            "kind": "agent_registry",
            "label": "Agent registry",
            "status": "ok" if not agent_error else "warning",
            "updated_at": registry.get("updated_at", ""),
            "path": registry.get("registry_path", ""),
            "summary": {"agents": len(all_agents), "connected_agents": len(connected_agents)},
            "error": agent_error,
        },
        _gateway_sync_item(project),
        _obsidian_sync_item(project),
        *_report_sync_items(project),
    ]
    sync_items = sorted(
        sync_items,
        key=lambda item: str(item.get("updated_at") or ""),
        reverse=True,
    )[:limit_i]
    activity_health = _dashboard_activity_health(
        connected_agents=connected_agents,
        all_agents=all_agents,
        recent_candidates=recent_candidates,
        sync_health=sync_health,
        sync_items=sync_items,
        review_inbox=review_inbox,
    )

    return {
        "status": "ok",
        "project_dir": str(project),
        "language": language,
        "agents": {
            "count": len(all_agents),
            "connected_count": len(connected_agents),
            "registry_path": registry.get("registry_path", ""),
            "updated_at": registry.get("updated_at", ""),
            "items": connected_agents[:limit_i],
            "all_items": all_agents,
        },
        "recent_sync": sync_items,
        "activity_health": activity_health,
        "sync_health": sync_health,
        "recent_candidates": recent_candidates,
        "human_review": {
            "summary": (review.get("summary") or {}),
            "items": (review.get("cards") or [])[:limit_i],
            "unified_inbox": review_inbox,
            "human_review_5_percent": brief.get("human_review_5_percent", {}),
            "next_action": review.get("next_action", "") or brief.get("next_action", ""),
        },
        "safety": {
            "read_only": True,
            "writes_active_memory": False,
            "writes_candidates": False,
            "includes_raw_candidate_content": False,
        },
    }


def gui_sync_status(project_dir: str | Path, *, limit: int = 5) -> dict[str, Any]:
    """Return the read-only multi-host sync health payload for the GUI."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    if not db_path.exists():
        return {
            "ok": False,
            "status": "blocked",
            "reason": "vault.db missing",
            "counts": {},
            "recent_revisions": [],
            "open_conflicts": [],
            "audit_events": [],
        }
    with VaultDB(db_path) as db:
        return sync_status(db, limit=limit)


def gui_memory_migration(
    project_dir: str | Path,
    *,
    source: str,
    source_format: str = "auto",
    write_candidates: bool = False,
    scope: str = "project",
    sensitivity: str = "low",
    owner_agent: str = "",
    only: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """Preview or import external memory into candidates from the GUI."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    source_i = str(source or "").strip()
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing"}
    if not source_i:
        return {"status": "error", "error": "source_required"}
    try:
        with VaultDB(db_path) as db:
            payload = migrate_memory_source(
                db,
                source_i,
                source_format=source_format,
                dry_run=not bool(write_candidates),
                scope=scope,
                sensitivity=sensitivity,
                owner_agent=owner_agent,
                only=only,
                limit=max(1, min(int(limit or 20), 50)),
                reason="Imported through GUI Memory Migration; review before promotion.",
            )
    except Exception as exc:  # Keep local GUI errors user-facing and non-fatal.
        return {
            "status": "error",
            "error": "migration_failed",
            "reason": str(exc),
            "source": source_i,
            "format": source_format,
        }
    payload["gui"] = {
        "write_candidates": bool(write_candidates),
        "content_hidden_by_default": True,
        "next_action": (
            "Open Review Inbox and promote only the memories you trust."
            if write_candidates
            else "Preview looks safe; import as candidates when ready."
        ),
    }
    return payload


def _compact_sync_conflict(db: VaultDB, row: dict[str, Any]) -> dict[str, Any]:
    candidate = db.get_memory_candidate(str(row.get("candidate_id") or "")) if row.get("candidate_id") else None
    knowledge = db.get_knowledge(int(row["knowledge_id"])) if row.get("knowledge_id") is not None else None
    knowledge_item = compact_knowledge(knowledge) if knowledge else None
    if knowledge_item is not None:
        knowledge_item["content"] = str((knowledge or {}).get("content_raw") or "")
    return {
        "id": row.get("id", ""),
        "status": row.get("status", ""),
        "conflict_type": row.get("conflict_type", ""),
        "reason": row.get("reason", ""),
        "knowledge": knowledge_item,
        "candidate": compact_candidate(candidate, include_content=True, include_gates=True) if candidate else None,
        "confirmation": {
            "keep_local": confirmation_token(str(row.get("id") or ""), "keep_local"),
            "accept_remote": confirmation_token(str(row.get("id") or ""), "accept_remote"),
            "manual": confirmation_token(str(row.get("id") or ""), "manual"),
        },
        "safety": {
            "candidate_first": True,
            "accept_remote_archives_local": True,
            "requires_confirmation": True,
        },
    }


def gui_sync_conflict(project_dir: str | Path, conflict_id: str) -> dict[str, Any]:
    """Return one sync conflict with enough context for a human decision."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    cid = str(conflict_id or "").strip()
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing"}
    if not cid:
        return {"status": "error", "error": "invalid_conflict_id"}
    with VaultDB(db_path) as db:
        row = db.conn.execute("SELECT * FROM memory_conflicts WHERE id=?", (cid,)).fetchone()
        if not row:
            return {"status": "error", "error": "not_found", "conflict_id": cid}
        return {"status": "ok", "conflict": _compact_sync_conflict(db, dict(row))}


def gui_resolve_sync_conflict(
    project_dir: str | Path,
    conflict_id: str,
    *,
    resolution: str,
    reason: str = "",
    agent_id: str = "gui-reviewer",
    confirm: str = "",
) -> dict[str, Any]:
    """Resolve a sync conflict from the local GUI with explicit confirmation."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    cid = str(conflict_id or "").strip()
    resolution_i = str(resolution or "").strip().lower()
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing"}
    if resolution_i not in {"keep_local", "accept_remote", "manual"}:
        return {"status": "error", "error": "invalid_resolution"}
    if not cid or str(confirm or "") != confirmation_token(cid, resolution_i):
        return {"status": "error", "error": "confirmation_required"}
    with VaultDB(db_path) as db:
        row = resolve_conflict(
            db,
            cid,
            resolution=resolution_i,
            reason=reason,
            actor_agent=agent_id,
            apply_memory_change=resolution_i == "accept_remote",
            project_dir=project,
        )
    return {"status": "ok", "resolution": resolution_i, "conflict": dict(row)}


def gui_overview(project_dir: str | Path, *, limit: int = 5, language: str = "en") -> dict[str, Any]:
    """Return the startup payload shown by the local GUI."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    if not db_path.exists():
        return {
            "status": "blocked",
            "project_dir": str(project),
            "reason": "vault.db missing",
            "stats": {},
            "brief": {},
            "inbox": {},
            "daily_report": {},
            "recent": [],
        }

    with VaultDB(db_path) as db:
        stats = db.stats()
        recent = [
            compact_knowledge(row)
            for row in db.list_knowledge(limit=max(1, min(int(limit or 5), 20)))
        ]
        candidates = [
            compact_candidate(row)
            for row in db.list_memory_candidates(status="candidate", limit=max(1, min(int(limit or 5), 20)))
        ]
        task_rows = list_tasks(db, status="active", limit=max(1, min(int(limit or 5), 20)))
    brief = automation_brief(project, limit=limit, review_limit=limit)
    review = automation_review_summary(project, limit=limit, precomputed_brief=brief)
    inbox = automation_inbox(project, limit=limit, include_content=False)
    daily_report = build_daily_report(
        project,
        limit=limit,
        language=language,
        precomputed_brief=brief,
        precomputed_review=review,
    )
    dashboard = gui_agent_dashboard(
        project,
        limit=limit,
        language=language,
        precomputed_brief=brief,
        precomputed_review=review,
        precomputed_candidates=candidates,
    )
    return {
        "status": "ok",
        "project_dir": str(project),
        "stats": stats,
        "agent_dashboard": dashboard,
        "review_inbox": dashboard.get("human_review", {}).get("unified_inbox", {}),
        "brief": compact_brief(brief),
        "inbox": compact_inbox(inbox),
        "daily_report": daily_report,
        "tasks": [compact_task(row) for row in task_rows],
        "candidates": candidates,
        "recent": recent,
    }


def gui_daily_report(project_dir: str | Path, *, limit: int = 5, language: str = "en") -> dict[str, Any]:
    """Return the consumer-facing daily report for the local GUI."""
    return build_daily_report(project_dir, limit=limit, language=language)


def gui_tasks(project_dir: str | Path, *, status: str = "active", limit: int = 20) -> dict[str, Any]:
    """Return compact Task Ledger rows for the local GUI."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    limit_i = normalize_search_limit(limit, default=20, maximum=100)
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing", "tasks": []}
    if limit_i <= 0:
        return {"status": "ok", "task_status": status or "active", "tasks": []}
    with VaultDB(db_path) as db:
        rows = list_tasks(db, status=status or "active", limit=limit_i)
    return {
        "status": "ok",
        "task_status": status or "active",
        "tasks": [compact_task(row) for row in rows],
    }


def gui_task(project_dir: str | Path, task_id: str) -> dict[str, Any]:
    """Return one Task Ledger item plus compact handoff Markdown."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    tid = str(task_id or "").strip()
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing"}
    if not tid:
        return {"status": "error", "error": "invalid_task_id"}
    with VaultDB(db_path) as db:
        task = get_task(db, tid, include_events=True)
        if not task:
            return {"status": "error", "error": "not_found", "task_id": tid}
        handoff = task_handoff(db, tid)
        pending_handoffs = [
            _compact_handoff(row)
            for row in list_task_handoffs(db, status="pending", limit=20)
            if str(row.get("task_id") or "") == tid
        ]
    return {
        "status": "ok",
        "task": compact_task(task),
        "markdown": handoff.get("markdown", ""),
        "pending_handoffs": pending_handoffs,
    }


def gui_claim_task_handoff(
    project_dir: str | Path,
    handoff_id: str,
    *,
    agent_id: str = "gui-reviewer",
    note: str = "",
    confirm: str = "",
) -> dict[str, Any]:
    """Claim one directed Task Ledger handoff from the GUI."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    hid = str(handoff_id or "").strip()
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing"}
    if not hid:
        return {"status": "error", "error": "invalid_handoff_id"}
    required = confirmation_token(hid, "claim")
    if str(confirm or "") != required:
        return {"status": "error", "error": "confirmation_required", "confirmation": required}
    try:
        with VaultDB(db_path) as db:
            handoff = get_task_handoff(db, hid) or {}
            agent = str(agent_id or "").strip()
            if not agent or agent == "gui-reviewer":
                agent = str(handoff.get("to_agent") or handoff.get("owner_agent") or "gui-reviewer")
            result = claim_task_handoff(db, hid, agent_id=agent, note=note)
    except (KeyError, PermissionError, ValueError) as exc:
        return {"status": "error", "error": str(exc)}
    return {"status": "ok", "handoff": _compact_handoff(result.get("handoff") or {})}


def gui_documents(
    project_dir: str | Path,
    *,
    query: str = "",
    layer: str = "",
    category: str = "",
    scope: str = "",
    sensitivity: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """Return a compact, filterable active-memory document list for the GUI."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    limit_i = normalize_search_limit(limit, default=50, maximum=100)
    if not db_path.exists():
        return {
            "status": "blocked",
            "reason": "vault.db missing",
            "documents": [],
            "filters": {},
            "facets": {},
        }
    if limit_i <= 0:
        return {
            "status": "ok",
            "documents": [],
            "filters": {},
            "facets": {},
        }

    layer_i = _clean_filter(layer)
    category_i = _clean_filter(category)
    scope_i = _clean_filter(scope)
    sensitivity_i = _clean_filter(sensitivity)
    query_i = str(query or "").strip()

    where = ["COALESCE(status, 'active') != 'archived'"]
    params: list[Any] = []
    if layer_i:
        where.append("layer=?")
        params.append(layer_i)
    if category_i:
        where.append("category=?")
        params.append(category_i)
    if scope_i:
        where.append("COALESCE(scope, 'project')=?")
        params.append(scope_i)
    if sensitivity_i:
        where.append("COALESCE(sensitivity, 'low')=?")
        params.append(sensitivity_i)
    if query_i:
        pattern = f"%{escape_like_pattern(query_i)}%"
        where.append(
            """(
                title LIKE ? ESCAPE '\\'
                OR summary LIKE ? ESCAPE '\\'
                OR tags LIKE ? ESCAPE '\\'
                OR category LIKE ? ESCAPE '\\'
                OR source LIKE ? ESCAPE '\\'
            )"""
        )
        params.extend([pattern, pattern, pattern, pattern, pattern])

    with VaultDB(db_path) as db:
        rows = db.conn.execute(
            f"""SELECT id, title, category, layer, trust, summary, tags, source,
                       scope, sensitivity, owner_agent, memory_type,
                       valid_from, valid_until, expires_at, updated_at
                FROM knowledge
                WHERE {' AND '.join(where)}
                ORDER BY updated_at DESC, trust DESC, id DESC
                LIMIT ?""",
            [*params, limit_i],
        ).fetchall()
        facets = {
            "layers": _facet_counts(db, "layers"),
            "categories": _facet_counts(db, "categories"),
            "scopes": _facet_counts(db, "scopes"),
            "sensitivities": _facet_counts(db, "sensitivities"),
        }

    return {
        "status": "ok",
        "documents": [compact_knowledge(dict(row)) for row in rows],
        "filters": {
            "query": query_i,
            "layer": layer_i,
            "category": category_i,
            "scope": scope_i,
            "sensitivity": sensitivity_i,
            "limit": limit_i,
        },
        "facets": facets,
    }


def _facet_counts(db: VaultDB, facet: str) -> list[dict[str, Any]]:
    expression = _FACET_EXPRESSIONS[facet]
    rows = db.conn.execute(
        f"""SELECT {expression} AS value, COUNT(*) AS count
            FROM knowledge
            WHERE COALESCE(status, 'active') != 'archived'
            GROUP BY value
            ORDER BY count DESC, value ASC
            LIMIT 50"""
    ).fetchall()
    return [
        {"value": row["value"] or "", "count": row["count"]}
        for row in rows
        if row["value"] not in (None, "")
    ]


def gui_search(
    project_dir: str | Path,
    query: str,
    *,
    mode: str = "keyword",
    limit: int = 10,
) -> dict[str, Any]:
    """Run a local read-only search for the GUI."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    limit_i = normalize_search_limit(limit, default=10, maximum=50)
    if not query.strip() or limit_i <= 0:
        return {"status": "ok", "query": query, "results": []}
    if mode not in {"auto", "keyword", "semantic", "hybrid", "vector"}:
        mode = "keyword"
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing", "query": query, "results": []}

    with VaultDB(db_path) as db:
        search = VaultSearch(db, embed_provider=None, embed_provider_name="none")
        rows = search.search(
            query,
            mode=mode,
            limit=limit_i,
            use_rerank=False,
            compact=False,
            include_snippet=True,
            fields=[
                "id",
                "title",
                "category",
                "layer",
                "trust",
                "summary",
                "tags",
                "source",
                "scope",
                "sensitivity",
                "owner_agent",
                "memory_type",
                "valid_from",
                "valid_until",
                "expires_at",
                "line_start",
                "line_end",
                "best_span",
                "recommended_next_tool",
                "_score",
                "_snippet",
            ],
        )
    return {"status": "ok", "query": query, "mode": mode, "results": [compact_knowledge(r) for r in rows]}


def gui_entry(project_dir: str | Path, knowledge_id: int) -> dict[str, Any]:
    """Return metadata, map nodes, claims, and graph summary for one entry."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing"}
    try:
        kid = int(knowledge_id)
    except (TypeError, ValueError):
        return {"status": "error", "error": "invalid_knowledge_id"}
    if kid <= 0:
        return {"status": "error", "error": "invalid_knowledge_id"}

    with VaultDB(db_path) as db:
        row = db.get_knowledge(kid)
        if not row:
            return {"status": "error", "error": "not_found", "knowledge_id": kid}
        nodes = [
            dict(r)
            for r in db.conn.execute(
                """SELECT node_uid, heading, level, path, summary, line_start, line_end
                   FROM knowledge_nodes
                   WHERE knowledge_id=?
                   ORDER BY line_start, level, id""",
                (kid,),
            ).fetchall()
        ]
        claims = [
            dict(r)
            for r in db.conn.execute(
                """SELECT claim, node_uid, line_start, line_end, confidence, source
                   FROM knowledge_claims
                   WHERE knowledge_id=?
                   ORDER BY line_start, id
                   LIMIT 20""",
                (kid,),
            ).fetchall()
        ]
        edges = graph_edges_for_entry(db, kid)
    return {
        "status": "ok",
        "entry": compact_knowledge(row),
        "nodes": nodes,
        "claims": claims,
        "graph": edges,
        "timeline": timeline_for(row),
        "governance": governance_for(row),
        "usage": usage_for(row),
    }


def gui_read_range(
    project_dir: str | Path,
    knowledge_id: int,
    *,
    line_start: int = 1,
    line_end: int = 40,
    max_lines: int = 80,
) -> dict[str, Any]:
    """Return a bounded source range for the GUI evidence reader."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing"}
    try:
        kid = int(knowledge_id)
        start = int(line_start)
        end = int(line_end)
        max_lines_i = max(1, min(int(max_lines), 200))
    except (TypeError, ValueError):
        return {"status": "error", "error": "invalid_range"}
    if kid <= 0:
        return {"status": "error", "error": "invalid_knowledge_id"}

    with VaultDB(db_path) as db:
        row = db.get_knowledge(kid)
        if not row:
            return {"status": "error", "error": "not_found", "knowledge_id": kid}
        lines = (row.get("content_raw") or "").splitlines()
    if not lines:
        return {"status": "ok", "knowledge_id": kid, "title": row.get("title", ""), "lines": []}

    total = len(lines)
    start = min(max(1, start), total)
    end = min(max(start, end), total)
    if end - start + 1 > max_lines_i:
        end = start + max_lines_i - 1
    payload_lines = [
        {"line": number, "text": lines[number - 1]}
        for number in range(start, end + 1)
    ]
    return {
        "status": "ok",
        "knowledge_id": kid,
        "title": row.get("title", ""),
        "line_start": start,
        "line_end": end,
        "citation": f"#{kid} {row.get('title', '')} L{start}-L{end}",
        "lines": payload_lines,
    }


def gui_candidates(project_dir: str | Path, *, status: str = "candidate", limit: int = 20) -> dict[str, Any]:
    """Return reviewable memory candidates without full content."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    limit_i = max(1, min(int(limit or 20), 50))
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing", "candidates": []}
    status_filter = None if status == "all" else (status or "candidate")
    with VaultDB(db_path) as db:
        rows = db.list_memory_candidates(status=status_filter, limit=limit_i)
    return {
        "status": "ok",
        "candidate_status": status_filter or "all",
        "candidates": [compact_candidate(row) for row in rows],
    }


def gui_candidate(project_dir: str | Path, candidate_id: str) -> dict[str, Any]:
    """Return one memory candidate with content and gate details for review."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    cid = str(candidate_id or "").strip()
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing"}
    if not cid:
        return {"status": "error", "error": "invalid_candidate_id"}
    with VaultDB(db_path) as db:
        row = db.get_memory_candidate(cid)
    if not row:
        return {"status": "error", "error": "not_found", "candidate_id": cid}
    return {
        "status": "ok",
        "candidate": compact_candidate(row, include_content=True, include_gates=True),
        "confirmation": {
            "promote": confirmation_token(cid, "promote"),
            "reject": confirmation_token(cid, "reject"),
            "block": confirmation_token(cid, "block"),
        },
    }


def gui_review_candidate(
    project_dir: str | Path,
    candidate_id: str,
    *,
    action: str,
    reason: str = "",
    confirm: str = "",
) -> dict[str, Any]:
    """Apply an explicit review action to a candidate."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    cid = str(candidate_id or "").strip()
    action_i = str(action or "").strip().lower()
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing"}
    if action_i not in {"promote", "reject", "block"}:
        return {"status": "error", "error": "invalid_action"}
    expected = confirmation_token(cid, action_i)
    if not cid or str(confirm or "") != expected:
        return {
            "status": "error",
            "error": "confirmation_required",
        }

    with VaultDB(db_path) as db:
        if action_i == "promote":
            payload = promote_candidate(db, cid, confirm=True, project_dir=project)
        else:
            outcome = "rejected" if action_i == "reject" else "blocked"
            payload = review_candidate(
                db,
                cid,
                outcome=outcome,
                reason=reason or f"GUI review marked candidate {outcome}",
            )
    return {"status": "ok", "action": action_i, "result": compact_review_result(payload)}
