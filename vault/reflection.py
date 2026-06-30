"""Memory reflection cycle: dream, consolidate, archive, and forget safely."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .automation import automation_run
from .db import VaultDB
from .dream import run_dream
from .memory import create_candidate, text_similarity


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
    consolidation = _run_consolidation_reflection(
        project,
        limit=limit,
        write_candidates=write_candidates,
    )
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
        "consolidation": consolidation,
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


def _run_consolidation_reflection(
    project: Path,
    *,
    limit: int,
    write_candidates: bool,
) -> dict[str, Any]:
    """Find small clusters of similar active memories and propose consolidation."""
    db_path = project / "vault.db"
    if not db_path.exists():
        return {"status": "skipped", "reason": "vault.db not found", "suggestions": []}
    with VaultDB(db_path) as db:
        rows = [
            dict(row)
            for row in db.conn.execute(
                """SELECT id, title, content_raw, category, tags, trust, updated_at
                   FROM knowledge
                   WHERE COALESCE(status, 'active') != 'archived'
                   ORDER BY updated_at DESC, id DESC
                   LIMIT ?""",
                (max(10, min(int(limit or 50) * 4, 400)),),
            ).fetchall()
        ]
        suggestions = _build_consolidation_suggestions(rows, limit=max(1, min(int(limit or 50), 50)))
        written: list[dict[str, Any]] = []
        if write_candidates:
            for suggestion in suggestions:
                existing = db.conn.execute(
                    """SELECT id, status FROM memory_candidates
                       WHERE source = 'reflection'
                         AND source_ref = ?
                         AND memory_type = 'consolidation_suggestion'
                         AND status IN ('candidate', 'approved')
                       LIMIT 1""",
                    (suggestion["source_ref"],),
                ).fetchone()
                if existing:
                    written.append({
                        "status": "skipped_existing",
                        "candidate_id": existing["id"],
                        "source_ref": suggestion["source_ref"],
                    })
                    continue
                result = create_candidate(db, **suggestion)
                written.append({
                    "status": result.get("status"),
                    "candidate_id": result.get("candidate_id"),
                    "source_ref": suggestion["source_ref"],
                    "gates": result.get("gates", {}),
                })
        return {
            "status": "completed",
            "suggestion_count": len(suggestions),
            "written_count": sum(1 for item in written if item.get("status") == "candidate_created"),
            "suggestions": [_compact_consolidation_suggestion(item) for item in suggestions],
            "written": written,
        }


def _build_consolidation_suggestions(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    seen_ids: set[int] = set()
    suggestions: list[dict[str, Any]] = []
    for row in rows:
        base_id = int(row.get("id") or 0)
        if not base_id or base_id in seen_ids:
            continue
        cluster = [row]
        for other in rows:
            other_id = int(other.get("id") or 0)
            if other_id == base_id or other_id in seen_ids:
                continue
            if str(other.get("category") or "") != str(row.get("category") or ""):
                continue
            score = max(
                text_similarity(row.get("content_raw") or "", other.get("content_raw") or ""),
                text_similarity(row.get("title") or "", other.get("title") or ""),
            )
            if score >= 0.62:
                cluster.append(other)
            if len(cluster) >= 5:
                break
        if len(cluster) < 2:
            continue
        ids = sorted(int(item["id"]) for item in cluster)
        seen_ids.update(ids)
        suggestions.append(_consolidation_candidate(cluster, ids))
        if len(suggestions) >= limit:
            break
    return suggestions


def _consolidation_candidate(cluster: list[dict[str, Any]], ids: list[int]) -> dict[str, Any]:
    primary = cluster[0]
    category = str(primary.get("category") or "general")
    title = f"Consolidate {category} memories: {primary.get('title', '')}"[:96]
    bullets = []
    for item in cluster[:5]:
        content = " ".join(str(item.get("content_raw") or "").split())
        bullets.append(f"- #{item.get('id')} {item.get('title')}: {content[:220]}")
    source_ref = "reflection:consolidate:" + ",".join(str(kid) for kid in ids)
    return {
        "title": title,
        "content": (
            "Reflection suggests consolidating these related memories because they overlap "
            "and may be easier to retrieve as one reviewed summary.\n\n"
            "Source memories:\n"
            + "\n".join(bullets)
            + "\n\nReview this candidate before replacing, archiving, or lowering the originals."
        ),
        "reason": "Reflection found a similar-memory cluster and proposes a reviewable consolidation.",
        "layer": "L2",
        "category": "consolidation",
        "tags": "reflection,consolidation,review",
        "trust": round(max(float(item.get("trust") or 0.5) for item in cluster), 2),
        "source": "reflection",
        "source_ref": source_ref,
        "scope": "project",
        "sensitivity": "low",
        "owner_agent": "",
        "allowed_agents": "",
        "memory_type": "consolidation_suggestion",
    }


def _compact_consolidation_suggestion(suggestion: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": suggestion.get("title"),
        "source_ref": suggestion.get("source_ref"),
        "memory_type": suggestion.get("memory_type"),
        "category": suggestion.get("category"),
        "trust": suggestion.get("trust"),
    }
