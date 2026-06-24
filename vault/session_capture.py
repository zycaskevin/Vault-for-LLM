"""Capture agent session transcripts into reviewable memory candidates."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import VaultDB
from .memory import (
    duplicate_gate,
    metadata_gate,
    normalize_metadata,
    propose_memory,
    quality_gate,
)
from .privacy import redact_secrets, scan_privacy


_MAX_UNIT_CHARS = 900
_MIN_UNIT_CHARS = 35
_DISCOVERY_SUFFIXES = {".jsonl", ".md", ".markdown", ".txt", ".log"}
_DISCOVERY_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".obsidian",
    ".trash",
}


@dataclass(frozen=True)
class SessionUnit:
    text: str
    ref: str
    role: str = ""


@dataclass(frozen=True)
class CaptureRule:
    name: str
    category: str
    tags: tuple[str, ...]
    pattern: re.Pattern[str]
    reason: str


@dataclass(frozen=True)
class DiscoveredTranscript:
    path: Path
    source_system: str
    input_format: str
    size_bytes: int
    modified_at: str
    score: float
    reasons: tuple[str, ...]


CAPTURE_RULES: tuple[CaptureRule, ...] = (
    CaptureRule(
        "decision",
        "decision",
        ("session-capture", "decision"),
        re.compile(r"(?i)\b(decision|decided|choose|chosen|prefer|selected)\b|決定|決策|選擇|採用|偏好"),
        "Session line contains a reusable decision or preference.",
    ),
    CaptureRule(
        "pitfall",
        "error",
        ("session-capture", "pitfall"),
        re.compile(r"(?i)\b(error|bug|failed|failure|root cause|regression|fix|fixed)\b|錯誤|失敗|問題|踩坑|原因|修復"),
        "Session line contains a reusable bug, failure, or fix signal.",
    ),
    CaptureRule(
        "workflow",
        "workflow",
        ("session-capture", "workflow"),
        re.compile(r"(?i)\b(always|never|must|should|workflow|runbook|sop|install|deploy|command)\b|必須|不要|不能|流程|步驟|安裝|部署|指令|規則"),
        "Session line contains reusable workflow or operating guidance.",
    ),
    CaptureRule(
        "source_of_truth",
        "source-of-truth",
        ("session-capture", "source-of-truth"),
        re.compile(r"(?i)\b(source of truth|canonical|official|single source)\b|正式來源|唯一來源|真相源|官方文件"),
        "Session line identifies source-of-truth or canonical context.",
    ),
)


def discover_session_transcripts(
    project_dir: str | Path,
    *,
    search_dirs: list[str | Path] | None = None,
    source_system: str = "auto",
    limit: int = 10,
    max_depth: int = 3,
    max_file_mb: float = 5.0,
    allow_absolute_paths: bool = False,
) -> dict[str, Any]:
    """Find likely session transcript exports without reading their contents."""
    root = Path(project_dir).expanduser().resolve()
    limit = max(1, min(int(limit or 10), 100))
    max_depth = max(0, min(int(max_depth or 3), 8))
    try:
        max_bytes = max(1, int(float(max_file_mb or 5.0) * 1024 * 1024))
    except (TypeError, ValueError):
        max_bytes = 5 * 1024 * 1024
    roots = _discovery_roots(root, search_dirs=search_dirs, allow_absolute_paths=allow_absolute_paths)

    seen: set[Path] = set()
    candidates: list[DiscoveredTranscript] = []
    skipped = {"missing": 0, "outside_project": 0, "too_large": 0, "unsupported": 0}
    for base in roots:
        if not base.exists() or not base.is_dir():
            skipped["missing"] += 1
            continue
        for path in _iter_discovery_files(base, max_depth=max_depth):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            suffix = resolved.suffix.lower()
            if suffix not in _DISCOVERY_SUFFIXES:
                skipped["unsupported"] += 1
                continue
            try:
                resolved.relative_to(root)
            except ValueError:
                if not allow_absolute_paths:
                    skipped["outside_project"] += 1
                    continue
            stat = resolved.stat()
            if stat.st_size > max_bytes:
                skipped["too_large"] += 1
                continue
            discovered = _score_discovered_transcript(
                resolved,
                root=root,
                stat_size=stat.st_size,
                stat_mtime=stat.st_mtime,
                source_system=source_system,
            )
            if discovered.score < 0.35:
                continue
            candidates.append(discovered)

    candidates.sort(key=lambda item: (-item.score, item.path.name.lower(), str(item.path)))
    selected = candidates[:limit]
    return {
        "action": "discover_session_transcripts",
        "status": "completed",
        "project_dir": str(root),
        "source_system": str(source_system or "auto"),
        "limit": limit,
        "max_depth": max_depth,
        "max_file_mb": max_file_mb,
        "read_contents": False,
        "count": len(selected),
        "scanned_roots": [str(path) for path in roots],
        "skipped": skipped,
        "transcripts": [_format_discovered_transcript(item, root=root) for item in selected],
        "next_action": "Run `vault capture session <path> --pretty` to preview a selected transcript.",
    }


def capture_session_candidates(
    db: VaultDB,
    transcript_path: str | Path,
    *,
    input_format: str = "auto",
    source_system: str = "auto",
    agent_id: str = "",
    write_candidates: bool = False,
    max_candidates: int = 20,
    min_score: float = 0.55,
    scope: str = "project",
    sensitivity: str = "low",
    owner_agent: str = "",
    allowed_agents: str | list[str] = "",
    include_content: bool = False,
) -> dict[str, Any]:
    """Extract reviewable candidate memories from a session transcript.

    The extractor is deterministic and intentionally conservative. It never
    promotes active memory and only writes rows when ``write_candidates`` is
    true.
    """
    path = Path(transcript_path).expanduser()
    units = load_session_units(path, input_format=input_format)
    detected_source = _detect_source_system(path, source_system)
    max_candidates = max(1, min(int(max_candidates or 20), 200))
    try:
        min_score_f = max(0.0, min(1.0, float(min_score)))
    except (TypeError, ValueError):
        min_score_f = 0.55

    proposals = _extract_proposals(
        units,
        path=path,
        source_system=detected_source,
        agent_id=agent_id,
        max_candidates=max_candidates,
        min_score=min_score_f,
        scope=scope,
        sensitivity=sensitivity,
        owner_agent=owner_agent or agent_id,
        allowed_agents=allowed_agents,
    )

    results: list[dict[str, Any]] = []
    written_count = 0
    rejected_count = 0
    for proposal in proposals:
        if write_candidates:
            result = propose_memory(db, mode="candidate", **_memory_kwargs(proposal))
            written_count += 1
            if result.get("status") == "rejected":
                rejected_count += 1
            output_content = _safe_output_content(proposal["content"], result.get("gates") or {})
            output_title = _safe_output_content(proposal["title"], result.get("gates") or {})
            item = {
                "title": output_title,
                "score": proposal["capture_score"],
                "rule": proposal["capture_rule"],
                "source_ref": proposal["source_ref"],
                "status": result.get("status"),
                "candidate_id": result.get("candidate_id"),
                "gates": result.get("gates"),
            }
        else:
            gates = _preview_gates(db, proposal)
            output_content = _safe_output_content(proposal["content"], gates["statuses"])
            output_title = _safe_output_content(proposal["title"], gates["statuses"])
            gate_payload = (
                _redact_payload_strings(gates["payload"])
                if gates["statuses"].get("privacy") == "fail"
                else gates["payload"]
            )
            item = {
                "title": output_title,
                "score": proposal["capture_score"],
                "rule": proposal["capture_rule"],
                "source_ref": proposal["source_ref"],
                "status": "preview",
                "would_write": True,
                "gates": gates["statuses"],
                "gate_payload": gate_payload,
            }
        if include_content:
            item["content"] = output_content
        else:
            item["content_preview"] = " ".join(output_content.split())[:220]
        results.append(item)

    return {
        "action": "capture_session",
        "status": "completed",
        "source_system": detected_source,
        "transcript_path": str(path),
        "input_format": _resolve_input_format(path, input_format),
        "write_candidates": bool(write_candidates),
        "units_scanned": len(units),
        "extracted": len(proposals),
        "written": written_count,
        "rejected": rejected_count,
        "min_score": min_score_f,
        "candidates": results,
        "safety": {
            "candidate_first": True,
            "auto_promote": False,
            "hard_delete": False,
            "privacy_gate": True,
        },
        "next_action": (
            "Run `vault candidates --include-gates` to review captured memories."
            if write_candidates
            else "Re-run with --write-candidates after reviewing this dry-run preview."
        ),
    }


def load_session_units(path: Path, *, input_format: str = "auto") -> list[SessionUnit]:
    resolved_format = _resolve_input_format(path, input_format)
    text = path.read_text(encoding="utf-8")
    if resolved_format == "jsonl":
        units: list[SessionUnit] = []
        for index, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                units.extend(_split_text_units(line, ref=f"L{index}"))
                continue
            units.extend(_units_from_json_object(obj, ref=f"jsonl:{index}"))
        return _dedupe_units(units)
    return _dedupe_units(_split_text_units(text, ref="text"))


def _discovery_roots(
    project_dir: Path,
    *,
    search_dirs: list[str | Path] | None,
    allow_absolute_paths: bool,
) -> list[Path]:
    if search_dirs:
        roots: list[Path] = []
        for raw in search_dirs:
            if raw is None:
                continue
            path = Path(raw).expanduser()
            resolved = path.resolve() if path.is_absolute() else (project_dir / path).resolve()
            if path.is_absolute() and not allow_absolute_paths:
                continue
            roots.append(resolved)
        return _dedupe_paths(roots)

    defaults = [
        project_dir,
        project_dir / "sessions",
        project_dir / "transcripts",
        project_dir / "exports",
        project_dir / "agent-sessions",
        project_dir / "reports",
    ]
    return _dedupe_paths(defaults)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    deduped: list[Path] = []
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return deduped


def _iter_discovery_files(root: Path, *, max_depth: int) -> list[Path]:
    files: list[Path] = []
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda item: item.name.lower())
        except (OSError, PermissionError):
            continue
        for entry in entries:
            name = entry.name
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if name.startswith(".") or name in _DISCOVERY_SKIP_DIRS:
                    continue
                if depth < max_depth:
                    stack.append((entry, depth + 1))
                continue
            if entry.is_file():
                files.append(entry)
    return files


def _score_discovered_transcript(
    path: Path,
    *,
    root: Path,
    stat_size: int,
    stat_mtime: float,
    source_system: str,
) -> DiscoveredTranscript:
    reasons: list[str] = []
    name = path.name.lower()
    text = str(path).lower()
    score = 0.0
    if path.suffix.lower() == ".jsonl":
        score += 0.25
        reasons.append("jsonl export")
    elif path.suffix.lower() in {".md", ".markdown", ".txt"}:
        score += 0.15
        reasons.append("text transcript format")
    if re.search(r"(session|transcript|conversation|chat|export|handoff)", name):
        score += 0.30
        reasons.append("session-like filename")
    if re.search(r"(codex|hermes|openclaw|claude|opencode)", text):
        score += 0.20
        reasons.append("agent-like path")
    if str(source_system or "auto").lower() not in {"", "auto"}:
        wanted = str(source_system).lower()
        if wanted in text:
            score += 0.20
            reasons.append(f"matches source_system={wanted}")
        else:
            score -= 0.15
    if stat_size < 512:
        score -= 0.15
    elif stat_size <= 1024 * 1024:
        score += 0.10
        reasons.append("reasonable size")
    try:
        path.relative_to(root)
        score += 0.05
        reasons.append("inside project")
    except ValueError:
        pass

    detected_source = _detect_source_system(path, source_system)
    modified = datetime.fromtimestamp(stat_mtime, tz=timezone.utc).isoformat()
    return DiscoveredTranscript(
        path=path,
        source_system=detected_source,
        input_format=_resolve_input_format(path, "auto"),
        size_bytes=stat_size,
        modified_at=modified,
        score=round(max(0.0, min(score, 1.0)), 3),
        reasons=tuple(reasons),
    )


def _format_discovered_transcript(item: DiscoveredTranscript, *, root: Path) -> dict[str, Any]:
    try:
        capture_path = str(item.path.relative_to(root))
        path_scope = "project"
    except ValueError:
        capture_path = str(item.path)
        path_scope = "absolute"
    return {
        "path": str(item.path),
        "capture_path": capture_path,
        "path_scope": path_scope,
        "source_system": item.source_system,
        "format": item.input_format,
        "size_bytes": item.size_bytes,
        "modified_at": item.modified_at,
        "score": item.score,
        "reasons": list(item.reasons),
        "next_command": f"vault capture session {json.dumps(capture_path)} --pretty",
    }


def _resolve_input_format(path: Path, input_format: str) -> str:
    normalized = str(input_format or "auto").lower()
    if normalized in {"jsonl", "markdown", "md", "text", "txt"}:
        return "markdown" if normalized == "md" else "text" if normalized == "txt" else normalized
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return "jsonl"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    return "text"


def _detect_source_system(path: Path, source_system: str) -> str:
    normalized = str(source_system or "auto").strip().lower()
    if normalized and normalized != "auto":
        return normalized
    name = path.name.lower()
    if "codex" in name:
        return "codex"
    if "hermes" in name:
        return "hermes"
    if "openclaw" in name:
        return "openclaw"
    if "claude" in name:
        return "claude-code"
    return "agent-session"


def _units_from_json_object(obj: Any, *, ref: str) -> list[SessionUnit]:
    role = ""
    if isinstance(obj, dict):
        role = str(obj.get("role") or obj.get("author") or obj.get("speaker") or "")
    units: list[SessionUnit] = []
    for text in _extract_text_values(obj):
        units.extend(_split_text_units(text, ref=ref, role=role))
    return units


def _extract_text_values(obj: Any) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, list):
        values: list[str] = []
        for item in obj:
            values.extend(_extract_text_values(item))
        return values
    if not isinstance(obj, dict):
        return []

    preferred: list[str] = []
    for key in ("text", "content", "message", "summary", "body", "output", "response"):
        if key in obj:
            preferred.extend(_extract_text_values(obj[key]))
    if preferred:
        return preferred

    values: list[str] = []
    ignored = {"id", "uuid", "created_at", "updated_at", "timestamp", "role", "author", "speaker"}
    for key, value in obj.items():
        if key in ignored:
            continue
        values.extend(_extract_text_values(value))
    return values


def _split_text_units(text: str, *, ref: str, role: str = "") -> list[SessionUnit]:
    units: list[SessionUnit] = []
    for index, raw in enumerate(str(text or "").splitlines(), start=1):
        line = _clean_line(raw)
        if not _is_candidate_line(line):
            continue
        line_ref = ref if ref.startswith("jsonl:") else f"{ref}:{index}"
        units.append(SessionUnit(text=line[:_MAX_UNIT_CHARS], ref=line_ref, role=role))
    return units


def _clean_line(line: str) -> str:
    line = re.sub(r"^\s{0,4}(?:[-*]|\d+[.)])\s+", "", line or "").strip()
    line = re.sub(r"^>+\s*", "", line)
    line = re.sub(r"^(assistant|user|system|agent|codex|hermes|claude)\s*:\s*", "", line, flags=re.I)
    return " ".join(line.split())


def _is_candidate_line(line: str) -> bool:
    if len(line) < _MIN_UNIT_CHARS:
        return False
    if line.startswith(("http://", "https://", "{", "}", "[", "]")):
        return False
    if re.fullmatch(r"[-_=#`~]{3,}", line):
        return False
    if len(line) > _MAX_UNIT_CHARS * 2:
        return False
    return True


def _dedupe_units(units: list[SessionUnit]) -> list[SessionUnit]:
    seen: set[str] = set()
    deduped: list[SessionUnit] = []
    for unit in units:
        key = re.sub(r"\s+", " ", unit.text).casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(unit)
    return deduped


def _extract_proposals(
    units: list[SessionUnit],
    *,
    path: Path,
    source_system: str,
    agent_id: str,
    max_candidates: int,
    min_score: float,
    scope: str,
    sensitivity: str,
    owner_agent: str,
    allowed_agents: str | list[str],
) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    seen_content: set[str] = set()
    for unit in units:
        scored = _score_unit(unit.text)
        if not scored:
            continue
        rule, score = scored
        if score < min_score:
            continue
        content = _candidate_content(unit, path=path, source_system=source_system)
        content_key = re.sub(r"\s+", " ", content).casefold()
        if content_key in seen_content:
            continue
        seen_content.add(content_key)
        title = _candidate_title(rule, unit.text)
        proposals.append(
            {
                "title": title,
                "content": content,
                "reason": rule.reason,
                "layer": "L2",
                "category": rule.category,
                "tags": ",".join(rule.tags),
                "trust": round(score, 2),
                "source": "session_capture",
                "source_ref": f"{source_system}:{path.name}:{unit.ref}",
                "scope": scope,
                "sensitivity": sensitivity,
                "owner_agent": owner_agent,
                "allowed_agents": allowed_agents,
                "memory_type": "session_lesson",
                "capture_score": round(score, 3),
                "capture_rule": rule.name,
                "agent_id": agent_id,
            }
        )
    proposals.sort(key=lambda item: (-float(item["capture_score"]), item["source_ref"], item["title"]))
    return proposals[:max_candidates]


def _score_unit(text: str) -> tuple[CaptureRule, float] | None:
    best: tuple[CaptureRule, float] | None = None
    for rule in CAPTURE_RULES:
        matches = rule.pattern.findall(text)
        if not matches:
            continue
        score = min(0.95, 0.5 + 0.15 * len(matches))
        if re.search(r"(?i)\b(because|therefore|so that|root cause|next time)\b|因為|因此|所以|下次", text):
            score += 0.08
        if re.search(r"(?i)\b(must|never|always|do not|cannot)\b|必須|不要|不能|絕對", text):
            score += 0.07
        score = min(1.0, score)
        if best is None or score > best[1]:
            best = (rule, score)
    return best


def _candidate_title(rule: CaptureRule, text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip(" -:：")
    compact = re.sub(r"^[#>*`\s-]+", "", compact)
    if len(compact) > 72:
        compact = compact[:69].rstrip() + "..."
    label = {
        "decision": "Session decision",
        "pitfall": "Session pitfall",
        "workflow": "Session workflow",
        "source_of_truth": "Session source of truth",
    }.get(rule.name, "Session memory")
    return f"{label}: {compact}"


def _candidate_content(unit: SessionUnit, *, path: Path, source_system: str) -> str:
    role = f"\nRole: {unit.role}" if unit.role else ""
    return (
        f"Captured from {source_system} session transcript `{path.name}` at {unit.ref}.{role}\n\n"
        f"Evidence:\n{unit.text}\n\n"
        "Use this as a reviewable memory candidate, not as active knowledge until promoted."
    )


def _preview_gates(db: VaultDB, proposal: dict[str, Any]) -> dict[str, Any]:
    meta = normalize_metadata(
        title=proposal["title"],
        content=proposal["content"],
        reason=proposal["reason"],
        layer=proposal["layer"],
        category=proposal["category"],
        tags=proposal["tags"],
        trust=proposal["trust"],
        source=proposal["source"],
        source_ref=proposal["source_ref"],
        scope=proposal["scope"],
        sensitivity=proposal["sensitivity"],
        owner_agent=proposal["owner_agent"],
        allowed_agents=proposal["allowed_agents"],
        memory_type=proposal["memory_type"],
    )
    privacy = scan_privacy(
        "\n".join(
            [
                meta["title"],
                meta["content"],
                meta["source_ref"],
                meta["reason"],
                meta["owner_agent"],
                meta["allowed_agents"],
            ]
        )
    )
    duplicate = duplicate_gate(db, meta["title"], meta["content"])
    metadata = metadata_gate(meta)
    quality = quality_gate(meta)
    payload = {"privacy": privacy, "duplicate": duplicate, "metadata": metadata, "quality": quality}
    return {
        "statuses": {
            "privacy": privacy["status"],
            "duplicate": duplicate["status"],
            "metadata": metadata["status"],
            "quality": quality["status"],
        },
        "payload": payload,
    }


def _memory_kwargs(proposal: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "title",
        "content",
        "reason",
        "layer",
        "category",
        "tags",
        "trust",
        "source",
        "source_ref",
        "scope",
        "sensitivity",
        "owner_agent",
        "allowed_agents",
        "memory_type",
        "expires_at",
    }
    return {key: value for key, value in proposal.items() if key in allowed}


def _safe_output_content(content: str, gate_statuses: dict[str, Any]) -> str:
    if str(gate_statuses.get("privacy") or "") == "fail":
        return redact_secrets(content)
    return content


def _redact_payload_strings(value: Any) -> Any:
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, list):
        return [_redact_payload_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_payload_strings(item) for key, item in value.items()}
    return value
