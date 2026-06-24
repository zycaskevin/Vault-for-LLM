# Decision Record: Agent Adapter Startup Templates

Date: 2026-06-24

## Context

Many users run more than one Agent runtime on the same computer: Codex, Claude
Code, OpenClaw, Hermes Agent, OpenCode, n8n, and other MCP-capable systems.
Vault-for-LLM already has a shared project vault, a local Agent registry,
update-status metadata, and memory automation handoff reports. The remaining
gap is operational: each runtime needs a small, copyable startup contract so it
does not rediscover the same sequence by reading the full README.

## Decision

`vault setup-agent` should generate adapter-specific startup templates under
`agent-install/`:

- `README-agent-adapters.md`
- `codex-startup.md`
- `claude-code-startup.md`
- `openclaw-startup.md`
- `hermes-startup.md`
- `adapter-startup-contract.json`

The shared startup order is:

1. Read update status for the current `agent_id`.
2. If missing, run the local fallback without a live PyPI check.
3. Read the latest compact automation handoff.
4. Search only when the task needs more context.
5. Read bounded evidence before citing memory.
6. Propose durable lessons as candidate memory.

## Safety Boundary

- The templates do not auto-upgrade any runtime.
- The templates do not read raw transcripts by default.
- The templates do not auto-promote memory.
- Tool profiles reduce MCP schema size but are not an authorization boundary.
- Runtime identity should be public-safe and generic. Private persona details
  belong in the user's local Agent profile files, not generated public docs.

## Consequences

- Setup output becomes directly useful to Agent installers instead of only
  human readers.
- Multiple local systems can share one project vault without fragmenting memory.
- Runtime-specific instructions remain small and copyable while the durable
  contract remains machine-readable in JSON.
