# Supabase Near-Realtime Sync Boundary

Date: 2026-07-01

## Decision

Vault supports near-realtime local-to-Supabase push sync, not default
bidirectional sync.

The local `vault.db` remains the source of truth. Supabase is a shared remote
read copy for hosted agents, cross-device readers, Coze, n8n, and other systems
that cannot directly access the local SQLite file.

## Why

Users want different agents and devices to see fresh memory without manually
running a sync command. At the same time, automatic cloud-to-local writes would
introduce conflict resolution, trust, data deletion, and privacy risks.

Near-realtime push gives most of the freshness benefit while keeping the
governance boundary simple:

- local agents write to the reviewed local vault,
- a trusted local sync host pushes safe remote fields,
- remote agents read through guarded Supabase RPCs,
- cloud-hosted systems do not receive service-role keys.

## Implementation Shape

- `scripts.watch_supabase_sync` watches local `vault.db` and WAL/SHM files.
- It debounces local changes before running `scripts.sync_to_supabase`.
- It writes `reports/supabase-sync-latest.json`.
- `vault setup-agent --supabase-sync realtime` writes
  `agent-install/supabase-realtime-sync.sh`.
- `vault remote status` reports `near_realtime_push` when the realtime template
  exists.

## Non-Goals

- No automatic Supabase-to-local merge.
- No hosted write path for Coze/browser clients.
- No default service-role key placement outside trusted sync hosts.
- No claim that `--supabase-sync all` starts a realtime watcher; realtime must
  be explicitly requested.
