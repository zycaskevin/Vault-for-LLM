# GUI Safe Candidate Review

Date: 2026-06-27

## Decision

The first write-capable GUI workflow is limited to memory candidate review:

- inspect candidate metadata, gate status, and content
- promote a candidate through the existing `promote_candidate(confirm=True)`
  workflow
- reject or block a candidate through the existing `review_candidate()`
  workflow

The GUI must not directly write active knowledge, bypass gates, or introduce a
parallel review system.

## Safety Boundary

All GUI review mutations use `POST` and require an explicit confirmation token:

```text
<candidate_id>:<action>
```

For example:

```text
mem_abc123:promote
```

This keeps accidental clicks, bookmarks, preloaders, and plain `GET` requests
from mutating memory.

Promotion still reruns privacy and metadata gates. Rejection and blocking still
record feedback events so automation can learn from human review.

## Scope

In scope:

- candidate queue in the GUI overview
- candidate detail view
- promote, reject, and block actions with confirmation
- local-only JSON endpoints served by `vault gui`

Out of scope:

- editing candidate content in the GUI
- bulk review actions
- direct active-memory edits
- policy edits
- remote Supabase write workflows

## Rationale

The GUI should make the 5 percent human review surface easy to judge without
turning the browser into an unsafe admin panel.

Candidate review is the right first mutation because it already has established
gates, feedback events, and rollback-friendly state transitions.
