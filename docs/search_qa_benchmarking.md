# Search QA benchmarking

Search QA is a local retrieval regression tool. It runs fixed query sets against a SQLite `vault.db`, records deterministic snapshots, and compares before/after metric deltas.

It is **not** an end-to-end agent benchmark. A passing Search QA run means the configured retrieval path found expected notes under fixed queries; it does not prove that an agent will choose the right tool, read enough context, or complete a real task.

## Repository fixture files

Public-safe sample fixtures live in the repository source checkout:

- `benchmarks/search_qa/basic.en.json`
- `benchmarks/search_qa/basic.zh-Hant.json`

They include English and Traditional Chinese / CJK cases for:

- Document Map and `read_range` guidance.
- Citation-policy boundaries: search results are navigation hints; bounded reads are citation evidence.
- No-result controls / hard negatives.

The fixtures are intentionally small so CI and local development can run them without cloud services or private data.

These are source-checkout fixtures under the repository's top-level `benchmarks/` directory. They are not installed by the PyPI wheel. If you installed Vault-for-LLM from PyPI, run `vault search-qa` against your own QA files, or clone/download the repository to use these examples.

## Create a small local demo DB

You can run Search QA against any existing Vault database. For a public-safe demo database that matches the repository fixtures, create a temporary project and add neutral notes:

```bash
DEMO_DIR=/tmp/vault-searchqa-demo
rm -rf "$DEMO_DIR"
mkdir -p "$DEMO_DIR"
cd "$DEMO_DIR"

vault init
vault add "Tool-gated Reading Guide" --content "# Tool-gated Reading Guide
Intro
## Tool-gated Reading
Tool-gated reading keeps agents from reading whole documents.
It requires map navigation before read_range evidence."

vault add "Citation Policy Boundary" --content "# Citation Policy Boundary
Search citations are navigation hints only, not final answer support.
Final citations require read_range output."

vault add "文件地圖閱讀指南" --content "# 文件地圖閱讀指南
簡介
## 文件地圖與讀取範圍
文件地圖幫助代理先查看章節，再使用讀取範圍取得證據。
此流程避免一次讀完整份文件。"

vault add "引用政策邊界" --content "# 引用政策邊界
搜尋引用只是導航提示，不是最終引用。
最終引用需要來自讀取範圍的輸出。"

vault map build
```

Or use an existing project database by running from that project directory, or by passing `--db-path /path/to/vault.db`.

## Run a deterministic Search QA snapshot

From a repository source checkout root, run English and CJK smoke snapshots against the demo DB or your own `vault.db`:

```bash
vault search-qa run \
  --db-path /tmp/vault-searchqa-demo/vault.db \
  --qa-file benchmarks/search_qa/basic.en.json \
  --mode keyword \
  --min-score 0.34 \
  --output /tmp/vault-searchqa.en.json

vault search-qa run \
  --db-path /tmp/vault-searchqa-demo/vault.db \
  --qa-file benchmarks/search_qa/basic.zh-Hant.json \
  --mode keyword \
  --min-score 0.34 \
  --output /tmp/vault-searchqa.zh-Hant.json
```

If you are already inside the project whose `vault.db` you want to test, `--db-path` is optional. The `--qa-file` path below still assumes you are running from a repository source checkout; otherwise pass a path to your own QA file:

```bash
vault search-qa run \
  --qa-file benchmarks/search_qa/basic.en.json \
  --mode keyword \
  --min-score 0.34 \
  --output /tmp/vault-searchqa.en.json
```

## Compare before and after retrieval changes

Save a baseline before changing ranking, FTS/BM25, vector search, CJK tokenization, or RRF fusion:

```bash
vault search-qa run \
  --qa-file benchmarks/search_qa/basic.en.json \
  --mode keyword \
  --output /tmp/searchqa-before.json
```

After the retrieval change, run the same fixture, mode, database, and limit:

