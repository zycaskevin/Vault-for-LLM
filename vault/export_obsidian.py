"""Read-only Obsidian export for Vault-for-LLM knowledge entries.

This module intentionally exports from ``vault.db`` to Markdown files only.
It never writes back to ``raw/``, ``compiled/``, SQLite, or any remote sync target.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
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
        f"valid_from: {_yaml_string(row.get('valid_from', ''))}",
        f"valid_until: {_yaml_string(row.get('valid_until', ''))}",
        f"supersedes_id: {row.get('supersedes_id') or ''}",
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


def _load_review_candidates(conn: sqlite3.Connection, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, title, reason, status, privacy_status, duplicate_status,
               quality_status, source, source_ref, scope, sensitivity,
               memory_type, created_at, updated_at
        FROM memory_candidates
        WHERE status IN ('candidate', 'approved', 'blocked')
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (max(0, int(limit)),),
    ).fetchall()
    return [dict(row) for row in rows]


def _load_recent_knowledge(conn: sqlite3.Connection, *, limit: int = 8) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, title, category, layer, scope, sensitivity, trust, source, updated_at
        FROM knowledge
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (max(0, int(limit)),),
    ).fetchall()
    return [dict(row) for row in rows]


def _note_basename(row: dict[str, Any]) -> str:
    return f"{int(row['id']):04d}-{slugify_filename(str(row.get('title') or 'untitled'))}"


def _note_wikilink(row: dict[str, Any]) -> str:
    title = row.get("title") or f"Vault #{row['id']}"
    return f"[[{_note_basename(row)}|{title}]]"


def _load_graph_edges(conn: sqlite3.Connection, *, limit: int = 40) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT e.id, e.relation, e.weight, e.auto_inferred, e.created_at,
               s.id AS source_id, s.title AS source_title, s.category AS source_category,
               t.id AS target_id, t.title AS target_title, t.category AS target_category
        FROM edges e
        JOIN knowledge s ON s.id = e.source_id
        JOIN knowledge t ON t.id = e.target_id
        ORDER BY e.weight DESC, e.id ASC
        LIMIT ?
        """,
        (max(1, min(int(limit or 40), 200)),),
    ).fetchall()
    return [dict(row) for row in rows]


def _load_category_counts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT category, COUNT(*) AS count
        FROM knowledge
        GROUP BY category
        ORDER BY count DESC, category ASC
        LIMIT 20
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _load_obsidian_manifest(project_path: Path) -> dict[str, Any]:
    path = project_path / ".vault" / "obsidian-import-manifest.json"
    if not path.exists():
        return {"version": 1, "notes": {}, "manifest_path": str(path), "exists": False}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "notes": {}, "manifest_path": str(path), "exists": False, "error": "unreadable"}
    if not isinstance(payload, dict):
        payload = {"version": 1, "notes": {}}
    payload["manifest_path"] = str(path)
    payload["exists"] = True
    payload.setdefault("notes", {})
    return payload


