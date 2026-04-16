# Guardrails Lite — Agent Installation Guide

> This document is written for AI agents. If you're an AI reading this, follow the steps below to install Guardrails Lite for your user.

## Quick Install (Recommended)

```bash
# 1. Create a virtual environment
python3 -m venv ~/.guardrails-lite
source ~/.guardrails-lite/bin/activate

# 2. Install from local (or future PyPI)
pip install -e /path/to/Vault-for-LLM

# 3. Initialize a project
cd /path/to/your/project
guardrails init

# 4. Verify
guardrails doctor
```

## Semantic Search (Optional)

```bash
# Install ONNX embedding support (~150MB, no PyTorch needed)
pip install guardrails-knowledge[semantic]

# Download embedding model (interactive)
guardrails install-embedding
# Choose: zh (Chinese), en (English), mix (Mixed, recommended)

# Verify
guardrails doctor
# Should show: onnxruntime ✅, optimum[onnxruntime] ✅
```

## Three Install Modes

### Mode 1: Minimal (Keyword search only)
```bash
pip install guardrails-knowledge
guardrails init
# Search works with keyword matching only
```

### Mode 2: Semantic (Local ONNX embeddings)
```bash
pip install guardrails-knowledge[semantic]
guardrails init
guardrails install-embedding
# Search works with vector similarity (recommended)
```

### Mode 3: Ollama (Zero extra install if you have Ollama)
```bash
pip install guardrails-knowledge
guardrails init
guardrails config set embedding.provider ollama
guardrails config set embedding.model nomic-embed-text
# Uses your existing Ollama installation
```

## Environment Check

```bash
guardrails doctor
```

Expected output:
```
Python               3.11.x ✅
sqlite-vec           ✅ 0.1.9
onnxruntime          ✅ 1.24.x  (or ❌ if not installed)
optimum[onnxruntime] ✅         (or ❌ if not installed)
Ollama               ✅/❌
嵌入模型快取           ✅/❌
```

## Usage Workflow

```bash
# 1. Add knowledge (3 ways)
guardrails add "My Title" --content "Knowledge content here"
guardrails add "My Title" --file knowledge.md
# Or just put .md files in raw/ directory

# 2. Compile (raw/ → database + compiled/)
guardrails compile

# 3. Search
guardrails search "GPU memory issues"           # auto mode
guardrails search "GPU memory" --mode keyword    # keyword only
guardrails search "GPU memory" --mode hybrid     # blended
guardrails search "GPU memory" --layer L2         # filter by layer

# 4. List & Stats
guardrails list
guardrails list --layer L2 --category error
guardrails stats

# 5. Health check
guardrails lint
guardrails doctor
```

## Knowledge File Format

Put `.md` files in `raw/` directory with YAML frontmatter:

```markdown
---
title: Knowledge Title
layer: L2
category: error
tags: tag1,tag2,tag3
trust: 0.9
source: real-experience
---

# Knowledge Title

Content here. Will be compressed to AAAK format during compile.
```

### Layer Guide
- **L0**: Identity (who am I, core values)
- **L1**: Core facts (environment, active projects)
- **L2**: Context (recent decisions, troubleshooting)
- **L3**: Deep knowledge (architecture,踩坑記錄)

### Trust Score Guide
- 0.9+: Verified by real experience
- 0.7-0.8: High confidence from documentation
- 0.5-0.6: General knowledge, not yet verified
- Below 0.3: Unverified, needs review

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
from guardrails_lite.guardrails_embed import ONNXEmbeddingProvider
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