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


def test_mcp_agent_signature_optional_without_signature(monkeypatch):
    monkeypatch.delenv("VAULT_MCP_REQUIRE_AGENT_SIGNATURE", raising=False)
    monkeypatch.delenv("VAULT_MCP_AGENT_SECRET", raising=False)

    assert mcp_security.check_agent_signature("vault_stats", {"agent_id": "agent-a"}) is None


def test_mcp_agent_signature_required_rejects_missing_signature(monkeypatch):
    monkeypatch.setenv("VAULT_MCP_REQUIRE_AGENT_SIGNATURE", "1")
    monkeypatch.setenv("VAULT_MCP_AGENT_SECRET", "local-secret")

    denied = mcp_security.check_agent_signature("vault_stats", {"agent_id": "agent-a"})

    assert denied is not None
    assert denied["error"] == "agent_signature_required"
    assert "invalid" in denied["message"] or "require" in denied["message"]


def test_mcp_agent_signature_required_accepts_valid_hmac(monkeypatch):
    monkeypatch.setenv("VAULT_MCP_REQUIRE_AGENT_SIGNATURE", "1")
    monkeypatch.setenv("VAULT_MCP_AGENT_SECRET_AGENT_A", "scoped-secret")
    args = {"agent_id": "agent-a", "query": "deployment"}
    args["agent_signature"] = mcp_security.sign_agent_request("vault_search", args, "scoped-secret")

    assert mcp_security.check_agent_signature("vault_search", args) is None


def test_mcp_agent_signature_optional_rejects_bad_signature(monkeypatch):
    monkeypatch.delenv("VAULT_MCP_REQUIRE_AGENT_SIGNATURE", raising=False)
    monkeypatch.setenv("VAULT_MCP_AGENT_SECRET", "local-secret")

    denied = mcp_security.check_agent_signature(
        "vault_stats",
        {"agent_id": "agent-a", "agent_signature": "bad"},
    )

    assert denied is not None
    assert denied["failure_mode"] == "agent_signature_required"
