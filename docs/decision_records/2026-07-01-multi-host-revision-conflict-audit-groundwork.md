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
- `vault sync preview-conflict`
- `vault sync resolve-conflict`

Conflict resolution supports three reviewed decisions:

- `keep_local`: keep the active local row and reject the conflicting candidate.
- `manual`: record that a trusted operator handled the conflict outside the
  automatic path.
- `accept_remote --apply-memory-change`: promote the remote candidate through
  the normal candidate path and archive the conflicting local row.

`accept_remote` is deliberately guarded by an explicit flag because it changes
active memory. It still does not silently overwrite rows; the old local content
remains archived for audit and restore.

Before resolving, operators and agents should use `vault sync preview-conflict
<conflict_id>` to see a compact local-vs-remote summary, short diff, available
resolution choices, and a safe recommended next command. The preview is
read-only and intentionally does not return full raw memory dumps.

Not implemented yet:

- multi-master active-knowledge writes
- automatic conflict merging
- full active-knowledge rollback from the revision graph
- distributed revision exchange
- cryptographic remote writer identity beyond existing agent/MCP controls

## Product Language

Use this phrasing externally:

> Remote machines can submit memory candidates. A trusted local Vault pulls them
> into review, records revisions, detects conflicts, and keeps an audit trail.
> If a trusted reviewer accepts a remote candidate, Vault promotes it through the
> candidate path and archives the conflicting local row instead of overwriting it.
> Full multi-master active-memory writes are intentionally not enabled yet.

Avoid saying:

> Vault has real-time bidirectional active-memory sync.

That would overstate the current safety boundary.
