"""MCP security helpers.

This module keeps rate limiting and write-governance checks out of the main
MCP tool router so new tools can reuse the same boundary consistently.
"""

from __future__ import annotations

import os
import time
from typing import Any

from vault.access_policy import can_write_memory, normalize_write_policy

MCP_RATE_LIMIT_PER_MINUTE = 300
MCP_RATE_LIMIT_BURST = 60

_RATE_BUCKETS: dict[tuple[str, str], tuple[float, float]] = {}


def reset_rate_limiter() -> None:
    """Reset in-memory MCP rate buckets. Intended for tests."""
    _RATE_BUCKETS.clear()


def _rate_limit_config() -> tuple[int, int]:
    try:
        per_minute = int(os.environ.get("VAULT_MCP_RATE_LIMIT_PER_MINUTE", MCP_RATE_LIMIT_PER_MINUTE))
    except ValueError:
        per_minute = MCP_RATE_LIMIT_PER_MINUTE
    try:
        burst = int(os.environ.get("VAULT_MCP_RATE_LIMIT_BURST", MCP_RATE_LIMIT_BURST))
    except ValueError:
        burst = MCP_RATE_LIMIT_BURST
    return max(0, per_minute), max(1, burst)


def check_mcp_rate_limit(tool_name: str, arguments: dict[str, Any]) -> dict | None:
    per_minute, burst = _rate_limit_config()
    if per_minute <= 0:
        return None
    agent_id = str(arguments.get("agent_id") or arguments.get("owner_agent") or "anonymous").strip().lower()
    key = (agent_id or "anonymous", tool_name)
    now = time.monotonic()
    tokens, updated_at = _RATE_BUCKETS.get(key, (float(burst), now))
    refill_per_second = per_minute / 60.0
    tokens = min(float(burst), tokens + max(0.0, now - updated_at) * refill_per_second)
    if tokens < 1.0:
        retry_after = max(1, int((1.0 - tokens) / refill_per_second) if refill_per_second else 60)
        _RATE_BUCKETS[key] = (tokens, now)
        return {
            "error": "rate_limited",
            "failure_mode": "mcp_rate_limited",
            "message": f"MCP tool rate limit exceeded for {tool_name}. Retry after about {retry_after}s.",
            "retry_after_seconds": retry_after,
            "tool": tool_name,
            "agent_id": agent_id,
            "next_action": {
                "tool": tool_name,
                "arguments": arguments or {},
                "instruction": "Retry later or lower the calling cadence for this agent/tool.",
            },
        }
    _RATE_BUCKETS[key] = (tokens - 1.0, now)
    return None


def _write_policy_from_arguments(arguments: dict[str, Any]) -> object:
    return normalize_write_policy(
        agent_id=arguments.get("agent_id") or arguments.get("owner_agent") or "",
        allow_shared=bool(arguments.get("allow_shared", False)),
        allow_private=bool(arguments.get("allow_private", False)),
        allow_high_sensitivity=bool(arguments.get("allow_high_sensitivity", False)),
        allow_restricted=bool(arguments.get("allow_restricted", False)),
    )


def write_denied_payload(operation: str, reason: str, metadata: dict[str, Any]) -> dict:
    return {
        "success": False,
        "error": "write_access_denied",
        "failure_mode": "write_access_denied",
        "operation": operation,
        "message": reason,
        "scope": str(metadata.get("scope") or "project"),
        "sensitivity": str(metadata.get("sensitivity") or "low"),
        "next_action": {
            "tool": operation,
            "instruction": (
                "Use candidate review for normal writes, or pass an agent_id plus the explicit "
                "allow_* flag only after the user has approved that scope/sensitivity."
            ),
        },
    }


def check_write_allowed(operation: str, arguments: dict[str, Any], metadata: dict[str, Any]) -> dict | None:
    allowed, reason = can_write_memory(metadata, _write_policy_from_arguments(arguments))
    if allowed:
        return None
    return write_denied_payload(operation, reason, metadata)
