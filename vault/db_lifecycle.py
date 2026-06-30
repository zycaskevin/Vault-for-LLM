"""Memory usage, archive, and cold-store helpers for VaultDB."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import re
import sqlite3
from typing import Any

from .importance import compute_memory_importance

UpdateKnowledge = Callable[..., bool]


def parse_timestamp(value: str) -> datetime | None:
    """Parse ISO-like timestamps stored in governance metadata."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.fromisoformat(f"{text}T00:00:00+00:00")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_now(value: str | datetime | None) -> tuple[datetime, str]:
    if isinstance(value, datetime):
        now_dt = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return now_dt, now_dt.isoformat()
    if value:
        parsed = parse_timestamp(str(value))
        now_dt = parsed or datetime.now(timezone.utc)
        return now_dt, now_dt.isoformat()
    now_dt = datetime.now(timezone.utc)
    return now_dt, now_dt.isoformat()


def record_knowledge_access(
    conn: sqlite3.Connection,
    knowledge_ids: list[int] | tuple[int, ...] | set[int],
    *,
    cited: bool = False,
    accessed_at: str | None = None,
) -> int:
    """Record retrieval/citation usage counters for active knowledge rows."""
    ids = sorted({int(kid) for kid in knowledge_ids if kid})
    if not ids:
        return 0
    now = accessed_at or datetime.now(timezone.utc).isoformat()
    placeholders = ",".join("?" for _ in ids)
    citation_sql = ", citation_count = citation_count + 1" if cited else ""
    cur = conn.execute(
        f"""UPDATE knowledge
               SET access_count = access_count + 1,
                   last_accessed_at = ?
                   {citation_sql}
             WHERE id IN ({placeholders})
               AND COALESCE(status, 'active') != 'archived'""",
        [now, *ids],
    )
    conn.commit()
    return int(cur.rowcount or 0)


def top_used_knowledge(conn: sqlite3.Connection, limit: int = 10, *, include_archived: bool = False) -> list[dict]:
    """Return the most frequently retrieved memories."""
    limit_i = max(1, min(int(limit or 10), 1000))
    where = ""
    if not include_archived:
        where = "WHERE COALESCE(status, 'active') != 'archived'"
    rows = conn.execute(
        f"""SELECT id, title, layer, category, trust, freshness,
                   scope, sensitivity, memory_type, expires_at, status,
                   access_count, citation_count, last_accessed_at, updated_at
              FROM knowledge
              {where}
             ORDER BY access_count DESC, citation_count DESC, last_accessed_at DESC, updated_at DESC
             LIMIT ?""",
        (limit_i,),
    ).fetchall()
    return [dict(row) for row in rows]


def usage_stats(conn: sqlite3.Connection, limit: int = 10) -> dict:
    """Return memory usage and lifecycle counters for operators/agents."""
    now = datetime.now(timezone.utc)
    rows = conn.execute(
        """SELECT status, expires_at, access_count, citation_count
             FROM knowledge"""
    ).fetchall()
    status_counts: dict[str, int] = {}
    expired_active = 0
    total_accesses = 0
    total_citations = 0
    for row in rows:
        status = str(row["status"] or "active")
        status_counts[status] = status_counts.get(status, 0) + 1
        total_accesses += int(row["access_count"] or 0)
        total_citations += int(row["citation_count"] or 0)
        expires_at = parse_timestamp(row["expires_at"])
        if status != "archived" and expires_at is not None and expires_at <= now:
            expired_active += 1
    return {
        "knowledge_count": len(rows),
        "status_counts": status_counts,
        "expired_active_count": expired_active,
        "total_accesses": total_accesses,
        "total_citations": total_citations,
        "top_used": top_used_knowledge(conn, limit=limit),
    }


