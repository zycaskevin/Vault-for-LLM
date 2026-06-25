# Repository Governance: Public Boundary + Artifact Hygiene

This repository can support both internal/private workflows and public/open-source releases. The rule is simple: **functionality may be shared, artifacts are not interchangeable**.

## 1. Public / internal PR boundary

Before pushing or opening a public PR, run a fail-closed public-boundary gate.

### Required public PR checklist

1. Verify the target repository URL and visibility. Do not infer safety from the remote name.
2. Build the public branch from the latest public base, usually `origin/main`.
3. Port internal modules and docs into public package names and public-safe language.
4. Exclude internal-only artifacts by default:
   - `PROGRESS.md`
   - `AUDIT_REPORT.md`
   - private agent runtime directories
   - local tool runtime directories
   - handoffs / worklogs
   - runtime DBs and generated reports
   - raw private notes and compiled private knowledge
   - local absolute paths, private platform IDs, chat/user IDs
5. Scan the final PR diff, not only the working tree.
6. Ask for an independent review focused on privacy/public-boundary leakage.

### Public PR gate command

```bash
python scripts/public_pr_gate.py --base origin/main --head HEAD
```

For a cleanup PR that only removes internal-only files or renames them out of forbidden paths already present in the base branch, use the explicit cleanup flag:

```bash
python scripts/public_pr_gate.py --base origin/main --head HEAD --allow-cleanup-deletions
```

For CI or machine-readable output:

```bash
python scripts/public_pr_gate.py --base origin/main --head HEAD --json
```

To scan a prepared diff:

```bash
git diff origin/main..HEAD | python scripts/public_pr_gate.py --stdin
```

If the gate fails, do not push/open the public PR. If a public PR was already opened and later found to contain private context, close the PR, delete the remote branch, and rebuild a clean public-safe branch from the public base.

## 2. Post-development artifact hygiene

After substantial agent/development work, run an artifact hygiene pass before commit/push handoff.

### Audit first

```bash
python scripts/artifact_audit.py --root .
```

JSON mode:

```bash
python scripts/artifact_audit.py --root . --json
```

### Cleanup dry-run

```bash
python scripts/artifact_cleanup.py --root . --json
```

The cleanup command is dry-run by default. It reports:

- `would_delete`: reproducible caches/build outputs that are safe to delete.
- `needs_review`: large/tool runtime folders that require human approval first.
- `archive_candidates`: handoffs/reports that may be worth moving to a private runtime archive.

### Safe-only cleanup

```bash
python scripts/artifact_cleanup.py --root . --execute --safe-only
```

This deletes only safe generated artifacts such as:

- `__pycache__/`
- `.pytest_cache/`
- `.ruff_cache/`
- `.mypy_cache/`
- `*.egg-info/`
- coverage outputs
- `graphify-out/cache/`

Generic `build/` and `dist/` directories are review-only by default because some projects use those names for source-of-truth or checked-in fixtures.

It does **not** delete review-only large artifacts such as `.opencode/`, generic `build/` / `dist/`, or full `graphify-out/` directories.

## 3. Discussion record rule

After any substantial product, architecture, automation, security, or memory-governance discussion, write the conclusion into a repository document before starting the next implementation pass.

This is a development rule, not a nice-to-have. Chat history is not a stable source of truth. If a decision should shape future code, installer behavior, agent workflow, security policy, benchmark interpretation, or roadmap direction, it must be captured in a public-safe document first.

The record should include:

- the decision or principle
- the reason it matters
- the intended product behavior
- the boundary or safety rule
- follow-up implementation tasks
- anything explicitly deferred

Good destinations include:

- `docs/decision_records/` for product and architecture decisions
- `docs/automation.md` for memory automation behavior
- `docs/memory_governance.md` for memory layering and access rules
- `docs/repo_governance.md` for development process rules

Do not include private names, private conversation details, secrets, local-only paths, raw transcript content, or personal agent lore in public decision records. Use role-based language such as "personal companion agent", "coding agent", "project agent", or "remote agent".

## 4. Git staging rule

Do not use `git add .` in a dirty repo with runtime artifacts. Stage by allowlist:

```bash
git add -- scripts/artifact_audit.py scripts/artifact_cleanup.py scripts/public_pr_gate.py tests/test_repo_hygiene_tools.py docs/repo_governance.md
```

Before commit:

```bash
git status --short --untracked-files=all
git diff --cached --stat
git diff --cached --check
python -m pytest tests/test_repo_hygiene_tools.py -q
```

## 5. Module-size rule

Large modules hide security and behavior changes. Before adding major logic to an existing large module, prefer extracting a focused helper module with tests.

The CI module-size gate is baseline-based:

- New `vault/*.py` modules must stay under the default line limit.
- Existing oversized modules are allowed only up to their recorded baseline.
- If an oversized module grows, split code out or update the baseline with an explicit decision record explaining why the growth is temporary and how it will be paid down.

Run locally:

```bash
python scripts/module_size_gate.py
```

## 6. Design principle

The tools are intentionally conservative:

- Audit is read-only.
- Cleanup defaults to dry-run.
- Execute mode requires `--safe-only`.
- Public PR gate fails closed when the diff is large or contains internal-only files/strings.
- Module-size gate fails closed when oversized files grow beyond their reviewed baseline.
