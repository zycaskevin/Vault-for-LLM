# Vault-for-LLM — Claude Code Integration Guide

## Quick Start

Vault-for-LLM is a local-first knowledge system for LLM agents. It compiles
Markdown notes into a searchable SQLite database with keyword search (FTS5/BM25),
optional semantic embeddings, document-map bounded reads, and candidate-first
memory gates.

## Prerequisites

- Python 3.10+
- SQLite 3.35+ (with FTS5 support)

## Installation

```bash
# Core install (keyword search only)
pip install vault-for-llm

# With optional semantic search
pip install "vault-for-llm[semantic]"

# With optional MCP server
pip install "vault-for-llm[mcp]"
```

## MCP Integration

Vault-for-LLM exposes an MCP server for agent memory workflows.

### Setup

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

### MCP Tool Priority (for Claude Code / agent loops)

```
vault_search → vault_map_show → vault_read_range
```

1. **`vault_search`** — Search active knowledge. Returns compact results by default;
   pass `compact: false` only when fuller previews are needed.
2. **`vault_map_show`** — Inspect the document map (sections, claims, hierarchy).
3. **`vault_read_range`** — Read a bounded source range and get a citation string.
   **Final answers should cite `vault_read_range` output, NOT search snippets.**

### Candidate-First Memory (recommended for agents)

```text
1. vault_memory_propose   # create candidate (goes through gates)
2. human/agent review     # inspect privacy/duplicate/metadata results
3. vault_memory_promote   # explicit confirm=true
4. vault_search           # find it later
```

Do NOT use `vault_add` for autonomous agents — it writes directly to active
knowledge and bypasses the candidate review gate.

### Available MCP Tools

| Category | Tools |
|---|---|
| Retrieval | `vault_search`, `vault_stats` |
| Candidate-first memory | `vault_memory_propose`, `vault_memory_promote` |
| Curation | `vault_dream_run` |
| Bounded reading | `vault_map_show`, `vault_read_range` |
| Compatibility | `vault_add` (prefer candidate-first tools) |
| Remote (optional) | `vault_remote_map_show`, `vault_remote_read_range` |

### Environment Variables

- `GUARDRAILS_PATH` — Override the project path used by `vault-mcp`. Defaults
  to the `--project-dir` argument or the current directory.

## Core CLI Workflow

```bash
# Initialize
vault init

# Add knowledge (legacy — prefer candidate-first)
vault add "Topic" --content "Content"

# Compile to SQLite
vault compile

# Search
vault search "what I'm looking for"
```

## Candidate-First Workflow (recommended)

```bash
# Propose a memory (goes through privacy/duplicate/quality gates)
vault remember "Memory title" \
  --content "Markdown memory content" \
  --reason "Why this is worth remembering"

# Promote after review
vault promote mem_xxxxxxxxxxxx --confirm
```

## Semantic Search (optional)

```bash
# Install with semantic extras
pip install "vault-for-llm[semantic]"

# Auto-detect and install embedding model
vault install-embedding --model mix

# Or configure Ollama
vault config set embedding.provider ollama
vault config set embedding.model nomic-embed-text

# Rebuild semantic index
vault semantic rebuild
```

## Knowledge Layers

- **L0 Identity** — loaded every session (who the user/project is)
- **L1 Core Facts** — stable environment and project facts
- **L2 Recent Context** — recent decisions, incidents, working context
- **L3 Deep Knowledge** — lessons, APIs, architecture; searched on demand

Files live in `raw/`, `templates/L0-identity/`, `templates/L1-core-facts/`,
`templates/L2-context/`. Run `vault compile` to build the SQLite database.

## Testing

```bash
pip install ".[dev]"
pytest -q
```

193 tests covering CLI, search, semantic, MCP, document map, memory curator,
dream workflow, DB backup, and repo hygiene.

## Repository Structure

```
vault/          # Core package (cli, db, search, mcp, compiler, etc.)
scripts/        # Operational scripts (sync, audit, privacy scan, etc.)
tests/          # 22 test files, 193 tests
benchmarks/     # Search QA benchmarks (JSON fixtures)
docs/           # Architecture docs, upgrade plans, roadmaps
templates/      # L0/L1/L2 knowledge templates
raw/            # Compiled knowledge source (run vault compile)
```

## Safety Notes

- `vault-mcp` is a local stdio server with **no network authentication**.
  Only use with trusted agents.
- Core usage is local-only. Supabase sync is optional.
- Memory gates block secret-like content, duplicates, and weak metadata.
