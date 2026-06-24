# Automation Activity Observability

Date: 2026-06-24

## Decision

Add a compact read-only automation activity feed for recent closed-loop memory
automation.

## Rationale

Auto-promote can be safe only when agents and operators can quickly see what
happened. Full automation reports are useful for auditing, but they are too
large for routine agent startup. The system needs a bounded activity surface
that shows promotions, previews, and skipped reasons without exposing raw
candidate content.

## Behavior

- `vault automation activity` scans recent automation reports.
- MCP `vault_automation_activity` exposes the same read-only feed to agents.
- The feed includes ids, titles, policy reasons, gate statuses, and report
  paths.
- Private, high-sensitivity, and restricted skipped candidates hide titles.
- The feed does not include raw candidate content.
- The feed does not promote, reject, archive, delete, or mutate memory.

## Safety Boundary

This feature changes observability only. It does not widen auto-promote policy,
does not grant write permission, and does not replace the candidate review
queue.
