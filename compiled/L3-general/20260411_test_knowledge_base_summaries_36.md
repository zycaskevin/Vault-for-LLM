---
category: general
hash: 8fa77863f3ffafda
id: 183
layer: L3
tags: test-data,knowledge-base,summaries
title: 20260411 test knowledge base summaries 36
trust: 0.5
updated_at: '2026-04-16T17:21:16.588629+00:00'
---

# 測試數據: knowledge-base_webhook_0
## 原始文件
knowledge-base/core-concepts/webhook.md
## 推斷類別
summaries
## 內容片段
@app.route('/webhook', methods=['POST'])
def handle_webhook():
data = request.json
# 處理 webhook 數據
return {"status": "ok"}
```
---
*用於分類器測試的數據*
