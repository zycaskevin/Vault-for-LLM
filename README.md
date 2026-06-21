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

For adjacent retrieval and context-budget systems, see the [PageIndex and
Headroom comparison](docs/comparisons/pageindex_headroom.md). The short version:
Vault can borrow PageIndex-style document tree navigation and Headroom-style
context budgeting while keeping core project memory local, governed, and
source-cited.

To see the positioning as local numbers rather than slogans, run the [project memory proof demos](docs/project_memory_proofs.md): agent onboarding recall, candidate-first review, and stale-source bounded-read checks. To compare exported Hermes/Codex-style sessions against governed Vault memory, use the [agent onboarding benchmark](docs/agent_onboarding_benchmark.md).

---

## Core principles

- **Local by default** — SQLite is the source of truth. No cloud is required for core usage.
- **Works without embeddings** — keyword search works first; semantic search is optional.
- **Agent-oriented memory** — split always-needed facts from searchable deep knowledge.
- **Bounded retrieval** — Document Map tools help agents read the right section instead of dumping entire files into context.
- **Optional sync** — Supabase support is an optional sync/read target, not required infrastructure.
- **CLI-first** — this is a developer-facing tool. Core local usage is stable; advanced QA, semantic, and sync workflows still evolve.

---

## Works across agent systems

Vault-for-LLM is not tied to one agent runtime. The shared contract is simple:
local Markdown + SQLite, exposed through CLI and optional stdio MCP.

| System | How to use Vault-for-LLM |
|---|---|
| Hermes Agent / Nancy | Configure `vault-mcp` for search/read/propose tools; run CLI jobs for dream reports, backups, and onboarding benchmarks. |
| OpenClaw | Use the bundled adapter in [`integrations/openclaw/`](integrations/openclaw/) to register `vault_search`, `vault_read_range`, `vault_memory_propose`, and `vault_stats`; generic MCP also works. |
| n8n | Call the `vault` CLI from Execute Command nodes, wrap it behind an internal HTTP service, or bridge to MCP for workflow automation. |
| Codex | Use the CLI inside the repo/workspace; use MCP on Codex surfaces that support local MCP servers. |
| OpenCode | Use the same generic local MCP pattern as Claude Code/Codex when MCP is available, or shell out to the CLI. |
| Claude Code | Configure `vault-mcp` as a local stdio MCP server, or use CLI commands in shell-capable sessions. |
| Any MCP-compatible agent | Run `vault-mcp --project-dir <project>` and follow `vault_search` → `vault_read_range` → answer with sources. |

See [Agent Integrations](docs/agent_integrations.md) for setup patterns, OpenClaw adapter details, and runtime-specific notes.

### Agent-facing install contract

Many Vault-for-LLM installs are performed by agents rather than by humans. For
agent-driven setup or repo changes, use:

- [`AGENTS.md`](AGENTS.md) — concise operating rules for coding agents.
- [`agent_manifest.json`](agent_manifest.json) — machine-readable install,
  scope, safety, runtime, and validation metadata.
- [`docs/agent_install.md`](docs/agent_install.md) — short install runbook for
  Hermes, Codex, Claude Code, OpenClaw, OpenCode, n8n, and other agents.

Human users do not need to install everything manually. You can ask your agent:

```text
Install Vault-for-LLM for this project. Read AGENTS.md and agent_manifest.json,
ask me whether the vault should be shared or private, ask which optional
features to enable, ask whether I have an existing Obsidian vault to import,
configure CLI/MCP, run the first Obsidian import if requested, ask whether I
want automatic Obsidian sync, and run a search/read/propose smoke test.
```

Agents should read those files before choosing a database scope, configuring
MCP, installing optional features, or writing memory.

The common install architecture is the same across Hermes Agent, Codex,
OpenCode, Claude Code, OpenClaw, and other MCP-capable agents:

```text
choose projectDir -> choose optional features -> ask about Obsidian -> install vault -> configure CLI/MCP -> first import/sync check -> verify search/read/propose
```

Runtime-specific adapters should stay thin. The durable contract is the shared
`projectDir`, `vault` CLI, `vault-mcp`, and candidate-first memory policy.

Agent installers should also ask about optional capabilities instead of enabling
everything by default:

