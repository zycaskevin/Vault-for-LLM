"""Read-only Obsidian export for Vault-for-LLM knowledge entries.

This module intentionally exports from ``vault.db`` to Markdown files only.
It never writes back to ``raw/``, ``compiled/``, SQLite, or any remote sync target.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_EXPORT_DIR = "00-Vault-Knowledge"


def slugify_filename(value: str) -> str:
    """Return a stable, path-safe filename slug while preserving readable text."""
    slug = re.sub(r"[\\/:*?\"<>|]+", "-", value.strip())
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-._ ")
    return slug or "untitled"


def _parse_tags(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]

    text = str(raw).strip()
    if not text:
        return []

    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass

    return [part.strip() for part in text.split(",") if part.strip()]


def _yaml_string(value: Any) -> str:
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


def _frontmatter(row: dict[str, Any]) -> str:
    tags = _parse_tags(row.get("tags"))
    tag_list = "[" + ", ".join(json.dumps(tag, ensure_ascii=False) for tag in tags) + "]"
    allowed_agents = _parse_tags(row.get("allowed_agents"))
    allowed_agent_list = "[" + ", ".join(json.dumps(agent, ensure_ascii=False) for agent in allowed_agents) + "]"
    lines = [
        "---",
        f"vault_id: {row['id']}",
        f"title: {_yaml_string(row.get('title', ''))}",
        f"category: {_yaml_string(row.get('category', 'general'))}",
        f"tags: {tag_list}",
        f"layer: {_yaml_string(row.get('layer', 'L3'))}",
        f"trust: {float(row.get('trust') or 0):g}",
        f"source: {_yaml_string(row.get('source', ''))}",
        f"scope: {_yaml_string(row.get('scope', 'project'))}",
        f"sensitivity: {_yaml_string(row.get('sensitivity', 'low'))}",
        f"owner_agent: {_yaml_string(row.get('owner_agent', ''))}",
        f"allowed_agents: {allowed_agent_list}",
        f"memory_type: {_yaml_string(row.get('memory_type', 'knowledge'))}",
        f"expires_at: {_yaml_string(row.get('expires_at', ''))}",
        f"created: {_yaml_string(row.get('created_at', ''))}",
        f"updated: {_yaml_string(row.get('updated_at', ''))}",
        f"summary: {_yaml_string(row.get('summary', ''))}",
        "---",
    ]
    return "\n".join(lines)


def _render_note(row: dict[str, Any]) -> str:
    title = str(row.get("title") or f"Vault #{row['id']}")
    body = str(row.get("content_raw") or "").strip()
    if not body.startswith("#"):
        body = f"# {title}\n\n{body}" if body else f"# {title}"
    return f"{_frontmatter(row)}\n\n{body}\n\n## Citation\n\nVault #{row['id']}\n"


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"vault.db not found at {db_path}")
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _load_rows(
    conn: sqlite3.Connection,
    *,
    category: str | None = None,
    layer: str | None = None,
    min_trust: float = 0.0,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM knowledge WHERE trust >= ?"
    params: list[Any] = [min_trust]
    if category:
        query += " AND category = ?"
        params.append(category)
    if layer:
        query += " AND layer = ?"
        params.append(layer)
    query += " ORDER BY id ASC"
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def export_obsidian_vault(
    *,
    project_dir: str | Path,
    vault_dir: str | Path,
    category: str | None = None,
    tag: str | None = None,
    layer: str | None = None,
    limit: int | None = None,
    min_trust: float = 0.0,
    source: str = "db",
    dry_run: bool = False,
    export_dir_name: str = DEFAULT_EXPORT_DIR,
) -> dict[str, Any]:
    """Export knowledge entries to an Obsidian vault as Markdown notes.

    The current MVP supports ``source='db'`` only. It is deliberately one-way:
    Vault SQLite → Obsidian Markdown. Dry-runs return planned paths without
    creating directories or files.
    """
    if source != "db":
        raise ValueError("Obsidian export currently supports --source db only")

    project_path = Path(project_dir)
    destination = Path(vault_dir)
    db_path = project_path / "vault.db"

    with _connect_readonly(db_path) as conn:
        rows = _load_rows(conn, category=category, layer=layer, min_trust=min_trust)

    if tag:
        rows = [row for row in rows if tag in _parse_tags(row.get("tags"))]
    if limit is not None:
        rows = rows[:limit]

    planned: list[str] = []
    written = 0
    for row in rows:
        category_dir = slugify_filename(str(row.get("category") or "general"))
        filename = f"{int(row['id']):04d}-{slugify_filename(str(row.get('title') or 'untitled'))}.md"
        note_path = destination / export_dir_name / category_dir / filename
        planned.append(str(note_path))
        if dry_run:
            continue
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(_render_note(row), encoding="utf-8")
        written += 1

    return {
        "matched": len(rows),
        "written": written,
        "dry_run": dry_run,
        "vault_dir": str(destination),
        "export_dir": export_dir_name,
        "paths": planned,
    }
