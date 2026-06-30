# Skill MCP Write And Sync Strategy

Date: 2026-06-30

Status: Accepted

## Context

Vault now has a local Skill Registry with latest-version rows, revision history,
and upgrade planning. Agents need a way to coordinate Skill changes through MCP,
but Skill updates are sensitive: a bad tool design could let one agent silently
overwrite another runtime's actual Skill files.

## Decision

MCP Skill writes are allowed only as registry operations.

- `review` profile may inspect Skill metadata, version history, upgrade plans,
  sync status, and sync manifests.
- `maintenance` and `full` profiles may also write to the local registry with
  explicit permission flags.
- `core` profile does not expose Skill tools.
- MCP Skill tools never install, overwrite, or delete runtime Skill files.
- Raw Skill content is omitted from sync manifests unless a trusted worker sets
  an explicit content-export flag.
- Skill registry writes are privacy-gated and require an explicit write flag.
- Sync completion is recorded with a separate `mark_synced` operation after an
  external trusted sync worker succeeds.

## Rationale

This gives agents enough surface to cooperate on capability handoff without
turning Vault into a runtime package manager. A registry write is reviewable and
auditable. A runtime install remains an operator-approved step because each
agent platform has different file locations, activation rules, and safety
constraints.

## Consequences

Agents can now:

- propose or revise shared Skill registry entries through MCP,
- build compact sync manifests for Supabase, n8n, or other external workers,
- detect pending Skill sync work without reading raw Skill content,
- mark a Skill as synced after an external job completes.

Agents still cannot:

- silently modify Codex, Claude Code, Hermes Agent, OpenClaw, or OpenCode Skill
  directories,
- export raw Skill content by default,
- write Skill registry rows from the smallest `core` MCP profile.

Future work may add platform-specific runtime installers, but those installers
should remain explicit, auditable, and separate from registry synchronization.
