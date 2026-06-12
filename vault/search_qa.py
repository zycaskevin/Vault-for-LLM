"""Deterministic Search QA evaluation and before/after comparison.

This module is intentionally pure-Python around local SQLite search. It does not
call Supabase, Ollama, or embedding services when invoked with ``mode='keyword'``
and ``embed_provider=None`` (the CLI uses that path for keyword smoke runs).
Search-result citations are treated as navigation hints only.
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import VaultDB
from .search import VaultSearch

METRIC_KEYS: tuple[str, ...] = (
    "total_cases",
    "cases_with_results",
    "top1_hits",
    "topk_hits",
    "mean_reciprocal_rank",
    "map_guidance_rate",
    "read_range_guidance_rate",
    "citation_policy_violations",
    "mean_latency_ms",
    "p95_latency_ms",
    "min_latency_ms",
    "max_latency_ms",
)


def load_search_qa_set(path: str | Path) -> dict[str, Any]:
    """Load and minimally validate an extendable Search QA Set JSON file."""
    qa_path = Path(path)
    data = json.loads(qa_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Search QA file must contain a JSON object")
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise ValueError("Search QA file must contain a cases list")
    for idx, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"Search QA case {idx} must be an object")
        if not case.get("id"):
            raise ValueError(f"Search QA case {idx} missing id")
        if not case.get("query"):
            raise ValueError(f"Search QA case {case.get('id', idx)} missing query")
    return data


def evaluate_search_qa(
    *,
    db_path: str | Path,
    qa_file: str | Path,
    mode: str = "keyword",
    limit: int = 10,
    generated_at: str | None = None,
    embed_provider: Any | None = None,
    semantic_vector_kind: str = "claim",
    allow_hash: bool = False,
) -> dict[str, Any]:
    """Run all QA cases through ``VaultSearch`` and return a JSON snapshot."""
    qa_path = Path(qa_file)
    qa = load_search_qa_set(qa_path)
    limit = max(1, int(limit))
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()

    db = VaultDB(db_path).connect()
    try:
        search = VaultSearch(db, embed_provider=embed_provider)
        case_summaries = [
            _evaluate_case(
                search,
                case,
                mode=mode,
                limit=limit,
                semantic_vector_kind=semantic_vector_kind,
                allow_hash=allow_hash,
            )
            for case in qa["cases"]
        ]
    finally:
        db.close()

    aggregate = _aggregate_cases(case_summaries)
    return {
        "snapshot_version": 1,
        "qa_file": str(qa_path),
        "mode": mode,
        "limit": limit,
        "generated_at": generated_at,
        "aggregate": aggregate,
        "cases": case_summaries,
    }


def compare_search_qa_snapshots(
    before: str | Path | dict[str, Any],
    after: str | Path | dict[str, Any],
) -> dict[str, Any]:
    """Compare two Search QA snapshot JSON objects or files with stable deltas."""
    before_snapshot = _load_snapshot(before)
    after_snapshot = _load_snapshot(after)
    before_metrics = before_snapshot.get("aggregate") or {}
    after_metrics = after_snapshot.get("aggregate") or {}

    metrics: dict[str, dict[str, int | float]] = {}
    keys = list(METRIC_KEYS)
    for key in sorted((set(before_metrics) | set(after_metrics)) - set(METRIC_KEYS)):
        keys.append(key)

    for key in keys:
        b = _number(before_metrics.get(key, 0))
        a = _number(after_metrics.get(key, 0))
        metrics[key] = {
            "before": b,
            "after": a,
            "delta": _stable_delta(a, b),
        }

    return {
        "comparison_version": 1,
        "before": _snapshot_ref(before_snapshot),
        "after": _snapshot_ref(after_snapshot),
        "metrics": metrics,
    }


def format_search_qa_comparison(comparison: dict[str, Any]) -> str:
    """Render a small human-readable before/after report."""
    lines = ["Search QA comparison"]
    metrics = comparison.get("metrics") or {}
    for key in METRIC_KEYS:
        if key not in metrics:
            continue
        metric = metrics[key]
        delta = metric.get("delta", 0)
        lines.append(
            f"- {key}: {metric.get('before', 0)} -> {metric.get('after', 0)} "
            f"({ _format_delta(delta) })"
        )
    for key in sorted(set(metrics) - set(METRIC_KEYS)):
        metric = metrics[key]
        delta = metric.get("delta", 0)
        lines.append(
            f"- {key}: {metric.get('before', 0)} -> {metric.get('after', 0)} "
            f"({ _format_delta(delta) })"
        )
    return "\n".join(lines)


def format_search_qa_snapshot(snapshot: dict[str, Any]) -> str:
    """Render a compact run summary for CLI output."""
    aggregate = snapshot.get("aggregate") or {}
    return (
        "Search QA run complete\n"
        f"- total_cases: {aggregate.get('total_cases', 0)}\n"
        f"- cases_with_results: {aggregate.get('cases_with_results', 0)}\n"
        f"- top1_hits: {aggregate.get('top1_hits', 0)}\n"
        f"- topk_hits: {aggregate.get('topk_hits', 0)}\n"
        f"- mean_reciprocal_rank: {aggregate.get('mean_reciprocal_rank', 0.0)}\n"
        f"- map_guidance_rate: {aggregate.get('map_guidance_rate', 0.0)}\n"
        f"- read_range_guidance_rate: {aggregate.get('read_range_guidance_rate', 0.0)}\n"
        f"- citation_policy_violations: {aggregate.get('citation_policy_violations', 0)}\n"
        f"- mean_latency_ms: {aggregate.get('mean_latency_ms', 0.0)}\n"
        f"- p95_latency_ms: {aggregate.get('p95_latency_ms', 0.0)}\n"
        f"- min_latency_ms: {aggregate.get('min_latency_ms', 0.0)}\n"
        f"- max_latency_ms: {aggregate.get('max_latency_ms', 0.0)}"
    )


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    """Write deterministic UTF-8 JSON for snapshots/comparisons."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _evaluate_case(
    search: VaultSearch,
    case: dict[str, Any],
    *,
    mode: str,
    limit: int,
    semantic_vector_kind: str = "claim",
    allow_hash: bool = False,
) -> dict[str, Any]:
    query = str(case["query"])
    start = time.perf_counter()
    raw_results = search.search(
        query,
        mode=mode,
        limit=limit,
        use_rerank=False,
        semantic_vector_kind=semantic_vector_kind,
        allow_hash=allow_hash,
    )
    latency_ms = (time.perf_counter() - start) * 1000
    results = [_summarize_result(result) for result in raw_results[:limit]]

    hit_rank = _hit_rank(case, results)
    has_map_guidance = any(_has_map_guidance(result) for result in results)
    has_read_range_guidance = any(_has_read_range_guidance(result) for result in results)
    violations = _citation_policy_violations(results)

    return {
        "id": str(case["id"]),
        "query": query,
        "expected_ids": _as_list(case.get("expected_ids")),
        "expected_titles": _as_list(case.get("expected_titles")),
        "expected_title_substrings": _as_list(case.get("expected_title_substrings")),
        "result_count": len(results),
        "top1_hit": hit_rank == 1,
        "topk_hit": hit_rank is not None,
        "hit_rank": hit_rank,
        "reciprocal_rank": (1 / hit_rank) if hit_rank else 0.0,
        "has_map_guidance": has_map_guidance,
        "has_read_range_guidance": has_read_range_guidance,
        "citation_policy_violations": violations,
        "latency_ms": round(latency_ms, 6),
        "results": results,
    }


