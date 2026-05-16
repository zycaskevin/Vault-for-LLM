# Document Map Guide

Document Map is Vault-for-LLM's bounded-reading layer for long knowledge entries.

Instead of asking an agent to read an entire long note, Vault can parse the note into sections and claims. Agents can first inspect the map, then read a specific line range with a stable citation.

---

## Problem

Search results are good for discovery, but they are not enough for citation-safe answers:

1. A search result may only show a short preview.
2. A long note may contain many unrelated sections.
3. Agents can accidentally treat search snippets as verified citations.
4. Dumping full files into context is expensive and noisy.

Document Map creates an intermediate navigation layer.

---

## Data model

Document Map uses two local SQLite table families:

| Concept | Purpose |
|---|---|
| `knowledge_nodes` | Section-level map: headings, line ranges, summaries |
| `knowledge_claims` | Claim-level records connected to source spans |

The local SQLite database remains the source of truth. Optional Supabase tables can mirror these rows for remote MCP reads.

---

## Agent reading loop

Recommended loop:

```text
1. vault search "query"
   ↓
2. vault map show <knowledge_id>
   ↓
3. vault map read <knowledge_id> --lines <start-end>
   ↓
4. Answer using only citations produced by bounded reads
```

Rules:

- Search-result citations are navigation hints, not final-answer proof.
- Final citations should come from bounded `read_range` / `map read` output.
- Do not invent citations.
- If a map is missing, build it before relying on section navigation.

---

## CLI examples

```bash
# Backfill map rows for all entries or a specific entry
vault map build
vault map build 123

# Inspect structure
vault map show 123

# Read a bounded line range
vault map read 123 --lines 10-40

# Query extracted claims
vault map query "migration rollback"
```

---

## MCP tools

The MCP server exposes the same idea through tools:

- `vault_map_show`
- `vault_read_range`
- `vault_remote_map_show` when optional remote sync is configured
- `vault_remote_read_range` when optional remote sync is configured

---

## Optional remote sync

Document Map rows can be synced to Supabase when teams or remote agents need read access:

```bash
pip install supabase
python scripts/sync_to_supabase.py --document-map
```

Public sync model:

```text
local SQLite source of truth → optional Supabase sync/read target
```

Do not treat Supabase as required for local usage.

---

## Testing expectations

Document Map changes should preserve:

- local CLI map commands
- MCP map/read payload shape
- citation-policy behavior
- Search QA metrics
- no network requirement for core tests

Useful checks:

```bash
python -m pytest tests/test_document_map.py tests/test_search_map_integration.py -q
python -m pytest tests/test_agent_behavior_policy.py -q
```

Test names may change while the project is alpha; use `python -m pytest -q` for the full available suite.
