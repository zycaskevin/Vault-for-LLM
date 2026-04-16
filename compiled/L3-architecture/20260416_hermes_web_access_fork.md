---
category: architecture
hash: 97d31cf81c2fe98c
id: 7
layer: L3
tags: ''
title: 20260416 hermes web access fork
trust: 0.5
updated_at: '2026-04-16T23:45:27.629269+00:00'
---

TITLE:20260416 hermes web access fork
- eze-is/web-access 是 Claude Code 專用的聯網技能（Node.js cdp-proxy.mjs）。
- Hermes Agent 需要 Python 原生版本 + WSL2 橋接。
- cdp-proxy.mjs → cdp-bridge.py（Python aiohttp，零 Node 版本依賴）
- 新增 WSL2 三層橋接ARCH
- 新增 cdp-bridge.sh 管理腳本（start/stop/status/restart）
- 推到公開 repo 前必須掃描：。
- 硬編碼的私有 IP（172.29.x.x）
- 用戶特定路徑（C:\Users\User）
... (8 more)
