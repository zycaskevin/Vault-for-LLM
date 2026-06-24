# CHANGELOG

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
