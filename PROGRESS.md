# Guardrails Document Map Upgrade — Progress

Last updated: 2026-05-09 12:35 CST

## Current Sprint: Sprint 3 — Agent Behavior Loop + Citation Policy Harness — COMPLETED

### Goal
Ensure external agents do not merely have Document Map tools available, but are guided and tested to follow the intended reading loop:

```text
guardrails_search → guardrails_map_show → guardrails_read_range → final answer with read_range citation
```

### Scope Delivered
1. Added deterministic agent behavior policy harness in `guardrails_lite/agent_policy.py`.
2. Added `tests/test_agent_behavior_policy.py` to reject unsupported traces:
   - citation-free answers when citation is required;
   - invented citations;
   - search-only citation claims;
   - `read_range` without prior `map_show`;
   - mismatched `knowledge_id` loops.
3. Treated search-result citations as navigation hints only; final answer citations must come from `guardrails_read_range`.
4. Added additive `next_action` / `next_actions` metadata in search/map/read_range payloads.
5. Added opt-in `compact=true` support for search and map payloads without changing default output shapes.
6. Normalized MCP failure responses with `failure_mode` and actionable `next_action` metadata while preserving existing `error` values.
7. Updated `docs/document_map_upgrade_plan.md` with the Sprint 3 agent behavior contract.
8. Updated `/home/zycas/.hermes/skills/guardrails/SKILL.md` with Sprint 3 citation policy discipline.

### Guardrails Observed
- Document-first: this file was updated before feature implementation.
- TDD: behavior/payload tests were added for the Sprint 3 slice.
- Surgical changes only: no Supabase sync, compile hook, dashboard metrics, or unrelated refactors were included.
- Backward compatibility: default payload shapes were preserved; compact mode is opt-in.

### Final Verification
```bash
/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m pytest \
  tests/test_agent_behavior_policy.py \
  tests/test_guardrails_mcp_map.py \
  tests/test_search_map_integration.py -q
# 12 passed in 2.04s

/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m pytest -q
# 50 passed, 2 warnings in 36.71s

git diff --check
# passed
```

Graphify was updated after verification:

```bash
/home/zycas/miniconda3/bin/graphify update .
# 947 nodes, 1736 edges, 71 communities
```

Final commit is performed after this verification block.

## Current Maintenance Pass: Full Test Environment + Repo Hygiene + Audit — COMPLETED

### Goal
Restore the project to a cleaner post-Sprint-2 working state before Sprint 3 by:
1. Auditing current repo/test/documentation state.
2. Reproducing and fixing full `pytest -q` collection blockers when they are environment/dependency related.
3. Classifying and resolving non-Sprint untracked files without mixing unrelated work into Sprint 2.

### Guardrails
- Do not start Sprint 3 feature work in this pass.
- Do not hide real product test failures behind dependency changes.
- Do not delete untracked files without evidence of what they contain.
- Keep Sprint 2 commit `970784a Add document map MCP tools` as the baseline.

### Results

#### Audit ✅
- Sprint 2 baseline remains `970784a Add document map MCP tools`.
- Graphify report was reviewed after Sprint 2; main hubs remain `GuardrailsDB`, `GuardrailsSearch`, `EmbeddingProvider`, `GuardrailsGraph`, and Document Map MCP helpers.
- Branch state observed during audit: local `main` is ahead of and behind `origin/main`; do not push/merge this maintenance commit until a sync/rebase strategy is chosen.

#### Full test environment ✅
- The earlier full-suite blockers were environment/dependency issues, not Sprint 2 product regressions.
- Correct interpreter for verification is:
  `/home/zycas/miniconda3/envs/guardrails-lite/bin/python`
- Full suite now passes with the direct interpreter:
  `45 passed`.
- Caveat: `conda run -n guardrails-lite python` can be polluted by the previously activated `/tmp/research-scrapling-tinyfish/venv-scrapling` environment in this shell. Use the direct interpreter path above for reliable verification until shell environment state is reset.

#### Untracked file classification ✅
- `_knowledge_base/` contains local research notes (`ai-website-cloner`, `scrapling-tinyfish`, `siami-reading-ghost-fields`) unrelated to Sprint 2 source changes. It is now ignored as local research/scratch material.
- `scripts/cross_validate_cloud_only.py` is a local cron-style wrapper around `scripts/cross_validate.py`. It compiles, but changes runtime behavior (`apply=True`, cloud-only, model/timeouts) and needs a separate operational review before becoming project source.
- `scripts/guardrails_gap_scanner.py` is a local daily gap-scanner draft. It compiles, but has hard-coded local paths and the docstring mentions Telegram delivery while the current implementation only prints. It needs a separate operational review before becoming project source.
- The two draft scripts are now ignored explicitly to keep Sprint maintenance commits clean.

#### Final verification ✅
- `git diff --check` passed.
- Targeted Document Map suite passed: `41 passed in 23.33s`.
- Script syntax check passed for `scripts/cross_validate.py`, `scripts/cross_validate_cloud_only.py`, and `scripts/guardrails_gap_scanner.py`.
- Full suite passed with direct interpreter: `45 passed in 33.44s`.
- Graphify was not rebuilt in this maintenance commit because no code files changed; only `.gitignore` and `PROGRESS.md` changed.

## Previous Sprint: Sprint 2 (B/E1) — COMPLETED

### Goal
Make Guardrails usable as an agent brain: search results point to Document Map spans, and MCP clients can inspect structure before reading bounded line ranges with fixed citations.

