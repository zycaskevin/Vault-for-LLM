# Decision Record: Explainable Memory Importance Score

Date: 2026-06-24

## Context

Vault automation already records lightweight usage counters and can identify
expired-but-used memories. The next step in the automation loop is to decide
which memories should be protected, refreshed, summarized, or cold-stored first.
Using raw access counts alone is too shallow: a frequently opened note is not
always more important than a rarely opened but cited source-of-truth decision.

## Decision

`vault automation brief` now exposes an explainable `importance_score` for
top-used memories. The score is a bounded ranking signal, not a permission
system and not a source-of-truth override.

The first model includes:

- access count
- citation count
- recency from `last_accessed_at`
- trust
- freshness
- TTL pressure for expired or soon-expiring memories that are still used
- small protection hints from scope and sensitivity

The brief also returns `importance_components`, `signals`, and a recommendation
per item. `weight_score` remains as a compatibility alias for existing
integrations.

## Consequences

- Agents can explain why a memory is being protected or reviewed.
- Expired-but-used memories are easier to refresh or cold-store before they
  vanish from daily recall.
- The 5% human-review surface stays short while becoming more actionable.
- Future ranking work can tune one component at a time without changing the
  access-control model.

## Non-goals

- The importance score does not promote candidate memory.
- The importance score does not bypass scope, sensitivity, owner, or allowed
  agent checks.
- The importance score does not hard-delete or archive memory by itself.
