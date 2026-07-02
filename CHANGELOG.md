# CHANGELOG

## [0.7.25] - 2026-07-02

### Added

- Added stable `--json` and `--pretty` output for `vault init`, including
  created directory metadata, `vault.db` path, `.gitignore` path, and
  machine-readable next actions.
- Added stable `--json` and `--pretty` output for `vault compile`, including
  compile stats, dry-run/no-embed flags, and captured compiler progress
  messages without mixing human text into stdout.

### Safety

- `vault compile --json` now captures compiler progress output into the JSON
  payload so agents can parse the command reliably.

### Validation

- Added regression coverage for `vault init --json`, `vault compile --json`,
  and `vault compile --pretty`.

## [0.7.24] - 2026-07-02

### Added

- Added Obsidian as a human-facing Vault review surface: generated `_Inbox`
  notes now include Daily Memory Report, Memory Candidates, Sync Status, and
  Folder Rules Preview.
- Added Obsidian folder-rule support for imports, letting human folder
  structure map into Vault `scope`, `sensitivity`, category, and tags.
- Added Obsidian `[[wikilink]]` preservation and graph import so source notes
  can contribute `obsidian_link` edges after `vault graph build`.
- Added `setup-agent` Obsidian options for writing conservative default folder
  rules, exporting the review inbox, and generating a short
  `README-obsidian-human-gui.md` guide.
- Added Obsidian two-sided conflict detection: if the source note and Vault raw
  copy both changed since the last import, Vault keeps the raw note unchanged
  and records a metadata-only conflict for review.
- Added generated Vault Remote Server hardening files:
  `vault-remote-server.env.example` and `REMOTE_SERVER_HARDENING.md`.
- Added a compact multi-Agent GUI `activity_health` card for connected agents,
  pending candidates, sync conflicts, Obsidian mirror conflicts, and human 5%
  review pressure.

### Changed

- Updated Agent install docs to present Obsidian as the human-readable notebook
  while Vault remains the governed agent memory core.
- Generated Obsidian sync templates can now run incremental import and then
  export the review inbox back to `00-Vault-Knowledge/_Inbox/`.
- Obsidian Sync Status now reports unmatched active notes so users can tune
  folder rules without learning the full CLI.
- Obsidian Sync Status now reports Obsidian mirror conflicts separately from
  remote candidate sync conflicts.
- Generated systemd and Docker Compose Remote Server templates now point to an
  env-file workflow for stable token handling.

### Safety

- Vault-generated Obsidian notes stay under `00-Vault-Knowledge/` and are
  skipped by the importer to avoid feeding generated review cards back into raw
  source notes.
- Folder rules are conservative: protected folders can make notes more
  restrictive, but note frontmatter should not accidentally downgrade those
  folders.
- Sync conflict cards remain metadata-only and do not expose raw conflicting
  memory content.
- Obsidian mirror conflicts do not overwrite either side; operators can review
  source and raw paths before deciding what to keep.
- Remote Server hardening guidance keeps public exposure, token rotation,
  backups, audit review, and candidate-first remote writes explicit.

### Validation

- Verified Obsidian import/export, setup-agent, module-size, history privacy,
  and package compile checks locally.
- Verified a real setup-agent Obsidian cron smoke: generated templates, executed
  the sync command, and confirmed `_Inbox` notes were written.

## [0.7.22] - 2026-07-01

### Added

- Added `vault gateway serve`, a token-protected HTTP Gateway for agents and
  local workflows that need one small memory entrypoint instead of the full CLI
  or MCP schema surface.
- Added Gateway endpoints for `/health`, `/search`, `/read-range`, and
  `/submit-candidate`, with read-policy defaults, bounded reads, candidate-only
  writes, and compact audit logs.
- Added candidate-first memory migration through `vault import memory`, so
  Chatbox/chat exports, Markdown folders, JSON, CSV, transcript, and OKF-like
  bundles can be previewed and imported into `memory_candidates` without
  writing active knowledge directly.

### Changed

- Documented Gateway as the stable adapter boundary for Codex, Claude Code,
  OpenClaw, Hermes Agent, n8n, Coze bridges, and future devices.
- Updated README, CLI reference, agent integration docs, and decision records
  to keep Gateway and external-memory migration explicit and reviewable.

### Safety

- Gateway requires `agent_id` for read/write calls, hides private memory by
  default, caps default read sensitivity at `low`, and never returns raw
  content from search.
- Gateway candidate submission never writes active knowledge. Shared, private,
  high-sensitivity, and restricted candidates require explicit server launch
  flags.
- Gateway `--no-auth` is rejected for non-localhost binds.
- External memory migration defaults to dry-run preview and can write only
  review candidates when explicitly requested.

### Validation

- Verified Gateway, memory migration, project-dir, access-policy, and MCP
  security tests locally after merging.
- Verified full post-merge test suite locally: 2338 passed, 10 skipped.

## [0.7.21] - 2026-07-01

### Added

- Added a unified GUI human-review inbox that combines daily report cards,
  candidate memories, sync conflicts, and directed Task Ledger handoffs into
  one compact "daily 5%" review surface.
- Added explicit GUI Task Handoff claiming with confirmation tokens so a
  receiving agent can take over handoff work without writing to L0-L3 memory.

### Changed

- Moved the local GUI HTML out of the Python module and into a packaged
  `vault/assets/gui_app.html` asset, keeping `vault.gui_app.APP_HTML` as the
  compatibility loader while reducing `vault/gui_app.py` from the size ceiling
  to a tiny asset loader.

### Safety

- Kept the unified review inbox metadata-only by default: raw candidate
  content, sync-conflict content, and handoff Markdown stay hidden until the
  user opens the specific detail view.
- Kept sync-conflict decisions separated as `keep_local`, `accept_remote`, and
  `manual`; accepting remote promotes the reviewed candidate and archives the
  old local row instead of silently overwriting it.

### Validation

- Verified GUI, Task Ledger, and multi-host sync tests locally.
- Verified module-size gate, wheel build, and packaged GUI asset inclusion.

## [0.7.20] - 2026-07-01

### Added

- Added manifest-backed incremental Obsidian import so changed notes update
  Vault without re-importing unchanged notes, while missing source notes stay
  safe unless `--prune-missing` is explicitly requested.
- Added a read-only multi-Agent GUI dashboard showing connected agents, recent
  sync state, recent memory candidates, and the small human-review queue.
- Added minimal MCP install configs for Codex, Claude Code, Hermes Agent,
  OpenClaw, Coze, and n8n so agents can connect to one shared Vault with the
  shortest working setup.
- Added near-realtime Supabase push sync templates through
  `--supabase-sync realtime` plus `scripts.watch_supabase_sync`.

### Safety

- Kept Supabase near-realtime sync one-way: local `vault.db` remains the source
  of truth and Supabase remains a shared read copy.
- Kept Coze/n8n on remote-reader templates by default and documented that
  service-role keys belong only on trusted sync hosts.
- Kept the multi-Agent dashboard read-only; it does not write active memory,
  candidates, or raw private content.

### Validation

- Verified local full tests: `2308 passed, 10 skipped`.
- Built and checked both wheel and sdist with `twine check`.
- Ran a clean wheel-install smoke for `vault-for-llm[mcp,supabase]`, covering
  `vault`, `vault-mcp`, `init`, `doctor`, `add`, `compile --no-embed`,
  `search --json`, Obsidian incremental import, `setup-agent`, Supabase watcher
  dry-run, `remote status`, GUI API, and MCP tool profiles.

