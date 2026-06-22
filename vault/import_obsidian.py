"""Obsidian vault import helpers.

This path imports user-authored Obsidian Markdown into Vault ``raw/`` files.
It deliberately skips Vault's own Obsidian export folder so repeated export and
import workflows do not feed generated notes back into the source vault.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from vault.compiler import extract_frontmatter, safe_path_segment
from vault.db import normalize_governance_metadata


DEFAULT_OBSIDIAN_EXCLUDES = {
    ".git",
    ".obsidian",
    ".trash",
    "00-Vault-Knowledge",
}


@dataclass
class ObsidianImportResult:
    scanned: int = 0
    added: int = 0
    updated: int = 0
    skipped: int = 0
    ignored: int = 0
    errors: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    dry_run: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "added": self.added,
            "updated": self.updated,
            "skipped": self.skipped,
            "ignored": self.ignored,
            "errors": self.errors,
            "paths": self.paths,
            "dry_run": self.dry_run,
        }


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        raw_items = re.split(r"[,\s]+", str(value))

    tags: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        tag = str(item).strip().strip("#")
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


def _extract_title(path: Path, metadata: dict[str, Any], body: str) -> str:
    title = metadata.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()

    for line in body.splitlines():
        if line.startswith("# "):
            candidate = line[2:].strip()
            if candidate:
                return candidate

    return path.stem.replace("-", " ").replace("_", " ").strip() or "Untitled"


def _safe_relative_markdown_path(relative_path: Path) -> Path:
    safe_parts = [safe_path_segment(part, default="untitled") for part in relative_path.parts]
    safe_path = Path(*safe_parts)
    if safe_path.suffix.lower() != ".md":
        safe_path = safe_path.with_suffix(".md")
    return safe_path


def _is_excluded(path: Path, root: Path, excludes: set[str]) -> bool:
    relative = path.relative_to(root)
    return any(part in excludes for part in relative.parts)


def iter_obsidian_markdown(vault_dir: str | Path, excludes: set[str] | None = None) -> list[Path]:
    """Return Markdown notes in stable order while skipping Obsidian/system dirs."""
    root = Path(vault_dir)
    active_excludes = set(DEFAULT_OBSIDIAN_EXCLUDES)
    if excludes:
        active_excludes.update(str(item).strip() for item in excludes if str(item).strip())

    notes: list[Path] = []
    for path in sorted(root.rglob("*.md")):
        if path.is_symlink() or not path.is_file():
            continue
        if _is_excluded(path, root, active_excludes):
            continue
        notes.append(path)
    return notes


def render_vault_raw_note(
    *,
    source_path: Path,
    obsidian_root: Path,
    category: str,
    tags: list[str],
    layer: str,
    trust: float,
    imported_at: str,
) -> tuple[str, str]:
    """Render a Vault raw Markdown note and return ``(content, source_hash)``."""
    original = source_path.read_text(encoding="utf-8")
    metadata, body = extract_frontmatter(original)
    source_hash = _content_hash(original)
    relative = source_path.relative_to(obsidian_root).as_posix()

    obsidian_tags = _normalize_tags(metadata.get("tags"))
    merged_tags = []
    for tag in [*tags, *obsidian_tags, "obsidian"]:
        if tag and tag not in merged_tags:
            merged_tags.append(tag)

    frontmatter: dict[str, Any] = {
        "title": _extract_title(source_path, metadata, body),
        "layer": layer,
        "category": category,
        "tags": merged_tags,
        "trust": trust,
        "source": f"obsidian:{relative}",
        "imported_from": "obsidian",
        "obsidian_source_path": relative,
        "obsidian_source_hash": source_hash,
        "imported_at": imported_at,
    }
    governance = normalize_governance_metadata(
        scope=metadata.get("scope", "project"),
        sensitivity=metadata.get("sensitivity", "low"),
        owner_agent=metadata.get("owner_agent", ""),
        allowed_agents=metadata.get("allowed_agents", ""),
        memory_type=metadata.get("memory_type", "knowledge"),
        expires_at=metadata.get("expires_at", ""),
    )
    governance["allowed_agents"] = json.loads(governance["allowed_agents"])
    frontmatter.update(governance)
    aliases = metadata.get("aliases")
    if aliases:
        frontmatter["obsidian_aliases"] = aliases

    rendered_frontmatter = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    return f"---\n{rendered_frontmatter}---\n\n{body.strip()}\n", source_hash


def sync_obsidian_vault(
    *,
    project_dir: str | Path,
    vault_dir: str | Path,
    category: str = "obsidian",
    tags: str | list[str] = "obsidian",
    layer: str = "L3",
    trust: float = 0.5,
    raw_subdir: str = "obsidian",
    excludes: set[str] | list[str] | None = None,
    dry_run: bool = False,
    allow_private: bool = False,
) -> dict[str, Any]:
    """Sync Obsidian Markdown notes into ``raw/<raw_subdir>/``.

    The function is intentionally idempotent. It compares the original
    Obsidian file hash against the previously imported raw copy and only
    rewrites changed files.
    """
    project_path = Path(project_dir)
    obsidian_root = Path(vault_dir).expanduser().resolve()
    if not obsidian_root.is_dir():
        raise FileNotFoundError(f"Obsidian vault not found: {obsidian_root}")

    raw_root = project_path / "raw" / safe_path_segment(raw_subdir, default="obsidian")
    import_tags = _normalize_tags(tags)
    imported_at = datetime.now(timezone.utc).isoformat()
    result = ObsidianImportResult(dry_run=dry_run)

    active_excludes = set(excludes or [])
    notes = iter_obsidian_markdown(obsidian_root, active_excludes)
    result.ignored = len(list(obsidian_root.rglob("*.md"))) - len(notes)

    for note in notes:
        result.scanned += 1
        relative = note.relative_to(obsidian_root)
        destination = raw_root / _safe_relative_markdown_path(relative)

        try:
            content, source_hash = render_vault_raw_note(
                source_path=note,
                obsidian_root=obsidian_root,
                category=category,
                tags=import_tags,
                layer=layer,
                trust=trust,
                imported_at=imported_at,
            )
            if not allow_private:
                from vault.privacy import scan_privacy

                privacy = scan_privacy(content)
                if privacy.get("status") == "fail":
                    kinds = ", ".join(
                        sorted(
                            {
                                str(item.get("type", "secret"))
                                for item in privacy.get("findings", [])
                            }
                        )
                    )
                    result.errors.append(f"{relative.as_posix()}: privacy gate failed ({kinds})")
                    continue

            existing_hash = ""
            if destination.exists():
                existing_metadata, _ = extract_frontmatter(destination.read_text(encoding="utf-8"))
                existing_hash = str(existing_metadata.get("obsidian_source_hash", ""))

            if existing_hash == source_hash:
                result.skipped += 1
                continue

            if destination.exists():
                result.updated += 1
            else:
                result.added += 1

            result.paths.append(str(destination))
            if dry_run:
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
        except Exception as exc:  # pragma: no cover - defensive per-file isolation
            result.errors.append(f"{relative.as_posix()}: {exc}")

    return result.as_dict()
