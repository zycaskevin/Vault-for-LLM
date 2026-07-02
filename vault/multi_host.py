"""Local revision graph, conflict preview, and audit helpers."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path
from typing import Any

from .db import VaultDB
from .memory import normalize_text


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_digest(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def record_audit_event(
    db: VaultDB,
    *,
    actor_agent: str = "",
    action: str,
    target_type: str = "",
    target_id: str = "",
    revision_id: str = "",
    payload: dict[str, Any] | None = None,
) -> int:
    now = utc_now()
    cursor = db.conn.execute(
        """INSERT INTO memory_audit_log
           (created_at, actor_agent, action, target_type, target_id, revision_id, payload_json)
           VALUES(?,?,?,?,?,?,?)""",
        (
            now,
            actor_agent or "",
            action,
            target_type,
            str(target_id or ""),
            revision_id or "",
            json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
        ),
    )
    db.conn.commit()
    return int(cursor.lastrowid)


def record_memory_revision(
    db: VaultDB,
    *,
    title: str,
    content: str,
    operation: str,
    status: str,
    knowledge_id: int | None = None,
    candidate_id: str = "",
    remote_request_id: str = "",
    parent_revision_id: str = "",
    source_agent: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = utc_now()
    revision_id = f"rev_{uuid.uuid4().hex[:16]}"
    content_hash = content_digest(content)
    revision_hash = hashlib.sha256(
        json.dumps(
            {
                "knowledge_id": knowledge_id,
                "candidate_id": candidate_id,
                "remote_request_id": remote_request_id,
                "parent_revision_id": parent_revision_id,
                "title": title,
                "content_hash": content_hash,
                "operation": operation,
                "status": status,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    db.conn.execute(
        """INSERT INTO memory_revisions
           (id, created_at, knowledge_id, candidate_id, remote_request_id,
            parent_revision_id, revision_hash, content_hash, title, source_agent,
            operation, status, payload_json)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            revision_id,
            now,
            knowledge_id,
            candidate_id or "",
            remote_request_id or "",
            parent_revision_id or "",
            revision_hash,
            content_hash,
            title or "",
            source_agent or "",
            operation or "",
            status or "",
            json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
        ),
    )
    db.conn.commit()
    record_audit_event(
        db,
        actor_agent=source_agent,
        action=f"revision:{operation}",
        target_type="knowledge" if knowledge_id else "candidate",
        target_id=str(knowledge_id or candidate_id or remote_request_id),
        revision_id=revision_id,
        payload={"status": status, "remote_request_id": remote_request_id},
    )
    return {
        "revision_id": revision_id,
        "revision_hash": revision_hash,
        "content_hash": content_hash,
        "created_at": now,
    }


def detect_candidate_conflicts(
    db: VaultDB,
    *,
    candidate_id: str,
    revision_id: str,
) -> list[dict[str, Any]]:
    candidate = db.get_memory_candidate(candidate_id)
    if not candidate:
        return []
    title_key = normalize_text(candidate.get("title", ""))
    candidate_hash = content_digest(candidate.get("content", ""))
    rows = db.conn.execute(
        """SELECT id, title, content_raw
           FROM knowledge
           WHERE status='active'"""
    ).fetchall()
    conflicts: list[dict[str, Any]] = []
    for row in rows:
        if normalize_text(row["title"]) != title_key:
            continue
        active_hash = content_digest(row["content_raw"] or "")
        if active_hash == candidate_hash:
            continue
        conflict = _create_conflict_if_missing(
            db,
            knowledge_id=int(row["id"]),
            candidate_id=candidate_id,
            right_revision_id=revision_id,
            conflict_type="same_title_content_mismatch",
            reason="Remote candidate title matches active knowledge but content differs.",
        )
        conflicts.append(conflict)
    return conflicts


