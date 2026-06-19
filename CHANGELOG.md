# CHANGELOG

## [0.6.21] - 2026-06-18

### Fixed

#### Security & Release Pipeline
- **PyPI Trusted Publishing migration** — Switched from long-lived API Token to OIDC-based Trusted Publishing, removing `PYPI_API_TOKEN` secret dependency from publish workflow.
- **MCP `vault_search` parameter support** — Added missing `include_snippet`, `normalize_scores`, `offset`, and `fields` parameters to MCP schema and handler.
- **`update_knowledge` field validation** — Added field name whitelist to prevent potential SQL injection via dynamic column names.

#### P0: Legacy System Cleanup
- **`pyproject.toml` package name** — Renamed from `guardrails-knowledge` to `vault-for-llm`, updated version to `0.6.21`.
- **README/docs command cleanup** — Replaced legacy Guardrails CLI commands with Vault-for-LLM equivalents where public setup instructions are maintained.
- **README/docs placeholder cleanup** — Removed stale `YOUR_USERNAME` placeholders and updated package names/environment variable examples in public setup docs.
- **`duplicate_report.json` privacy leak** — Removed from Git tracking via `git rm --cached`, added to `.gitignore`, created template file.

#### Compatibility
- **`optimum` v2.x `__version__` removal** — Added `try/except` with `importlib.metadata` fallback in `vault/cli.py` for compatibility with `optimum` v2.x which removed the module-level `__version__` attribute.
