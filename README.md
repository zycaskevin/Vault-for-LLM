# Vault-for-LLM

**English | [繁體中文](README.zh-Hant.md) | [简体中文](README.zh-CN.md)**

> Local-first memory for LLM agents.
>
> Vault-for-LLM creates a portable SQLite knowledge vault for your projects and AI agents. Add Markdown notes, compile them into searchable structured memory, and let agents query the vault through the `vault` CLI or the `vault-mcp` server.

---

## Why this exists

LLM agents are powerful, but most of them forget project context between sessions. They lose decisions, repeated mistakes, user preferences, debugging history, and hard-won operational knowledge.

Vault-for-LLM gives an agent a simple local memory layer:

1. You write knowledge as Markdown.
2. `vault compile` stores it in a local SQLite database.
3. Agents search it only when needed, instead of stuffing everything into every prompt.
4. MCP-compatible agents can query the vault during a conversation.

The goal is not to replace your notes app. The goal is to make your notes **usable by agents**.

---

## What makes it different

Vault-for-LLM is not just another vector store. It is evolving into an **agent memory QA layer**:

- Can the agent find the right memory when it needs it?
- Can it read only the relevant section instead of dumping whole documents into context?
- Can it tell whether a knowledge entry is complete, stale, duplicated, or under-specified?
- Can teams measure search quality before and after changing retrieval logic?
- Can reusable agent workflows be shared as skills instead of rediscovered in every project?

In other words: regular RAG focuses on retrieval; Vault-for-LLM focuses on whether memory can be **used correctly by agents**.

---

## Core principles

- **Local by default** — SQLite is the source of truth. No cloud is required for core usage.
- **Works without embeddings** — keyword search works first; semantic search is optional.
- **Agent-oriented memory** — split always-needed facts from searchable deep knowledge.
- **Bounded retrieval** — Document Map tools help agents read the right section instead of dumping entire files into context.
- **Optional sync** — Supabase support is an optional sync/read target, not required infrastructure.
- **Alpha, CLI-first** — this is a developer-facing tool. Expect rough edges and evolving APIs.

---

## What's new in 0.4.3

Version 0.4.3 adds **repository hygiene and public-boundary tools** for teams that use Vault-for-LLM in both private work and open-source release flows:

- `scripts/public_pr_gate.py` scans the actual PR diff and fails closed on private-only files, runtime data, local paths, secret-looking assignments, renamed paths, deleted lines, and large unexpected diffs.
- `scripts/artifact_audit.py` reports generated caches, review-only runtime folders, and archive candidates without deleting anything.
- `scripts/artifact_cleanup.py` defaults to dry-run and only deletes reproducible cache artifacts when explicitly run with `--execute --safe-only`.
- `docs/repo_governance.md` documents the public/internal release boundary and whitelist staging workflow.

These tools are source-checkout governance helpers; they do not change the core `vault` CLI memory workflow.

---

## What it can do

| Area | Capability |
|---|---|
| Knowledge storage | Markdown `raw/` files compiled into local SQLite |
| Search | keyword search, optional vector search, hybrid search |
| Embeddings | optional ONNX Runtime or Ollama embeddings |
| Memory layers | L0 identity, L1 core facts, L2 recent context, L3 deep knowledge |
| Knowledge graph | inferred entities/edges and graph expansion |
| Document Map | section/claim navigation and bounded `read_range` citations ([policy and demo](docs/document_map_citation_policy.md)) |
| MCP | `vault-mcp` exposes search/add/stats/map/read tools to compatible agents |
| Quality tools | lint, freshness, convergence, cross-validation, dedup, Search QA snapshots ([benchmarking guide](docs/search_qa_benchmarking.md)) |
| Repository governance | source-checkout public-boundary gate, artifact audit, and safe-only cleanup helpers ([governance guide](docs/repo_governance.md)) |
| Optional remote sync | Supabase sync scripts for teams or remote read paths |
| Local skill registry | experimental `vault skill` commands for sharing reusable workflows inside a local Vault; not a hosted marketplace |

---

## Quality tools roadmap

These features exist today, but they are still alpha and should be treated as quality-assurance tools rather than a fully managed platform:

| Tool | Purpose | Maturity |
|---|---|---|
| Document Map | Navigate sections/claims and read bounded source ranges with citations | usable, still evolving |
| Search QA | Run fixed query sets and compare before/after retrieval metrics; see the [benchmarking guide](docs/search_qa_benchmarking.md) and source-checkout fixtures under `benchmarks/search_qa/` | usable for deterministic regression checks |
| Convergence checks | Detect whether a knowledge entry has enough definition, procedure, and edge-case detail | experimental |
| Cross-validation | Verify extracted claims across different model families | experimental / optional-model dependent |
| Freshness + dedup | Mark stale entries and detect repeated knowledge | experimental |
| Local skill registry | Push/search/pull reusable agent workflows in local SQLite | experimental / local-only |
| Repo hygiene scripts | Audit generated artifacts, clean safe caches, and scan public PR diffs before release | source-checkout helper |

The `benchmarks/search_qa/` examples are repository fixtures in a source checkout, not files installed by the PyPI wheel. After `pip install vault-for-llm`, run `vault search-qa` with your own QA JSON files, or clone/download this repository to use the example fixtures.

The stable path is still the core loop: `vault init` → `vault add` → `vault compile` → `vault search` → `vault-mcp`.

---

## Architecture

```text
L0 Identity        → who the user/project is; loaded every session
L1 Core Facts      → stable environment and project facts; loaded every session
L2 Recent Context  → recent decisions, incidents, and working context
L3 Deep Knowledge  → lessons, APIs, architecture, troubleshooting; searched on demand

Markdown raw/  →  vault compile  →  SQLite database  →  vault search / MCP tools
```

