# Automation Cycle Module Split

Date: 2026-06-25

Status: Accepted

## Context

The automation loop has become the center of the self-improving memory workflow:
feedback learning, Dream suggestions, candidate review, transcript capture,
workspace handoff, and fleet-facing reports all meet there. Keeping every helper
inside `vault/automation.py` made the file harder to review and made safety
changes harder to isolate.

This matters because automation is the part of Vault-for-LLM that can eventually
move memory through a closed loop. The code should make boundaries obvious:
orchestration belongs in `automation.py`, while cycle handoff details belong in a
smaller helper module.

## Decision

Move automation cycle workspace and transcript-capture helpers into
`vault.automation_cycle`.

The new module owns:

- writing `reports/automation/cycle-latest.json`
- building the compact cycle workspace
- generating the priority brief, suggested next tasks, and agent-start prompt
- optionally capturing selected session transcripts as candidates
- preserving content-hidden transcript capture summaries for handoffs

`vault.automation.automation_cycle()` remains the public orchestration entry
point. It still calls evaluation, policy loading, automation run, workspace
generation, and Markdown report writing in the same order.

## Safety Boundaries

- Transcript capture remains opt-in and candidate-only.
- Captured transcript content is not written into cycle handoffs.
- Captured candidates still require normal review before active memory changes,
  unless a separate narrow auto-promote policy is explicitly enabled.
- Cycle workspace writes remain constrained to `reports/automation`.
- The split does not widen auto-promote, archive, cold-store, or private-memory
  access behavior.

## Consequences

- `vault/automation.py` is smaller and easier to review.
- The automation cycle handoff surface can evolve without making the main
  automation orchestration module larger.
- Tests must continue to verify that `cycle-latest.json`,
  `cycle-latest.md`, transcript capture safety flags, and workspace path
  boundaries stay stable.

