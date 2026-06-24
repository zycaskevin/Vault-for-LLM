# Cold-Store Lifecycle

Date: 2026-06-24

## Decision

Add an explicit, dry-run-first cold-store workflow for expired-but-used memory.

The workflow is available through:

```bash
vault usage cold-store-expired
vault usage cold-store-expired --apply
```

and MCP:

```text
vault_cold_store_expired
```

## Why

Archiving unused expired memory is not enough. Some memories are technically
expired but still retrieved or cited. Those should not disappear from the daily
recall path without leaving a smaller summary and an audit trail.

## Behavior

Eligible rows:

- have `expires_at` in the past;
- have at least one retrieval or citation usage signal;
- are not private;
- are not high/restricted sensitivity;
- are not L0/L1.

On apply, Vault:

- writes a compact summary;
- sets `summary_generated_at`;
- demotes eligible rows to the daily-detail layer;
- sets `status=archived`;
- keeps original `content_raw` in the database for audit and restore.

## Non-Goals

This is not hard deletion. It does not erase raw content, mutate private
memory, or rewrite source-of-truth documents. It is a reversible lifecycle step
that removes eligible rows from normal recall while preserving accountability.
