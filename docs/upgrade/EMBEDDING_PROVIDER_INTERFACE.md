# Embedding provider interface and cache guard

PR D adds explicit provider metadata, fail-closed semantic gates, and an in-memory embedding cache for semantic-index plumbing.

## Provider contract

Semantic-index providers are expected to expose:

- `provider_id`: stable identifier used in cache keys and stored vector rows.
- `dim`: embedding dimension.
- `is_semantic`: `True` for real embedding providers, `False` for deterministic hash/test providers.
- `encode(texts)`: accepts a string or list of strings and returns vectors.

Existing public providers now expose provider identity:

- `ONNXEmbeddingProvider`: `onnx:<model-name>`
- `OllamaEmbeddingProvider`: `ollama:<base-url>:<model>`
- `SentenceTransformerProvider`: `sentence-transformers:<model-name>`
- `DeterministicHashEmbeddingProvider`: `hash-deterministic-v1`, `is_semantic=False`

## Fail-closed gate

Use `validate_embedding_provider(provider, require_semantic=True)` when a workflow must not silently use hash/test embeddings.

Default behavior remains friendly for tests and demos:

```python
validate_embedding_provider(provider, allow_hash=True)
```

Production-style behavior should fail closed:

```python
validate_embedding_provider(provider, require_semantic=True)
validate_embedding_provider(provider, allow_hash=False)
```

Both reject `DeterministicHashEmbeddingProvider` with a clear error message.

## In-memory cache

`CachedEmbeddingProvider` wraps any provider and caches vectors by:

```text
provider_id + dimension + cache_version + sha256(text)
```

This avoids duplicate embedding calls inside one process and prevents cache reuse across provider/model/dimension changes.

## Verification

```bash
ruff check vault/embed.py vault/semantic.py tests/test_semantic_index.py
pytest -q tests/test_semantic_index.py
```

Tests cover:

- hash provider rejected when semantic embeddings are required
- hash provider allowed when explicitly allowed for tests
- repeated text/query only calls the wrapped provider once
- provider id changes do not share cache entries
