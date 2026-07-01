# Obsidian As The Human GUI

## Decision

Vault should keep its built-in GUI as a memory control center, while Obsidian
acts as the human-readable knowledge garden and review surface.

The two surfaces have different jobs:

- Obsidian is for writing notes, browsing linked knowledge, reviewing generated
  reports, and using a familiar graph-oriented workspace.
- Vault GUI is for system health, connected agents, permissions, sync status,
  conflicts, daily review queues, and automation safety.

Obsidian should not become a second uncontrolled source of truth. The safer
model is:

1. user-authored Obsidian notes are imported into Vault as governed source
   material;
2. Vault SQLite remains the agent retrieval, governance, permission, and audit
   core;
3. Vault-generated Obsidian notes live in a generated folder such as
   `00-Vault-Knowledge/`;
4. candidates, conflicts, and daily review reports can be exported back to
   Obsidian as human review inboxes.

## Rationale

Obsidian is already a strong human interface for Markdown, folders, tags, and
wikilinks. Rebuilding that inside Vault would make Vault heavier without
improving the agent memory layer.

Vault is strongest when it governs memory for agents: scope, sensitivity,
owners, allowed agents, source hashes, candidates, sync state, graph edges,
bounded reads, and audit-friendly retrieval. The built-in GUI should therefore
show what humans need to approve or understand, not compete with Obsidian as a
note editor.

## Implementation Direction

The first safe slice is:

- map Obsidian folders into Vault governance defaults, such as private personal
  folders or public publishing folders;
- parse Obsidian `[[wikilinks]]` into import metadata so graph search can later
  use human-authored links;
- export a generated review inbox with daily memory reports, candidate memory
  prompts, and sync status;
- include remote candidate sync conflict cards in the generated sync status,
  without exposing raw conflicting memory content;
- keep generated Vault export folders excluded from import to avoid feedback
  loops;
- add conflict/status surfaces before any automatic live bidirectional mirror.

The later slices are:

- an Obsidian review inbox for daily reports, candidate memories, and conflicts;
- graph integration where Obsidian links become Vault graph edges;
- a watch/scheduled sync mode once conflict handling is visible and safe;
- optional Obsidian plugin support after the file-based workflow is stable.

## Non-Goals

- Do not overwrite arbitrary user-authored Obsidian notes from agent output.
- Do not require Obsidian for normal Vault use.
- Do not turn Vault GUI into a full note editor or large graph editor.
- Do not enable automatic bidirectional conflict resolution before users can
  preview and audit conflicts.

## Consequences

This keeps Vault useful for users who do not use Obsidian, while giving Obsidian
users a natural human-facing workspace. It also preserves Vault's core promise:
agents can share one governed memory layer without scattering memory across
tool-specific silos.
