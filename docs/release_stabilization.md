# Release Stabilization Checklist

Vault-for-LLM should merge focused maintenance PRs before publishing the next
external package release. Use this checklist when deciding whether `main` is
ready to become a new release.

## Stabilization Queue

| Area | Done when |
| --- | --- |
| Large-module paydown | Remaining near-limit modules have clear ownership boundaries or a documented reason to stay as-is. |
| README cleanup | README gives the short product path; detailed command and integration guidance lives in focused docs. |
| MCP profile guidance | Agent docs recommend `core` by default, explain when to use `review`, `maintenance`, `remote`, and `full`, and warn about token/tool-surface cost. |
| Automation review UX | `automation brief`, `inbox`, and `handoff` show compact, deduped review cards and hide raw candidate content by default. |
| Temporal memory | Search and docs explain how current, old, superseded, and valid-window facts are handled. |
| Supabase safety | Remote-reader, RLS, and multi-Agent access examples are tested with least-privilege keys and documented as optional advanced paths. |
| Install smoke matrix | Source checkout and clean wheel install both validate CLI, MCP stdio, setup-agent, automation, migration, and key integrations. |

## Required Local Gates

Run these before opening a release PR or tag:

```bash
PYTHONPATH=. pytest -q
PYTHONPATH=. python scripts/module_size_gate.py
PYTHONPATH=. python scripts/public_pr_gate.py
PYTHONPATH=. python scripts/check_release_parity.py
PYTHONPATH=. python scripts/readme_command_smoke.py
PYTHONPATH=. python scripts/history_privacy_scan.py
python -m build
twine check dist/*
```

## Required Install Smoke

The release should be checked from a clean environment, not only from the source
checkout.

Run the install smoke matrix after building the wheel:

```bash
python -m build
python scripts/install_smoke_matrix.py --mode both --wheel dist/vault_for_llm-*.whl
```

The matrix checks both source-checkout and clean wheel-install behavior. It
creates temporary projects and runs:

- `vault --version`
- `vault init`
- `vault add`
- `vault search`
- `vault list`
- `vault map build`
- `vault map read`
- `vault remember`
- `vault candidates`
- `vault capture session`
- `vault automation brief`
- `vault automation cycle --write-workspace`
- `vault automation handoff`
- `vault db status`
- `vault usage stats --json`
- `vault-mcp --tool-profile core`

The MCP step includes actual client calls to:

- `vault_search`
- `vault_read_range`

Use `--mode source` for fast PR validation and `--mode wheel` when checking only
the built package.

If the current Python cannot create a venv on the release machine, pass an
explicit interpreter:

```bash
python scripts/install_smoke_matrix.py --mode wheel \
  --wheel dist/vault_for_llm-*.whl \
  --venv-python python3.11
```

## Optional Advanced Smokes

Run these when the release touches the relevant area:

- `vault setup-agent` generated artifact validation.
- Obsidian import/export dry-run and one real import.
- Supabase remote reader and RLS/RPC validation.
- Semantic index smoke with hash provider and, when available, one real embedding provider.
- Migration smoke against an older `vault.db` fixture.

## Release Cadence Rule

Do not release just because a maintenance PR merged.

Release when the batch is meaningful to external users, fixes a security or
privacy issue, or changes install/runtime behavior in a way users should receive.
