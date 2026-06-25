"""Automatic conversation-memory pipeline."""

from __future__ import annotations

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
    return {
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
