"""Skill CRUD helpers for VaultDB."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
import sqlite3
from typing import Any


def escape_like_pattern(term: str) -> str:
    """Escape LIKE wildcards for skill search filters."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def init_skill_tables(conn: sqlite3.Connection) -> None:
    """Create Skill registry tables without expanding the core DB module."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL UNIQUE,
            version       TEXT NOT NULL DEFAULT '1.0.0',
            agent_source  TEXT NOT NULL DEFAULT '',
            category      TEXT NOT NULL DEFAULT 'general',
            capabilities  TEXT NOT NULL DEFAULT '',
            dependencies  TEXT NOT NULL DEFAULT '',
            trust         REAL  NOT NULL DEFAULT 0.5,
            content_raw   TEXT NOT NULL DEFAULT '',
            content_hash  TEXT NOT NULL DEFAULT '',
            description   TEXT NOT NULL DEFAULT '',
            created_at    TEXT NOT NULL DEFAULT '',
            updated_at    TEXT NOT NULL DEFAULT '',
            last_synced   TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skills_agent ON skills(agent_source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skills_category ON skills(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skills_trust ON skills(trust)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skill_revisions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_name    TEXT NOT NULL,
            version       TEXT NOT NULL DEFAULT '1.0.0',
            agent_source  TEXT NOT NULL DEFAULT '',
            category      TEXT NOT NULL DEFAULT 'general',
            capabilities  TEXT NOT NULL DEFAULT '',
            dependencies  TEXT NOT NULL DEFAULT '',
            trust         REAL  NOT NULL DEFAULT 0.5,
            content_raw   TEXT NOT NULL DEFAULT '',
            content_hash  TEXT NOT NULL DEFAULT '',
            description   TEXT NOT NULL DEFAULT '',
            created_at    TEXT NOT NULL DEFAULT '',
            updated_at    TEXT NOT NULL DEFAULT '',
            UNIQUE(skill_name, version)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_revisions_name ON skill_revisions(skill_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_revisions_version ON skill_revisions(version)")


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
    force: bool = False,
) -> int:
    """Register a skill and return its id. Existing non-newer names return -1 unless forced."""
    now = datetime.now(timezone.utc).isoformat()
    content_hash = hashlib.sha256(content_raw.encode()).hexdigest()[:16]

    existing = conn.execute("SELECT id, version FROM skills WHERE name=?", (name,)).fetchone()
    if existing:
        if not force and _version_key(version) <= _version_key(existing["version"]):
            _upsert_skill_revision(
                conn,
                skill_name=name,
                version=version,
                agent_source=agent_source,
                category=category,
                capabilities=capabilities,
                dependencies=dependencies,
                trust=trust,
                content_raw=content_raw,
                content_hash=content_hash,
                description=description,
                now=now,
            )
            conn.commit()
            return -1
        conn.execute(
            """UPDATE skills
               SET version=?, agent_source=?, category=?, capabilities=?, dependencies=?,
                   trust=?, content_raw=?, content_hash=?, description=?, updated_at=?
               WHERE name=?""",
            (
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
                name,
            ),
        )
        _upsert_skill_revision(
            conn,
            skill_name=name,
            version=version,
            agent_source=agent_source,
            category=category,
            capabilities=capabilities,
            dependencies=dependencies,
            trust=trust,
            content_raw=content_raw,
            content_hash=content_hash,
            description=description,
            now=now,
        )
        conn.commit()
        return int(existing["id"])

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
    _upsert_skill_revision(
        conn,
        skill_name=name,
        version=version,
        agent_source=agent_source,
        category=category,
        capabilities=capabilities,
        dependencies=dependencies,
        trust=trust,
        content_raw=content_raw,
        content_hash=content_hash,
        description=description,
        now=now,
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


def list_skill_versions(conn: sqlite3.Connection, name: str) -> list[dict]:
    """List known versions for one skill without returning raw content."""
    rows = conn.execute(
        """SELECT id, skill_name, version, agent_source, category, capabilities,
                  dependencies, trust, content_hash, description, created_at, updated_at
           FROM skill_revisions
           WHERE skill_name=?
           ORDER BY updated_at DESC, id DESC""",
        (name,),
    ).fetchall()
    return sorted((dict(row) for row in rows), key=lambda row: _version_key(row.get("version")), reverse=True)


def diff_skill_versions(conn: sqlite3.Connection, name: str, from_version: str, to_version: str) -> dict:
    """Return a compact field-level diff for two skill versions."""
    before = _get_skill_revision(conn, name, from_version)
    after = _get_skill_revision(conn, name, to_version)
    if not before or not after:
        return {
            "ok": False,
            "error": "version_not_found",
            "name": name,
            "from_version": from_version,
            "to_version": to_version,
        }
    fields = ["agent_source", "category", "capabilities", "dependencies", "trust", "content_hash", "description"]
    changes = {
        field: {"from": before.get(field), "to": after.get(field)}
        for field in fields
        if before.get(field) != after.get(field)
    }
    return {
        "ok": True,
        "name": name,
        "from_version": from_version,
        "to_version": to_version,
        "content_changed": before.get("content_hash") != after.get("content_hash"),
        "changed_fields": changes,
    }


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
        "dependencies, trust, content_hash, description, created_at, updated_at, last_synced FROM skills "
        f"WHERE {where} ORDER BY trust DESC, updated_at DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    return [dict(row) for row in rows]


def mark_skill_synced(conn: sqlite3.Connection, name: str) -> None:
    """Mark a skill as synced to remote storage."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE skills SET last_synced=? WHERE name=?", (now, name))
    conn.commit()


