# Vault-for-LLM 简体中文说明

**[English](README.md) | [繁體中文](README.zh-Hant.md) | 简体中文**

> 给 LLM Agent 用的本地优先记忆层。
>
> Vault-for-LLM 会在你的项目里创建一个可移植的 SQLite 知识库。你可以用 Markdown 写笔记，把它们编译成可搜索、可引用的结构化记忆，并通过 `vault` CLI 或 `vault-mcp` 让 AI Agent 在对话中查询。

---

## 为什么需要它？

LLM Agent 很强，但大多数 Agent 每次开新 session 就会忘记上下文：决策、踩坑、用户偏好、项目设置、调试过程都要重新教一次。

Vault-for-LLM 解决的是这件事：

1. 你把重要知识写成 Markdown。
2. `vault compile` 把它编译进本地 SQLite。
3. Agent 需要时再搜索，不用把所有内容塞进 prompt。
4. 支持 MCP 的 Agent 可以在对话中直接查知识库。

它不是要取代你的笔记软件，而是让你的笔记**可以被 Agent 使用**。

---

## 它和一般知识库有什么不同？

Vault-for-LLM 不只是另一个向量数据库。它正在往 **Agent 记忆质量控制层** 演进：

- Agent 需要时，能不能找到正确记忆？
- 能不能只读相关段落，而不是把整篇文档塞进上下文？
- 能不能判断一条知识是否完整、过期、重复，或缺少操作细节？
- 团队能不能在修改 retrieval 逻辑前后，量化搜索质量有没有退步？
- 可重复使用的 Agent workflow，能不能变成技能共享，而不是每个项目重新摸索？

换句话说：一般 RAG 重点是“把资料找出来”；Vault-for-LLM 更关心的是“这些记忆能不能被 Agent 正确使用”。

---

## 核心原则

- **本地优先**：SQLite 是 source of truth；核心功能不需要云端。
- **不用 embedding 也能跑**：先有关键词搜索；语义搜索是可选功能。
- **为 Agent 记忆设计**：把每次都要加载的事实，和需要时才搜索的深知识分开。
- **定界读取**：Document Map 让 Agent 读正确段落，而不是整篇文件塞进上下文。
- **可选同步**：Supabase 是可选的同步/远端读取目标，不是必要基础设施。
- **Alpha、CLI 优先**：目前是开发者工具，API 与体验仍在演进。

---

## 0.4.3 新增内容

0.4.3 补上 **repo hygiene 与公开边界检查工具**，适合同一套功能同时服务私人工作流与开源发布流程的团队：

- `scripts/public_pr_gate.py` 会扫描实际 PR diff，对私人文件、runtime 数据、本机路径、疑似 secret assignment、rename path、deleted line、过大的非预期 diff 采用 fail-closed。
- `scripts/artifact_audit.py` 只读取并报告 generated cache、需人工复核的 runtime folder、可归档候选，不会删文件。
- `scripts/artifact_cleanup.py` 默认 dry-run；只有明确加上 `--execute --safe-only` 时，才删除可重建的 cache artifacts。
- `docs/repo_governance.md` 说明公开/内部 release 边界与 whitelist staging 流程。

这些是 source checkout 内的治理辅助工具，不会改变核心 `vault` CLI 记忆工作流。

---

## 它能做什么？

| 领域 | 能力 |
|---|---|
| 知识存储 | 将 `raw/` Markdown 编译进本地 SQLite |
| 搜索 | 关键词搜索、可选向量搜索、混合搜索 |
| Embedding | 可选 ONNX Runtime 或 Ollama |
| 记忆分层 | L0 身份、L1 核心事实、L2 近期上下文、L3 深知识 |
| 知识图谱 | 自动推断实体/关系，支持图谱扩展 |
| Document Map | 章节/主张导航，支持有行号范围的 citation |
| MCP | `vault-mcp` 将 search/add/stats/map/read 工具暴露给兼容 Agent |
| 质量工具 | lint、freshness、convergence、cross-validation、dedup、Search QA snapshot |
| Repo 治理 | source checkout 内的公开边界 gate、artifact audit、safe-only cleanup helper |
| 可选远端同步 | Supabase sync scripts，适合团队或远端读取 |
| 本机技能登记库 | 实验中的 `vault skill` 命令，用于在本地 Vault 内共享可复用 workflow；不是托管市场 |

