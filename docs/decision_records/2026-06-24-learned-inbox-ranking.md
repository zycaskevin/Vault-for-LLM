# Learned Inbox Ranking

Date: 2026-06-24

## Context

Vault automation already records promote/reject/block feedback and can write a
bounded `reports/automation/learning_policy.json`. Before this decision, the
learning policy mostly helped Dream/curation ordering. The daily human-review
surface still treated most candidate groups with static priority.

## Decision

`vault automation inbox` now reads the learning policy and applies matching
bounded priority multipliers to candidate review items. The same ordering flows
into `vault automation brief` because the brief uses the inbox digest.

Each adjusted candidate exposes:

- `base_priority`;
- `priority`;
- `learning_multiplier`;
- `learning_action`;
- `learning_reason`;
- `learning_rule_confidence`.

## Safety Boundary

Learning policy remains a ranking hint only.

It does not:

- authorize promotion;
- authorize deletion or cold-store;
- bypass privacy, duplicate, metadata, quality, scope, sensitivity, ownership,
  or source-reference checks;
- change `auto_promote_low_risk_candidates`.

The multiplier remains capped by the policy bounds, currently `0.85` to `1.15`.

## Result

After enough reviewed feedback, agents can show humans the most promising or
most questionable memory candidates earlier, while keeping candidate-first
governance intact.
