---
category: general
hash: f1e4a00b0fc5e0d6
id: 172
layer: L3
tags: test-data,knowledge-base,summaries
title: 20260411 test knowledge base summaries 19
trust: 0.5
updated_at: '2026-04-16T17:21:16.525576+00:00'
---

# 測試數據: knowledge-base_database-design_1
## 原始文件
knowledge-base/integrations/supabase/database-design.md
## 推斷類別
summaries
## 內容片段
### conversations 表
```sql
CREATE TABLE conversations (
id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
user_id UUID REFERENCES users(id),
title TEXT,
created_at TIMESTAMP DEFAULT NOW()
);
```
---
*用於分類器測試的數據*
