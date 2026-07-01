# Memory Migration Hub

Date: 2026-07-01

## Decision

Vault should accept memory from other tools and chat exports through a generic
candidate-first migration path.

External memory may come from Chatbox, ChatGPT, Claude, Codex, Hermes,
OpenClaw, Obsidian-adjacent Markdown folders, JSON/CSV archives, transcript
files, or OKF bundles. These sources should not be trusted as active project
knowledge on arrival.

## Boundary

The migration hub writes to `memory_candidates`, not active `knowledge`.

Preview is the default behavior. A caller must explicitly request candidate
writes, and promotion still goes through the normal privacy, duplicate,
metadata, quality, and human/automation review gates.

## Rationale

Vault's long-term role is a user-owned memory layer that different agents,
devices, and tools can share. If users already have memory elsewhere, Vault
needs a safe merge path. Direct import into active memory would blur source
quality, leak private content, and make the vault feel like another black box.

Candidate-first migration keeps the useful part of interoperability while
preserving governance:

- source systems stay visible in `source` / `source_ref`
- content is scanned before review
- duplicate warnings are surfaced before promotion
- GUI users can preview before adding candidates
- imported content can be rejected or blocked without touching active memory

## Initial Implementation

- `vault import memory --source ...` previews Markdown, JSON, CSV, transcript,
  and OKF inputs.
- `vault import memory --write-candidates` writes review candidates only.
- The local GUI exposes a small Memory Migration panel with preview and import
  actions.
- OKF import remains supported directly and through the migration hub.

## Non-goals

- No direct active-memory import from third-party exports.
- No automatic trust of another memory product's ranking or scoring.
- No multi-master merge of active knowledge. Cross-host writes still enter the
  candidate / conflict workflow first.
