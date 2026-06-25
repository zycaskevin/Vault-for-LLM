from vault import mcp_security


def test_mcp_security_rate_limit_can_be_disabled(monkeypatch):
    mcp_security.reset_rate_limiter()
    monkeypatch.setenv("VAULT_MCP_RATE_LIMIT_PER_MINUTE", "0")

    assert mcp_security.check_mcp_rate_limit("vault_stats", {"agent_id": "agent-a"}) is None
    assert mcp_security.check_mcp_rate_limit("vault_stats", {"agent_id": "agent-a"}) is None


def test_mcp_security_rate_limit_invalid_env_falls_back(monkeypatch):
    mcp_security.reset_rate_limiter()
    monkeypatch.setenv("VAULT_MCP_RATE_LIMIT_PER_MINUTE", "not-an-int")
    monkeypatch.setenv("VAULT_MCP_RATE_LIMIT_BURST", "not-an-int")

    assert mcp_security.check_mcp_rate_limit("vault_stats", {"agent_id": "agent-a"}) is None


def test_mcp_security_write_gate_requires_explicit_shared_grant():
    denied = mcp_security.check_write_allowed(
        "vault_add",
        {"agent_id": "agent-a"},
        {"scope": "shared", "sensitivity": "low"},
    )
    allowed = mcp_security.check_write_allowed(
        "vault_add",
        {"agent_id": "agent-a", "allow_shared": True},
        {"scope": "shared", "sensitivity": "low"},
    )

    assert denied is not None
    assert denied["error"] == "write_access_denied"
    assert "allow_shared" in denied["message"]
    assert allowed is None
