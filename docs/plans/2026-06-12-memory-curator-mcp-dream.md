# Memory Curator MCP + Dream Implementation Plan

> **For Hermes:** Use `profile-agent-task-protocol` + `writing-plans` before implementation. For coding execution, use subagent-driven-development task-by-task and verify every MCP tool with real calls.

**Goal:** Let agents use Vault-for-LLM through MCP to safely remember knowledge, read knowledge with citations, and periodically curate memory through a scheduled “dream” workflow.

**Architecture:** Keep SQLite + Markdown `raw/` as the local source of truth. Add a policy-driven memory layer above existing `vault_add`, `vault_search`, `vault_map_show`, and `vault_read_range`: propose → gate → write candidate → promote. Add dream jobs as deterministic CLI/MCP workflows that produce reports first, then optionally apply safe changes with explicit policy flags.

**Tech Stack:** Python 3.10+, SQLite, existing `vault.db`, `vault.mcp`, `vault.cli`, pytest, optional Hermes cron/native MCP integration.

---

## Scope Boundary

### In scope for next phase

1. **MCP automatic memory**
   - Agent can propose memory through MCP.
   - System classifies layer/category/tags/trust/source.
   - System performs duplicate and privacy checks before durable write.
   - Default write path is candidate/report-first, not silent promotion.

2. **MCP memory reading**
   - Keep current search → map_show → read_range policy.
   - Improve tool descriptions and tests so agents naturally cite only `vault_read_range` output.
   - Add explicit read workflow smoke tests.

3. **Dream / scheduled curation**
   - Scheduled workflow scans stale, duplicate, weak, and unconverged entries.
   - Produces a dream report.
   - Safe mode default: report-only.
   - Apply mode requires explicit flags and keeps backup/rollback.

4. **Operational docs and tests**
   - CLI + MCP contracts documented.
   - Unit/integration tests for memory proposal, candidate promotion, dream report generation, and MCP read/write workflow.

### Out of scope for this phase

- Fully autonomous deletion of knowledge.
- Silent overwriting of high-trust human-authored entries.
- Remote Supabase as source of truth.
- LLM-dependent curation as the only path; deterministic gates must work without cloud LLM.
- Production cron auto-send before sample report is reviewed.

---

## Product Model

### Three user-facing capabilities

| Capability | Agent-facing MCP tool | CLI command | Default safety |
|---|---|---|---|
| Remember | `vault_memory_propose`, `vault_memory_promote` | `vault remember`, `vault promote` | Candidate-first |
| Read | `vault_search`, `vault_map_show`, `vault_read_range` | `vault search`, `vault map show/read` | Citation-gated |
| Dream | `vault_dream_run`, `vault_dream_report` | `vault dream` | Report-only |

### Memory states

```text
candidate → approved/promoted → active → stale/review_needed → superseded/archived
```

### Trust defaults

| Source | Default trust | Notes |
|---|---:|---|
| Raw chat/session extraction | 0.4 | Must be candidate unless explicitly approved |
| Agent-inferred summary | 0.5 | Needs source and duplicate check |
| User explicitly says remember/write | 0.8 | Can promote after privacy/dup checks |
| Human-edited docs | 0.9 | Do not overwrite silently |
| Verified test/command evidence | 0.8–0.95 | Include evidence block |

---

## Target MCP Contract

### `vault_memory_propose`

Purpose: agent submits a possible memory without immediately polluting the active vault.

Input schema:

```json
{
  "type": "object",
  "properties": {
    "title": {"type": "string"},
    "content": {"type": "string"},
    "source": {"type": "string", "default": "mcp"},
    "source_ref": {"type": "string", "default": ""},
    "layer": {"type": "string", "enum": ["L0", "L1", "L2", "L3"], "default": "L3"},
    "category": {"type": "string", "default": "general"},
    "tags": {"type": "string", "default": ""},
    "trust": {"type": "number", "default": 0.5},
    "reason": {"type": "string", "description": "Why this is worth remembering"},
    "mode": {"type": "string", "enum": ["candidate", "promote_if_safe"], "default": "candidate"}
  },
  "required": ["title", "content", "reason"]
}
```