---

## 质量工具发展方向

这些功能目前已经存在，但仍属 alpha，应该把它们视为质量保证工具，而不是完整托管平台：

| 工具 | 用途 | 成熟度 |
|---|---|---|
| Document Map | 导航章节/主张，并用 citation 读取定界原文范围 | 可用，仍在演进 |
| Search QA | 跑固定查询集，比较 retrieval 修改前后的指标 | 可用于 deterministic regression checks |
| 收敛检查 | 判断知识是否具备定义、操作流程、边界案例 | 实验性 |
| 交叉验证 | 用不同模型家族验证抽取出的 claims | 实验性 / 依赖可选模型 |
| Freshness + dedup | 标记过期知识、检测重复条目 | 实验性 |
| 本机技能登记库 | 在本地 SQLite 中 push/search/pull 可重复使用的 Agent workflows | 实验性 / 仅本地 |
| Repo hygiene scripts | 审计 generated artifacts、清理安全 cache、发布前扫描 public PR diff | source-checkout helper |

目前最稳定的路径仍是核心流程：`vault init` → `vault add` → `vault compile` → `vault search` → `vault-mcp`。

---

## 架构

```text
L0 Identity        → 用户/项目是谁；每次 session 加载
L1 Core Facts      → 稳定环境与项目事实；每次 session 加载
L2 Recent Context  → 近期决策、事故、工作上下文
L3 Deep Knowledge  → 经验、API、架构、踩坑；需要时搜索

Markdown raw/  →  vault compile  →  SQLite database  →  vault search / MCP tools
```

这样可以让 Agent 的 prompt 保持小，但需要时仍能查到深层记忆。

---

## 安装

### 从 PyPI 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install vault-for-llm

vault doctor
```

### 可选：语义搜索

基础安装已支持关键词搜索。如果要使用本地 ONNX embedding：

```bash
pip install "vault-for-llm[semantic]"
vault install-embedding --model mix
```

或使用已有 Ollama embedding model：

```bash
vault config set embedding.provider ollama
vault config set embedding.model nomic-embed-text
```

### 可选：MCP server

```bash
pip install "vault-for-llm[mcp]"
vault-mcp --project-dir /path/to/your/project
```

### 开发者：从源码安装

```bash
git clone https://github.com/zycaskevin/Vault-for-LLM.git
cd Vault-for-LLM
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## 快速开始

```bash
# 1. 在项目里创建 vault
vault init

# 2. 新增第一条知识
vault add "First lesson" --content "The bug was caused by X. The fix was Y."

# 3. 编译 Markdown 进本地 SQLite vault
vault compile

# 4. 之后搜索
vault search "what caused the bug"
```

你也可以直接把 Markdown 文件放到 `raw/`，再执行 `vault compile`。

示例：

```markdown
---
title: "Postgres migration pitfall"
category: "error"
layer: L3
tags: ["postgres", "migration"]
trust: 0.8
source: "project-notes"
created: "2026-05-16"
---

# Postgres migration pitfall

记录坏在哪里、为什么坏、下次怎么避免。
```

---

## 目录结构

```text
your-project/
├── L0-identity/              # 用户或项目身份，每次 session 加载
│   └── identity.md
├── L1-core-facts/            # 稳定事实，每次 session 加载
│   └── current-projects.md
├── L2-context/               # 近期上下文、决策、事故
│   └── recent-sessions/
├── L3-knowledge/             # 可搜索的深知识
├── raw/                      # 原始 Markdown 知识条目
├── compiled/                 # 编译/压缩后的知识 artifact
├── vault.db             # vault 生成的本地 SQLite database
└── templates/                # 起始模板
```

