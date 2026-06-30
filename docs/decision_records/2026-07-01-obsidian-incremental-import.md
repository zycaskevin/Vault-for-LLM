# Obsidian Incremental Import

## Context

Vault-for-LLM should let users keep writing in Obsidian while agents read from a
structured Vault database. A one-time import is not enough: notes change, new
notes appear, and old notes may be moved or deleted.

## Decision

Obsidian import is incremental and manifest-backed.

Vault writes `.vault/obsidian-import-manifest.json` with source note paths,
source hashes, raw-copy paths, and last-seen state. On each import:

- new notes create new raw copies,
- changed notes update existing raw copies,
- unchanged notes are skipped,
- source notes that disappeared are reported as missing.

Missing source notes are not deleted from `raw/` by default. Deletion requires
explicit `--prune-missing`.

## Consequences

- Scheduled Obsidian sync can safely run without rewriting unchanged notes.
- Agents can detect moved/deleted notes without silent data loss.
- Users keep final control over destructive cleanup.
- Future GUI panels can show missing-note counts from the import result or
  manifest before offering cleanup actions.
