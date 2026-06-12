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
    "actions_applied": 0
  },
  "next_action": "Review report, then rerun with apply_safe if desired"
}
```

## `apply_safe`

`apply_safe` is intentionally conservative. It may create a backup and run future low-risk actions, but it must never silently delete, merge, or overwrite high-trust knowledge.

```bash
vault dream --mode apply_safe --write-report
```

Current implementation keeps `actions_applied=0`; it is a safe extension point.

## Scheduling

For a simple local cron/systemd job, schedule the report-only command:

```bash
cd /path/to/vault-project
vault dream --mode report --limit 50 --write-report
```

For Hermes cron, use a self-contained prompt or script that runs the same command and reports the new `reports/dream/*.md` path. Do not auto-promote or auto-delete from a scheduled job until reports have been reviewed.

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
