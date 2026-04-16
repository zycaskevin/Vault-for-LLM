---
category: decision
hash: c202b607d3a47c3b
id: 4
layer: L3
tags: ''
title: 20260416 guardrails compiler fixes
trust: 0.5
updated_at: '2026-04-16T23:45:27.614147+00:00'
---

TITLE:20260416 guardrails compiler fixes
- WHY：update_recent_sessions() 從 ~/.hermes/cron/output/ 取最近 .md
- 但那個目錄 100% 是 cron job 輸出（618 cron vs 71 telegram sessions）
- 修復：改從 state.db sessions 表查詢，WHERE source NOT LIKE 'cron%'
- WHY：同一 source 被多個 cron 觸發編譯，時間戳命名導致不覆蓋
- 修復：寫入前先刪同 source 舊版本（`glob(f'*-{raw_file.stem}.md')`）
- 清除歷史重複：8 個重複檔案已刪
- WHY：cron 可能同時觸發兩次 compiler
- 修復：fcntl.flock(LOCK_EX | LOCK_NB) file lock
... (10 more)
