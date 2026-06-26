"""MCP security helpers.

This module keeps rate limiting and write-governance checks out of the main
MCP tool router so new tools can reuse the same boundary consistently.
"""

from __future__ import annotations

import os
import hmac
import hashlib
import json
import time
from typing import Any

from vault.access_policy import can_write_memory, normalize_write_policy

MCP_RATE_LIMIT_PER_MINUTE = 300
MCP_RATE_LIMIT_BURST = 60

_RATE_BUCKETS: dict[tuple[str, str], tuple[float, float]] = {}
_SIGNATURE_FIELDS = {"agent_signature", "signature", "agent_secret"}


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


def _truthy_env(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _agent_secret(agent_id: str) -> str:
    normalized = "".join(ch if ch.isalnum() else "_" for ch in str(agent_id or "").upper()).strip("_")
    if normalized:
        scoped = os.environ.get(f"VAULT_MCP_AGENT_SECRET_{normalized}")
        if scoped:
            return scoped
    return os.environ.get("VAULT_MCP_AGENT_SECRET", "")


def _canonical_signed_arguments(arguments: dict[str, Any]) -> str:
    safe_args = {
        str(key): value
        for key, value in (arguments or {}).items()
        if str(key) not in _SIGNATURE_FIELDS
    }
    return json.dumps(safe_args, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sign_agent_request(tool_name: str, arguments: dict[str, Any], secret: str) -> str:
    """Return an HMAC signature for MCP agent identity checks.

    This helper is deterministic so tests, adapters, and local setup scripts can
    generate the exact value Vault expects without exposing the secret in logs.
    """
    payload = f"{tool_name}\n{_canonical_signed_arguments(arguments)}"
    return hmac.new(str(secret or "").encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def check_agent_signature(tool_name: str, arguments: dict[str, Any]) -> dict | None:
    """Optionally verify signed MCP agent identity.

    Disabled by default for backwards compatibility. When
    ``VAULT_MCP_REQUIRE_AGENT_SIGNATURE=1`` is set, every MCP call needs an
    ``agent_id`` plus ``agent_signature``. If a caller provides a signature while
    the gate is optional, Vault still verifies it and rejects invalid signatures.
    """
    arguments = arguments or {}
    signature = str(arguments.get("agent_signature") or arguments.get("signature") or "").strip()
    require = _truthy_env("VAULT_MCP_REQUIRE_AGENT_SIGNATURE")
    if not require and not signature:
        return None

    agent_id = str(arguments.get("agent_id") or arguments.get("owner_agent") or "").strip().lower()
    if not agent_id:
        return _signature_denied(tool_name, "signed MCP calls require agent_id", agent_id)
    secret = _agent_secret(agent_id)
    if not secret:
        return _signature_denied(tool_name, "no MCP agent secret configured for agent_id", agent_id)
    expected = sign_agent_request(tool_name, arguments, secret)
    if not signature or not hmac.compare_digest(signature, expected):
        return _signature_denied(tool_name, "invalid MCP agent signature", agent_id)
    return None


def _signature_denied(tool_name: str, message: str, agent_id: str) -> dict:
    return {
        "error": "agent_signature_required",
        "failure_mode": "agent_signature_required",
        "message": message,
        "tool": tool_name,
        "agent_id": agent_id,
        "next_action": {
            "tool": tool_name,
            "instruction": (
                "Configure VAULT_MCP_AGENT_SECRET or VAULT_MCP_AGENT_SECRET_<AGENT>, "
                "then sign the MCP arguments with HMAC-SHA256."
            ),
        },
    }


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
