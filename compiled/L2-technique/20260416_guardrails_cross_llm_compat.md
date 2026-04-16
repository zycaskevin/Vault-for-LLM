---
category: technique
hash: 2a823fcb5770228f
id: 266
layer: L2
tags: ''
title: 20260416 guardrails cross llm compat
trust: 0.5
updated_at: '2026-04-16T22:55:43.626075+00:00'
---

# Guardrails 百科 — 跨 LLM 相容指南
## 問題
目前 Guardrails 只被 Hermes Agent 讀取。接 Claude Code / OpenClaw 時完全讀不到知識。
## 解法：CLAUDE.md / AGENTS.md 橋接
### 方案 1：CLAUDE.md 注入 L0+L1（最簡單）
Claude Code 每次啟動自動讀 CLAUDE.md。把 L0+L1 的核心內容寫進去：
```markdown
# CLAUDE.md
... (原 21 段，取前 5 段)
