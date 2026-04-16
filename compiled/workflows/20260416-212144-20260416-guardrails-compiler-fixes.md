---
title: "Guardrails Compiler 修復"
type: "workflows"
source: "raw"
original_date: ""
tags: []
processed_date: "2026-04-16T21:21:44.251554"
quality_score: 3
---

# Guardrails Compiler 修復

修復 L2 current.md 垃圾資料、刪除 compiled/ 重複檔案、解決並發問題、支援環境變數、修正縮排錯誤

## 關鍵要點
- 改用 state.db 查詢非 cron 會話，並去重
- 刪除 compiled/ 同 source 重複檔案
- 使用 file lock 避免 compiler 並發
- 支援 GUARDRAILS_PATH 環境變數
- 修正 wakeup.py 縮排錯誤


## 相關連結
[Guardrails Compiler, cron job, file lock, environment variables, session management]

---
*自動編譯於 2026-04-16 21:21:44*