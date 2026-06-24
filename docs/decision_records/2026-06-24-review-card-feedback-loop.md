# Decision Record: Review Card Feedback Loop

Date: 2026-06-24

## Context

`vault automation review-summary` gives humans a tiny approval-card surface for
the few memory automation decisions that still need judgment. The next step is
to let those decisions improve future ordering without turning the system into
an uncontrolled self-writing memory store.

## Decision

Add `vault automation review-feedback` as a feedback-only command for one
review-summary card.

Supported decisions:

- `accept`
- `reject`
- `defer`

The command records a `memory_feedback_events` row with `event_type` set to
`review_card_outcome`. When `--write-learning-policy` is used, it immediately
refreshes `reports/automation/learning_policy.json`.

## Safety Boundary

Review feedback never:

- promotes memory
- writes memory candidates
- archives memory
- deletes memory
- applies the card's recommended lifecycle action
- overrides privacy, access, or governance policy

The learning policy remains a bounded ranking hint. It can move future review
cards up or down, but it cannot authorize mutation.

## Consequences

- Repeatedly accepted card types can move earlier in the 5% review surface.
- Repeatedly rejected card types can move later or stay under review.
- Humans keep the final decision right while agents learn to sort better.
