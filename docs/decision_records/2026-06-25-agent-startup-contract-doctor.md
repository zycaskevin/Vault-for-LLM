# Decision Record: Agent Startup Contract Doctor

Date: 2026-06-25

## Context

Vault can generate startup packs for multiple local agent runtimes. After
v0.6.105 and v0.6.106, the current startup contract became fleet-aware:

```text
update-status -> fleet-aware handoff -> bounded search/read -> candidate-first propose
```

Older generated `agent-install/` folders may still exist on user machines. If an
agent keeps using an old `mcp-startup.json`, adapter contract, or runtime
template, it may miss `fleet_health_content` or treat fleet health as a
replacement for the selected cycle/inbox handoff.

## Decision

Add `vault agent startup-doctor` as a read-only setup-pack health check.

The doctor checks:

- `mcp-startup.json`
- `adapter-startup-contract.json`
- `runtime-update-playbook.json`
- Codex, Claude Code, OpenClaw, and Hermes startup templates
- generated startup README files

The expected handoff contract is:

- read `fleet_health_content` first when present;
- then read selected cycle/inbox `content`;
- do not replace `content` with fleet health.

## Output Contract

The command returns:

- `ok`
- `status`: `pass`, `warn`, or `fail`
- `checks[]`
- `missing_files[]`
- `outdated_files[]`
- `recommended_actions[]`

This lets shell-capable agents and MCP wrappers decide whether to regenerate the
setup pack before starting work.

## Safety Boundary

The doctor only reads generated setup files. It does not:

- edit runtime instruction files;
- read private memory;
- promote memory;
- query PyPI or run network update checks;
- restart or upgrade any runtime.

## Consequences

Users can now verify whether an already-installed agent startup pack follows the
latest fleet-aware startup rule before relying on it.
