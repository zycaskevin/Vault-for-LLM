"""Read and review API helpers for the local Vault GUI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .automation import automation_brief
from .automation_inbox import automation_inbox
from .daily_report import build_daily_report
from .db import VaultDB
from .db_knowledge import escape_like_pattern
from .memory import promote_candidate, review_candidate
from .search import VaultSearch
from .search_utils import normalize_search_limit
from .gui_format import (
    compact_brief,
    compact_candidate,
    compact_inbox,
    compact_knowledge,
    compact_task,
    compact_review_result,
    confirmation_token,
    governance_for,
    graph_edges_for_entry,
    timeline_for,
    usage_for,
)
from .task_ledger import get_task, list_tasks, task_handoff


def _clean_filter(value: str | None) -> str:
    cleaned = str(value or "").strip()
    return "" if cleaned.lower() in {"", "all", "any", "*"} else cleaned


_FACET_EXPRESSIONS = {
    "layers": "layer",
    "categories": "category",
    "scopes": "COALESCE(scope, 'project')",
    "sensitivities": "COALESCE(sensitivity, 'low')",
}


def gui_overview(project_dir: str | Path, *, limit: int = 5) -> dict[str, Any]:
    """Return the startup payload shown by the local GUI."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    if not db_path.exists():
        return {
            "status": "blocked",
            "project_dir": str(project),
            "reason": "vault.db missing",
            "stats": {},
            "brief": {},
            "inbox": {},
            "daily_report": {},
            "recent": [],
        }

    with VaultDB(db_path) as db:
        stats = db.stats()
        recent = [
            compact_knowledge(row)
            for row in db.list_knowledge(limit=max(1, min(int(limit or 5), 20)))
        ]
        candidates = [
            compact_candidate(row)
            for row in db.list_memory_candidates(status="candidate", limit=max(1, min(int(limit or 5), 20)))
        ]
        task_rows = list_tasks(db, status="active", limit=max(1, min(int(limit or 5), 20)))
    brief = automation_brief(project, limit=limit, review_limit=limit)
    inbox = automation_inbox(project, limit=limit, include_content=False)
    daily_report = build_daily_report(project, limit=limit)
    return {
        "status": "ok",
        "project_dir": str(project),
        "stats": stats,
        "brief": compact_brief(brief),
        "inbox": compact_inbox(inbox),
        "daily_report": daily_report,
        "tasks": [compact_task(row) for row in task_rows],
        "candidates": candidates,
        "recent": recent,
    }


def gui_daily_report(project_dir: str | Path, *, limit: int = 5) -> dict[str, Any]:
    """Return the consumer-facing daily report for the local GUI."""
    return build_daily_report(project_dir, limit=limit)


def gui_tasks(project_dir: str | Path, *, status: str = "active", limit: int = 20) -> dict[str, Any]:
    """Return compact Task Ledger rows for the local GUI."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    limit_i = normalize_search_limit(limit, default=20, maximum=100)
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing", "tasks": []}
    if limit_i <= 0:
        return {"status": "ok", "task_status": status or "active", "tasks": []}
    with VaultDB(db_path) as db:
        rows = list_tasks(db, status=status or "active", limit=limit_i)
    return {
        "status": "ok",
        "task_status": status or "active",
        "tasks": [compact_task(row) for row in rows],
    }


def gui_task(project_dir: str | Path, task_id: str) -> dict[str, Any]:
    """Return one Task Ledger item plus compact handoff Markdown."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    tid = str(task_id or "").strip()
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing"}
    if not tid:
        return {"status": "error", "error": "invalid_task_id"}
    with VaultDB(db_path) as db:
        task = get_task(db, tid, include_events=True)
        if not task:
            return {"status": "error", "error": "not_found", "task_id": tid}
        handoff = task_handoff(db, tid)
    return {
        "status": "ok",
        "task": compact_task(task),
        "markdown": handoff.get("markdown", ""),
    }


