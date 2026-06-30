"""Security diagnostics for local agent-facing Vault surfaces."""

from __future__ import annotations

import os
from typing import Mapping, Any


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "require", "required"}


def security_doctor(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Return a compact security posture report for CLI and setup smoke tests."""
    env_map = env or os.environ
    require_hmac = _truthy(env_map.get("VAULT_MCP_REQUIRE_AGENT_SIGNATURE", ""))
    agent_secret_keys = sorted(key for key in env_map if key.startswith("VAULT_MCP_AGENT_SECRET"))
    gui_token = str(env_map.get("VAULT_GUI_TOKEN", "")).strip()

    checks = [
        {
            "id": "mcp_hmac_required",
            "ok": require_hmac,
            "severity": "warn",
            "message": (
                "MCP HMAC signatures are required."
                if require_hmac
                else "MCP HMAC signatures are optional. Set VAULT_MCP_REQUIRE_AGENT_SIGNATURE=1 for stricter agent identity checks."
            ),
        },
        {
            "id": "mcp_agent_secret_configured",
            "ok": bool(agent_secret_keys),
            "severity": "warn",
            "message": (
                f"Configured MCP agent secret env keys: {', '.join(agent_secret_keys)}."
                if agent_secret_keys
                else "No VAULT_MCP_AGENT_SECRET* key is configured; signed MCP calls cannot be verified."
            ),
        },
        {
            "id": "gui_token_default",
            "ok": True,
            "severity": "info",
            "message": (
                "VAULT_GUI_TOKEN is configured; GUI will reuse it."
                if gui_token
                else "GUI generates an ephemeral token by default; pass --no-auth only for localhost testing."
            ),
        },
        {
            "id": "mcp_read_default",
            "ok": True,
            "severity": "info",
            "message": "MCP local read tools default to max_sensitivity=medium unless a stricter/elevated value is explicitly provided.",
        },
    ]
    warn_count = sum(1 for item in checks if not item["ok"] and item["severity"] == "warn")
    return {
        "ok": warn_count == 0,
        "warning_count": warn_count,
        "checks": checks,
        "next_action": (
            "For shared or untrusted agent runtimes, enable HMAC and configure per-agent secrets."
            if warn_count
            else "Security defaults look ready for local agent use."
        ),
    }
