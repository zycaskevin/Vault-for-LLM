---
source: "line-tools-article"
title: "Day 98 用 AI 讀 LINE 訊息？這個工具讓你不用自己翻對話紀錄"
platform: "line"
category: "tool-introduction"
language: "zh-TW"
tags: ["LINE", "MCP", "Claude Code", "AI工具", "桌面自動化", "台灣"]
confidence: 0.95
extracted_at: "2026-04-12T11:50:00+08:00"
---

# Day 98 用 AI 讀 LINE 訊息？這個工具讓你不用自己翻對話紀錄

## 原始文章內容

在台灣工作，LINE 幾乎是逃不掉的溝通工具。
工作上的對話散落在各個群組和私聊裡，每次要回顧某段討論都得自己慢慢翻。
如果你也有這個困擾，這篇介紹一個開源工具，讓 AI 直接幫你讀 LINE 訊息。

---

### 【MCP 是什麼？】

MCP（Model Context Protocol，模型上下文協定）你可以把它想成 AI 的"外掛"。
就像手機可以裝 App 來擴充功能，MCP 就是讓 AI 助手可以連接外部工具的標準介面。

---

### 【LINE Desktop MCP 運作原理】

底層原理是模擬滑鼠點擊和鍵盤輸入——讓程式"假裝是你在操作電腦"。

不是透過 LINE 的官方 API，而是直接操控電腦上已經登入的 LINE 桌面版。

完全不會觸發 LINE 的任何限制，不會被封鎖或停權。

---

### 【支援平台】

- Windows（需要 AutoHotkey v2）
- macOS（需要 cliclick）
- LINE 桌面版 v9.10 以上

---

### 【設定方式】

在 Claude Code 的全域設定檔（~/.claude.json）加入：

```json
"line-desktop-mcp": {
  "command": "npx",
  "args": ["line-desktop-mcp@latest"]
}
```

---

### 【實際體驗】

終端機用 Claude Code 操作 → 流暢快速
Claude Cowork 模式 → 慢（退而求其次用 computer use）

原因：Cowork 模式沒正確使用 MCP 外掛，而是用截圖方式操作。

---

### 【應用場景】

- 快速搜尋某段時間的對話紀錄
- 請 AI 整理某個群組的討論重點
- 自動發送制式訊息

---

### 【作者】

台灣開發者，GitHub 開源

---

*原文作者：Day 98*
*發布平台：未知*
*原始連結：未知*