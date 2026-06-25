# Automatic, Temporal, and Reflective Memory

Date: 2026-06-25

## Decision

Vault-for-LLM should expose three first-class memory operations for long-running
agents:

1. **Automatic memory pipeline**: discover session transcripts, extract reusable
   lessons, run duplicate/privacy/quality gates, and optionally write candidate
   memories without requiring developers to call `vault remember` for every
   line.
2. **Temporal fact windows**: store `valid_from`, `valid_until`, and
   `supersedes_id` separately from `expires_at`, so old facts can remain
   auditable while current facts stay easy to find.
3. **Reflection cycle**: run Dream-style curation plus lifecycle automation as a
   report-first routine that can propose consolidation, archive stale memories,
   and cold-store expired-but-used facts without hard deletion.

## Product Boundary

These features make Vault more automatic, but not uncontrolled.

- Session capture still writes **candidate memory**, not active knowledge, unless
  a separately approved low-risk promotion policy is enabled.
- Reflection is report-first. It can write review candidates and apply
  reversible lifecycle actions only when the operator passes explicit flags.
- Temporal windows describe fact validity. They do not delete old facts.
- `expires_at` remains a recall/lifecycle control. `valid_until` means "this
  fact stopped being true."

## CLI Shape

The first implementation lives under one grouped command to avoid growing the
large CLI module:

```bash
vault memory pipeline --search-dir sessions --write-candidates
vault memory temporal status
vault memory temporal list --state past
vault memory reflection --write-candidates
```

## Safety Defaults

- Pipeline preview is the default.
- Candidate-first remains the default write path.
- Reflection does not hard delete.
- High-sensitivity and private data still depend on the existing privacy and
  governance gates.
- Future MCP/Supabase variants should reuse the same policy boundaries instead
  of introducing separate remote behavior.

## Why This Matters

The goal is not only to store more memory. The goal is to let agent memory become
more useful over time while keeping human review concentrated on the small set of
items that actually need judgment.
