---
title: "Holographic Memory vs Guardrails 分工架構"
date: 2026-04-17
tags: [memory-system, guardrails, holographic, architecture, design-decision]
trust: 1.0
---

# Holographic Memory vs Guardrails 分工

## 核心原則：分層分工，不衝突

**Holographic Memory** = 海馬迴（自動、輕量、快速）
- 偏好（Arthur 喜歡什麼、不喜歡什麼）
- 人際關係（誰是誰）
- 即時決策（這次對話才決定的事）
- 小事實（生日、時區、模型名稱）

**Guardrails 百科** = 大腦皮層（手動+半自動、深度、結構化）
- L0 身份 / L1 核心事實 / L2 動態上下文 / L3 深度知識
- 踩過的坑、架構決策、文章審查、流程 SOP

## 四條規則

1. **隨口小事實 → Holographic**（自動存，memory/fact_store 工具）
2. **完整修復/決策 → Guardrails**（鐵律：做完就寫 raw/）
3. **Holographic 發現矛盾 → 通知 Guardrails 升級為正式知識**
4. **Guardrails L1 核心事實 → Holographic 不重複存**（以 Guardrails 為主）

## 為什麼不衝突

- Holographic 擅長自動捕捉（對話中的事實、偏好）
- Guardrails 擅長結構化深度（AAA K壓縮、信任分數、演化追蹤）
- 兩者重疊時，Guardrails 為權威來源（因為經過 compiler 審核）
- Holographic 的矛盾偵測是預警系統，不是最終答案

## 資料量對比

| | Holographic | Guardrails |
|---|---|---|
| 筆數 | ~6 條 | ~120 條 |
| 存儲 | SQLite (memory_store.db) | Supabase + 本地 .md |
| 搜尋 | HRR向量+FTS5+Jaccard | pgvector + rg關鍵字 |
| 觸發 | AI 自動寫 | 人+AI 手動寫入 raw/ → compiler |