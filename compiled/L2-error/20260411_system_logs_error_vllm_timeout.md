---
category: error
hash: 2673df4cf970457d
id: 5
layer: L2
tags: vllm,timeout,error,debugging
title: 20260411 system logs error vllm timeout
trust: 0.5
updated_at: '2026-04-16T22:55:43.617137+00:00'
---

# vLLM 超時錯誤處理記錄
## 錯誤描述
在執行長時間推理任務時，vLLM 服務在 120 秒後返回超時錯誤。
## 錯誤訊息
```
Error: Request timeout after 120000ms
Model: /home/zycas/models/qwen3
Endpoint: http://127.0.0.1:8000/v1/chat/completions
```
## 發生條件
1. 輸入 token 數 > 2000
2. 模型加載後首次推理
3. 系統內存使用率 > 70%
## 解決方案
... (原 9 段，取前 5 段)