## [0.7.19] - 2026-06-30

### Changed

- Refined the consumer `setup-agent` terminal output so normal users see a
  short "For you" section while agent maintenance details stay under
  "For your agent".
- Added `agent_next_steps` to the setup payload as a clearer alias for
  automation/agent-facing setup follow-up work while preserving the existing
  `next_steps` field for compatibility.

### Docs

- Documented the consumer-output boundary in the product hardening decision
  record: humans get the short daily-memory workflow, agents use `--json` for
  the full maintenance checklist.

## [0.7.18] - 2026-06-30

### Added

- Added permission-gated MCP Skill registry writes with `vault_skill_push`; writes stay inside the Vault registry, are privacy-gated, validate Skill names, and never install runtime Skill files.
- Added MCP Skill sync status and sync manifest tools so trusted external workers can sync by metadata/hash first and export bounded content only with explicit approval.
- Added `vault_skill_mark_synced` for recording successful external Skill sync handoff.
- Added a decision record documenting the Skill MCP write/sync boundary.
- Added `vault guide` and an agent-first usage guide so humans see a small CLI surface while agents use MCP profiles and generated setup artifacts for the wider toolbox.
- Added a shared SQLite runtime helper that applies WAL, `busy_timeout`, foreign keys, and retry/backoff for common write paths.

### Safety

- Kept Skill write tools out of the `core` and `review` profiles; only `maintenance` and `full` expose registry writes.
- Kept Skill sync manifests content-free by default and blocked fail-level privacy findings during content export.
- Documented the SQLite concurrency boundary for multi-agent installs: the runtime is more tolerant of lock contention, but sustained high-write workloads should still use a long-lived MCP service or future write-worker queue instead of many short-lived CLI subprocesses.

## [0.7.17] - 2026-06-30

### Added

- Added memory-intelligence annotations to automatic session capture, including `extraction_score`, `novelty_score`, `recommended_action`, and `merge_target` so agents can distinguish new memory from updates to existing memory.
- Added reflection consolidation suggestions that cluster similar active memories and write reviewable `consolidation_suggestion` candidates without rewriting active knowledge.
- Added temporal search ranking so current facts are preferred, historical facts remain auditable but slightly lower ranked, and future facts are visible only with a lower truth priority.
- Added a decision record for the Memory Intelligence loop: candidate scoring, time-aware recall, and report-first consolidation.

### Safety

- Memory-intelligence outputs remain candidate-first and deterministic. They do not auto-promote, hard-delete, rewrite active knowledge, or bypass governance.

## [0.7.16] - 2026-06-30

### Added

- Added `vault security doctor` for local GUI/MCP security posture checks.
- Added Skill Registry revision history, compact version diffs, upgrade-plan CLI, and read-oriented MCP Skill tools in review/maintenance/full profiles.
- Added Task Ledger `priority` and `due_at` fields across schema, CLI, MCP, GUI payloads, handoff markdown, and automation-cycle snapshots.
- Added a decision record for selectively adopting Letta-style memory management without turning Vault into a full agent runtime.

### Changed

- GUI now requires an access token by default; `--no-auth` is only allowed for localhost-bound test sessions.
- Local MCP read tools now default to `max_sensitivity=medium`; high/restricted reads must be requested explicitly.
- Agent registry entries can declare expected Skills with `vault agent register --skills`.

## [0.7.15] - 2026-06-29

### Added

- Added Task Ledger as a runtime working-set layer for resumable agent work, separate from permanent L0-L3 memory.
- Added Task Ledger MCP tools for starting, reading, updating, handing off, and completing active work in `review`, `maintenance`, and `full` profiles.
- Added a read-only GUI Active Tasks panel and compact task APIs so humans can inspect active/blocked work without exposing raw long-term memory.
- Added Task Ledger snapshots to `vault automation cycle --write-workspace`, keeping next actions and continuation notes in the compact agent handoff.

### Safety

- Kept Task Ledger out of the `core` MCP profile so the smallest default schema stays compact.
- Kept Task Ledger as task state, not active knowledge: it does not create L0-L3 memories, promote candidates, or mutate long-term memory during automation cycle reads.
- GUI task APIs return compact task metadata and handoff markdown, not raw candidate bodies or private memory dumps.

### Maintenance

- Updated public README pins, the claim matrix, and the short release announcement for the Task Ledger continuity release.

## [0.7.14] - 2026-06-26

### Added

- Added a filterable local GUI document list with layer, category, and sensitivity filters, plus a compact `/api/documents` endpoint that does not return raw memory content.
- Added a right-side GUI Document Map panel for section and claim navigation, with section clicks opening bounded evidence ranges.
- Added a compact right-side GUI graph visualization with clickable linked-memory nodes.

### Changed

- Split automation policy defaults, YAML loading, mode normalization, and policy value parsing into `vault/automation_policy.py`.
- Kept the existing `vault.automation` imports for `default_policy`, `load_policy`, `write_policy`, `DEFAULT_MODE`, and `POLICY_FILE` so external callers do not need to change.

### Maintenance

- Tightened the module-size baseline for `vault/automation.py` after the policy split.
- Added a decision record and short release note for the automation policy module paydown.

## [0.7.13] - 2026-06-26

### Changed

- Split MCP search result shaping into `vault/mcp_search.py`, keeping the MCP router focused on tool dispatch and signed identity checks.
- Split CLI temporal search option wiring into `vault/cli_search.py`.
- Split graph expansion recall logic into `vault/search_graph.py` while preserving the v0.7.11 read-policy guard.

### Maintenance

- Tightened the module-size baseline for `vault/cli.py`, `vault/mcp.py`, and `vault/search.py` after the refactor.
- Added a decision record for the first module-size paydown following the v0.7.12 security hardening release.

## [0.7.12] - 2026-06-26

### Added

- Added optional signed MCP agent identity. When `VAULT_MCP_REQUIRE_AGENT_SIGNATURE=1` is set, MCP calls must include `agent_id` and a valid HMAC-SHA256 `agent_signature`.
- Added per-agent secret lookup through `VAULT_MCP_AGENT_SECRET_<AGENT>` with `VAULT_MCP_AGENT_SECRET` as the fallback.
- Added `sign_agent_request()` for local adapters and tests that need to generate the exact signature Vault verifies.

### Safety

- Signed identity is opt-in for backwards compatibility, but invalid signatures are rejected whenever a caller provides one.
- Agent secrets stay in environment variables and are not written to setup artifacts, reports, or logs.

## [0.7.11] - 2026-06-26

### Added

- Search results now include `temporal_state` (`current`, `past`, `future`, or `timeless`) when temporal fact-window metadata is present.
- `vault search` and MCP `vault_search` now support temporal filtering controls for excluding expired or future facts while keeping historical facts auditable by default.

### Fixed

- Graph-expanded search results now apply the same read policy as primary search results, preventing graph neighbors from exposing private or restricted memory.
- Base64-encoded payloads that decode to fail-level secrets now fail the privacy gate instead of only warning.

### Safety

- Temporal search remains backwards-compatible: past/future facts are marked by default and can be excluded explicitly.
- Graph expansion now checks `scope`, `sensitivity`, `owner_agent`, and `allowed_agents` before adding neighbor memories.

## [0.7.10] - 2026-06-25

### Added

