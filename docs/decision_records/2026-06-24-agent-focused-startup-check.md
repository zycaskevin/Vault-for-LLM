# Agent-Focused Startup Check

Date: 2026-06-24

## Context

After v0.6.82, Vault-for-LLM can write and read one machine-level
`update-status.json` for multiple local Agent runtimes. The next install
experience should let each Agent ask a narrower question during startup:

> Do I, this specific Agent runtime, need an upgrade, restart, or registry
> refresh before using shared memory?

## Decision

Do not add a new MCP tool for this. Extending `vault_update_status` keeps the
core MCP profile compact.

CLI and MCP should support an optional Agent focus:

- CLI: `vault update-status --read-status --agent <agent-id>`
- MCP: `vault_update_status(read_status=true, agent_id="<agent-id>")`

The response keeps the existing full status payload and adds focused fields:

- `startup_agent_id`
- `startup_agent_registered`
- `current_agent`
- `current_agent_notice`
- `current_agent_needs_attention`
- `current_agent_recommended_action`
- `startup_checklist`

## Consequences

- Agent startup can be more automatic without auto-upgrading anything.
- Tool count does not increase.
- Existing callers that do not pass `agent_id` keep the old payload shape.
- Setup-generated startup contracts should use `agent_id` by default so each
  runtime sees its own update/restart advice first.
