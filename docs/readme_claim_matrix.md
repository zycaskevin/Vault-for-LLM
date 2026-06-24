# README Claim Matrix

Generated: 2026-06-23
Scope: public README feature/capability claims after the v0.6.84 multi-Agent update notice update. Localized README files should mirror the same maturity and non-goal language.

## Maturity Tiers

- **stable**: core local path that should work without cloud services, embeddings, Supabase, MCP, or model APIs.
- **usable**: implemented and covered by targeted tests, but payloads and agent workflows may still evolve before 1.0.
- **usable-alpha**: available and tested, but intentionally conservative or still maturing.
- **advanced optional**: useful for specific deployments, but not part of the default local path.
- **positioning**: product framing or non-goal language, not an independent runtime capability.

## Current Claim Matrix

| ID | README claim | Tier | Evidence / implementation | Verification status |
|---|---|---|---|---|
| C01 | Vault-for-LLM is local-first project memory for AI agents. | stable | Base storage is Markdown plus SQLite; `vault init/add/compile/search` works locally. | README command smoke passes. |
| C02 | Vault does not replace models, wikis, Obsidian, or hosted memory systems. | positioning | README and docs frame Vault as the governed layer between human notes and agent access. | Product positioning only. |
| C03 | Agent-driven install is the recommended path. | usable | `vault setup-agent` and `vault install-agent` generate project setup, optional feature guidance, stable venv scripts, sync templates, local agent registry entries, hybrid vault layout manifests, MCP startup guides, update-status install packs, common Agent adapter startup templates, and smoke-test next steps. | `tests/test_agent_setup.py` and `tests/test_agent_registry.py` pass; PyPI smoke is part of release closeout. |
| C04 | Manual quickstart works from PyPI. | stable | `vault-for-llm[mcp]==0.6.84` installs and exposes `vault`. | Clean Python 3.11 PyPI install smoke is part of release closeout. |
| C05 | MCP lets agents start from status/handoff, search, read bounded ranges, propose memory, and inspect stats. | usable | `vault-mcp` exposes the core tool profile: `vault_search`, `vault_read_range`, `vault_memory_propose`, `vault_stats`, `vault_update_status`, `vault_automation_handoff`. `vault_update_status` includes per-Agent update notices from the local registry, can read existing `update-status.json` with `read_status=true`, and can return `current_agent_notice` plus `startup_checklist` when `agent_id` is provided. | MCP tests and README command smoke pass. |
| C06 | L0-L3 are depth layers, not access-control boundaries by themselves. | stable docs / usable implementation | Schema supports `layer`; governance metadata handles `scope`, `sensitivity`, `owner_agent`, `allowed_agents`, `memory_type`, and expiry. | Access-policy and MCP/read tests pass. |
| C07 | Usage counters can influence ranking only as a small boost. | usable-alpha | Search uses `access_count`, `citation_count`, and `last_accessed_at` as a saturated rerank signal. | Usage/rerank tests pass. |
| C08 | Expired memory can be archived instead of deleted. | usable-alpha | `vault usage archive-expired` and automation use `status=archived`; normal search/list hide archived rows. | Usage/archive tests pass. |
| C09 | Agent session transcripts can be discovered and captured into reviewable memory candidates. | usable-alpha | `vault capture discover` and MCP `vault_capture_discover` find likely transcript exports without reading contents. `vault capture session` and MCP `vault_capture_session` parse JSONL, Markdown, and text transcripts for reusable decisions, pitfalls, workflows, and source-of-truth lines. Capture defaults to dry-run preview and writes only `memory_candidates` when `--write-candidates` / `write_candidates=true` is set. MCP discover/capture are available in review/maintenance profiles, not core, and require explicit permission for absolute external paths. | `tests/test_session_capture.py` covers discovery, preview, writes, nested JSONL, privacy rejection, and CLI dispatch. `tests/test_mcp_memory.py` covers MCP discovery, preview, explicit writes, profile visibility, and path safety. |
| C10 | Policy-based automation is report-first by default and candidate-only when it writes. | usable-alpha | `vault automation plan/run/cycle/report/inbox/handoff/eval/doctor`; reports include a dry-run diff and action ledger. `automation inbox` provides a compact read-only review queue that hides candidate content by default and prioritizes privacy-blocked, sensitive, duplicate, weak-quality, and automation-generated candidates. `vault automation inbox --include-transcripts` can add metadata-only uncaptured transcript hints without reading transcript contents. `vault automation cycle --write-workspace --include-transcripts` writes `reports/automation/cycle-latest.json` and `reports/automation/cycle-latest.md`, a compact next-agent workbench with candidate review, metadata-only transcript paths, learning-policy summary, `priority_brief`, `suggested_next_tasks`, and `agent_start_prompt`. `vault automation handoff` prints the latest compact handoff for the next agent, preferring `cycle-latest.md`, and remains read-only. `vault automation inbox --write-handoff` writes `reports/automation/inbox-latest.json`, and generated cron, LaunchAgent, and n8n schedules run it after the selected `cycle` or `run` command. `vault setup-agent --automation-write-workspace` makes generated schedules write the same compact cycle workspace during scheduled cycle runs. Generated memory automation README files include `vault automation handoff --project-dir ...` as the read-only next-agent startup command. `vault setup-agent --automation-include-transcripts` makes generated schedules include metadata-only transcript hints in scheduled handoffs. MCP `vault_automation_inbox` exposes the same compact queue to review/maintenance agents without adding it to the core profile, including optional transcript hints via `include_transcripts`. Balanced policy can pre-fill Dream and Forgetting suggestions as memory candidates only when `--apply` is used, while `automation eval` and `automation cycle` turn promoted/rejected/blocked candidate feedback into bounded curation hints. `vault candidate-review` and MCP `vault_memory_review` let reviewers record rejected/blocked feedback without promotion. Dream can write duplicate-group `consolidation_suggestion` candidates for reviewed merge/archive decisions. Automation never promotes candidates or hard-deletes rows. Generated schedule templates default to `vault automation cycle`, can opt down to `run`, and omit `--apply` unless explicitly requested. | Automation tests, Agent setup tests, Dream/MCP tests, PyPI setup-agent smoke, and full pytest passed before release. |
| C11 | Profile / Dream / Forgetting agents are guidance-first, not autonomous deletion. | usable-alpha docs | `setup-agent --features memory_agents` writes conservative guidance; automation policy remains user-owned. | Agent setup tests pass. |
| C12 | Supabase is optional sharing infrastructure, not required for core use. | advanced optional | Optional `[supabase]` extra, sync script, guarded RPC/RLS templates, remote-reader templates. | Supabase template tests and remote-reader tests pass; core smoke runs without Supabase. |
| C13 | Obsidian import/export is supported. | usable | CLI supports `vault import obsidian` and `vault export obsidian`; importer skips generated and hidden folders. | Obsidian import/export tests pass. |
| C14 | Search QA measures retrieval evidence, not final answer quality. | usable | `vault search-qa run/compare` and benchmark fixtures measure source hits, MRR, no-result, and citation-policy boundaries. | Search QA regression gate passes. |
| C15 | Semantic search and API/local embedding providers are optional and evolving. | evolving / advanced optional | `[semantic]` extra and provider config support local ONNX/Ollama/OpenAI/Cohere/Voyage paths. | Provider/unit tests and semantic smoke paths pass; not enabled by default. |
| C16 | License is Apache-2.0. | stable metadata | `pyproject.toml` and `LICENSE` use Apache-2.0. | Release parity and package metadata checks pass. |