def archive_expired_knowledge(
    conn: sqlite3.Connection,
    *,
    now: str | datetime | None = None,
    limit: int = 100,
    dry_run: bool = False,
    skip_used: bool = False,
    protected_scopes: list[str] | tuple[str, ...] | None = None,
    protected_sensitivities: list[str] | tuple[str, ...] | None = None,
) -> dict:
    """Archive active memories whose `expires_at` timestamp is in the past."""
    now_dt, now_text = normalize_now(now)
    limit_i = max(1, min(int(limit or 100), 10000))
    rows = conn.execute(
        """SELECT id, title, layer, category, trust, freshness,
                  memory_type, scope, sensitivity, status, expires_at,
                  access_count, citation_count, last_accessed_at
             FROM knowledge
            WHERE COALESCE(status, 'active') != 'archived'
              AND COALESCE(expires_at, '') != ''
            ORDER BY expires_at ASC, id ASC
            LIMIT ?""",
        (limit_i,),
    ).fetchall()
    expired = []
    for row in rows:
        expires_at = parse_timestamp(row["expires_at"])
        if expires_at is not None and expires_at <= now_dt:
            expired.append(dict(row))
    protected_scope_set = {str(value).strip().lower() for value in (protected_scopes or []) if str(value).strip()}
    protected_sensitivity_set = {
        str(value).strip().lower() for value in (protected_sensitivities or []) if str(value).strip()
    }
    skipped_used = []
    skipped_protected = []
    archiveable = []
    for row in expired:
        scope = str(row.get("scope") or "").strip().lower()
        sensitivity = str(row.get("sensitivity") or "").strip().lower()
        if scope in protected_scope_set or sensitivity in protected_sensitivity_set:
            skipped_protected.append(row)
            continue
        usage_count = int(row.get("access_count") or 0) + int(row.get("citation_count") or 0)
        if skip_used and usage_count > 0:
            skipped_used.append(row)
        else:
            archiveable.append(row)

    if dry_run or not archiveable:
        return {
            "action": "archive-expired",
            "dry_run": bool(dry_run),
            "archived_count": 0,
            "eligible_count": len(expired),
            "skipped_used_count": len(skipped_used),
            "skipped_protected_count": len(skipped_protected),
            "now": now_text,
            "items": archiveable,
            "skipped_used": skipped_used,
            "skipped_protected": skipped_protected,
        }

    ids = [int(row["id"]) for row in archiveable]
    placeholders = ",".join("?" for _ in ids)
    conn.execute(
        f"""UPDATE knowledge
               SET status='archived',
                   archived_at=?,
                   updated_at=?
             WHERE id IN ({placeholders})""",
        [now_text, now_text, *ids],
    )
    conn.commit()
    return {
        "action": "archive-expired",
        "dry_run": False,
        "archived_count": len(ids),
        "eligible_count": len(expired),
        "skipped_used_count": len(skipped_used),
        "skipped_protected_count": len(skipped_protected),
        "now": now_text,
        "items": archiveable,
        "skipped_used": skipped_used,
        "skipped_protected": skipped_protected,
    }


