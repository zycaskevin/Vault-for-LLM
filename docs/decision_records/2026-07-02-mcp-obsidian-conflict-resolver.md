# MCP Obsidian Conflict Resolver

Date: 2026-07-02

## Decision

Vault exposes the explicit Obsidian conflict resolver through MCP as a
maintenance-profile tool:

```text
vault_obsidian_resolve_conflict
```

The tool uses the same resolver contract as the CLI:

- `accept-obsidian`
- `accept-vault`
- `keep-both`

It is not included in the `core` MCP profile. Agents must opt into the
maintenance profile or an explicit allowlist before they can resolve conflicts.

## Why

Agent-facing conflict resolution should use the same safety contract as the CLI
instead of each agent inventing its own merge behavior. This keeps Obsidian
watch/import safe and makes future GUI controls a thin wrapper around the same
resolver semantics.

## Safety

- Normal import and watch mode still do not silently resolve two-sided edits.
- The MCP tool verifies the recorded conflict hashes through
  `resolve_obsidian_conflict()`.
- The tool can refresh the generated Obsidian conflict inbox after resolution.
- The tool returns a next action telling agents to re-run import/compile after
  resolving, so manifest and compiled knowledge stay fresh.

## Follow-Up

- Add GUI buttons that call the same resolver actions.
- Add an MCP/GUI conflict list view so agents and users can inspect unresolved
  Obsidian conflicts before selecting a resolution.