def _load_sync_health(conn: sqlite3.Connection, *, limit: int = 10) -> dict[str, Any]:
    """Return compact sync health without exposing raw conflict content."""
    limit_i = max(1, min(int(limit or 10), 50))

    def count(table: str, where: str = "") -> int:
        try:
            row = conn.execute(f"SELECT COUNT(*) FROM {table} {where}").fetchone()
            return int(row[0]) if row else 0
        except sqlite3.Error:
            return 0

    open_conflicts: list[dict[str, Any]] = []
    try:
        rows = conn.execute(
            """
            SELECT id, created_at, updated_at, knowledge_id, candidate_id,
                   conflict_type, reason
            FROM memory_conflicts
            WHERE status = 'open'
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit_i,),
        ).fetchall()
        open_conflicts = [dict(row) for row in rows]
    except sqlite3.Error:
        open_conflicts = []

    counts = {
        "revisions": count("memory_revisions"),
        "open_conflicts": count("memory_conflicts", "WHERE status='open'"),
        "resolved_conflicts": count("memory_conflicts", "WHERE status='resolved'"),
        "audit_events": count("memory_audit_log"),
    }
    if counts["open_conflicts"]:
        status = "needs_review"
        next_action = "Review open sync conflicts before accepting remote memory changes."
    elif counts["revisions"] or counts["audit_events"]:
        status = "ok"
        next_action = "No open sync conflicts. Continue candidate-first remote sync."
    else:
        status = "idle"
        next_action = "No multi-host sync activity recorded yet."
    return {
        "status": status,
        "counts": counts,
        "open_conflicts": open_conflicts,
        "next_action": next_action,
    }


def _render_candidate_row(row: dict[str, Any]) -> str:
    gates = (
        f"privacy={row.get('privacy_status', '')}, "
        f"duplicate={row.get('duplicate_status', '')}, "
        f"quality={row.get('quality_status', '')}"
    )
    reason = str(row.get("reason") or "").strip()
    reason_line = f"\n  - Reason: {reason}" if reason else ""
    return (
        f"- [ ] **{row.get('title', 'Untitled')}** (`{row.get('id', '')}`)\n"
        f"  - Status: `{row.get('status', '')}` | Scope: `{row.get('scope', '')}` | "
        f"Sensitivity: `{row.get('sensitivity', '')}`\n"
        f"  - Source: `{row.get('source', '')}` `{row.get('source_ref', '')}`\n"
        f"  - Gates: {gates}{reason_line}"
    )


def _folder_rule_preview(notes: dict[str, Any]) -> tuple[str, int]:
    groups: dict[str, list[str]] = {}
    unmatched: list[str] = []
    for path, item in sorted(notes.items()):
        if not isinstance(item, dict) or item.get("status") != "active":
            continue
        rule = str(item.get("folder_rule") or "").strip()
        if rule:
            groups.setdefault(rule, []).append(path)
        else:
            unmatched.append(path)

    sections: list[str] = []
    for rule, paths in sorted(groups.items()):
        examples = "\n".join(f"  - `{path}`" for path in paths[:10])
        more = f"\n  - ... {len(paths) - 10} more" if len(paths) > 10 else ""
        sections.append(f"- **{rule}**: {len(paths)} active note(s)\n{examples}{more}")
    if unmatched:
        examples = "\n".join(f"  - `{path}`" for path in unmatched[:10])
        more = f"\n  - ... {len(unmatched) - 10} more" if len(unmatched) > 10 else ""
        sections.append(f"- **No folder rule matched**: {len(unmatched)} active note(s)\n{examples}{more}")
    return "\n\n".join(sections) or "- No active Obsidian notes in the manifest.", len(unmatched)


def _render_review_inbox(
    *,
    candidates: list[dict[str, Any]],
    recent: list[dict[str, Any]],
    manifest: dict[str, Any],
    sync_health: dict[str, Any],
    generated_at: str,
) -> dict[str, str]:
    notes = manifest.get("notes") if isinstance(manifest.get("notes"), dict) else {}
    active_count = sum(1 for item in notes.values() if isinstance(item, dict) and item.get("status") == "active")
    missing = sorted(
        path for path, item in notes.items()
        if isinstance(item, dict) and item.get("status") == "missing"
    )
    obsidian_conflicts = sorted(
        (path, item) for path, item in notes.items()
        if isinstance(item, dict) and item.get("status") == "conflict"
    )
    folder_preview, unmatched_count = _folder_rule_preview(notes)

    candidate_lines = "\n\n".join(_render_candidate_row(row) for row in candidates) or "No pending memory candidates."
    recent_lines = "\n".join(
        f"- Vault #{row['id']} **{row.get('title', '')}** "
        f"({row.get('category', '')}, {row.get('scope', '')}/{row.get('sensitivity', '')})"
        for row in recent
    ) or "- No active knowledge yet."
    missing_lines = "\n".join(f"- `{path}`" for path in missing[:30]) or "- No missing Obsidian source notes."
    obsidian_conflict_lines = "\n".join(
        f"- [ ] `{path}` -> `{item.get('raw_path', '')}`\n"
        f"  - Reason: {item.get('reason', 'obsidian_source_and_vault_raw_both_changed')}"
        for path, item in obsidian_conflicts[:20]
    ) or "- No Obsidian mirror conflicts."
    sync_counts = sync_health.get("counts") or {}
    open_conflicts = sync_health.get("open_conflicts") or []
    conflict_lines = "\n".join(
        "- [ ] "
        f"`{row.get('id', '')}` {row.get('conflict_type', '')} "
        f"(candidate `{row.get('candidate_id', '')}`, knowledge `#{row.get('knowledge_id', '')}`)\n"
        f"  - Reason: {row.get('reason', '')}"
        for row in open_conflicts[:20]
    ) or "- No open remote sync conflicts."

    daily = f"""---
title: "Vault Daily Memory Report"
generated_by: "vault-for-llm"
generated_at: "{generated_at}"
---

# Vault Daily Memory Report

## Needs Your Attention

- Pending memory candidates: **{len(candidates)}**
- Missing Obsidian source notes: **{len(missing)}**
- Obsidian mirror conflicts: **{len(obsidian_conflicts)}**
- Open remote sync conflicts: **{int(sync_counts.get('open_conflicts') or 0)}**
- Imported active Obsidian notes: **{active_count}**

## Recent Active Knowledge

{recent_lines}

## Next Safe Actions

- Review `Memory Candidates.md` before promoting agent-proposed memory.
- Review `Sync Status.md` before pruning missing Obsidian notes.
- Resolve remote sync conflicts before accepting remote memory changes.
- Keep generated Vault notes inside `00-Vault-Knowledge/`.
"""

    candidate_note = f"""---
title: "Vault Memory Candidates"
generated_by: "vault-for-llm"
generated_at: "{generated_at}"
---

# Vault Memory Candidates

These are review prompts, not automatic approvals. Open Vault GUI or use the
review CLI/MCP tools to promote, reject, or delay.

{candidate_lines}
"""

    sync_status = f"""---
title: "Vault Obsidian Sync Status"
generated_by: "vault-for-llm"
generated_at: "{generated_at}"
---

# Vault Obsidian Sync Status

## Import Manifest

- Manifest exists: **{bool(manifest.get('exists'))}**
- Manifest path: `{manifest.get('manifest_path', '')}`
- Obsidian vault: `{manifest.get('vault_dir', '')}`
- Raw subdir: `{manifest.get('raw_subdir', '')}`
- Folder rules: **{manifest.get('folder_rules_count', 0)}**
- Folder-rule unmatched active notes: **{unmatched_count}**
- Obsidian mirror conflicts: **{len(obsidian_conflicts)}**

## Remote Candidate Sync

- Status: **{sync_health.get('status', 'idle')}**
- Revisions: **{int(sync_counts.get('revisions') or 0)}**
- Open conflicts: **{int(sync_counts.get('open_conflicts') or 0)}**
- Resolved conflicts: **{int(sync_counts.get('resolved_conflicts') or 0)}**
- Audit events: **{int(sync_counts.get('audit_events') or 0)}**
- Next action: {sync_health.get('next_action', '')}

## Open Remote Sync Conflicts

{conflict_lines}

## Obsidian Mirror Conflicts

{obsidian_conflict_lines}

## Missing Source Notes

{missing_lines}

## Safety Rule

Missing notes are not pruned unless an operator explicitly runs import with
`--prune-missing`. If both Obsidian and Vault have changed the same idea, keep
the conflict in review instead of overwriting user-authored notes.
"""
    folder_rules = f"""---
title: "Vault Obsidian Folder Rules Preview"
generated_by: "vault-for-llm"
generated_at: "{generated_at}"
---

# Vault Obsidian Folder Rules Preview

This is a preview of how Obsidian source notes are mapped into Vault memory
governance. It is generated from the last import manifest, not from a fresh
filesystem scan.

## Rule Matches

{folder_preview}

## Human Check

- Notes under sensitive folders should match a private/high or restricted rule.
- Shared project notes should match a shared/project rule.
- If many notes are unmatched, edit `.vault/obsidian-folder-rules.yaml` and run
  the Obsidian import again.
"""
    return {
        "_Inbox/Daily Memory Report.md": daily,
        "_Inbox/Memory Candidates.md": candidate_note,
        "_Inbox/Sync Status.md": sync_status,
        "_Inbox/Folder Rules Preview.md": folder_rules,
    }


def _render_graph_overview(
    *,
    recent: list[dict[str, Any]],
    category_counts: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, str]:
    recent_lines = "\n".join(f"- {_note_wikilink(row)}" for row in recent) or "- No active knowledge yet."
    category_lines = "\n".join(
        f"- **{row.get('category') or 'general'}**: {int(row.get('count') or 0)}"
        for row in category_counts
    ) or "- No categories yet."
    edge_lines = []
    for row in edges:
        source = {"id": row["source_id"], "title": row["source_title"]}
        target = {"id": row["target_id"], "title": row["target_title"]}
        edge_lines.append(
            f"- {_note_wikilink(source)} -- `{row.get('relation')}` "
            f"({float(row.get('weight') or 0):g}) -> {_note_wikilink(target)}"
        )
    edge_text = "\n".join(edge_lines) or "- No graph edges yet. Run `vault graph build` after importing Obsidian notes."

    home = f"""---
title: "Vault Home"
generated_by: "vault-for-llm"
generated_at: "{generated_at}"
---

# Vault Home

## Start Here

- [[Graph Overview]]
- [[Daily Memory Report]]
- [[Memory Candidates]]
- [[Sync Status]]
- [[Folder Rules Preview]]

## Recent Knowledge

{recent_lines}

## Categories

{category_lines}
"""
    graph = f"""---
title: "Vault Graph Overview"
generated_by: "vault-for-llm"
generated_at: "{generated_at}"
---

# Vault Graph Overview

This is a human-readable graph doorway for Obsidian. Agent retrieval should
still use Vault search, Document Map, and bounded reads.

## Strongest Links

{edge_text}
"""
    return {
        "_Index/Vault Home.md": home,
        "_Index/Graph Overview.md": graph,
    }


def export_obsidian_graph_overview(
    *,
    project_dir: str | Path,
    vault_dir: str | Path,
    dry_run: bool = False,
    export_dir_name: str = DEFAULT_EXPORT_DIR,
    limit: int = 40,
) -> dict[str, Any]:
    """Export Obsidian index notes that turn Vault into a browsable graph GUI."""
    project_path = Path(project_dir)
    destination = Path(vault_dir)
    db_path = project_path / "vault.db"
    generated_at = datetime.now(timezone.utc).isoformat()
    with _connect_readonly(db_path) as conn:
        rendered = _render_graph_overview(
            recent=_load_recent_knowledge(conn, limit=10),
            category_counts=_load_category_counts(conn),
            edges=_load_graph_edges(conn, limit=limit),
            generated_at=generated_at,
        )

    paths: list[str] = []
    written = 0
    for relative, content in rendered.items():
        note_path = destination / export_dir_name / relative
        paths.append(str(note_path))
        if dry_run:
            continue
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(content, encoding="utf-8")
        written += 1
    return {
        "matched": len(rendered),
        "written": written,
        "dry_run": dry_run,
        "vault_dir": str(destination),
        "export_dir": export_dir_name,
        "paths": paths,
    }


def export_obsidian_review_inbox(
    *,
    project_dir: str | Path,
    vault_dir: str | Path,
    dry_run: bool = False,
    export_dir_name: str = DEFAULT_EXPORT_DIR,
    limit: int = 20,
) -> dict[str, Any]:
    """Export a compact human review inbox into Obsidian."""
    project_path = Path(project_dir)
    destination = Path(vault_dir)
    db_path = project_path / "vault.db"
    generated_at = datetime.now(timezone.utc).isoformat()

    with _connect_readonly(db_path) as conn:
        candidates = _load_review_candidates(conn, limit=limit)
        recent = _load_recent_knowledge(conn, limit=8)
        sync_health = _load_sync_health(conn, limit=limit)
    manifest = _load_obsidian_manifest(project_path)
    rendered = _render_review_inbox(
        candidates=candidates,
        recent=recent,
        manifest=manifest,
        sync_health=sync_health,
        generated_at=generated_at,
    )

    paths: list[str] = []
    written = 0
    for relative, content in rendered.items():
        note_path = destination / export_dir_name / relative
        paths.append(str(note_path))
        if dry_run:
            continue
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(content, encoding="utf-8")
        written += 1

    return {
        "matched": len(rendered),
        "written": written,
        "dry_run": dry_run,
        "vault_dir": str(destination),
        "export_dir": export_dir_name,
        "paths": paths,
        "candidate_count": len(candidates),
        "missing_count": sum(
            1 for item in (manifest.get("notes") or {}).values()
            if isinstance(item, dict) and item.get("status") == "missing"
        ),
        "sync_status": sync_health.get("status", "idle"),
        "sync_conflict_count": int((sync_health.get("counts") or {}).get("open_conflicts") or 0),
    }


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
    include_review_inbox: bool = False,
    include_graph_overview: bool = False,
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

    review_result: dict[str, Any] | None = None
    if include_review_inbox:
        review_result = export_obsidian_review_inbox(
            project_dir=project_path,
            vault_dir=destination,
            dry_run=dry_run,
            export_dir_name=export_dir_name,
        )
        planned.extend(review_result["paths"])
        written += int(review_result["written"])

    graph_result: dict[str, Any] | None = None
    if include_graph_overview:
        graph_result = export_obsidian_graph_overview(
            project_dir=project_path,
            vault_dir=destination,
            dry_run=dry_run,
            export_dir_name=export_dir_name,
        )
        planned.extend(graph_result["paths"])
        written += int(graph_result["written"])

    payload = {
        "matched": len(rows),
        "written": written,
        "dry_run": dry_run,
        "vault_dir": str(destination),
        "export_dir": export_dir_name,
        "paths": planned,
    }
    if review_result is not None:
        payload["review_inbox"] = review_result
    if graph_result is not None:
        payload["graph_overview"] = graph_result
    return payload