def cold_store_expired_knowledge(
    conn: sqlite3.Connection,
    *,
    update_knowledge: UpdateKnowledge,
    now: str | datetime | None = None,
    limit: int = 100,
    dry_run: bool = True,
    min_usage: int = 1,
    summary_max_chars: int = 360,
    protected_scopes: list[str] | tuple[str, ...] | None = None,
    protected_sensitivities: list[str] | tuple[str, ...] | None = None,
    protected_layers: list[str] | tuple[str, ...] | None = None,
    target_layer: str = "L3",
) -> dict:
    """Summarize and archive expired-but-used memories into cold storage."""
    now_dt, now_text = normalize_now(now)
    limit_i = max(1, min(int(limit or 100), 10000))
    min_usage_i = max(1, int(min_usage or 1))
    summary_chars = max(80, min(int(summary_max_chars or 360), 2000))
    target_layer_text = str(target_layer or "L3").strip() or "L3"
    protected_scope_set = {str(value).strip().lower() for value in (protected_scopes or ["private"]) if str(value).strip()}
    protected_sensitivity_set = {
        str(value).strip().lower()
        for value in (protected_sensitivities or ["high", "restricted"])
        if str(value).strip()
    }
    protected_layer_set = {str(value).strip().upper() for value in (protected_layers or ["L0", "L1"]) if str(value).strip()}

    rows = conn.execute(
        """SELECT id, title, layer, category, tags, trust, freshness,
                  content_raw, summary, last_accessed_at,
                  memory_type, scope, sensitivity, status, expires_at,
                  access_count, citation_count
             FROM knowledge
            WHERE COALESCE(status, 'active') != 'archived'
              AND COALESCE(expires_at, '') != ''
            ORDER BY expires_at ASC, id ASC
            LIMIT ?""",
        (limit_i,),
    ).fetchall()

    candidates: list[dict[str, Any]] = []
    skipped_low_usage: list[dict[str, Any]] = []
    skipped_protected: list[dict[str, Any]] = []
    for row_obj in rows:
        row = dict(row_obj)
        expires_at = parse_timestamp(row["expires_at"])
        if expires_at is None or expires_at > now_dt:
            continue
        usage_count = int(row.get("access_count") or 0) + int(row.get("citation_count") or 0)
        compact = cold_store_preview_row(
            row,
            now_text=now_text,
            summary_max_chars=summary_chars,
            target_layer=target_layer_text,
        )
        if str(row.get("layer") or "").strip().upper() in protected_layer_set:
            compact["skip_reason"] = "protected_layer"
            skipped_protected.append(compact)
            continue
        if str(row.get("scope") or "").strip().lower() in protected_scope_set:
            compact["skip_reason"] = "protected_scope"
            skipped_protected.append(compact)
            continue
        if str(row.get("sensitivity") or "").strip().lower() in protected_sensitivity_set:
            compact["skip_reason"] = "protected_sensitivity"
            skipped_protected.append(compact)
            continue
        if usage_count < min_usage_i:
            compact["skip_reason"] = "usage_below_threshold"
            skipped_low_usage.append(compact)
            continue
        candidates.append(compact)
    candidates.sort(
        key=lambda item: (
            float(item.get("importance_score") or 0.0),
            int(item.get("citation_count") or 0),
            int(item.get("access_count") or 0),
            int(item.get("id") or 0),
        ),
        reverse=True,
    )
    skipped_low_usage.sort(key=lambda item: (float(item.get("importance_score") or 0.0), int(item.get("id") or 0)), reverse=True)
    skipped_protected.sort(key=lambda item: (float(item.get("importance_score") or 0.0), int(item.get("id") or 0)), reverse=True)

    if dry_run or not candidates:
        return {
            "action": "cold-store-expired",
            "dry_run": bool(dry_run),
            "applied_count": 0,
            "eligible_count": len(candidates),
            "skipped_low_usage_count": len(skipped_low_usage),
            "skipped_protected_count": len(skipped_protected),
            "min_usage": min_usage_i,
            "target_layer": target_layer_text,
            "now": now_text,
            "items": candidates,
            "skipped_low_usage": skipped_low_usage,
            "skipped_protected": skipped_protected,
            "safety": cold_store_safety(),
        }

    applied = []
    demoted_count = 0
    for item in candidates:
        kid = int(item["id"])
        before_layer = str(item.get("layer") or "")
        after_layer = str(item.get("target_layer") or target_layer_text)
        if before_layer != after_layer:
            demoted_count += 1
        update_knowledge(
            kid,
            status="archived",
            archived_at=now_text,
            summary=item["summary"],
            summary_generated_at=now_text,
            layer=after_layer,
            freshness=0.0,
        )
        applied.append({**item, "status_after": "archived"})

    return {
        "action": "cold-store-expired",
        "dry_run": False,
        "applied_count": len(applied),
        "summary_count": len(applied),
        "demoted_count": demoted_count,
        "eligible_count": len(candidates),
        "skipped_low_usage_count": len(skipped_low_usage),
        "skipped_protected_count": len(skipped_protected),
        "min_usage": min_usage_i,
        "target_layer": target_layer_text,
        "now": now_text,
        "items": applied,
        "skipped_low_usage": skipped_low_usage,
        "skipped_protected": skipped_protected,
        "safety": cold_store_safety(),
    }


