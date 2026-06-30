# Memory Intelligence Loop

Date: 2026-06-30

## Decision

Vault should deepen the existing automatic, temporal, and reflective memory
features without becoming a heavy agent runtime.

The next memory loop is:

1. Pipeline extracts candidate memories from transcripts.
2. Candidate scoring explains extraction quality, novelty, and whether the
   content looks like an update to an existing memory.
3. Search ranks current temporal facts ahead of past facts while preserving
   historical recall for audit.
4. Reflection proposes consolidation candidates for similar active memories.
5. Humans or explicitly authorized policies decide what becomes active memory.

## Boundaries

- Pipeline remains candidate-first.
- Reflection does not rewrite, delete, or promote active knowledge.
- Temporal ranking is a relevance hint, not an access-control rule.
- Past facts remain searchable unless callers explicitly exclude them.
- Future facts stay visible when requested, but receive lower truth priority.

## Rationale

The first automatic memory layer proved the plumbing: transcript discovery,
candidate creation, temporal fields, and report-first reflection. The next
useful step is judgment: which candidate is new, which candidate updates an
existing memory, which fact is current, and which old memories should be
consolidated.

This keeps Vault on its own path. It borrows the useful part of Letta-style
autonomous memory management, but preserves Vault's local-first, inspectable,
reviewable model.

## Implementation Shape

- Session capture adds `extraction_score`, `novelty_score`,
  `recommended_action`, and `merge_target` to preview and write results.
- Search applies a small deterministic temporal score adjustment after normal
  relevance ranking.
- Reflection clusters similar memories and writes
  `consolidation_suggestion` candidates only when `--write-candidates` is
  explicitly used.

## Non-Goals

- No LLM-only memory extraction requirement.
- No automatic deletion.
- No automatic active-memory rewrite.
- No hidden promotion.
- No change to L0-L3 semantics or Task Ledger boundaries.
