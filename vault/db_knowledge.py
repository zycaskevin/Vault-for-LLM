"""Knowledge CRUD and keyword fallback helpers for VaultDB."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import sqlite3
from typing import Any

from .search_utils import normalize_search_limit

from .governance import normalize_governance_metadata


FtsRowSync = Callable[[int], None]
FtsRowDelete = Callable[[int], None]


def escape_like_pattern(term: str) -> str:
    """Escape LIKE wildcards for literal fallback search."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def add_knowledge(
    conn: sqlite3.Connection,
    *,
    sync_fts_row: FtsRowSync,
    title: str,
    content_raw: str,
    layer: str = "L3",
    category: str = "general",
    tags: str = "",
    trust: float = 0.5,
    source: str = "",
    content_aaak: str = "",
    summary: str = "",
    scope: str = "project",
    sensitivity: str = "low",
    owner_agent: str = "",
    allowed_agents: Any = None,
    memory_type: str = "knowledge",
    expires_at: str = "",
    valid_from: str = "",
    valid_until: str = "",
    supersedes_id: int | str | None = None,
) -> int:
    """Add one knowledge row and return its id."""
    now = datetime.now(timezone.utc).isoformat()
    content_hash = hashlib.sha256(content_raw.encode()).hexdigest()[:16]
    governance = normalize_governance_metadata(
        scope=scope,
        sensitivity=sensitivity,
        owner_agent=owner_agent,
        allowed_agents=allowed_agents,
        memory_type=memory_type,
        expires_at=expires_at,
        valid_from=valid_from,
        valid_until=valid_until,
        supersedes_id=supersedes_id,
    )

    cursor = conn.execute(
        """INSERT INTO knowledge
           (title, layer, category, tags, trust,
            content_raw, content_aaak, content_hash, source,
            summary, summary_generated_at,
            scope, sensitivity, owner_agent, allowed_agents, memory_type, expires_at,
            valid_from, valid_until, supersedes_id,
            created_at, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            title,
            layer,
            category,
            tags,
            trust,
            content_raw,
            content_aaak,
            content_hash,
            source,
            summary,
            now if summary else "",
            governance["scope"],
            governance["sensitivity"],
            governance["owner_agent"],
            governance["allowed_agents"],
            governance["memory_type"],
            governance["expires_at"],
            governance["valid_from"],
            governance["valid_until"],
            governance["supersedes_id"],
            now,
            now,
        ),
    )
    knowledge_id = int(cursor.lastrowid)
    sync_fts_row(knowledge_id)
    conn.commit()
    return knowledge_id


def update_knowledge(
    conn: sqlite3.Connection,
    knowledge_id: int,
    update_columns: set[str] | frozenset[str],
    *,
    sync_fts_row: FtsRowSync,
    **fields: Any,
) -> bool:
    """Update knowledge fields."""
    if not fields:
        return False
    invalid = set(fields) - set(update_columns)
    if invalid:
        raise ValueError(f"invalid knowledge update field(s): {sorted(invalid)}")
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    if "content_raw" in fields:
        fields["content_hash"] = hashlib.sha256(fields["content_raw"].encode()).hexdigest()[:16]

    sets = ", ".join(f"{key}=?" for key in fields)
    values = list(fields.values()) + [knowledge_id]
    conn.execute(f"UPDATE knowledge SET {sets} WHERE id=?", values)
    sync_fts_row(knowledge_id)
    conn.commit()
    return True


def get_knowledge(conn: sqlite3.Connection, knowledge_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM knowledge WHERE id=?", (knowledge_id,)).fetchone()
    return dict(row) if row else None


def delete_knowledge(
    conn: sqlite3.Connection,
    knowledge_id: int,
    *,
    delete_fts_row: FtsRowDelete,
    vec_available: bool,
) -> bool:
    """Delete a knowledge row and dependent local indexes."""
    if get_knowledge(conn, knowledge_id) is None:
        return False
    conn.execute("DELETE FROM semantic_vectors WHERE knowledge_id=?", (knowledge_id,))
    conn.execute("DELETE FROM knowledge_claims WHERE knowledge_id=?", (knowledge_id,))
    conn.execute("DELETE FROM knowledge_nodes WHERE knowledge_id=?", (knowledge_id,))
    conn.execute("DELETE FROM lint_cache WHERE knowledge_id=?", (knowledge_id,))
    conn.execute("DELETE FROM entity_knowledge WHERE knowledge_id=?", (knowledge_id,))
    conn.execute("DELETE FROM edges WHERE source_id=? OR target_id=?", (knowledge_id, knowledge_id))
    delete_fts_row(knowledge_id)
    if vec_available:
        conn.execute("DELETE FROM knowledge_vec WHERE knowledge_id=?", (knowledge_id,))
    conn.execute("DELETE FROM knowledge WHERE id=?", (knowledge_id,))
    conn.commit()
    return True


def list_knowledge(
    conn: sqlite3.Connection,
    *,
    layer: str | None = None,
    category: str | None = None,
    min_trust: float = 0.0,
    limit: int = 100,
    include_archived: bool = False,
) -> list[dict]:
    """List knowledge rows with layer/category/trust filters."""
    limit = normalize_search_limit(limit, default=100)
    if limit <= 0:
        return []
    query = "SELECT * FROM knowledge WHERE trust >= ?"
    params: list[Any] = [min_trust]
    if not include_archived:
        query += " AND COALESCE(status, 'active') != 'archived'"
    if layer:
        query += " AND layer=?"
        params.append(layer)
    if category:
        query += " AND category=?"
        params.append(category)
    query += " ORDER BY trust DESC, updated_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def search_keyword(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 10,
    min_trust: float = 0.0,
) -> list[dict]:
    """Pure LIKE keyword search fallback."""
    if query is None:
        return []
    limit = normalize_search_limit(limit)
    if limit <= 0:
        return []

    escaped = escape_like_pattern(query)
    pattern = f"%{escaped}%"
    rows = conn.execute(
        """
            SELECT *, 0.0 AS _score
            FROM knowledge
            WHERE trust >= ?
              AND COALESCE(status, 'active') != 'archived'
              AND (title LIKE ? ESCAPE '\\' OR content_raw LIKE ? ESCAPE '\\'
                   OR content_aaak LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\'
                   OR category LIKE ? ESCAPE '\\')
            ORDER BY trust DESC
            LIMIT ?
        """,
        (min_trust, pattern, pattern, pattern, pattern, pattern, limit),
    ).fetchall()
    return [dict(row) for row in rows]
