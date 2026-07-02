"""MCP tools for Gateway observability."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .gateway_audit import gateway_audit_report


MCP_GATEWAY_TOOL_NAMES = ["vault_gateway_audit"]

MCP_GATEWAY_TOOLS = [
    {
        "name": "vault_gateway_audit",
        "description": (
            "Read Gateway audit health: auth failures, blocked requests, rate-limit/IP policy hits, "
            "and recent safe audit events. Read-only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum recent audit events to return.",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                },
                "event": {
                    "type": "string",
                    "description": "Optional event filter, such as auth_failed or request_blocked.",
                    "default": "",
                },
            },
        },
    }
]


def _json_result(payload: dict[str, Any]) -> dict[str, str]:
    return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}


def handle_gateway_tool_call(name: str, arguments: dict[str, Any], *, db_path: str) -> dict[str, str] | None:
    """Handle MCP Gateway observability calls, or return ``None`` if unknown."""
    if name not in MCP_GATEWAY_TOOL_NAMES:
        return None
    try:
        limit = max(1, min(int(arguments.get("limit") or 20), 100))
    except (TypeError, ValueError):
        limit = 20
    project = Path(db_path).expanduser().resolve().parent
    payload = gateway_audit_report(
        project,
        limit=limit,
        event=str(arguments.get("event", "") or ""),
    )
    return _json_result(payload)
