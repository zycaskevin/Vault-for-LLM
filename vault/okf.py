"""Open Knowledge Format bundle validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
import posixpath
import re
from pathlib import Path
from typing import Any

import yaml


RESERVED_FILES = {"index.md", "log.md"}
SKIP_DIRS = {".git", ".obsidian", ".trash", "__pycache__"}
DEFAULT_MAX_FILE_BYTES = 2_000_000
LOCAL_MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)#?:]+(?:\.md)?(?:#[^)]+)?)\)")


@dataclass(frozen=True)
class FrontmatterResult:
    metadata: dict[str, Any]
    body: str
    has_frontmatter: bool
    error: str = ""


def parse_markdown_frontmatter(text: str) -> FrontmatterResult:
    """Parse YAML frontmatter while preserving parse errors for validation."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return FrontmatterResult({}, text, False)

    fm_lines: list[str] = []
    end_idx = -1
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
        fm_lines.append(lines[idx])
    if end_idx < 0:
        return FrontmatterResult({}, text, True, "frontmatter is not closed")

    raw = "\n".join(fm_lines)
    try:
        loaded = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        return FrontmatterResult({}, "\n".join(lines[end_idx + 1 :]).strip(), True, str(exc))
    if not isinstance(loaded, dict):
        return FrontmatterResult({}, "\n".join(lines[end_idx + 1 :]).strip(), True, "frontmatter must be a mapping")
    return FrontmatterResult(loaded, "\n".join(lines[end_idx + 1 :]).strip(), True)


