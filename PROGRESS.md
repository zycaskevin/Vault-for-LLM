# Vault-for-LLM Progress

## 2026-06-12 — Memory Curator MCP + Dream implemented

**Current direction:** Vault-for-LLM now has the first implementation slice for agent-facing memory operations through MCP:

1. 自動記憶：agent 先提出 memory candidate，再經 privacy / duplicate / metadata gates promote。
2. 讀取記憶：維持 search → map_show → read_range → citation 的安全讀取路徑。
3. 定時整理記憶 / 做夢：report-only dream workflow 先產生整理報告；`apply_safe` 目前是安全 no-op extension point。

**Planning artifact:** `docs/plans/2026-06-12-memory-curator-mcp-dream.md`

**Implemented artifacts:**

- Core memory curator: `vault/memory.py`, `vault/privacy.py`
- Dream engine: `vault/dream.py`
- DB migration: `memory_candidates` table, schema version 6
- CLI:
  - `vault remember`
  - `vault promote`
  - `vault dream`
- MCP:
  - `vault_memory_propose`
  - `vault_memory_promote`
  - `vault_dream_run`
  - `vault_add` kept as low-level direct write, with tool description steering autonomous agents to `vault_memory_propose`
- Docs:
  - `docs/mcp_memory_workflow.md`
  - `docs/dream_workflow.md`
  - README / zh-Hant / zh-CN updated
- Tests:
  - `tests/test_memory_curator.py`
  - `tests/test_mcp_memory.py`
  - `tests/test_dream.py`
  - schema-version/migration regressions updated for v6

**Safety fixes after review:**

- Privacy-fail proposals are rejected and stored redacted; they no longer become promotable candidates containing raw secrets.
- `vault dream --mode report` no longer creates `vault.db` when the DB is missing; it returns a zero-count warning payload instead.
- `schema_status` now treats `memory_candidates` as a required v6 table.

**Verification evidence:**

```text
PYTHONPATH=$PWD pytest -q
175 passed, 4 warnings in 12.67s
```

```text
git diff --check && PYTHONPATH=$PWD python -m py_compile vault/cli.py vault/mcp.py vault/dream.py vault/memory.py vault/privacy.py && python scripts/readme_command_smoke.py
✅ README documented command smoke passed
```

CLI smoke in a temporary vault project:

```text
remember candidate_created mem_3ab0e83f01dc
promote promoted kid 1
search_has_smoke True
map_has_nodes True
read_has_citation True
dream_report_exists True {'actions_applied': 0, 'duplicates': 0, 'metadata': 1, 'orphans': 0, 'stale': 1, 'weak': 1}
```

**Still intentionally not doing:** silent deletion, autonomous overwrite of high-trust entries, remote Supabase as source of truth, cron auto-send before sample dream report review.

**Next recommended step:** review diff, then open a scoped PR/commit for Memory Curator MCP + Dream. After merge, dogfood by wiring `vault-mcp` into a sandbox Hermes profile before using it in the main profile.
