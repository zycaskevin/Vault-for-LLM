---
category: error
hash: 011fc8138845921a
id: 12
layer: L3
tags: guardrails-lite,contextual-retrieval,ollama,chunking,vector-search
title: Guardrails Lite Contextual Retrieval — Ollama 本地上下文增強
trust: 0.8
updated_at: '2026-04-17T02:12:21.952520+00:00'
---

TITLE:Guardrails Lite Contextual Retrieval — Ollama 本地上下文增強
- 長文件分塊後，每塊變成獨立向量，失去與整份文件的上下文關聯。
- 為每個分塊生成 1-2 句上下文摘要，前置到嵌入文本：。
- `content_raw`：存原文（搜尋時顯示）
- `content_aaak`：存帶上下文的壓縮版
- contextualize_chunks(。
- chunks: list[ChunkResult],。
- ollama_model: str = "qwen3:8b",。
- 檢查 Ollama 是否可用（`/api/tags`）
... (38 more)
