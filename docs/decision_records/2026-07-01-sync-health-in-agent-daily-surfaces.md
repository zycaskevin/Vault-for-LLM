# Sync Health In Agent Daily Surfaces

Date: 2026-07-01

## Decision

Multi-host sync health should appear in the surfaces agents and humans already
check every day:

- `vault automation brief`
- `vault automation fleet-health`
- `vault automation handoff`
- `vault daily-report`
- the GUI Agent Dashboard / Sync Health card
- MCP `vault_sync_status`

The sync signal is read-only. It reports open conflicts, revision count, and
audit event count. It does not read raw private memory and does not mutate active
knowledge.

## Why

The product direction is "one memory vault for many agents and devices", but
normal users should not need to learn a long sync command list. If an OpenClaw,
Hermes, Codex, Claude Code, n8n, or hosted agent submits a remote memory
candidate, the local review loop should surface the important 5% automatically.

Putting sync health into daily/agent startup surfaces gives the right default:

1. Agents see open conflicts before doing new work.
2. Humans see only short review cards.
3. Remote candidates stay candidate-first.
4. Active memory is not overwritten by remote hosts.

## Boundary

This is not real-time multi-master active-memory sync.

Open conflicts are review items. A trusted local Vault still decides whether a
candidate is promoted, rejected, deferred, or manually resolved. Low-risk
automatic promotion remains controlled by local automation policy and gates.

## Product Language

Use this phrasing:

> Remote agents can submit memory candidates. Vault surfaces sync conflicts in
> the daily report, GUI, MCP, and agent handoff so a trusted local workflow can
> review them before active memory changes.

Avoid saying:

> Vault automatically merges all machines into one live shared memory.

That would imply an active multi-master database boundary that is intentionally
not enabled yet.
