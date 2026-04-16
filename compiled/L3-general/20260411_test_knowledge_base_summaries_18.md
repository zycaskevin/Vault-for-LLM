---
category: general
hash: 308e2df346433ff4
id: 171
layer: L3
tags: test-data,knowledge-base,summaries
title: 20260411 test knowledge base summaries 18
trust: 0.5
updated_at: '2026-04-16T17:21:16.512870+00:00'
---

# 測試數據: knowledge-base_database-design_0
## 原始文件
knowledge-base/integrations/supabase/database-design.md
## 推斷類別
summaries
## 內容片段
### users 表
```sql
CREATE TABLE users (
id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
email TEXT UNIQUE,
name TEXT,
created_at TIMESTAMP DEFAULT NOW()
);
```
---
*用於分類器測試的數據*
