---
category: error
hash: 15bd27aef283e7d0
id: 35
layer: L3
tags: test-data,error-base,techniques
title: 20260411 test error base techniques 168
trust: 0.5
updated_at: '2026-04-16T17:21:15.826500+00:00'
---

# 測試數據: error-base_port-9000-conflict_1
## 原始文件
error-base/error-catalog/port-conflict/port-9000-conflict.md
## 推斷類別
techniques
## 內容片段
## 解決方案
1. 確認 9000 端口被系統服務佔用（PID 1045）
2. 禁止殺掉此進程（系統服務）
3. 修改應用配置，使用其他端口
---
*用於分類器測試的數據*
