# Review Feedback Visible Closed Loop

Date: 2026-06-25

## Context

Review-summary cards are the smallest human approval surface in the automation
loop. Before this change, `vault automation review-feedback
--write-learning-policy` recorded the decision and wrote
`reports/automation/learning_policy.json`, but the user still had to run another
command to see how that decision affected the next review queue.

That made the feedback loop technically correct but emotionally invisible: the
system learned, yet the next useful artifact was not produced at the point of
review.

## Decision

When `automation review-feedback` is called with `--write-learning-policy`, Vault
now immediately refreshes:

- `reports/automation/learning_policy.json`
- `reports/automation/review-summary-latest.json`
- `reports/automation/review-summary-latest.md`
- `reports/automation/learning-health-latest.json`
- `reports/automation/learning-health-latest.md`

The command payload and CLI output expose the refreshed paths and the top learned
action, so an agent or person can open the next card deck immediately.

## Boundaries

Review feedback remains feedback-only. It does not:

- promote candidates
- archive active memory
- move memory to cold storage
- delete rows
- widen policy
- apply the card's recommended lifecycle action

Learned actions remain ranking hints only. They can affect card ordering through
the existing capped multiplier, but they are not authorization decisions.

## Consequences

The review loop is now visible in one step:

1. Read `review-summary-latest.md`.
2. Accept, reject, or defer one card with `automation review-feedback`.
3. Open the refreshed `review-summary-latest.md` and `learning-health-latest.md`.

This keeps human review short while giving agents a clear artifact to continue
from after each decision.
