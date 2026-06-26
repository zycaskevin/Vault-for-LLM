"""Temporal validity helpers for memory facts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .db import VaultDB


def normalize_temporal_metadata(
    *,
    valid_from: str = "",
    valid_until: str = "",
    supersedes_id: int | str | None = None,
) -> dict[str, Any]:
    """Normalize temporal fact-window metadata."""
    return {
        "valid_from": _iso_text(valid_from),
        "valid_until": _iso_text(valid_until),
        "supersedes_id": _positive_int_or_none(supersedes_id),
    }


def temporal_state(
    row: dict[str, Any],
    *,
    as_of: str | None = None,
    superseded_ids: set[int] | None = None,
) -> str:
    """Classify one memory as current, past, future, or timeless."""
    now = _parse_timestamp(as_of) or datetime.now(timezone.utc)
    valid_from = _parse_timestamp(row.get("valid_from"))
    valid_until = _parse_timestamp(row.get("valid_until"))
    row_id = _positive_int_or_none(row.get("id"))
    superseded = bool(row_id and superseded_ids and row_id in superseded_ids)
    if valid_from is None and valid_until is None and not superseded:
        return "timeless"
    if valid_from is not None and valid_from > now:
        return "future"
    if superseded or (valid_until is not None and valid_until <= now):
        return "past"
    return "current"


def temporal_summary(db: "VaultDB", *, as_of: str = "") -> dict[str, Any]:
    """Return counts for current/past/future/timeless memories."""
    counts = {"current": 0, "past": 0, "future": 0, "timeless": 0}
    rows = db.conn.execute(
        """SELECT id, valid_from, valid_until, supersedes_id
           FROM knowledge
           WHERE COALESCE(status, 'active') != 'archived'"""
    ).fetchall()
    superseded_ids = _superseded_ids([dict(row) for row in rows])
    for row in rows:
        counts[temporal_state(dict(row), as_of=as_of, superseded_ids=superseded_ids)] += 1
    return {
        "action": "temporal_status",
        "as_of": as_of or datetime.now(timezone.utc).isoformat(),
        "counts": counts,
        "total": sum(counts.values()),
        "model": {
            "valid_from": "when the fact starts being true",
            "valid_until": "when the fact stops being true",
            "supersedes_id": "older memory id this fact replaces",
        },
    }


def list_temporal_memories(
    db: "VaultDB",
    *,
    state: str = "current",
    as_of: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """List memories matching a temporal state."""
    wanted = str(state or "current").strip().lower()
    if wanted not in {"current", "past", "future", "timeless", "all"}:
        raise ValueError("state must be current, past, future, timeless, or all")
    limit = max(1, min(int(limit or 50), 500))
    rows = db.conn.execute(
        """SELECT id, title, layer, category, memory_type, valid_from, valid_until,
                  supersedes_id, updated_at
           FROM knowledge
           WHERE COALESCE(status, 'active') != 'archived'
           ORDER BY updated_at DESC, id DESC
           LIMIT ?""",
        (limit * 4,),
    ).fetchall()
    superseded_ids = _superseded_ids([dict(row) for row in rows])
    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["temporal_state"] = temporal_state(item, as_of=as_of, superseded_ids=superseded_ids)
        if wanted == "all" or item["temporal_state"] == wanted:
            items.append(item)
        if len(items) >= limit:
            break
    return {
        "action": "temporal_list",
        "state": wanted,
        "as_of": as_of or datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "items": items,
    }


def annotate_temporal_rows(
    rows: list[dict[str, Any]],
    *,
    as_of: str = "",
) -> list[dict[str, Any]]:
    """Attach ``temporal_state`` to search/result rows without mutating input rows."""
    if not rows:
        return []
    copied = [dict(row) for row in rows]
    superseded_ids = _superseded_ids(copied)
    for row in copied:
        row["temporal_state"] = temporal_state(row, as_of=as_of, superseded_ids=superseded_ids)
    return copied


def filter_temporal_rows(
    rows: list[dict[str, Any]],
    *,
    include_expired: bool = True,
    include_future: bool = True,
    as_of: str = "",
) -> list[dict[str, Any]]:
    """Filter annotated rows by temporal fact-window state.

    ``include_expired=True`` preserves legacy recall. Callers that want current
    facts only can set it to false while keeping past facts auditable through
    ``vault memory temporal list``.
    """
    annotated = annotate_temporal_rows(rows, as_of=as_of)
    out: list[dict[str, Any]] = []
    for row in annotated:
        state = row.get("temporal_state")
        if state == "past" and not include_expired:
            continue
        if state == "future" and not include_future:
            continue
        out.append(row)
    return out


def _iso_text(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value or "").strip()


def _parse_timestamp(value: Any) -> datetime | None:
    text = _iso_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _superseded_ids(rows: list[dict[str, Any]]) -> set[int]:
    return {
        number
        for row in rows
        for number in [_positive_int_or_none(row.get("supersedes_id"))]
        if number is not None
    }


def _positive_int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
