# CHANGELOG

## [0.6.53] - 2026-06-23

### Added

- Added Dream candidate suggestions so memory-cleanup reports can propose reviewable `memory_candidate` rows instead of only producing static findings.
- Added policy-gated Dream candidate writes with `dream_write_candidates`; candidate writes require `vault automation run --apply` and stay disabled in conservative mode.
- Added forgetting review candidates with `forgetting_write_candidates` so expired but still-used or policy-protected memories can enter a review queue without being archived automatically.

### Changed

- Updated automation reports and CLI summaries with Dream and forgetting candidate counts so agents can explain what was suggested, written, skipped, and left for human review.
- De-duplicated automation-generated candidates by `source_ref` so repeated scheduled runs do not flood the candidate queue.

## [0.6.52] - 2026-06-23

### Added

- Added `action_ledger` and `dry_run_diff` to `vault automation run` reports so agents and operators can review exactly which memories would change, which changed, and why.
- Added default protected-memory skips for automation TTL archival: `scope: private` and `sensitivity: high|restricted` stay active and are reported as `skipped_policy`, even when `--apply` is used.
- Added human-readable CLI output for automation diff and ledger summaries.

### Changed

- Updated automation documentation and the public claim matrix to describe report ledgers, dry-run diffs, and policy-protected lifecycle skips.

## [0.6.51] - 2026-06-23

### Added

- Added `vault setup-agent --automation-schedule cron|launchagent|n8n|all` so agent installers can generate report-first memory automation schedules.
- Added `--automation-mode`, `--automation-interval-minutes`, and explicit opt-in `--automation-apply` controls for scheduled automation templates.
- Added cron, macOS LaunchAgent, n8n workflow, and `README-memory-automation.md` templates for policy-based memory maintenance.

### Fixed

- Fixed explicit `--project-dir` handling so commands do not climb to a parent vault when the requested project directory is empty.
- Added the practical MCP tool reference to the docs set and onboarding benchmark fixture.

## [0.6.50] - 2026-06-23

### Added

- Added a small saturated usage boost to the lightweight reranker so frequently useful memories can break close relevance ties without overriding source relevance, trust, freshness, or access policy.
- Added usage-aware automation review output that separates expired memories into low-risk archive candidates and expired-but-still-used items that need TTL review.
- Added human-readable `vault automation plan/run` usage review summaries, including `skipped_used` counts for protected expired memories.

## [0.6.49] - 2026-06-23

### Added

- Added `vault automation plan/run/report/doctor` as a policy-based memory maintenance layer.
- Added `automation_policy.yaml` defaults for `conservative`, `balanced`, and `autonomous` modes so agents can do routine cleanup while humans keep policy ownership.
- Added report-first automation that collects usage stats, previews or applies reversible TTL archival, runs Dream reports, and writes `reports/automation/*.json`.

## [0.6.48] - 2026-06-23

### Added

- Added optional OpenAI, Cohere, and Voyage embedding providers for semantic and hybrid search without requiring local ONNX model downloads.
- Added API-provider parsing, retry telemetry, normalization, and fail-closed API-key checks without adding SDK dependencies to the base package.
- Documented local-first and remote embedding configuration paths in the semantic search guide.

## [0.6.47] - 2026-06-23

### Added

- Added incremental semantic rebuild support with `vault semantic rebuild --changed-only`, so missing or stale `semantic_vectors` can be refreshed without rebuilding the whole vault.
- Added `--changed-only` support to semantic smoke/startup/daemon rebuild paths, plus `--limit` / `--semantic-limit` controls for bounded maintenance runs.
- Reported `changed_only`, `candidate_rows`, and `skipped_rows` in semantic rebuild payloads so agents can tell whether an index pass did real work.

## [0.6.46] - 2026-06-23

### Added

- Added memory usage counters on active knowledge rows: `access_count`, `citation_count`, and `last_accessed_at`.
- Added `vault usage stats` and `vault usage archive-expired` so operators and maintenance agents can inspect retrieval usage and archive expired memories without deleting them.
- Added schema v9 archive metadata (`status`, `archived_at`) and hid archived memories from normal local search and list results.

