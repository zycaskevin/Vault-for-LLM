# Contributing

Thanks for helping improve Vault-for-LLM.

## Install Paths

Vault keeps two supported local development paths:

- `pip` / `venv`: the common Python path and the main public install model.
- `uv`: the reproducible source-development path for maintainers, CI smoke
  checks, and coding agents.

Public users should still install releases with `pip install vault-for-llm`.
Use `uv` when working from a source checkout.

## pip Development Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,mcp]"
pytest -q
```

## uv Development Setup

```bash
uv sync --extra dev --extra mcp
uv run pytest -q
```

The checked-in `uv.lock` makes this path reproducible for agents and humans.

## Lockfile Policy

- Commit `uv.lock`.
- Run `uv lock` whenever `pyproject.toml` dependencies or optional extras
  change.
- Run `uv lock --check` before opening a PR that changes dependencies.
- Do not require `uv` for normal package users; keep `pip install
  vault-for-llm` working.
- Do not use the semantic extra in default CI smoke checks unless the PR is
  specifically testing semantic dependencies, because that stack is much
  heavier than core and MCP development.

## Useful Checks

```bash
pytest -q
python -m compileall -q vault scripts tests
python scripts/module_size_gate.py
uv lock --check
uv run python -m pytest -q tests/test_lite.py tests/test_cli_project_dir.py
```
