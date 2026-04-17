---
category: architecture
hash: c17d64ff7dc73fad
id: 11
layer: L2
tags: guardrails,RAG,分塊,語意分塊,摘要引導,chapter-detection,向量搜尋
title: Guardrails Lite 長文件分塊匯入 — 4 種策略對標 2025 SOTA
trust: 0.95
updated_at: '2026-04-17T02:12:21.946922+00:00'
---

TITLE:Guardrails Lite 長文件分塊匯入 — 4 種策略對標 2025 SOTA
- 丟一部 10 萬字小說到 Guardrails，原本只會變成 1 筆知識 → 1 個模糊向量 → 搜「主角跟誰吵架」只能找到整本書。
- 正則偵測中文章節（第X章/節）、英文章節（Chapter X/Part X）、Markdown 標題（# / ##）
- 短章直接當一塊，長章內部再用語意分塊
- 零 LLM 成本，純規則
- 計算相鄰句子嵌入向量的餘弦相似度
- 相似度驟降處 (< threshold) 切斷
- 保證每塊語意連貫，不會把兩個不相關話題黏在一起
- 用文本前 2000 字當「摘要代理」
... (28 more)
