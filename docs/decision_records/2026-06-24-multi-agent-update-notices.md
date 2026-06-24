# Decision Record: Multi-Agent Update Notices

Date: 2026-06-24

## Decision

`vault update-status` and MCP `vault_update_status` should return per-Agent
update notices from the local Agent registry.

Each notice should show:

- the registered Agent id
- the project vault path
- the private vault path when one exists
- the Vault version recorded when that Agent last registered
- whether the Agent is behind the current runtime version
- whether the Agent is behind the latest known version when one is provided
- a short recommended action

When `--write-status` or MCP `write_status=true` is used, the same payload is
written to `~/.vault-for-llm/update-status.json` so other local runtimes can
read the latest machine-level update message.

## Rationale

Users may install Vault-for-LLM into several local runtimes on the same machine:
Codex, Claude Code, OpenClaw, Hermes Agent, n8n helpers, or other MCP-capable
systems. Those runtimes may use different virtualenvs and may not update at the
same time.

A shared registry lets Vault avoid scattered memory management:

1. `setup-agent` registers each runtime once.
2. one updated runtime can run `vault update-status --write-status`.
3. future runtimes can call CLI `vault update-status` or MCP
   `vault_update_status`.
4. the response names which registered Agents may need an upgrade or restart.

This keeps update notification local, inspectable, and optional. It does not
require a cloud service.

## Safety Boundary

- Update checks do not contact PyPI unless `check_pypi=true`.
- The status file contains paths, Agent ids, and version metadata only.
- The status file does not include raw memory, transcript content, API keys, or
  private note bodies.
- The notice is advisory. It does not modify other virtualenvs or restart
  agents.

## Non-goals

- This does not auto-upgrade every Agent environment.
- This does not replace OS package managers or runtime-specific extension
  update systems.
- This does not change shared/private vault access rules.