## CLI 命令参考

| 命令 | 用途 |
|---|---|
| `vault init` | 初始化项目 vault |
| `vault doctor` | 检查本地环境与可选依赖 |
| `vault add "Title" --content "..."` | 新增知识条目 |
| `vault add "Title" --file note.md` | 从 Markdown 文件新增条目 |
| `vault import long-doc.md` | 导入并分块长文档 |
| `vault compile` | 编译 `raw/` 到 SQLite + `compiled/` |
| `vault search "query"` | 搜索知识库 |
| `vault search "query" --graph-expand 2` | 搜索并加上图谱扩展 |
| `vault export obsidian --vault /path/to/ObsidianVault --dry-run` | 导出单向只读 Markdown notes，方便用 Obsidian 浏览 |
| `vault list` | 列出知识条目 |
| `vault stats` | 显示 vault 统计 |
| `vault lint` | 执行质量检查 |
| `vault map build` | 创建/回填 Document Map |
| `vault map show <id>` | 显示条目的章节地图 |
| `vault map read <id> --lines 10-30` | 读取定界行号范围 |
| `vault graph build` | 创建推断知识图谱 |
| `vault graph show` | 显示图谱统计 |
| `vault converge` | 实验性自问收敛检查 |
| `vault cross-validate` | 实验性跨模型验证 |
| `vault freshness` | 实验性新鲜度/复习排程 |
| `vault dedup` | 检测或合并重复条目 |
| `vault search-qa run` | 执行 Search QA metrics snapshot |
| `vault skill search "query"` | 搜索本机实验性技能登记库条目 |

执行 `vault <command> --help` 可查看各命令参数。

### Obsidian 导出

如果想让人类用 Obsidian 浏览已编译的 vault，又不想改动知识库 source of truth，可以使用：

```bash
vault export obsidian \
  --vault /path/to/ObsidianVault \
  --category technique \
  --dry-run
```

这个导出是刻意设计成单向、只读：只从 `vault.db` 读取，将 Markdown notes 写到 `00-Vault-Knowledge/`，包含 YAML frontmatter 与 `Vault #<id>` citation；不写回 `raw/`、`compiled/`、SQLite，也不触发任何 remote sync。重跑会覆盖同一组稳定路径，不会产生重复笔记。

---

## MCP 集成

安装 MCP extras 并启动 server：

```bash
pip install "vault-for-llm[mcp]"
vault-mcp --project-dir /path/to/your/project
```

MCP server 配置示例：

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

当前 MCP tools 包含：

- `vault_search`
- `vault_add`
- `vault_stats`
- `vault_map_show`
- `vault_read_range`
- 若设置了可选 Supabase sync，还有 `vault_remote_map_show` / `vault_remote_read_range`

---

## 可选 Supabase sync

Vault-for-LLM 的核心用法是本地-only。Supabase 支持是给需要团队同步或远端读取的人使用。

本地 SQLite database 仍是 source of truth；Supabase 是可选的同步/远端读取目标。远端表名默认使用 Vault 品牌命名；接入既有私有 schema 时，可用 `VAULT_SUPABASE_*_TABLE` 环境变量覆盖。

```bash
# alpha 阶段请手动安装
pip install supabase

# 设置 Supabase credentials 后，按需执行 sync script
python scripts/sync_to_supabase.py --document-map
```

---

## 当前成熟度

Vault-for-LLM 仍是 alpha：

- 内部 package、module、database 与 MCP tool 名称已统一为 Vault 品牌。
- convergence、cross-validation、Search QA、skills、Supabase sync 等进阶功能仍在演进。
- 默认安装方式已可使用 PyPI；从源码安装主要给开发者使用。
- 稳定版前，API 与 schema 可能变动。

如果你想走最稳路线，先从这四个命令开始：

```bash
vault init
vault add
vault compile
vault search
```

---

## 开发

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
```

部分测试路径会需要 ONNX、MCP 或 Supabase 等可选依赖。

---

## 授权

MIT
