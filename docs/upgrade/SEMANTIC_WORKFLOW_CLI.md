# Semantic Workflow CLI

`vault semantic` provides operator-facing workflows for semantic index maintenance and smoke checks.

## Safety defaults

The command fails closed by default:

- A real semantic embedding provider is required (`require_semantic=True`).
- Deterministic hash embeddings are rejected unless `--allow-hash` is explicitly supplied.
- The hash provider path is intended only for development, CI, and public deterministic tests.

Provider selection:

- `--allow-hash` uses `DeterministicHashEmbeddingProvider(dim=--hash-dim)`.
- Otherwise the CLI reads `embedding_provider` and `embedding_model` from `vault.db` config and creates a provider with `vault.embed.create_embedding_provider`.
- `warm` and `smoke` wrap the provider in `CachedEmbeddingProvider` so repeated QA queries are deduplicated in memory.

## Commands

### Rebuild semantic vectors

```bash
vault semantic rebuild
vault semantic rebuild --knowledge-id 123
```

Development/test only:

```bash
vault semantic rebuild --allow-hash --hash-dim 32
```

JSON stdout includes:

- `action`
- `provider_id`
- `is_semantic`
- `dimension`
- `knowledge_rows`
- `node_vectors`
- `claim_vectors`

### Warm QA query embeddings

```bash
vault semantic warm --qa-file benchmarks/search_qa/basic.en.json
```

`warm` loads the QA set, deduplicates `cases[].query`, and calls `provider.encode()` for the unique queries. It does **not** write rows to `semantic_vectors`.

JSON stdout includes:

- `action`
- `provider_id`
- `is_semantic`
- `dimension`
- `warmed_queries`
- `cache_size`

### Smoke workflow

```bash
vault semantic smoke --qa-file benchmarks/search_qa/basic.en.json --output semantic-smoke.json
```

`smoke` runs:

1. semantic index rebuild,
2. QA query warmup,
3. keyword Search QA evaluation by default.

Use `--mode keyword|auto|vector|hybrid` to change the QA evaluation mode. `--output` writes the combined semantic workflow JSON snapshot, not only the QA snapshot.

JSON stdout includes:

- `action`
- provider fields (`provider_id`, `is_semantic`, `dimension`)
- `rebuild` stats
- `warmed_queries`
- `cache_size`
- `qa.aggregate`
- `output_written`

Add `--pretty` to any subcommand for indented JSON output.
