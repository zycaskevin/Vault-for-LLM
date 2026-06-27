"""Shared search constants and small utility helpers."""

from __future__ import annotations

import re

DEFAULT_KEYWORD_MIN_SCORE = 0.34
MAX_LIMIT = 500
MAX_GRAPH_EXPAND_DEPTH = 5


def _normalize_text(value: str) -> str:
    """Normalize text for best-effort claim matching."""
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def normalize_search_limit(value: object, *, default: int = 10, maximum: int = MAX_LIMIT) -> int:
    """Return a safe search/list limit.

    User-facing CLI parsers reject non-positive limits where appropriate. This
    helper protects lower-level Python and MCP paths too: a non-positive value
    means "return no rows", never "SQLite LIMIT -1".
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    if parsed <= 0:
        return 0
    return min(parsed, int(maximum))