This keeps the agent prompt small while still making deeper memory available when relevant.

---

## Installation

### Install from PyPI

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install vault-for-llm

vault doctor
```

### Optional semantic search

Keyword search works with the base install. For local ONNX embeddings:

```bash
pip install "vault-for-llm[semantic]"
vault install-embedding --model mix
```

Or use an existing Ollama embedding model:

```bash
vault config set embedding.provider ollama
vault config set embedding.model nomic-embed-text
```

### Optional MCP server

```bash
pip install "vault-for-llm[mcp]"
vault-mcp --project-dir /path/to/your/project
```

### Development install from source

```bash
git clone https://github.com/zycaskevin/Vault-for-LLM.git
cd Vault-for-LLM
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Quickstart

```bash
# 1. Create a vault in your project
vault init

# 2. Add a first knowledge entry
vault add "First lesson" --content "The bug was caused by X. The fix was Y."

# 3. Compile Markdown into the local SQLite vault
vault compile

# 4. Search it later
vault search "what caused the bug"
```

You can also add Markdown files directly under `raw/` and run `vault compile`.

Example entry:

```markdown
---
title: "Postgres migration pitfall"
category: "error"
layer: L3
tags: ["postgres", "migration"]
trust: 0.8
source: "project-notes"
created: "2026-05-16"
---

# Postgres migration pitfall

What broke, why it broke, and how to avoid it next time.
```

---

## Directory structure

```text
your-project/
├── L0-identity/              # user or project identity loaded every session
│   └── identity.md
├── L1-core-facts/            # stable facts loaded every session
│   └── current-projects.md
├── L2-context/               # recent context, decisions, incidents
│   └── recent-sessions/
├── L3-knowledge/             # deep knowledge organized for retrieval
├── raw/                      # source Markdown knowledge entries
├── compiled/                 # compiled / compressed knowledge artifacts
├── vault.db             # local SQLite database generated by vault
└── templates/                # starter templates
```

## CLI reference

| Command | Purpose |
|---|---|
| `vault init` | Initialize a project vault |
| `vault doctor` | Check local environment and optional dependencies |
| `vault add "Title" --content "..."` | Add one knowledge entry |
| `vault add "Title" --file note.md` | Add an entry from a Markdown file |
| `vault import long-doc.md` | Import and chunk a long document |
| `vault compile` | Compile `raw/` into SQLite + `compiled/` artifacts |
| `vault search "query"` | Search the vault |
| `vault search "query" --graph-expand 2` | Search with graph expansion |
| `vault list` | List knowledge entries |
| `vault stats` | Show vault statistics |
| `vault lint` | Run quality checks |
| `vault map build` | Build/backfill Document Map rows |
| `vault map show <id>` | Show a knowledge entry's section map |
| `vault map read <id> --lines 10-30` | Read a bounded source range |
| `vault graph build` | Build the inferred knowledge graph |
| `vault graph show` | Show graph statistics |
| `vault converge` | Experimental convergence/self-questioning check |
| `vault cross-validate` | Experimental cross-model validation |
| `vault freshness` | Experimental freshness/review scheduling |
| `vault dedup` | Detect or merge duplicate entries |
| `vault search-qa run` / `vault search-qa compare` | Run Search QA metrics snapshots and before/after comparisons ([guide](docs/search_qa_benchmarking.md)) |
| `vault skill search "query"` | Search local experimental skill registry entries |

Run `vault <command> --help` for command-specific options.

For citation-safe memory use, see the [Document Map citation policy](docs/document_map_citation_policy.md): search results are navigation hints, while `vault map read` returns bounded source text for final citations.

---

## MCP integration

Install MCP extras and start the server:

```bash
pip install "vault-for-llm[mcp]"
vault-mcp --project-dir /path/to/your/project
```

Example MCP server config:

```json
{
  "mcpServers": {
    "vault": {
      "command": "vault-mcp",
      "args": ["--project-dir", "/path/to/your/project"]
    }
  }
}
```

Current MCP tools include:

- `vault_search`
- `vault_add`
- `vault_stats`
- `vault_map_show`
- `vault_read_range`
- `vault_remote_map_show` / `vault_remote_read_range` when optional Supabase sync is configured

For agent loops, prefer `vault_search` → `vault_map_show` → `vault_read_range`. `vault_search` returns compact MCP payloads by default; pass `compact: false` only when a caller explicitly needs the fuller preview output. Final answers should cite `vault_read_range` output rather than search previews.

---

## Optional Supabase sync

Core Vault-for-LLM usage is local-only. Supabase support is for teams or remote read paths that want a synced copy of local SQLite data.

The local SQLite database remains the source of truth. Supabase is an optional sync/read target. Remote table names use Vault-branded defaults and can be overridden with `VAULT_SUPABASE_*_TABLE` environment variables when integrating an existing private schema.

```bash
# install manually while this is alpha
pip install supabase

# configure Supabase credentials in your environment, then run sync scripts as needed
python scripts/sync_to_supabase.py --document-map
```

---

## Current maturity

Vault-for-LLM is alpha software:

- Package, module, database, and MCP tool names are Vault-branded.
- Advanced features such as convergence, cross-validation, Search QA, skills, and Supabase sync are evolving.
- The default install is available from PyPI; source installs are for development.
- APIs and schemas may change before a stable release.

If you want the most stable path, start with:

```bash
vault init
vault add
vault compile
vault search
```

---

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
```

Some optional test paths require optional dependencies such as ONNX, MCP, or Supabase.

---

## License

MIT
