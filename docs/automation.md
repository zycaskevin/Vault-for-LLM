# Memory Automation

Vault automation is policy-based. The goal is to let agents do routine memory
maintenance while humans keep ownership of the rules and high-impact changes.

Automation does not hard-delete memory. The first phase is report-first and
reversible:

- capture useful agent-session lessons as reviewable candidates
- collect usage and lifecycle counters
- split expired memories into low-risk archive candidates and used items that
  need TTL review
- skip protected memories, such as `scope: private` or high-sensitivity rows,
  unless the policy is intentionally changed
- preview expired-memory archival
- optionally archive expired memories when policy and `--apply` both allow it
- write an action ledger and dry-run diff explaining what changed or was skipped
- run a Dream report for stale, duplicate, weak, or orphaned knowledge
- produce an automation report for operators and agents

## Modes

| Mode | Intended use | Default behavior |
|---|---|---|
| `conservative` | sensitive teams or early rollout | reports only; `--apply` does not archive |
| `balanced` | personal and small-team vaults | report-first; `--apply` may archive expired rows |
| `autonomous` | long-running private agents | higher review thresholds; still no hard delete |

Humans review the policy. Agents handle the repetitive work.

## Commands

Preview candidate extraction from an agent session:

```bash
vault capture discover --pretty
vault capture session codex-session.jsonl --pretty
```

Write extracted session lessons into the candidate queue:

```bash
vault capture session codex-session.jsonl --write-candidates --pretty
```

Discovery lists likely transcript exports without reading transcript contents.
Session capture supports JSONL, Markdown, and plain text transcripts. It looks
for reusable decisions, pitfalls, workflows, and source-of-truth lines. It does
not write active knowledge; captured items still pass through privacy,
duplicate, metadata, and quality gates.

MCP reviewer agents can call `vault_capture_discover` and
`vault_capture_session` for the same extractor. These MCP tools stay out of the
`core` profile. Capture is preview-only by default and requires
`write_candidates=true` before it writes gated candidates.

Preview the current plan:

```bash
vault automation plan --pretty
```

Write a starter policy:

```bash
vault automation plan --mode balanced --write-policy --pretty
```

Run the maintenance pass without mutation:

```bash
vault automation run --pretty
```

Apply only policy-allowed reversible actions:

```bash
vault automation run --apply --pretty
```

List recent automation reports:

```bash
vault automation report --pretty
```

Show the latest report as a review handoff:

```bash
vault automation report --latest --detail --pretty
```

Show the shortest review inbox:

```bash
vault automation inbox --limit 5 --pretty
```

`automation inbox` is the daily review surface for the closed loop. It reads the
candidate queue and latest automation report, then ranks the smallest useful
set of items for a human or trusted agent to inspect. It is read-only, hides
candidate content by default, and prioritizes privacy-blocked, sensitive,
duplicate, weak-quality, and automation-generated candidates.

Scheduled agents can persist the same short handoff:

```bash
vault automation inbox --write-handoff --pretty
```

This writes `reports/automation/inbox-latest.json`, which is safe for the next
agent to read before deciding whether to promote, reject, block, or ask for a
human decision.

Read a specific report:

```bash
vault automation report --report-path reports/automation/2026-06-23-054055.json --detail --pretty
```

Check readiness for scheduled automation:

```bash
vault automation doctor --pretty
```

Evaluate whether automation suggestions are becoming useful:

```bash
vault automation eval --pretty
```

`automation eval` reads feedback events from candidate outcomes such as
promoted, rejected, or blocked suggestions. It reports acceptance rates by
source, memory type, and category. This is the first learning loop: automation
can see which kinds of suggestions humans or trusted agents actually accepted,
without using that signal to auto-promote, auto-delete, or override privacy
policy.

For automation agents that need a handoff file, run:

```bash
vault automation eval --write-learning-policy --pretty
```

This writes `reports/automation/learning_policy.json`. The file is intentionally
bounded: it can suggest `prefer_candidates`, `downgrade_or_require_review`,
`keep_observing`, or `observe`, with priority multipliers capped between `0.85`
and `1.15`. It is a ranking and review hint, not an authorization policy.

On later runs, `vault dream` and `vault automation run` read the same handoff
file automatically. Matching Dream candidate suggestions are annotated with the
learning action, confidence, and multiplier, then sorted by bounded priority.
This helps review agents look at the most promising cleanup work first without
changing the candidate-first safety boundary.

Candidate feedback can come from promotion, from explicit CLI review, or from
MCP review tools:

```bash
vault candidate-review mem_123 --outcome rejected --reason "Too vague."
```

The same path is available to agents as `vault_memory_review`. Both record a
`memory_feedback_events` row without promoting memory.

Run one full feedback-to-curation cycle:

```bash
vault automation cycle --apply --pretty
```

`automation cycle` is the one-command version of the learning loop. It first
runs `automation eval --write-learning-policy`, then runs policy-based
automation so Dream can consume the freshly written learning policy. The cycle
is still bounded: it can write review candidates and reversible archive actions
only when policy plus `--apply` allow them. It never promotes candidates,
hard-deletes memory, or overrides privacy/access policy.

## Policy

`automation_policy.yaml` controls the automation boundary:

