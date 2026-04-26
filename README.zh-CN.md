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
L0 身份层      → 使用者是谁（每次对话注入）
L1 核心事实    → 环境与活跃项目（每次对话注入）
L2 动态情境    → 近期决策与调试记录（每日自动更新）
L3 深度知识    → 架构、技术、经验（按需搜索）
```

### 为什么要分层？

| 层级 | 加载时机 | Token 成本 | 示例 |
|------|----------|-----------|------|
| L0 | 每次对话 | 极低（<100） | 使用者名称、角色、偏好 |
| L1 | 每次对话 | 低（<500） | 操作系统、安装工具、活跃项目 |
| L2 | 需要时 | 中（<2000） | 昨天修了什么 bug、最近的技术决策 |
| L3 | 按需搜索 | 按需 | 某框架的踩坑笔记、API 用法 |

---

## 安装

### 快速安装

```bash
# 1. Clone
git clone https://github.com/zycaskevin/Vault-for-LLM.git
cd Vault-for-LLM

# 2. 安装（建议使用虚拟环境）
python3 -m venv ~/.vault-for-llm
source ~/.vault-for-llm/bin/activate
pip install -e .

# 3. 初始化项目
vault init

# 4. 验证
vault doctor
```

### 三种安装模式

**模式一：最小安装** — 仅关键词搜索
```bash
pip install vault-for-llm
vault init
# 仅支持关键词匹配搜索
```

**模式二：语义搜索** — 本地 ONNX 嵌入模型（~150MB，不需 PyTorch/GPU）
```bash
pip install vault-for-llm[semantic]
vault init
vault install-embedding
# 选择：zh（中文）、en（英文）、mix（混合，推荐）
# 支持向量相似度搜索（推荐）
```

**模式三：Ollama** — 已有 Ollama 则零额外安装
```bash
pip install vault-for-llm
vault init
vault config set embedding.provider ollama
vault config set embedding.model nomic-embed-text
# 使用你现有的 Ollama 安装
```

### 环境检查

```bash
vault doctor
```

预期输出：
```
Python               3.11.x ✅
sqlite-vec           ✅ 0.1.9
onnxruntime          ✅ 1.24.x  （未安装则显示 ❌）
optimum[onnxruntime] ✅         （未安装则显示 ❌）
Ollama               ✅/❌
嵌入模型缓存           ✅/❌
```

---

## 初始设置

### 步骤一：填写你的身份（L0）

复制模板并编辑 — 这是关于你（使用者），不是关于 AI：
```bash
cp templates/L0-identity/identity.md L0-identity/identity.md
# 编辑 L0-identity/identity.md，填入你的个人信息
```

### 步骤二：填写核心事实（L1）

```bash
cp templates/L1-core-facts/current-projects.md L1-core-facts/current-projects.md
# 编辑填入你当前的项目和环境
```

### 步骤三：新增第一条知识条目（L3）

在 `raw/` 目录建立 `.md` 文件：

```markdown
---
title: "我的第一条知识"
category: "technique"
layer: L3
tags: ["tag1", "tag2"]
trust: 0.8
source: "real-experience"
created: "2026-04-17"
---

# 我的第一条知识

