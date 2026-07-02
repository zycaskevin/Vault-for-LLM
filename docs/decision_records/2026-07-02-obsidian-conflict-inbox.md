# Obsidian Conflict Inbox

Date: 2026-07-02

## Decision

Vault can write an Obsidian conflict review note during import:

```bash
vault import obsidian --vault /path/to/ObsidianVault --conflict-inbox
```

When both the Obsidian source note and the imported Vault raw copy changed
since the last import, Vault still does not overwrite either side. If
`--conflict-inbox` is enabled, Vault writes a generated review note to:

```text
00-Vault-Knowledge/_Inbox/Obsidian Import Conflicts.md
```

The note lists the source path, Vault raw path, conflict reason, and compact
hashes. It deliberately does not include the conflicting note bodies.

## Why

Obsidian should be usable as the human-facing Vault console. A user should not
need to read CLI output to know that a note requires review, especially when
watch mode is running in the background.

The conflict inbox keeps the workflow human-friendly while preserving the
current safety model:

- no automatic conflict resolution,
- no raw conflicting content in generated notes,
- no writes outside `00-Vault-Knowledge/`,
- no import of generated review notes back into Vault.

## Follow-Up

- Add a guided conflict resolution UI for accepting Obsidian, accepting Vault
  raw, or keeping both.
- Add a full two-way mirror mode only after conflict resolution is explicit.
- Show the same conflict queue in the GUI dashboard.
