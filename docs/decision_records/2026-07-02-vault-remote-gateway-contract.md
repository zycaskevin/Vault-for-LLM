# Vault Remote Starts As A Gateway Contract

## Context

Vault-for-LLM is moving toward one governed memory base that many agents,
devices, tools, and hosted workflows can use. The user wants Codex, Claude Code,
OpenClaw, Hermes Agent, Coze, n8n, Obsidian, future robots, cars, phones, and
home devices to point at the same memory system instead of each tool keeping a
separate memory silo.

There are two possible next steps:

1. build a large self-hosted Vault Remote server immediately;
2. make the existing Gateway contract stable enough that local and remote
   adapters can share the same small interface first.

## Decision

Start with the Gateway contract.

`vault gateway serve` remains the small HTTP adapter in front of a governed
local project vault. It now exposes the same machine-readable contract in two
ways:

- `GET /openapi.json`
- `vault gateway openapi --json`

The contract is intentionally narrow:

- `/health`
- `/openapi.json`
- `/search`
- `/read-range`
- `/submit-candidate`

The contract also documents the safety boundary:

- agents must identify themselves with `agent_id` for reads;
- private memory is hidden by default;
- max sensitivity defaults to `low`;
- search does not return raw content;
- writes create `memory_candidates`, not active knowledge;
- active multi-master sync is not part of Gateway v0.

## Why This First

This keeps the architecture adapter-based. Gateway can be the local HTTP door
today, Supabase can stay an optional remote read/candidate adapter, and a future
self-hosted Vault Remote server can reuse the same contract instead of inventing
another integration surface.

This also gives non-MCP systems a stable path. Coze, n8n, OpenClaw plugins,
local scripts, and future devices can discover the request shapes from
`/openapi.json` without learning the full CLI or MCP schema.

## Non-Goals

This pass does not add:

- active knowledge writes through Gateway;
- true active multi-master sync;
- a hosted service;
- a new cloud dependency;
- Obsidian real-time bidirectional mirroring.

Obsidian should still become a strong human-facing GUI, but real-time
bidirectional mirroring and conflict UI are a separate product slice.

## Consequences

The integration model becomes:

```text
Agent / workflow / device
  -> Gateway contract
  -> local SQLite vault today
  -> Supabase adapter or Vault Remote adapter later
```

Vault keeps focusing on unified memory governance, while transport and storage
adapters remain replaceable hands and feet.
