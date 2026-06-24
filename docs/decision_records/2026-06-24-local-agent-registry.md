# Decision Record: Local Agent Registry Before Full Hybrid Vault Layout

Date: 2026-06-24

## Context

Vault-for-LLM needs to support multiple local Agent runtimes on the same
machine. A user may connect coding agents, companion agents, workflow agents,
automation tools, and remote readers to the same project memory. If every
runtime installs and tracks Vault independently, updates, handoffs, project
paths, and memory boundaries become fragmented.

## Decision

Add a local multi-agent registry before changing the physical vault layout.

The registry records which Agents are connected to Vault on this machine and
which project vault they use. It does not store private conversation content or
agent persona data.

Default registry path:

```text
~/.vault-for-llm/agent-registry.json
```

## Product Behavior

`vault setup-agent` automatically registers the configured Agent. Manual
registration is also available:

```bash
vault agent register --agent codex --project ~/Vaults/my-project --scope shared
```

Any Agent can inspect local status with:

```bash
vault update-status
```

The status view should show:

- installed Vault version
- optional latest-version comparison
- registered Agents
- project vault paths
- suggested startup commands, especially `vault automation handoff --project-dir ...`

## Boundary

The registry is a local coordination file, not an authorization system and not a
memory store. Access control still belongs to vault metadata, Supabase RLS/RPC
when remote sync is enabled, and future private/shared vault layout rules.

The status command should not contact the network by default. Agents can opt
into PyPI checking with `--check-pypi`, or pass a known version with
`--latest-version`.

## Deferred

- Full hybrid physical layout: shared project vault plus per-Agent private
  vaults.
- MCP tool access for update status and handoff.
- Automated upgrade execution. For now, Vault should report update status and
  suggest next steps; applying upgrades remains explicit.
