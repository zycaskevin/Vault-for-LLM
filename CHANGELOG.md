# Changelog

## [0.4.1] — 2026-05-17

### Changed
- Refresh package metadata for a post-cleanup PyPI release so the project description and long description match the public local-first Markdown + SQLite positioning without pre-A4 skill-marketplace wording.
- Modernize package license metadata to the PEP 639 SPDX `MIT` form with explicit `LICENSE` inclusion, removing deprecated setuptools license-table/classifier usage while preserving MIT semantics.
- Keep the release focused on metadata/version alignment; no README claim changes are required by `docs/readme_claim_matrix.md`.

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