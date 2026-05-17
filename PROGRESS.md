# Vault-for-LLM Public Release Progress

Last updated: 2026-05-17 09:30 CST

## Current Status

P0 public boundary cleanup is approved to start via Kanban.

The latest planning artifact is:

- `docs/agent_memory_qa_roadmap.md` — Agent Memory QA roadmap and Kanban execution graph inspired by agentmemory, while preserving Vault-for-LLM's local-first Markdown + SQLite positioning.

Kanban board:

- `vault-for-llm-public-cleanup`

Current branch observed during this planning pass:

- `fix/vault-internal-rename`

## Current Decision

Vault-for-LLM should be positioned as:

> Local-first Markdown + SQLite memory QA for LLM agents.

The public project should not try to become a broad capture-first memory runtime. It should borrow useful patterns from adjacent tools such as agentmemory — onboarding, capture/import, retrieval fusion, privacy filtering, benchmark packaging — but keep the core product small, inspectable, and open-source-user facing.

## Recommended Next Roadmap

### P0 — Public boundary cleanup

- Run a tracked-file audit for private/internal names and deployment assumptions.
- Neutralize or remove public-unsuitable raw knowledge examples.
- Split optional public Supabase sync from any private dashboard health assumptions.
- Decide whether `vault skill` remains hidden, is downgraded to experimental, or is product-neutralized.
- Build a README claim matrix: claim → proof → maturity.

### P1 — Stable local core verification

- Verify fresh install in a clean environment.
- Ensure `vault doctor`, `vault init`, `vault add`, `vault compile`, and `vault search` work without cloud/model dependencies.
- Guard optional dependency imports so full test collection does not fail when optional packages are absent.
- Verify README command examples against actual CLI parser behavior.

### P2 — Document Map as differentiator

- Publish a neutral demo for `search → map show → read_range`.
- Clarify citation policy: search results are navigation hints; bounded reads are final citation sources.
- Add or verify tests for citation-safe bounded reading.

### P3 — Search QA and retrieval roadmap

- Add public-safe Search QA fixtures, including CJK cases.
- Use before/after snapshots before changing ranking.
- Plan FTS/BM25 + vector + graph + RRF only after regression gates exist.

### P4 — Review-gated capture/import

- Design `vault capture import` / `vault import-session` as opt-in, local-only, review-gated workflows.
- Keep captured data out of normal search until promoted.
- Add privacy scan before promotion, compile, and optional sync.

### P5 — First-hour UX

- Improve `vault doctor`.
- Add `vault demo`.
- Add `vault connect --print` with no default side effects.

## Current Boundaries / Non-goals

- Do not make Supabase required for core usage.
- Do not present advanced commands as production-ready platform features.
- Do not expand the default MCP tool surface without a strong agent-in-conversation need.
- Do not enable silent auto-capture or uncontrolled auto-write.
- Do not market `vault skill` as a mature marketplace until it is product-neutral and safety-reviewed.
- Do not include private/internal paths, dashboards, or deployment details in public-facing docs.

## Verification Notes From Planning Review

Observed during the roadmap review:

- Existing README direction is closer now, but should still be tightened around maturity and proof.
- Existing docs already mention Document Map and optimization principles.
- Reviewers flagged that optional Supabase dependency handling may break full pytest collection if not guarded.
- Reviewers also flagged possible internal/private vocabulary and product-specific skill defaults that should be handled in P0.

## Historical Archive

### Public positioning and alpha roadmap — done

Earlier work clarified that Vault-for-LLM is a local-first agent memory layer with experimental quality tools. Public docs now describe the stable path as `vault init`, `vault add`, `vault compile`, `vault search`, and `vault-mcp`, while keeping advanced quality features alpha/experimental.

### Remove pre-Vault internal naming from public codebase — done

Earlier work renamed the public package/module/CLI/MCP surfaces to Vault branding and made new projects use `vault.db` by default. Continued public-boundary cleanup is still recommended as P0 because later review found more subtle internal/product-specific traces.