```yaml
mode: balanced
auto_archive_expired: true
protect_used_expired: true
protected_scopes:
  - private
protected_sensitivities:
  - high
  - restricted
auto_apply_safe_metadata: false
dream_write_candidates: true
forgetting_write_candidates: true
write_reports: true
dream_checks:
  - freshness
  - dedup
  - convergence
  - metadata
  - orphans
review_thresholds:
  expired_active: 5
  used_expired: 1
  pending_candidates: 10
  duplicate_groups: 1
  weak_metadata: 10
```

Phase 1 intentionally keeps `auto_apply_safe_metadata` off. Dream reports can
suggest metadata cleanup, but scheduled automation should not rewrite memory
content, promote private memories, change sharing permissions, or delete rows.

`dream_write_candidates` lets automation pre-fill the review queue with Dream
suggestions only when `vault automation run --apply` is used. This is enabled
in `balanced` and `autonomous` starter policies, disabled in `conservative`,
and still never promotes candidates into active knowledge. Repeated apply runs
skip an existing Dream candidate with the same `source_ref`, so scheduled jobs
do not keep adding duplicate review items.

`forgetting_write_candidates` works the same way for lifecycle review. When
`--apply` is used, automation can create candidate-only suggestions for expired
memories that were not archived because they are still used or protected by
scope/sensitivity policy. These candidates use `memory_type:
forgetting_suggestion`, never delete rows, and never change permissions.

`protect_used_expired` keeps automation from archiving memories that are expired
but still have retrieval or citation usage. Those rows appear in
`usage_review.expired_but_used` and `human_review.items` so the user can decide
whether the TTL is wrong, the memory should be summarized, or the source should
move to a longer-lived layer.

`protected_scopes` and `protected_sensitivities` keep private or sensitive
memory out of routine lifecycle automation. By default, expired private,
high-sensitivity, and restricted rows appear in `usage_review.expired_protected`
and the run `action_ledger` with `status: skipped_policy`. They stay active even
when `vault automation run --apply` is used.

## Reports, Ledgers, and Diffs

Every automation run can write a JSON report under `reports/automation/`. The
important review fields are:

- `dry_run_diff`: count of rows that would be archived, were archived, or were
  skipped by usage/policy. It also states that automation performs no hard
  delete, no candidate promotion, and no permission changes.
- `action_ledger`: per-memory entries with `knowledge_id`, operation, before
  status, after status, risk, and reason.
- `dream.summary`: counts Dream findings, candidate suggestions,
  `candidates_written`, and `candidates_skipped_existing`.
- `forgetting`: counts candidate-only forgetting suggestions written or skipped
  because an equivalent review candidate already exists.
- `usage_review`: operator-facing buckets such as archiveable expired rows,
  expired-but-used rows, protected expired rows, and top-used memories.
- `human_review`: whether a person should inspect the run before stronger
  autonomy.
- `memory_feedback_events`: candidate outcome events used by
  `vault automation eval` to show which suggestion sources are earning trust
  over time. These events are audit data, not direct policy changes. They can
  be written by candidate promotion, `vault candidate-review`, or MCP
  `vault_memory_review`.
- `learning_policy`: bounded priority hints derived from feedback events. Use
  it to guide future Dream or curator ordering, not to auto-promote or bypass
  access policy.
- `dream.learning_policy`: whether the Dream run loaded a learning policy and
  how many candidate suggestions received a matching rule. Automation report
  summaries expose the same status so scheduled agents can monitor it cheaply.
- `consolidation_suggestion`: Dream can write this candidate type for duplicate
  groups. It asks for a reviewed merge/archive decision and never changes
  active knowledge by itself.

This gives agents a small, structured handoff: they can summarize the report,
but the source of truth remains the machine-readable ledger.
Use `vault automation report --latest --detail` when a new agent needs to
continue after a scheduled maintenance run.

## Scheduled Use

For cron, LaunchAgent, n8n, or agent scheduler jobs, generate reviewed
templates during agent setup:

```bash
vault setup-agent \
  --non-interactive \
  --agent automation-agent \
  --scope shared \
  --agent-project-dir /path/to/project \
  --features core,mcp,memory_agents \
  --automation-schedule all \
  --automation-mode balanced
```

This writes `agent-install/memory-automation.cron`,
`agent-install/com.zycaskevin.vault-for-llm.memory-automation.plist`,
`agent-install/n8n-memory-automation.workflow.json`, and
`agent-install/README-memory-automation.md`.

Generated schedules default to `vault automation cycle`, which evaluates
reviewed candidate outcomes, writes `reports/automation/learning_policy.json`,
and then runs normal policy-based automation. After a successful scheduled run,
the generated cron, LaunchAgent, and n8n templates also run
`vault automation inbox --write-handoff`, producing
`reports/automation/inbox-latest.json` as the next-agent handoff. Use
`--automation-command run` when you want a maintenance-only schedule without the
feedback-learning phase.

The scheduled command should stay explicit about the target vault:

```bash
vault automation cycle --project-dir /path/to/project --pretty
vault automation inbox --project-dir /path/to/project --write-handoff --pretty
```

Use `--apply` only after the user has reviewed `automation_policy.yaml` and
accepted reversible archival for expired rows. Keep the Python virtualenv and
project directory in stable paths, not `/tmp`.
