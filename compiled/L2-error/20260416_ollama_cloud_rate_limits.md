---
category: error
hash: 2d5e3e86a34c3460
id: 270
layer: L2
tags: ''
title: 20260416 ollama cloud rate limits
trust: 0.5
updated_at: '2026-04-16T22:55:43.635047+00:00'
---

# Ollama Cloud API 限流踩坑
## 方案
Pro $20/月（2026/04）
## 限制
- 同時 3 個雲端模型並行（Max $100/月才 10 個）
- 每 5 小時 session limit 重置，每 7 天 weekly limit 重置
... (原 28 段，取前 5 段)
