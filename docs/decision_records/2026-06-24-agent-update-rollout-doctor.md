# Decision Record: Agent Update Rollout Doctor

Date: 2026-06-24

## Context

Users may run several local Agent runtimes on the same machine: Codex, Claude
Code, OpenClaw, Hermes Agent, OpenCode, n8n, and other MCP-capable hosts. Each
runtime can have its own Python environment, but they may all point at the same
shared project vault.

After one runtime upgrades Vault-for-LLM, the others need a shared local signal
that tells them whether they should restart, re-register, or upgrade. The
signal must stay local, small, and readable by agents at startup.

## Decision

Add an update-distribution health check:

- `vault agent doctor`
- `vault update-status --doctor`

The doctor checks:

1. `~/.vault-for-llm/update-status.json` exists.
2. the shared notice is fresh enough for the chosen age threshold.
3. every registered Agent appears in `agent_update_notices`.
4. no registered Agent is behind the current runtime or latest known version.

`vault setup-agent` should also write:

- `agent-install/refresh-update-status.sh`
- `agent-install/README-agent-update-rollout.md`

## Safety Boundary

- This is not an auto-upgrader.
- It does not install packages in other Agent environments.
- It does not restart processes.
- It does not add new MCP tools.
- It only reports local metadata: registry entries, versions, status freshness,
  and recommended actions.

## Consequences

- One upgraded runtime can refresh the shared local status file.
- Other runtimes can read the same notice at startup and know whether they need
  attention.
- The shared vault stays coordinated without forcing all Agent environments into
  one Python install.
