# Pipeline Receipt Startup Preface

## Context

`vault memory pipeline --write-report` writes a compact ingestion receipt, but
new agent sessions still had to know the report path or inspect schedule logs to
see whether transcript ingestion ran.

The existing startup handoff already surfaces fleet health, review-summary
cards, and learning-health as read-only prefaces before the selected cycle or
inbox handoff.

## Decision

`vault automation handoff` and MCP `vault_automation_handoff` now expose the
latest pipeline receipt as:

- `pipeline_receipt_path`
- `pipeline_receipt_content_type`
- `pipeline_receipt_content`

The startup read order is:

1. `fleet_health_content`
2. `pipeline_receipt_content`
3. `review_summary_content`
4. `learning_health_content`
5. selected `content`

The selected `content` field remains the cycle/inbox handoff for backward
compatibility. Handoff assembly now lives in `vault/automation_handoff.py` so
the main automation module does not grow past the module-size guardrail.

## Consequences

- A scheduled memory-ingestion pass is visible to the next agent without
  requiring raw logs or full report traversal.
- Startup still follows progressive disclosure: health, ingestion receipt,
  human-review cards, learning health, then task handoff.
- Pipeline receipt prefaces are read-only and do not promote memory, read raw
  transcripts, or expose candidate body fields.
