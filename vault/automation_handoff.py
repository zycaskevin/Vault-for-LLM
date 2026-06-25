"""Read-only automation startup handoff assembly."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .automation_reports import (
    _relative_to_project,
    _resolve_fleet_health_read_path,
    _resolve_handoff_read_path,
    _resolve_learning_health_read_path,
    _resolve_review_summary_read_path,
)


def automation_handoff(
    project_dir: str | Path,
    *,
    source: str = "auto",
    handoff_path: str | Path = "",
) -> dict[str, Any]:
    """Read the latest compact automation handoff for the next agent."""
    project = Path(project_dir)
    report_dir = project / "reports" / "automation"
    selected = _resolve_handoff_read_path(project, report_dir, source=source, handoff_path=handoff_path)
    prefaces = _startup_prefaces(project, report_dir, selected=selected)
    if selected is None:
        return {
            "action": "handoff",
            "generated_at": _now(),
            "project_dir": str(project),
            "status": "missing",
            "source": source,
            "handoff_path": "",
            "content_type": "",
            "content": "",
            **prefaces,
            "summary": {},
            "safety": {
                "read_only": True,
                "writes_active_memory": False,
                "transcript_discovery_reads_contents": False,
            },
            "next_action": "Run `vault automation cycle --write-workspace` to create a daily handoff.",
        }

    content = selected.read_text(encoding="utf-8")
    parsed = _parse_json_handoff(content) if selected.suffix.lower() == ".json" else {}
    return {
        "action": "handoff",
        "generated_at": _now(),
        "project_dir": str(project),
        "status": "completed",
        "source": source,
        "handoff_path": _relative_to_project(project, selected),
        "content_type": "markdown" if selected.suffix.lower() == ".md" else "json",
        "content": content,
        **prefaces,
        "summary": parsed.get("summary", {}) if parsed else {},
        "agent_start_prompt": parsed.get("agent_start_prompt", "") if parsed else "",
        "safety": {
            "read_only": True,
            "writes_active_memory": False,
            "transcript_discovery_reads_contents": False,
            "uses_existing_handoff_only": True,
        },
        "next_action": (
            "Read this handoff first, then use the listed suggested_next_tasks without "
            "auto-promoting candidates or reading transcript contents by default."
        ),
    }


def _startup_prefaces(project: Path, report_dir: Path, *, selected: Path | None) -> dict[str, str]:
    fleet = _preface(project, _resolve_fleet_health_read_path(report_dir), selected=selected, prefix="fleet_health")
    pipeline = _preface(project, _resolve_pipeline_receipt_read_path(report_dir), selected=selected, prefix="pipeline_receipt")
    review = _preface(project, _resolve_review_summary_read_path(report_dir), selected=selected, prefix="review_summary")
    learning = _preface(project, _resolve_learning_health_read_path(report_dir), selected=selected, prefix="learning_health")
    return {**fleet, **pipeline, **review, **learning}


def _preface(project: Path, path: Path | None, *, selected: Path | None, prefix: str) -> dict[str, str]:
    empty = {f"{prefix}_path": "", f"{prefix}_content_type": "", f"{prefix}_content": ""}
    if path is None:
        return empty
    if selected is not None and path.resolve() == selected.resolve():
        return empty
    return {
        f"{prefix}_path": _relative_to_project(project, path),
        f"{prefix}_content_type": "markdown" if path.suffix.lower() == ".md" else "json",
        f"{prefix}_content": path.read_text(encoding="utf-8"),
    }


def _resolve_pipeline_receipt_read_path(report_dir: Path) -> Path | None:
    for name in ("pipeline-latest.md", "pipeline-latest.json"):
        candidate = report_dir / name
        if candidate.exists():
            return candidate
    return None


def _parse_json_handoff(content: str) -> dict[str, Any]:
    try:
        loaded = json.loads(content)
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