## Public Boundary Notes

- README examples use generic role IDs such as `profile-agent`, `work-agent`, `remote-agent`, and `automation-agent`.
- No private transcript, runtime database, report artifact, local absolute user path, or secret should be committed.
- Benchmark numbers in README are described as retrieval evidence only; they are not final answer/judge scores.
- Supabase examples should never hand a service role key to normal hosted agents, Coze, n8n, or browser clients.

## Verification Commands

Recent release and README cleanup verification used:

```bash
python scripts/readme_command_smoke.py
python scripts/public_pr_gate.py
python scripts/check_release_parity.py --tag v0.6.84
python -m pytest tests/test_session_capture.py tests/test_agent_setup.py tests/test_automation.py tests/test_cli_project_dir.py tests/test_release_parity.py -q
```

For release v0.6.84, clean Python 3.11 PyPI install closeout should verify:

- `vault-for-llm[mcp]==0.6.84` installs from PyPI.
- `vault --version` returns `vault-for-llm 0.6.84`.
- `vault capture discover` lists likely transcript exports without reading transcript content.
- `vault capture session <transcript>` previews session-derived candidates and `--write-candidates` writes gated candidates only.
- MCP `vault_capture_discover` is available in review/maintenance profiles, hidden from the core profile, and returns a `capture_path` that can feed MCP `vault_capture_session`.
- MCP `vault_capture_session` is available in review/maintenance profiles, hidden from the core profile, previews by default, and writes candidates only when `write_candidates=true`.
- `vault setup-agent --automation-schedule all --automation-write-workspace --automation-include-transcripts` generates cron, LaunchAgent, n8n, and README templates that default to `vault automation cycle`, write `cycle-latest.json` plus `cycle-latest.md`, and write metadata-only transcript hints into the inbox handoff.
- Generated `README-memory-automation.md` includes `vault automation handoff --project-dir ...` as the next-agent startup command.
- `vault automation cycle --write-workspace --include-transcripts` writes compact `cycle-latest.json` and `cycle-latest.md` handoffs with candidate review, transcript paths, curation policy summary, priority brief, suggested next tasks, and agent start prompt.
- `vault automation handoff` prints the latest compact handoff and prefers `reports/automation/cycle-latest.md`.
- `vault automation plan --write-policy`, `vault automation doctor`, report-first `vault automation run`, and `vault automation cycle` work against a fresh project vault.
- `vault automation inbox --limit 5 --write-handoff` shows a compact read-only review queue and writes `reports/automation/inbox-latest.json`.
- `vault automation inbox --include-transcripts --write-handoff` adds metadata-only uncaptured transcript hints to the handoff without reading transcript contents.
- `vault setup-agent` writes `agent-install/mcp-startup.json` and `agent-install/README-mcp-startup.md`.
- MCP `vault_update_status` and `vault_automation_handoff` are available in the core profile.
- `vault update-status --latest-version <version> --json` includes `agent_update_notices` for registered runtimes.
- `vault update-status --read-status --json` and MCP `vault_update_status(read_status=true)` read existing machine-level status without recomputing.
- `vault update-status --read-status --agent codex --json` and MCP `vault_update_status(read_status=true, agent_id="codex")` include `current_agent_notice` and `startup_checklist`.
- `vault setup-agent` writes `agent-install/README-update-status.md`, `update-status-contract.json`, `update-status.cron`, and `update-status.launchagent.plist`.
- `vault setup-agent` writes `agent-install/README-agent-adapters.md`, `codex-startup.md`, `claude-code-startup.md`, `openclaw-startup.md`, `hermes-startup.md`, and `adapter-startup-contract.json`.
- MCP `vault_automation_inbox` is available in review/maintenance profiles and hidden from the core profile.
- `vault candidate-review` and MCP `vault_memory_review` record rejected/blocked feedback events.
- Dream can write `consolidation_suggestion` candidates for duplicate groups without changing active knowledge.
