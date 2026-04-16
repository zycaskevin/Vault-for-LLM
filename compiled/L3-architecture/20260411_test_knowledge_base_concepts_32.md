---
category: architecture
hash: 520d72c7c1d414bb
id: 130
layer: L3
tags: test-data,knowledge-base,concepts
title: 20260411 test knowledge base concepts 32
trust: 0.5
updated_at: '2026-04-16T17:21:16.308520+00:00'
---

# 測試數據: knowledge-base_model-routing_2
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