def validate_okf_bundle(bundle_dir: str | Path, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> dict[str, Any]:
    """Validate an OKF-style Markdown bundle without mutating any files."""
    root = Path(bundle_dir).expanduser().resolve()
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    concepts: list[dict[str, Any]] = []
    reserved: list[dict[str, Any]] = []

    if not root.exists():
        return _payload(root, concepts, reserved, errors=[_issue("", "bundle_missing", "bundle path does not exist")], warnings=[])
    if not root.is_dir():
        return _payload(root, concepts, reserved, errors=[_issue("", "not_directory", "bundle path must be a directory")], warnings=[])

    concept_ids: set[str] = set()
    markdown_paths = list(_iter_markdown_files(root))
    markdown_lookup = {_rel(path, root): path for path in markdown_paths}

    for path in markdown_paths:
        rel = _rel(path, root)
        if _is_reserved(rel):
            parsed = _read_and_parse(path, rel, max_file_bytes, errors)
            if parsed is not None:
                reserved.append({"path": rel, "frontmatter": parsed.metadata, "body_bytes": len(parsed.body.encode("utf-8"))})
                _warn_broken_links(rel, parsed.body, markdown_lookup, warnings)
            continue

        concept_id = rel[:-3] if rel.endswith(".md") else rel
        normalized_id = concept_id.casefold()
        if normalized_id in concept_ids:
            errors.append(_issue(rel, "duplicate_concept", f"duplicate concept id: {concept_id}"))
            continue
        concept_ids.add(normalized_id)

        parsed = _read_and_parse(path, rel, max_file_bytes, errors)
        if parsed is None:
            continue
        if not parsed.has_frontmatter:
            errors.append(_issue(rel, "missing_frontmatter", "concept file must start with YAML frontmatter"))
        if parsed.error:
            errors.append(_issue(rel, "invalid_frontmatter", parsed.error))
        okf_type = str(parsed.metadata.get("type") or "").strip()
        if not okf_type:
            errors.append(_issue(rel, "missing_type", "concept frontmatter must include non-empty type"))
        if not parsed.metadata.get("title"):
            warnings.append(_issue(rel, "missing_title", "concept frontmatter has no title"))
        if not parsed.metadata.get("description"):
            warnings.append(_issue(rel, "missing_description", "concept frontmatter has no description"))
        _warn_broken_links(rel, parsed.body, markdown_lookup, warnings)
        concepts.append(
            {
                "path": rel,
                "concept_id": concept_id,
                "type": okf_type,
                "title": parsed.metadata.get("title", ""),
                "description": parsed.metadata.get("description", ""),
                "tags": parsed.metadata.get("tags", []),
                "timestamp": parsed.metadata.get("timestamp", ""),
                "resource": parsed.metadata.get("resource", ""),
            }
        )

    if not any(item["path"] == "index.md" for item in reserved):
        warnings.append(_issue("index.md", "missing_index", "root index.md is recommended for progressive disclosure"))
    if not any(item["path"] == "log.md" for item in reserved):
        warnings.append(_issue("log.md", "missing_log", "root log.md is recommended for bundle history"))

    return _payload(root, concepts, reserved, errors=errors, warnings=warnings)


def import_okf_bundle(
    db: Any,
    bundle_dir: str | Path,
    *,
    dry_run: bool = False,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    layer: str = "L3",
    category: str = "",
    tags: str | list[str] = "",
    trust: float = 0.5,
    reason: str = "",
    scope: str = "project",
    sensitivity: str = "low",
    owner_agent: str = "",
    allowed_agents: str | list[str] = "",
    memory_type: str = "okf_concept",
    expires_at: str = "",
    valid_from: str = "",
    valid_until: str = "",
    supersedes_id: int | str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Import OKF concepts into memory candidates, never active knowledge."""
    validation = validate_okf_bundle(bundle_dir, max_file_bytes=max_file_bytes)
    if not validation["valid"]:
        return {
            "status": "error",
            "dry_run": dry_run,
            "bundle_dir": validation["bundle_dir"],
            "validation": validation,
            "candidate_count": 0,
            "created_count": 0,
            "rejected_count": 0,
            "candidates": [],
        }

    from .memory import create_candidate

    root = Path(bundle_dir).expanduser().resolve()
    candidates: list[dict[str, Any]] = []
    created_count = 0
    rejected_count = 0
    concept_rows = validation["concepts"]
    if limit is not None:
        concept_rows = concept_rows[: max(0, int(limit))]

    for concept in concept_rows:
        rel = str(concept["path"])
        parsed = parse_markdown_frontmatter((root / rel).read_text(encoding="utf-8"))
        meta = parsed.metadata
        okf_type = str(meta.get("type") or concept.get("type") or "").strip()
        title = str(meta.get("title") or concept.get("concept_id") or Path(rel).stem).strip()
        description = str(meta.get("description") or "").strip()
        resource = _metadata_string(meta.get("resource"))
        timestamp = _metadata_string(meta.get("timestamp"))
        concept_tags = _join_tags([tags, meta.get("tags"), "okf", okf_type])
        mapped_category = (category or okf_type or "okf").strip()
        mapped_reason = reason or f"Imported from OKF bundle path {rel}; review before promotion."
        source_ref = _source_ref(rel, resource=resource, timestamp=timestamp)
        content = _candidate_content(
            title=title,
            okf_type=okf_type,
            description=description,
            resource=resource,
            timestamp=timestamp,
            body=parsed.body,
        )
        mapped_valid_from = _metadata_string(meta.get("valid_from")) or str(valid_from or "").strip()
        mapped_valid_until = _metadata_string(meta.get("valid_until")) or str(valid_until or "").strip()
        entry = {
            "path": rel,
            "title": title,
            "type": okf_type,
            "category": mapped_category,
            "tags": concept_tags,
            "source_ref": source_ref,
            "content_preview": content[:240],
        }
        if dry_run:
            candidates.append({"status": "preview", **entry})
            continue

        result = create_candidate(
            db,
            title=title,
            content=content,
            layer=layer,
            category=mapped_category,
            tags=concept_tags,
            trust=trust,
            source="okf",
            source_ref=source_ref,
            reason=mapped_reason,
            scope=scope,
            sensitivity=sensitivity,
            owner_agent=owner_agent,
            allowed_agents=allowed_agents,
            memory_type=memory_type,
            expires_at=expires_at,
            valid_from=mapped_valid_from,
            valid_until=mapped_valid_until,
            supersedes_id=supersedes_id,
        )
        if result["status"] == "candidate_created":
            created_count += 1
        elif result["status"] == "rejected":
            rejected_count += 1
        candidates.append({**entry, **result})

    status = "preview" if dry_run else "ok"
    return {
        "status": status,
        "dry_run": dry_run,
        "bundle_dir": validation["bundle_dir"],
        "validation": validation,
        "candidate_count": len(candidates),
        "created_count": created_count,
        "rejected_count": rejected_count,
        "candidates": candidates,
    }


def _read_and_parse(path: Path, rel: str, max_file_bytes: int, errors: list[dict[str, Any]]) -> FrontmatterResult | None:
    try:
        if path.stat().st_size > max(1, max_file_bytes):
            errors.append(_issue(rel, "file_too_large", f"file exceeds {max_file_bytes} bytes"))
            return None
        return parse_markdown_frontmatter(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        errors.append(_issue(rel, "invalid_utf8", str(exc)))
    except OSError as exc:
        errors.append(_issue(rel, "read_error", str(exc)))
    return None


def _iter_markdown_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.md"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_symlink():
            continue
        if path.is_file():
            files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def _warn_broken_links(rel: str, body: str, markdown_lookup: dict[str, Path], warnings: list[dict[str, Any]]) -> None:
    base = Path(rel).parent
    for raw_target in LOCAL_MARKDOWN_LINK.findall(body or ""):
        target = raw_target.split("#", 1)[0].strip()
        if not target:
            continue
        if target.startswith("/"):
            normalized = target.lstrip("/")
        else:
            normalized = (base / target).as_posix()
        if not normalized.endswith(".md"):
            normalized = f"{normalized}.md"
        normalized = posixpath.normpath(normalized.replace("\\", "/"))
        if normalized.startswith("../") or normalized not in markdown_lookup:
            warnings.append(_issue(rel, "broken_link", f"missing local markdown target: {raw_target}"))


def _join_tags(values: list[Any]) -> str:
    tags: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            items = value
        else:
            items = str(value).split(",")
        for item in items:
            tag = str(item).strip()
            if tag and tag not in tags:
                tags.append(tag)
    return ",".join(tags)


def _metadata_string(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        text = value.isoformat()
        if text.endswith("+00:00"):
            text = f"{text[:-6]}Z"
        return text
    return str(value).strip()


def _source_ref(path: str, *, resource: str = "", timestamp: str = "") -> str:
    parts = [f"okf:{path}"]
    if resource:
        parts.append(f"resource={resource}")
    if timestamp:
        parts.append(f"timestamp={timestamp}")
    return " ".join(parts)


def _candidate_content(
    *,
    title: str,
    okf_type: str,
    description: str,
    resource: str,
    timestamp: str,
    body: str,
) -> str:
    parts = [f"# {title}"]
    if okf_type:
        parts.append(f"OKF type: {okf_type}")
    if description:
        parts.append(description)
    if resource:
        parts.append(f"Resource: {resource}")
    if timestamp:
        parts.append(f"Timestamp: {timestamp}")
    if body:
        parts.append(body.strip())
    return "\n\n".join(parts).strip()


def _is_reserved(rel: str) -> bool:
    return Path(rel).name in RESERVED_FILES


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _issue(path: str, code: str, message: str) -> dict[str, str]:
    return {"path": path, "code": code, "message": message}


def _payload(
    root: Path,
    concepts: list[dict[str, Any]],
    reserved: list[dict[str, Any]],
    *,
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    status = "error" if errors else "warn" if warnings else "ok"
    return {
        "status": status,
        "valid": not errors,
        "bundle_dir": str(root),
        "concept_count": len(concepts),
        "reserved_count": len(reserved),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "concepts": concepts,
        "reserved": reserved,
        "errors": errors,
        "warnings": warnings,
    }