| Feature | Default | Install command | Ask when |
|---|---|---|---|
| `core` | yes | `python -m pip install vault-for-llm==0.6.24` | Always: local Markdown, SQLite, keyword search. |
| `mcp` | yes for MCP-capable agents | `python -m pip install "vault-for-llm[mcp]==0.6.24"` | The runtime can connect local stdio MCP tools. |
| `obsidian_import` | no | built into core CLI | The user already has an Obsidian vault and wants agents to search those notes through Vault. |
| `semantic` | no | `python -m pip install "vault-for-llm[semantic]"` | The user wants embedding-backed semantic/hybrid search. |
| `supabase` | no | `python -m pip install "vault-for-llm[supabase]"` | The user wants optional remote sync/read paths. |
| `headroom` | no | `python -m pip install headroom-ai` | The agent often reads long logs, terminal output, or large retrieved context and needs optional compression before sending content to the LLM. |
| `dev` | no | `python -m pip install -e ".[dev]"` | Source checkout, benchmarks, PR work, or release validation. |

Do not silently enable semantic, Supabase, or Headroom extras: semantic and
Supabase add heavier dependencies, model/provider setup, or remote credentials;
Headroom is useful only when context-window or token pressure is a real issue.
If Headroom is enabled, keep citations tied to original `vault_read_range`
output, not compressed summaries.

For Obsidian, the agent should ask for the vault path, run a dry-run first,
perform the first import only after confirmation, then ask whether to schedule
the same `vault import obsidian --compile` command for ongoing sync.

### Choose the Vault project scope

Vault-for-LLM is bound to the `project-dir`, not to a specific agent runtime:

```text
one project directory = one vault.db
```

If Hermes, OpenClaw, Codex, Claude Code, and n8n all point to the same
`--project-dir`, they share the same governed project memory. If they point to
different directories, they use isolated databases.

| Scope | Use when | Example project-dir |
|---|---|---|
| Shared project vault | Multiple trusted agents collaborate on the same confirmed project knowledge | `~/Vaults/my-project` |
| Agent-private vault | One agent is experimenting, noisy, or untrusted | `~/.openclaw/workspace/vault-project` |
| Domain/customer vault | Data boundaries must stay separate | `~/Vaults/clinic-customer-service` |
| Temporary vault | Demos, tests, and benchmarks | `/tmp/vault-benchmark-*` |

For shared vaults, prefer `vault_memory_propose` over direct writes so multiple
agents do not pollute active memory before review.

For agents running on different machines, the local `project-dir` cannot be
shared directly. In that case, optional Supabase sync can act as a remote
shared read/sync layer: each host keeps its own local SQLite vault, then syncs
approved knowledge, Document Map rows, summaries, hashes, and metadata to the
same Supabase project. This lets Hermes on one host, Codex on another host, and
n8n on a server read from a common project-memory view without making Supabase a
required dependency for local use.

---

## Current Source Status

The current source tree is `0.6.24`. Core local search is stable, while
advanced semantic, rerank, sync, and benchmarking workflows remain optional.
See [CHANGELOG.md](CHANGELOG.md) for release details.

---

## What it can do

| Area | Capability |
|---|---|
| Knowledge storage | Markdown `raw/` files compiled into local SQLite |
| Search | FTS5/BM25 keyword search with fallback, optional vector search, hybrid search, query expansion |
| Reranking | lightweight zero-dependency reranker (default), optional Cross-Encoder reranker for production-grade relevance |
| Embeddings | optional ONNX Runtime or Ollama embeddings, provider guard, durable cache workflows |
| LLM enhancement | optional LLM-powered query rewriting for better retrieval recall |
| Memory layers | L0 identity, L1 core facts, L2 recent context, L3 deep knowledge |
| Knowledge graph | inferred entities/edges and graph expansion |
| Document Map | section/claim navigation and bounded `read_range` citations ([policy and demo](docs/document_map_citation_policy.md)) |
| MCP | `vault-mcp` exposes search/add/stats/map/read plus candidate-first memory tools to compatible agents ([MCP memory workflow](docs/mcp_memory_workflow.md)) |
| Memory curator | `vault remember`, `vault promote`, and MCP propose/promote tools for gated autonomous memory writes |
| Dream reports | `vault dream` produces report-first memory curation summaries for stale, duplicate, weak, or poorly-described knowledge ([dream workflow](docs/dream_workflow.md)) |
| Quality tools | lint, freshness, convergence, cross-validation, dedup, Search QA snapshots ([benchmarking guide](docs/search_qa_benchmarking.md)), semantic smoke/warm workflows |
| Benchmarking | `benchmarks/search_benchmark.py` for reproducible before/after retrieval quality and latency comparison |
| Repository governance | source-checkout public-boundary gate, artifact audit, and safe-only cleanup helpers ([governance guide](docs/repo_governance.md)) |
| Agent integrations | CLI/MCP patterns for Hermes Agent, OpenClaw, n8n, Codex, Claude Code, and generic MCP-compatible agents ([integration guide](docs/agent_integrations.md)) |
| Future retrieval layers | Design notes for Document Map tree navigation and optional Headroom context-budget integration ([tree navigation](docs/design/document_tree_navigation.md), [Headroom notes](docs/integrations/headroom.md)) |
| Optional remote sync | Supabase sync scripts for teams or remote read paths |
| Local skill registry | experimental `vault skill` commands for sharing reusable workflows inside a local Vault; not a hosted marketplace |

