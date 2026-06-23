# README Claim Matrix

Generated: 2026-06-23
Scope: public README feature/capability claims after the v0.6.54 product README cleanup. Localized README files should mirror the same maturity and non-goal language.

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
| C03 | Agent-driven install is the recommended path. | usable | `vault setup-agent` and `vault install-agent` generate project setup, optional feature guidance, stable venv scripts, sync templates, and smoke-test next steps. | `tests/test_agent_setup.py` passes; PyPI smoke is part of release closeout. |
| C04 | Manual quickstart works from PyPI. | stable | `vault-for-llm[mcp]==0.6.54` installs and exposes `vault`. | Clean Python 3.11 PyPI install smoke is part of release closeout. |
| C05 | MCP lets agents search, read bounded ranges, propose memory, and inspect stats. | usable | `vault-mcp` exposes the core tool profile: `vault_search`, `vault_read_range`, `vault_memory_propose`, `vault_stats`. | MCP tests and README command smoke pass. |
| C06 | L0-L3 are depth layers, not access-control boundaries by themselves. | stable docs / usable implementation | Schema supports `layer`; governance metadata handles `scope`, `sensitivity`, `owner_agent`, `allowed_agents`, `memory_type`, and expiry. | Access-policy and MCP/read tests pass. |
| C07 | Usage counters can influence ranking only as a small boost. | usable-alpha | Search uses `access_count`, `citation_count`, and `last_accessed_at` as a saturated rerank signal. | Usage/rerank tests pass. |
| C08 | Expired memory can be archived instead of deleted. | usable-alpha | `vault usage archive-expired` and automation use `status=archived`; normal search/list hide archived rows. | Usage/archive tests pass. |
| C09 | Policy-based automation is report-first by default and candidate-only when it writes. | usable-alpha | `vault automation plan/run/report/doctor`; reports include a dry-run diff and action ledger. Balanced policy can pre-fill Dream and Forgetting suggestions as memory candidates only when `--apply` is used, but automation never promotes candidates or hard-deletes rows. Generated schedule templates omit `--apply` unless explicitly requested. | Automation tests, Dream/MCP tests, PyPI setup-agent smoke, and full pytest passed before release. |
| C10 | Profile / Dream / Forgetting agents are guidance-first, not autonomous deletion. | usable-alpha docs | `setup-agent --features memory_agents` writes conservative guidance; automation policy remains user-owned. | Agent setup tests pass. |
| C11 | Supabase is optional sharing infrastructure, not required for core use. | advanced optional | Optional `[supabase]` extra, sync script, guarded RPC/RLS templates, remote-reader templates. | Supabase template tests and remote-reader tests pass; core smoke runs without Supabase. |
| C12 | Obsidian import/export is supported. | usable | CLI supports `vault import obsidian` and `vault export obsidian`; importer skips generated and hidden folders. | Obsidian import/export tests pass. |
| C13 | Search QA measures retrieval evidence, not final answer quality. | usable | `vault search-qa run/compare` and benchmark fixtures measure source hits, MRR, no-result, and citation-policy boundaries. | Search QA regression gate passes. |
| C14 | Semantic search and API/local embedding providers are optional and evolving. | evolving / advanced optional | `[semantic]` extra and provider config support local ONNX/Ollama/OpenAI/Cohere/Voyage paths. | Provider/unit tests and semantic smoke paths pass; not enabled by default. |
| C15 | License is Apache-2.0. | stable metadata | `pyproject.toml` and `LICENSE` use Apache-2.0. | Release parity and package metadata checks pass. |

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
python scripts/check_release_parity.py --tag v0.6.54
python -m pytest tests/test_agent_setup.py tests/test_automation.py tests/test_cli_project_dir.py tests/test_release_parity.py -q
```

For release v0.6.54, clean Python 3.11 PyPI install closeout should verify:

- `vault-for-llm[mcp]==0.6.54` installs from PyPI.
- `vault --version` returns `vault-for-llm 0.6.54`.
- `vault setup-agent --automation-schedule all` generates cron, LaunchAgent, n8n, and README templates.
- `vault automation plan --write-policy`, `vault automation doctor`, and report-first `vault automation run` work against a fresh project vault.
