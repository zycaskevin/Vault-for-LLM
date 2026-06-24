# Decision Record: Automation Learning Health

Date: 2026-06-25

## Context

Vault automation can now record review-card feedback and turn repeated outcomes
into bounded ranking hints. That gives the system a learning loop, but humans
and agents still need a small status surface before opening full evaluation
reports.

## Decision

Add `vault automation learning-health` as a read-only health panel for the
feedback-learning loop.

The command summarizes:

- accepted or promoted outcomes
- rejected or blocked outcomes
- deferred outcomes
- active prefer/downgrade/observe rules
- short health cards
- top learned rules

`--write-health` writes `reports/automation/learning-health-latest.json` and
`.md` for dashboards, startup handoffs, or scheduled review.

## Safety Boundary

Learning health never:

- lists raw feedback reasons
- promotes memory
- writes memory candidates
- archives memory
- deletes memory
- applies the learning policy
- overrides privacy, access, or governance policy

## Consequences

- Humans can see whether automation learning is cold, healthy, worth watching,
  or needs review.
- Agents can use one compact startup signal instead of opening full eval output.
- Learning remains an ordering hint, not a mutation or authorization path.
