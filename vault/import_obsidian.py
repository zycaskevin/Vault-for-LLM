"""Obsidian vault import helpers.

This path imports user-authored Obsidian Markdown into Vault ``raw/`` files.
It deliberately skips Vault's own Obsidian export folder so repeated export and
import workflows do not feed generated notes back into the source vault.
"""

from __future__ import annotations

import hashlib
import fnmatch
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

_SCOPE_RANK = {"public": 0, "shared": 1, "project": 2, "private": 3}
_SENSITIVITY_RANK = {"low": 0, "medium": 1, "high": 2, "restricted": 3}
_WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]\n]+)\]\]")


@dataclass
class ObsidianImportResult:
    scanned: int = 0
    added: int = 0
    updated: int = 0
    skipped: int = 0
    deleted: int = 0
    missing: int = 0
    ignored: int = 0
    errors: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    missing_paths: list[str] = field(default_factory=list)
    manifest_path: str = ""
    dry_run: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "added": self.added,
            "updated": self.updated,
            "skipped": self.skipped,
            "deleted": self.deleted,
            "missing": self.missing,
            "ignored": self.ignored,
            "errors": self.errors,
            "paths": self.paths,
            "missing_paths": self.missing_paths,
            "manifest_path": self.manifest_path,
            "dry_run": self.dry_run,
        }


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _manifest_path(project_dir: Path) -> Path:
    return project_dir / ".vault" / "obsidian-import-manifest.json"


def _load_manifest(project_dir: Path) -> dict[str, Any]:
    path = _manifest_path(project_dir)
    if not path.exists():
        return {"version": 1, "notes": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "notes": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "notes": {}}
    notes = payload.get("notes")
    if not isinstance(notes, dict):
        payload["notes"] = {}
    payload.setdefault("version", 1)
    return payload


def _write_manifest(project_dir: Path, payload: dict[str, Any]) -> Path:
    path = _manifest_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


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


def _normalize_rule_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("rules") or payload.get("folder_rules") or payload.get("folders") or []
    if not isinstance(payload, list):
        return []

    rules: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        pattern = str(item.get("pattern") or item.get("path") or "").strip()
        if not pattern:
            continue
        rule = dict(item)
        rule["pattern"] = pattern
        rules.append(rule)
    return rules


