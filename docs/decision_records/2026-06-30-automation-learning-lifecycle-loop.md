# Automation Learning And Lifecycle Loop

Date: 2026-06-30

## Decision

Strengthen the automation loop without turning it into a black-box memory
writer.

The loop now treats long-term feedback as a safety signal for automation:

- repeated positive outcomes can move matching review cards earlier;
- repeated rejected/blocked outcomes can require review before auto-promotion;
- memory importance exposes a `weight_tier` and `lifecycle_action`;
- cold-store previews expose a `lifecycle_strategy` for compress, demote, and
  archive decisions.

## Why

Vault should become more useful as it observes promote/reject outcomes, but
automation must stay bounded. Learning is allowed to rank and block risky
automation. It is not allowed to bypass privacy gates, access policy, or human
approval boundaries.

## Boundaries

- Learning policy is a ranking and safety hint, not an authorization policy.
- Auto-promotion remains opt-in and still requires `--apply`.
- A learned downgrade can block auto-promotion and keep a candidate in review.
- Cold-store still summarizes and archives reversibly; it does not hard delete.
- Original memory content remains available for audit/restore after cold-store.

## Product Shape

This keeps the 95/5 review model:

- agents handle recurring review ordering, lifecycle previews, and cold-store
  summaries;
- humans see the small set of cards where policy or learned outcomes disagree;
- stronger autonomy can be considered only after repeated feedback supports it.