- `vault automation handoff` and MCP `vault_automation_handoff` now expose `pipeline_receipt_content` as a read-only startup preface when `reports/automation/pipeline-latest.md` or `.json` exists.
- Generated setup-agent MCP startup guides, adapter startup contracts, and runtime playbooks now use this read order: `fleet_health_content`, `pipeline_receipt_content`, `review_summary_content`, `learning_health_content`, then the selected handoff `content`.
- Added `vault/automation_handoff.py` to keep startup handoff assembly out of the already-large automation workflow module.

### Safety

- The selected `content` handoff remains stable for existing cycle/inbox readers.
- Pipeline receipt prefaces are read-only and do not include raw transcript contents or candidate body fields.

## [0.7.9] - 2026-06-25

### Added

- `vault memory pipeline --write-report` now writes `reports/automation/pipeline-latest.json` and `pipeline-latest.md` as a compact memory-ingestion receipt.
- Generated setup-agent cron, LaunchAgent, and n8n schedules now include `--write-report` on the memory pipeline step, so scheduled ingestion leaves a visible artifact for the next agent.
- Added a decision record and short release note for pipeline ingestion receipts.

### Safety

- Pipeline reports strip raw candidate body fields, content previews, and gate payloads from persisted receipts.
- The pipeline remains candidate-first: reports do not promote active memory, read extra transcript contents, hard-delete rows, or bypass privacy gates.

## [0.7.8] - 2026-06-25

### Added

- `vault automation handoff` and MCP `vault_automation_handoff` now attach `review_summary_content` and `learning_health_content` as read-only startup prefaces when the latest files exist.
- Generated MCP startup guides and runtime adapter templates now require this read order: `fleet_health_content`, `review_summary_content`, `learning_health_content`, then the selected handoff `content`.
- `vault agent startup-doctor` now detects older startup packs that only mention fleet health and do not include review-summary / learning-health prefaces.
- Added a decision record and short release note for startup prefaces in the multi-Agent handoff contract.

### Safety

- The selected handoff `content` remains unchanged for existing readers; startup prefaces are attached separately.
- Review-summary and learning-health prefaces are read-only and do not expose raw candidate content, promote memory, archive rows, or apply lifecycle actions.

## [0.7.7] - 2026-06-25

### Added

- `vault automation review-feedback --write-learning-policy` now closes the visible learning loop by immediately refreshing `reports/automation/review-summary-latest.json`, `review-summary-latest.md`, `learning-health-latest.json`, and `learning-health-latest.md` after recording the card decision.
- Review-feedback CLI output now prints the next review-summary path, learning-health path, and top learned action when the closed-loop refresh is available.
- Added `vault/automation_review.py` to keep review-card feedback helpers out of the main automation workflow module.
- Added a decision record and short release note for visible review-feedback closed loops.

### Safety

- Review-feedback remains feedback-only: it records the card outcome and refreshes reports, but it does not promote memory, archive rows, widen policy, delete rows, or apply the card's recommended lifecycle action.
- Learned review-card actions remain bounded ranking hints only, with the same capped multiplier and no authorization effect.

## [0.7.6] - 2026-06-25

### Added

- Generated memory automation schedules now write `vault automation review-summary --write-summary` between the inbox handoff and learning-health dashboard, so scheduled runs produce the shortest 5% human-review card deck by default.
- Review-summary Markdown now renders decision-card sections with suggested decisions and safe next steps instead of only a wide table.
- Added a decision record and short release note for scheduled human-review cards.

### Safety

- Review-summary remains read-only and does not expose raw candidate content.
- The generated schedule still does not promote active memory, widen policy, archive, or delete unless existing explicit `--automation-apply` controls allow those separate reversible actions.

## [0.7.5] - 2026-06-25

### Added

- Generated memory automation schedules now run the automatic memory pipeline and report-first reflection pass before the existing automation cycle, inbox handoff, and learning-health dashboard.
- Added MCP tools for `vault_memory_pipeline`, `vault_memory_temporal_status`, and `vault_memory_reflection` in review, maintenance, and full profiles while keeping the core profile unchanged.
- Added a decision record documenting the scheduled candidate-first memory closed loop.

### Safety

- Scheduled pipeline and reflection writes remain candidate-only.
- The generated closed loop does not add hard deletion, hidden active-memory promotion, or extra core MCP tool-schema tokens.

## [0.7.4] - 2026-06-25

### Fixed

- Updated generated `agent-install/local-smoke.sh` to derive its default Python interpreter from the installed `vault` console script when `PYTHON` is not explicitly set. This keeps agent installer self-tests aligned with the venv or packaged environment that actually owns Vault-for-LLM.

### Testing

- Verified the v0.7.3 PyPI package exposed automatic memory pipeline, temporal memory status/list, reflection candidates, and setup-agent artifacts before cutting this installer-smoke patch.

## [0.7.3] - 2026-06-25

### Added

- Added `vault memory pipeline`, a preview-first automatic conversation-memory pipeline that discovers transcripts, extracts reusable session lessons, deduplicates through the existing candidate gates, and optionally writes candidate memories.
- Added temporal fact-window metadata (`valid_from`, `valid_until`, `supersedes_id`) for active knowledge and memory candidates, plus `vault memory temporal status/list` to separate current, past, future, and timeless facts.
- Added `vault memory reflection`, a first-class reflection wrapper around Dream curation and lifecycle automation so agents can run report-first memory consolidation, archive, and cold-store review from one command.
- Added a decision record for automatic, temporal, and reflective memory boundaries.

### Safety

- The memory pipeline previews by default and writes candidates only with `--write-candidates`; it does not promote active knowledge.
- Temporal windows preserve old facts for audit instead of deleting them.
- Reflection remains report-first, candidate-first, and hard-delete-free; lifecycle changes require existing policy controls and explicit `--apply`.

## [0.7.2] - 2026-06-25

### Changed

- Added `docs/reviews/v0.7.1-review.md`, a corrected public review note that distinguishes the v0.7 platform line from the v0.7.1 patch and clarifies that `vault add` does not replace candidate-first `vault remember`.
- Made `vault stats` report legacy sqlite-vec embeddings and JSON-backed `semantic_vectors` separately, while preserving `embedding_count` as a compatibility summary.
- Made `vault doctor` distinguish an installed `sqlite-vec` Python package from a runtime-blocked loadable extension, including restricted SQLite errors such as `not authorized`.
- Updated packaged install examples and release claim references to `0.7.2`.

### Safety

- This patch release does not add a new memory mutation path, hosted dependency, MCP permission, auto-promote path, remote sync behavior, or background automation trigger.
- sqlite-vec runtime failures now remain explicit degradations: keyword search and JSON-backed semantic vectors can still work, while legacy sqlite-vec shadow search is marked unavailable.

## [0.7.1] - 2026-06-25

### Changed

- Clarified the README manual quickstart with the packaged CLI shapes verified during v0.7.0 PyPI smoke testing: `vault add ... --content ...` for active notes and `vault map read <id> --lines START-END` for bounded source reads.
- Extended `scripts/readme_command_smoke.py` to verify `map build/read`, so README quickstart coverage now protects the bounded-read path.
- Strengthened generated `agent-install/local-smoke.sh` to test active add/search, Document Map build/read, candidate-first `remember`, candidate listing, and core MCP startup tools.
- Updated packaged install examples and release claim references to `0.7.1`.

### Safety

- This patch release does not add a new memory mutation path, hosted dependency, MCP permission, auto-promote path, remote sync behavior, or background automation trigger.
- The smoke-script change only verifies the existing active-note and bounded-read path before the existing candidate-first memory check.

## [0.7.0] - 2026-06-25

### Changed

