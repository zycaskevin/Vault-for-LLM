---
category: architecture
hash: e73d6386afacc76d
id: 129
layer: L3
tags: test-data,knowledge-base,concepts
title: 20260411 test knowledge base concepts 30
trust: 0.5
updated_at: '2026-04-16T17:21:16.303619+00:00'
---

# 測試數據: knowledge-base_model-routing_0
## 原始文件
knowledge-base/core-concepts/model-routing.md
## 推斷類別
concepts
## 內容片段
### AUTO 模式
```python
def route_model(intent, complexity):
if complexity < 0.3:
return "gemini-flash"  # 1 point
elif complexity < 0.7:
return "claude-sonnet"  # 5 points
else:
return "claude-opus"   # 20 points
```
---
*用於分類器測試的數據*