def skill_upgrade_plan(conn: sqlite3.Connection, *, installed: dict[str, str] | None = None) -> dict:
    """Compare installed skill versions to the registry's latest versions."""
    installed = installed or {}
    rows = list_skills(conn, limit=1000)
    items = []
    for row in rows:
        name = str(row.get("name") or "")
        latest = str(row.get("version") or "")
        current = str(installed.get(name) or "")
        upgrade_available = bool(current and _version_key(latest) > _version_key(current))
        items.append(
            {
                "name": name,
                "current_version": current,
                "latest_version": latest,
                "upgrade_available": upgrade_available,
                "status": "not_installed" if not current else ("upgrade_available" if upgrade_available else "current"),
                "category": row.get("category", ""),
                "agent_source": row.get("agent_source", ""),
                "trust": row.get("trust", 0.0),
                "description": row.get("description", ""),
            }
        )
    return {
        "ok": True,
        "skill_count": len(items),
        "upgrade_count": sum(1 for item in items if item["upgrade_available"]),
        "skills": items,
    }


def _version_key(value: Any) -> tuple[int, ...]:
    parts = re.findall(r"\d+", str(value or ""))
    return tuple(int(part) for part in parts[:4]) or (0,)


def _get_skill_revision(conn: sqlite3.Connection, name: str, version: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM skill_revisions WHERE skill_name=? AND version=?",
        (name, version),
    ).fetchone()
    return dict(row) if row else None


def _upsert_skill_revision(
    conn: sqlite3.Connection,
    *,
    skill_name: str,
    version: str,
    agent_source: str,
    category: str,
    capabilities: str,
    dependencies: str,
    trust: float,
    content_raw: str,
    content_hash: str,
    description: str,
    now: str,
) -> None:
    conn.execute(
        """INSERT INTO skill_revisions(
               skill_name, version, agent_source, category, capabilities, dependencies,
               trust, content_raw, content_hash, description, created_at, updated_at
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(skill_name, version) DO UPDATE SET
               agent_source=excluded.agent_source,
               category=excluded.category,
               capabilities=excluded.capabilities,
               dependencies=excluded.dependencies,
               trust=excluded.trust,
               content_raw=excluded.content_raw,
               content_hash=excluded.content_hash,
               description=excluded.description,
               updated_at=excluded.updated_at""",
        (
            skill_name,
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
        ),
    )
