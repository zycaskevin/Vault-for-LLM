"""MCP search result shaping helpers."""

from __future__ import annotations

from typing import Any

MCP_SEARCH_MAX_LIMIT = 50
MCP_SEARCH_MAX_OFFSET = 1000

MCP_ALLOWED_SEARCH_FIELDS = {
    "id",
    "title",
    "category",
    "layer",
    "trust",
    "tags",
    "best_claim",
    "best_span",
    "best_node",
    "node_uid",
    "path",
    "heading",
    "line_start",
    "line_end",
    "citation",
    "recommended_next_tool",
    "next_action",
    "next_actions",
    "rerank_score",
    "_score",
    "_original_score",
    "_snippet",
    "content_preview",
    "temporal_state",
    "valid_from",
    "valid_until",
    "supersedes_id",
}

_COMPACT_FIELDS = (
    "id",
    "title",
    "best_claim",
    "best_span",
    "node_uid",
    "path",
    "heading",
    "line_start",
    "line_end",
    "citation",
    "recommended_next_tool",
    "next_action",
    "next_actions",
    "temporal_state",
    "valid_from",
    "valid_until",
    "supersedes_id",
)

_FULL_FIELDS = (
    "id",
    "title",
    "category",
    "layer",
    "trust",
    "tags",
    "best_claim",
    "best_span",
    "best_node",
    "node_uid",
    "path",
    "heading",
    "line_start",
    "line_end",
    "citation",
    "recommended_next_tool",
    "next_action",
    "next_actions",
    "temporal_state",
    "valid_from",
    "valid_until",
    "supersedes_id",
)


def clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def search_field_set(fields: Any) -> set[str] | None:
    if not isinstance(fields, list):
        return None
    return {str(field) for field in fields if str(field) in MCP_ALLOWED_SEARCH_FIELDS}


def shape_search_results(
    results: list[dict[str, Any]],
    *,
    compact: bool = True,
    field_set: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return MCP-safe search result payloads.

    The MCP router should stay focused on tool dispatch. This helper keeps
    compact/full search payloads, temporal metadata, and field filtering in one
    small module so future search output changes do not keep inflating mcp.py.
    """
    return [_shape_one(row, compact=compact, field_set=field_set) for row in results]


def _shape_one(row: dict[str, Any], *, compact: bool, field_set: set[str] | None) -> dict[str, Any]:
    item = _select_fields(row, _COMPACT_FIELDS if compact else _FULL_FIELDS)
    item["rerank_score"] = row.get("rerank_score", row.get("_rerank_score"))
    item["_score"] = row.get("_score")
    item["_original_score"] = row.get("_original_score")
    item["_snippet"] = row.get("_snippet")
    if not compact:
        raw = row.get("content_raw", "")
        item["content_preview"] = raw[:200] + "..." if raw and len(raw) > 200 else raw
    item = {key: value for key, value in item.items() if value is not None}
    if field_set is not None:
        item = {key: value for key, value in item.items() if key in field_set}
    return item


def _select_fields(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {key: row.get(key) for key in fields}
