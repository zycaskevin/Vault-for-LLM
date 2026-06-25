"""Shared governance metadata normalization."""

from __future__ import annotations

import json
from typing import Any

from .temporal import normalize_temporal_metadata

_VALID_SCOPES = {"private", "project", "shared", "public"}
_VALID_SENSITIVITIES = {"low", "medium", "high", "restricted"}


def normalize_allowed_agents(value: Any = None) -> str:
    """Return allowed agent names as a compact JSON array string."""
    if value is None or value == "":
        return "[]"
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value if str(item).strip()]
        return json.dumps(items, ensure_ascii=False)
    text = str(value).strip()
    if not text:
        return "[]"
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            items = [str(item).strip() for item in parsed if str(item).strip()]
            return json.dumps(items, ensure_ascii=False)
    items = [part.strip() for part in text.split(",") if part.strip()]
    return json.dumps(items, ensure_ascii=False)


def normalize_governance_metadata(
    *,
    scope: str = "project",
    sensitivity: str = "low",
    owner_agent: str = "",
    allowed_agents: Any = None,
    memory_type: str = "knowledge",
    expires_at: str = "",
    valid_from: str = "",
    valid_until: str = "",
    supersedes_id: int | str | None = None,
) -> dict[str, Any]:
    """Normalize memory-governance fields shared by DB, CLI, MCP, and sync."""
    norm_scope = str(scope or "project").strip().lower()
    if norm_scope not in _VALID_SCOPES:
        norm_scope = "project"
    norm_sensitivity = str(sensitivity or "low").strip().lower()
    if norm_sensitivity not in _VALID_SENSITIVITIES:
        norm_sensitivity = "low"
    if hasattr(expires_at, "isoformat"):
        norm_expires_at = expires_at.isoformat()
    else:
        norm_expires_at = str(expires_at or "").strip()
    return {
        "scope": norm_scope,
        "sensitivity": norm_sensitivity,
        "owner_agent": str(owner_agent or "").strip(),
        "allowed_agents": normalize_allowed_agents(allowed_agents),
        "memory_type": str(memory_type or "knowledge").strip() or "knowledge",
        "expires_at": norm_expires_at,
        **normalize_temporal_metadata(
            valid_from=valid_from,
            valid_until=valid_until,
            supersedes_id=supersedes_id,
        ),
    }