### Scope Delivered

#### B1 — Search result enrichment ✅
- Modified `guardrails_lite/guardrails_search.py`.
- Search results are enriched with Document Map metadata when available:
  - `node_uid`
  - `path`
  - `heading`
  - `line_start`
  - `line_end`
  - `best_span`
  - `best_node`
  - `citation`
  - `recommended_next_tool`
- Backward compatibility preserved: entries without populated map rows still return normally with map fields absent/empty.

#### B2 — MCP tools ✅
- Modified `guardrails_lite/guardrails_mcp.py`.
- Added MCP-callable tools:
  - `guardrails_map_show(knowledge_id)` — returns entry metadata and section structure from `knowledge_nodes`.
  - `guardrails_read_range(knowledge_id, node_uid, line_start, line_end)` — returns bounded line-numbered source content.
- Implementation remains local-first; no Supabase schema changes in Sprint 2.

#### B3 — Range limit and citation guard ✅
- `guardrails_read_range` defaults to maximum 80 lines.
- Over-limit requests return `range_too_large` and ask the caller to split ranges.
- Successful reads include a fixed citation string from the tool, e.g. `#405 Title L1-L8`.
- Agents should not invent citations; citations come from `guardrails_read_range` output.

#### E1 — Guardrails skill update ✅
- Updated `/home/zycas/.hermes/skills/guardrails/SKILL.md`.
- Added reading discipline:
  - For long knowledge entries: `search → guardrails_map_show → guardrails_read_range`.
  - Answers based on encyclopedia content should prefer `#id + line range` citations.
- Corrected CLI fallback syntax:
  - CLI: `guardrails map read <knowledge_id> --lines 12-36`
  - MCP: `guardrails_read_range` supports `node_uid` or `line_start` + `line_end`.

### Verification Results

#### Automated tests ✅
```bash
conda run -n guardrails-lite python -m pytest \
  tests/test_document_map.py \
  tests/test_document_map_cli.py \
  tests/test_search_map_integration.py \
  tests/test_guardrails_mcp_map.py -q
```

Result: `41 passed in 6.81s`

#### Manual CLI verification ✅
```bash
conda run -n guardrails-lite guardrails map show 405
conda run -n guardrails-lite guardrails map read 405 --lines 1-8
```

Verified output includes line-numbered source content and citation:
`#405 PageIndex 的可借鑑價值：Document Map + Tool-gated Reading L1-L8`

#### Manual MCP handler verification ✅
Direct `handle_tool_call()` checks passed for:
- `guardrails_map_show` with `knowledge_id=405`
- `guardrails_read_range` with `knowledge_id=405, line_start=1, line_end=8`
- `guardrails_read_range` with `knowledge_id=405, node_uid="摘要-1"`

Verified outputs include:
- tool registration names: `guardrails_map_show`, `guardrails_read_range`
- `nodes[]` from Document Map
- bounded `content`
- `content_hash`
- fixed `citation`
- node metadata when reading by `node_uid`

#### Manual search enrichment verification ✅
Keyword searches for mapped entry #405 were verified:
- Query: `PageIndex`
- Query: `先看全局地圖`

Returned enriched fields include:
- `node_uid='摘要-1'`
- `path='摘要'`
- `line_start=3`
- `line_end=3`
- `best_span='L3-L3'`
- `citation='#405 PageIndex 的可借鑑價值：Document Map + Tool-gated Reading L3-L3'`
- `recommended_next_tool='guardrails_read_range'`

Entries without map rows were also observed to remain backward-compatible with empty map fields.

#### Diff hygiene ✅
- `git diff --check` passed with no whitespace errors.

#### Full test suite note ⚠️
Full `pytest -q` was attempted but blocked during collection by existing environment dependencies unrelated to Sprint 2:
- `ModuleNotFoundError: No module named 'onnxruntime'` in `tests/test_e2e.py`
- `ModuleNotFoundError: No module named 'yaml'` in `tests/test_lite.py` and `tests/test_new_features.py`

Sprint 2 targeted tests pass.

#### Graphify update ✅
The AGENTS.md Python import command failed because the active Python environment cannot import `graphify` as a module. Correct current CLI path was found at `/home/zycas/miniconda3/bin/graphify`; code graph was updated with:

```bash
/home/zycas/miniconda3/bin/graphify update .
```

Result:
- `785 nodes`
- `1434 edges`
- `61 communities`
- Updated `graphify-out/graph.json` and `graphify-out/GRAPH_REPORT.md`

### Files Changed

#### Modified
- `guardrails_lite/guardrails_search.py`
- `guardrails_lite/guardrails_mcp.py`
- `/home/zycas/.hermes/skills/guardrails/SKILL.md`

#### Added
- `PROGRESS.md`
- `tests/test_search_map_integration.py`
- `tests/test_guardrails_mcp_map.py`

#### Preserved / Not Sprint 2
The following pre-existing untracked files were not touched:
- `_knowledge_base/`
- `scripts/cross_validate_cloud_only.py`
- `scripts/guardrails_gap_scanner.py`

### Next Sprint
Sprint 3 should focus on agent-loop behavior:
1. Ensure external agents actually follow `search → map_show → read_range`.
2. Add integration examples or harness checks that reject unsupported, citation-free answers.
3. Decide whether MCP result payloads should be more compact for high-volume agent use.

Sprint 4 remains the Supabase/schema synchronization phase and was intentionally not started in Sprint 2.