- Promoted the Agent Knowledge Platform foundation from the v0.7 release-candidate line to stable v0.7.0.
- Clarified the README smoke path: active `add/search/read` checks are separate from candidate-first `remember/propose` checks.
- Updated packaged install examples and release claim references to `0.7.0`.

### Safety

- This stable release does not add a new memory mutation path, hosted dependency, MCP permission, or background automation trigger beyond the validated v0.7 RC line.
- v0.7.0 follows clean PyPI install, `setup-agent`, startup-doctor, README minimal-path, MCP, and release-gate smoke testing from the RC line.

## [0.7.0rc2] - 2026-06-25

### Changed

- Clarified `setup-agent --agent-roster` role values in CLI help and setup documentation after v0.7.0rc1 install smoke testing.
- Added a v0.7.0rc2 validation note for the packaged `setup-agent` path.
- Updated packaged install examples and release claim references to `0.7.0rc2`.

### Safety

- This release candidate does not add a new memory mutation path, hosted dependency, MCP permission, or background automation trigger.
- The RC keeps the v0.7 platform boundary and focuses on install-path clarity before the stable v0.7.0 release.

## [0.7.0rc1] - 2026-06-25

### Changed

- Started the v0.7 release-candidate line for the Agent Knowledge Platform foundation.
- Added release-parity support for PEP 440 release-candidate tags such as `v0.7.0rc1`.
- Updated packaged install examples and release claim references to `0.7.0rc1`.

### Safety

- This release candidate does not add a new memory mutation path, hosted dependency, MCP permission, or background automation trigger.
- The RC exists to validate packaging, installer guidance, MCP startup behavior, and platform-boundary documentation before the stable v0.7.0 release.

## [0.6.124] - 2026-06-25

### Changed

- Split MCP automation inbox, activity, brief, handoff, dream, and cold-store handlers into `vault.mcp_automation`.
- Kept MCP tool names and JSON result shapes unchanged while continuing to reduce `vault/mcp.py` as the central router.
- Lowered the `vault/mcp.py` module-size baseline after the split.

### Safety

- Automation, dream, and cold-store behavior is unchanged, including dry-run defaults, bounded limits, and existing lifecycle protections.
- This split does not add any new MCP tool, write permission, auto-promote path, remote sync behavior, or background automation trigger.

## [0.6.123] - 2026-06-25

### Changed

- Split MCP memory write, candidate review, candidate listing, promotion, and session-capture handlers into `vault.mcp_memory`.
- Kept `vault.mcp` compatibility imports for memory candidate formatting and transcript path resolution helpers.
- Lowered the `vault/mcp.py` module-size baseline after the split.

### Safety

- MCP write policy checks, privacy gates, candidate-first behavior, session transcript path restrictions, and direct `vault_add` warnings are unchanged.
- This split does not add any new MCP tool, write permission, auto-promote path, or remote sync behavior.

## [0.6.122] - 2026-06-25

### Changed

- Split local MCP Document Map and bounded-read helpers into `vault.mcp_read`.
- Kept `vault.mcp` compatibility imports for `vault_map_show`, `vault_read_range`, local read payload helpers, citation helpers, and local error helpers.
- Lowered the `vault/mcp.py` module-size baseline after the split.

### Safety

- Local `vault_map_show` and `vault_read_range` behavior is unchanged, including read-policy filtering, range limits, citations, and error `next_action` payloads.
- Remote Supabase MCP tools remain routed through `vault.mcp_remote`; this split does not change remote access-control behavior or add any new write path.

## [0.6.121] - 2026-06-25

### Changed

- Split semantic index CLI handlers, provider construction, QA query loading, and cache payload helpers into `vault.cli_semantic`.
- Kept `vault.cli` compatibility imports for `cmd_semantic` and existing semantic helper functions.
- Lowered the `vault/cli.py` module-size baseline after the split.

### Safety

- `vault semantic rebuild`, `warm`, `smoke`, `cache-stats`, `cache-prune`, `startup`, and `daemon` behavior is unchanged.
- The split does not add any new embedding provider, model loading path, remote dependency, or automatic memory mutation.

## [0.6.120] - 2026-06-25

### Changed

- Split lightweight reranking, cross-encoder reranking, freshness, graph-depth, and usage-boost scoring helpers into `vault.search_rerank`.
- Kept `vault.search` compatibility imports for `LightweightReranker`, `CrossEncoderReranker`, `calc_freshness`, `calc_graph_depth`, and `calc_usage_boost`.
- Lowered the `vault/search.py` module-size baseline after the split.

### Safety

- Search behavior, access filtering, active-memory filtering, and rerank score fields are unchanged.
- The split does not add any new model loading path or remote dependency.

## [0.6.119] - 2026-06-25

### Changed

- Split automation cycle workspace, priority brief, next-task, agent-start prompt, and transcript-capture helpers into `vault.automation_cycle`.
- Kept `vault automation cycle` payloads, workspace paths, transcript-capture safety metadata, and public import behavior unchanged.
- Lowered the `vault/automation.py` module-size baseline after the split.

### Safety

- Transcript capture remains opt-in, candidate-only, content-hidden in cycle handoffs, and constrained to review before active memory changes.
- Cycle workspace writes remain constrained under `reports/automation`.

## [0.6.118] - 2026-06-25

### Changed

- Split automation inbox, candidate queue priority, review digest, and inbox handoff helpers into `vault.automation_inbox`.
- Kept `vault.automation.automation_inbox` available through the existing import path for CLI, MCP, and downstream callers.
- Lowered the `vault/automation.py` module-size baseline after the split.

### Safety

- Automation inbox remains read-only by default: it does not auto-promote, hard-delete, or expose candidate content unless `include_content` is explicitly requested.

## [0.6.117] - 2026-06-25

### Changed

- Split automation feedback-learning policy, learning-health cards, and learned priority matching helpers into `vault.automation_learning`.
- Kept `vault.automation` behavior unchanged while reducing the review surface of the daily automation workflow module.
- Lowered the `vault/automation.py` module-size baseline after the split.

### Safety

- Automation learning remains a bounded ranking/review hint only; the split does not change auto-promote, archive, cold-store, candidate, or active-memory mutation policy.

## [0.6.116] - 2026-06-25

### Changed

- Split Agent setup Supabase guide, read-policy SQL, and setup-language normalization helpers into `vault.agent_setup_supabase`.
- Kept `vault.agent_setup` compatibility imports for CLI, tests, and downstream callers.
- Lowered the `vault/agent_setup.py` module-size baseline after the split.

### Safety

- `vault setup-agent` Supabase guide output, advanced `supabase-read-policy.sql`, setup language aliases, and public imports remain unchanged.

## [0.6.115] - 2026-06-25

### Changed

- Split Agent setup startup, update-status, runtime adapter, and startup-doctor helpers into `vault.agent_setup_startup`.
- Kept `vault.agent_setup` compatibility imports for CLI and downstream callers.
- Lowered the `vault/agent_setup.py` module-size baseline after the split.

### Safety

- `vault setup-agent`, generated MCP startup files, update-status templates, runtime adapter templates, runtime template install behavior, and startup doctor output remain unchanged.

## [0.6.114] - 2026-06-25

### Changed

- Split Agent setup schedule, sync, and remote-reader template helpers into `vault.agent_setup_templates`.
- Kept `vault.agent_setup` compatibility imports for existing tests and downstream callers.
- Lowered the `vault/agent_setup.py` module-size baseline after the split.

### Safety

