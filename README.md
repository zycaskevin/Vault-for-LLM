# Vault-for-LLM

**English | [繁體中文](README.zh-Hant.md) | [简体中文](README.zh-CN.md)**

> Local-first, production-minded memory workflows for LLM agents.
>
> Vault-for-LLM turns Markdown project knowledge into a portable SQLite memory vault that agents can search on demand. It is built for the boring parts that make agent memory usable in real projects: retrieval QA, bounded document reads, semantic search, schema migrations, and verified backup/restore.

---

## Why this exists

LLM agents are powerful, but most of them forget the things that matter between sessions: project decisions, repeated mistakes, user preferences, debugging history, and hard-won operational knowledge.

Vault-for-LLM gives an agent a simple local memory layer:

1. You write knowledge as Markdown.
2. `vault compile` stores it in a local SQLite database.
3. Agents search it only when needed, instead of stuffing everything into every prompt.
4. MCP-compatible agents can query the vault during a conversation.

The goal is not to replace your notes app or become another hosted vector database. The goal is to make your project knowledge **usable, measurable, and recoverable by agents**.

---

## What makes it different

Vault-for-LLM is not just another vector store. It is evolving into an **agent memory QA layer**:

- Can the agent find the right memory when it needs it?
- Can it read only the relevant section instead of dumping whole documents into context?
- Can it tell whether a knowledge entry is complete, stale, duplicated, or under-specified?
- Can teams measure search quality before and after changing retrieval logic?
- Can reusable agent workflows be shared as skills instead of rediscovered in every project?

In other words: regular RAG focuses on retrieval; Vault-for-LLM focuses on whether memory can be **used correctly by agents**.

For a broader positioning against Mem0, Letta/MemGPT, Zep, and LangGraph memory, see the [memory system comparison](docs/memory_system_comparison.md). The short version: Vault-for-LLM optimizes for local, inspectable, candidate-first project memory with retrieval QA and bounded citations; hosted or runtime-native memory systems may be better when you need managed personalization, a full stateful-agent runtime, or enterprise temporal graph infrastructure.

---

## Core principles

- **Local by default** — SQLite is the source of truth. No cloud is required for core usage.
- **Works without embeddings** — keyword search works first; semantic search is optional.
- **Agent-oriented memory** — split always-needed facts from searchable deep knowledge.
- **Bounded retrieval** — Document Map tools help agents read the right section instead of dumping entire files into context.
- **Optional sync** — Supabase support is an optional sync/read target, not required infrastructure.
- **CLI-first** — this is a developer-facing tool. Core local usage is stable; advanced QA, semantic, and sync workflows still evolve.

---

## What's new in 0.5.0

Version 0.5.0 upgrades Vault-for-LLM from “local keyword-search memory” into a production-hardened local memory workflow:

- **Search QA baseline** — run fixed query sets and compare retrieval quality/latency before and after search changes.
- **FTS5/BM25 keyword search** — faster keyword retrieval when SQLite FTS5 is available, with safe fallback to the legacy `LIKE` path for compatibility and CJK misses.
- **Guarded semantic workflow** — optional semantic vectors, provider validation, persistent embedding cache, and operator commands for rebuild/warm/smoke/startup/daemon.
- **Explicit DB schema status/migration** — inspect and run idempotent SQLite migrations with [`vault db status/migrate`](docs/db_migrations.md), and create/verify/restore local SQLite backups with [`vault db backup/verify-backup/restore`](docs/db_backup_restore.md).
- **Release gates** — README command smoke, wheel smoke, version parity, secret scan, full-history privacy scan, and public-boundary checks.

Semantic search is **optional by design**: the base install still works with keyword search only. If you configure a real embedding provider, use [`vault semantic ...`](docs/semantic_search.md) to rebuild vectors, warm caches, and run smoke checks. Deterministic hash embeddings require `--allow-hash` and are for CI/local tests only.

Older repository hygiene tools from 0.4.3 are documented in [`scripts/README.md`](scripts/README.md) and [`docs/repo_governance.md`](docs/repo_governance.md).

---

## What it can do

