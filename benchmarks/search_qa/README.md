# Search QA benchmark fixtures

This repository directory contains public-safe Search QA fixture files for local retrieval regression checks.

These are source-checkout fixtures. They live under the repository's top-level `benchmarks/` directory and are not installed by the PyPI wheel. If you installed Vault-for-LLM from PyPI, run `vault search-qa` against your own QA files, or clone/download the repository to use these examples.

- `basic.en.json` — English cases for Document Map / `read_range` guidance, citation-policy wording, and a no-result control.
- `basic.zh-Hant.json` — Traditional Chinese / CJK cases covering the same retrieval-focused behaviors.
- `semantic_hybrid.en.json` — Semantic/hybrid cases that check mode, claim, filtered-recall, cache-key, and no-result behavior against a matching semantic index.

These fixtures are intentionally small. They are meant to verify that `vault search-qa run` can load repository benchmark files and produce deterministic local snapshots against a matching demo or project database. They do **not** measure end-to-end agent task success, answer correctness, or tool-use planning.

## JSON shape

Each file uses the schema accepted by `vault.search_qa.load_search_qa_set`:

```json
{
  "version": 1,
  "description": "human-readable purpose",
  "cases": [
    {
      "id": "stable_case_id",
      "query": "retrieval query",
      "expected_titles": ["Exact expected title"],
  "expected_title_substrings": ["optional", "all required substrings"],
  "expected_ids": ["optional stable knowledge IDs"],
  "expected_claim_substrings": ["optional", "all required best_claim substrings"],
  "expected_best_span": ["optional Lx-Ly span"],
  "expected_node_uid": ["optional document-map node uid"],
  "allowed_result_modes": ["optional exact result modes"],
  "require_mode_prefix": "optional mode prefix",
  "expected_no_results": false
    }
  ]
}
```

Use `expected_titles` or `expected_title_substrings` for portable fixtures. Use `expected_ids` only when the target database has stable IDs.
Use `expected_no_results: true` for hard-negative cases where the correct behavior is to return no matches; Search QA will count false positives separately.

## Scope and limits

Search QA tracks retrieval regression metrics such as top-1 hits, hit@k, mean reciprocal rank, Document Map guidance, `read_range` guidance, citation-policy violations, claim/span/node hits, and result-mode violations. It is best used before changing keyword ranking, FTS/BM25, semantic/vector retrieval, or rank fusion.
