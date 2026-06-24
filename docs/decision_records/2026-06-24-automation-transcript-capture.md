# Decision: Opt-In Transcript Capture For Automation Cycle

Date: 2026-06-24

## Context

Vault already had the major automation loop pieces: candidate memory, usage
telemetry, feedback evaluation, Dream suggestions, forgetting suggestions, and a
compact cycle workspace. The missing link was ingestion from finished Agent
sessions. `vault automation cycle --include-transcripts` could list likely
transcript exports, but it did not convert them into reviewable memory
candidates.

## Decision

Add opt-in transcript capture to `vault automation cycle`.

The cycle may read discovered transcript files and write memory candidates only
when capture is explicitly enabled and `--apply` is present:

```bash
vault automation cycle --apply --include-transcripts --capture-transcripts
```

Generated schedules can opt into the same behavior with:

```bash
vault setup-agent --automation-capture-transcripts
```

## Boundaries

- Discovery remains metadata-only and does not read transcript contents.
- Capture reads selected transcript contents only after explicit opt-in.
- Capture writes `memory_candidates` only.
- Capture never promotes active memory.
- Capture never hard-deletes memory.
- Cycle reports and handoffs strip transcript content and candidate previews.
- Privacy, duplicate, metadata, and quality gates still decide whether a
  candidate is accepted into the review queue or rejected.

## Rationale

This closes the transcript-to-candidate part of the automation loop without
removing human ownership. Agents can do repetitive extraction work, while humans
or trusted review agents keep the promote/reject/block decision.