Output:

```json
{
  "status": "candidate_created|promoted|rejected",
  "candidate_id": "...",
  "knowledge_id": 123,
  "gates": {
    "privacy": "pass|warn|fail",
    "duplicate": "pass|warn|fail",
    "metadata": "pass|warn|fail"
  },
  "next_action": {"tool": "vault_memory_promote", "arguments": {"candidate_id": "..."}}
}
```

### `vault_memory_promote`

Purpose: promote a candidate into `raw/` + SQLite after safety gates.

Inputs:

```json
{
  "candidate_id": "string",
  "confirm": true,
  "compile": true,
  "build_map": true
}
```

Rules:

- Requires candidate exists.
- Runs privacy check again.
- Runs duplicate check again.
- Writes Markdown to `raw/`.
- Inserts/updates SQLite through existing compiler path where possible.
- Builds Document Map for promoted entry.
- Returns readback evidence.

### `vault_dream_run`

Purpose: run curation pass.

Inputs:

```json
{
  "mode": "report|apply_safe",
  "checks": ["freshness", "dedup", "convergence", "metadata", "orphans"],
  "limit": 50,
  "write_report": true,
  "backup": true
}
```

Default: `mode=report`.

Output:

```json
{
  "report_path": "reports/dream/YYYY-MM-DD-HHMMSS.md",
  "summary": {
    "stale": 3,
    "duplicates": 2,
    "weak": 5,
    "actions_applied": 0
  },
  "next_action": "Review report, then rerun with apply_safe if desired"
}
```

---

## File/Module Plan

### New modules

- `vault/memory.py`
  - candidate creation
  - metadata normalization
  - privacy gate orchestration
  - duplicate gate orchestration
  - promotion workflow

- `vault/dream.py`
  - report-only dream run
  - safe apply hooks
  - report renderer
  - backup integration

- `vault/privacy.py`
  - deterministic secret/PII scanner
  - returns structured pass/warn/fail payload

- `tests/test_memory_curator.py`
  - proposal, candidate, promotion, duplicate/privacy gates

- `tests/test_dream.py`
  - dream report and apply-safe no-op behavior

- `tests/test_mcp_memory.py`
  - MCP tool list and real handle_tool_call flows

### Existing files to modify

- `vault/mcp.py`
  - add `vault_memory_propose`
  - add `vault_memory_promote`
  - add `vault_dream_run`
  - keep old `vault_add` for compatibility, but mark as lower-level/direct write

- `vault/cli.py`
  - add `vault remember`
  - add `vault promote`
  - add `vault dream`

- `README.md`, `README.zh-Hant.md`, `README.zh-CN.md`
  - document agent memory workflow
  - document safe dream schedule

- `docs/`
  - add MCP memory workflow doc
  - add dream workflow doc

---

## Implementation Tasks

### Task 1: Add memory candidate storage model

**Objective:** Store proposed memories separately from active knowledge.

**Files:**
- Modify: `vault/db.py`
- Create: `tests/test_memory_curator.py`

**Design:** Add a `memory_candidates` table through existing migration mechanism.

Columns:

```text
id TEXT PRIMARY KEY
created_at TEXT NOT NULL
updated_at TEXT NOT NULL
title TEXT NOT NULL
content TEXT NOT NULL
layer TEXT NOT NULL
category TEXT NOT NULL
tags TEXT NOT NULL
trust REAL NOT NULL
source TEXT NOT NULL
source_ref TEXT NOT NULL
reason TEXT NOT NULL
status TEXT NOT NULL
privacy_status TEXT NOT NULL
duplicate_status TEXT NOT NULL
gate_payload_json TEXT NOT NULL
promoted_knowledge_id INTEGER
```

**Verification:**

```bash
pytest tests/test_db_migrations.py tests/test_memory_curator.py -q
```

Expected: migration tests pass and candidate CRUD tests pass.

---

### Task 2: Implement deterministic privacy gate

**Objective:** Prevent obvious secrets/private data from entering durable memory silently.

