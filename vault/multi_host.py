"""Local revision graph, conflict preview, and audit helpers."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
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


def resolve_conflict(
    db: VaultDB,
    conflict_id: str,
    *,
    resolution: str,
    reason: str = "",
    actor_agent: str = "",
) -> dict[str, Any]:
    if resolution not in {"keep_local", "accept_remote", "manual"}:
        raise ValueError("resolution must be keep_local, accept_remote, or manual")
    row = db.conn.execute("SELECT * FROM memory_conflicts WHERE id=?", (conflict_id,)).fetchone()
    if not row:
        raise KeyError(f"conflict not found: {conflict_id}")
    now = utc_now()
    payload = {
        "resolution": resolution,
        "reason": reason,
        "actor_agent": actor_agent,
        "resolved_at": now,
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
        revision_id=str(row["right_revision_id"] or row["left_revision_id"] or ""),
        payload=payload,
    )
    return dict(db.conn.execute("SELECT * FROM memory_conflicts WHERE id=?", (conflict_id,)).fetchone())
