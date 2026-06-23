# Dream Workflow

`vault dream` is the report-first memory curation workflow for Vault-for-LLM. It helps operators find stale, duplicated, weak, or poorly described knowledge without letting the agent silently rewrite the vault.

## Design rule

```text
Dream reports first. It does not delete, merge, or overwrite knowledge automatically.
```

Default mode is safe:

```bash
vault dream --mode report --limit 50 --write-report
```

This writes a Markdown report under:

```text
reports/dream/YYYY-MM-DD-HHMMSS.md
```

## Checks

| Check | Purpose |
|---|---|
| `freshness` | Find entries with low freshness or missing verification metadata |
| `dedup` | Find repeated titles or repeated content hashes |
| `convergence` | Find entries with unknown/weak convergence state |
| `metadata` | Find missing tags, weak category, low trust, or empty content |
| `orphans` | Find document-map rows whose parent knowledge entry is missing |

Run a subset:

```bash
vault dream --checks freshness dedup metadata --limit 20 --write-report
```

## Candidate suggestions

Dream also turns findings into reviewable memory-candidate suggestions. By default those suggestions only appear in the JSON payload and Markdown report:

```json
{
  "candidate_suggestions": [
    {
      "kind": "metadata_review",
      "title": "Review weak metadata: Deployment SOP",
      "source": "dream",
      "source_ref": "knowledge:42",
      "memory_type": "dream_suggestion"
    }
  ]
}
```

To write those suggestions into the candidate queue, opt in explicitly:

```bash
vault dream --mode report --checks metadata dedup freshness --write-candidates --write-report
```

This still does not promote anything into active knowledge. The resulting candidates must pass the same privacy, duplicate, metadata, and quality gates as normal `vault remember` proposals, then be reviewed with:

```bash
vault candidates
vault promote <candidate_id> --confirm
```

## MCP usage

Compatible agents can call:

```json
{
  "tool": "vault_dream_run",
  "arguments": {
    "mode": "report",
    "checks": ["freshness", "dedup", "convergence", "metadata", "orphans"],
    "limit": 50,
    "write_report": true,
    "write_candidates": false,
    "backup": true
  }
}
```

Return shape:

```json
{
  "report_path": "reports/dream/2026-06-12-120000.md",
  "summary": {
    "stale": 3,
    "duplicates": 1,
    "weak": 4,
    "metadata": 5,
    "orphans": 0,
    "candidate_suggestions": 4,
    "candidates_written": 0,
    "actions_applied": 0
  },
  "next_action": "Review report, then rerun with apply_safe if desired"
}
```

## `apply_safe`

`apply_safe` is intentionally conservative. It creates a backup by default and applies only low-risk metadata actions from the report plan, such as adding a `needs-review` tag to entries with empty tags or replacing the catch-all `general` category with `review`. It must never silently delete, merge, rewrite content, or overwrite high-trust knowledge.

```bash
vault dream --mode apply_safe --write-report
```

The JSON output includes `proposed_actions`, `applied_actions`, `backup_path`, and `plan_path`. If the result needs to be reverted, restore the emitted backup:

```bash
vault db restore /path/to/backup.db --db-path ./vault.db --force --pretty
```

## Scheduling

For a simple local cron/systemd job, schedule the report-only command:

```bash
cd /path/to/vault-project
vault dream --mode report --limit 50 --write-report
```

For Hermes cron, use a self-contained prompt or script that runs the same command and reports the new `reports/dream/*.md` path. Do not auto-promote or auto-delete from a scheduled job until reports have been reviewed.

If you want an agent to pre-fill the review queue, schedule `--write-candidates` only after you are comfortable with the report quality. This creates candidates, not active knowledge, and keeps human review available without making humans do every sorting step by hand.

## Rollback

Before any future `apply_safe` action that mutates active knowledge, create a verified DB backup:

```bash
vault db backup --verify
```

Restore path:

```bash
vault db restore /path/to/backup.db --force
```

See [`db_backup_restore.md`](db_backup_restore.md) for the backup/restore contract.
