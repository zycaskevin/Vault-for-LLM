"""Candidate-first migration helpers for external memory exports."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import VaultDB
from .memory import (
    create_candidate,
    duplicate_gate,
    metadata_gate,
    normalize_metadata,
    quality_gate,
)
from .okf import parse_markdown_frontmatter
from .privacy import scan_privacy


SUPPORTED_FORMATS = {"auto", "markdown", "json", "csv", "okf", "transcript"}
DEFAULT_MAX_FILE_BYTES = 2_000_000
SKIP_DIRS = {".git", ".obsidian", ".trash", "__pycache__", "node_modules"}


@dataclass(frozen=True)
class MigrationItem:
    title: str
    content: str
    source_system: str
    source_ref: str
    external_id: str = ""
    created_at: str = ""
    memory_type: str = "imported_memory"
    tags: str = ""
    confidence: float = 0.5
    raw_metadata: dict[str, Any] | None = None


def migrate_memory_source(
    db: VaultDB,
    source: str | Path,
    *,
    source_format: str = "auto",
    dry_run: bool = True,
    layer: str = "L3",
    category: str = "",
    tags: str | list[str] = "",
    trust: float = 0.5,
    reason: str = "",
    scope: str = "project",
    sensitivity: str = "low",
    owner_agent: str = "",
    allowed_agents: str | list[str] = "",
    memory_type: str = "",
    expires_at: str = "",
    valid_from: str = "",
    valid_until: str = "",
    supersedes_id: int | str | None = None,
    only: str | list[str] = "",
    limit: int | None = None,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> dict[str, Any]:
    """Preview or write external memory exports into ``memory_candidates``."""
    source_path = Path(source).expanduser()
    fmt = _normalize_format(source_format)
    if not source_path.exists():
        return _payload(
            source_path,
            fmt,
            dry_run=dry_run,
            status="error",
            errors=[{"code": "source_missing", "message": "source path does not exist"}],
        )

    if fmt == "auto":
        fmt = _detect_format(source_path)

    if fmt == "okf":
        from .okf import import_okf_bundle

        return import_okf_bundle(
            db,
            source_path,
            dry_run=dry_run,
            max_file_bytes=max_file_bytes,
            layer=layer,
            category=category,
            tags=tags,
            trust=trust,
            reason=reason or "Imported from external OKF memory bundle; review before promotion.",
            scope=scope,
            sensitivity=sensitivity,
            owner_agent=owner_agent,
            allowed_agents=allowed_agents,
            memory_type=memory_type or "okf_concept",
            expires_at=expires_at,
            valid_from=valid_from,
            valid_until=valid_until,
            supersedes_id=supersedes_id,
            limit=limit,
        )

    errors: list[dict[str, Any]] = []
    items = _load_items(source_path, fmt, max_file_bytes=max_file_bytes, errors=errors)
    allowed_kinds = _parse_only(only)
    if allowed_kinds:
        items = [item for item in items if _item_kind(item) in allowed_kinds]
    if limit is not None:
        items = items[: max(0, int(limit))]

    candidates: list[dict[str, Any]] = []
    created_count = 0
    rejected_count = 0
    privacy_fail = 0
    duplicate_warn = 0
    skipped_count = 0

    for item in items:
        if not item.title.strip() or not item.content.strip():
            skipped_count += 1
            candidates.append(
                {
                    "status": "skipped",
                    "title": item.title,
                    "source_ref": item.source_ref,
                    "reason": "missing title or content",
                }
            )
            continue
        mapped_tags = _join_tags([tags, item.tags, item.source_system, "migration"])
        mapped_memory_type = memory_type or item.memory_type or "imported_memory"
        mapped_category = category or _category_for(item)
        mapped_reason = reason or f"Imported from {item.source_system}; review before promotion."
        source_ref = item.source_ref or f"migration:{item.source_system}:{item.external_id or item.title}"
        item_valid_from = valid_from or item.created_at
        meta = normalize_metadata(
            item.title,
            item.content,
            layer=layer,
            category=mapped_category,
            tags=mapped_tags,
            trust=trust if trust != 0.5 else item.confidence,
            source=f"migration:{item.source_system}",
            source_ref=source_ref,
            reason=mapped_reason,
            scope=scope,
            sensitivity=sensitivity,
            owner_agent=owner_agent,
            allowed_agents=allowed_agents,
            memory_type=mapped_memory_type,
            expires_at=expires_at,
            valid_from=item_valid_from,
            valid_until=valid_until,
            supersedes_id=supersedes_id,
        )
        preview = _preview_candidate(db, meta, item)
        if preview["gates"]["privacy"] == "fail":
            privacy_fail += 1
        if preview["gates"]["duplicate"] == "warn":
            duplicate_warn += 1
        if dry_run:
            candidates.append(preview)
            continue
        result = create_candidate(db, **meta)
        if result["status"] == "rejected":
            rejected_count += 1
        else:
            created_count += 1
        candidates.append({**preview, **result, "status": result["status"]})

    status = "preview" if dry_run else "ok"
    if errors:
        status = "warn" if candidates else "error"
    return _payload(
        source_path,
        fmt,
        dry_run=dry_run,
        status=status,
        items=items,
        candidates=candidates,
        created_count=created_count,
        rejected_count=rejected_count,
        skipped_count=skipped_count,
        privacy_fail=privacy_fail,
        duplicate_warn=duplicate_warn,
        errors=errors,
        only=sorted(allowed_kinds),
    )


def _normalize_format(value: str) -> str:
    fmt = str(value or "auto").strip().lower()
    if fmt not in SUPPORTED_FORMATS:
        allowed = ", ".join(sorted(SUPPORTED_FORMATS))
        raise ValueError(f"unsupported memory import format: {value} (expected {allowed})")
    return fmt


def _detect_format(path: Path) -> str:
    if path.is_dir():
        if (path / "index.md").exists() and (path / "log.md").exists():
            return "okf"
        return "markdown"
    suffix = path.suffix.lower()
    if suffix in {".json", ".jsonl"}:
        return "json" if suffix == ".json" else "transcript"
    if suffix == ".csv":
        return "csv"
    if suffix in {".md", ".markdown", ".txt"}:
        name = path.name.lower()
        return "transcript" if any(token in name for token in ("chat", "transcript", "conversation")) else "markdown"
    return "markdown"


def _load_items(path: Path, fmt: str, *, max_file_bytes: int, errors: list[dict[str, Any]]) -> list[MigrationItem]:
    if fmt == "markdown":
        return _load_markdown_items(path, max_file_bytes=max_file_bytes, errors=errors)
    if fmt == "json":
        return _load_json_items(path, max_file_bytes=max_file_bytes, errors=errors)
    if fmt == "csv":
        return _load_csv_items(path, max_file_bytes=max_file_bytes, errors=errors)
    if fmt == "transcript":
        return _load_transcript_items(path, max_file_bytes=max_file_bytes, errors=errors)
    raise ValueError(f"unsupported memory import format: {fmt}")


def _load_markdown_items(path: Path, *, max_file_bytes: int, errors: list[dict[str, Any]]) -> list[MigrationItem]:
    files = _iter_files(path, {".md", ".markdown", ".txt"}) if path.is_dir() else [path]
    items: list[MigrationItem] = []
    root = path if path.is_dir() else path.parent
    for file_path in files:
        text = _read_text(file_path, root, max_file_bytes=max_file_bytes, errors=errors)
        if text is None:
            continue
        parsed = parse_markdown_frontmatter(text)
        meta = parsed.metadata
        body = parsed.body if parsed.has_frontmatter else text
        title = _first_nonempty(
            _metadata_string(meta.get("title")),
            _first_heading(body),
            file_path.stem.replace("_", " ").replace("-", " "),
        )
        rel = _relative_ref(file_path, root)
        items.append(
            MigrationItem(
                title=title,
                content=body.strip(),
                source_system=_metadata_string(meta.get("source_system")) or "markdown",
                source_ref=f"migration:markdown:{rel}",
                external_id=_metadata_string(meta.get("external_id")) or rel,
                created_at=_metadata_string(meta.get("created_at")) or _metadata_string(meta.get("timestamp")),
                memory_type=_metadata_string(meta.get("memory_type")) or "imported_note",
                tags=_join_tags([meta.get("tags")]),
                confidence=_float(meta.get("confidence"), 0.6),
                raw_metadata=meta,
            )
        )
    return items


def _load_json_items(path: Path, *, max_file_bytes: int, errors: list[dict[str, Any]]) -> list[MigrationItem]:
    text = _read_text(path, path.parent, max_file_bytes=max_file_bytes, errors=errors)
    if text is None:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        errors.append(_issue(str(path), "invalid_json", str(exc)))
        return []
    rows = _extract_json_rows(payload)
    items: list[MigrationItem] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        items.append(_item_from_mapping(row, idx=idx, source_system="json"))
    return items


def _load_csv_items(path: Path, *, max_file_bytes: int, errors: list[dict[str, Any]]) -> list[MigrationItem]:
    text = _read_text(path, path.parent, max_file_bytes=max_file_bytes, errors=errors)
    if text is None:
        return []
    rows = csv.DictReader(text.splitlines())
    return [_item_from_mapping(dict(row), idx=idx, source_system="csv") for idx, row in enumerate(rows)]


def _load_transcript_items(path: Path, *, max_file_bytes: int, errors: list[dict[str, Any]]) -> list[MigrationItem]:
    files = _iter_files(path, {".jsonl", ".json", ".md", ".txt"}) if path.is_dir() else [path]
    items: list[MigrationItem] = []
    root = path if path.is_dir() else path.parent
    for file_path in files:
        text = _read_text(file_path, root, max_file_bytes=max_file_bytes, errors=errors)
        if text is None:
            continue
        content = _transcript_text(text, file_path)
        rel = _relative_ref(file_path, root)
        items.append(
            MigrationItem(
                title=f"Conversation import: {file_path.stem.replace('_', ' ').replace('-', ' ')}",
                content=content,
                source_system=_infer_chat_source(file_path),
                source_ref=f"migration:transcript:{rel}",
                external_id=rel,
                memory_type="imported_conversation",
                tags="conversation,transcript",
                confidence=0.45,
                raw_metadata={"path": rel},
            )
        )
    return items


def _extract_json_rows(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("memories", "items", "entries", "knowledge", "messages", "conversations", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return [payload]


def _item_from_mapping(row: dict[str, Any], *, idx: int, source_system: str) -> MigrationItem:
    messages = row.get("messages") if isinstance(row.get("messages"), list) else None
    content = _first_nonempty(
        _metadata_string(row.get("content")),
        _metadata_string(row.get("text")),
        _metadata_string(row.get("body")),
        _metadata_string(row.get("summary")),
        _join_messages(messages or []),
    )
    title = _first_nonempty(
        _metadata_string(row.get("title")),
        _metadata_string(row.get("name")),
        _first_heading(content),
        f"Imported memory {idx + 1}",
    )
    detected_source = _metadata_string(row.get("source_system")) or _metadata_string(row.get("source")) or source_system
    external_id = _metadata_string(row.get("id")) or _metadata_string(row.get("external_id")) or str(idx + 1)
    return MigrationItem(
        title=title,
        content=content,
        source_system=detected_source,
        source_ref=_metadata_string(row.get("source_ref")) or f"migration:{detected_source}:{external_id}",
        external_id=external_id,
        created_at=_metadata_string(row.get("created_at")) or _metadata_string(row.get("timestamp")) or _metadata_string(row.get("date")),
        memory_type=_metadata_string(row.get("memory_type")) or _metadata_string(row.get("type")) or "imported_memory",
        tags=_join_tags([row.get("tags"), row.get("tag")]),
        confidence=_float(row.get("confidence"), _float(row.get("trust"), 0.5)),
        raw_metadata=row,
    )


def _preview_candidate(db: VaultDB, meta: dict[str, Any], item: MigrationItem) -> dict[str, Any]:
    privacy = scan_privacy("\n".join([meta["title"], meta["content"], meta["source_ref"], meta["reason"]]))
    duplicate = duplicate_gate(db, meta["title"], meta["content"])
    metadata = metadata_gate(meta)
    quality = quality_gate(meta)
    status = "rejected" if privacy["status"] == "fail" or metadata["status"] == "fail" else "preview"
    return {
        "status": status,
        "title": meta["title"],
        "source_system": item.source_system,
        "source_ref": meta["source_ref"],
        "external_id": item.external_id,
        "memory_type": meta["memory_type"],
        "category": meta["category"],
        "tags": meta["tags"],
        "scope": meta["scope"],
        "sensitivity": meta["sensitivity"],
        "content_preview": " ".join(meta["content"].split())[:240],
        "content_length": len(meta["content"]),
        "gates": {
            "privacy": privacy["status"],
            "duplicate": duplicate["status"],
            "metadata": metadata["status"],
            "quality": quality["status"],
        },
        "gate_payload": {"privacy": privacy, "duplicate": duplicate, "metadata": metadata, "quality": quality},
        "recommended_action": "review_before_promote",
    }


def _payload(
    source_path: Path,
    source_format: str,
    *,
    dry_run: bool,
    status: str,
    items: list[MigrationItem] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    created_count: int = 0,
    rejected_count: int = 0,
    skipped_count: int = 0,
    privacy_fail: int = 0,
    duplicate_warn: int = 0,
    errors: list[dict[str, Any]] | None = None,
    only: list[str] | None = None,
) -> dict[str, Any]:
    items = items or []
    candidates = candidates or []
    errors = errors or []
    return {
        "status": status,
        "dry_run": dry_run,
        "source": str(source_path),
        "format": source_format,
        "item_count": len(items),
        "candidate_count": len(candidates),
        "created_count": created_count,
        "rejected_count": rejected_count,
        "skipped_count": skipped_count,
        "privacy_fail": privacy_fail,
        "duplicate_warn": duplicate_warn,
        "error_count": len(errors),
        "errors": errors,
        "only": only or [],
        "safety": {
            "candidate_first": True,
            "writes_active_knowledge": False,
            "raw_private_content_hidden_by_default": True,
        },
        "candidates": candidates,
    }


def _iter_files(root: Path, suffixes: set[str]) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix.lower() in suffixes:
            files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def _read_text(path: Path, root: Path, *, max_file_bytes: int, errors: list[dict[str, Any]]) -> str | None:
    rel = _relative_ref(path, root)
    try:
        if path.stat().st_size > max(1, max_file_bytes):
            errors.append(_issue(rel, "file_too_large", f"file exceeds {max_file_bytes} bytes"))
            return None
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        errors.append(_issue(rel, "invalid_utf8", str(exc)))
    except OSError as exc:
        errors.append(_issue(rel, "read_error", str(exc)))
    return None


def _transcript_text(text: str, path: Path) -> str:
    if path.suffix.lower() == ".jsonl":
        lines: list[str] = []
        for raw in text.splitlines():
            if not raw.strip():
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                lines.append(raw.strip())
                continue
            if isinstance(item, dict):
                role = _metadata_string(item.get("role")) or _metadata_string(item.get("author")) or "message"
                content = _metadata_string(item.get("content")) or _metadata_string(item.get("text")) or _metadata_string(item.get("message"))
                if content:
                    lines.append(f"{role}: {content}")
        return "\n".join(lines).strip()
    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return text.strip()
        rows = _extract_json_rows(payload)
        if rows and all(isinstance(row, dict) for row in rows):
            joined = _join_messages(rows) if rows and rows[0].get("role") else ""
            if joined:
                return joined
            return "\n\n".join(_item_from_mapping(row, idx=i, source_system="transcript").content for i, row in enumerate(rows))
    return text.strip()


def _join_messages(messages: list[Any]) -> str:
    lines: list[str] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = _metadata_string(item.get("role")) or _metadata_string(item.get("author")) or "message"
        content = _metadata_string(item.get("content")) or _metadata_string(item.get("text")) or _metadata_string(item.get("message"))
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines).strip()


def _parse_only(value: str | list[str]) -> set[str]:
    if isinstance(value, list):
        raw = ",".join(value)
    else:
        raw = str(value or "")
    aliases = {
        "project-knowledge": "project_knowledge",
        "project": "project_knowledge",
        "knowledge": "project_knowledge",
        "preference": "preferences",
        "prefs": "preferences",
        "decision": "decisions",
        "summary": "summaries",
    }
    result = set()
    for item in raw.split(","):
        token = item.strip().lower().replace(" ", "-")
        if not token:
            continue
        result.add(aliases.get(token, token.replace("-", "_")))
    return result


def _item_kind(item: MigrationItem) -> str:
    blob = f"{item.title}\n{item.content}\n{item.memory_type}\n{item.tags}".casefold()
    if any(token in blob for token in ("decision", "decided", "決策", "決定")):
        return "decisions"
    if any(token in blob for token in ("prefer", "preference", "avoid", "偏好", "喜歡", "避免")):
        return "preferences"
    if any(token in blob for token in ("summary", "摘要", "recap")):
        return "summaries"
    if any(token in blob for token in ("project", "deploy", "api", "bug", "fix", "sop", "架構", "部署", "錯誤", "修復")):
        return "project_knowledge"
    return "summaries" if item.memory_type == "imported_conversation" else "project_knowledge"


def _category_for(item: MigrationItem) -> str:
    kind = _item_kind(item)
    return {
        "decisions": "decision",
        "preferences": "preference",
        "summaries": "summary",
        "project_knowledge": "knowledge",
    }.get(kind, "migration")


def _infer_chat_source(path: Path) -> str:
    name = path.name.casefold()
    for source in ("chatgpt", "claude", "chatbox", "codex", "hermes", "openclaw"):
        if source in name:
            return source
    return "transcript"


def _relative_ref(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _first_heading(text: str) -> str:
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def _first_nonempty(*values: str) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _metadata_string(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def _float(value: Any, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _join_tags(values: list[Any]) -> str:
    tags: list[str] = []
    for value in values:
        if not value:
            continue
        if isinstance(value, (list, tuple, set)):
            parts = value
        else:
            parts = str(value).split(",")
        for part in parts:
            tag = str(part).strip()
            if tag and tag not in tags:
                tags.append(tag)
    return ",".join(tags)


def _issue(path: str, code: str, message: str) -> dict[str, str]:
    return {"path": path, "code": code, "message": message}