def _create_conflict_if_missing(
    db: VaultDB,
    *,
    knowledge_id: int,
    candidate_id: str,
    right_revision_id: str,
    conflict_type: str,
    reason: str,
) -> dict[str, Any]:
    existing = db.conn.execute(
        """SELECT * FROM memory_conflicts
           WHERE status='open' AND knowledge_id=? AND candidate_id=? AND conflict_type=?
           LIMIT 1""",
        (knowledge_id, candidate_id, conflict_type),
    ).fetchone()
    if existing:
        return dict(existing)
    now = utc_now()
    conflict_id = f"conf_{uuid.uuid4().hex[:16]}"
    db.conn.execute(
        """INSERT INTO memory_conflicts
           (id, created_at, updated_at, status, knowledge_id, left_revision_id,
            right_revision_id, candidate_id, conflict_type, reason, resolution_json)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            conflict_id,
            now,
            now,
            "open",
            knowledge_id,
            "",
            right_revision_id,
            candidate_id,
            conflict_type,
            reason,
            "{}",
        ),
    )
    db.conn.commit()
    record_audit_event(
        db,
        action="conflict:opened",
        target_type="conflict",
        target_id=conflict_id,
        revision_id=right_revision_id,
        payload={"knowledge_id": knowledge_id, "candidate_id": candidate_id, "reason": reason},
    )
    return dict(db.conn.execute("SELECT * FROM memory_conflicts WHERE id=?", (conflict_id,)).fetchone())


def list_revisions(db: VaultDB, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = db.conn.execute(
        """SELECT * FROM memory_revisions
           ORDER BY created_at DESC
           LIMIT ?""",
        (max(1, min(int(limit or 20), 100)),),
    ).fetchall()
    return [dict(row) for row in rows]


def list_conflicts(db: VaultDB, *, status: str = "open", limit: int = 20) -> list[dict[str, Any]]:
    params: list[Any] = []
    query = "SELECT * FROM memory_conflicts"
    if status:
        query += " WHERE status=?"
        params.append(status)
    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(max(1, min(int(limit or 20), 100)))
    return [dict(row) for row in db.conn.execute(query, params).fetchall()]


def list_audit_log(db: VaultDB, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = db.conn.execute(
        """SELECT * FROM memory_audit_log
           ORDER BY id DESC
           LIMIT ?""",
        (max(1, min(int(limit or 20), 100)),),
    ).fetchall()
    return [dict(row) for row in rows]


def preview_conflict(db: VaultDB, conflict_id: str, *, context_lines: int = 2) -> dict[str, Any]:
    """Return a compact, read-only conflict preview for review UIs and agents."""
    row = db.conn.execute("SELECT * FROM memory_conflicts WHERE id=?", (conflict_id,)).fetchone()
    if not row:
        raise KeyError(f"conflict not found: {conflict_id}")
    conflict = dict(row)
    knowledge = db.get_knowledge(int(conflict["knowledge_id"])) if conflict.get("knowledge_id") is not None else None
    candidate = db.get_memory_candidate(str(conflict.get("candidate_id") or "")) if conflict.get("candidate_id") else None
    local_content = str((knowledge or {}).get("content_raw") or "")
    remote_content = str((candidate or {}).get("content") or "")
    local_title = str((knowledge or {}).get("title") or "")
    remote_title = str((candidate or {}).get("title") or "")
    return {
        "ok": True,
        "status": "needs_review" if conflict.get("status") == "open" else str(conflict.get("status") or ""),
        "conflict": _compact_conflict(conflict),
        "local": {
            "type": "active_knowledge",
            "id": conflict.get("knowledge_id"),
            "title": local_title,
            "status": str((knowledge or {}).get("status") or ""),
            "content_hash": content_digest(local_content) if local_content else "",
            "content_preview": _preview_text(local_content),
        },
        "remote": {
            "type": "remote_candidate",
            "id": conflict.get("candidate_id") or "",
            "title": remote_title,
            "status": str((candidate or {}).get("status") or ""),
            "trust": float((candidate or {}).get("trust") or 0.0),
            "scope": str((candidate or {}).get("scope") or ""),
            "sensitivity": str((candidate or {}).get("sensitivity") or ""),
            "source_ref": str((candidate or {}).get("source_ref") or ""),
            "content_hash": content_digest(remote_content) if remote_content else "",
            "content_preview": _preview_text(remote_content),
        },
        "diff": _content_diff(local_content, remote_content, context_lines=context_lines),
        "available_resolutions": [
            {
                "resolution": "keep_local",
                "effect": "Reject the remote candidate and keep active local knowledge unchanged.",
                "requires_apply_memory_change": False,
            },
            {
                "resolution": "manual",
                "effect": "Mark this conflict reviewed after a human or trusted agent writes a separate merged memory.",
                "requires_apply_memory_change": False,
            },
            {
                "resolution": "accept_remote",
                "effect": "Promote the remote candidate and archive the conflicting local knowledge row.",
                "requires_apply_memory_change": True,
            },
        ],
        "recommendation": _conflict_recommendation(conflict, knowledge or {}, candidate or {}),
    }


def sync_status(db: VaultDB, *, limit: int = 5) -> dict[str, Any]:
    """Return a compact, read-only multi-host sync health summary."""
    limit_i = max(1, min(int(limit or 5), 20))
    counts = {
        "revisions": int(db.conn.execute("SELECT COUNT(*) FROM memory_revisions").fetchone()[0]),
        "open_conflicts": int(
            db.conn.execute("SELECT COUNT(*) FROM memory_conflicts WHERE status='open'").fetchone()[0]
        ),
        "resolved_conflicts": int(
            db.conn.execute("SELECT COUNT(*) FROM memory_conflicts WHERE status='resolved'").fetchone()[0]
        ),
        "audit_events": int(db.conn.execute("SELECT COUNT(*) FROM memory_audit_log").fetchone()[0]),
    }
    recent_revisions = list_revisions(db, limit=limit_i)
    open_conflicts = list_conflicts(db, status="open", limit=limit_i)
    audit_events = list_audit_log(db, limit=limit_i)
    if counts["open_conflicts"]:
        status = "needs_review"
        next_action = "Review open conflicts before accepting remote memory changes."
    elif counts["revisions"] or counts["audit_events"]:
        status = "ok"
        next_action = "No open sync conflicts. Continue candidate-first remote sync."
    else:
        status = "idle"
        next_action = "No multi-host sync activity recorded yet."
    return {
        "ok": True,
        "status": status,
        "counts": counts,
        "recent_revisions": recent_revisions,
        "open_conflicts": open_conflicts,
        "audit_events": audit_events,
        "safety": {
            "read_only": True,
            "writes_active_memory": False,
            "multi_master_active_sync": False,
            "candidate_first": True,
        },
        "next_action": next_action,
    }


def _compact_conflict(conflict: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": conflict.get("id", ""),
        "status": conflict.get("status", ""),
        "conflict_type": conflict.get("conflict_type", ""),
        "reason": conflict.get("reason", ""),
        "knowledge_id": conflict.get("knowledge_id"),
        "candidate_id": conflict.get("candidate_id", ""),
        "left_revision_id": conflict.get("left_revision_id", ""),
        "right_revision_id": conflict.get("right_revision_id", ""),
        "created_at": conflict.get("created_at", ""),
        "updated_at": conflict.get("updated_at", ""),
    }


def _preview_text(text: str, *, max_len: int = 600) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3].rstrip() + "..."


def _content_diff(local: str, remote: str, *, context_lines: int = 2, max_lines: int = 80) -> list[str]:
    local_lines = str(local or "").splitlines()
    remote_lines = str(remote or "").splitlines()
    diff = list(
        unified_diff(
            local_lines,
            remote_lines,
            fromfile="local_active",
            tofile="remote_candidate",
            lineterm="",
            n=max(0, min(int(context_lines or 2), 5)),
        )
    )
    return diff[: max(1, min(int(max_lines or 80), 200))]


def _conflict_recommendation(
    conflict: dict[str, Any],
    knowledge: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    trust = float(candidate.get("trust") or 0.0)
    if str(conflict.get("status") or "") != "open":
        return {
            "safe_action": "none",
            "reason": "Conflict is already resolved.",
            "command": "",
        }
    if not candidate:
        return {
            "safe_action": "keep_local",
            "reason": "Remote candidate is missing, so active local knowledge should be preserved.",
            "command": f"vault sync resolve-conflict {conflict.get('id', '')} --resolution keep_local",
        }
    if trust >= 0.85 and str(candidate.get("sensitivity") or "low") == "low":
        return {
            "safe_action": "review_accept_remote",
            "reason": "Remote candidate is low sensitivity and high trust; review the preview before applying.",
            "command": (
                f"vault sync resolve-conflict {conflict.get('id', '')} "
                "--resolution accept_remote --apply-memory-change"
            ),
        }
    if knowledge and candidate:
        return {
            "safe_action": "manual_review",
            "reason": "Both local and remote sides exist. Prefer manual review or a merged candidate.",
            "command": f"vault sync resolve-conflict {conflict.get('id', '')} --resolution manual --reason reviewed",
        }
    return {
        "safe_action": "keep_local",
        "reason": "Default safe action is to keep local active memory until a reviewer decides otherwise.",
        "command": f"vault sync resolve-conflict {conflict.get('id', '')} --resolution keep_local",
    }


def resolve_conflict(
    db: VaultDB,
    conflict_id: str,
    *,
    resolution: str,
    reason: str = "",
    actor_agent: str = "",
    apply_memory_change: bool = False,
    project_dir: str | Path | None = None,
    compile: bool = False,
    build_map: bool = True,
) -> dict[str, Any]:
    if resolution not in {"keep_local", "accept_remote", "manual"}:
        raise ValueError("resolution must be keep_local, accept_remote, or manual")
    row = db.conn.execute("SELECT * FROM memory_conflicts WHERE id=?", (conflict_id,)).fetchone()
    if not row:
        raise KeyError(f"conflict not found: {conflict_id}")
    row_d = dict(row)
    applied_changes = _apply_conflict_resolution(
        db,
        row_d,
        resolution=resolution,
        actor_agent=actor_agent,
        apply_memory_change=apply_memory_change,
        project_dir=project_dir,
        compile=compile,
        build_map=build_map,
    )
    now = utc_now()
    payload = {
        "resolution": resolution,
        "reason": reason,
        "actor_agent": actor_agent,
        "resolved_at": now,
        "memory_change_applied": bool(applied_changes),
        "applied_changes": applied_changes,
    }
    db.conn.execute(
        """UPDATE memory_conflicts
           SET status='resolved', updated_at=?, resolution_json=?
           WHERE id=?""",
        (now, json.dumps(payload, ensure_ascii=False, sort_keys=True), conflict_id),
    )
    db.conn.commit()
    record_audit_event(
        db,
        actor_agent=actor_agent,
        action="conflict:resolved",
        target_type="conflict",
        target_id=conflict_id,
        revision_id=str(row_d.get("right_revision_id") or row_d.get("left_revision_id") or ""),
        payload=payload,
    )
    return dict(db.conn.execute("SELECT * FROM memory_conflicts WHERE id=?", (conflict_id,)).fetchone())


def _apply_conflict_resolution(
    db: VaultDB,
    conflict: dict[str, Any],
    *,
    resolution: str,
    actor_agent: str = "",
    apply_memory_change: bool = False,
    project_dir: str | Path | None = None,
    compile: bool = False,
    build_map: bool = True,
) -> list[dict[str, Any]]:
    """Apply the memory-side effects for a reviewed conflict resolution.

    `manual` intentionally leaves memory untouched. `accept_remote` is guarded
    by `apply_memory_change` because it promotes a remote candidate and archives
    the current local row. This keeps remote writes candidate-first and
    auditable instead of silently overwriting active knowledge.
    """
    candidate_id = str(conflict.get("candidate_id") or "")
    knowledge_id = int(conflict["knowledge_id"]) if conflict.get("knowledge_id") is not None else None
    right_revision_id = str(conflict.get("right_revision_id") or "")
    applied: list[dict[str, Any]] = []

    if resolution == "manual":
        return applied

    if not candidate_id:
        raise ValueError("conflict has no candidate_id to resolve")
    candidate = db.get_memory_candidate(candidate_id)
    if not candidate:
        raise KeyError(f"candidate not found: {candidate_id}")

    if resolution == "keep_local":
        if candidate.get("status") != "promoted":
            db.update_memory_candidate(candidate_id, status="rejected")
            record_memory_revision(
                db,
                title=str(candidate.get("title") or ""),
                content=str(candidate.get("content") or ""),
                operation="remote_candidate_rejected_keep_local",
                status="rejected",
                candidate_id=candidate_id,
                parent_revision_id=right_revision_id,
                source_agent=actor_agent,
                payload={"conflict_id": conflict.get("id"), "resolution": resolution},
            )
            applied.append({"target": "candidate", "id": candidate_id, "action": "rejected"})
        return applied

    if resolution != "accept_remote":
        return applied
    if not apply_memory_change:
        raise ValueError("accept_remote requires apply_memory_change=True")

    from .memory import promote_candidate

    promotion = promote_candidate(
        db,
        candidate_id,
        confirm=True,
        project_dir=project_dir,
        compile=compile,
        build_map=build_map,
    )
    promoted_id = int(promotion.get("knowledge_id") or 0)
    applied.append({"target": "candidate", "id": candidate_id, "action": "promoted", "knowledge_id": promoted_id})

    if knowledge_id and promoted_id and knowledge_id != promoted_id:
        old = db.get_knowledge(knowledge_id)
        if old and str(old.get("status") or "active") != "archived":
            archived_at = utc_now()
            record_memory_revision(
                db,
                title=str(old.get("title") or ""),
                content=str(old.get("content_raw") or ""),
                operation="local_knowledge_archived_for_remote_accept",
                status="archived",
                knowledge_id=knowledge_id,
                parent_revision_id=right_revision_id,
                source_agent=actor_agent,
                payload={
                    "conflict_id": conflict.get("id"),
                    "replacement_knowledge_id": promoted_id,
                    "resolution": resolution,
                },
            )
            db.update_knowledge(knowledge_id, status="archived", archived_at=archived_at)
            record_audit_event(
                db,
                actor_agent=actor_agent,
                action="knowledge:archived_for_remote_accept",
                target_type="knowledge",
                target_id=str(knowledge_id),
                revision_id=right_revision_id,
                payload={"replacement_knowledge_id": promoted_id, "conflict_id": conflict.get("id")},
            )
            applied.append(
                {
                    "target": "knowledge",
                    "id": knowledge_id,
                    "action": "archived",
                    "replacement_knowledge_id": promoted_id,
                }
            )

    if promoted_id:
        record_memory_revision(
            db,
            title=str(candidate.get("title") or ""),
            content=str(candidate.get("content") or ""),
            operation="remote_candidate_promoted_accept_remote",
            status="active",
            knowledge_id=promoted_id,
            candidate_id=candidate_id,
            parent_revision_id=right_revision_id,
            source_agent=actor_agent,
            payload={"conflict_id": conflict.get("id"), "resolution": resolution},
        )
    return applied
