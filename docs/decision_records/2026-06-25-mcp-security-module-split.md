# MCP Security Module Split

Date: 2026-06-25

## Context

Vault-for-LLM's MCP server has become the main bridge between a vault and agent runtimes. Security checks such as rate limiting and write governance were added to protect shared and private memory boundaries, but those checks lived inline inside the main tool router.

Inline security logic works for a small router, but it becomes harder to audit as the MCP surface grows.

## Decision

Move MCP rate limiting and write-governance helpers into `vault.mcp_security`.

The public MCP router keeps the existing function aliases and behavior:

- `vault_add` and `vault_memory_promote` still use the same write-denial policy.
- Rate-limited calls still return the same structured `rate_limited` payload.
- Existing tests that call `vault.mcp._reset_rate_limiter()` continue to work.

## Consequences

The MCP router is smaller, and future tools can reuse one security helper module instead of copying write-policy or rate-limit logic.

This change is intentionally narrow. It does not introduce a new authentication system, change MCP tool names, or change shared-vault write requirements. It only makes the current security boundary easier to test and maintain.

## Follow-Ups

- Continue splitting the MCP router by concern after security behavior is stable.
- Add module-size gates so large files do not quietly grow past reviewable size.
- Keep remote-reader and Supabase access checks documented separately from local MCP governance.
