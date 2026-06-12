# Persistent Embedding Cache

Vault semantic workflows can optionally persist embedding results in the SQLite database. This keeps default behavior unchanged: `warm` and `smoke` use only a process-local in-memory cache unless `--persist-cache` is passed.

## Storage

`VaultDB` initializes an `embedding_cache` table with public-safe keys:

- `provider_id`
- `dimension`
- SHA-256 hash of the UTF-8 source text
- JSON-encoded embedding vector
- optional source `text`
- `created_at`, `last_used_at`, and `hit_count`

The uniqueness boundary is `(provider_id, dimension, text_hash)`, so cache rows are not reused across providers or dimensions.

## CLI usage

Persist cache entries while warming QA queries:

```bash
vault semantic warm --qa-file qa.json --persist-cache
```

Persist cache entries while rebuilding and running a smoke snapshot:

```bash
vault semantic smoke --qa-file qa.json --persist-cache --output semantic_smoke.json
```

`rebuild` also supports the flag because it encodes node and claim vectors:

```bash
vault semantic rebuild --persist-cache
```

For local deterministic testing, combine with the explicit hash-provider gate:

```bash
vault semantic warm --qa-file qa.json --allow-hash --hash-dim 8 --persist-cache
```

When `--persist-cache` is used, JSON output includes a `persistent_cache` object with counters such as `persistent_hits`, `persistent_misses`, `writes`, and in-memory `memory_rows`.

## Stats

Show aggregate cache stats:

```bash
vault semantic cache-stats
```

Filter by provider and dimension:

```bash
vault semantic cache-stats --provider-id hash-deterministic-v1 --dimension 8
```

The output is JSON and includes:

- `action: "cache-stats"`
- `total_rows`
- `total_hits`
- optional `provider_id` / `dimension` filters
- oldest/newest `last_used_at` timestamps

## Pruning

Keep only the newest N rows:

```bash
vault semantic cache-prune --max-rows 10000
```

Delete rows older than a number of days:

```bash
vault semantic cache-prune --older-than-days 30
```

Filters can be combined:

```bash
vault semantic cache-prune --provider-id my-provider --dimension 384 --max-rows 5000
```

The output is JSON with `deleted_rows`.
