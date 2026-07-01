# Multi-Host Revision, Conflict, And Audit Groundwork

Date: 2026-07-01

## Decision

Vault-for-LLM should not jump directly from remote candidate requests to
multi-master active-knowledge writes.

The first safe multi-host layer is local observability:

- record a revision when a remote candidate is imported;
- record another revision when a pulled candidate is locally promoted;
- detect simple conflicts before remote content changes active knowledge;
- write audit events for imports, promotions, conflict openings, and conflict
  resolutions;
- expose the state through `vault sync revisions`, `vault sync conflicts`, and
  `vault sync audit`.

Conflict resolution records a reviewed decision. It does not silently overwrite
active knowledge.

## Why

The product goal is one memory vault that many agents, runtimes, and eventually
devices can use. That requires remote contribution, but direct shared writes can
damage the memory base if a hosted agent, stale machine, or untrusted workflow
writes the wrong fact.

Candidate-first sync keeps the strongest current boundary:

1. Remote hosts can suggest memory.
2. A trusted local host pulls those suggestions into `memory_candidates`.
3. Existing privacy, duplicate, metadata, and quality gates still run.
4. Optional low-risk promotion is controlled by local `automation_policy.yaml`.
5. Conflicts become visible before they become active knowledge.

## Current Scope

Implemented now:

- `memory_revisions`
- `memory_conflicts`
- `memory_audit_log`
- revision records for remote candidate import and low-risk local promotion
- simple same-title / different-content conflict detection
- local conflict resolution audit
- `vault sync revisions`
- `vault sync conflicts`
- `vault sync audit`
- `vault sync resolve-conflict`

Not implemented yet:

- multi-master active-knowledge writes
- automatic conflict merging
- rollback of active knowledge from the revision graph
- distributed revision exchange
- cryptographic remote writer identity beyond existing agent/MCP controls

## Product Language

Use this phrasing externally:

> Remote machines can submit memory candidates. A trusted local Vault pulls them
> into review, records revisions, detects conflicts, and keeps an audit trail.
> Full multi-master active-memory writes are intentionally not enabled yet.

Avoid saying:

> Vault has real-time bidirectional active-memory sync.

That would overstate the current safety boundary.
