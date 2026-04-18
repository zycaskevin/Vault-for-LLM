# Vault-for-LLM Setup Guide

Get your AI knowledge base running in 5 minutes.

## Prerequisites

- Python 3.10+
- Git

No cloud, no Docker, no GPU required.

---

## Quick Install

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/Vault-for-LLM.git
cd Vault-for-LLM

# 2. Install
pip install -e .

# 3. Initialize
vault init

# 4. Verify
vault doctor
```

See [INSTALL.md](INSTALL.md) for detailed installation options (semantic search, Ollama, etc.)

---

## Initial Setup

### Step 1: Fill in your identity (L0)

Copy the template and edit:
```bash
cp templates/L0-identity/identity.md L0-identity/identity.md
# Edit L0-identity/identity.md with your information
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

## Connect your AI

### Claude Code / Cursor / Any AI IDE
1. Copy `CLAUDE.md` to your project root — it contains the integration guide
2. AI will auto-read L0 + L1, and search L3 on demand

### Any LLM Agent
1. Read `README.md` to understand the architecture
2. Read `L0-identity/identity.md` for user context
3. Use `vault search "query"` for knowledge retrieval

---

## Upgrade: Semantic Search (Optional)

```bash
pip install guardrails-knowledge[semantic]
vault install-embedding
# Choose: zh (Chinese), en (English), mix (Mixed, recommended)
```

Benefits:
- Vector similarity search (not just keyword)
- Better recall for paraphrased queries
- Knowledge graph with BFS expansion

---

## FAQ

**Q: Do I need to use all four layers?**
A: L0+L1 are essential (AI needs to know who you are). L2+L3 are optional but strongly recommended.

**Q: Token cost?**
A: L0+L1 inject ~500-800 tokens per conversation. L3 uses AAAK compression — only 1/6 of original token cost.

**Q: Trust scores?**
A: User-defined = 1.0, verified = 0.9, documentation = 0.7, unverified = 0.5. When knowledge conflicts, AI trusts higher scores.

---

*Questions? Open a GitHub Issue*
