# Obsidian Conflict Resolver

Date: 2026-07-02

## Decision

Vault supports explicit Obsidian import conflict resolution:

```bash
vault import obsidian \
  --vault /path/to/ObsidianVault \
  --resolve-conflict "Projects/Decision.md" \
  --resolution accept-obsidian
```

Supported choices:

- `accept-obsidian`: the Obsidian source note updates Vault's imported raw copy.
- `accept-vault`: Vault's imported raw body updates the Obsidian source note.
- `keep-both`: Obsidian updates Vault, and Vault's previous raw body is saved
  as a sibling conflict copy in Obsidian.

## Safety Boundary

Conflict resolution is explicit. Watch mode and normal import must not silently
resolve two-sided edits.

The resolver checks that the Obsidian source note and Vault raw copy still match
the hashes recorded when the conflict was detected. If either side changed
again, Vault asks the operator to re-run import before resolving.

`accept-obsidian` and `keep-both` still run the privacy gate before writing into
Vault raw notes unless the operator explicitly uses `--allow-private`.

## Why

Obsidian is becoming the human-facing Vault interface. A normal user should be
able to handle conflicts as three clear choices instead of reading manifest
hashes:

1. Use my Obsidian edit.
2. Use the Vault version.
3. Keep both.

The CLI names stay precise for agents, while GUI and Obsidian inbox surfaces can
present the same choices as separate buttons.

## Follow-Up

- Expose the same resolver in the local GUI dashboard.
- Add MCP resolver tooling behind the maintenance profile.
- Build a full two-way mirror only on top of this explicit conflict contract.
