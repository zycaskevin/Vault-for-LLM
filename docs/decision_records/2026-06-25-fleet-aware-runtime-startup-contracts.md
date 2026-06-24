# Decision Record: Fleet-Aware Runtime Startup Contracts

Date: 2026-06-25

## Context

Multiple local runtimes can share one Vault project: Codex, Claude Code,
OpenClaw, Hermes Agent, and other MCP-capable agents. Earlier setup packs
already generated startup templates with the same broad order:

1. read update status;
2. read automation handoff;
3. search/read only when needed;
4. propose durable memory as candidates.

v0.6.105 made `vault automation handoff` fleet-aware by attaching
`fleet_health_content` when a shared fleet-health panel exists. The generated
runtime templates needed to teach agents how to consume that field.

## Decision

Generated setup files now make the handoff contract explicit:

- read `fleet_health_content` first when present;
- then read the selected cycle/inbox `content`;
- never replace the selected `content` with fleet health;
- treat fleet health as a shared automation-health preface, not private memory.

This contract is written into:

- `agent-install/mcp-startup.json`
- `agent-install/README-mcp-startup.md`
- `agent-install/adapter-startup-contract.json`
- `agent-install/README-agent-adapters.md`
- `agent-install/runtime-update-playbook.json`
- `agent-install/README-runtime-update-playbook.md`
- generated Codex, Claude Code, OpenClaw, and Hermes startup templates

## Safety Boundary

The startup contract remains read-only by default:

- no auto-upgrade;
- no raw transcript reads by default;
- no automatic memory promotion;
- no assumption that tool profiles are authorization boundaries;
- one shared project vault can coexist with private per-Agent identity/profile
  memory.

## Consequences

All generated runtime templates now share the same startup path:

```text
update-status -> fleet-aware handoff -> bounded search/read -> candidate-first propose
```

This reduces fragmented memory behavior across local agent systems while keeping
the shared health view separate from private or task-specific memory.
