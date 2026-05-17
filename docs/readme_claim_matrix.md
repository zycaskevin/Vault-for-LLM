# README Claim Matrix

Generated: 2026-05-17
Scope: public `README.md` feature/capability claims after P0/A1-A4 cleanup. The localized README files should mirror these classifications.

## Maturity tiers

- **stable**: core local path that should work without cloud services, embeddings, Supabase, MCP, or model APIs.
- **usable-alpha**: implemented and covered by targeted tests or CLI help, but APIs/payloads may still evolve.
- **experimental**: available for early testing or optional integrations; do not present as production platform, hosted service, or mature marketplace.
- **positioning**: product framing or non-goal language, not an independent runtime capability.

## Evidence reviewed

- P0/A1 output: `docs/p0_public_string_audit.md` found 9 public-boundary issues and no literal secrets or local absolute home paths.
- P0/A2 output: raw/example content and product-specific fixtures were neutralized; remaining Supabase work was deferred to A3.
- P0/A3 output: Supabase/dashboard assumptions were split; public defaults are Vault-branded and Supabase is optional sync/read target.
- P0/A4 output: `vault skill` remains visible only as an experimental local skill registry, not a hosted or mature marketplace.
- Code/docs inspected: `README.md`, `pyproject.toml`, `vault/cli.py`, `vault/db.py`, `vault/mcp.py`, `vault/embed.py`, `vault/graph.py`, `vault/search_qa.py`, `docs/agent_memory_qa_roadmap.md`.
- Verification commands run for this matrix:
  - `python -m vault.cli --help` plus `map`, `search-qa`, `skill`, and `vault.mcp --help`.
  - `python -m pytest -q tests/test_lite.py tests/test_document_map.py tests/test_document_map_cli.py tests/test_search_map_integration.py tests/test_vault_mcp_map.py tests/test_search_quality_metrics.py tests/test_new_features.py tests/test_agent_behavior_policy.py tests/test_vault_health_metrics.py` -> **75 passed**.
  - Quickstart module smoke in a temp directory with `PYTHONPATH=/home/zycas/Vault-for-LLM python -m vault.cli ...` -> init/add/compile/search succeeded.
  - Public-string grep over README/docs outside this audit doc -> no stale `Hermes`, `hermes_vault`, `delegate_task`, `.hermes`, dashboard, `gr_*`, or marketplace wording in README/docs.
  - PyPI JSON check for `vault-for-llm` -> version `0.4.0` exists and classifier is Alpha; current PyPI long description still contains pre-A4 hosted-registry wording, so republishing is a release action.

## Claim matrix

