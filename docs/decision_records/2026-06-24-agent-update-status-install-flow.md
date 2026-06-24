# Agent Update Status Install Flow

Date: 2026-06-24

## Context

Vault-for-LLM can now register multiple local Agent runtimes and report
per-Agent update notices through `vault update-status` and MCP
`vault_update_status`. The remaining product gap is installation: every Agent
should know how to read the same machine-level update notice without creating a
separate version-check workflow.

## Decision

`vault setup-agent` should generate an update-status install pack next to the
other Agent templates. The pack explains the shared local status file,
read/write commands, MCP startup contract, and optional scheduler templates.

Agents should prefer this order:

1. read an existing local status file;
2. if missing, ask Vault for live local registry status without network access;
3. only check PyPI when the user explicitly asks for a live version check;
4. never auto-upgrade another Agent runtime.

## Consequences

- `~/.vault-for-llm/update-status.json` is machine-level metadata only. It
  reports versions, registered Agents, vault paths, and handoff commands.
- CLI and MCP both need a read-only path for existing status data:
  `vault update-status --read-status` and `vault_update_status(read_status=true)`.
- Setup-generated cron and LaunchAgent examples write local status on a schedule
  without contacting PyPI by default.
- MCP startup guides should read existing update status first and document the
  bounded fallback.
