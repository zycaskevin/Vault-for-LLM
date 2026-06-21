# CHANGELOG

## [0.6.22] - 2026-06-20

### Added

#### Agent Runtime Integrations
- Added an agent integration guide documenting how to use Vault-for-LLM from Hermes Agent/Nancy, OpenClaw, n8n, Codex, Claude Code, generic MCP-compatible agents, and shell-based automation.
- Added an OpenClaw adapter under `integrations/openclaw/` with a portable `vault-openclaw` wrapper, OpenClaw skill instructions, plugin metadata, manual tools, install/verify scripts, and config snippets.
- Updated README variants to make CLI/MCP portability a first-class product message instead of presenting Vault as tied to one agent runtime.

#### Agent Memory Benchmarking
- Added a README evidence snapshot for project onboarding, candidate-first memory, and external retrieval probes with explicit caveats.
- Added a reproducible repository-doc agent onboarding benchmark fixture with 28 source-aware QA cases.
- Added `scripts/build_agent_onboarding_vault.py` to build a temporary benchmark Vault from README/docs source-of-truth files instead of committing runtime databases.
- Documented how to run exported Codex/Hermes-style sessions against the governed Vault benchmark while keeping private session exports and reports outside git.
- Validated the current local Codex-session comparison path at 28 tasks: session transcript baseline hit rate `7/28`, Vault top-k/source/read-range guidance rates `28/28`.
- Validated a private Hermes/Nancy transcript export at 28 tasks: session transcript baseline hit rate `3/28`, Vault top-k/source/read-range guidance rates `28/28`, and candidate active delta before promotion `0`.

#### License
- Relicensed the source tree from MIT to Apache-2.0 now that contributions are still controlled by the project maintainers, adding explicit patent-license terms for downstream agent-infrastructure users.

### Fixed

#### Release Follow-up & Hygiene
- Closed superseded review PRs after the #37-#40 mainline fix series.
- Removed tracked runtime artifacts and ignored future coverage, report, and benchmark outputs.
- Added a CI Search QA regression gate that runs the public benchmark fixture and enforces top-k, MRR, no-result, citation-policy, and result-mode thresholds.

#### Search & Semantic Reliability
- Refreshed sqlite-vec semantic shadow indexes after semantic rebuilds and guarded reads with freshness checks.
- Routed unfiltered semantic search through sqlite-vec while preserving full-scan recall for metadata-filtered semantic queries.
- Expanded semantic Search QA fixtures to cover mode, claim, filtered-recall, cache-key, and no-result behavior.

#### MCP & Embedding Robustness
- Hardened MCP search runtime input handling with limit/offset clamps and a response-field allowlist.
- Honored capped `Retry-After` delays for Ollama embedding retries and exposed retry-after telemetry.

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
