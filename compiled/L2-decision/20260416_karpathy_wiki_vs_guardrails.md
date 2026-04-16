---
category: decision
hash: ae938ac13c6d94bb
id: 269
layer: L2
tags: ''
title: 20260416 karpathy wiki vs guardrails
trust: 0.5
updated_at: '2026-04-16T22:55:43.660257+00:00'
---

# Karpathy LLM Wiki vs Guardrails 百科對照分析
## 骨架對照
| Karpathy | Guardrails | 差異 |
|----------|-----------|------|
| raw/ | raw/ (L3) | 一樣 |
| wiki/ (compiled pages) | compiled/ + Supabase AAAK | AAAK 是給 LLM 讀的壓縮格式，不是給人讀的長文 |
| schema / CLAUDE.md | L0 identity + L1 core facts | Guardrails 多了信任分數和實體關聯 |
| index.md | L2 dynamic context | 自動生成，不是手動維護的 MOC |
## Karpathy 做得好的（我們要帶回來）
1. **矛盾偵測** — 新素材進來自動比對舊 page 衝突，標出留給人判斷
2. **跨頁連鎖更新** — 新 source 可能同時動到 10-15 張 page
3. **Lint / 健康檢查** — 掃整座 wiki 找孤立 page、過期內容、概念缺口
## 我們比他好的
1. **分層服務** — L0→L1→L2→L3，不同問題拿不同層，不需要每次翻整座 wiki
2. **信任分數** — 每條知識 trust 0-1，互相矛盾的資訊不會平等對待
3. **AAAK 壓縮** — 6x 壓縮，LLM 讀更少 token
4. **自動化** — L2 自動從 state.db 拉 session 摘要、自動統計活躍技能
## 核心分歧：容器問題
... (原 15 段，取前 5 段)