## [0.6.45] - 2026-06-23

### Security

- Hardened remote Supabase Document Map and `read_range` MCP paths so they must pass through guarded read-policy RPCs before returning nodes, claims, or raw content.
- Added `vault_get_readable`, `vault_nodes_readable`, `vault_claims_readable`, and `vault_content_readable` to the advanced Supabase policy template.
- Revoked direct anon/authenticated reads from synced Document Map node and claim tables in the Supabase policy template.
- Preserved remote `agent_id`, `include_private`, and `max_sensitivity` policy arguments across search -> map -> read tool guidance.

## [0.6.44] - 2026-06-23

### Fixed

- Fixed generated Supabase LaunchAgent templates so stdout/stderr logs use `supabase-sync.log` and `supabase-sync.err.log` instead of Obsidian log filenames.
- Added regression coverage for Supabase LaunchAgent log paths.

## [0.6.43] - 2026-06-22

### Fixed

- Improved the interactive `vault setup-agent` first-run flow so a core+MCP install no longer asks to install optional Python dependencies when no optional dependency feature was selected.
- Added regression coverage for the core+MCP interactive path.

## [0.6.42] - 2026-06-22

### Changed

- Reworked the agent install runbook into a smaller first-run flow with optional features introduced only when they match the user's goal.
- Refined the Supabase setup guide so local-first use, simple sync, remote readers, and advanced RLS are easier to choose between.
- Kept multi-agent sharing, private profile memory, Headroom, Obsidian, and memory maintenance guidance in focused docs rather than the README.

## [0.6.41] - 2026-06-22

### Changed

- Reworked the English and Traditional Chinese README files into shorter product entry points with warmer, clearer wording.
- Moved detailed workflows toward focused docs links instead of keeping every installer, integration, benchmark, and roadmap detail in the README.
- Kept the core install, quickstart, agent flow, governance model, integration map, and benchmark caveats visible on the first public page.

## [0.6.40] - 2026-06-22

### Added

- Added `vault setup-agent --stable-venv PATH` and `--write-stable-venv-script` to generate a reviewed long-lived Python virtualenv bootstrap script.
- Added `agent-install/setup-stable-venv.sh` and `README-stable-venv.md` templates so scheduled jobs, MCP commands, and Supabase sync can move off disposable `/tmp` virtualenvs.
- Documented stable venv setup in README variants, the agent install runbook, and `agent_manifest.json`.

## [0.6.39] - 2026-06-22

### Fixed

- Hardened Supabase sync payloads so blank `content_hash` values are treated as missing and replaced with a deterministic SHA256 hash before update or insert.
- Updated agent install prompts, README examples, and `agent_manifest.json` to ask for stable long-lived project and Python virtualenv paths instead of using `/tmp`.
- Added release notes and tests covering blank hash regeneration for Supabase NOT NULL schemas.

## [0.6.38] - 2026-06-22

### Fixed

- Sanitized public docs, release notes, CLI help examples, manifest examples, and tests so multi-agent examples use generic role IDs instead of private/local agent names.
- Replaced private transcript labels with generic Hermes profile wording while keeping benchmark numbers and reproducibility notes intact.
- Re-ran repository privacy scans for private names, local user paths, emails, tokens, and credential-like patterns; remaining credential-pattern hits are code/test placeholders rather than committed secrets.

## [0.6.37] - 2026-06-22

### Added

- Added `vault setup-agent --agent-roster` to generate a multi-agent roster, access matrix, per-agent env examples, and setup commands.
- Added `vault setup-agent --validation-pack remote|n8n|coze|all` to generate live validation scripts and checklists for real Supabase/n8n/Coze deployments.
- Documented the roster and validation workflow across README variants, CLI reference, agent install runbook, integration guide, memory governance, and `agent_manifest.json`.
- Added tests proving generated rosters, access matrices, validation scripts, and hosted-reader checklists are written correctly.

## [0.6.36] - 2026-06-22

### Added

