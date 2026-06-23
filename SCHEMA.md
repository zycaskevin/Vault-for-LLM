# Vault Knowledge Schema

This document defines the public knowledge format and operating rules for a Vault-for-LLM project.

Vault-for-LLM is local-first: Markdown files are the human-editable source material, and the local SQLite database is the compiled source of truth used by the CLI and MCP server. Optional remote systems such as Supabase are sync/read targets, not required infrastructure.

---

## 1. Data flow

```text
raw/ Markdown  →  vault compile  →  local SQLite database  →  vault search / MCP tools
                                      ↓
                                compiled/ artifacts
                                      ↓
                         optional Supabase sync target
```

Rules:

1. `raw/` entries are human-editable source notes.
2. `compiled/` artifacts are generated and may be rebuilt.
3. SQLite is the local source of truth for CLI/MCP retrieval.
4. Supabase, when configured, is an optional sync/read target.
5. Search-result citations are navigation hints; final citations should come from bounded `read_range` output when using Document Map tools.

---

## 2. Recommended directory structure

```text
your-project/
├── L0-identity/
│   └── identity.md
├── L1-core-facts/
│   └── current-projects.md
├── L2-context/
│   └── recent-sessions/
├── L3-knowledge/
├── raw/
├── compiled/
├── vault.db
└── templates/
```


---

## 3. Memory layers

| Layer | Purpose | Loading pattern |
|---|---|---|
| L0 | User/project identity and stable preferences | Load every session |
| L1 | Stable environment and active project facts | Load every session |
| L2 | Recent decisions, incidents, and working context | Load when relevant |
| L3 | Deep knowledge, lessons, APIs, troubleshooting | Search on demand |

---

## 4. Knowledge frontmatter

Each `raw/` Markdown entry should include YAML frontmatter:

```yaml
---
title: "Knowledge title"
category: "concept|technique|workflow|lesson|error|comparison|general"
layer: L3
tags: ["tag1", "tag2"]
summary: "One short sentence explaining what this entry is about."
trust: 0.0-1.0
source: "source-description"
created: "YYYY-MM-DD"
---
```

Recommended fields:

| Field | Meaning |
|---|---|
| `title` | Human-readable entry title |
| `category` | Broad knowledge type |
| `layer` | `L0`, `L1`, `L2`, or `L3` |
| `tags` | Lowercase tags for filtering/search |
| `summary` | 1-sentence relevance preview |
| `trust` | Confidence score from 0.0 to 1.0 |
| `source` | Where the knowledge came from |
| `created` | Creation date |

Optional fields:

```yaml
updated: "YYYY-MM-DD"
status: "active|archived|deprecated"
expires_at: "YYYY-MM-DD"
```

Compiled SQLite rows also track maintenance-only usage fields:

| Field | Meaning |
|---|---|
| `access_count` | Number of times the memory appeared in local retrieval results |
| `citation_count` | Number of times a workflow explicitly marked the memory as cited evidence |
| `last_accessed_at` | Most recent retrieval timestamp |
| `archived_at` | Timestamp when a row was moved to `status: archived` |

`vault usage archive-expired` moves expired active memories to archived status.
It does not delete source rows.

---

## 5. Suggested categories and tags

Suggested `category` values:

- `concept`
- `technique`
- `workflow`
- `lesson`
- `error`
- `comparison`
- `general`

Suggested tag families:

| Tag family | Examples |
|---|---|
| `llm` | models, prompts, evaluation |
| `tools` | CLI, IDE, MCP |
| `infra` | Docker, network, runtime |
| `data` | SQLite, vector-search, sync |
| `workflow` | automation, QA, agents |
| `security` | privacy, secrets, access control |
| `testing` | regression, CI, fixtures |
| `design` | UX, information architecture |

Use lowercase tags and hyphenate multi-word tags.

---

## 6. Write and compile workflow

```bash
# Add one entry directly
vault add "Title" --content "What you learned and why it matters."

# Or write Markdown under raw/, then compile
vault compile

# Search later
vault search "query"
```

Compiler expectations:

1. Do not mutate `raw/` source content unexpectedly.
2. Rebuild generated `compiled/` artifacts as needed.
3. Update SQLite rows and indexes.
4. Build Document Map rows where supported.
5. Keep output deterministic enough for tests and review.

---

## 7. Retrieval rules for agents

When an agent uses a Vault project:

1. Read L0/L1 only when the project explicitly asks for always-loaded memory.
2. Search L3 knowledge on demand with `vault search` or `vault_search`.
3. Prefer keyword search first when no embedding provider is installed.
4. For long entries, inspect Document Map structure before reading ranges.
5. Use bounded `read_range` output for final citations when citation accuracy matters.
6. Do not invent citations or claim a source was read if only search results were inspected.

---

## 8. Optional remote sync

Remote sync is optional. The expected public model is:

```text
local SQLite source of truth  →  optional Supabase sync/read target
```

A remote store should not silently overwrite local source data. If bidirectional sync is added in the future, conflict rules must be explicit and documented.

---

## 9. Public terminology

| Use | Avoid in public docs |
|---|---|
| Vault-for-LLM | internal project names |
| `vault` CLI | non-Vault command names in examples |
| local SQLite vault | private/internal main database |
| optional Supabase sync | required cloud dependency |
| MCP server | product-specific internal wiring |
| alpha/experimental feature | overclaiming stability |

---

_Last updated: 2026-05-16_
