---
category: technique
hash: c202b607d3a47c3b
id: 265
layer: L2
tags: ''
title: 20260416 guardrails compiler fixes
trust: 0.5
updated_at: '2026-04-16T22:55:43.621811+00:00'
---

# Guardrails Compiler 修復記錄
## 問題 1：L2 current.md 全是 cron 垃圾
- 原因：update_recent_sessions() 從 ~/.hermes/cron/output/ 取最近 .md
- 但那個目錄 100% 是 cron job 輸出（618 cron vs 71 telegram sessions）
- 修復：改從 state.db sessions 表查詢，WHERE source NOT LIKE 'cron%'
... (原 25 段，取前 5 段)