```bash
vault search-qa run \
  --qa-file benchmarks/search_qa/basic.en.json \
  --mode keyword \
  --output /tmp/searchqa-after.json

vault search-qa compare \
  --before /tmp/searchqa-before.json \
  --after /tmp/searchqa-after.json \
  --output /tmp/searchqa-compare.json
```

## Keyword vs semantic/hybrid QA

Keyword QA is the stable base path and does not require embeddings, network
access, or external services. Semantic and hybrid QA require a stored semantic
index built with the same provider/model/dimension and vector kind that the QA
run uses.

For deterministic CI plumbing checks, use the hash provider explicitly:

```bash
vault semantic rebuild --allow-hash --hash-dim 8

vault search-qa run \
  --qa-file benchmarks/search_qa/semantic_hybrid.en.json \
  --mode hybrid \
  --allow-hash \
  --hash-dim 8 \
  --semantic-vector-kind claim \
  --output /tmp/searchqa-hybrid.json
```

Hash vectors are test doubles. They prove command wiring, snapshot shape, and
stored-index fusion, but they do not measure real semantic retrieval quality.

Example comparison output:

```text
Search QA comparison
- total_cases: 3 -> 3 (0)
- cases_with_results: 2 -> 2 (0)
- top1_hits: 2 -> 1 (-1)
- topk_hits: 2 -> 2 (0)
- mean_reciprocal_rank: 0.6666666666666666 -> 0.5 (-0.166666666667)
- map_guidance_rate: 0.3333333333333333 -> 0.3333333333333333 (0.0)
- read_range_guidance_rate: 0.3333333333333333 -> 0.3333333333333333 (0.0)
- citation_policy_violations: 0 -> 0 (0)
```

Interpret positive deltas for hit counts and MRR as likely retrieval improvements. Interpret positive deltas for `citation_policy_violations` as regressions. Investigate any drop in `map_guidance_rate` or `read_range_guidance_rate` when changing Document Map enrichment or result payloads.

## Metrics

Search QA snapshots include these aggregate metrics:

- `total_cases` — number of cases loaded from the fixture.
- `cases_with_results` — cases returning at least one search result.
- `top1_hits` — cases where the first result matches `expected_ids`, `expected_titles`, or all `expected_title_substrings`.
- `topk_hits` — cases where any returned result within the configured limit matches expectations.
- `no_result_cases` — hard-negative cases marked with `expected_no_results: true`.
- `no_result_false_positives` — hard-negative cases that returned at least one result.
- `no_result_precision` — share of hard-negative cases that correctly returned no results.
- `mean_reciprocal_rank` — average reciprocal rank of the first expected result, with `0.0` for misses.
- `map_guidance_rate` — fraction of cases whose results include `vault_map_show` guidance.
- `read_range_guidance_rate` — fraction of cases whose results include `vault_read_range` guidance.
- `citation_policy_violations` — count of search results that are incorrectly labeled as final citations, or that expose search-result citations without `read_range` guidance.
- `mean_latency_ms` — mean per-query retrieval latency in milliseconds for this run.
- `p95_latency_ms` — nearest-rank p95 per-query retrieval latency in milliseconds.
- `min_latency_ms` / `max_latency_ms` — minimum and maximum per-query retrieval latency in milliseconds.

Latency metrics are intended for same-machine before/after comparisons. Treat them as directional baseline numbers, not absolute performance claims across machines or CI runners.

## CI usage

A local-only CI smoke test should use keyword mode and a temporary SQLite database. It should not require embeddings, Supabase, network access, private notes, or agent runtimes.

Recommended gate before retrieval work, after creating a temporary demo DB or pointing at a project-local `vault.db`:

```bash
python -m pytest -q tests/test_search_quality_metrics.py
vault search-qa run \
  --db-path /tmp/vault-searchqa-demo/vault.db \
  --qa-file benchmarks/search_qa/basic.en.json \
  --mode keyword \
  --output /tmp/vault-searchqa.json
```

Use Search QA before changing ranking, keyword matching, FTS/BM25, vector retrieval, CJK tokenization, or RRF. Keep fixture claims retrieval-focused and label their limits clearly in public docs.
