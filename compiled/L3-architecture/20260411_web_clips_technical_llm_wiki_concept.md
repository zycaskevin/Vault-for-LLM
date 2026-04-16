---
category: architecture
hash: e19dc9df524e02bb
id: 19
layer: L3
tags: ai,knowledge-management,llm,compilation
title: 20260411 web clips technical llm wiki concept
trust: 0.5
updated_at: '2026-04-16T23:50:10.296861+00:00'
---

TITLE:20260411 web clips technical llm wiki concept
- Andrej Karpathy 在 2026 年 4 月提出了一個名為「LLM Wiki」的知識管理ARCH。
- 傳統的 RAG（檢索增強生成）模式在每次提問時，都會重新掃描原始檔案，知識無法疊加；而 LLM Wiki 則是讓 AI 扮演「編譯器」，將散落的筆記、EXP分享或文獻，預先閱讀並整理成結構化的知...
- **raw/（原始資料層）**
- 定位：絕對不可變動（Immutable）的來源庫
- 內容：收集所有未經處理的原始資訊
- **先分類，再萃取**：針對不同資訊屬性應用不同萃取邏輯
- **雙重輸出迴圈**：每次向知識庫提問時，AI 不只要給出答案，還要同步更新對應的 Wiki 頁面
- **隔離工作區**：人類自行驗證過的確切筆記，必須與 AI 正在自動擴寫的「草稿區」分開
... (9 more)
