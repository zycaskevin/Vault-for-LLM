# Vault-for-LLM

**[繁體中文](README.zh-Hant.md) | [简体中文](README.zh-CN.md) | English**

> 🧠 A local-first, open-source knowledge management system for LLM agents.
> Zero cloud dependency. Zero Docker. Zero PyTorch. Just `pip install` and go.

---

## What is Vault-for-LLM?

Vault-for-LLM is a **four-layer hierarchical knowledge base** designed to give any LLM agent persistent, searchable memory. It runs entirely locally using SQLite + sqlite-vec + ONNX embeddings.

### Key Features

- **Four-layer architecture** (L0–L3) for structured knowledge injection
- **Hybrid search**: keyword + semantic vector search (ONNX, no GPU needed)
- **Knowledge graph**: auto-inferred entities and edges with 2-hop BFS expansion
- **Atomic claims with source citations**: sub-chunk granularity, every claim traceable to original text
- **Self-questioning convergence**: system judges if it "knows enough" to explain a topic (KAL-inspired)
- **Cross-family LLM validation**: extract with one model, verify with another to catch hallucinations
- **Freshness tracking + FSRS spaced repetition**: automated staleness detection and review scheduling
- **AAAK compression**: 6x compression for compiled knowledge
- **Trust scoring**: every knowledge entry has a confidence score (0.0–1.0)
- **Lint & contradiction detection**: automatic quality checks
- **MCP server**: expose your vault to any MCP-compatible AI agent mid-conversation
- **CLI-first**: 20+ commands for full lifecycle management

---

## Architecture

```
L0 Identity      → Who the user is (injected every conversation)
L1 Core Facts    → Environment & active projects (injected every conversation)
L2 Context       → Recent decisions & troubleshooting (auto-updated daily)
L3 Deep Knowledge → Architecture, techniques, lessons (searched on demand)
```

---

## What's New in v0.4.0

| Feature | Description |
|---------|-------------|
| **Convergence Check** | KAL-inspired self-questioning loop — system asks "Can I explain this?" and keeps learning until it can |
| **Cross Validation** | Asymmetric LLM verification — extract claims with Model A, verify with Model B |
| **Freshness Tracking** | Automatic staleness detection + FSRS interval scheduling for knowledge review |
| **Atomic Claims** | Claims at sub-chunk granularity with `source_span` citations for precision retrieval |
| **Graph Expansion** | 2-hop recursive CTE walk through knowledge graph for contextual retrieval |
| **MCP Server** | Model Context Protocol server — let any chat AI query and inject knowledge mid-conversation |
| **Updated CLI** | New commands: `vault converge`, `vault cross-validate`, `vault freshness` |

See [CHANGELOG.md](CHANGELOG.md) for full details.

---

## Installation

### Quick Install

```bash
# 1. Clone
git clone https://github.com/zycaskevin/Vault-for-LLM.git
cd Vault-for-LLM

# 2. Install (optionally use a venv)
python3 -m venv ~/.vault-for-llm
source ~/.vault-for-llm/bin/activate
pip install -e .

# 3. Initialize a project
vault init

# 4. Verify
vault doctor
```

### Three Install Modes

**Mode 1: Minimal** — keyword search only
```bash
pip install vault-for-llm
vault init
# Search works with keyword matching only
```

**Mode 2: Semantic** — local ONNX embeddings (~150MB, no PyTorch/GPU needed)
```bash
pip install vault-for-llm[semantic]
vault init
vault install-embedding
# Choose: zh (Chinese), en (English), mix (Mixed, recommended)
# Search works with vector similarity (recommended)
```

**Mode 3: Ollama** — zero extra install if you already have Ollama
```bash
pip install vault-for-llm
vault init
vault config set embedding.provider ollama
vault config set embedding.model nomic-embed-text
# Uses your existing Ollama installation
```

### Environment Check

```bash
vault doctor
```

Expected output:
```
Python               3.11.x ✅
sqlite-vec           ✅ 0.1.9
onnxruntime          ✅ 1.24.x  (or ❌ if not installed)
optimum[onnxruntime] ✅         (or ❌ if not installed)
Ollama               ✅/❌
Embedding cache       ✅/❌
```

---

## Initial Setup

### Step 1: Fill in who YOU are (L0)

Copy the template and edit — this is about you, the user, not the AI:
```bash
cp templates/L0-identity/identity.md L0-identity/identity.md
# Edit L0-identity/identity.md with YOUR information
```

### Step 2: Fill in core facts (L1)

```bash
cp templates/L1-core-facts/current-projects.md L1-core-facts/current-projects.md
# Edit with your current projects and environment
```

### Step 3: Add your first knowledge entry (L3)

Create a `.md` file in `raw/`:

```markdown
---
title: "My First Knowledge Entry"
category: "technique"
layer: L3
tags: ["tag1", "tag2"]
trust: 0.8
source: "real-experience"
created: "2026-04-17"
---

# My First Knowledge Entry

What you learned, what broke, what worked.
```

### Step 4: Compile

```bash
vault compile
```

This will:
- Compile `raw/` entries to `compiled/` (AAAK 6x compression)
- Build the search index
- Auto git commit (for easy rollback)
- Run lint health checks

---

## Directory Structure

```
your-project/
├── L0-identity/             ← Who the user is (injected every conversation)
│   └── identity.md
├── L1-core-facts/           ← Core facts (injected every conversation)
│   └── current-projects.md
├── L2-context/              ← Dynamic context (auto-updated daily)
│   └── recent-sessions/
│       └── current.md
├── L3-knowledge/            ← Deep knowledge (searched on demand)
├── raw/                     ← Raw knowledge input (your .md files go here)
├── compiled/                ← AAAK compressed backup (auto-generated)
├── guardrails.db            ← SQLite database (auto-generated by `vault compile`)
└── templates/               ← Clean templates for L0/L1/L2
```

