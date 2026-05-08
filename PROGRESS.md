# Guardrails Document Map Upgrade — Progress

Last updated: 2026-05-08 21:14 CST

## Current Sprint: Sprint 2 (B/E1) — COMPLETED

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
