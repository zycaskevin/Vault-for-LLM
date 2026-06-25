# Search Rerank Module Split

Date: 2026-06-25

Status: Accepted

## Context

`vault/search.py` owns the end-to-end retrieval path: keyword search, semantic
search, hybrid fusion, graph expansion, access filtering, bounded evidence, and
result shaping. The reranking logic is important, but it is a distinct concern:
it adjusts the order of already-retrieved candidates using local scoring signals
or an optional cross-encoder model.

Keeping rerankers inside the main search module made future ranking and memory
weight changes harder to review. This matters because Vault-for-LLM is moving
toward a memory loop where usage, citation, freshness, and governance signals
can improve recall without making the retrieval core harder to reason about.

## Decision

Move reranking and rank-signal helpers into `vault.search_rerank`.

The new module owns:

- `LightweightReranker`
- `CrossEncoderReranker`
- `calc_freshness`
- `calc_graph_depth`
- `calc_usage_boost`
- `_is_active_memory`

`vault.search` still imports and re-exports those names so existing callers can
continue using `from vault.search import LightweightReranker`.

## Safety Boundaries

- Search result filtering is unchanged.
- Active archived-memory filtering is unchanged.
- Rerank score fields are unchanged.
- Cross-encoder loading behavior is unchanged and remains optional.
- No remote model or hosted service is introduced by this split.

## Consequences

- `vault/search.py` is smaller and easier to review.
- Ranking changes can be tested in a focused module before they affect the full
  retrieval pipeline.
- Existing tests that import reranker helpers from `vault.search` remain valid.