---

## AI Integration Guide

### Any LLM Agent (Universal)

1. Read this README to understand the architecture
2. Read `L0-identity/identity.md` to know the user
3. Read `L1-core-facts/current-projects.md` for current state
4. Use `vault search "query"` for semantic search

### Claude Code / Cursor / Any AI IDE

1. Copy `CLAUDE.md` (included) into your project root
2. For deep knowledge, search `compiled/` or `raw/`
3. Use `rg "keyword" raw/ compiled/` for fast lookup

### MCP Integration (Chat with your vault)

Connect your vault to any MCP-compatible AI agent:

```bash
# Install MCP dependencies
pip install "vault-for-llm[mcp]"

# Start the server
vault-mcp --project-dir /path/to/your/project
```

Now your AI can **search, add, and query knowledge mid-conversation** — no manual copy-paste needed.

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `vault init` | Initialize a new project |
| `vault doctor` | Health check |
| `vault add "Title" --content "..."` | Add knowledge entry |
| `vault add "Title" --file notes.md` | Add from file |
| `vault import doc.md` | Import long document (auto-chunked) |
| `vault compile` | Compile raw/ → database + compiled/ |
| `vault search "query"` | Search (auto: keyword + semantic) |
| `vault search "query" --graph-expand 2` | Search + 2-hop graph expansion |
| `vault list` | List all entries |
| `vault stats` | Show database statistics |
| `vault lint` | Run quality checks |
| `vault converge` | Self-questioning convergence check |
| `vault cross-validate` | Cross-family LLM validation |
| `vault freshness` | Freshness + review scheduling |
| `vault dedup` | Detect semantic duplicates |
| `vault dedup --dry-run` | Preview merge plan (no changes) |
| `vault dedup --merge` | Auto-merge duplicates (keeps higher trust) |
| `vault graph build` | Build knowledge graph |
| `vault graph show` | Show graph summary |
| `vault graph export --format mermaid` | Export graph as Mermaid diagram |
| `vault graph expand <id>` | Expand from a specific node |
| `vault config set <key> <value>` | Set config (e.g. embedding provider) |

---

## MCP Server (Claude Code / Cursor / OpenClaw)

Expose your vault directly to any MCP-compatible AI agent:

```bash
# Install MCP dependencies
pip install "vault-for-llm[mcp]"

# Start the server (run from your project directory)
vault-mcp

# Or specify path explicitly
vault-mcp --project-dir /path/to/your/project
```

Add to your Claude Code config (`~/.claude/claude_desktop_config.json`):

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

Available MCP tools: `vault_search`, `vault_add`, `vault_get`, `vault_list`, `vault_stats`

---

## Knowledge File Format

All `.md` files use YAML frontmatter:

```yaml
---
title: "Knowledge Title"
category: "concept|technique|workflow|lesson|error|comparison"
layer: "L0|L1|L2|L3"
tags: ["tag1", "tag2"]
trust: 0.0-1.0
source: "source-description"
created: "YYYY-MM-DD"
---
```

### Trust Score Guide

| Range | Meaning |
|-------|---------|
| 0.9+ | Verified by real experience |
| 0.7–0.8 | High confidence from documentation |
| 0.5–0.6 | General knowledge, not yet verified |
| < 0.3 | Unverified, needs review |

---

## Compiler

```bash
vault compile
```

What it does:
- `raw/` → database (upsert by content hash)
- `raw/` → `compiled/` (AAAK 6x compression)
- Extract atomic claims with source_span citations
- Auto L2 update + lint health check + git commit

---

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Database | SQLite + sqlite-vec | Zero-config, portable, vector search |
| Embeddings | ONNX Runtime (~150MB) | No PyTorch/GPU needed |
| Search | Hybrid (keyword + vector + graph expansion) | Best of both worlds |
| Graph | SQLite (entities + edges + 2-hop CTE) | Lightweight relationship tracking |
| Compression | AAAK format | 6x size reduction |
| Validation | Cross-family LLM + Convergence check | Catch what single models miss |

---

## Requirements

- Python 3.10+
- ~150MB for ONNX embedding model (optional)
- No GPU, no Docker, no cloud account needed

---

## FAQ

**Q: Do I need to use all four layers?**
A: L0+L1 are essential (AI needs to know who you are). L2+L3 are optional but strongly recommended.

**Q: Token cost?**
A: L0+L1 inject ~500-800 tokens per conversation. L3 uses AAAK compression — only 1/6 of original token cost.

**Q: Trust scores?**
A: User-defined = 1.0, verified = 0.9, documentation = 0.7, unverified = 0.5. When knowledge conflicts, AI trusts higher scores.

---

## Troubleshooting

### sqlite-vec not found
```bash
pip install sqlite-vec
# If that fails, you may need to build from source
pip install sqlite-vec --no-binary :all:
```

### ONNX model download fails
```bash
# Manual download
python3 -c "
from vault.guardrails_embed import ONNXEmbeddingProvider
e = ONNXEmbeddingProvider(model_key='mix')
e._ensure_model()
"
```

### Ollama not connecting
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags
# Make sure you have an embedding model installed
ollama pull nomic-embed-text
```

---

## License

MIT License — see [LICENSE](LICENSE).

---

*Built for developers who want their AI agents to actually remember things.*