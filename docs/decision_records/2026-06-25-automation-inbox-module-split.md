# Automation Inbox Module Split

Date: 2026-06-25

## Decision

Move automation inbox and review-digest helpers from `vault.automation` into `vault.automation_inbox`.

The moved helpers cover:

- `automation_inbox`
- inbox handoff JSON writing
- candidate queue priority and recommended action hints
- candidate and report review digest cards
- compact inbox summary generation

## Context

The automation inbox is a bounded review surface for humans and agents. It is intentionally read-only by default and should expose the smallest useful queue before anyone opens raw candidate content or changes memory state.

This responsibility is different from the broader automation cycle orchestration, which also handles Dream reports, lifecycle review, cold-store, auto-promote previews, activity logs, handoffs, and fleet health.

## Consequences

- `vault.automation` remains the daily automation orchestration module.
- `vault.automation_inbox` owns inbox queue shaping and review digest details.
- Existing CLI/MCP behavior remains unchanged because `vault.automation` still imports and exposes `automation_inbox`.
- Future inbox changes should keep content hidden by default and keep handoff paths constrained under `reports/automation`.

## Verification

The release gate should verify:

- `vault automation inbox` still returns `read_only`, `auto_promote: false`, and `content_hidden_by_default` safety fields.
- `vault automation inbox --write-handoff` still writes under `reports/automation`.
- MCP `vault_automation_inbox` still returns compact queues without raw content by default.
- `scripts/module_size_gate.py` reflects the lower `vault/automation.py` size after the split.
