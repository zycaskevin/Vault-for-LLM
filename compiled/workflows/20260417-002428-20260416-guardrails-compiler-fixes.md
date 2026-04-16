---
title: "Guardrails Compiler 修復"
type: "workflows"
source: "raw"
original_date: ""
tags: []
processed_date: "2026-04-17T00:24:28.514758"
quality_score: 3
---

# Guardrails Compiler 修復

修復 L2 current.md 垃圾資料、刪除 compiled/ 重複檔案、解決並發問題、修正腳本路徑與縮排錯誤

## 關鍵要點
- 改用 state.db 查詢非 cron 來源的 session
- 刪除 compiled/ 目錄中同 source 的舊版本檔案
- 使用 file lock 避免 cron 同時觸發 compiler
- 支援環境變數覆蓋腳本路徑，修正縮排錯誤


## 相關連結
[Guardrails Compiler, cron job, file lock, state.db, compiled directory]

---
*自動編譯於 2026-04-17 00:24:28*