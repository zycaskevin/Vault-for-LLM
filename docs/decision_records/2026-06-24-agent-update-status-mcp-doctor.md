# Decision Record: MCP Update Status Doctor Mode

Date: 2026-06-24

## Context

Vault-for-LLM v0.6.85 added CLI update-distribution health checks through
`vault agent doctor` and `vault update-status --doctor`. MCP-only Agent
runtimes still needed a shell command to run the same check.

The project already treats MCP tool count as a token-budget concern, so the
right design is to extend the existing startup tool rather than add another
tool.

## Decision

Extend MCP `vault_update_status` with:

- `doctor: true`
- `max_status_age_minutes`
- existing `agent_id` focus

The doctor mode returns the same local metadata as the CLI doctor:

- status file existence
- freshness
- status/runtime version mismatch
- registered Agent coverage
- Agent runtimes needing attention
- recommended actions

## Safety Boundary

- No new MCP tool is added.
- No package install, upgrade, process restart, or memory mutation happens.
- The response is local metadata only.
- `check_pypi` remains opt-in and is not needed for doctor mode.

## Consequences

Codex, Claude Code, OpenClaw, Hermes Agent, and other MCP-capable runtimes can
complete the startup loop through MCP alone:

1. read status;
2. run doctor when freshness or rollout state is unclear;
3. read handoff;
4. search/read/propose only when needed.
