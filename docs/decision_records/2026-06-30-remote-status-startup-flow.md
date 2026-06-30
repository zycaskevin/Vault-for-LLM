# Remote Status Startup Flow

## Context

Vault-for-LLM now supports multiple local and hosted agents sharing one project
memory base. `vault remote status` explains the local-to-Supabase sharing
boundary without contacting Supabase. The next step is making that check part
of generated agent startup instructions so runtimes do not skip it.

## Decision

Generated startup artifacts should include `vault remote status --json` as a
CLI preflight between update-status and automation handoff.

This remains a CLI preflight rather than a new MCP tool because:

- it avoids increasing the default MCP tool/schema surface,
- it does not need network access or remote credentials,
- it is mainly a topology and safety check,
- CLI-capable agents can run it before live remote reader calls.

The startup-doctor contract checks for this preflight so older install packs
can be regenerated when they lack remote sharing guidance.

## Consequences

- Codex, Claude Code, OpenClaw, Hermes, and similar runtimes get the same remote
  sharing boundary in generated templates.
- Hosted-reader setups are less likely to confuse Supabase read copies with
  real-time bidirectional sync.
- Future MCP support can still be added later if the command becomes valuable
  enough to justify a dedicated tool.
