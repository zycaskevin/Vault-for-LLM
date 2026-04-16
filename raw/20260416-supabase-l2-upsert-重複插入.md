# Supabase L2 UPSERT 重複插入

> 類型: error | 來源: session | 日期: 2026-04-16

## 問題
guardrails_l2_update.py 每次執行都會在 Supabase 插入新記錄，即使 title+category 相同。

## 原因
content_hash 使用 MD5(content) 計算，而 content 包含時間戳（自動更新：2026-04-16 11:30），導致每次執行 hash 都不同。但 upsert_supabase() 用 layer+category+title 查重，這個邏輯本身沒問題。

真正問題是：遷移腳本留下了 title 為 'active'、'current'、'topics' 的舊 L2 記錄（來自本地 L2 檔名），和新的 '活躍技能清單'、'當前話題'、'最近 Session' 衝突。

## 修復
1. content_hash 改用 stable_hash：排除時間戳後的內容算 hash
2. upsert 前先刪除重複記錄（delete_supabase_duplicates）
3. 刪除遷移遺留的舊 title 記錄
4. 24 筆 → 3 筆

---
*採集時間: 2026-04-16 11:45*