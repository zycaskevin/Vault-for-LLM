# Vault-for-LLM Public Release Progress

Last updated: 2026-05-17 10:34 CST

## Current Status

P0 public boundary cleanup is completed through Kanban and locally verified.

Latest planning/review artifacts:

- `docs/agent_memory_qa_roadmap.md` — Agent Memory QA roadmap and Kanban execution graph inspired by agentmemory, while preserving Vault-for-LLM's local-first Markdown + SQLite positioning.
- `docs/p0_public_string_audit.md` — public-boundary audit and remediation notes.
- `docs/readme_claim_matrix.md` — README claim → proof → maturity matrix.

Kanban board:

- `vault-for-llm-public-cleanup`

Current branch observed during this pass:

- `fix/vault-internal-rename`

## Current Decision

Vault-for-LLM should be positioned as:

> Local-first Markdown + SQLite memory QA for LLM agents.

The public project should not try to become a broad capture-first memory runtime. It should borrow useful patterns from adjacent tools such as agentmemory — onboarding, capture/import, retrieval fusion, privacy filtering, benchmark packaging — but keep the core product small, inspectable, and open-source-user facing.

## Recommended Next Roadmap

### P1 — Stable local core verification / release hygiene

- Decide whether to publish the prepared `0.4.1` package release.
- If publishing, run the PyPI release gate from `open-source-repo-operations`: tag exact commit, upload artifacts, verify fresh PyPI install, then rotate/restrict credentials.
- Address build warnings before 2027 deadline: migrate `project.license` to SPDX string and remove deprecated license classifier.
- Keep checking README command examples against actual CLI parser behavior before each release.

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
- Treat `vault skill` as an experimental local registry; do not market it as a hosted or mature marketplace until safety-reviewed.
- Do not include private/internal paths, admin surfaces, or deployment details in public-facing docs.

## Verification Notes From P0

Verified after Kanban execution:

- Full local test suite: `79 passed`.
- `git diff --check` passed.
- `python -m compileall -q vault scripts tests` passed.
- `python -m vault.cli doctor` passed with only optional `optimum[onnxruntime]` missing.
- `python -m vault.cli --help` and `python -m vault.mcp --help` passed.
- Public stale-string grep found no stale Hermes/dashboard/marketplace wording in README/docs/default code paths.
- Graphify rebuild completed: 117 nodes, 5 edges, 114 communities.
- Build gate passed in a temporary venv: `python -m build` and `twine check dist/*` both passed for `0.4.1`; setuptools emitted deprecation warnings for legacy license metadata.
- Clean wheel import from `/tmp` verified `vault.__version__ == "0.4.1"` from site-packages.

## Historical Archive

### Public positioning and alpha roadmap — done

Earlier work clarified that Vault-for-LLM is a local-first agent memory layer with experimental quality tools. Public docs now describe the stable path as `vault init`, `vault add`, `vault compile`, `vault search`, and `vault-mcp`, while keeping advanced quality features alpha/experimental.

### Remove pre-Vault internal naming from public codebase — done

Earlier work renamed the public package/module/CLI/MCP surfaces to Vault branding and made new projects use `vault.db` by default. Continued public-boundary cleanup is still recommended as P0 because later review found more subtle internal/product-specific traces.
