# Vault Gateway v0

## Context

Vault is becoming a shared memory layer for many agent runtimes: Codex, Claude
Code, OpenClaw, Hermes Agent, Coze, n8n, and future devices. Asking every
runtime to learn every CLI command, MCP tool profile, Supabase path, and local
database rule makes the system harder to adopt and harder to secure.

The product direction is adapter-based: hands, tools, hosted readers, and
devices can change, but the user should keep one governed memory vault.

## Decision

Add `vault gateway serve` as a thin HTTP entrypoint for agent memory access.

Gateway v0 is intentionally small:

- `GET /health`
- `POST /search`
- `POST /read-range`
- `POST /submit-candidate`

It is not a new database, not a sync engine, and not a direct active-knowledge
writer. It sits in front of the local project vault and applies the same safety
defaults agents should use everywhere else:

- reads require `agent_id`;
- private memory is hidden by default;
- max readable sensitivity defaults to `low`;
- search results hide raw content by default;
- writes create `memory_candidates` only;
- shared, private, high-sensitivity, or restricted candidates require explicit
  server launch flags;
- token authentication is enabled by default;
- `--no-auth` is allowed only for localhost binds;
- every request writes a compact audit row under `reports/gateway/audit.jsonl`.

## Why Not Merge Everything Into MCP?

MCP remains the preferred direct integration for MCP-native runtimes. Gateway
serves a different role: one small HTTP door for runtimes, hosted tools, local
scripts, and future devices that should not need to understand the full CLI or
MCP schema surface.

## Why Candidate-First Writes?

Gateway will often sit between many agents and one vault. Direct active-memory
writes would make memory pollution and permission mistakes too easy. Candidate
submission gives agents a common way to contribute without bypassing review,
automation gates, promotion rules, or the daily 5% human report.

## Consequences

Gateway gives the project a stable public integration shape:

```text
Agent / device / workflow
  -> Vault Gateway
  -> local SQLite vault today
  -> Supabase / hosted Vault Remote / other adapters later
```

This keeps Vault focused on unified memory governance while leaving storage and
transport adapters replaceable.

Future work:

- setup-agent templates that can generate Gateway client snippets for each
  runtime;
- optional Gateway adapter for remote candidate sync;
- per-agent temporary grants and richer audit views;
- hosted Vault Remote that can use the same endpoint contract.