**Files:**
- Create: `vault/privacy.py`
- Test: `tests/test_memory_curator.py`

**Rules:**

- Fail: API keys, GitHub tokens, private keys, bearer tokens, passwords.
- Warn: emails, phone-like strings, URLs with query tokens.
- Pass: no finding.

**Output shape:**

```json
{
  "status": "pass|warn|fail",
  "findings": [{"type": "github_token", "severity": "fail", "span": "redacted"}]
}
```

**Verification:**

```bash
pytest tests/test_memory_curator.py::test_privacy_gate_blocks_tokens -q
```

---

### Task 3: Implement duplicate gate

**Objective:** Candidate write should warn/fail when it duplicates existing active knowledge.

**Files:**
- Create/modify: `vault/memory.py`
- Test: `tests/test_memory_curator.py`

**Approach:**

- Reuse existing search/dedup functions where practical.
- At minimum compare title normalized exact match and content hash.
- If semantic index is available, add semantic similarity warning.

**Verification:**

```bash
pytest tests/test_memory_curator.py::test_duplicate_gate_warns_on_same_title -q
```

---

### Task 4: Implement `vault remember` CLI

**Objective:** Create candidate memories from CLI with gate output.

**Files:**
- Modify: `vault/cli.py`
- Modify: `vault/memory.py`
- Test: `tests/test_memory_curator.py`

**Command:**

```bash
vault remember "Title" --content "..." --reason "Maintainer said this is a reusable workflow" --mode candidate
```

**Verification:**

```bash
vault remember "Smoke memory" --content "A tiny smoke test memory." --reason "CLI smoke" --mode candidate
vault list
```

Expected: candidate created; active knowledge unchanged until promotion.

---

### Task 5: Implement `vault promote` CLI

**Objective:** Promote a candidate through gates into active raw/SQLite memory.

**Files:**
- Modify: `vault/cli.py`
- Modify: `vault/memory.py`
- Test: `tests/test_memory_curator.py`

**Command:**

```bash
vault promote <candidate_id> --confirm --compile --build-map
```

**Acceptance:**

- Writes `raw/<safe-slug>.md` with frontmatter.
- Inserts/updates active knowledge.
- Runs compile/map build.
- Returns knowledge ID and readback citation path.

**Verification:**

```bash
pytest tests/test_memory_curator.py::test_promote_candidate_writes_raw_and_active_db -q
```

---

### Task 6: Add MCP memory tools

**Objective:** Agents can propose and promote memory through MCP.

**Files:**
- Modify: `vault/mcp.py`
- Test: `tests/test_mcp_memory.py`

**Tools:**

- `vault_memory_propose`
- `vault_memory_promote`

**Compatibility rule:** Keep `vault_add`, but update description to “direct low-level add; prefer vault_memory_propose for autonomous agents”.

**Verification:**

```bash
pytest tests/test_mcp_memory.py -q
```

Test should call `handle_tool_call("vault_memory_propose", ...)` and inspect JSON result.

---

### Task 7: Harden MCP read workflow tests

**Objective:** Make sure agents read memory in the right order.

**Files:**
- Modify/create: `tests/test_mcp_memory.py`
- Possibly modify: `vault/agent_policy.py`

**Workflow:**

```text
vault_search → vault_map_show → vault_read_range → final answer citation
```

**Verification:**

```bash
pytest tests/test_mcp_memory.py::test_mcp_read_workflow_returns_read_range_citation -q
pytest tests/test_agent_policy.py -q
```

---

### Task 8: Implement dream report engine

**Objective:** Produce scheduled curation reports without modifying memory by default.

**Files:**
- Create: `vault/dream.py`
- Modify: `vault/cli.py`
- Test: `tests/test_dream.py`

**Checks:**

- freshness
- dedup
- convergence
- metadata quality
- candidates older than N days

**Command:**

```bash
vault dream --mode report --limit 50 --write-report
```

**Report path:**

```text
reports/dream/YYYY-MM-DD-HHMMSS.md
```

**Verification:**