def gui_documents(
    project_dir: str | Path,
    *,
    query: str = "",
    layer: str = "",
    category: str = "",
    scope: str = "",
    sensitivity: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """Return a compact, filterable active-memory document list for the GUI."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    limit_i = normalize_search_limit(limit, default=50, maximum=100)
    if not db_path.exists():
        return {
            "status": "blocked",
            "reason": "vault.db missing",
            "documents": [],
            "filters": {},
            "facets": {},
        }
    if limit_i <= 0:
        return {
            "status": "ok",
            "documents": [],
            "filters": {},
            "facets": {},
        }

    layer_i = _clean_filter(layer)
    category_i = _clean_filter(category)
    scope_i = _clean_filter(scope)
    sensitivity_i = _clean_filter(sensitivity)
    query_i = str(query or "").strip()

    where = ["COALESCE(status, 'active') != 'archived'"]
    params: list[Any] = []
    if layer_i:
        where.append("layer=?")
        params.append(layer_i)
    if category_i:
        where.append("category=?")
        params.append(category_i)
    if scope_i:
        where.append("COALESCE(scope, 'project')=?")
        params.append(scope_i)
    if sensitivity_i:
        where.append("COALESCE(sensitivity, 'low')=?")
        params.append(sensitivity_i)
    if query_i:
        pattern = f"%{escape_like_pattern(query_i)}%"
        where.append(
            """(
                title LIKE ? ESCAPE '\\'
                OR summary LIKE ? ESCAPE '\\'
                OR tags LIKE ? ESCAPE '\\'
                OR category LIKE ? ESCAPE '\\'
                OR source LIKE ? ESCAPE '\\'
            )"""
        )
        params.extend([pattern, pattern, pattern, pattern, pattern])

    with VaultDB(db_path) as db:
        rows = db.conn.execute(
            f"""SELECT id, title, category, layer, trust, summary, tags, source,
                       scope, sensitivity, owner_agent, memory_type,
                       valid_from, valid_until, expires_at, updated_at
                FROM knowledge
                WHERE {' AND '.join(where)}
                ORDER BY updated_at DESC, trust DESC, id DESC
                LIMIT ?""",
            [*params, limit_i],
        ).fetchall()
        facets = {
            "layers": _facet_counts(db, "layers"),
            "categories": _facet_counts(db, "categories"),
            "scopes": _facet_counts(db, "scopes"),
            "sensitivities": _facet_counts(db, "sensitivities"),
        }

    return {
        "status": "ok",
        "documents": [compact_knowledge(dict(row)) for row in rows],
        "filters": {
            "query": query_i,
            "layer": layer_i,
            "category": category_i,
            "scope": scope_i,
            "sensitivity": sensitivity_i,
            "limit": limit_i,
        },
        "facets": facets,
    }


def _facet_counts(db: VaultDB, facet: str) -> list[dict[str, Any]]:
    expression = _FACET_EXPRESSIONS[facet]
    rows = db.conn.execute(
        f"""SELECT {expression} AS value, COUNT(*) AS count
            FROM knowledge
            WHERE COALESCE(status, 'active') != 'archived'
            GROUP BY value
            ORDER BY count DESC, value ASC
            LIMIT 50"""
    ).fetchall()
    return [
        {"value": row["value"] or "", "count": row["count"]}
        for row in rows
        if row["value"] not in (None, "")
    ]


def gui_search(
    project_dir: str | Path,
    query: str,
    *,
    mode: str = "keyword",
    limit: int = 10,
) -> dict[str, Any]:
    """Run a local read-only search for the GUI."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    limit_i = normalize_search_limit(limit, default=10, maximum=50)
    if not query.strip() or limit_i <= 0:
        return {"status": "ok", "query": query, "results": []}
    if mode not in {"auto", "keyword", "semantic", "hybrid", "vector"}:
        mode = "keyword"
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing", "query": query, "results": []}

    with VaultDB(db_path) as db:
        search = VaultSearch(db, embed_provider=None, embed_provider_name="none")
        rows = search.search(
            query,
            mode=mode,
            limit=limit_i,
            use_rerank=False,
            compact=False,
            include_snippet=True,
            fields=[
                "id",
                "title",
                "category",
                "layer",
                "trust",
                "summary",
                "tags",
                "source",
                "scope",
                "sensitivity",
                "owner_agent",
                "memory_type",
                "valid_from",
                "valid_until",
                "expires_at",
                "line_start",
                "line_end",
                "best_span",
                "recommended_next_tool",
                "_score",
                "_snippet",
            ],
        )
    return {"status": "ok", "query": query, "mode": mode, "results": [compact_knowledge(r) for r in rows]}


def gui_entry(project_dir: str | Path, knowledge_id: int) -> dict[str, Any]:
    """Return metadata, map nodes, claims, and graph summary for one entry."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing"}
    try:
        kid = int(knowledge_id)
    except (TypeError, ValueError):
        return {"status": "error", "error": "invalid_knowledge_id"}
    if kid <= 0:
        return {"status": "error", "error": "invalid_knowledge_id"}

    with VaultDB(db_path) as db:
        row = db.get_knowledge(kid)
        if not row:
            return {"status": "error", "error": "not_found", "knowledge_id": kid}
        nodes = [
            dict(r)
            for r in db.conn.execute(
                """SELECT node_uid, heading, level, path, summary, line_start, line_end
                   FROM knowledge_nodes
                   WHERE knowledge_id=?
                   ORDER BY line_start, level, id""",
                (kid,),
            ).fetchall()
        ]
        claims = [
            dict(r)
            for r in db.conn.execute(
                """SELECT claim, node_uid, line_start, line_end, confidence, source
                   FROM knowledge_claims
                   WHERE knowledge_id=?
                   ORDER BY line_start, id
                   LIMIT 20""",
                (kid,),
            ).fetchall()
        ]
        edges = graph_edges_for_entry(db, kid)
    return {
        "status": "ok",
        "entry": compact_knowledge(row),
        "nodes": nodes,
        "claims": claims,
        "graph": edges,
        "timeline": timeline_for(row),
        "governance": governance_for(row),
        "usage": usage_for(row),
    }


def gui_read_range(
    project_dir: str | Path,
    knowledge_id: int,
    *,
    line_start: int = 1,
    line_end: int = 40,
    max_lines: int = 80,
) -> dict[str, Any]:
    """Return a bounded source range for the GUI evidence reader."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing"}
    try:
        kid = int(knowledge_id)
        start = int(line_start)
        end = int(line_end)
        max_lines_i = max(1, min(int(max_lines), 200))
    except (TypeError, ValueError):
        return {"status": "error", "error": "invalid_range"}
    if kid <= 0:
        return {"status": "error", "error": "invalid_knowledge_id"}

    with VaultDB(db_path) as db:
        row = db.get_knowledge(kid)
        if not row:
            return {"status": "error", "error": "not_found", "knowledge_id": kid}
        lines = (row.get("content_raw") or "").splitlines()
    if not lines:
        return {"status": "ok", "knowledge_id": kid, "title": row.get("title", ""), "lines": []}

    total = len(lines)
    start = min(max(1, start), total)
    end = min(max(start, end), total)
    if end - start + 1 > max_lines_i:
        end = start + max_lines_i - 1
    payload_lines = [
        {"line": number, "text": lines[number - 1]}
        for number in range(start, end + 1)
    ]
    return {
        "status": "ok",
        "knowledge_id": kid,
        "title": row.get("title", ""),
        "line_start": start,
        "line_end": end,
        "citation": f"#{kid} {row.get('title', '')} L{start}-L{end}",
        "lines": payload_lines,
    }