def load_obsidian_folder_rules(project_dir: str | Path, rules_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load optional folder-to-governance rules for Obsidian imports."""
    path = Path(rules_path).expanduser() if rules_path else Path(project_dir) / ".vault" / "obsidian-folder-rules.yaml"
    if not path.exists():
        return []
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    return _normalize_rule_list(payload)


def _matches_rule(relative_text: str, pattern: str) -> bool:
    pattern = pattern.strip().lstrip("/")
    if not pattern:
        return False
    if fnmatch.fnmatch(relative_text, pattern):
        return True
    if pattern.endswith("/"):
        return relative_text.startswith(pattern)
    if not any(ch in pattern for ch in "*?[]"):
        return relative_text.startswith(pattern.rstrip("/") + "/")
    return False


def _folder_policy_for(relative_text: str, rules: list[dict[str, Any]] | None) -> dict[str, Any]:
    policy: dict[str, Any] = {}
    for rule in rules or []:
        pattern = str(rule.get("pattern") or "").strip()
        if not _matches_rule(relative_text, pattern):
            continue
        policy.update({k: v for k, v in rule.items() if k != "pattern"})
        policy["pattern"] = pattern
    return policy


def _most_restrictive(value_a: Any, value_b: Any, rank: dict[str, int], default: str) -> str:
    a = str(value_a or "").strip().lower()
    b = str(value_b or "").strip().lower()
    if not a and not b:
        return default
    if not a:
        return b if b in rank else default
    if not b:
        return a if a in rank else default
    if a not in rank:
        a = default
    if b not in rank:
        b = default
    return a if rank[a] >= rank[b] else b


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_obsidian_wikilinks(text: str) -> list[str]:
    """Return de-duplicated Obsidian wikilink targets from Markdown text."""
    links: list[str] = []
    seen: set[str] = set()
    for match in _WIKILINK_RE.finditer(text or ""):
        target = match.group(1).split("|", 1)[0].strip()
        if target and target not in seen:
            seen.add(target)
            links.append(target)
    return links


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
    folder_rules: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """Render a Vault raw Markdown note and return ``(content, source_hash)``."""
    original = source_path.read_text(encoding="utf-8")
    metadata, body = extract_frontmatter(original)
    source_hash = _content_hash(original)
    relative = source_path.relative_to(obsidian_root).as_posix()
    folder_policy = _folder_policy_for(relative, folder_rules)

    obsidian_tags = _normalize_tags(metadata.get("tags"))
    folder_tags = _normalize_tags(folder_policy.get("tags"))
    merged_tags = []
    for tag in [*tags, *folder_tags, *obsidian_tags, "obsidian"]:
        if tag and tag not in merged_tags:
            merged_tags.append(tag)

    category_value = metadata.get("category") or folder_policy.get("category") or category
    layer_value = metadata.get("layer") or folder_policy.get("layer") or layer
    trust_value = _as_float(metadata.get("trust", folder_policy.get("trust", trust)), trust)
    scope_value = _most_restrictive(folder_policy.get("scope"), metadata.get("scope"), _SCOPE_RANK, "project")
    sensitivity_value = _most_restrictive(
        folder_policy.get("sensitivity"),
        metadata.get("sensitivity"),
        _SENSITIVITY_RANK,
        "low",
    )
    wikilinks = extract_obsidian_wikilinks(body)

    frontmatter: dict[str, Any] = {
        "title": _extract_title(source_path, metadata, body),
        "layer": layer_value,
        "category": category_value,
        "tags": merged_tags,
        "trust": trust_value,
        "source": f"obsidian:{relative}",
        "imported_from": "obsidian",
        "obsidian_source_path": relative,
        "obsidian_source_hash": source_hash,
        "imported_at": imported_at,
    }
    governance = normalize_governance_metadata(
        scope=scope_value,
        sensitivity=sensitivity_value,
        owner_agent=metadata.get("owner_agent", folder_policy.get("owner_agent", "")),
        allowed_agents=metadata.get("allowed_agents", folder_policy.get("allowed_agents", "")),
        memory_type=metadata.get("memory_type", folder_policy.get("memory_type", "knowledge")),
        expires_at=metadata.get("expires_at", folder_policy.get("expires_at", "")),
    )
    governance["allowed_agents"] = json.loads(governance["allowed_agents"])
    frontmatter.update(governance)
    aliases = metadata.get("aliases")
    if aliases:
        frontmatter["obsidian_aliases"] = aliases
    if wikilinks:
        frontmatter["obsidian_links"] = wikilinks
    if folder_policy.get("pattern"):
        frontmatter["obsidian_folder_rule"] = folder_policy["pattern"]

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
    prune_missing: bool = False,
    folder_rules_path: str | Path | None = None,
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
    manifest = _load_manifest(project_path)
    previous_notes = dict(manifest.get("notes") or {})
    current_notes: dict[str, dict[str, Any]] = {}
    folder_rules = load_obsidian_folder_rules(project_path, folder_rules_path)

    active_excludes = set(excludes or [])
    notes = iter_obsidian_markdown(obsidian_root, active_excludes)
    result.ignored = len(list(obsidian_root.rglob("*.md"))) - len(notes)

    for note in notes:
        result.scanned += 1
        relative = note.relative_to(obsidian_root)
        relative_text = relative.as_posix()
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
                folder_rules=folder_rules,
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
                current_notes[relative_text] = {
                    "source_hash": source_hash,
                    "raw_path": str(destination.relative_to(project_path)),
                    "last_seen_at": imported_at,
                    "status": "active",
                    "folder_rule": _folder_policy_for(relative_text, folder_rules).get("pattern", ""),
                }
                continue

            if destination.exists():
                result.updated += 1
            else:
                result.added += 1

            result.paths.append(str(destination))
            current_notes[relative_text] = {
                "source_hash": source_hash,
                "raw_path": str(destination.relative_to(project_path)),
                "last_seen_at": imported_at,
                "status": "active",
                "folder_rule": _folder_policy_for(relative_text, folder_rules).get("pattern", ""),
            }
            if dry_run:
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
        except Exception as exc:  # pragma: no cover - defensive per-file isolation
            result.errors.append(f"{relative.as_posix()}: {exc}")

    missing_notes = sorted(set(previous_notes) - set(current_notes))
    for relative_text in missing_notes:
        previous = previous_notes.get(relative_text) if isinstance(previous_notes.get(relative_text), dict) else {}
        raw_path = str(previous.get("raw_path") or "")
        if not raw_path:
            continue
        raw_file = (project_path / raw_path).resolve()
        try:
            raw_file.relative_to((project_path / "raw").resolve())
        except ValueError:
            result.errors.append(f"{relative_text}: manifest raw_path escaped raw/ ({raw_path})")
            continue
        result.missing += 1
        result.missing_paths.append(str(raw_file))
        if prune_missing and raw_file.exists():
            result.deleted += 1
            if not dry_run:
                raw_file.unlink()

    if not dry_run:
        if prune_missing:
            manifest_notes = current_notes
        else:
            manifest_notes = dict(previous_notes)
            manifest_notes.update(current_notes)
            for relative_text in missing_notes:
                previous = manifest_notes.get(relative_text)
                if isinstance(previous, dict):
                    previous["status"] = "missing"
                    previous["missing_at"] = imported_at
        manifest.update(
            {
                "version": 1,
                "vault_dir": str(obsidian_root),
                "raw_subdir": safe_path_segment(raw_subdir, default="obsidian"),
                "updated_at": imported_at,
                "folder_rules_path": str(Path(folder_rules_path).expanduser()) if folder_rules_path else "",
                "folder_rules_count": len(folder_rules),
                "notes": manifest_notes,
            }
        )
        result.manifest_path = str(_write_manifest(project_path, manifest))

    return result.as_dict()
