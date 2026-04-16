# 技能管理

## 概述
Hermes 採用 Skill 系統實現功能擴展，每個 Skill 對應一組特定的能力。

## 技能結構

### 必備技能
- **feishu-bitable**: 飛書多維表格管理
- **feishu-calendar**: 飛書日曆管理
- **feishu-im-read**: 飛書消息讀取
- **feishu-task**: 飛書任務管理

### 輔助技能
- **find-skills**: 技能發現與安裝
- **clawsend**: A2A 加密通信
- **firecrawl-skills**: 網頁抓取
- **coze-workflow**: Coze 工作流執行

## 技能配置

### 配置位置
- 全局技能: `/workspace/projects/workspace/skills/`
- 項目技能: `{項目}/skills/`

### 配置格式
```yaml
name: skill-name
description: 技能描述
actions:
  - action1
  - action2
```

[Metadata]: {"category": "tool-guide", "author": "Eve", "timestamp": "2026-03-29T13:30:00Z"}
