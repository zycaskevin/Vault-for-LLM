# Low-Risk Auto-Promote Policy

Date: 2026-06-24

## Decision

Vault automation may support automatic promotion from candidate memory to
active memory, but only through an explicit low-risk policy. The default remains
off for all automation modes.

## Rationale

The memory loop needs to become more automatic over time, but active memory is
the durable source of truth for agents. Automatic promotion should therefore be
narrow, auditable, and reversible by review, not a general "remember
everything" switch.

## Policy Boundary

The first supported policy promotes only candidates that meet all of these
conditions:

- `auto_promote_low_risk_candidates: true`
- command includes `--apply`
- source is allowed, default `session_capture`
- memory type is allowed, default `session_lesson`
- scope is allowed, default `project`, `shared`, or `public`
- sensitivity is allowed, default `low`
- trust is at or above the configured threshold, default `0.65`
- source reference is present
- privacy, duplicate, metadata, and quality gates all pass

Private, high-sensitivity, restricted, duplicate, weak, or sourceless
candidates remain in the review queue.

## Consequences

- `vault automation run` and `vault automation cycle` can now close the
  candidate-to-active loop when policy and `--apply` both allow it.
- Dry runs preview eligible candidates without promotion.
- Reports, cycle workspaces, and CLI output expose promotion counts and skipped
  reasons for review.
- Broader promotion rules must be introduced as explicit policy changes, not as
  hidden learning behavior.