| Area | Capability |
|---|---|
| Knowledge storage | Markdown `raw/` files compiled into local SQLite |
| Search | FTS5/BM25 keyword search with fallback, optional vector search, hybrid search |
| Embeddings | optional ONNX Runtime or Ollama embeddings, provider guard, durable cache workflows |
| Memory layers | L0 identity, L1 core facts, L2 recent context, L3 deep knowledge |
| Knowledge graph | inferred entities/edges and graph expansion |
| Document Map | section/claim navigation and bounded `read_range` citations ([policy and demo](docs/document_map_citation_policy.md)) |
| MCP | `vault-mcp` exposes search/add/stats/map/read plus candidate-first memory tools to compatible agents ([MCP memory workflow](docs/mcp_memory_workflow.md)) |
| Memory curator | `vault remember`, `vault promote`, and MCP propose/promote tools for gated autonomous memory writes |
| Dream reports | `vault dream` produces report-first memory curation summaries for stale, duplicate, weak, or poorly-described knowledge ([dream workflow](docs/dream_workflow.md)) |
| Quality tools | lint, freshness, convergence, cross-validation, dedup, Search QA snapshots ([benchmarking guide](docs/search_qa_benchmarking.md)), semantic smoke/warm workflows |
| Repository governance | source-checkout public-boundary gate, artifact audit, and safe-only cleanup helpers ([governance guide](docs/repo_governance.md)) |
| Optional remote sync | Supabase sync scripts for teams or remote read paths |
| Local skill registry | experimental `vault skill` commands for sharing reusable workflows inside a local Vault; not a hosted marketplace |

---

## Quality tools roadmap

These features exist today, but their maturity differs. Core local commands are the stable path; advanced QA, semantic, sync, and skill-registry workflows are still evolving:

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

The stable path is still the core loop: `vault init` → `vault add`/`vault remember` → `vault compile`/`vault promote` → `vault search` → `vault-mcp`. For autonomous agents, prefer `vault_memory_propose` over direct `vault_add`.

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

> Release note: the GitHub source tree is currently `0.5.0`, while PyPI may still show an older version until Trusted Publisher publishing is unblocked. If you need the newest 0.5.0 source features immediately, use the source install below.

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

Security note: `vault-mcp` is a local stdio MCP server. It does not implement network authentication or user-level access control. Only configure it for agents you trust with read/write access to the selected `--project-dir`, and prefer a dedicated project directory for shared or experimental agents.

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

### Candidate-first agent memory

For autonomous agents or unreviewed memories, prefer the safer candidate workflow:

```bash
vault remember "Memory title" \
  --content "Markdown memory content" \
  --reason "Why this is worth remembering"

# after review
vault promote mem_xxxxxxxxxxxx --confirm
```

MCP-compatible agents should use `vault_memory_propose` and `vault_memory_promote`; see [MCP memory workflow](docs/mcp_memory_workflow.md).

### Dream curation reports

Run a report-first memory curation pass:

```bash
vault dream --mode report --limit 50 --write-report
```

Reports are written under `reports/dream/`. See [dream workflow](docs/dream_workflow.md).


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

### Optional semantic workflow

Semantic search is optional by design. The base install keeps working with keyword search only. After configuring a real embedding provider, the main operator commands are:

```bash
vault semantic rebuild --persist-cache
vault search "what caused the bug" --mode semantic
vault search "what caused the bug" --mode hybrid
vault semantic smoke --qa-file benchmarks/search_qa/basic.en.json --mode semantic --pretty
vault semantic cache-stats --pretty
```

`vault search --mode semantic` reads stored `semantic_vectors` directly. `--mode hybrid` fuses keyword results with the stored semantic index when available, and falls back safely when it is not.

Search QA can also run semantic/hybrid snapshots, but the QA command must use the same provider/model/dimension and vector kind used to rebuild `semantic_vectors`. For deterministic local smoke tests, rebuild with `--allow-hash --hash-dim N` and pass the same flags to `vault search-qa run`; hash vectors validate plumbing only and are not a semantic-quality benchmark.

