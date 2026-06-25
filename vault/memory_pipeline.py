"""Automatic conversation-memory pipeline."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .automation import automation_cycle
from .db import VaultDB
from .session_capture import capture_session_candidates, discover_session_transcripts


def run_memory_pipeline(
    project_dir: str | Path,
    *,
    search_dirs: list[str | Path] | None = None,
    source_system: str = "auto",
    agent_id: str = "",
    write_candidates: bool = False,
    run_cycle: bool = False,
    apply: bool = False,
    transcript_limit: int = 3,
    max_candidates_per_transcript: int = 8,
    min_score: float = 0.55,
    scope: str = "project",
    sensitivity: str = "low",
    include_content: bool = False,
    write_report: bool = False,
) -> dict[str, Any]:
    """Discover transcripts, extract candidates, and optionally run automation."""
    project = Path(project_dir).expanduser().resolve()
    discovery = discover_session_transcripts(
        project,
        search_dirs=search_dirs,
        source_system=source_system,
        limit=transcript_limit,
    )
    captures: list[dict[str, Any]] = []
    if (project / "vault.db").exists():
        with VaultDB(project / "vault.db") as db:
            for item in discovery.get("transcripts", [])[: max(0, int(transcript_limit or 0))]:
                payload = capture_session_candidates(
                    db,
                    item["path"],
                    source_system=source_system,
                    agent_id=agent_id,
                    write_candidates=write_candidates,
                    max_candidates=max_candidates_per_transcript,
                    min_score=min_score,
                    scope=scope,
                    sensitivity=sensitivity,
                    owner_agent=agent_id,
                    include_content=include_content,
                )
                captures.append(_compact_capture(payload))
    cycle = None
    if run_cycle:
        cycle = automation_cycle(
            project,
            apply=apply,
            include_transcripts=False,
            capture_transcripts=False,
            write_workspace=True,
        )
    payload = {
        "action": "memory_pipeline_run",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_dir": str(project),
        "write_candidates": bool(write_candidates),
        "run_cycle": bool(run_cycle),
        "apply": bool(apply),
        "discovery": {
            "count": discovery.get("count", 0),
            "read_contents": discovery.get("read_contents", False),
            "skipped": discovery.get("skipped", {}),
        },
        "captures": captures,
        "candidate_count": sum(int(item.get("written_count", 0)) for item in captures),
        "preview_count": sum(int(item.get("preview_count", 0)) for item in captures),
        "cycle": _compact_cycle(cycle) if cycle else None,
        "next_action": _next_action(write_candidates=write_candidates, run_cycle=run_cycle, apply=apply),
    }
    if write_report:
        payload.update(_write_pipeline_report(project, payload))
    return payload


def _compact_capture(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "transcript": payload.get("transcript_path"),
        "source_system": payload.get("source_system"),
        "status": payload.get("status"),
        "preview_count": 0 if payload.get("write_candidates") else len(payload.get("candidates", [])),
        "written_count": payload.get("written", 0),
        "rejected_count": payload.get("rejected", 0),
        "candidates": payload.get("candidates", [])[:5],
    }


def _compact_cycle(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    return {
        "status": payload.get("status"),
        "apply": payload.get("apply"),
        "report_path": payload.get("report_path"),
        "workspace_path": payload.get("workspace_path"),
        "candidate_count_after": payload.get("candidate_count_after"),
    }


def _next_action(*, write_candidates: bool, run_cycle: bool, apply: bool) -> str:
    if not write_candidates:
        return "Re-run with --write-candidates after reviewing the preview."
    if not run_cycle:
        return "Run vault automation inbox or re-run with --cycle to prioritize candidates."
    if not apply:
        return "Review the cycle report, then re-run with --apply if the policy is acceptable."
    return "Review vault automation activity and promote or reject the remaining review cards."


def _write_pipeline_report(project: Path, payload: dict[str, Any]) -> dict[str, str]:
    report_dir = project / "reports" / "automation"
    report_dir.mkdir(parents=True, exist_ok=True)
    safe = _report_payload(payload)
    json_path = report_dir / "pipeline-latest.json"
    md_path = report_dir / "pipeline-latest.md"
    json_path.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_pipeline_markdown(safe), encoding="utf-8")
    return {
        "report_path": _relative_to_project(project, json_path),
        "report_markdown_path": _relative_to_project(project, md_path),
    }


def _report_payload(payload: dict[str, Any]) -> dict[str, Any]:
    safe = dict(payload)
    captures: list[dict[str, Any]] = []
    for capture in payload.get("captures", []) or []:
        item = dict(capture)
        candidates = []
        for candidate in item.get("candidates", []) or []:
            compact = dict(candidate)
            compact.pop("content", None)
            compact.pop("content_preview", None)
            compact.pop("gate_payload", None)
            candidates.append(compact)
        item["candidates"] = candidates
        captures.append(item)
    safe["captures"] = captures
    return safe


def _render_pipeline_markdown(payload: dict[str, Any]) -> str:
    discovery = payload.get("discovery") or {}
    captures = payload.get("captures") or []
    lines = [
        "# Memory Pipeline",
        "",
        f"- generated_at: `{payload.get('generated_at', '')}`",
        f"- transcripts_discovered: `{int(discovery.get('count') or 0)}`",
        f"- captures_processed: `{len(captures)}`",
        f"- candidates_written: `{int(payload.get('candidate_count') or 0)}`",
        f"- previews: `{int(payload.get('preview_count') or 0)}`",
        f"- write_candidates: `{str(bool(payload.get('write_candidates'))).lower()}`",
        f"- run_cycle: `{str(bool(payload.get('run_cycle'))).lower()}`",
        "",
        "## Captures",
        "",
    ]
    if captures:
        for capture in captures[:10]:
            transcript = Path(str(capture.get("transcript") or "")).name or "(unknown)"
            lines.append(
                "- "
                f"`{_md_text(transcript)}`: "
                f"written `{int(capture.get('written_count') or 0)}`, "
                f"preview `{int(capture.get('preview_count') or 0)}`, "
                f"rejected `{int(capture.get('rejected_count') or 0)}`"
            )
    else:
        lines.append("- No transcript captures were processed.")
    lines.extend(["", "## Next", "", _md_text(str(payload.get("next_action") or "")), ""])
    return "\n".join(lines)


def _relative_to_project(project: Path, path: Path) -> str:
    try:
        return str(path.relative_to(project))
    except ValueError:
        return str(path)


def _md_text(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()
