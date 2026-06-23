# Memory Automation

Vault automation is policy-based. The goal is to let agents do routine memory
maintenance while humans keep ownership of the rules and high-impact changes.

Automation does not hard-delete memory. The first phase is report-first and
reversible:

- collect usage and lifecycle counters
- split expired memories into low-risk archive candidates and used items that
  need TTL review
- preview expired-memory archival
- optionally archive expired memories when policy and `--apply` both allow it
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

Check readiness for scheduled automation:

```bash
vault automation doctor --pretty
```

## Policy

`automation_policy.yaml` controls the automation boundary:

```yaml
mode: balanced
auto_archive_expired: true
protect_used_expired: true
auto_apply_safe_metadata: false
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

`protect_used_expired` keeps automation from archiving memories that are expired
but still have retrieval or citation usage. Those rows appear in
`usage_review.expired_but_used` and `human_review.items` so the user can decide
whether the TTL is wrong, the memory should be summarized, or the source should
move to a longer-lived layer.

## Scheduled Use

For cron, LaunchAgent, n8n, or agent scheduler jobs, prefer:

```bash
vault automation run --project-dir /path/to/project --pretty
```

Use `--apply` only after the user has reviewed `automation_policy.yaml` and
accepted reversible archival for expired rows. Keep the Python virtualenv and
project directory in stable paths, not `/tmp`.
