# Automation Fleet Health

Date: 2026-06-25
Status: accepted

## Context

Vault-for-LLM can now run scheduled memory automation, write compact cycle
handoffs, write review inboxes, and report learning-health. Multi-Agent installs
also have a local Agent registry and update-distribution health checks.

The missing operator view was a single short panel that answers:

- which Agent runtimes are registered for this shared project,
- whether automation learning is healthy,
- whether update-status distribution needs attention.

## Decision

Add `vault automation fleet-health` as a read-only CLI/report surface.

It combines:

- local Agent registry metadata,
- `automation learning-health` status,
- update-distribution health.

With `--write-health`, it writes:

- `reports/automation/fleet-health-latest.json`
- `reports/automation/fleet-health-latest.md`

## Safety

- Fleet health is read-only.
- It does not promote, archive, delete, or rewrite memory.
- It does not read private memory.
- It does not include raw candidate content.
- It does not include raw feedback reasons.
- It uses Agent registry metadata only for runtime visibility.

## MCP Boundary

Fleet health is not added to the `core` MCP profile in this step. Core agents
already have `vault_automation_brief`, `vault_automation_handoff`, and
`vault_update_status`. Keeping fleet health as a generated report and CLI
surface avoids adding another always-visible MCP tool while still giving
dashboards and scheduled jobs a shared status file.

## Consequences

Shared installs can now expose one compact automation health panel across
Hermes, Codex, Claude Code, OpenClaw, n8n, or other registered runtimes without
scattering private memory or increasing the default MCP tool surface.