def _summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    """Keep per-case output compact and JSON-serializable."""
    fields = (
        "id",
        "title",
        "category",
        "layer",
        "trust",
        "tags",
        "best_claim",
        "best_span",
        "node_uid",
        "path",
        "heading",
        "line_start",
        "line_end",
        "citation",
        "final_citation",
        "final_answer_citation",
        "citation_role",
        "recommended_next_tool",
        "next_action",
        "next_actions",
        "_score",
        "_mode",
    )
    summary: dict[str, Any] = {}
    for field in fields:
        if field in result:
            key = "score" if field == "_score" else "mode" if field == "_mode" else field
            summary[key] = _jsonable(result[field])
    return summary


def _aggregate_cases(cases: list[dict[str, Any]]) -> dict[str, int | float]:
    total = len(cases)
    if total == 0:
        return {
            "total_cases": 0,
            "cases_with_results": 0,
            "top1_hits": 0,
            "topk_hits": 0,
            "mean_reciprocal_rank": 0.0,
            "map_guidance_rate": 0.0,
            "read_range_guidance_rate": 0.0,
            "citation_policy_violations": 0,
            "mean_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "min_latency_ms": 0.0,
            "max_latency_ms": 0.0,
        }

    latencies = [float(case.get("latency_ms", 0.0)) for case in cases]
    sorted_latencies = sorted(latencies)
    p95_index = max(0, math.ceil(0.95 * len(sorted_latencies)) - 1)

    return {
        "total_cases": total,
        "cases_with_results": sum(1 for case in cases if case["result_count"] > 0),
        "top1_hits": sum(1 for case in cases if case["top1_hit"]),
        "topk_hits": sum(1 for case in cases if case["topk_hit"]),
        "mean_reciprocal_rank": sum(case["reciprocal_rank"] for case in cases) / total,
        "map_guidance_rate": sum(1 for case in cases if case["has_map_guidance"]) / total,
        "read_range_guidance_rate": sum(1 for case in cases if case["has_read_range_guidance"]) / total,
        "citation_policy_violations": sum(
            len(case["citation_policy_violations"]) for case in cases
        ),
        "mean_latency_ms": round(sum(latencies) / total, 6),
        "p95_latency_ms": round(sorted_latencies[p95_index], 6),
        "min_latency_ms": round(min(latencies), 6),
        "max_latency_ms": round(max(latencies), 6),
    }


