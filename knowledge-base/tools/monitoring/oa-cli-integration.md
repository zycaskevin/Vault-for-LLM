# OA CLI 監控系統集成

## 概述
OA CLI (Open Agent CLI) 是用於監控和管理 AI 無人公司的命令行工具。

## 核心功能

### 1. 自我發現
自動檢測 Agent 能力邊界。

### 2. 自我修復
自動檢測問題並觸發修復。

### 3. 自我進化
提供歷史數據支持優化。

## 使用方式

### 查看狀態
```bash
cd /workspace/projects/workspace/oa-project && oa status
```

### 收集數據
```bash
cd /workspace/projects/workspace/oa-project && oa collect
```

### 啟動 Dashboard
```bash
cd /workspace/projects/workspace/oa-project && oa serve
```

## Dashboard
- **地址**: http://localhost:3460
- **功能**: 目標卡片、流程圖追蹤、自動刷新

[Metadata]: {"category": "tool-guide", "author": "Eve", "timestamp": "2026-03-29T13:30:00Z"}