你学到了什么、踩了什么坑、什么方法有效。
```

### 步骤四：编译

```bash
vault compile
```

这会：
- 将 `raw/` 条目编译到 `compiled/`（AAAK 6 倍压缩）
- 建立搜索索引
- 自动 git commit（方便回滚）
- 执行 lint 健康检查

---

## 目录结构

```
你的项目/
├── L0-identity/             ← 用户身份（每次对话注入）
│   └── identity.md
├── L1-core-facts/           ← 核心事实（每次对话注入）
│   └── current-projects.md
├── L2-context/              ← 动态情境（每日自动更新）
│   └── recent-sessions/
│       └── current.md
├── L3-knowledge/            ← 深度知识（按需搜索）
├── raw/                     ← 原始知识输入（你的 .md 文件放这里）
├── compiled/                ← AAAK 压缩备份（自动生成）
├── guardrails.db            ← SQLite 数据库（vault compile 自动生成）
└── templates/               ← L0/L1/L2 干净模板
```

---

## AI 整合指南

### 通用 LLM Agent

1. 阅读 `L0-identity/identity.md` 了解使用者
2. 阅读 `L1-core-facts/current-projects.md` 了解现状
3. 使用 `vault search "查询"` 进行语义搜索

### Claude Code / Cursor / 任何 AI IDE

1. 将 `CLAUDE.md` 复制到项目根目录
2. 深度知识搜索：使用 `rg "关键字" raw/ compiled/`
3. 或使用 `vault search "查询"`

---

## CLI 命令参考

| 命令 | 说明 |
|------|------|
| `vault init` | 初始化新项目 |
| `vault doctor` | 环境健康诊断 |
| `vault add "标题" --content "内容"` | 新增知识条目 |
| `vault add "标题" --file 文件.md` | 从文件导入 |
| `vault import 长文.md` | 导入长文档（自动分块） |
| `vault compile` | 编译 raw/ → 数据库 + compiled/ |
| `vault search "查询"` | 搜索（自动：关键词 + 语义） |
| `vault search "查询" --graph-expand 1` | 搜索 + 知识图谱扩展 |
| `vault list` | 列出所有条目 |
| `vault stats` | 显示数据库统计 |
| `vault lint` | 执行质量检查 |
| `vault dedup` | 检测语义重复知识 |
| `vault dedup --dry-run` | 预览合并计划（不修改数据） |
| `vault dedup --merge` | 自动合并重复（保留高信任度） |
| `vault graph build` | 构建知识图谱 |
| `vault graph show` | 显示图谱摘要 |
| `vault graph export --format mermaid` | 导出 Mermaid 图谱 |
| `vault graph expand <id>` | 从指定节点展开图谱 |
| `vault config set <key> <value>` | 设置配置（如嵌入后端） |

---

## MCP Server（Claude Code / Cursor / OpenClaw）

让 AI Agent 直接通过 MCP 协议操作知识库：

```bash
# 安装 MCP 依赖
pip install "vault-for-llm[mcp]"

# 启动（在含有 guardrails.db 的项目目录运行）
vault-mcp

# 或指定路径
vault-mcp --project-dir /path/to/your/project
```

加入 Claude Code 配置（`~/.claude/claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "vault": {
      "command": "vault-mcp",
      "args": ["--project-dir", "/path/to/your/project"]
    }
  }
}
```

可用工具：`vault_search`、`vault_add`、`vault_get`、`vault_list`、`vault_stats`

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
vault compile
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

## 常见问题

**Q：我需要使用全部四层吗？**
A：L0+L1 是必要的（AI 需要知道你是谁）。L2+L3 是可选的，但强烈建议使用。

**Q：Token 成本？**
A：L0+L1 每次对话注入约 500-800 tokens。L3 使用 AAAK 压缩 — 仅需原始 token 成本的 1/6。

**Q：信任评分？**
A：用户自定义 = 1.0、已验证 = 0.9、文档来源 = 0.7、未验证 = 0.5。知识冲突时，AI 优先信任较高分数。

---

## 疑难排解

### sqlite-vec 找不到
```bash
pip install sqlite-vec
# 如果失败，可能需要从源码编译
pip install sqlite-vec --no-binary :all:
```

### ONNX 模型下载失败
```bash
# 手动下载
python3 -c "
from vault.guardrails_embed import ONNXEmbeddingProvider
e = ONNXEmbeddingProvider(model_key='mix')
e._ensure_model()
"
```

### Ollama 无法连接
```bash
# 检查 Ollama 是否运行中
curl http://localhost:11434/api/tags
# 确认已安装嵌入模型
ollama pull nomic-embed-text
```

---

## 授权

MIT License — 详见 [LICENSE](LICENSE)。

---

*为开发者打造 — 让你的 AI Agent 真正记住事情。*
