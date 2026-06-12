# Changelog

## [0.5.0] — 2026-06-12

### Added
- Add deterministic Search QA baseline fixtures and metrics to measure retrieval quality and latency before retrieval changes.
- Add SQLite FTS5/BM25 keyword search with automatic fallback when FTS5 is unavailable or CJK matching needs the legacy LIKE path.
- Add semantic index plumbing with `semantic_vectors` rows for knowledge and claim-level citation-aware vectors.
- Add embedding provider metadata and fail-closed provider validation so production-like semantic paths require a real semantic provider.
- Add in-memory and persistent embedding caches keyed by provider identity, vector dimension, cache version, and text hash.
- Add `vault semantic rebuild`, `warm`, `smoke`, `cache-stats`, and `cache-prune` operator workflows.
- Add importable semantic lifecycle hooks plus `vault semantic startup` and bounded `daemon` commands for service integration.
- Add `docs/semantic_search.md`, README semantic workflow guidance in all README variants, and a README documented command smoke CI job.

### Changed
- Startup and daemon semantic workflows use the persistent embedding cache by default; pass `--no-persist-cache` for cold runs.
- The semantic daemon is bounded by default with `--repeat 1`; `--repeat 0` is reserved for supervisor-managed forever mode.
- Semantic test doubles are explicit: deterministic hash embeddings require `--allow-hash` and are documented as CI/local smoke only.

### Verification
- Full local test suite: `138 passed`.
- README documented command smoke: init/add/compile/search, Search QA, semantic smoke, and cache-stats commands pass in a clean temp project.
- Public-boundary gate and GitHub Release Readiness CI pass on `main`.

## [0.4.3] — 2026-05-24

### Added
- Add source-checkout repository hygiene tools for public release workflows:
  - `scripts/public_pr_gate.py` scans actual PR diffs for public-boundary risks, including path-only internal artifacts, renamed paths, deleted/context lines, local paths, runtime data, secret-looking assignments, and large unexpected diffs.
  - `scripts/artifact_audit.py` reports safe-delete generated caches, review-only runtime folders, and archive candidates without deleting files.
  - `scripts/artifact_cleanup.py` defaults to dry-run and requires `--execute --safe-only` before deleting reproducible cache artifacts.
- Add `docs/repo_governance.md` to document public/internal release boundaries, artifact hygiene, and whitelist staging.
- Add `scripts/README.md` with maintainer script usage, safe defaults, and optional remote-sync boundaries.
- Replace the default `templates/entity_rules.yaml` with a public-safe generic starter and add a neutral custom-domain example under `examples/`.
- Ignore generated `INDEX.md` alongside runtime reports.
- Remove tracked internal progress/audit/release-readiness notes from the public source tree and move the synthetic example knowledge note from tracked `raw/` into `examples/knowledge/`.
- Add an explicit public PR gate cleanup mode for PRs that remove already-tracked internal-only artifacts.
- Document that `vault-mcp` is a local stdio server without built-in network authentication or user-level access control.
- Add regression tests for safe cache cleanup, review-only build/dist handling, public PR gate path scanning, deleted private payloads, and clean public diffs.

## [0.4.2] — 2026-05-17

### Fixed
- Skip Git auto-commit attempts when `vault compile` runs outside a Git worktree.
- Suppress expected stderr from non-Git `git diff --cached` and `git diff --no-index` probes in first-user/non-Git smoke flows.
- Add regression coverage for compile hygiene in non-Git projects.

## [0.4.1] — 2026-05-17

### Changed
- Refresh package metadata for a post-cleanup PyPI release so the project description and long description match the public local-first Markdown + SQLite positioning without pre-A4 skill-marketplace wording.
- Modernize package license metadata to the PEP 639 SPDX `MIT` form with explicit `LICENSE` inclusion, removing deprecated setuptools license-table/classifier usage while preserving MIT semantics.
- Document citation-safe Document Map usage: search results are navigation hints; bounded `read_range` / `map read` output is the final citation source.
- Add public repository Search QA fixtures for English and Traditional Chinese retrieval smoke checks, with docs that label benchmarks as retrieval-only and source-checkout examples rather than wheel-installed data.
- Make MCP `vault_search` compact by default while preserving explicit `compact: false` for fuller preview output.

## [0.4.0] — 2026-04-22

### Added
- **Convergence Check** (`scripts/convergence_check.py`): KAL-style self-questioning loop — system judges if it "knows enough" to explain a topic, inspired by MindForge's Knowledge Acquisition Loop
- **Cross Validation** (`scripts/cross_validate.py`): Asymmetric LLM verification — extract with one model, verify with another (Gemma→Claude pattern) to catch hallucinations the extractor misses
- **Freshness Check** (`scripts/freshness_check.py`): Automated staleness detection + FSRS-style spaced repetition scheduling for knowledge entries
- **MCP Server** (`mcp.py`): Model Context Protocol server — let any chat AI query and inject into the knowledge base mid-conversation
- **Atomic Claims**: Extract claims at sub-chunk granularity with `source_span` binding for citation-level precision
- **test_new_features.py**: Full test suite for all new features (26 tests)

### Changed
- `db.py`: Added `convergence_score`, `cross_validated`, `freshness`, and `next_review` columns
- `compiler.py`: Now produces atomic claims with source_span citations
- `search.py`: Added graph expansion (2-hop recursive CTE walk) for related knowledge retrieval
- `cli.py`: New commands: `converge`, `cross-validate`, `freshness`

### Inspired By
- MindForge's KAL (Knowledge Acquisition Loop) — convergence check
- MindForge's cross-family LLM validation — cross_validate.py
- Karpathy's LLM Wiki three-layer architecture — already in our DNA, reinforced