# Automation Strategy

Vault automation is meant to reduce review load without removing human control.
The default posture is:

1. Agents do routine discovery, scoring, sorting, and report writing.
2. New memory enters the candidate queue first.
3. Risky lifecycle actions stay visible and reversible.
4. Humans review the smallest useful surface, not the whole memory corpus.

## Modes

| Mode | Use when | Default behavior |
|---|---|---|
| `conservative` | First install, sensitive projects, or uncertain policies | Report-first, no automatic archive or promotion |
| `balanced` | Normal local project memory automation | Reversible lifecycle actions may be planned or applied when explicitly requested |
| `autonomous` | Trusted local maintenance jobs with prior review | Wider automation, still bounded by policy gates |

`vault automation plan --write-policy` writes the policy file. The file remains
user-owned; agents should explain changes before applying them.

## The Daily Loop

```bash
vault memory pipeline --write-report
vault memory reflection
vault automation cycle --write-workspace
vault automation inbox --limit 5 --write-handoff
vault automation review-summary --write-summary
vault automation learning-health --write-health
```

This loop gives agents a compact startup surface:

- what transcripts were discovered
- what candidates were created
- what memories look expired, duplicated, or underspecified
- which five-ish review cards need human attention
- whether feedback learning changed sorting hints

## Auto-Promotion

Auto-promotion is off unless policy explicitly enables it. Even then, it should
only apply to narrow low-risk memories that pass existing gates:

- allowed source, such as `session_capture`
- allowed memory type, such as `session_lesson`
- low sensitivity
- acceptable trust
- source reference present
- privacy, metadata, duplicate, and quality gates pass

The goal is not to let agents write everything. The goal is to let agents learn
which routine memories are safe enough that humans only need to inspect the
exception queue.

## What Automation Must Not Do

- Do not hard-delete memory.
- Do not expose raw private candidate content in dashboard or handoff reports.
- Do not promote high/restricted sensitivity memories automatically.
- Do not treat LLM-generated summaries as stronger evidence than original
  source ranges.

## GUI Implication

A future GUI should not start with a giant table of every memory. It should
start with the automation health surface:

- current cycle status
- five review cards
- candidate gate failures
- learning-health summary
- rollback or audit links for applied lifecycle actions
