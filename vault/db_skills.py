"""Skill CRUD helpers for VaultDB."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import sqlite3
from typing import Any


def escape_like_pattern(term: str) -> str:
    """Escape LIKE wildcards for skill search filters."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def add_skill(
    conn: sqlite3.Connection,
    *,
    name: str,
    content_raw: str,
    version: str = "1.0.0",
    agent_source: str = "",
    category: str = "general",
    capabilities: str = "",
    dependencies: str = "",
    trust: float = 0.5,
    description: str = "",
) -> int:
    """Register a skill and return its id. Existing names return -1."""
    now = datetime.now(timezone.utc).isoformat()
    content_hash = hashlib.sha256(content_raw.encode()).hexdigest()[:16]

    existing = conn.execute("SELECT id FROM skills WHERE name=?", (name,)).fetchone()
    if existing:
        return -1

    cursor = conn.execute(
        """INSERT INTO skills
           (name, version, agent_source, category, capabilities, dependencies,
            trust, content_raw, content_hash, description,
            created_at, updated_at, last_synced)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            name,
            version,
            agent_source,
            category,
            capabilities,
            dependencies,
            trust,
            content_raw,
            content_hash,
            description,
            now,
            now,
            "",
        ),
    )
    conn.commit()
    return cursor.lastrowid


def update_skill(
    conn: sqlite3.Connection,
    name: str,
    update_columns: set[str] | frozenset[str],
    **fields: Any,
) -> bool:
    """Update a skill by name."""
    if not fields:
        return False
    invalid = set(fields) - set(update_columns)
    if invalid:
        raise ValueError(f"invalid skill update field(s): {sorted(invalid)}")
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    if "content_raw" in fields:
        fields["content_hash"] = hashlib.sha256(fields["content_raw"].encode()).hexdigest()[:16]

    sets = ", ".join(f"{key}=?" for key in fields)
    values = list(fields.values()) + [name]
    conn.execute(f"UPDATE skills SET {sets} WHERE name=?", values)
    conn.commit()
    return conn.total_changes > 0


def get_skill(conn: sqlite3.Connection, name: str) -> dict | None:
    """Return one skill row by name."""
    row = conn.execute("SELECT * FROM skills WHERE name=?", (name,)).fetchone()
    return dict(row) if row else None


def delete_skill(conn: sqlite3.Connection, name: str) -> bool:
    """Delete a skill by name."""
    conn.execute("DELETE FROM skills WHERE name=?", (name,))
    conn.commit()
    return conn.total_changes > 0


def search_skills(
    conn: sqlite3.Connection,
    *,
    query: str,
    capabilities: str | None = None,
    category: str | None = None,
    min_trust: float = 0.0,
    agent_source: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search skills by keyword plus optional filters."""
    conditions = ["trust >= ?"]
    params: list[Any] = [min_trust]

    if query:
        conditions.append(
            "(name LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' "
            "OR capabilities LIKE ? ESCAPE '\\' OR content_raw LIKE ? ESCAPE '\\')"
        )
        pattern = f"%{escape_like_pattern(query)}%"
        params.extend([pattern, pattern, pattern, pattern])

    if capabilities:
        conditions.append("capabilities LIKE ? ESCAPE '\\'")
        params.append(f"%{escape_like_pattern(capabilities)}%")

    if category:
        conditions.append("category=?")
        params.append(category)

    if agent_source:
        conditions.append("agent_source=?")
        params.append(agent_source)

    where = " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT * FROM skills WHERE {where} "
        "ORDER BY trust DESC, updated_at DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    return [dict(row) for row in rows]


def list_skills(
    conn: sqlite3.Connection,
    *,
    agent_source: str | None = None,
    category: str | None = None,
    min_trust: float = 0.0,
    limit: int = 100,
) -> list[dict]:
    """List skills without content_raw for a lighter result surface."""
    conditions = ["trust >= ?"]
    params: list[Any] = [min_trust]

    if agent_source:
        conditions.append("agent_source=?")
        params.append(agent_source)
    if category:
        conditions.append("category=?")
        params.append(category)

    where = " AND ".join(conditions)
    rows = conn.execute(
        "SELECT id, name, version, agent_source, category, capabilities, "
        "dependencies, trust, description, updated_at FROM skills "
        f"WHERE {where} ORDER BY trust DESC, updated_at DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    return [dict(row) for row in rows]


def mark_skill_synced(conn: sqlite3.Connection, name: str) -> None:
    """Mark a skill as synced to remote storage."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE skills SET last_synced=? WHERE name=?", (now, name))
    conn.commit()