def _hit_rank(case: dict[str, Any], results: list[dict[str, Any]]) -> int | None:
    for rank, result in enumerate(results, start=1):
        if _matches_expected(case, result):
            return rank
    return None


def _matches_expected(case: dict[str, Any], result: dict[str, Any]) -> bool:
    result_id = result.get("id")
    title = str(result.get("title") or "")
    title_lower = title.lower()

    expected_ids = {_normalize_id(value) for value in _as_list(case.get("expected_ids"))}
    if expected_ids and _normalize_id(result_id) in expected_ids:
        return True

    expected_titles = {str(value) for value in _as_list(case.get("expected_titles"))}
    if expected_titles and title in expected_titles:
        return True

    substrings = [str(value).lower() for value in _as_list(case.get("expected_title_substrings"))]
    if substrings and all(substring in title_lower for substring in substrings):
        return True

    return False


def _citation_policy_violations(results: list[dict[str, Any]]) -> list[str]:
    violations: list[str] = []
    for result in results:
        if (
            result.get("final_citation")
            or result.get("final_answer_citation")
            or result.get("citation_role") in {"final", "final_answer"}
        ):
            _append_once(violations, "search_result_labeled_as_final_citation")
        if result.get("citation") and not _has_read_range_guidance(result):
            _append_once(violations, "search_result_citation_without_read_range_guidance")
    return violations


def _has_map_guidance(result: dict[str, Any]) -> bool:
    return _has_tool_guidance(result, "vault_map_show")


def _has_read_range_guidance(result: dict[str, Any]) -> bool:
    return (
        result.get("recommended_next_tool") == "vault_read_range"
        or _has_tool_guidance(result, "vault_read_range")
    )


def _has_tool_guidance(result: dict[str, Any], tool: str) -> bool:
    next_action = result.get("next_action")
    if isinstance(next_action, dict) and next_action.get("tool") == tool:
        return True
    next_actions = result.get("next_actions") or []
    if isinstance(next_actions, list):
        return any(
            isinstance(action, dict) and action.get("tool") == tool
            for action in next_actions
        )
    return False


def _load_snapshot(snapshot: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(snapshot, dict):
        return snapshot
    path = Path(snapshot)
    return json.loads(path.read_text(encoding="utf-8"))


def _snapshot_ref(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "qa_file": snapshot.get("qa_file", ""),
        "mode": snapshot.get("mode", ""),
        "limit": snapshot.get("limit", 0),
        "generated_at": snapshot.get("generated_at", ""),
    }


def _stable_delta(after: int | float, before: int | float) -> int | float:
    delta = after - before
    if isinstance(after, int) and isinstance(before, int):
        return int(delta)
    return round(float(delta), 12)


def _format_delta(delta: int | float) -> str:
    if isinstance(delta, (int, float)) and delta > 0:
        return f"+{delta}"
    return str(delta)


def _number(value: Any) -> int | float:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0
    if parsed.is_integer():
        return int(parsed)
    return parsed


def _normalize_id(value: Any) -> str:
    return str(value).strip()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _append_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(k): _jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_jsonable(v) for v in value]
        return str(value)