- `vault setup-agent` output, generated cron/LaunchAgent/n8n templates, Supabase sync templates, remote-reader templates, and automation schedule templates remain unchanged.

## [0.6.113] - 2026-06-25

### Changed

- Split automation CLI command handling and parser registration into `vault.cli_automation`.
- Kept `vault.cli.cmd_automation` as a compatibility wrapper for existing tests and downstream imports.
- Lowered the `vault/cli.py` module-size baseline after the split.

### Safety

- Public `vault automation ...` command names, options, JSON payloads, and human-readable output behavior remain unchanged.

## [0.6.112] - 2026-06-25

### Changed

- Split automation report, handoff, and Markdown artifact helpers into `vault.automation_reports`.
- Kept public automation CLI and MCP behavior unchanged while reducing the review surface of `vault/automation.py`.
- Lowered the `vault/automation.py` module-size baseline after the split.

### Safety

- Automation lifecycle behavior, candidate promotion policy, report path boundaries, and read-only handoff surfaces are unchanged.

## [0.6.111] - 2026-06-25

### Changed

- Split Supabase remote MCP reader helpers into `vault.mcp_remote`.
- Kept legacy `vault.mcp` helper imports and monkeypatch-compatible wrappers for existing tests, CLI imports, and downstream callers.
- Lowered the `vault/mcp.py` module-size baseline after the split.

### Safety

- Remote search, remote doctor, remote map, and remote read-range behavior remains unchanged while the review surface is smaller.

## [0.6.110] - 2026-06-25

### Added

- Added `scripts/module_size_gate.py`, a baseline-based module-size guard for `vault/*.py`.
- Added `scripts/module_size_baseline.json` to record current oversized modules without allowing silent growth.
- Added CI coverage for the module-size gate.

### Docs

- Documented the module-size rule in repo governance, scripts guide, a decision record, and the short release note.

## [0.6.109] - 2026-06-25

### Changed

- Split MCP rate limiting and write-governance checks into `vault.mcp_security`, keeping the public MCP router behavior unchanged.
- Added focused tests for the extracted MCP security helper module.

### Safety

- The MCP write boundary now has a smaller, reusable module surface for future tools instead of living inline inside the main MCP router.
- Existing rate-limit and write-denial payloads remain compatible.

## [0.6.108] - 2026-06-25

### Added

- Added write-side MCP governance for direct active-memory writes and candidate promotion. Shared/public, private, high-sensitivity, and restricted writes now require explicit agent identity plus the matching `allow_*` capability flag.
- Added deterministic prompt-injection and encoded-secret warnings to the privacy gate, including English and Chinese instruction-override patterns, Taiwan phone/ID warnings, high-entropy token warnings, and Base64 decoded sensitive-content checks.
- Added in-process MCP tool rate limiting with configurable `VAULT_MCP_RATE_LIMIT_PER_MINUTE` and `VAULT_MCP_RATE_LIMIT_BURST` environment variables.

### Safety

- Legacy low-sensitivity project writes remain compatible, but broader multi-Agent writes must now be explicit.
- Rate limiting returns a structured `rate_limited` payload with retry guidance instead of exposing internal errors.
- Prompt-injection findings are warnings, not automatic deletion; they keep candidate-first review flows intact while making risky memory visible.

## [0.6.107] - 2026-06-25

### Added

- Added `vault agent startup-doctor`, a read-only check for `agent-install/` startup contracts generated by `vault setup-agent`.
- The doctor verifies MCP startup order, `fleet_health_content -> content` handoff result contracts, runtime adapter templates, and runtime update playbook guidance.
- The JSON output reports pass/warn/fail checks, missing/outdated files, and recommended actions so agents can decide when to regenerate setup files.

### Safety

- `startup-doctor` only reads generated setup files. It does not modify runtime instruction files, read private memory, promote memory, or run update checks.

## [0.6.106] - 2026-06-25

### Changed

- `vault setup-agent` generated MCP startup files now document the fleet-aware handoff result contract: read `fleet_health_content` first when present, then the selected `content` handoff.
- Generated Agent adapter startup contracts for Codex, Claude Code, OpenClaw, and Hermes now include a machine-readable `handoff_contract` and per-step `result_contract`.
- Runtime update playbooks now explicitly treat fleet health as a read-only startup preface for shared multi-Agent automation health.

### Safety

- Startup templates keep the existing boundaries: no auto-upgrade, no raw transcript reads by default, no automatic memory promotion, and one shared project vault can coexist with private per-Agent memory.

## [0.6.105] - 2026-06-25

### Changed

- `vault automation handoff` now includes the latest `fleet-health-latest.md` or `.json` as a startup health preface when present, while preserving the selected cycle/inbox handoff as the main `content`.
- The CLI prints fleet health before the cycle handoff so multi-Agent installs see shared automation health before individual next-task instructions.
- MCP `vault_automation_handoff` exposes `fleet_health_path`, `fleet_health_content_type`, and `fleet_health_content` without changing the existing `content` field contract.

### Safety

- Fleet-health handoff attachment remains read-only and uses only existing `reports/automation` artifacts; it does not read private memory, raw candidate content, raw transcript content, or raw feedback reasons.

## [0.6.104] - 2026-06-25

### Added

- Added `vault automation fleet-health`, a read-only multi-Agent automation health panel that combines local agent registry metadata, learning-health status, and update-distribution health.
- Fleet health can write `reports/automation/fleet-health-latest.json` and `.md` for dashboards and shared Agent startup checks.

### Safety

- Fleet health uses registry metadata and compact reports only; it does not read private memory, raw candidate content, or raw feedback reasons.

## [0.6.103] - 2026-06-25

### Changed

- Agent setup memory automation schedules now write the compact learning-health dashboard after each scheduled automation run.
- Generated cron, LaunchAgent, and n8n memory automation templates now run `vault automation learning-health --write-health` after the inbox handoff, producing `reports/automation/learning-health-latest.json` and `.md`.

## [0.6.102] - 2026-06-25

### Added

- Added `vault automation learning-health`, a read-only dashboard surface for accepted/rejected/deferred automation feedback and bounded learning-policy rules.
- Learning health can write `reports/automation/learning-health-latest.json` and `.md` for dashboards, startup handoffs, and scheduled review.

### Changed

- Automation learning now has a compact health status (`cold_start`, `healthy`, `watch`, or `needs_review`) before humans inspect full eval output.

## [0.6.101] - 2026-06-24

### Added

- Added `vault automation review-feedback`, a feedback-only command for recording `accept`, `reject`, or `defer` decisions on `review-summary` cards.
- Review-card feedback now flows into the existing bounded learning-policy pipeline, so repeated approvals can raise similar cards and repeated rejections can lower them.

### Changed

- `vault automation review-summary` now applies bounded learned ranking hints from prior review-card feedback while remaining read-only.

## [0.6.100] - 2026-06-24

### Added

- Added `vault automation review-summary`, a read-only 5% human approval surface that turns brief/inbox/report signals into short review cards.
- Review summaries can write `reports/automation/review-summary-latest.json` and `.md` for dashboards, scheduled handoffs, or human review.

### Changed

- Automation review UX now has a smaller first-stop surface before opening full reports, inbox queues, raw candidate content, or lifecycle ledgers.

## [0.6.99] - 2026-06-24

### Added

- `cold-store-expired` previews and automation reports now include the same explainable `importance_score`, components, signals, and recommendation used by `automation brief`.
- Automation action ledgers and dry-run diffs now surface importance-guided lifecycle context, including the highest cold-store importance score for a run.

