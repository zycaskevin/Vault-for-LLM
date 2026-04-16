---
category: error
hash: 2d5e3e86a34c3460
id: 9
layer: L3
tags: ''
title: 20260416 ollama cloud rate limits
trust: 0.5
updated_at: '2026-04-16T23:45:27.639904+00:00'
---

TITLE:20260416 ollama cloud rate limits
- Pro $20/月（2026/04）。
- 同時 3 個雲端模型並行（Max $100/月才 10 個）
- 每 5 小時 session limit 重置，每 7 天 weekly limit 重置
- 用量以 GPU 時間計算，不是 token 數
- 短時間連續呼叫 5+ 個大模型請求（如多模型辯論）
- 長 prompt + 大模型（deepseek-v3.2, kimi-k2.5, qwen3.5:397b）= 高 GPU 時間
- delegate_task 同時派 3+ 個子代理到 Ollama Cloud
- 請求 timeout（60s+ 無回應）
... (14 more)
