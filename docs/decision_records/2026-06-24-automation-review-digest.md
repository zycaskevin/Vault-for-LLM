# Automation Review Digest

Date: 2026-06-24

## Context

The memory loop is becoming more automated: session capture can write
candidates, automation can evaluate feedback, low-risk promotion can be
enabled by policy, and cold-store can summarize then archive expired-but-used
memory. The user still wants review ownership, but only for the smallest
meaningful set of decisions.

## Decision

`vault automation inbox` now builds a `review_digest` before the detailed
candidate queue. The digest converts the latest automation report's
`human_review.items` into compact cards with:

- `recommended_action`;
- `safe_action`;
- priority;
- count;
- report path.

`vault automation brief` uses the same digest for its 5% human-review section.

## Boundaries

- The digest is read-only.
- Candidate content stays hidden unless explicitly requested.
- Report-level cards do not approve policy changes.
- The digest is a triage surface, not a substitute for the detailed report
  ledger when something looks surprising.

## Result

Humans can review protected TTL decisions, expired-but-used memory,
cold-store summaries, promotion previews, Dream suggestions, and Forgetting
suggestions without opening raw candidate content first. Agents still handle
routine sorting and reporting.
