# Memory Pipeline Ingestion Receipt

## Context

The automatic memory loop can now discover session transcripts, extract reusable
lessons, and write gated memory candidates. Scheduled agents need proof that the
ingestion step ran, but they should not need to inspect logs, raw transcripts,
or full candidate bodies just to continue work.

## Decision

`vault memory pipeline` can write `reports/automation/pipeline-latest.json` and
`reports/automation/pipeline-latest.md` when `--write-report` is passed.
Generated setup-agent automation schedules include this flag by default.

The report is a receipt, not a memory store. It contains discovery counts,
processed capture counts, candidate write/preview/reject counts, compact
candidate metadata, and the next action. It strips raw candidate body fields,
content previews, and gate payloads from the persisted report.

## Consequences

- Scheduled memory ingestion becomes observable to the next agent.
- The report can be shared with review or maintenance agents without becoming a
  transcript dump.
- Candidate-first safety remains unchanged: the pipeline still writes only
  candidates when explicitly requested and never promotes active memory.
- Future handoff work can surface the receipt as a startup preface after moving
  handoff-preface assembly out of the already-large automation module.
