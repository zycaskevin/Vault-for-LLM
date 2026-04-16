---
category: general
hash: fef904807a03b09c
id: 91
layer: L3
tags: test-data,experience-base,summaries
title: 20260411 test experience base summaries 245
trust: 0.5
updated_at: '2026-04-16T17:21:16.111930+00:00'
---

# 測試數據: experience-base_proactive-agent_1
## 原始文件
experience-base/best-practices/proactive-agent.md
## 推斷類別
summaries
## 內容片段
```python
def should_intervene(context):
if context.urgent:
return True
if context.milestone_reached:
return True
if context.user_explicit_request:
return True
return False
```
---
*用於分類器測試的數據*