- Added `vault remote smoke` to verify Supabase remote reader credentials and the `vault_search_readable` RPC before wiring hosted agents.
- Added `vault setup-agent --remote-reader shell|n8n|coze|all` to generate shell, n8n, and Coze remote reader templates.
- Added remote reader installer artifacts: `README-remote-reader.md`, `remote-reader-smoke.sh`, `n8n-remote-reader.workflow.json`, `coze-supabase-vault-openapi.json`, and `remote-reader.env.example`.
- Documented the productized multi-agent setup path across README variants, agent install runbook, integration guide, Supabase setup, CLI reference, memory governance, and `agent_manifest.json`.

## [0.6.35] - 2026-06-22

### Added

- Added CLI `vault remote search`, `vault remote map`, and `vault remote read` for Supabase read-only remote memory workflows.
- Reused the same `vault_search_readable` RPC and remote Document Map helpers as MCP, so shell/n8n agents can search safe summaries and then request bounded evidence.
- Documented the CLI remote flow in README variants, CLI reference, and agent integration docs.
- Added tests for CLI remote search/map/read with a fake Supabase client, proving the command path does not require live network access in CI.

## [0.6.34] - 2026-06-22

### Added

- Added MCP `vault_remote_search`, a Supabase read-only search tool that calls the `vault_search_readable` RPC from the advanced Supabase read-policy template.
- Added `vault_remote_search` to the `remote` MCP tool profile so hosted agents can use `vault_remote_search` -> `vault_remote_map_show` -> `vault_remote_read_range`.
- Added tests proving remote search passes agent/sensitivity parameters to the RPC and does not expose `content_raw` in results.
- Updated README, MCP workflow, CLI reference, agent integration docs, and `agent_manifest.json` with the remote search flow.

## [0.6.33] - 2026-06-22

### Added

- Added `docs/supabase_read_policy.sql`, a ready-to-paste advanced Supabase read-policy template for hosted agents, Coze, n8n, and cross-host readers.
- Added `vault_search_readable`, a read-only Supabase RPC shape that applies `scope`, `sensitivity`, `owner_agent`, `allowed_agents`, and `expires_at` filtering while returning safe metadata and summaries only.
- Updated `vault setup-agent --supabase-setup advanced` to generate `agent-install/supabase-read-policy.sql` next to the guided Supabase setup document.
- Added tests that keep the generated advanced SQL in sync with the checked-in template and prevent accidental raw full-text exposure in the read-only RPC.

## [0.6.32] - 2026-06-22

### Added

- Added read-side governance filters for local search and MCP reads. Agents can pass `agent_id`, `include_private`, and `max_sensitivity` to `vault search`, `vault_search`, `vault_map_show`, and `vault_read_range`.
- Added shared access-policy helpers so search, map inspection, and bounded reads use the same `scope` / `sensitivity` / `owner_agent` / `allowed_agents` semantics.
- Added tests proving legacy reads remain unchanged without an agent policy, while private/restricted entries are filtered or blocked when an agent policy is supplied.

## [0.6.31] - 2026-06-22

### Added

- Added first-class governance metadata columns to active knowledge and memory candidates: `scope`, `sensitivity`, `owner_agent`, `allowed_agents`, `memory_type`, and `expires_at`.
- Preserved governance metadata through CLI `vault add` / `vault remember`, MCP `vault_add` / `vault_memory_propose`, memory promotion, Markdown compilation, Obsidian import/export, and Supabase sync payloads.
- Added tests for multi-agent memory governance metadata across DB writes, candidate promotion, compiler frontmatter, Obsidian import, and Supabase payloads.

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
- Updated README variants, CLI reference, agent install runbook, and `agent_manifest.json` so Hermes profile, Codex, OpenClaw, Claude Code, OpenCode, n8n, and other agents can distinguish enabling a feature from actually installing its dependencies.
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
- Added an agent integration guide documenting how to use Vault-for-LLM from Hermes Agent, OpenClaw, n8n, Codex, OpenCode, Claude Code, generic MCP-compatible agents, and shell-based automation.
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
- Validated a private Hermes profile transcript export at 28 tasks: session transcript baseline hit rate `3/28`, Vault top-k/source/read-range guidance rates `28/28`, and candidate active delta before promotion `0`.

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
