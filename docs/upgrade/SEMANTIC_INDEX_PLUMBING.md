# Semantic index plumbing

PR C adds public-safe semantic-index plumbing without requiring a real embedding service.

## Scope

This stage intentionally builds the data model and deterministic test path before wiring production semantic providers into retrieval ranking.

It adds:

- `semantic_vectors` SQLite table for node and claim vectors.
- deterministic hash embedding provider for tests and examples.
- rebuild helper that derives Document Map nodes and AAAK claims, then writes vectors.
- stale-vector cleanup on rebuild by provider/dimension/knowledge row.
- semantic index search helper that returns stored vector rows with line-range citation metadata.

## Why hash embeddings?

Hash embeddings are not true semantic embeddings. They are a stable public-safe test double so the index lifecycle can be tested in a clean checkout without external model downloads, Ollama, API keys, or private infrastructure.

The provider exposes:

- `provider_id = "hash-deterministic-v1"`
- `dim`
- `is_semantic = False`

Later provider-gating PRs can fail closed when a command requires true semantic embeddings.

## Data model

`semantic_vectors` stores vectors as JSON so base installs do not require sqlite-vec:

- `knowledge_id`
- `vector_kind`: `node` or `claim`
- `item_uid`: `node_uid` or `claim_uid`
- `provider_id`
- `dimension`
- `vector`
- `source_text`
- `content_hash`
- `line_start`, `line_end`

The unique key is:

```text
provider_id + dimension + vector_kind + knowledge_id + item_uid
```

## Rebuild behavior

`rebuild_semantic_index(db, provider, knowledge_id=None)`:

1. Ensures Document Map rows exist by rebuilding nodes/claims for each selected knowledge row.
2. Deletes existing semantic vectors for that knowledge row/provider/dimension.
3. Inserts fresh node vectors from path/heading/summary text.
4. Inserts fresh claim vectors from claim text.
5. Commits once after the rebuild.

This makes stale vector cleanup deterministic and easy to test.

## Retrieval helper

`search_semantic_index(db, query, provider, vector_kind="claim")` computes a deterministic query vector, scores stored vectors with a dot product, and returns rows enriched with:

- knowledge title/category/layer/trust
- heading/path when the vector maps to a node
- `line_start`, `line_end`
- `citation`, for example `#1 Semantic Index Guide L4-L4`
- `_mode = "semantic_hash"`

This is plumbing only. Public ranking integration remains a later PR.

## Verification

```bash
ruff check vault/db.py vault/semantic.py tests/test_semantic_index.py
pytest -q tests/test_semantic_index.py
```

Expected coverage:

- deterministic provider stability
- node and claim vector creation
- stale vector cleanup after knowledge update
- citation metadata preservation in semantic index search
