# Startup Review And Learning Prefaces

Date: 2026-06-25

## Context

Vault automation now writes a short human-review card deck and a learning-health
dashboard. Before this change, agents could read the latest automation handoff,
but the handoff contract only guaranteed fleet health plus the selected
cycle/inbox content.

That meant the smallest review surface existed, but each runtime still had to
know which extra files to open.

## Decision

`vault automation handoff` and MCP `vault_automation_handoff` now attach these
startup prefaces when they exist:

- `fleet_health_content`
- `review_summary_content`
- `learning_health_content`
- `content`

The selected handoff remains in `content`. The new prefaces are separate fields
so existing readers do not lose compatibility.

Generated MCP startup guides, adapter templates, runtime playbooks, and
`startup-doctor` all use the same read order:

1. fleet health
2. 5% human-review cards
3. learning-health status
4. selected cycle/inbox handoff

## Boundaries

The prefaces are read-only. They do not:

- read raw transcripts
- expose raw candidate content
- promote candidates
- archive or delete active memory
- apply review-card lifecycle recommendations

## Consequences

Every runtime can start from one handoff tool call and still see the smallest
useful memory surfaces first. This keeps Codex, Claude Code, OpenClaw, Hermes
Agent, and other MCP-capable runtimes aligned without each one inventing a
different startup ritual.
