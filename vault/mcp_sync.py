"""MCP read-only tools for multi-host sync visibility."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .db import VaultDB
from .multi_host import sync_status

MCP_SYNC_TOOL_NAMES = ["vault_sync_status"]

MCP_SYNC_TOOLS = [
    {
        "name": "vault_sync_status",
        "description": (
            "Read local multi-host sync health: revision counts, open conflicts, "
            "and audit events. Read-only; does not resolve conflicts or mutate memory."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum recent revisions, conflicts, and audit events to return.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
            },
        },
    }
]


def _json_result(payload: dict[str, Any]) -> dict[str, str]:
    return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}


def handle_sync_tool_call(name: str, arguments: dict[str, Any], *, db_path: str) -> dict[str, str] | None:
    """Handle MCP sync visibility calls, or return ``None`` if unknown."""
    if name not in MCP_SYNC_TOOL_NAMES:
        return None
    try:
        limit = max(1, min(int(arguments.get("limit") or 5), 20))
    except (TypeError, ValueError):
        limit = 5
    path = Path(db_path)
    if not path.exists():
        return _json_result(
            {
                "ok": False,
                "status": "blocked",
                "reason": "vault.db missing",
                "counts": {},
                "recent_revisions": [],
                "open_conflicts": [],
                "audit_events": [],
            }
        )
    with VaultDB(path) as db:
        return _json_result(sync_status(db, limit=limit))