---

## Quality tools roadmap

These features exist today, but their maturity differs. Core local commands are the stable path; advanced QA, semantic, sync, and skill-registry workflows are still evolving:

| Tool | Purpose | Maturity |
|---|---|---|
| Document Map | Navigate sections/claims and read bounded source ranges with citations | usable, still evolving |
| Search QA | Run fixed query sets and compare before/after retrieval metrics; see the [benchmarking guide](docs/search_qa_benchmarking.md) and source-checkout fixtures under `benchmarks/search_qa/` | usable for deterministic regression checks |
| Cross-Encoder reranker | Production-grade relevance scoring for search result reranking via cross-encoder models | usable with optional deps |
| Search benchmark framework | Reproducible before/after comparison of retrieval quality and latency across search strategies | usable |
| LLM query rewriting | LLM-powered query reformulation for improved retrieval recall | usable with optional deps |
| Convergence checks | Detect whether a knowledge entry has enough definition, procedure, and edge-case detail | experimental |
| Cross-validation | Verify extracted claims across different model families | experimental / optional-model dependent |
| Freshness + dedup | Mark stale entries and detect repeated knowledge | experimental |
| Local skill registry | Push/search/pull reusable agent workflows in local SQLite | experimental / local-only |
| Repo hygiene scripts | Audit generated artifacts, clean safe caches, and scan public PR diffs before release | source-checkout helper |

The `benchmarks/search_qa/` examples are repository fixtures in a source checkout, not files installed by the PyPI wheel. After `pip install vault-for-llm`, run `vault search-qa` with your own QA JSON files, or clone/download this repository to use the example fixtures.

The stable path is still the core loop: `vault init` → `vault add`/`vault remember` → `vault compile`/`vault promote` → `vault search` → `vault-mcp`. For autonomous agents, prefer `vault_memory_propose` over direct `vault_add`.

Think of direct `vault_add` as letting someone walk straight into the archive and put a note on the shelf. It is still available for trusted scripts, but the safer daily path is the candidate desk: propose first, inspect gates, then promote.

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

### Agent memory lifecycle

```text
Conversation / task
  → propose memory candidate
  → privacy + duplicate + metadata + quality gates
  → promote reviewed memory
  → raw Markdown + SQLite active knowledge
  → search / map / read_range recall
  → dream report for cleanup and safe metadata fixes
```

In story form: the agent writes a note, the front desk checks whether it is safe and useful, the librarian shelves it only after review, and later the agent asks the catalog for just the right shelf and paragraph.

---

## Installation

### Install from PyPI

Vault-for-LLM `0.6.24` is published on PyPI.

For agent-driven installation, paste this into Hermes Agent, Codex, OpenCode, Claude Code, OpenClaw, or another agent that can run local commands:

```text
Install Vault-for-LLM for this project. Use PyPI package vault-for-llm[mcp]==0.6.24.
Ask whether the vault database should be shared, private, domain-specific, or temporary.
Ask separately about MCP, semantic search, Supabase sync, Headroom context compression,
and dev/benchmark dependencies. Ask whether I have an existing Obsidian vault to import.
Run vault setup-agent, configure CLI/MCP, do an Obsidian dry-run before importing,
and finish with a search/read/propose smoke test.
```

Manual install:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install "vault-for-llm[mcp]==0.6.24"

vault setup-agent
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
vault-mcp --project-dir /path/to/your/project --tool-profile core
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

### Optional Supabase dependency

Supabase sync is optional. Install its dependency only when you want a remote
sync/read path:

```bash
pip install "vault-for-llm[supabase]"
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

For autonomous agents or unreviewed memories, prefer the safer candidate workflow. This is the recommended path after PR27:

```bash
vault remember "Memory title" \
  --content "Markdown memory content" \
  --reason "Why this is worth remembering"

