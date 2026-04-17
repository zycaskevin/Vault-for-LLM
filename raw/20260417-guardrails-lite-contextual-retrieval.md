---
title: Guardrails Lite Contextual Retrieval — Ollama 本地上下文增強
layer: L3
tags: [guardrails-lite, contextual-retrieval, ollama, chunking, vector-search]
trust: 0.8
---

# 問題

長文件分塊後，每塊變成獨立向量，失去與整份文件的上下文關聯。搜「人類唯一的優勢」只能靠向量相似度猜，但因為分塊內容太短太局部，精確度下降。

# 解法：Contextual Retrieval（Anthropic 2024）

為每個分塊生成 1-2 句上下文摘要，前置到嵌入文本：

- `content_raw`：存原文（搜尋時顯示）
- `content_aaak`：存帶上下文的壓縮版
- **嵌入向量 = context_prefix + content**（這是關鍵）

用 Ollama 本地生成上下文，零雲端依賴。

# 實作

## 函數簽名

```python
contextualize_chunks(
    chunks: list[ChunkResult],
    doc_title: str,
    ollama_model: str = "qwen3:8b",
    ollama_url: str = "http://localhost:11434",
    max_context_length: int = 150,
) -> list[ChunkResult]
```

## 流程

1. 檢查 Ollama 是否可用（`/api/tags`）
2. 依序嘗試：指定模型 → qwen3:8b → llama3.2:3b → gemma3:4b → mistral:7b → 任何可用模型
3. 對每個 chunk 發 `/api/generate`，prompt 要求 1-2 句上下文
4. 截斷過長內容（>150 字），設 `chunk.context_prefix`
5. Ollama 不可用時自動降級（等同 v1.5），不報錯

## CLI 用法

```bash
guardrails import novel.md --strategy chapter --title "三體" --contextualize
guardrails import novel.md --strategy chapter --title "三體" --contextualize --ollama-model qwen2.5:0.5b
```

## 嵌入邏輯（_add_chunk）

```python
# 嵌入用 context + content（Contextual Retrieval 核心）
embed_text = f"{context_prefix}\n{content}" if context_prefix else content

# AAAK 壓縮版也帶上下文
content_for_aaak = f"【{context_prefix}】{content}" if context_prefix else content
aaak = simple_aaak_compress(title, content_for_aaak)

# 原文單獨存，搜尋命中後顯示用
db.add_knowledge(content_raw=content, content_aaak=aaak, ...)
```

# 踩坑

## 1. Ollama timeout

原始 `timeout=30` 在 8B 模型純 CPU 推理時不夠（每 chunk ~40s）。改為 `timeout=120`。

## 2. CLI 顯示 bug

contextualize 完成 CLI 卻顯示「未啟用」。原因：用 `LIKE '【%'` 檢查 `content_aaak`，但 aaak 開頭是 `TITLE:...`，不是 `【`。改為 `LIKE '%【%'`。

## 3. pip install -e . 必須重跑

修改代碼後不重裝 CLI 會用舊版快取，導致 debug 幽靈。

# 測試結果

三體小說 5 章分塊，A/B 對比：

| 查詢 | 無 context | 有 context | 改善 |
|------|-----------|-----------|------|
| 葉文潔向太陽發射信號 | 0.677 | 0.634 | -6%（本來就高）|
| 人類唯一的優勢 | 0.462 | **0.523** | **+13.2%** |

符合 Anthropic 論文預期：模糊查詢改善顯著，精確查詢影響小。

# Ollama 模型選擇

| 模型 | 速度（CPU） | 品質 | 適用場景 |
|------|-----------|------|---------|
| qwen2.5:0.5b | ~5s/chunk | 一般 | 快速測試、大量文件 |
| qwen3:8b | ~40s/chunk | 好 | 正式匯入、品質優先 |

# 路線圖

- v1：chapter + semantic chunking
- v1.5：summary-guided（用前 2000 字當 surrogate summary）
- v2：Contextual Retrieval ✅（本次）
- v2.5：Adaptive Chunking（自動選策略）— 暫緩
- v3：Proposition-level chunking
- v4：RAPTOR（遞迴摘要樹）
- v5：GraphRAG

# 相關

- guardrails_import.py：分塊 + contextualize 邏輯
- guardrails_cli.py：`--contextualize` / `--ollama-model` 參數
- Anthropic Contextual Retrieval 原始論文：https://www.anthropic.com/research/contextual-retrieval