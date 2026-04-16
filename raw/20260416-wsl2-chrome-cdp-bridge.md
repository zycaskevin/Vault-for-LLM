# WSL2 Chrome CDP 三層橋接方案

##問題
Hermes Agent 跑在 WSL2，Chrome 跑在 Windows。WSL2 無法直連 Windows localhost:9222（CDP 綁定 127.0.0.1 only）。

## 解法：三層橋接
1. Chrome — `--remote-debugging-port=9222` 監聽 `127.0.0.1:9222`
2. tcp-proxy.js — Windows Node.js TCP 轉發 `0.0.0.0:9223 → 127.0.0.1:9222`
3. cdp-bridge.py — WSL Python aiohttp HTTP/WS Proxy `0.0.0.0:3456 → <gateway>:9223`

## 踩坑
- Chrome 147+ `--remote-debugging-port` 必須先 kill 所有 chrome.exe 才生效，否則 flag 被靜默忽略
- 必須用獨立 profile (`--user-data-dir=cdp-chrome-profile`)，否則跟日常 Chrome 衝突
- Node.js ESM `import('ws')` 無法解析全局安裝的模組 — 放棄 Node，改用 Python aiohttp
- `/json/new` Chrome 要求 PUT verb，不是 GET（回傳 "Using unsafe HTTP verb GET"）
- cdp_command 要直接連 target 的 `webSocketDebuggerUrl`（從 `/json` list 取得），不能建立 browser-level session（會 "Session with given id not found"）
- Gateway IP 可用 `ip route show default | grep -oP 'via \K[\d.]+'` 自動偵測
- Windows TCP proxy 用 Node.js 原生 `net` 模組即可，不需要 ws 模組

## 開源
已 fork 為 https://github.com/zycaskevin/Hermes-web-access（MIT 授權）

## 技術棧
- Python 3.10+ / aiohttp（cdp-bridge.py）
- Node.js（tcp-proxy.js，Windows 端）
- Chrome DevTools Protocol
- fcntl file lock（防並發）
