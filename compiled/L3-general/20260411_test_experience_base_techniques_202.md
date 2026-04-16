---
category: general
hash: 00e582c18f6fe0d0
id: 107
layer: L3
tags: test-data,experience-base,techniques
title: 20260411 test experience base techniques 202
trust: 0.5
updated_at: '2026-04-16T17:21:16.193175+00:00'
---

# 測試數據: experience-base_memory-system-lesson-20260330_2
## 原始文件
experience-base/lessons-learned/memory-system-lesson-20260330.md
## 推斷類別
techniques
## 內容片段
[Situation] 啟用記憶回憶功能後，每次對話都會檢索相關記憶並注入到上下文
[Wrong] 忽視記憶回憶的 token 消耗，導致成本顯著增加
[Correct] 設置合理的上限（autoRecallMaxChars 和 autoRecallMaxItems），監控實際 token 使用，必要時調整參數
[Behavior Change] 啟用記憶回憶前評估 token 消耗影響，設置合理上限並持續監控
[Activation] 當啟用記憶回憶功能時，或當發現 token 消耗異常增加時
---
*用於分類器測試的數據*
