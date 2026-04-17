# Vault-for-LLM 简体中文说明

**[繁體中文](README.zh-Hant.md) | [简体中文](README.zh-CN.md) | [English](README.md)**

> 🧠 本地优先、开源的四层分层知识管理系统，让任何 LLM Agent 拥有持久、可搜索的记忆。
> 零云端依赖。零 Docker。零 PyTorch。`pip install` 即可使用。

---

## 这是什么？

Vault-for-LLM 是一个专为 LLM Agent 设计的**四层分层知识库**。它完全在本地运行，使用 SQLite + sqlite-vec + ONNX 嵌入模型，让你的 AI Agent 能够记住东西。

### 核心特色

- **四层架构**（L0–L3）— 结构化知识注入
- **混合搜索**：关键词 + 语义向量搜索（ONNX，无需 GPU）
- **知识图谱**：自动推断实体与关系边，支持 BFS 扩展
- **AAAK 压缩**：6 倍压缩率，大幅减少 token 消耗
- **信任评分**：每条知识都有信心分数（0.0–1.0）
- **质量检查**：自动 lint 与矛盾检测
- **CLI 优先**：20+ 命令，完整管理生命周期

---

## 架构说明

```
L0 身份层      → Agent 是谁（每次对话注入）
L1 核心事实    → 环境与活跃项目（每次对话注入）
L2 动态情境    → 近期决策与调试记录（每日自动更新）
L3 深度知识    → 架构、技术、经验（按需搜索）
```

### 为什么要分层？

| 层级 | 加载时机 | Token 成本 | 示例 |
|------|----------|-----------|------|
| L0 | 每次对话 | 极低（<100） | Agent 名称、角色、基本规则 |
| L1 | 每次对话 | 低（<500） | 操作系统、安装工具、活跃项目 |
| L2 | 需要时 | 中（<2000） | 昨天修了什么 bug、最近的技术决策 |
| L3 | 按需搜索 | 按需 | 某框架的踩坑笔记、API 用法 |

---

## 快速开始

```bash
# 安装
pip install -e .

# 初始化项目
guardrails init

# 新增知识
guardrails add "我的第一条知识" --content "今天学到的东西"

# 编译（raw/ → 数据库 + compiled/）
guardrails compile

# 搜索
guardrails search "我要找的关键字"

# 健康检查
guardrails doctor
```

详细安装选项请参阅 [INSTALL.md](INSTALL.md)。

---

## 目录结构

```
你的项目/
├── guardrails.yaml          ← 项目配置（guardrails init 自动生成）
├── L0-identity/             ← 身份层（每次对话注入）
│   └── identity.md
├── L1-core-facts/           ← 核心事实（每次对话注入）
│   └── current-projects.md
├── L2-context/              ← 动态情境（每日自动更新）
│   └── recent-sessions/
│       └── current.md
├── L3-knowledge/            ← 深度知识（按需搜索）
├── raw/                     ← 原始知识输入（你的 .md 文件放这里）
├── compiled/                ← AAAK 压缩备份（自动生成）
└── templates/               ← L0/L1/L2 干净模板
```

---

## AI 整合指南

### 通用 LLM Agent

1. 阅读 `L0-identity/identity.md` 了解用户
2. 阅读 `L1-core-facts/current-projects.md` 了解现状
3. 使用 `guardrails search "查询"` 进行语义搜索

### Claude Code / Cursor / 任何 AI IDE

1. 将 `CLAUDE.md` 复制到项目根目录
2. 深度知识搜索：使用 `rg "关键字" raw/ compiled/`
3. 或使用 `guardrails search "查询"`

---

## CLI 命令参考

| 命令 | 说明 |
|------|------|
| `guardrails init` | 初始化新项目 |
| `guardrails doctor` | 健康检查 |
| `guardrails add "标题" --content "内容"` | 新增知识条目 |
| `guardrails add "标题" --file 文件.md` | 从文件导入 |
| `guardrails compile` | 编译 raw/ → 数据库 + compiled/ |
| `guardrails search "查询"` | 搜索（自动：关键词 + 语义） |
| `guardrails list` | 列出所有条目 |
| `guardrails stats` | 显示数据库统计 |
| `guardrails lint` | 执行质量检查 |
| `guardrails graph build` | 构建知识图谱 |
| `guardrails graph show` | 显示图谱摘要 |

---

## 知识文件格式

所有 `.md` 文件使用 YAML frontmatter：

```yaml
---
title: "知识标题"
category: "concept|technique|workflow|lesson|error|comparison"
layer: "L0|L1|L2|L3"
tags: ["标签1", "标签2"]
trust: 0.0-1.0
source: "来源说明"
created: "YYYY-MM-DD"
---
```

### 信任评分指南

| 范围 | 含义 |
|------|------|
| 0.9+ | 经实际验证 |
| 0.7–0.8 | 来自文档，高信心 |
| 0.5–0.6 | 一般知识，尚未验证 |
| < 0.3 | 未验证，需要审核 |

---

## 编译器

```bash
guardrails compile
```

执行流程：
- `raw/` → 数据库（以内容哈希去重）
- `raw/` → `compiled/`（AAAK 6 倍压缩）
- 自动 L2 更新 + lint 健康检查 + git commit

---

## 技术栈

| 组件 | 技术 | 原因 |
|------|------|------|
| 数据库 | SQLite + sqlite-vec | 零配置、可携带、向量搜索 |
| 嵌入模型 | ONNX Runtime（~150MB） | 不需 PyTorch/GPU |
| 搜索 | 混合（关键词 + 向量） | 两全其美 |
| 图谱 | SQLite（实体 + 边） | 轻量关系追踪 |
| 压缩 | AAAK 格式 | 6 倍大小缩减 |

---

## 系统需求

- Python 3.10+
- ~150MB（ONNX 嵌入模型，可选）
- 不需要 GPU、不需要 Docker、不需要云端账号

---

## 授权

MIT License — 详见 [LICENSE](LICENSE)。

---

*为开发者打造 — 让你的 AI Agent 真正记住事情。*
