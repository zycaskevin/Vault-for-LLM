# Decision Record: Automation Review Summary

Date: 2026-06-24

## Context

The automation loop can now generate activity feeds, briefs, inboxes, lifecycle
reports, learning policies, and cold-store recommendations. These are useful for
agents, but humans should not need to read full JSON reports just to decide
whether a memory lifecycle change deserves attention.

## Decision

Add `vault automation review-summary` as a read-only approval-card view. It
derives a tiny list of cards from the existing brief, inbox, and latest report.
Each card includes:

- priority
- kind and id
- recommended action
- short reason
- safe action
- whether a human decision is required
- importance details when relevant

`--write-summary` writes `reports/automation/review-summary-latest.json` and
`.md` for dashboards, scheduled handoffs, or human review.

## Safety Boundary

The review summary never:

- reads raw candidate content
- writes active memory
- writes memory candidates
- promotes candidates
- archives or deletes memory
- overrides policy, access control, or privacy gates

## Consequences

- Humans can inspect the smallest useful 5% surface first.
- Agents can hand off review state without pushing users into full reports.
- The richer automation loop stays useful without increasing human review load.
