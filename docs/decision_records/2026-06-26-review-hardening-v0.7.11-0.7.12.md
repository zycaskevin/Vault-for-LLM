# Review Hardening From v0.7.11 To v0.7.12

## Context

The v0.7.10 review identified four practical gaps:

- graph expansion could add neighbors before read-policy filtering,
- Base64-encoded secrets were detected only as warnings,
- temporal fact windows existed but search did not surface their state,
- `agent_id` was a governance label, not an authenticated identity.

## Decision

Vault addresses these as two small compatible releases.

v0.7.11 hardens recall behavior:

- graph expansion checks `ReadPolicy` before adding neighbor memories,
- search annotates results with `temporal_state`,
- callers can exclude past or future temporal facts when they need current-only
  recall,
- decoded Base64 content that matches fail-level secret patterns fails the
  privacy gate.

v0.7.12 adds optional signed MCP identity:

- `VAULT_MCP_REQUIRE_AGENT_SIGNATURE=1` makes every MCP call require `agent_id`
  and a valid HMAC-SHA256 `agent_signature`,
- `VAULT_MCP_AGENT_SECRET_<AGENT>` scopes secrets per local agent,
- `VAULT_MCP_AGENT_SECRET` remains a simple fallback for local deployments.

## Boundaries

This is not a full network authentication system. It is a local MCP hardening
layer for agents already running on the same machine or trusted host. Hosted or
cross-host deployments still need transport security, scoped platform tokens,
Supabase RLS/RPC, and service-role key separation.

Temporal search remains backwards-compatible: past facts are marked, not hidden,
unless the caller explicitly opts into current-only recall.

## Module Size Note

This hardening touches `vault/search.py`, `vault/mcp.py`, and `vault/cli.py`
because the same temporal and identity controls must be visible in Python API,
CLI, and MCP paths. The module-size baseline is intentionally updated for this
release with this note instead of compressing security code into less readable
forms.

Follow-up split direction:

- move MCP search schema and result shaping into a dedicated `mcp_search.py`,
- move CLI search option wiring into a smaller `cli_search.py`,
- keep temporal result annotation in `temporal.py` while leaving the search
  orchestrator responsible only for ordering filters.
