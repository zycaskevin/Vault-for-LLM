# Vault-for-LLM Public Release Progress

Last updated: 2026-05-18 10:42 CST

## Current Status

Vault-for-LLM `0.4.2` has been published to PyPI and pushed to GitHub at `76be7a1`; tag `v0.4.2` points to the same commit. Do not re-upload `0.4.1` or `0.4.2` because PyPI versions are immutable.

GitHub Release notes for `v0.4.2` are published at <https://github.com/zycaskevin/Vault-for-LLM/releases/tag/v0.4.2>. GitHub Actions `Vault CI` passed for both `main` and `v0.4.2` on commit `76be7a1`.

Current post-release task: first Trusted Publishing release-hygiene slice is implemented locally: release parity checker + full release-readiness CI workflow. Next step is to push, observe GitHub Actions on `main`, then implement `publish.yml` and external PyPI/GitHub Environment configuration in a separate slice.

Latest planning/review artifacts:

- `.github/workflows/ci.yml` — release-readiness CI covering Python 3.10/3.11/3.12 tests, compileall, release parity, build/twine/wheel smoke, raw knowledge lint, and lightweight secret scan.
- `scripts/check_release_parity.py` and `tests/test_release_parity.py` — local/GitHub tag parity gate for version, changelog, and package metadata drift.
- `docs/release_hygiene_trusted_publishing_design.md` — post-0.4.2 repo hygiene and Trusted Publishing implementation design.
- `docs/agent_memory_qa_roadmap.md` — Agent Memory QA roadmap and Kanban execution graph inspired by agentmemory, while preserving Vault-for-LLM's local-first Markdown + SQLite positioning.
- `docs/p0_public_string_audit.md` — public-boundary audit and remediation notes.
- `docs/readme_claim_matrix.md` — README claim → proof → maturity matrix.
- `docs/document_map_citation_policy.md` — public Document Map citation policy and CLI/MCP demo for search → map show → read range.
- `docs/search_qa_benchmarking.md` and `benchmarks/search_qa/` — public-safe Search QA fixture docs and English / Traditional Chinese retrieval smoke fixtures.
- `docs/release_checklist_0_4_1.md` — historical no-side-effect release checklist used for the 0.4.1 publishing step.
- `docs/p1_release_readiness_report.md` — final local release-readiness report and command evidence.

Kanban board:

- `vault-for-llm-public-cleanup`

Current branch observed during this pass:

- `fix/cli-non-git-diff-hygiene`

## Current Decision

Vault-for-LLM should be positioned as:

> Local-first Markdown + SQLite memory QA for LLM agents.

The public project should not try to become a broad capture-first memory runtime. It should borrow useful patterns from adjacent tools such as agentmemory — onboarding, capture/import, retrieval fusion, privacy filtering, repository benchmark fixtures — but keep the core product small, inspectable, and open-source-user facing.

## Recommended Next Roadmap

### P1 — Stable local core verification / release hygiene

- `0.4.2` is published; do not re-upload immutable PyPI versions `0.4.1` or `0.4.2`.
- GitHub Release notes for `v0.4.2` exist and CI passed on both `main` and tag `v0.4.2`.
- First release-hygiene implementation slice is complete locally: `scripts/check_release_parity.py` plus `.github/workflows/ci.yml`.
- New full CI replaces the old lightweight workflow and covers Python 3.10/3.11/3.12 tests, compileall, build, twine check, wheel smoke, version parity, raw knowledge lint, and lightweight secret scan.
- Next release-hygiene priority: push these commits and observe GitHub Actions, then implement `publish.yml` with PyPI Trusted Publishing in a separate slice.
- License metadata warning remediation is complete: `project.license` now uses the SPDX `MIT` string, `project.license-files` includes `LICENSE`, and the deprecated license classifier has been removed.
- Keep checking README command examples against actual CLI parser behavior before each release.

### P2 — Document Map as differentiator

- Added `docs/document_map_citation_policy.md` with a neutral temp-project CLI demo and MCP agent loop for `search → map show → read_range`.
- Clarified citation policy in public docs: search results are navigation hints; bounded reads are final citation sources.
- Updated MCP `vault_search` to return compact payloads by default while preserving explicit `compact: false` for fuller preview output.
- Added/updated targeted tests for MCP compact-default search and explicit full-output opt-out.

### P3 — Search QA and retrieval roadmap

- Added public-safe Search QA repository fixtures under `benchmarks/search_qa/`:
  - `basic.en.json` covers English Document Map / `read_range`, citation-policy, and no-result retrieval cases.
  - `basic.zh-Hant.json` covers Traditional Chinese / CJK equivalents.
  - `README.md` documents fixture scope, schema, and limits.
