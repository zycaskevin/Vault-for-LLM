# Decision Record: MCP Startup Status And Handoff

Date: 2026-06-24

## Decision

Expose the existing local startup checks through MCP:

- `vault_update_status` returns the same local runtime, version, registry, shared vault, private vault, and startup command payload as `vault update-status`.
- `vault_automation_handoff` reads the latest compact automation handoff, matching `vault automation handoff`.

Both tools belong in the `core` MCP profile because they are startup-oriented,
small, and read-first. Review queues, transcript capture, Dream, and maintenance
tools remain outside `core`.

## Safety Boundary

- `vault_update_status` does not contact PyPI unless `check_pypi=true`.
- `vault_update_status` does not write `update-status.json` unless `write_status=true`.
- `vault_automation_handoff` only reads existing files under `reports/automation`.
- `vault_automation_handoff` does not inspect raw transcript contents, promote candidates, or mutate active memory.

This keeps the Agent startup path bounded:

1. Ask Vault what version and Agent registry state are known.
2. Read the compact handoff for the relevant project vault.
3. Search and read bounded evidence only when the handoff says more context is needed.

## Rationale

Users may run several local Agents or runtimes on the same machine. If every
runtime has to shell out manually, startup behavior becomes inconsistent. MCP
startup tools let Hermes Agent, Codex, Claude Code, OpenClaw, and other
MCP-capable systems use the same shared registry and handoff flow without
expanding the daily tool surface too much.

## Non-goals

- This is not a remote update service.
- This is not a security boundary by itself.
- This does not make the automation loop promote or delete memory.
- This does not replace `vault setup-agent`; setup remains the installer and
  registry writer.
