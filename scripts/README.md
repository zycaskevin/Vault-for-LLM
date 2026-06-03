# Scripts Guide

These scripts are **source-checkout helpers** for maintainers and advanced users. The stable first-user workflow remains the installed `vault` CLI:

```bash
vault init
vault add "Title" --content "..."
vault compile
vault search "query"
```

Run scripts from the repository root unless a script documents another root option.

## Repository governance / public release

| Script | Purpose | Safe default |
|---|---|---|
| `public_pr_gate.py` | Scan the actual PR diff for public-boundary risks: private-only paths, runtime DBs/reports, local paths, secret-looking assignments, renamed paths, deleted/context lines, and unexpectedly large diffs. | Read-only |
| `artifact_audit.py` | Report generated caches, review-only runtime folders, and archive candidates. | Read-only |
| `artifact_cleanup.py` | Delete only reproducible cache artifacts. | Dry-run; deletion requires `--execute --safe-only` |
| `check_release_parity.py` | Verify release tag, `pyproject.toml`, `vault.__version__`, and `CHANGELOG.md` parity. | Read-only |

Examples:

```bash
python scripts/public_pr_gate.py --base origin/main --head HEAD
python scripts/artifact_audit.py --root .
python scripts/artifact_cleanup.py --root .              # dry-run
python scripts/artifact_cleanup.py --root . --execute --safe-only
python scripts/check_release_parity.py --tag v0.4.3
```

## Local knowledge-quality helpers

| Script | Purpose | Notes |
|---|---|---|
| `convergence_check.py` | Preview or apply convergence/completeness scoring. | Use `--apply` only after reviewing output. |
| `cross_validate.py` | Cross-model verification for extracted claims. | Optional model/API dependencies may be required. |
| `freshness_check.py` | Detect stale knowledge and review schedules. | Use `--apply` only after reviewing output. |
| `deduplicate_semantic.py` | Detect or merge similar entries. | Merge requires `--merge`; reports are runtime artifacts ignored by git. |
| `trust_adjustment.py` | Adjust trust based on local usage/quality signals. | Default is preview; `trust_report.json` is ignored by git. |
| `auto_backlink.py` | Insert internal links between Markdown entries. | Use `--dry-run` before modifying files. |
| `generate_index.py` | Generate an `INDEX.md` from `raw/` and `compiled/`. | Writes output only when invoked normally; `--help` is read-only. |
| `manual_review.py` | Inspect/approve/reject/fix local review queue items. | Mutating actions require explicit IDs. |
| `suggest_new_knowledge.py` | Suggest possible gaps in the local knowledge base. | Read-only. |

Examples:

```bash
python scripts/convergence_check.py --limit 10
python scripts/deduplicate_semantic.py --threshold 0.85
python scripts/trust_adjustment.py --min 0.8
python scripts/auto_backlink.py --dry-run
python scripts/generate_index.py --output INDEX.md
```

## Optional remote sync helpers

These scripts are for users who intentionally configure Supabase as an optional sync/read target. Core Vault-for-LLM usage does **not** require Supabase.

| Script | Purpose | Required configuration |
|---|---|---|
| `sync_to_supabase.py` | Sync local knowledge, skills, Document Map, or health snapshots. | `SUPABASE_URL` plus `SUPABASE_SERVICE_KEY` or `SUPABASE_ANON_KEY` |
| `sync_graph_to_supabase.py` | Sync inferred graph entities/edges to optional remote tables. | Supabase credentials and table env vars as needed |
| `fix_ek_links.py` | Repair missing remote graph entity-knowledge links. | Supabase credentials and table env vars as needed |
| `daily_knowledge_sync.py` | Maintenance wrapper for local compile/dedup/trust/review steps. | `vault` CLI on `PATH`; optional `VAULT_DIR` |

Examples:

```bash
python scripts/sync_to_supabase.py --document-map
python scripts/sync_graph_to_supabase.py
VAULT_DIR=/path/to/project python scripts/daily_knowledge_sync.py
```

## Safety notes

- Runtime reports such as `duplicate_report.json`, `trust_report.json`, and other `*_report.json` files are ignored by git.
- Do not run remote sync scripts unless you intentionally configured credentials and table names.
- Before pushing a public branch, run the public-boundary gate against the final diff:

```bash
git diff origin/main..HEAD | python scripts/public_pr_gate.py --stdin
```
