# Guardrails Compiler 修復記錄

## 問題 1：L2 current.md 全是 cron 垃圾
- 原因：update_recent_sessions() 從 ~/.hermes/cron/output/ 取最近 .md
- 但那個目錄 100% 是 cron job 輸出（618 cron vs 71 telegram sessions）
- 修復：改從 state.db sessions 表查詢，WHERE source NOT LIKE 'cron%'
- 加去重：同一對話因 context compaction 會拆成多個 session，用 first_msg[:50] 去重
- LIMIT 30 → 去重後取 10

## 問題 2：compiled/ 目錄重複檔案
- 原因：同一 source 被多個 cron 觸發編譯，時間戳命名導致不覆蓋
- 修復：寫入前先刪同 source 舊版本（`glob(f'*-{raw_file.stem}.md')`）
- 清除歷史重複：8 個重複檔案已刪

## 問題 3：compiler 並發
- 原因：cron 可能同時觸發兩次 compiler
- 修復：fcntl.flock(LOCK_EX | LOCK_NB) file lock
- 第二個實例直接跳過，不等待

## 問題 4：腳本路徑寫死
- 修復：GUARDRAILS_DIR 支援 GUARDRAILS_PATH 環境變數覆蓋
- .env 讀取順序：.env.local → .env → ~/.hermes/.env
- 三個腳本同步修改：compiler、L2 update、wakeup

## Bug: wakeup.py 縮排錯誤
- os.environ.setdefault(k, v) 跑出 if 外面，導致每行都執行
- 修復：修正縮排 + 加 break

## 教訓
- 百科更新後要主動寫入經驗，不要等用戶提醒
- 多個 cron 可能同時跑同一腳本，file lock 是必須的
