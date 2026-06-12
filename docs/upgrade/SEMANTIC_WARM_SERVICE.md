# Semantic Warm Service

This upgrade adds an importable semantic lifecycle hook and a bounded warm daemon for operators that want embedding cache warm-up during application startup.

## Importable API

Use `vault.semantic_lifecycle` directly from application code instead of shelling out to argparse-only CLI commands:

```python
from vault.semantic_lifecycle import run_semantic_startup, run_semantic_daemon

summary = run_semantic_startup(
    db_path="vault.db",
    qa_file="search_qa.json",
    persist_cache=True,
    rebuild=False,
    smoke=True,
)
```

### `run_semantic_startup(...)`

Runs one startup cycle and returns a JSON-serializable dictionary containing:

- `success`
- provider identity (`provider_id`, `is_semantic`, `dimension`)
- cache stats before and after
- rebuild counts when `rebuild=True`
- deduplicated warmed QA query count
- prune deleted row count when pruning is requested
- Search QA aggregate metrics when `smoke=True` and `qa_file` is supplied

Safe defaults:

- real configured embedding provider by default
- deterministic hash provider only with explicit `allow_hash=True` for tests/dev
- persistent embedding cache enabled by default (`persist_cache=True`)
- semantic vector rebuild disabled by default (`rebuild=False`) because rebuild mutates indexed vector rows and can be expensive

Optional arguments include `qa_file`, `allow_hash`, `hash_dim`, `db_path`, `persist_cache`, `rebuild`, `smoke`, `mode`, `limit`, `older_than_days`, and `max_rows`.

### `run_semantic_daemon(...)`

Runs repeated startup cycles and returns a JSON-serializable dictionary with per-iteration summaries:

```python
summary = run_semantic_daemon(
    db_path="vault.db",
    qa_file="search_qa.json",
    repeat=2,
    interval=0,
    allow_hash=True,  # tests/dev only
)
```

The daemon is bounded by default: `repeat=1`. `repeat=0` runs forever and should only be used under an explicit process supervisor. Tests and CI should use finite repeat values and may use `interval=0`.

### Provider cleanup

`close_provider(provider)` is a best-effort helper. It calls `provider.close()` when available and suppresses close errors so cleanup does not mask startup success or earlier failures.

## CLI

The existing one-shot commands (`rebuild`, `warm`, `smoke`, `cache-stats`, `cache-prune`) keep their behavior. New lifecycle commands are available under `vault semantic` and emit JSON to stdout.

### Startup

```bash
vault semantic startup \
  --db-path vault.db \
  --qa-file search_qa.json \
  --rebuild \
  --smoke \
  --output semantic_startup.json \
  --pretty
```

Useful options:

- `--no-persist-cache` disables the default durable embedding cache
- `--allow-hash --hash-dim 32` enables deterministic hash embeddings for tests/dev only
- `--older-than-days N` prunes cache rows older than `N` days
- `--max-rows N` keeps only the newest `N` cache rows
- `--mode keyword|auto|vector|hybrid` and `--limit N` control optional Search QA smoke

### Bounded daemon

```bash
vault semantic daemon \
  --db-path vault.db \
  --qa-file search_qa.json \
  --repeat 2 \
  --interval 60
```

The CLI default is `--repeat 1`, not forever. For smoke tests use `--interval 0`. If using `--repeat 0`, run it only under a supervisor that can stop or restart the process.

## Test/dev hash example

```bash
vault semantic startup \
  --db-path /tmp/vault.db \
  --qa-file /tmp/search_qa.json \
  --allow-hash \
  --hash-dim 8 \
  --rebuild \
  --smoke
```

Hash embeddings are public-safe and deterministic, but they are not semantic. Production startup should configure a real embedding provider instead of passing `--allow-hash`.
