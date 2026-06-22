# CHANGELOG

## [0.6.30] - 2026-06-22

### Added

- Added the `vault_memory_candidates` MCP review tool so MCP agents can inspect pending memory candidates without reading SQLite internals or dumping full raw content by default.

## [0.6.29] - 2026-06-22

### Added

- Added memory governance guidance for L0-L3, user profile/persona memory, dedicated profile/dream-forgetting agents, multi-agent sharing metadata, Supabase RLS boundaries, and Obsidian frontmatter sync.
- Added a long-term vision document for user-owned lifelong memory across agent families, devices, robots, sync layers, and model providers.
- Added Progressive Memory Disclosure as a design principle for keeping lifelong memory efficient, reviewable, permissioned, and source-grounded.
- Added `setup-agent` support for `memory_agents`, generating Profile / Dream / Forgetting agent guidance without auto-promoting, scheduling, deleting, or installing models.
- Added `vault candidates` so agents can review pending memory candidates without reading SQLite internals or dumping full raw content by default.

## [0.6.28] - 2026-06-22

### Added

- Added `vault setup-agent --language en|zh-Hant|zh-CN` so generated installer output and Supabase setup guides can match the user's language.
- Added interactive setup language selection for manual CLI installs; non-interactive agent installs can pass `--language` and otherwise keep the default.
- Added `vault setup-agent --supabase-setup none|simple|advanced` to generate a guided Supabase connection checklist without forcing RLS complexity into the default path.
- Added `docs/supabase_setup.md` with simple sync steps, minimal Supabase schema, and advanced RLS/multi-agent guidance.

### Changed

- Supabase next steps now explain when to skip Supabase and when it is useful for cross-host/team/shared-memory sync.

## [0.6.27] - 2026-06-22

### Fixed

- Ensured Supabase knowledge and skill sync payloads always include a non-empty `content_hash`, even when older local rows have a missing hash.
- Added `--db` support to `scripts.sync_to_supabase` so scheduled jobs can target a stable `vault.db` path.
- Added optional daily Supabase sync template generation to `vault setup-agent` via `--supabase-sync`.
- Added agent setup warnings when Vault is running from a temporary `/tmp/...` Python environment.
- Passed `fix_mistral_regex=True` when loading ONNX tokenizer models to address tokenizer warning noise from recent Transformers versions.

## [0.6.26] - 2026-06-22

### Fixed

#### Agent Installer Optional Dependencies

- Added `vault setup-agent --install-optional-deps` so non-interactive agents can install selected optional Python dependencies instead of only receiving next-step instructions.
- Added `vault setup-agent --install-embedding-model zh|en|mix` so semantic installs can download and configure a local ONNX embedding model during setup.
- Updated interactive setup so it asks whether to install selected optional dependencies now, and asks whether semantic search should configure a local embedding model.
- Updated README variants, CLI reference, agent install runbook, and `agent_manifest.json` so Hermes/Nancy, Codex, OpenClaw, Claude Code, OpenCode, n8n, and other agents can distinguish enabling a feature from actually installing its dependencies.
- Clarified that `/tmp/...` paths are disposable test workspaces, not stable Vault install locations or long-lived shared memory paths.

## [0.6.25] - 2026-06-22

### Fixed

#### Agent Installer Follow-up

- Made interactive `vault setup-agent` ask separate yes/no questions for MCP, semantic search, Supabase sync, Headroom context compression, and dev/benchmark dependencies instead of relying on one optional-features CSV prompt.
- Fixed `vault setup-agent --project-dir ...` / `vault install-agent --project-dir ...` so the global project directory is used as the installer target and can be created when missing.
- Added guarded `vault remove <id> --confirm` and `vault delete <id> --confirm` commands for deleting reviewed knowledge entries by ID.
- Cleaned up related semantic vectors, Document Map rows, lint cache, graph links, FTS rows, and sqlite-vec rows when knowledge entries are removed.
- Updated agent-facing README, runbook, and manifest guidance so agents explicitly ask about Supabase, semantic search, Headroom, and dev/benchmark extras before installing them.

