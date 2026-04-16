---
category: general
hash: 0d10f4f1f26544ea
id: 173
layer: L3
tags: test-data,knowledge-base,summaries
title: 20260411 test knowledge base summaries 20
trust: 0.5
updated_at: '2026-04-16T17:21:16.536033+00:00'
---

# 測試數據: knowledge-base_database-design_2
## 原始文件
knowledge-base/integrations/supabase/database-design.md
## 推斷類別
summaries
## 內容片段
### messages 表
```sql
CREATE TABLE messages (
id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
conversation_id UUID REFERENCES conversations(id),
role TEXT,
content TEXT,
created_at TIMESTAMP DEFAULT NOW()
);
```
---
*用於分類器測試的數據*
