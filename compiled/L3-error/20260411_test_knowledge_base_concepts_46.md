---
category: error
hash: 68f5420c73540924
id: 132
layer: L3
tags: test-data,knowledge-base,concepts
title: 20260411 test knowledge base concepts 46
trust: 0.5
updated_at: '2026-04-16T17:21:16.318735+00:00'
---

# 測試數據: knowledge-base_synchronization-protocol_1
## 原始文件
knowledge-base/core-concepts/synchronization-protocol.md
## 推斷類別
concepts
## 內容片段
| 觸發條件 | 動作 | 模式 |
|----------|------|------|
| 定時 (每60分鐘) | pull 最新知識 | Light |
| 任務完成 | push 經驗/錯誤 | Full |
| 新技能發現 | push skill | Full |
| 錯誤發生 | push error | Full |
| 手動請求 | full sync | Full |
---
*用於分類器測試的數據*