| ID | README claim | README lines | Tier | Proof / implementation | Command or test evidence | README edit before public release |
|---|---|---:|---|---|---|---|
| C01 | Vault-for-LLM is local-first memory for LLM agents and creates a portable SQLite knowledge vault. | 5-7 | stable | `pyproject.toml` package metadata names `vault-for-llm`; `vault/db.py` creates local SQLite tables; `vault/cli.py init` creates a local project vault. | Quickstart module smoke completed init/add/compile/search; targeted pytest suite passed. | None. |
| C02 | Users add Markdown notes, compile them into searchable structured memory, and agents query through CLI or MCP. | 7, 17-20 | stable for CLI; usable-alpha for MCP | `vault/cli.py` implements `add`, `compile`, `search`; `vault/mcp.py` exposes public `vault_*` tool helpers. | CLI help lists `add`, `compile`, `search`; MCP help works; MCP map tests passed. | None; keep MCP alpha/optional wording. |
| C03 | Vault is not a notes-app replacement; it makes notes usable by agents. | 22 | positioning | Supported by the architecture and CLI/MCP design, but this is product framing rather than a separate feature. | N/A beyond code/docs. | None. |
| C04 | Vault is evolving into an agent memory QA layer rather than just another vector store. | 28-36 | positioning / roadmap | `docs/agent_memory_qa_roadmap.md` defines the public position and maturity model; Search QA, Document Map, freshness, dedup, convergence, and cross-validation exist as CLI surfaces. | CLI help lists quality commands; targeted quality tests passed. | None while wording stays “evolving into.” Do not rephrase as a complete managed QA platform. |
| C05 | Local by default: SQLite is the source of truth; no cloud required for core usage. | 42, 46, 268-270 | stable | Base dependencies are local (`pyyaml`, `sqlite-vec`); Supabase is optional and only used by scripts/MCP remote helpers when configured. | Quickstart smoke used local SQLite only; A3 no-Supabase smoke passed per handoff. | None. |
| C06 | Works without embeddings: keyword search works first; semantic search is optional. | 43, 56, 112-126 | stable for keyword; experimental for semantic | `VaultSearch.search_keyword` and `search` support keyword mode; `pyproject.toml` puts ONNX stack behind `[semantic]`; `vault/embed.py` implements ONNX/Ollama providers. | `tests/test_lite.py` covers keyword search and vector fallback; targeted pytest passed. | None. |
| C07 | Agent-oriented memory layers L0/L1/L2/L3 are part of the architecture. | 44, 58, 87-92, 185-199 | stable | `vault init` creates `L0-identity`, `L1-core-facts`, `L2-context`, `L3-knowledge`; knowledge rows have a `layer` field. | CLI parser accepts `--layer` choices; quickstart/pytest passed. | None. |
| C08 | Bounded retrieval / Document Map lets agents navigate sections and read source ranges. | 45, 60, 74, 217-219, 255-262 | usable-alpha | `vault/docmap.py`, `vault/mcp.py`, and CLI `vault map build/show/read/query` implement section maps, claim maps, and bounded reads. | `vault map --help`; `tests/test_document_map.py`, `tests/test_document_map_cli.py`, `tests/test_search_map_integration.py`, `tests/test_vault_mcp_map.py` passed. | None; current “usable, still evolving” language is accurate. |
| C09 | Optional Supabase sync is an optional sync/read target, not required infrastructure. | 46, 63, 266-278 | experimental | A3 changed public defaults to Vault-branded table names with `VAULT_SUPABASE_*_TABLE` overrides; scripts import gracefully without Supabase where possible. | A3 handoff records no-Supabase script smoke; README grep has no dashboard/private table defaults. | None. |
| C10 | Alpha, CLI-first developer-facing tool with rough edges/evolving APIs. | 47, 70-81, 282-289 | positioning | `pyproject.toml` classifier is `Development Status :: 3 - Alpha`; roadmap maturity table separates stable/usable-alpha/experimental. | PyPI JSON classifier is Alpha; README contains explicit alpha wording. | None. |
| C11 | Knowledge storage: Markdown `raw/` files compiled into local SQLite. | 55, 93, 156-163, 185-199, 210-211 | stable | `VaultCompiler.compile` reads Markdown files; `VaultDB` stores knowledge in SQLite. | `tests/test_lite.py::test_compile_and_search` covered compile/search; quickstart smoke compiled a raw entry. | None. |
| C12 | Search supports keyword search. | 56, 160, 212 | stable | `VaultSearch.search_keyword`; CLI `search --keyword-only`. | Quickstart smoke found the added note with keyword search; targeted tests passed. | None. |
| C13 | Search supports optional vector and hybrid search. | 56, 117-126, 212 | usable-alpha | `VaultSearch.search_vector` and `search_hybrid`; embeddings are optional providers. | `tests/test_lite.py` verifies fallback when vector dimension mismatches; CLI help lists `--mode auto|keyword|vector|hybrid`. | None, but keep “optional” wording. |
| C14 | Optional ONNX Runtime or Ollama embeddings are supported. | 57, 112-126 | experimental | `vault/embed.py` implements `ONNXEmbeddingProvider` and `OllamaEmbeddingProvider`; semantic dependencies are optional extras. | CLI help lists `install-embedding`; tests avoid requiring optional model installs. | None. Do not imply embeddings are installed by default. |
| C15 | Knowledge graph has inferred entities/edges and graph expansion. | 59, 213, 220-221 | usable-alpha | `vault/graph.py` infers entities/edges; CLI `graph build/show/export/link/unlink/clear/expand`; search has `--graph-expand`. | CLI help lists `graph`; targeted `test_new_features.py` passed. | None. |
| C16 | MCP server exposes search/add/stats/map/read tools and optional remote read tools. | 61, 128-132, 233-263 | usable-alpha | `pyproject.toml` exposes `vault-mcp`; `vault/mcp.py` routes public `vault_*` tools and optional remote aliases. | `python -m vault.mcp --help`; `tests/test_vault_mcp_map.py` passed. | None; keep optional MCP install section. |
| C17 | Quality tools include lint, freshness, convergence, cross-validation, dedup, and Search QA snapshots. | 62, 68-81, 216-226 | mixed: Search QA usable-alpha; most others experimental | CLI parser exposes all listed commands; `vault/search_qa.py` implements deterministic snapshots and comparisons. | CLI help lists all commands; `tests/test_search_quality_metrics.py` and `tests/test_new_features.py` passed. | None because README table explicitly marks these alpha/experimental. |
| C18 | Local skill registry via `vault skill` is experimental, local-only, and not a hosted marketplace. | 64, 79, 227 | experimental | A4 neutralized README/CLI wording; `vault/db.py` has local `skills` table; CLI defaults are `vault-cli` and local registry commands. | `vault skill --help`; README/docs grep found no marketplace wording outside the historical audit doc. | None in repo README. Release action: republish package metadata because current PyPI long description still has old hosted-registry wording. |
| C19 | Stable path is `vault init` -> `vault add` -> `vault compile` -> `vault search` -> `vault-mcp`. | 81, 291-298 | stable for first four commands; usable-alpha for MCP | CLI implements core commands; MCP entry point exists. | Quickstart module smoke verified init/add/compile/search; MCP help works. | None; consider wording “then optionally `vault-mcp`” if future reviewers want stricter stable-only path. |
| C20 | Installation from PyPI is available. | 100-110, 282-289 | stable release artifact | PyPI JSON for `vault-for-llm` returns version `0.4.0`; `pyproject.toml` declares console scripts and extras. | PyPI JSON check succeeded. | No README edit needed, but release checklist must publish a new build after A1-A4 so PyPI README/long description is not stale. |
| C21 | Optional semantic extra installs ONNX dependencies; `vault install-embedding --model mix` exists. | 112-119 | experimental | `pyproject.toml` `[project.optional-dependencies].semantic`; `vault/cli.py install-embedding` parser. | CLI help lists `install-embedding`; no optional model download was run. | None. |
| C22 | Optional MCP extra installs MCP dependencies; `vault-mcp --project-dir` exists. | 128-133, 235-251 | usable-alpha | `pyproject.toml` `[mcp]` extra and `vault-mcp` script; MCP parser has `--project-dir`. | `python -m vault.mcp --help` lists `--project-dir`; MCP tests passed. | None. |
| C23 | Development install from source uses the public GitHub repo and editable dev extra. | 135-143, 302-309 | stable docs / release workflow | `pyproject.toml` defines `[dev]`; repo owner URL is intentional per A1 low-severity note if canonical. | A1 accepted `zycaskevin` as acceptable if canonical public owner. | None unless release should move to an organization URL. |
| C24 | Users can add Markdown files directly under `raw/` and run `vault compile`. | 163-181 | stable | `VaultCompiler` scans raw Markdown; `vault init` creates `raw/`. | Quickstart smoke and `test_compile_and_search` passed. | None. |
| C25 | CLI reference commands exist: init, doctor, add, import, compile, search, list, stats, lint, map, graph, converge, cross-validate, freshness, dedup, search-qa, skill. | 202-229 | mixed by feature tier | `vault/cli.py` parser registers all listed commands. | `python -m vault.cli --help` listed all commands. | None. |
| C26 | Current MCP tools include `vault_search`, `vault_add`, `vault_stats`, `vault_map_show`, `vault_read_range`, plus optional remote map/read tools. | 255-263 | usable-alpha; remote tools experimental | `vault/mcp.py` public tool routing and remote helper functions. | `tests/test_vault_mcp_map.py` includes public tool listing/routing and remote read/map tests. | None. |
| C27 | Current maturity section says advanced features and Supabase sync are evolving and APIs/schemas may change. | 282-289 | positioning | Matches roadmap maturity model and A3/A4 decisions. | PyPI classifier Alpha; README explicitly warns about evolving APIs. | None. |
| C28 | License is MIT. | 315-317 | stable metadata | `pyproject.toml` license text is MIT. | Metadata inspection. | None. |

## README edits / release actions identified

1. **No in-repo English README feature claim is unclassified** in this matrix.
2. **No required README wording edit remains** for P0/B1 based on the reviewed English README: experimental features are labelled, Supabase is optional, and `vault skill` is local-only/experimental.
3. **Release action, not a README edit:** PyPI currently serves an older long description containing pre-A4 hosted-registry wording. Before public release, publish a new package build (likely with a version bump, since PyPI does not allow replacing an existing release file) so the public package page matches the cleaned README.
4. **Release verification action:** run a clean virtualenv install (`pip install vault-for-llm`) and verify the `vault` console script resolves to this package. In this worker environment, `vault` on `PATH` points to an unrelated broken console script, so local smoke verification used `python -m vault.cli` with `PYTHONPATH` instead.
5. If the canonical public repository will move away from `zycaskevin/Vault-for-LLM`, update the clone URL in all README variants; otherwise A1 already classifies the current owner string as acceptable.

## Coverage statement

All public `README.md` feature/capability claims reviewed for P0/B1 have one of: stable, usable-alpha, experimental, or positioning classification. Claims without direct runtime tests are explicitly classified as positioning or release/process metadata, so no unproven runtime capability remains unclassified.
