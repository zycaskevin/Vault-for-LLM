---
category: error
hash: 2673df4cf970457d
id: 20
layer: L3
tags: vllm,timeout,error,debugging
title: 20260411 system logs error vllm timeout
trust: 0.5
updated_at: '2026-04-17T02:12:21.998754+00:00'
---

TITLE:20260411 system logs error vllm timeout
- 在執行長時間推理任務時，vLLM 服務在 120 秒後返回超時ERR。
- Error: Request timeout after 120000ms。
- Model: /home/zycas/models/qwen3。
- Endpoint: http://127.0.0.1:8000/v1/chat/completions。
- 輸入 token 數 > 2000
- 模型加載後首次推理
- 系統內存使用率 > 70%
- 增加請求超時時間至 300 秒
... (11 more)
