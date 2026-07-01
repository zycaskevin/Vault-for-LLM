# Remote Sharing Status Boundary

## Context

Vault-for-LLM is moving toward one shared memory base that can be used by Codex,
Claude Code, OpenClaw, Hermes, Coze, n8n, and other agents. Supabase remote
readers are useful for hosted or cross-host agents, and remote agents may submit
candidate requests, but the current supported model is not active-knowledge
multi-master sync.

The product needs a clear status surface so agents and users can see whether
they are using:

- a local SQLite vault as the source of truth,
- a Supabase reviewed read copy plus candidate request inbox,
- generated sync and remote-reader templates,
- a recent local sync report,
- reviewed multi-agent access policy files.

## Decision

Add `vault remote status` as an offline diagnostic command.

It does not contact Supabase and does not require remote credentials. It reads
only local state:

- `vault.db` summary,
- `agent-install/` Supabase setup, sync, remote-reader, and access files,
- optional sync report files,
- safe environment-variable presence checks,
- local Agent registry entries.

The command must explicitly say that:

- local `vault.db` is the source of truth,
- Supabase is a reviewed read copy plus candidate request inbox,
- the default sync direction is local-to-Supabase,
- active memory sync is not real-time bidirectional,
- remote freshness is unknown unless a local sync report exists.

`vault remote smoke` and `vault remote doctor` remain the live remote checks.

## Consequences

- New users can understand the sharing topology before handling API keys.
- Agents can include `vault remote status --json` in startup checks without
  network access.
- Hosted readers can be warned away from service-role keys.
- Future true bidirectional sync work must update this status surface and this
  decision record before claiming bidirectional support.
