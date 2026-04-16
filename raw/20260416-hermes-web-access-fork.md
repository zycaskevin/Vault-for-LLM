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
- 用戶特定路徑（C:\Users\User）
- 帳號/token/chat ID
- __pycache__/*.pyc

## 授權
雙版權 MIT：fork 作者 + 上游原作者（一澤 Eze）

## 教訓
- GitHub 已有初始 commit 時，force push 前先 pull --rebase 處理分歧
- .git-credentials 可用於 git push 認證（`git config --global credential.helper store`）
