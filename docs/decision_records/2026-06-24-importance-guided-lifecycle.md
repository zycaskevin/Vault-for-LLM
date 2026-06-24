# Decision Record: Importance-Guided Memory Lifecycle

Date: 2026-06-24

## Context

Vault now has an explainable memory importance model for `automation brief`.
That makes the daily review surface clearer, but lifecycle operations still
needed to use the same signal. Without a shared score, cold-store review could
show expired-but-used memories in database order instead of the order that best
matches user attention.

## Decision

Use the same `importance_score` model for lifecycle preview and reporting:

- `cold-store-expired` items include `importance_score`,
  `importance_components`, `importance_signals`, and
  `importance_recommendation`
- expired-but-used cold-store candidates are sorted by importance, citation
  count, access count, and id
- `usage_review` and automation action ledgers preserve the importance fields
- dry-run diffs expose `highest_cold_store_importance`

## Safety Boundary

Importance is still advisory. It can rank, explain, and prioritize review. It
must not:

- bypass access policy
- promote candidate memory
- hard-delete memory
- archive protected memory
- override user-owned automation policy

## Consequences

- Agents and dashboards can explain why an expired memory appears first.
- The 5% review surface becomes more actionable.
- Future memory lifecycle work can tune one scoring module rather than separate
  brief and cold-store heuristics.
