# Open-source baseline

This document records the public repository baseline before retrieval-ranking changes. It is intentionally public-safe: no private notes, local absolute paths, private chat identifiers, runtime databases, or internal handoff artifacts are included.

## Repository metadata

- Repository: `zycaskevin/Vault-for-LLM`
- URL: `https://github.com/zycaskevin/Vault-for-LLM`
- Visibility: `PUBLIC`
- Default branch: `main`
- Baseline commit: `62706c49871e437fc79a63908655de7df3dfdfed`
- Package name: `vault-for-llm`
- CLI entry points: `vault`, `vault-mcp`
- Python requirement: `>=3.10`

Metadata was verified with:

```bash
gh repo view zycaskevin/Vault-for-LLM --json nameWithOwner,visibility,isPrivate,defaultBranchRef,url
```

## Current public CLI/API surface checked for this baseline

The source package exposes the `vault` Python package and these console scripts from `pyproject.toml`:

- `vault = "vault.cli:main"`
- `vault-mcp = "vault.mcp:main"`

The current `vault --help` command lists these public subcommands:

```text
init, add, compile, search, list, lint, doctor, stats, install-embedding,
import, export, config, map, skill, graph, converge, cross-validate,
freshness, dedup, search-qa
```

Search QA is already exposed as:

```bash
vault search-qa run --qa-file benchmarks/search_qa/basic.en.json --mode keyword --output /tmp/searchqa.json
vault search-qa compare --before /tmp/searchqa-before.json --after /tmp/searchqa-after.json
```

## Current search architecture

- `vault.search.VaultSearch` supports keyword, vector, and hybrid modes.
- `vault.search_qa.evaluate_search_qa` runs deterministic local Search QA snapshots using keyword mode without external embedding services.
- Search-result citations are treated as navigation hints; final answer evidence is expected to come from bounded `vault map read` / MCP `vault_read_range` output.
- Repository Search QA fixtures live under `benchmarks/search_qa/` and are source-checkout fixtures, not wheel-installed package data.

## Baseline Search QA fixture scope

Public-safe fixtures currently cover:

- English retrieval smoke cases: `benchmarks/search_qa/basic.en.json`
- Traditional Chinese / CJK retrieval smoke cases: `benchmarks/search_qa/basic.zh-Hant.json`
- Expected-hit cases for Document Map / `read_range` guidance.
- Expected-hit cases for citation-policy boundary retrieval.
- Hard-negative no-result controls.

## Baseline metrics captured by PR A

Search QA snapshots record quality metrics:

- `top1_hits`
- `topk_hits`
- `mean_reciprocal_rank`
- `map_guidance_rate`
- `read_range_guidance_rate`
- `citation_policy_violations`

PR A also adds latency metrics so later FTS5/BM25 and semantic-search PRs can compare speed on the same machine:

- `mean_latency_ms`
- `p95_latency_ms`
- `min_latency_ms`
- `max_latency_ms`

Latency numbers are same-machine directional metrics only. They should not be compared across unrelated developer laptops, CI runners, or hardware classes.

## Baseline test command

Current local baseline after adding latency measurement:

```bash
pytest -q tests/test_search_quality_metrics.py
# 8 passed
```

Full-suite baseline before this PR branch started:

```bash
pytest -q
# 116 passed
```

## Public-boundary gate

The repository already contains a fail-closed public PR gate:

```bash
python scripts/public_pr_gate.py --base origin/main --head HEAD --target-visibility public
```

The gate scans the actual git diff for forbidden public-boundary content including local user paths, private runtime folders, secret-looking assignments, chat/user IDs, private-only files, runtime databases, and unexpectedly large diffs.

For this baseline document, local checkout paths and private environment details are intentionally omitted from committed content. Maintainers can record local worktree paths in private task logs if needed.