- Added `docs/search_qa_benchmarking.md` with local demo DB setup, `vault search-qa run`, before/after comparison examples, metric definitions, CI guidance, and retrieval-only benchmark limits.
- Updated README and `docs/readme_claim_matrix.md` to link the benchmarking guide and source-checkout fixtures without claiming wheel inclusion or end-to-end agent task success.
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

## Verification Notes From P0/P1

Verified after Kanban execution:

- Full local test suite in current environment: `79 passed`.
- Clean `.[dev]` venv full test suite: `79 passed`.
- `git diff --check` passed.
- `python -m compileall -q vault scripts tests` passed.
- `python -m vault.cli doctor` passed with only optional `optimum[onnxruntime]` missing.
- `python -m vault.cli --help` and `python -m vault.mcp --help` passed.
- Public stale-string grep found no stale Hermes/dashboard/marketplace wording in README/docs/default code paths except historical verification notes.
- Graphify rebuild completed: 117 nodes, 5 edges, 114 communities.
- Build gate passed in a temporary venv: `python -m build` and `twine check dist/*` both passed for `0.4.1`.
- License metadata warning remediation is verified: no `project.license` TOML-table or deprecated license-classifier warnings remain in the build log.
- Clean wheel import from `/tmp` verified `vault.__version__ == "0.4.1"` and import path from `/tmp/vfl-p1-site/`.
- Clean `.[dev]` test-path bug fixed: `tests/test_e2e.py` now checks `onnxruntime` availability explicitly before enabling semantic embedding checks.

## Verification Notes From P2 Targeted Cleanup

- `python -m pytest -q tests/test_vault_mcp_map.py tests/test_search_map_integration.py tests/test_agent_behavior_policy.py` passed: `23 passed`.
- Full local test suite passed after P2 changes: `79 passed`.
- `python -m compileall -q vault scripts tests` passed.
- Temp-project CLI demo smoke using module-equivalent commands for `vault init`, `vault add`, `vault compile --no-embed`, `vault map build`, `vault search --keyword-only`, `vault map show`, and `vault map read` passed.
- `git diff --check` passed.
- Graphify rebuild completed after code changes: 117 nodes, 5 edges, 114 communities.

## Verification Notes From P3 Search QA Repository Fixtures

- `python -m pytest -q tests/test_search_quality_metrics.py` passed: `8 passed`.
- Full local test suite passed after P3 changes: `81 passed`.
- `python -m compileall -q vault scripts tests` passed.
- Module-equivalent CLI demo smoke created a temporary public-safe DB, ran `map build`, and produced English / Traditional Chinese Search QA snapshots with `top1_hits=2`, `topk_hits=2`, nonzero map/read guidance, and `citation_policy_violations=0`.
- `git diff --check` passed.
- Public repository fixtures validated locally against a temporary SQLite DB with English and Traditional Chinese entries; Document Map / `read_range` guidance metrics are nonzero and citation-policy violations remain zero.
- Public wording was corrected to say these are repository/source-checkout fixtures, not wheel-installed files.
- Graphify rebuild completed after code/test changes: 117 nodes, 5 edges, 114 communities.

## Verification Notes From Trusted Publishing Release-Hygiene Slice

- Task 1 release parity checker implemented and reviewed: `scripts/check_release_parity.py` validates release tag, `pyproject.toml`, `vault.__version__`, and top `CHANGELOG.md` version parity.
- Task 1 regression tests passed locally: `tests/test_release_parity.py` now covers matching tags, mismatch messages, strict changelog top entry, invalid tag early failure, Python 3.10 parser fallback, branch-env no-tag parity, and GitHub tag-env parity.
- Task 2 full CI implemented and reviewed: `.github/workflows/ci.yml` replaces `.github/workflows/auto-review.yml` with tests, compileall, build/twine/wheel smoke, release parity, raw knowledge lint, and lightweight secret scan.
- Final local verification passed after Task 2 fix: full pytest `93 passed`, compileall, parity no-tag/branch/tag smokes, build, twine check, wheel install smoke, workflow shape validation, lightweight secret scan, `git diff --check`, and Graphify rebuild.
- Important blocker found and fixed during review: GitHub branch pushes set `GITHUB_REF_NAME=main`; `check_release_parity.py` now only infers a tag from env when `GITHUB_REF_TYPE=tag` or `GITHUB_REF_NAME` is a full `refs/tags/...` ref.

## Historical Archive

### Public positioning and alpha roadmap — done

Earlier work clarified that Vault-for-LLM is a local-first agent memory layer with experimental quality tools. Public docs now describe the stable path as `vault init`, `vault add`, `vault compile`, `vault search`, and `vault-mcp`, while keeping advanced quality features alpha/experimental.

### Remove pre-Vault internal naming from public codebase — done

Earlier work renamed the public package/module/CLI/MCP surfaces to Vault branding and made new projects use `vault.db` by default. Continued public-boundary cleanup is still recommended as P0 because later review found more subtle internal/product-specific traces.
