# Optimization Notes

This document collects public optimization directions for Vault-for-LLM. It is intentionally product- and project-neutral: no private deployment paths, remote admin surfaces, or internal agent wiring are required to use Vault.

---

## Optimization goals

Vault-for-LLM optimizes for agent memory that is:

1. **Local-first** — works with SQLite and Markdown without a cloud service.
2. **Cheap to retrieve** — agents search and read only what they need.
3. **Citation-aware** — long entries can be navigated with Document Map and bounded reads.
4. **Portable** — a project folder can carry its own knowledge vault.
5. **Agent-friendly** — CLI and MCP tools expose the same core operations.

---

## Retrieval stack

Recommended retrieval order:

```text
keyword search
  → optional vector search
  → hybrid reranking
  → optional graph expansion
  → Document Map navigation
  → bounded read_range citation
```

This keeps simple cases simple while giving advanced agents a path to deeper context.

---

## Local-first storage

Core storage should remain:

```text
Markdown raw/ entries → vault compile → local SQLite database
```

Why:

- SQLite is easy to back up and inspect.
- Markdown remains human-readable.
- Agents can operate without network access.
- Optional remote sync can be rebuilt from local state.

---

## Optional semantic search

Semantic search should be optional, not required:

| Mode | Dependency | Use case |
|---|---|---|
| Keyword | base install | reliable fallback, no model needed |
| ONNX | `.[semantic]` extra | local embeddings without PyTorch/GPU |
| Ollama | existing Ollama service | reuse an already-installed local model stack |

If no embedding provider is available, `vault search` should degrade gracefully to keyword search.

---

## Document Map optimization

For long notes, the key optimization is bounded reading:

1. Search finds candidate entries.
2. Document Map shows section structure.
3. The agent reads only a selected line range.
4. Final answers cite the bounded read, not the search preview.

This reduces context noise and makes answers more auditable.

---

## Quality and regression safety

Before changing retrieval ranking or schema behavior, prefer deterministic checks:

- unit tests for schema migration
- CLI smoke tests for `vault search`, `vault map`, and `vault search-qa`
- Search QA before/after snapshots
- citation-policy tests that reject invented/search-only citations
- `git diff --check` for whitespace hygiene

---

## Remote sync design

Remote sync should stay optional:

```text
local SQLite source of truth → optional remote read/sync target
```

If a future version adds bidirectional sync, it should define conflict resolution explicitly before enabling it by default.

---

## Public documentation rule

Public docs should describe:

- what users can install and run
- which features are stable versus experimental
- how local and optional remote modes differ
- migration notes for old internal names

Public docs should not include private paths, personal names, internal admin surfaces, or deployment-specific instructions from one user's environment.
