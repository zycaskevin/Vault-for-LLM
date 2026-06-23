# Semantic Search Workflow

Vault-for-LLM works without embeddings. Keyword search is the stable default path, and semantic search is an optional alpha workflow for projects that configure a real embedding provider.

This guide consolidates the public semantic-search behavior added by the upgrade series:

- FTS5/BM25 keyword search with safe fallback.
- `semantic_vectors` storage for knowledge/claim-level vectors.
- Provider safeguards that separate real semantic providers from deterministic test doubles.
- Persistent embedding cache for cross-process startup and daemon workflows.
- Operator-facing CLI commands for rebuild, warm, smoke, cache maintenance, startup, and daemon runs.

## Safety model

Semantic workflows fail closed by default:

1. A production-like semantic rebuild/search requires a provider whose metadata says it is semantic.
2. The deterministic hash provider is a test double. It is blocked unless you explicitly pass `--allow-hash`.
3. Cache keys include provider identity and vector dimension so rows from different providers do not silently mix.
4. Startup and daemon workflows use the persistent cache by default. Disable it with `--no-persist-cache` when you want a cold run.
5. The daemon is bounded by default: `--repeat 1`. Use `--repeat 0` only under a process supervisor.

## Configure a provider

Keyword search needs no provider. For semantic workflows, install and configure a real provider first.

Local ONNX path:

```bash
pip install "vault-for-llm[semantic]"
vault install-embedding --model mix
```

Ollama path:

```bash
vault config set embedding.provider ollama
vault config set embedding.model nomic-embed-text
```

## Rebuild semantic vectors

```bash
vault semantic rebuild --persist-cache --pretty
```

Useful options:

- `--knowledge-id <id>` rebuilds one knowledge row.
- `--changed-only` rebuilds only rows whose semantic vectors are missing,
  stale, or out of sync with current Document Map node/claim hashes.
- `--limit <n>` bounds a changed-only maintenance run.
- `--db-path <path>` targets a specific SQLite DB.
- `--persist-cache` uses the durable `embedding_cache` table during the rebuild.

For daily or startup maintenance, prefer an incremental pass:

```bash
vault semantic rebuild --changed-only --persist-cache --pretty
```

## Search with the stored semantic index

After `vault semantic rebuild`, main search exposes the stored index as an operator-facing mode:

```bash
vault search "query text" --mode semantic
vault search "query text" --mode hybrid
```

- `--mode semantic` searches `semantic_vectors` and returns normal search results with content fields plus citation/span metadata when available.
- `--mode hybrid` fuses keyword results with stored semantic-index results. If no safe semantic provider/index is available, it falls back to legacy vector search or keyword search.
- `--mode auto` stays safe: keyword remains the default unless a real semantic provider and matching stored vectors are present.
- Deterministic hash vectors are test-only and require explicit `--allow-hash` (and the matching `--hash-dim` if non-default) for main semantic search.
- Use `--semantic-vector-kind claim|node` to choose claim-level or node-level stored vectors; `claim` is the default.

When sqlite-vec is available, `vault semantic rebuild` also refreshes a
provider/kind/dimension-scoped shadow index. Unfiltered semantic searches use
that sqlite-vec path first and fall back to the JSON scan path if the shadow
index is missing or stale. Searches with metadata filters (`--min-trust`,
`--layer`, or `--category`) intentionally keep the filter-aware scan path for
now, because sqlite-vec KNN queries cannot apply those filters before candidate
selection.

## Warm query embeddings

Use warm when you have a Search QA file and want to precompute query embeddings without writing semantic vector rows:

```bash
vault semantic warm \
  --qa-file benchmarks/search_qa/basic.en.json \
  --persist-cache \
  --pretty
```

## Run a semantic smoke check

Smoke combines rebuild, query warmup, and Search QA snapshot generation:

```bash
vault semantic smoke \
  --qa-file benchmarks/search_qa/basic.en.json \
  --mode keyword \
  --changed-only \
  --limit 10 \
  --persist-cache \
  --pretty
```

For CI command-shape checks only:

```bash
vault semantic smoke \
  --allow-hash \
  --qa-file benchmarks/search_qa/basic.en.json \
  --mode keyword \
  --pretty
```

`--allow-hash` is not semantic retrieval. It only proves the command flow, JSON shape, cache plumbing, and Search QA integration.

## Inspect and prune the persistent cache

```bash
vault semantic cache-stats --pretty
vault semantic cache-prune --older-than-days 30 --max-rows 5000 --pretty
```

Filter cache maintenance by provider or dimension when needed:

```bash
vault semantic cache-stats --provider-id "ollama:http://localhost:11434:nomic-embed-text" --pretty
vault semantic cache-prune --dimension 768 --max-rows 1000 --pretty
```

## Startup and daemon lifecycle

The lifecycle module is importable as `vault.semantic_lifecycle`, and the CLI exposes the same workflow.

One-shot startup hook:

```bash
vault semantic startup \
  --qa-file benchmarks/search_qa/basic.en.json \
  --rebuild \
  --changed-only \
  --smoke \
  --pretty
```

Bounded daemon run:

```bash
vault semantic daemon --repeat 1 --interval 60 --pretty
```

Forever mode is explicit and should be managed by a supervisor:

```bash
vault semantic daemon --repeat 0 --interval 300
```

## CI and release gate

The repository CI includes `scripts/readme_command_smoke.py`. It runs a clean local project smoke for README-documented command shapes:

- `vault --help`
- `vault semantic --help`
- `vault search-qa --help`
- `vault init`
- `vault add`
- `vault compile --no-embed`
- `vault search --keyword-only`
- `vault search-qa run`
- `vault semantic smoke --allow-hash`
- `vault semantic cache-stats`

Run it locally before changing README command examples:

```bash
python scripts/readme_command_smoke.py
```

## Related upgrade notes

- [`docs/upgrade/FTS5_BM25_SEARCH.md`](upgrade/FTS5_BM25_SEARCH.md)
- [`docs/upgrade/SEMANTIC_INDEX_PLUMBING.md`](upgrade/SEMANTIC_INDEX_PLUMBING.md)
- [`docs/upgrade/EMBEDDING_PROVIDER_INTERFACE.md`](upgrade/EMBEDDING_PROVIDER_INTERFACE.md)
- [`docs/upgrade/SEMANTIC_WORKFLOW_CLI.md`](upgrade/SEMANTIC_WORKFLOW_CLI.md)
- [`docs/upgrade/PERSISTENT_EMBEDDING_CACHE.md`](upgrade/PERSISTENT_EMBEDDING_CACHE.md)
- [`docs/upgrade/SEMANTIC_WARM_SERVICE.md`](upgrade/SEMANTIC_WARM_SERVICE.md)