def gui_candidates(project_dir: str | Path, *, status: str = "candidate", limit: int = 20) -> dict[str, Any]:
    """Return reviewable memory candidates without full content."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    limit_i = max(1, min(int(limit or 20), 50))
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing", "candidates": []}
    status_filter = None if status == "all" else (status or "candidate")
    with VaultDB(db_path) as db:
        rows = db.list_memory_candidates(status=status_filter, limit=limit_i)
    return {
        "status": "ok",
        "candidate_status": status_filter or "all",
        "candidates": [compact_candidate(row) for row in rows],
    }


def gui_candidate(project_dir: str | Path, candidate_id: str) -> dict[str, Any]:
    """Return one memory candidate with content and gate details for review."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    cid = str(candidate_id or "").strip()
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing"}
    if not cid:
        return {"status": "error", "error": "invalid_candidate_id"}
    with VaultDB(db_path) as db:
        row = db.get_memory_candidate(cid)
    if not row:
        return {"status": "error", "error": "not_found", "candidate_id": cid}
    return {
        "status": "ok",
        "candidate": compact_candidate(row, include_content=True, include_gates=True),
        "confirmation": {
            "promote": confirmation_token(cid, "promote"),
            "reject": confirmation_token(cid, "reject"),
            "block": confirmation_token(cid, "block"),
        },
    }


def gui_review_candidate(
    project_dir: str | Path,
    candidate_id: str,
    *,
    action: str,
    reason: str = "",
    confirm: str = "",
) -> dict[str, Any]:
    """Apply an explicit review action to a candidate."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    cid = str(candidate_id or "").strip()
    action_i = str(action or "").strip().lower()
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing"}
    if action_i not in {"promote", "reject", "block"}:
        return {"status": "error", "error": "invalid_action"}
    expected = confirmation_token(cid, action_i)
    if not cid or str(confirm or "") != expected:
        return {
            "status": "error",
            "error": "confirmation_required",
            "expected_confirmation": expected,
        }

    with VaultDB(db_path) as db:
        if action_i == "promote":
            payload = promote_candidate(db, cid, confirm=True, project_dir=project)
        else:
            outcome = "rejected" if action_i == "reject" else "blocked"
            payload = review_candidate(
                db,
                cid,
                outcome=outcome,
                reason=reason or f"GUI review marked candidate {outcome}",
            )
    return {"status": "ok", "action": action_i, "result": compact_review_result(payload)}
