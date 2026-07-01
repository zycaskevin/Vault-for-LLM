# Safe Bidirectional Candidate Sync

Date: 2026-07-01

## Decision

Vault supports the first phase of multi-machine sync as **candidate request
sync**, not active-knowledge co-writing.

Remote agents can submit memory suggestions to Supabase through
`vault_submit_memory_request`. A trusted local sync host can pull those requests
into the local `memory_candidates` queue with `vault remote pull-candidates`.
Normal Vault gates, review, promotion, and audit rules still decide whether a
request becomes active knowledge.

## Why

The product goal is one memory layer that many agents and machines can use
without scattering knowledge across tools. But letting remote hosts directly
write active knowledge would make conflict resolution, privacy boundaries,
rollback, and trust too fragile for general users.

Candidate sync gives us useful bidirectional behavior now:

- remote machines can submit lessons and observations
- local or authorized agents remain the source-of-truth reviewers
- privacy and quality gates still run locally
- service role keys stay only on trusted sync hosts
- anon/publishable keys can submit through an RPC but cannot read or update the
  request table directly

## Non-Goals

- No direct remote writes into `vault_knowledge`.
- No automatic promotion from remote requests in phase 1.
- No multi-master active knowledge merge.
- No conflict resolver or revision graph yet.

## Next Phases

1. Low-risk auto merge:
   low sensitivity, high trust, no conflict, passing local gates can be promoted
   by explicit policy; everything else goes to the daily 5% review report.
2. True multi-host co-writing:
   revision graph, conflict resolver, rollback, and append-only audit log.

## Operator Boundary

Use `SUPABASE_ANON_KEY` or `SUPABASE_PUBLISHABLE_KEY` for
`vault remote submit-candidate`.

Use `SUPABASE_SERVICE_ROLE_KEY` only on the trusted host that runs
`vault remote pull-candidates --apply`.
