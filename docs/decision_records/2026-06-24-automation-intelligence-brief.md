# Automation Intelligence Brief

Date: 2026-06-24

## Decision

Add a compact read-only automation intelligence brief for humans, local agents,
and future dashboards.

The brief combines five signals:

- learning hints from long-term promote/reject outcomes;
- memory usage weights from retrieval and citation counters;
- long-term forgetting pressure for expired, used, and protected memories;
- shared agent activity health from the local agent registry;
- the smallest useful human-review queue.

## Why

The memory loop is becoming more autonomous. Humans should keep review power,
but they should not need to read every candidate, transcript, report, and
archive preview. The product direction is that agents handle most routine
memory work, while humans inspect a short 5% decision surface.

## Boundaries

`vault automation brief` is intentionally read-only. It does not:

- promote candidates;
- read raw candidate content;
- compress memories;
- demote memories;
- move rows to cold storage;
- widen automation policy.

Forgetting recommendations are strategy hints only. Future versions may add
separate explicit commands for summarize, demote, or cold-store workflows, but
the brief itself remains an observability surface.

## Interface

CLI:

```bash
vault automation brief --pretty
vault automation brief --write-brief --pretty
```

MCP:

```text
vault_automation_brief
```

The MCP tool is included in the `core` profile because it is safe for startup
and does not expose raw candidate content.

## Follow-Ups

- Feed brief output into a multi-agent dashboard.
- Add explicit summarize/demote/cold-store workflows after the strategy layer
  has enough real usage data.
- Keep learning hints as ranking guidance until repeated outcomes justify any
  narrower automation rule.
