---
category: error
hash: 234e92228130a7d9
id: 10
layer: L3
tags: ''
title: 20260416 wsl2 chrome cdp bridge
trust: 0.5
updated_at: '2026-04-17T02:12:21.940934+00:00'
---

TITLE:20260416 wsl2 chrome cdp bridge
- Hermes Agent 跑在 WSL2，Chrome 跑在 Windows。
- Chrome — `--remote-debugging-port=9222` 監聽 `127.0.0.1:9222`
- tcp-proxy.js — Windows Node.js TCP 轉發 `0.0.0.0:9223 → 127.0.0.1:9222`
- cdp-bridge.py — WSL Python aiohttp HTTP/WS Proxy `0.0.0.0:3456 → <gateway>:9223`
- Chrome 147+ `--remote-debugging-port` 必須先 kill 所有 chrome.exe 才生效，否則 flag 被靜默忽略
- 必須用獨立 profile (`--user-data-dir=cdp-chrome-profile`)，否則跟日常 Chrome 衝突
- Node.js ESM `import('ws')` 無法解析全局安裝的模組 — 放棄 No...