### Changed

- Expired-but-used cold-store candidates are now sorted by importance, citation count, access count, and id, so review starts with the memories most likely to deserve refresh, summary, or protected cold storage.

## [0.6.98] - 2026-06-24

### Added

- `automation brief` now exposes an explainable `importance_score` for top-used memories, with components for access, citation, recency, trust, freshness, TTL pressure, and governance protection hints.
- Brief JSON now includes `importance_components`, `signals`, and lifecycle recommendations such as `refresh_or_cold_store_before_forgetting`.

### Changed

- Memory ranking in the automation brief is now based on the explainable importance model instead of the old `access + citation` weight alone. `weight_score` remains as a compatibility alias.

## [0.6.97] - 2026-06-24

### Added

- `automation inbox` now reads `reports/automation/learning_policy.json` and applies bounded feedback multipliers to candidate review priority.
- Inbox and review digest items now expose `base_priority`, `learning_multiplier`, `learning_action`, and `learning_reason` so learned ranking remains auditable.

### Changed

- `automation brief` inherits the same learned review ordering through the inbox digest. Learning still only affects ranking; it does not auto-promote, auto-delete, or bypass privacy/access policy.

## [0.6.96] - 2026-06-24

### Added

- Added `automation inbox` review digest cards that summarize the latest automation report's human-review items before the raw candidate queue.
- `automation brief` now uses the same digest for its 5% human-review section, so daily startup and inbox review share one compact decision surface.

### Changed

- CLI inbox output now prints the review digest first, including recommended action and safe action, then falls back to the detailed candidate queue.

## [0.6.95] - 2026-06-24

### Added

- Automation runs now include `cold_store_expired` previews and, when policy plus `--apply` allow it, summarize-then-cold-store expired-but-used memories.
- Automation reports, activity feeds, brief summaries, dry-run diffs, and CLI output now show cold-store preview/applied/skipped counts.

### Changed

- Balanced and autonomous automation policies enable `cold_store_used_expired` by default, while conservative mode keeps it off.

## [0.6.94] - 2026-06-24

### Added

- Added `vault usage cold-store-expired`, a dry-run-first lifecycle command for expired-but-used memories.
- Added MCP `vault_cold_store_expired` in the maintenance/full tool profiles. It defaults to preview mode and skips private, high/restricted, and L0/L1 memories.

### Changed

- Long-term forgetting can now move from strategy to a reversible first action: write a compact summary, demote eligible rows to the daily-detail layer, mark them archived, and retain original content for audit/restore.

## [0.6.93] - 2026-06-24

### Added

- Added `vault automation brief`, a compact read-only intelligence view that joins learning hints, memory usage weights, forgetting pressure, shared agent health, and the shortest human-review queue.
- Added MCP `vault_automation_brief` to the core tool profile, so Codex, Claude Code, OpenClaw, Hermes-style agents, and other MCP runtimes can read the same automation health surface without raw candidate content.
- Added JSON and Markdown brief export via `vault automation brief --write-brief`.

### Changed

- Automation observability now has a single startup-friendly "5% human review" view before deeper reports, cycle workspaces, or candidate content are needed.

## [0.6.92] - 2026-06-24

### Added

- Added `vault automation activity`, a compact read-only closed-loop activity feed for recent automation reports.
- Added MCP `vault_automation_activity`, available in the core tool profile, so agents can see recent auto-promote previews, promotions, and skipped reasons without reading raw candidate content.

### Changed

- Automation observability now has a short startup-friendly surface in addition to full `automation report --detail` JSON.

## [0.6.91] - 2026-06-24

### Added

- Added `vault setup-agent --automation-auto-promote-low-risk`, an explicit installer switch that writes `automation_policy.yaml` with low-risk candidate auto-promotion enabled.
- Interactive `vault setup-agent` now asks whether scheduled memory automation should enable the low-risk `session_capture` / `session_lesson` auto-promote policy.
- Generated memory automation README files now show whether low-risk auto-promote policy is enabled and remind agents that it still requires `automation_policy.yaml` plus `--apply`.

### Changed

- Agent setup now surfaces the candidate-to-active-memory closed loop during installation instead of requiring users to hand-edit policy YAML.

## [0.6.90] - 2026-06-24

### Added

- Added policy-gated low-risk candidate auto-promotion for automation runs. It is off by default, requires explicit `auto_promote_low_risk_candidates: true`, and only runs with `--apply`.
- Added low-risk promotion safety checks for source, memory type, scope, sensitivity, trust, source reference, and all candidate gates before a candidate can enter active memory.
- Added automation report, cycle workspace, CLI, and human-review summaries for low-risk auto-promote previews and applied promotions.

### Changed

- Updated automation docs and README guidance to distinguish candidate capture, candidate-only curation, and explicit low-risk promotion into active memory.

## [0.6.89] - 2026-06-24

### Added

- Added opt-in transcript capture to `vault automation cycle`: `--capture-transcripts --apply` turns discovered session transcripts into gated review candidates without promoting active memory.
- Added transcript-capture summaries to `cycle-latest.json` and `cycle-latest.md`, including candidate IDs, counts, safety flags, and hidden-content guarantees.
- Added `vault setup-agent --automation-capture-transcripts` and `--automation-capture-transcript-limit` so generated cron, LaunchAgent, and n8n templates can close the transcript-to-candidate loop when the user explicitly opts in.

### Changed

- Updated automation docs and README guidance to distinguish metadata-only transcript discovery from content-reading transcript capture.

## [0.6.88] - 2026-06-24

### Added

- Added `vault agent install-runtime-template`, a dry-run-first command for safely applying generated Codex, Claude Code, OpenClaw, or Hermes startup templates into runtime instruction files.
- Added backups and marker-based replacement for runtime template installs, so repeated runs update the same Vault block instead of duplicating instructions.
- Added a cross-runtime update-notice smoke test covering Codex, Claude Code, OpenClaw, and Hermes on one shared project vault with one intentionally stale runtime.

### Changed

- Shortened the main README install flow and moved detailed multi-runtime behavior into `docs/agent_install.md`.

## [0.6.87] - 2026-06-24

### Added

- `setup-agent` now writes `agent-install/README-runtime-update-playbook.md` and `runtime-update-playbook.json`, giving Codex, Claude Code, OpenClaw, Hermes Agent, and other local runtimes one shared startup/post-upgrade/stale-notice rule.
- The generated Agent adapter README now points to the runtime update playbook, so multi-runtime installs can coordinate updates without splitting project memory across separate unmanaged databases.
- Added setup-agent tests for the generated runtime update playbook, including MCP doctor arguments, runtime targets, and no-auto-upgrade safety boundaries.

## [0.6.86] - 2026-06-24

### Added

- MCP `vault_update_status` now supports `doctor=true` and `max_status_age_minutes`, giving MCP-only agents the same update-distribution health check as `vault agent doctor`.
- `setup-agent` generated update-status and adapter contracts now include MCP doctor calls, so Codex, Claude Code, OpenClaw, Hermes Agent, and other MCP runtimes can validate shared update notices without shell access.
- Added a multi-Agent shared-vault MCP smoke test covering Codex, Claude Code, OpenClaw, and Hermes-style runtime ids.

## [0.6.85] - 2026-06-24

### Added

- Added `vault agent doctor` and `vault update-status --doctor` to verify that the shared update notice exists, is fresh, includes every registered Agent, and shows which runtimes need attention.
- `vault setup-agent` now writes `agent-install/refresh-update-status.sh` and `README-agent-update-rollout.md` so one upgraded runtime can refresh the shared local notice for all other runtimes.
- Added tests for stale/missing update-status health, Agent attention detection, and generated rollout templates.