For the full lifecycle — `warm`, `cache-prune`, `startup`, `daemon`, and the `--allow-hash` test-only provider — see [`docs/semantic_search.md`](docs/semantic_search.md).

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
| `vault export obsidian --vault /path/to/ObsidianVault --dry-run` | Export read-only Markdown notes for Obsidian browsing |
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
| `vault db status` / `vault db migrate` | Inspect or update local SQLite schema ([guide](docs/db_migrations.md)) |
| `vault db backup` / `vault db verify-backup` / `vault db restore` | Create, verify, and safely restore local SQLite backups ([guide](docs/db_backup_restore.md)) |
| `vault semantic rebuild` | Rebuild semantic vector rows after configuring a real embedding provider |
| `vault semantic warm` | Precompute QA query embeddings without writing vector rows |
| `vault semantic smoke` | Rebuild, warm, and run a Search QA smoke snapshot in one command |
| `vault semantic cache-stats` / `vault semantic cache-prune` | Inspect or prune the durable embedding cache |
| `vault semantic startup` / `vault semantic daemon` | Run importable startup or bounded daemon lifecycle hooks |
| `vault skill search "query"` | Search local experimental skill registry entries |

Run `vault <command> --help` for command-specific options.

### Obsidian export

Use `vault export obsidian` when you want humans to browse the compiled vault in Obsidian without changing the source knowledge base:

```bash
vault export obsidian \
  --vault /path/to/ObsidianVault \
  --category technique \
  --dry-run
```

The export is intentionally one-way and read-only: it reads from `vault.db`, writes Markdown notes under `00-Vault-Knowledge/`, includes YAML frontmatter plus `Vault #<id>` citations, and does not write back to `raw/`, `compiled/`, SQLite, or any remote sync target. Re-running the command overwrites the same stable note paths instead of creating duplicates.

For citation-safe memory use, see the [Document Map citation policy](docs/document_map_citation_policy.md): search results are navigation hints, while `vault map read` returns bounded source text for final citations.

---

## MCP integration

Install MCP extras and start the server:

```bash
pip install "vault-for-llm[mcp]"
vault-mcp --project-dir /path/to/your/project
```

Security note: `vault-mcp` is a local stdio MCP server. It does not implement network authentication or user-level access control. Only configure it for agents you trust with read/write access to the selected `--project-dir`, and prefer a dedicated project directory for shared or experimental agents.

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

- Retrieval: `vault_search`, `vault_stats`
- Candidate-first memory: `vault_memory_propose`, `vault_memory_promote`
- Curation: `vault_dream_run`
- Bounded reading: `vault_map_show`, `vault_read_range`
- Compatibility direct write: `vault_add` (prefer candidate-first tools for autonomous agents)
- Optional remote reads: `vault_remote_map_show` / `vault_remote_read_range` when optional Supabase sync is configured

For agent loops, prefer `vault_search` → `vault_map_show` → `vault_read_range`. `vault_search` returns compact MCP payloads by default; pass `compact: false` only when a caller explicitly needs the fuller preview output. Final answers should cite `vault_read_range` output rather than search previews.

---

## Optional Supabase sync

Core Vault-for-LLM usage is local-only. Supabase support is for teams or remote read paths that want a synced copy of local SQLite data.

The local SQLite database remains the source of truth. Supabase is an optional sync/read target. Remote table names use Vault-branded defaults and can be overridden with `VAULT_SUPABASE_*_TABLE` environment variables when integrating an existing private schema.

```bash
# optional integration dependency
pip install supabase

# configure Supabase credentials in your environment, then run sync scripts as needed
python scripts/sync_to_supabase.py --document-map
```

---

## Current maturity

Vault-for-LLM is CLI-first developer tooling:

- Core local commands (`init`, `add`, `compile`, `search`) are the most stable path.
- Search QA, FTS5/BM25 keyword search, Document Map citation reads, and semantic workflow commands are usable but still evolving.
- Optional integrations such as Supabase sync, MCP, and local skill registry may change before a stable 1.0 release.
- The default install is available from PyPI; source installs are for development.

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
