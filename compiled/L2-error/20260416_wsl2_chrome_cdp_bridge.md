---
category: error
hash: 234e92228130a7d9
id: 273
layer: L2
tags: ''
title: 20260416 wsl2 chrome cdp bridge
trust: 0.5
updated_at: '2026-04-16T22:55:43.651472+00:00'
---

# WSL2 Chrome CDP 三層橋接方案
##問題
Hermes Agent 跑在 WSL2，Chrome 跑在 Windows。WSL2 無法直連 Windows localhost:9222（CDP 綁定 127.0.0.1 only）。
## 解法：三層橋接
1. Chrome — `--remote-debugging-port=9222` 監聽 `127.0.0.1:9222`
2. tcp-proxy.js — Windows Node.js TCP 轉發 `0.0.0.0:9223 → 127.0.0.1:9222`
3. cdp-bridge.py — WSL Python aiohttp HTTP/WS Proxy `0.0.0.0:3456 → <gateway>:9223`
## 踩坑
- Chrome 147+ `--remote-debugging-port` 必須先 kill 所有 chrome.exe 才生效，否則 flag 被靜默忽略
... (原 17 段，取前 5 段)