## [0.6.84] - 2026-06-24

### Added

- `vault setup-agent` now writes `agent-install/README-agent-adapters.md`, Codex, Claude Code, OpenClaw, and Hermes Agent startup templates, plus `adapter-startup-contract.json`.
- The generated adapter templates make common runtimes follow the same startup order: read update status, read automation handoff, search/read only when needed, and propose candidate-first memory.
- Added a decision record for public-safe Agent adapter startup templates.

## [0.6.83] - 2026-06-24

### Added

- `vault update-status` and `vault agent status` now accept `--agent <id>` to add a focused startup check for the current Agent runtime.
- MCP `vault_update_status` now accepts `agent_id`, returning `current_agent_notice`, `current_agent_needs_attention`, and a `startup_checklist` without adding another MCP tool.
- `vault setup-agent` now writes MCP startup and update-status contracts with the configured Agent id, so each runtime can see its own upgrade/restart advice first.
- Added a decision record for the Agent-focused startup check.

## [0.6.82] - 2026-06-24

### Added

- Added `vault update-status --read-status` and MCP `vault_update_status(read_status=true)` so Agents can read an existing machine-level update notice without recomputing status or contacting PyPI.
- `vault setup-agent` now writes `agent-install/README-update-status.md`, `update-status-contract.json`, cron, and LaunchAgent templates for shared local Agent update notices.
- MCP startup guides now read existing update status first and document the no-network fallback path.
- Added a decision record for the Agent update-status install flow.

## [0.6.81] - 2026-06-24

### Added

- `vault update-status` and MCP `vault_update_status` now include `agent_update_notices`, a per-Agent advisory list showing registered runtime versions, project/private vault paths, and whether each Agent may need an upgrade or restart.
- Human-readable `vault update-status` output now prints Agent update notices so local runtimes can share the same machine-level update message.
- Added a decision record for local multi-Agent update notification through the Agent registry and `update-status.json`.

## [0.6.80] - 2026-06-24

### Added

- `vault setup-agent` now writes `agent-install/mcp-startup.json` and `agent-install/README-mcp-startup.md` so MCP-capable agents can follow the same startup order as CLI agents.
- The generated local smoke script now verifies that the MCP `core` profile includes `vault_update_status` and `vault_automation_handoff`.
- Agent setup next steps now point reviewers to the generated MCP startup guide.

## [0.6.79] - 2026-06-24

### Added

- Added MCP `vault_update_status`, matching the CLI `vault update-status` startup payload for local version, registry, shared vault, private vault, and handoff command discovery.
- Added MCP `vault_automation_handoff`, matching the CLI `vault automation handoff` read-only compact handoff flow.
- Added both startup tools to the `core` MCP profile so daily agents can begin from status and handoff before searching.

## [0.6.78] - 2026-06-24

### Added

- Added `vault setup-agent --memory-layout hybrid|shared|private`.
- Hybrid setup now creates a shared project vault plus a private Agent vault, writes `agent-install/hybrid-vault-layout.json`, and documents startup commands in `README-hybrid-vault-layout.md`.
- The local agent registry now records `memory_layout`, `private_project_dir`, and `private_db_path`.
- `vault update-status` now reports private Agent vault paths for hybrid installs.

## [0.6.77] - 2026-06-24

### Added

- Added a local multi-agent registry at `~/.vault-for-llm/agent-registry.json`.
- Added `vault agent register`, `vault agent list`, and `vault agent status` for local Agent/runtime registration.
- Added `vault update-status` so Agents can see the installed Vault version, optional latest-version comparison, registered Agents, project vaults, and startup handoff commands.
- `vault setup-agent` now registers the configured Agent automatically and adds `vault update-status` to setup next steps.

## [0.6.76] - 2026-06-24

### Added

- Generated memory automation schedule README files now include a "Next agent startup handoff" command using `vault automation handoff --project-dir ...`.
- `vault setup-agent` next steps now remind the next agent to start from `vault automation handoff` when memory automation schedules are generated.
- The generated README safety checklist now names `vault automation handoff` as the read-only startup command for scheduled-agent handoffs.

## [0.6.75] - 2026-06-24

### Added

- Added `vault automation handoff`, a read-only command that prints the latest compact automation handoff for the next agent.
- The handoff command prefers `reports/automation/cycle-latest.md`, then falls back to `cycle-latest.json` or `inbox-latest.json`.
- Added path validation for custom handoff reads so automation handoff files must stay under `reports/automation`.

## [0.6.74] - 2026-06-24

### Added

- Added `priority_brief`, `suggested_next_tasks`, and `agent_start_prompt` to the `cycle-latest.json` workspace handoff.
- Expanded `cycle-latest.md` into a daily agent handoff with Priority Brief, Suggested Next Tasks, and Agent Start Prompt sections.
- The new handoff sections preserve the existing safety boundary: raw candidate content stays hidden, transcript paths remain metadata-only, and the prompt reminds agents not to auto-promote or hard-delete memory.

## [0.6.73] - 2026-06-24

### Added

- `vault automation cycle --write-workspace` now writes `reports/automation/cycle-latest.md` alongside `cycle-latest.json`.
- The Markdown workspace handoff summarizes candidate review, metadata-only transcript paths, curation policy, safety flags, and next action without exposing raw candidate or transcript content.
- Generated automation schedule README files now document the Markdown companion when `--automation-write-workspace` is enabled.

## [0.6.72] - 2026-06-24

### Added

- Added `--automation-write-workspace` and `--automation-workspace-inbox-limit` to `vault setup-agent` / `vault install-agent`.
- Generated cron, LaunchAgent, and n8n automation schedules can now opt into `vault automation cycle --write-workspace`, producing `reports/automation/cycle-latest.json` during scheduled cycle runs.
- Interactive agent setup now asks whether scheduled cycle jobs should write the compact cycle workspace only after the user opts into memory automation schedules.

## [0.6.71] - 2026-06-24

### Added

- Added `vault automation cycle --write-workspace`, which writes `reports/automation/cycle-latest.json` as a compact next-agent workbench.
- Cycle workspace output includes candidate review queue, optional metadata-only transcript paths via `--include-transcripts`, and bounded learning-policy summary.
- Added CLI flags `--workspace-path`, `--inbox-limit`, `--include-transcripts`, and `--transcript-limit` for cycle workspace generation.

## [0.6.70] - 2026-06-24

### Added

- Added `--automation-include-transcripts` and `--automation-transcript-limit` to `vault setup-agent` / `vault install-agent`, so generated cron, LaunchAgent, and n8n automation schedules can opt into metadata-only uncaptured transcript hints.
- Generated memory automation README templates now document whether scheduled handoffs include transcript hints and reiterate that discovery does not read transcript contents.
- Interactive agent setup now asks whether scheduled inbox handoffs should include uncaptured transcript hints only after the user opts into memory automation schedules.

## [0.6.69] - 2026-06-24

### Added

- Added optional transcript discovery hints to `vault automation inbox` via `--include-transcripts`, keeping discovery metadata-only and content-free.
- Added `include_transcripts` and `transcript_limit` to MCP `vault_automation_inbox`, so review agents can see uncaptured session exports in the same compact handoff.
- Inbox handoff JSON can now include `transcript_discovery` and `summary.uncaptured_transcripts` when explicitly requested.

## [0.6.68] - 2026-06-24

