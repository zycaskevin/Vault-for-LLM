---
category: error
hash: ae54e2c22b851565
id: 8
layer: L3
tags: ''
title: 20260416 supabase l2 upsert 重複插入
trust: 0.5
updated_at: '2026-04-16T23:50:07.932313+00:00'
---

TITLE:20260416 supabase l2 upsert 重複插入
- > 類型: error | 來源: session | 日期: 2026-04-16。
- guardrails_l2_update.py 每次執行都會在 Supabase 插入新記錄，即使 title+category 相同。
- content_hash 使用 MD5(content) 計算，而 content 包含時間戳（自動更新：2026-04-16 11:30），導致每次執行 hash 都不同。
- 真正Q是：遷移腳本留下了 title 為 'active'、'current'、'topics' 的舊 L2 記錄（來自本地 L2 檔名），和新的 '活躍技能清單'、'當前話題'、'最近 Ses...
- content_hash 改用 stable_hash：排除時間戳後的內容算 hash
- upsert 前先刪除重複記錄（delete_supabase_duplicates）
- 刪除遷移遺留的舊 title 記錄