## [0.6.24] - 2026-06-21

### Added

- Added `vault setup-agent` / `vault install-agent`, an interactive and non-interactive agent installer that asks for database scope, optional features, Obsidian import, and sync-template generation.
- Added Obsidian automatic sync templates for cron, macOS LaunchAgent, and n8n Execute Command workflows.
- Added `vault_obsidian_import` for MCP maintenance/full profiles and the OpenClaw adapter, keeping daily `core` MCP tool schema small.
- Added a short v0.6.24 announcement draft under `docs/announcements/`.

## [0.6.23] - 2026-06-21

### Added

#### Agent Runtime Integrations
- Added MCP tool profiles so token-sensitive agents can start `vault-mcp` with a small `core` tool surface instead of the full compatibility set.
- Slimmed the README command surface and moved the broader command list to `docs/cli_reference.md`.
- Added `vault import obsidian` so existing Obsidian Markdown vaults can be imported into `raw/obsidian/`, re-run idempotently, and optionally compiled into `vault.db`.
- Documented Obsidian import/sync for README readers and agent installers, including dry-run first use, default export-folder exclusions, and cron/LaunchAgent/n8n scheduling.
- Added an agent integration guide documenting how to use Vault-for-LLM from Hermes Agent/Nancy, OpenClaw, n8n, Codex, OpenCode, Claude Code, generic MCP-compatible agents, and shell-based automation.
- Added an OpenClaw adapter under `integrations/openclaw/` with a portable `vault-openclaw` wrapper, OpenClaw skill instructions, plugin metadata, manual tools, install/verify scripts, and config snippets.
- Updated README variants to make CLI/MCP portability a first-class product message instead of presenting Vault as tied to one agent runtime.
- Documented shared/private/temporary Vault project scope so agent installs can choose whether to share one `vault.db` or use isolated databases.
- Added `AGENTS.md` and `agent_manifest.json` so agent-driven installers can read database scope, safety, runtime, and validation rules without scraping README prose.
- Added optional feature prompting guidance for agent installers, including core, MCP, semantic, Supabase, and dev/benchmark profiles.
- Added Obsidian as a first-class agent install prompt: ask for an existing vault path, run dry-run, perform the first import after confirmation, then ask whether to schedule automatic sync.
- Added CLI-wide `--project-dir` normalization so agent installers can pass the Vault project directory before or after subcommands.
- Added `vault-for-llm[supabase]` as an optional dependency group for remote sync/read path setup.
- Clarified README Supabase positioning for cross-host agent memory sharing while keeping local SQLite as the source of truth.

#### Agent Memory Benchmarking
- Added a README evidence snapshot for project onboarding, candidate-first memory, and external retrieval probes with explicit caveats.
- Added a reproducible repository-doc agent onboarding benchmark fixture with 28 source-aware QA cases.
- Added `scripts/build_agent_onboarding_vault.py` to build a temporary benchmark Vault from README/docs source-of-truth files instead of committing runtime databases.
- Documented how to run exported Codex/Hermes-style sessions against the governed Vault benchmark while keeping private session exports and reports outside git.
- Validated the current local Codex-session comparison path at 28 tasks: session transcript baseline hit rate `7/28`, Vault top-k/source/read-range guidance rates `28/28`.
- Validated a private Hermes/Nancy transcript export at 28 tasks: session transcript baseline hit rate `3/28`, Vault top-k/source/read-range guidance rates `28/28`, and candidate active delta before promotion `0`.

#### License
- Relicensed the source tree from MIT to Apache-2.0 now that contributions are still controlled by the project maintainers, adding explicit patent-license terms for downstream agent-infrastructure users.

## [0.6.22] - 2026-06-20

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
