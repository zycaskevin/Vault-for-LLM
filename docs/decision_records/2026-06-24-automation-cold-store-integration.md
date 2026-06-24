# Automation Cold-Store Integration

Date: 2026-06-24

## Decision

Integrate cold-store lifecycle handling into `vault automation run` and
`vault automation cycle`.

Balanced and autonomous policies enable `cold_store_used_expired` by default.
Conservative mode keeps it disabled. In every mode, cold-store writes still
require `--apply`.

## Why

The automation brief can identify expired-but-used memories, and v0.6.94 added
an explicit manual cold-store command. The next closed-loop step is to make the
scheduled automation path report and optionally apply the same lifecycle action
without adding a separate cron job.

## Behavior

Automation reports now include:

- `cold_store_expired`;
- cold-store action ledger entries;
- dry-run diff counts for preview/applied/skipped rows;
- activity-feed totals;
- brief summary counts.

Cold-store remains reversible:

- no hard delete;
- original content retained in `vault.db`;
- private, high/restricted, and L0/L1 rows are skipped;
- `--apply` is required for writes.