# after review
vault promote mem_xxxxxxxxxxxx --confirm
```

MCP-compatible agents should use `vault_memory_propose` and `vault_memory_promote`; see [MCP memory workflow](docs/mcp_memory_workflow.md).

The gates are intentionally simple and deterministic:

| Gate | Plain-language job |
|---|---|
| Privacy | “Does this look like a secret or private data?” |
| Duplicate | “Do we already have this memory or a near copy?” |
| Metadata | “Does it at least have a title/content/reason?” |
| Quality | “Is this specific enough to be useful and findable later?” |

### Search QA: checking whether memory recall is healthy

Search QA is a small exam for your vault. Some questions should find a known note; some hard-negative questions should find nothing. This helps catch both kinds of mistakes: forgetting the right memory and confidently returning the wrong one.

```bash
vault search-qa run \
  --qa-file benchmarks/search_qa/basic.en.json \
  --mode keyword \
  --min-score 0.34 \
  --output /tmp/searchqa.json
```

Fixtures can use `expected_no_results: true` for “do not return anything” checks. See the [Search QA benchmarking guide](docs/search_qa_benchmarking.md).

### Dream curation reports

Run a report-first memory curation pass:

```bash
vault dream --mode report --limit 50 --write-report
```

Reports are written under `reports/dream/`. `apply_safe` can apply only narrow metadata fixes, and it writes a plan plus backup path so you can roll back if the cleanup was not what you wanted. See [dream workflow](docs/dream_workflow.md).


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

## Common CLI Commands

| Command | Purpose |
|---|---|
| `vault init` | Initialize a project vault |
| `vault setup-agent` | Run the interactive agent installer and optional Obsidian sync template generator |
| `vault remember "Title" --content "..." --reason "..."` | Propose candidate memory for review |
| `vault promote <candidate_id> --confirm` | Promote reviewed candidate memory |
| `vault compile` | Compile Markdown into SQLite |
| `vault import obsidian --vault /path/to/ObsidianVault --dry-run` | Preview importing existing Obsidian notes into `raw/obsidian/` |
| `vault search "query"` | Search project memory |
| `vault map read <id> --lines 10-30` | Read a bounded range for citation |
| `vault remove <id> --confirm` | Remove a reviewed knowledge entry by ID |

For the broader command surface, see the [CLI reference](docs/cli_reference.md).

### Agent setup wizard

Use [`docs/agent_install.md`](docs/agent_install.md) plus `vault setup-agent`
or its alias `vault install-agent` when an agent should guide the installation
instead of asking a human to run every command manually:

```bash
vault setup-agent

vault setup-agent \
  --non-interactive \
  --agent codex \
  --scope shared \
  --agent-project-dir ~/Vaults/my-project \
  --features core,mcp,obsidian_import \
  --obsidian-vault ~/Documents/ObsidianVault \
  --import-obsidian \
  --obsidian-sync all
```

The wizard asks for database scope, project directory, MCP, semantic search, Supabase sync, Headroom context compression, developer/benchmark dependencies, an existing Obsidian vault path, whether to run the first import, and whether to generate cron, LaunchAgent, or n8n sync templates. Semantic, Supabase, Headroom, and dev dependencies default to off. `headroom` is an advanced optional feature for context compression; it is not required for Vault memory governance and should stay off unless the user has long logs, large tool output, or token pressure.

### Obsidian export

Use `vault export obsidian` when you want humans to browse the compiled vault in Obsidian without changing the source knowledge base:

```bash
vault export obsidian \
  --vault /path/to/ObsidianVault \
  --category technique \
  --dry-run
```

The export is intentionally one-way and read-only: it reads from `vault.db`, writes Markdown notes under `00-Vault-Knowledge/`, includes YAML frontmatter plus `Vault #<id>` citations, and does not write back to `raw/`, `compiled/`, SQLite, or any remote sync target. Re-running the command overwrites the same stable note paths instead of creating duplicates.

### Obsidian import and sync

If a user already has an Obsidian vault, agents can import those Markdown notes back into Vault:

```bash
vault import obsidian \
  --vault /path/to/ObsidianVault \
  --dry-run

vault import obsidian \
  --vault /path/to/ObsidianVault \
  --compile
```

The import path copies user-authored notes into `raw/obsidian/`, preserves the original Obsidian path and content hash in frontmatter, and skips `.obsidian/`, `.trash/`, `.git/`, and `00-Vault-Knowledge/` by default. This keeps Vault's own exported notes from being re-imported as source material.

Use `--dry-run` first when connecting an existing vault. Re-running the import is idempotent: unchanged notes are skipped, changed notes update the same raw path, and `--compile` is the explicit step that writes the imported notes into `vault.db`. For automatic sync, schedule the same command with cron, LaunchAgent, n8n, or an agent installer; no always-on watcher is required for the first version.

For citation-safe memory use, see the [Document Map citation policy](docs/document_map_citation_policy.md): search results are navigation hints, while `vault map read` returns bounded source text for final citations.

---

## MCP integration

Install MCP extras and start the server:

