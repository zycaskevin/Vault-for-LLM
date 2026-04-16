---
category: technique
hash: 97d31cf81c2fe98c
id: 268
layer: L2
tags: ''
title: 20260416 hermes web access fork
trust: 0.5
updated_at: '2026-04-16T22:55:43.656036+00:00'
---

# Hermes web-access 開源 Fork 流程
## 背景
eze-is/web-access 是 Claude Code 專用的聯網技能（Node.js cdp-proxy.mjs）。
Hermes Agent 需要 Python 原生版本 + WSL2 橋接。
## Fork 改造重點
1. cdp-proxy.mjs → cdp-bridge.py（Python aiohttp，零 Node 版本依賴）
2. 新增 WSL2 三層橋接架構
3. 新增 cdp-bridge.sh 管理腳本（start/stop/status/restart）
4. 新增 Windows 一鍵啟動（start_chrome_cdp.bat）
5. SKILL.md 去掉所有 Claude Code 專屬內容，改為 Hermes 原生
6. auto-detect WSL2 gateway IP（`ip route show default`）
## 安全審計
推到公開 repo 前必須掃描：
- 硬編碼的私有 IP（172.29.x.x）
... (原 12 段，取前 5 段)