def cold_store_preview_row(
    row: dict[str, Any],
    *,
    now_text: str,
    summary_max_chars: int,
    target_layer: str,
) -> dict[str, Any]:
    access = int(row.get("access_count") or 0)
    citations = int(row.get("citation_count") or 0)
    importance = compute_memory_importance(row, now=parse_timestamp(now_text) or datetime.now(timezone.utc))
    summary = build_cold_store_summary(row, max_chars=summary_max_chars, now_text=now_text)
    return {
        "id": int(row.get("id") or 0),
        "title": row.get("title", ""),
        "layer": row.get("layer", ""),
        "target_layer": target_layer,
        "category": row.get("category", ""),
        "memory_type": row.get("memory_type", ""),
        "scope": row.get("scope", ""),
        "sensitivity": row.get("sensitivity", ""),
        "expires_at": row.get("expires_at", ""),
        "access_count": access,
        "citation_count": citations,
        "usage_count": access + citations,
        "importance_score": importance["importance_score"],
        "weight_tier": importance["weight_tier"],
        "lifecycle_action": importance["lifecycle_action"],
        "importance_components": importance["importance_components"],
        "importance_signals": importance["signals"],
        "importance_recommendation": importance["recommendation"],
        "summary": summary,
        "operation": "summarize_then_cold_store",
        "lifecycle_strategy": _cold_store_lifecycle_strategy(row, importance, target_layer=target_layer),
    }


def build_cold_store_summary(row: dict[str, Any], *, max_chars: int, now_text: str) -> str:
    title = str(row.get("title") or "").strip()
    existing = str(row.get("summary") or "").strip()
    content = existing or str(row.get("content_raw") or "").strip()
    content = re.sub(r"\s+", " ", content)
    try:
        from .privacy import redact_secrets

        content = redact_secrets(content)
        title = redact_secrets(title)
    except Exception:
        pass
    if len(content) > max_chars:
        content = content[: max_chars - 1].rstrip() + "…"
    access = int(row.get("access_count") or 0)
    citations = int(row.get("citation_count") or 0)
    prefix = f"Cold-store summary for '{title}'"
    return (
        f"{prefix}: {content} "
        f"(archived_at={now_text}; previous_usage access={access}, citations={citations}; "
        "original content retained in vault.db for audit/restore)."
    )


def cold_store_safety() -> dict[str, bool]:
    return {
        "hard_delete": False,
        "original_content_retained": True,
        "normal_recall_removed": True,
        "summary_written": True,
        "protected_private_high_restricted_skipped": True,
    }


def _cold_store_lifecycle_strategy(row: dict[str, Any], importance: dict[str, Any], *, target_layer: str) -> dict[str, Any]:
    before_layer = str(row.get("layer") or "")
    action = str(importance.get("lifecycle_action") or "")
    demote = bool(before_layer and target_layer and before_layer != target_layer)
    if action in {"refresh_or_summarize_before_cold_store", "protect_and_refresh"}:
        review = "refresh_source_or_write_summary_candidate"
    elif action == "review_ttl_before_expiry":
        review = "extend_ttl_or_mark_superseded"
    else:
        review = "spot_check_summary_after_cold_store"
    return {
        "strategy": "compress_demote_archive",
        "compress": True,
        "demote_layer": demote,
        "from_layer": before_layer,
        "to_layer": target_layer,
        "archive_from_daily_recall": True,
        "retain_original_for_audit": True,
        "review_action": review,
        "weight_tier": importance.get("weight_tier", "cold"),
        "lifecycle_action": action,
    }