### Added

- Added `vault capture discover`, a privacy-safe transcript discovery command that ranks likely JSONL/Markdown/text session exports without reading their contents.
- Added MCP tool `vault_capture_discover` to the review and maintenance profiles so agents can find likely transcripts before calling `vault_capture_session`.
- Discovery returns `capture_path`, source-system hints, format hints, size, modified time, and next-command guidance while keeping transcript content out of the payload.

## [0.6.67] - 2026-06-24

### Added

- Added MCP tool `vault_capture_session` to the review and maintenance profiles, giving reviewer agents a preview-first path from session transcripts into gated memory candidates.
- MCP session capture defaults to dry-run preview, requires `write_candidates=true` before writing `memory_candidates`, and never promotes active knowledge.
- MCP session capture constrains transcript paths to the current project by default; absolute paths require explicit `allow_absolute_path=true`.

## [0.6.66] - 2026-06-24

### Added

- Added `--write-handoff` to `vault automation inbox`, writing `reports/automation/inbox-latest.json` for the next scheduled agent or reviewer.
- Scheduled automation templates now run the selected `vault automation cycle|run` command and then write the inbox handoff in cron, LaunchAgent, and n8n templates.
- Added MCP tool `vault_automation_inbox` to the review and maintenance profiles so agents can read the compact automation review queue without loading raw candidate content.

## [0.6.65] - 2026-06-24

### Added

- Added `vault automation inbox`, a compact read-only review queue for candidate memories and the latest automation report.
- The inbox prioritizes privacy-blocked, sensitive, duplicate, weak-quality, and automation-generated candidates while hiding candidate content by default.
- Added CLI and regression coverage for the inbox summary, redacted optional content output, and human-readable review queue.

## [0.6.64] - 2026-06-24

### Fixed

- Hardened privacy scanning for standalone `sk-...` API-key shaped tokens, so session-capture previews and candidate-write responses redact these values even when transcripts do not include an `api_key =` label.
- Added regression coverage for standalone API-key detection and session-capture preview redaction.

## [0.6.63] - 2026-06-24

### Added

- Added `vault capture session`, a deterministic transcript-to-candidate extractor for Codex/Hermes/OpenClaw/Claude-style JSONL, Markdown, and text session exports.
- Added dry-run previews for captured session memories, including gate status, capture score, source reference, and content previews without writing active knowledge.
- Added opt-in `--write-candidates` support so captured decisions, pitfalls, workflows, and source-of-truth lines enter `memory_candidates` through the existing privacy, duplicate, metadata, and quality gates.
- Added tests for dry-run capture, candidate writes, nested JSONL content, privacy rejection, and the CLI path.

### Changed

- Updated install examples and release claim checks for `0.6.63`.

## [0.6.62] - 2026-06-23

### Added

- Added `vault remote doctor`, a read-only Supabase remote-reader health check that verifies search, UUID/integer IDs, guarded readable-entry RPCs, Document Map nodes, claims, content access, map, and bounded read in one command.
- Added structured failure modes and next actions for remote-reader setup issues, so hosted agents can report whether the missing piece is search RPC, readable-entry RPC, Document Map rows, claims, content, or bounded reads.
- Added test coverage for the successful remote doctor path, missing Document Map rows, missing guarded RPCs, and CLI JSON output.

### Changed

- Updated install examples and release claim checks for `0.6.62`.

## [0.6.61] - 2026-06-23

### Fixed

- Fixed Supabase remote reader workflows when `vault_remote_search` returns UUID IDs instead of local integer IDs.
- Updated `vault remote map/read` and the matching MCP tools to accept positive integer IDs or Supabase UUIDs, while keeping malformed strings rejected.
- `vault remote map/read` now accept the same `--agent-id`, `--include-private`, and `--max-sensitivity` policy arguments as `vault remote search`.

## [0.6.60] - 2026-06-23

### Added

- Added `vault candidate-review` so agents and users can explicitly mark a memory candidate as `rejected` or `blocked` and record the reason as auditable feedback.
- Added MCP tool `vault_memory_review` to the review, maintenance, and full tool profiles for candidate rejection/blocking without promotion.
- Added Dream consolidation candidates for duplicate groups. Dream can now propose a `consolidation_suggestion` review item when duplicate memories may deserve a merged replacement, while leaving active knowledge unchanged.

### Changed

- Dream candidate-write results now include `source`, `source_ref`, `memory_type`, and `category` so automation agents can distinguish normal cleanup suggestions from consolidation suggestions.
- Updated automation, MCP, README, and CLI docs for explicit candidate feedback and consolidation-review candidates.

## [0.6.59] - 2026-06-23

### Changed

- Changed agent-generated memory automation schedules to use `vault automation cycle` by default, so scheduled jobs evaluate reviewed candidate feedback, write bounded learning-policy hints, and then run safe automation.
- Added `--automation-command cycle|run` to `vault setup-agent` / `vault install-agent` so users can explicitly choose the scheduled automation command.
- Updated memory automation templates and setup guidance to describe the default cycle behavior while keeping `--automation-apply` as the separate opt-in for reversible archival and candidate writes.

## [0.6.58] - 2026-06-23

### Added

- Added `vault automation cycle`, a safe closed-loop command that evaluates reviewed candidate outcomes, writes a bounded learning policy, then runs policy-based automation so Dream can consume the latest curation hints.
- Added human-readable cycle output with feedback count, learning-rule count, Dream learning-policy status, candidate writes, report path, and safety principle.

### Changed

- Updated install examples and release claim checks for `0.6.58`.

## [0.6.57] - 2026-06-23

### Added

- Added Dream learning-policy ranking so `vault dream` and `vault automation run` can read `reports/automation/learning_policy.json` and annotate/sort candidate suggestions with bounded priority hints.
- Added automation report summary fields for Dream learning-policy status and applied-rule counts.

### Fixed

- Excluded `reports/automation/learning_policy.json` from `vault automation report --latest` so handoff artifacts are not mistaken for timestamped automation run reports.

### Changed

- Updated install examples and release claim checks for `0.6.57`.

## [0.6.56] - 2026-06-23

### Added

- Added bounded `learning_policy` output to `vault automation eval` so candidate outcome feedback can become machine-readable curation priority hints.
- Added `vault automation eval --write-learning-policy` to write `reports/automation/learning_policy.json` for future Dream, curator, or scheduled maintenance agents.

### Changed

- Updated install examples and release claim checks for `0.6.56`.

## [0.6.55] - 2026-06-23

### Added

- Added schema v10 `memory_feedback_events` so candidate outcomes can become auditable feedback for future automation.
- Added outcome recording for promoted, rejected, and blocked memory candidates.
- Added `vault automation eval` to summarize automation feedback by source, memory type, category, acceptance rate, and recommendation.

### Changed

- Documented the automation feedback loop as curation guidance only: it does not auto-promote candidates, hard-delete memory, or override privacy and access policy.
- Updated install examples and release claim checks for `0.6.55`.

## [0.6.54] - 2026-06-23

### Added

- Added `vault search --json` and `--pretty` so setup scripts and agents can validate search results without parsing human-readable text.
- Added an executable `agent-install/local-smoke.sh` template from `vault setup-agent` so installers can verify add, JSON search, candidate memory creation, and candidate listing on the exact configured project vault.

### Changed

- Updated generated setup-agent smoke guidance to prefer structured JSON checks and the local smoke script before optional remote integrations.
- Updated agent install documentation and integration examples for the `0.6.54` release.

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
