"""Memory reflection cycle: dream, consolidate, archive, and forget safely."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .automation import automation_run
from .dream import run_dream


def run_reflection(
    project_dir: str | Path,
    *,
    checks: str = "freshness,dedup,convergence,metadata,orphans",
    limit: int = 50,
    write_candidates: bool = False,
    apply: bool = False,
    write_report: bool = True,
) -> dict[str, Any]:
    """Run one bounded memory-reflection pass."""
    project = Path(project_dir).expanduser().resolve()
    dream = run_dream(
        project,
        mode="report",
        checks=checks,
        limit=limit,
        write_report=write_report,
        write_candidates=write_candidates,
        backup=True,
    )
    lifecycle = automation_run(project, apply=apply, limit=limit, write_reports=write_report)
    return {
        "action": "memory_reflection_run",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_dir": str(project),
        "write_candidates": bool(write_candidates),
        "apply": bool(apply),
        "dream": {
            "status": dream.get("status"),
            "report_path": dream.get("report_path"),
            "candidate_count": len(dream.get("candidates", []) or []),
            "summary": dream.get("summary", {}),
        },
        "lifecycle": {
            "status": lifecycle.get("status"),
            "report_path": lifecycle.get("report_path"),
            "archive_expired": lifecycle.get("archive_expired", {}),
            "cold_store_expired": lifecycle.get("cold_store_expired", {}),
        },
        "safety": {
            "report_first": True,
            "hard_delete": False,
            "active_rewrites": False,
            "candidate_first": True,
            "apply_required_for_archive": True,
        },
        "next_action": _next_action(write_candidates=write_candidates, apply=apply),
    }


def _next_action(*, write_candidates: bool, apply: bool) -> str:
    if not write_candidates:
        return "Review the Dream report, then re-run with --write-candidates for reviewable suggestions."
    if not apply:
        return "Review candidates and lifecycle preview; add --apply only for policy-approved reversible archive/cold-store actions."
    return "Review automation activity and candidate queue; promotion still stays candidate-first."