```bash
pytest tests/test_dream.py -q
vault dream --mode report --limit 5 --write-report
```

Expected: report file exists and contains summary counts + recommended actions.

---

### Task 9: Add MCP dream tool

**Objective:** Let Hermes/native MCP agents run dream curation through MCP.

**Files:**
- Modify: `vault/mcp.py`
- Test: `tests/test_mcp_memory.py`

**Tool:** `vault_dream_run`

**Default:** report-only.

**Verification:**

```bash
pytest tests/test_mcp_memory.py::test_mcp_dream_run_report_only -q
```

---

### Task 10: Add scheduling docs and Hermes config example

**Objective:** Document how to run dream periodically through Hermes cron or system cron.

**Files:**
- Create: `docs/mcp_memory_workflow.md`
- Create: `docs/dream_workflow.md`
- Modify: `README.md`, `README.zh-Hant.md`, `README.zh-CN.md`

**Example Hermes MCP config:**

```yaml
mcp_servers:
  vault:
    command: "vault-mcp"
    args: ["--project-dir", "/path/to/vault"]
    timeout: 120
    connect_timeout: 60
```

**Example dream cron command:**

```bash
vault dream --mode report --limit 50 --write-report
```

**Verification:**

```bash
python scripts/readme_command_smoke.py
pytest -q
```

---

## Acceptance Criteria

### Automatic memory

- [ ] Agent can call MCP `vault_memory_propose` and get candidate result.
- [ ] Candidate creation does not alter active knowledge unless promoted.
- [ ] Privacy fail blocks promotion.
- [ ] Duplicate warning is visible before promotion.
- [ ] Promotion writes raw Markdown and active SQLite entry.
- [ ] Promoted entry is searchable.

### Read memory

- [ ] Agent can call search → map_show → read_range.
- [ ] `vault_read_range` returns exact citation.
- [ ] Policy rejects final citations not emitted by `vault_read_range`.

### Dream

- [ ] CLI `vault dream --mode report` creates a report.
- [ ] MCP `vault_dream_run` returns report path and summary.
- [ ] Report-only mode makes no active DB/raw changes except report artifact.
- [ ] Apply-safe mode requires backup and never deletes knowledge.

### Docs / operations

- [ ] README documents current recommended MCP tools.
- [ ] Dream scheduling documented as report-first.
- [ ] Rollback path documented using `vault db backup/restore`.
- [ ] Tests pass.

---

## Risk Matrix

| Risk | Level | Mitigation |
|---|---|---|
| Agent writes noisy low-value memories | High | candidate-first, reason required, trust defaults low |
| Secrets/PII written to memory | High | deterministic privacy gate before candidate and promotion |
| Duplicate/contradictory memories accumulate | Medium | duplicate gate + dream dedup report |
| Dream modifies good knowledge incorrectly | High | report-only default, apply-safe only, backup required |
| Search snippets treated as citations | Medium | existing policy + tests require read_range citation |
| MCP tool surface confuses agents | Medium | tool descriptions prefer propose/read_range; deprecate direct add for autonomous agents |

---

## Recommended Start Sequence

1. Candidate table + memory module.
2. Privacy gate.
3. Duplicate gate.
4. CLI `remember/promote`.
5. MCP `vault_memory_propose/promote`.
6. Dream report engine.
7. MCP `vault_dream_run`.
8. Docs + scheduling examples.
9. Full test/readme smoke.

---

## Definition of Done

The phase is done only when this real smoke works:

```bash
# 1. propose memory
vault remember "MCP memory smoke" \
  --content "Agents should use vault_memory_propose before durable writes." \
  --reason "Smoke test for autonomous memory workflow" \
  --mode candidate

# 2. promote memory
vault promote <candidate_id> --confirm --compile --build-map

# 3. read memory
vault search "autonomous memory workflow"
vault map show <knowledge_id>
vault map read <knowledge_id> --line-start 1 --line-end 20

# 4. dream report
vault dream --mode report --limit 5 --write-report

# 5. tests
pytest -q
```

And the MCP equivalent passes through `handle_tool_call` tests.
