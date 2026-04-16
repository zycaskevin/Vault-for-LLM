---
title: "Guardrails Compiler 修復"
type: "workflows"
source: "raw"
original_date: ""
tags: []
processed_date: "2026-04-16T22:22:35.458802"
quality_score: 3
---

# Guardrails Compiler 修復

修復 L2 current.md 垃圾資料、刪除 compiled/ 重複檔案、解決並發問題、調整腳本路徑、修正縮排錯誤

## 關鍵要點
- 修改 L2 current.md 來源為 state.db 並去重
- 刪除 compiled/ 目錄中同 source 的舊版本檔案
- 使用 file lock 避免 compiler 並發執行
- 支援環境變數覆蓋腳本路徑
- 修正 wakeup.py 縮排錯誤


## 相關連結
[Guardrails Compiler, state.db, cron job, file lock, environment variables]

---
*自動編譯於 2026-04-16 22:22:35*