```bash
pip install "vault-for-llm[mcp]"
vault-mcp --project-dir /path/to/your/project --tool-profile core
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

MCP can expose different tool profiles:

| Profile | Tools | Use when |
|---|---|---|
| `core` | `vault_search`, `vault_read_range`, `vault_memory_propose`, `vault_stats` | Daily agent use with fewer tool-schema tokens |
| `review` | Core plus `vault_memory_promote`, `vault_dream_run` | A trusted operator or agent reviews candidate memory |
| `remote` | Core plus Supabase remote read tools | Agents read a synced cross-host memory view |
| `maintenance` | Review plus freshness/convergence checks | Scheduled or operator-led curation |
| `full` | All tools, including compatibility `vault_add` | Backward compatibility or explicit power-user setups |

`full` remains the default for backward compatibility. For production agent
sessions, prefer `--tool-profile core` or an explicit allowlist:

```bash
vault-mcp --project-dir /path/to/project \
  --tools vault_search,vault_read_range,vault_memory_propose,vault_stats
```

Tool profiles reduce the tools advertised through `tools/list`; they are not a
security boundary. Run `vault-mcp` only for agents you trust with the selected
project directory.

For agent loops, prefer `vault_search` → `vault_read_range`. `vault_search`
returns compact MCP payloads by default, including source and range hints when
available. Use `vault_map_show` from a broader profile only when the agent needs
section navigation before reading. Final answers should cite `vault_read_range`
output rather than search previews.

---

## Optional Supabase sync

Core Vault-for-LLM usage is local-only. Supabase support is for teams or remote read paths that want a synced copy of local SQLite data.

The local SQLite database remains the source of truth. Supabase is an optional sync/read target. Remote table names use Vault-branded defaults and can be overridden with `VAULT_SUPABASE_*_TABLE` environment variables when integrating an existing private schema.

This is useful when multiple hosts need to share project memory. For example,
Hermes Agent on a workstation, Codex on a laptop, OpenClaw on another machine,
and n8n on a server can all use local Vaults while syncing approved memory to
one Supabase project for cross-host recall.

Knowledge and skill sync use a minimal-disclosure default: metadata, summaries, hashes, Document Map rows, and claims sync without full `content_raw`. Use `--include-content` only when you intentionally want full local content copied to Supabase; fail-severity privacy findings are still withheld.

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

## Retrieval quality (Search QA benchmarks)

### Evidence snapshot

Vault-for-LLM is measured as a retrieval and project-memory QA layer, not only
as a note database. These numbers are evidence probes, not universal guarantees;
larger or different corpora should be re-tested with the included benchmark
commands.

| Probe | Result | Caveat |
|---|---:|---|
| Repo onboarding fixture | Vault top-k/source/read-range guidance `28/28`; Codex transcript baseline `7/28`; Hermes/Nancy transcript baseline `3/28` | 28-task source-aware project benchmark; private transcripts are not committed |
| Candidate-first memory | `0` active-memory pollution before promotion | candidate proposals do not enter official memory automatically |
| LoCoMo hierarchical retrieval probe | `97.7%` Any evidence@50 and `90.5%` All evidence@50 on official-scored categories | retrieval evidence score only; not an official answer/judge leaderboard score |

See [Agent Onboarding Benchmark](docs/agent_onboarding_benchmark.md) for the
reproducible repo fixture and exported-session comparison workflow.

### Search QA fixture

Vault-for-LLM ships deterministic Search QA fixtures that measure retrieval
quality before and after code changes. Results below use the English fixture
(`benchmarks/search_qa/basic.en.json`) against a fresh database compiled from
the same fixture data (keyword/FTS5 mode):

| Metric | Value |
|---|---|
| total_cases | 3 |
| top-1 recall | 2/3 ≈ **67%** |
| top-k recall | 2/3 ≈ **67%** |
| no-result precision | 1.0 |
| Mean Reciprocal Rank | 0.67 |

The benchmark covers:
- `en_document_map_read_range` — "tool-gated reading map navigation read_range evidence" → expects "Tool-gated Reading"
- `en_citation_policy_boundary` — "citation policy boundary final answer support" → expects "Citation Policy Boundary"
- `en_no_result_control` — random string query → expects no results (false-positive check)

A Chinese counterpart (`basic.zh-Hant.json`) is also available but uses the
same synthetic knowledge, so metrics are identical.

To run locally:

```bash
python -m pytest tests/test_search_quality_metrics.py -v
```

Semantic/hybrid mode requires an embedding model (`--allow-hash` for CI smoke).
Results may vary — keyword search is the stable baseline.

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

Apache-2.0
