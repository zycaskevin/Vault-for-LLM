---
title: "Guardrails 跨LLM橋接"
type: "techniques"
source: "raw"
original_date: ""
tags: []
processed_date: "2026-04-17T00:24:32.743413"
quality_score: 3
---

# Guardrails 跨LLM橋接

解決Claude Code無法讀取Guardrails知識庫的問題，提供三種方案。

## 關鍵要點
- 方案1：CLAUDE.md注入L0+L1內容，簡易橋接
- 方案2：UserPromptSubmit Hook自動搜尋並插入相關知識
- 方案3：README.md索引優化，提升知識庫可讀性


## 相關連結
Guardrails, Hermes Agent, Obsidian, L0-L3架構, Supabase

---
*自動編譯於 2026-04-17 00:24:32*