# Vault-for-LLM 简体中文说明

**[English](README.md) | [繁體中文](README.zh-Hant.md) | 简体中文**

> 给 LLM Agent 用的本地优先、以生产实践为目标的记忆工作流。
>
> Vault-for-LLM 会把 Markdown 项目知识转成可移植的 SQLite 记忆库，让 Agent 需要时再搜索。它处理的是让 Agent 记忆能长期运作的无聊但重要部分：搜索 QA、定界读取、语义搜索、schema migration，以及可验证的 backup/restore。

---

## 为什么需要它？

LLM Agent 很强，但大多数 Agent 每次开新 session 就会忘记真正重要的上下文：决策、踩坑、用户偏好、项目设置、调试过程都要重新教一次。

Vault-for-LLM 解决的是这件事：

1. 你把重要知识写成 Markdown。
2. `vault compile` 把它编译进本地 SQLite。
3. Agent 需要时再搜索，不用把所有内容塞进 prompt。
4. 支持 MCP 的 Agent 可以在对话中直接查知识库。

它不是要取代你的笔记软件，也不是另一个托管向量数据库。它的目标是让你的项目知识**可以被 Agent 使用、被量测、也能被备份还原**。

---

## 它和一般知识库有什么不同？

Vault-for-LLM 不只是另一个向量数据库。它正在往 **Agent 记忆质量控制层** 演进：

- Agent 需要时，能不能找到正确记忆？
- 能不能只读相关段落，而不是把整篇文档塞进上下文？
- 能不能判断一条知识是否完整、过期、重复，或缺少操作细节？
- 团队能不能在修改 retrieval 逻辑前后，量化搜索质量有没有退步？
- 可重复使用的 Agent workflow，能不能变成技能共享，而不是每个项目重新摸索？

换句话说：一般 RAG 重点是“把资料找出来”；Vault-for-LLM 更关心的是“这些记忆能不能被 Agent 正确使用”。

如果想看它和 Mem0、Letta/MemGPT、Zep、LangGraph memory 的定位差异，请看 [memory system comparison](docs/memory_system_comparison.md)。白话版：Vault-for-LLM 偏向本地、可审查、候选制的项目记忆，重视 retrieval QA 与定界引用；如果你需要托管式个性化记忆、完整 stateful-agent runtime，或企业级 temporal graph memory，其他系统可能更合适。

---

## 核心原则

- **本地优先**：SQLite 是 source of truth；核心功能不需要云端。
- **不用 embedding 也能跑**：先有关键词搜索；语义搜索是可选功能。
- **为 Agent 记忆设计**：把每次都要加载的事实，和需要时才搜索的深知识分开。
- **定界读取**：Document Map 让 Agent 读正确段落，而不是整篇文件塞进上下文。
- **可选同步**：Supabase 是可选的同步/远端读取目标，不是必要基础设施。
- **CLI 优先**：这是开发者工具；核心本地流程稳定，进阶 QA、语义与同步工作流仍会演进。

---

## 可用在哪些 Agent 系统？

Vault-for-LLM 不是绑死在某一个 Agent runtime 上。它的共通接口很简单：
本地 Markdown + SQLite，通过 CLI 和可选的 stdio MCP 给不同系统使用。

| 系统 | 使用方式 |
|---|---|
| Hermes Agent / Nancy | 设置 `vault-mcp`，让 Agent 使用 search/read/propose tools；用 CLI 跑 dream report、backup、onboarding benchmark。 |
| OpenClaw | 使用 repo 内置的 [`integrations/openclaw/`](integrations/openclaw/) adapter，注册 `vault_search`、`vault_read_range`、`vault_memory_propose`、`vault_stats`；也可走 generic MCP。 |
| n8n | 在 Execute Command node 调用 `vault` CLI，或包装成内部 HTTP service / MCP bridge，放进 workflow 自动化。 |
| Codex | 在 repo/workspace 里直接使用 CLI；若所用 Codex surface 支持本地 MCP，也可接 `vault-mcp`。 |
| OpenCode | 支持 MCP 时走和 Claude Code/Codex 相同的 generic local MCP；也可在 shell-capable session 里调用 CLI。 |
| Claude Code | 把 `vault-mcp` 设成 local stdio MCP server，或在可跑 shell 的 session 中使用 CLI。 |
| 任何 MCP-compatible Agent | 执行 `vault-mcp --project-dir <project>`，按 `vault_search` → `vault_read_range` → 带来源回答的流程使用。 |

更多设置示例请看 [Agent Integrations](docs/agent_integrations.md)，里面包含 OpenClaw adapter、n8n、Codex、Claude Code 与 generic MCP 的接法。

### 给 Agent 的安装契约

很多 Vault-for-LLM 的安装和 repo 修改会由 Agent 代做，不一定是人手动照 README 操作。Agent 在设置 MCP、选择数据库 scope、或写入记忆前，应先读：

- [`AGENTS.md`](AGENTS.md)：给 coding agent 的简短操作守则。
- [`agent_manifest.json`](agent_manifest.json)：机器可读的安装、scope、安全、runtime、验证信息。

人类用户不需要手动照每条命令安装。你可以直接对 Agent 说：

```text
帮这个项目安装 Vault-for-LLM。先读 AGENTS.md 和 agent_manifest.json，
问我要 shared 还是 private vault，问我要开启哪些 optional features，
问我有没有既有 Obsidian vault 要导入，设置 CLI/MCP，需要时做第一次
Obsidian 导入，再问我要不要开启后续自动同步，最后跑 search/read/propose smoke test。
```

Hermes Agent、Codex、OpenCode、Claude Code、OpenClaw 和其他 MCP-capable agent 可以共用同一套安装架构：

```text
选 projectDir -> 选 optional features -> 询问 Obsidian -> 安装 vault -> 设置 CLI/MCP -> 第一次导入/同步确认 -> 验证 search/read/propose
```

各 runtime 的 adapter 应该保持很薄；真正稳定的契约是共同的
`projectDir`、`vault` CLI、`vault-mcp`，以及候选制记忆流程。

Agent 安装时也应该询问要不要开启可选功能，而不是全部默认装上：

| 功能 | 默认 | 安装命令 | 什么时候问 |
|---|---|---|---|
| `core` | 是 | `python -m pip install vault-for-llm` | 永远需要：本地 Markdown、SQLite、keyword search。 |
| `mcp` | MCP-capable agent 建议开 | `python -m pip install "vault-for-llm[mcp]"` | runtime 可以接 local stdio MCP tools。 |
| `obsidian_import` | 否 | core CLI 内置 | 用户已经有 Obsidian vault，想让 Agent 也能查这些笔记。 |
| `semantic` | 否 | `python -m pip install "vault-for-llm[semantic]"` | 用户想要 embedding-backed semantic/hybrid search。 |
| `supabase` | 否 | `python -m pip install "vault-for-llm[supabase]"` | 用户想要 optional remote sync/read path。 |
| `dev` | 否 | `python -m pip install -e ".[dev]"` | source checkout、benchmark、PR 或 release validation。 |

不要偷偷开启 semantic 或 Supabase extras；它们会增加较重的依赖、模型/provider 设置，或远程凭证。

对 Obsidian，Agent 应主动询问 vault 路径，先跑 `--dry-run`，用户确认后做第一次导入，再询问要不要用 cron、LaunchAgent、n8n 或 host agent 排程同一条 `vault import obsidian --compile` 来做后续自动同步。

### 选择 Vault project scope

Vault-for-LLM 绑定的是 `project-dir`，不是某一个 Agent runtime：

```text
一个 project directory = 一个 vault.db
```

如果 Hermes、OpenClaw、Codex、Claude Code、n8n 都指向同一个
`--project-dir`，它们就共用同一份 governed project memory。指向不同文件夹时，就会使用彼此隔离的数据库。

| Scope | 适合情境 | project-dir 示例 |
|---|---|---|
| Shared project vault | 多个可信 Agent 协作同一份已确认的项目知识 | `~/Vaults/my-project` |
| Agent-private vault | 某个 Agent 做实验、比较吵、或不完全可信 | `~/.openclaw/workspace/vault-project` |
| Domain/customer vault | 不同客户或业务数据需要隔离 | `~/Vaults/clinic-customer-service` |
| Temporary vault | Demo、测试、benchmark | `/tmp/vault-benchmark-*` |

共用 vault 时，建议让 Agent 使用 `vault_memory_propose`，不要直接写入正式记忆，避免多 Agent 一起把 active memory 弄乱。

如果 Agent 跑在不同主机上，本地 `project-dir` 就不能直接共用。这时可选的 Supabase sync 可以作为远程共享读取/同步层：每台主机保留自己的本地 SQLite vault，再把已批准的知识、Document Map、摘要、hash 和 metadata 同步到同一个 Supabase project。这样 Hermes 在一台机器、Codex 在另一台、n8n 在服务器上，也能读到共同的 project-memory view；但 Supabase 仍然不是本地核心功能的必要依赖。

---

## 当前源码状态：v0.6.24

当前 source tree 已包含 v0.6.24 的 agent integration、OpenClaw adapter、Obsidian 导入同步、benchmark proof 与质量 gate，并保留候选制记忆 workflow 与搜索增强。白话说，Vault 现在不像一个谁都能乱塞纸条的抽屉，更像一间有前台的小图书馆：

- **候选制记忆**：Agent 想记东西时，先交到前台（`vault remember` / `vault_memory_propose`），由 privacy、duplicate、metadata、quality gates 检查，再决定能不能上架。
- **更安全的召回**：keyword search 有弱匹配门槛，应该找不到的 query 比较不会硬抓一条不相关记忆回来；可用 `--min-score` 调整。
- **Search QA hard negatives**：固定题库可以写 `expected_no_results: true`，同时检查“该找到的有没有找到”和“不该找到时有没有乱认亲”。
- **CI Search QA gate**：release readiness CI 会跑公开 fixture，检查 top-k、MRR、no-result precision、citation-policy 与 mode gate。
- **Dream 先出报告再整理**：`vault dream` 先写 report / plan；`apply_safe` 只做很小的 metadata 修正，并保留 backup/rollback 路径。
- **有 guardrail 的语义工作流**：可选 semantic vectors、provider validation、persistent embedding cache，以及 CI/本机用 deterministic hash smoke tests。
- **明确的 DB schema status/migration**：用 [`vault db status/migrate`](docs/db_migrations.md) 检查并执行 idempotent SQLite migrations。
- **本地 SQLite backup/verify/restore**：用 [`vault db backup/verify-backup/restore`](docs/db_backup_restore.md) 创建、验证、还原备份；restore 前会拒绝非 Vault 或格式损坏的 DB。
- **Release gates**：README command smoke、wheel smoke、version parity、secret scan、full-history privacy scan、artifact audit、public-boundary checks。

语义搜索是**刻意设计成可选功能**：基础安装只靠关键词搜索也能跑。配置真 embedding provider 后，可用 [`vault semantic ...`](docs/semantic_search.md) 重建 vectors、预热 cache、跑 smoke checks。Deterministic hash embeddings 必须明确加 `--allow-hash`，只供 CI/本地测试使用。

0.4.3 的 repo hygiene 工具请看 [`scripts/README.md`](scripts/README.md) 与 [`docs/repo_governance.md`](docs/repo_governance.md)。

---

## 它能做什么？

| 领域 | 能力 |
|---|---|
| 知识存储 | 将 `raw/` Markdown 编译进本地 SQLite |
| 搜索 | FTS5/BM25 关键词搜索与 fallback、可选向量搜索、混合搜索 |
| Embedding | 可选 ONNX Runtime 或 Ollama、provider guard、durable cache workflow |
| 记忆分层 | L0 身份、L1 核心事实、L2 近期上下文、L3 深知识 |
| 知识图谱 | 自动推断实体/关系，支持图谱扩展 |
| Document Map | 章节/主张导航，支持有行号范围的 citation |
| MCP | `vault-mcp` 将 search/add/stats/map/read 与候选制记忆工具暴露给兼容 Agent（[MCP 记忆流程](docs/mcp_memory_workflow.md)） |
| 记忆整理器 | `vault remember`、`vault promote`、MCP propose/promote 工具，让 autonomous memory write 先经过 gate |
| Dream 报告 | `vault dream` 产生 report-first 记忆整理摘要，找出过期、重复、不完整或 metadata 弱的知识（[Dream workflow](docs/dream_workflow.md)） |
| 质量工具 | lint、freshness、convergence、cross-validation、dedup、Search QA snapshot、semantic smoke/warm workflow |
| Repo 治理 | source checkout 内的公开边界 gate、artifact audit、safe-only cleanup helper |
| Agent 集成 | Hermes Agent、OpenClaw、n8n、Codex、Claude Code 与 generic MCP-compatible agents 的 CLI/MCP 使用方式（[集成指南](docs/agent_integrations.md)） |
| 可选远端同步 | Supabase sync scripts，适合团队或远端读取 |
| 本机技能登记库 | 实验中的 `vault skill` 命令，用于在本地 Vault 内共享可复用 workflow；不是托管市场 |

---

## 质量工具发展方向

这些功能目前已经存在，但成熟度不同。核心本地命令是最稳定路径；进阶 QA、语义、同步与 skill registry 工作流仍会演进：

| 工具 | 用途 | 成熟度 |
|---|---|---|
| Document Map | 导航章节/主张，并用 citation 读取定界原文范围 | 可用，仍在演进 |
| Search QA | 跑固定查询集，比较 retrieval 修改前后的指标 | 可用于 deterministic regression checks |
| 收敛检查 | 判断知识是否具备定义、操作流程、边界案例 | 实验性 |
| 交叉验证 | 用不同模型家族验证抽取出的 claims | 实验性 / 依赖可选模型 |
| Freshness + dedup | 标记过期知识、检测重复条目 | 实验性 |
| 本机技能登记库 | 在本地 SQLite 中 push/search/pull 可重复使用的 Agent workflows | 实验性 / 仅本地 |
| Repo hygiene scripts | 审计 generated artifacts、清理安全 cache、发布前扫描 public PR diff | source-checkout helper |

目前最稳定的路径仍是核心流程：`vault init` → `vault add`/`vault remember` → `vault compile`/`vault promote` → `vault search` → `vault-mcp`。Autonomous agent 建议使用 `vault_memory_propose`，不要直接用 `vault_add` 写入未审核记忆。

可以把 direct `vault_add` 想成让人直接走进仓库把纸条塞上架；它仍留给可信脚本使用，但日常 Agent 记忆应该先走候选前台：先提案、检查 gates、再 promote。

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

### Agent 记忆生命周期

```text
对话 / 任务
  → 提出候选记忆
  → privacy + duplicate + metadata + quality gates
  → promote 已审核记忆
  → raw Markdown + SQLite active knowledge
  → search / map / read_range 召回
  → dream report 做整理与安全 metadata 修正
```

用故事讲：Agent 先写一张纸条，前台检查它安不安全、有没有重复、值不值得留下；通过后图书馆员才把它上架。之后 Agent 要用时，不是把整间图书馆搬进 prompt，而是查目录、找到书架、只读需要的段落。

---

## 安装

### 从 PyPI 安装

> 发布备注：GitHub source tree 目前是 `0.6.24`。如果 PyPI 落后最新 GitHub release，请先使用下方 source install 获取最新 source features。

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
vault-mcp --project-dir /path/to/your/project --tool-profile core
```

安全提醒：`vault-mcp` 是本机 stdio MCP server，没有内置网络认证或用户层级访问控制。只把它配置给你信任、且可以读写该 `--project-dir` 的 Agent；若要给共享或实验性 Agent 使用，建议使用独立 project directory。

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

### 候选制 Agent 记忆

Autonomous agent 或未审核记忆，建议走候选流程。这是 PR27 后的推荐路径：

```bash
vault remember "Memory title" \
  --content "Markdown memory content" \
  --reason "Why this is worth remembering"

# 审核后
vault promote mem_xxxxxxxxxxxx --confirm
```

MCP agent 应使用 `vault_memory_propose` 和 `vault_memory_promote`；详见 [MCP 记忆流程](docs/mcp_memory_workflow.md)。

| Gate | 白话工作 |
|---|---|
| Privacy | “这是不是像密钥或私人资料？” |
| Duplicate | “我们是不是已经有这条或很像的记忆？” |
| Metadata | “至少有标题、内容、原因吗？” |
| Quality | “这条记忆之后找得到、用得上吗？” |

### Search QA：检查记忆召回健不健康

Search QA 像是给 vault 的小考。有些题目应该找到指定记忆，有些 hard-negative 题目应该什么都找不到。这样能同时抓两种错：该记得却忘了，以及不该回却乱回。

```bash
vault search-qa run \
  --qa-file benchmarks/search_qa/basic.zh-Hant.json \
  --mode keyword \
  --min-score 0.34 \
  --output /tmp/searchqa.json
```

Fixture 可用 `expected_no_results: true` 表示“这题正确答案是不要回任何结果”。详见 [Search QA benchmarking guide](docs/search_qa_benchmarking.md)。

### Dream 记忆整理报告

```bash
vault dream --mode report --limit 50 --write-report
```

报告会写到 `reports/dream/`。`apply_safe` 只会做很窄的 metadata 修正，并输出 plan 与 backup path；如果整理结果不符合预期，可以 rollback。详见 [dream workflow](docs/dream_workflow.md)。

### 可选：语义工作流

语义搜索是刻意设计成可选功能。基础安装只靠关键词搜索也能跑。配置真 embedding provider 后，主要操作命令是：

```bash
vault semantic rebuild --persist-cache
vault search "what caused the bug" --mode semantic
vault search "what caused the bug" --mode hybrid
vault semantic smoke --qa-file benchmarks/search_qa/basic.en.json --mode semantic --pretty
vault semantic cache-stats --pretty
```

`vault search --mode semantic` 会直接读取已存储的 `semantic_vectors`；`--mode hybrid` 会在可用时融合关键词与 stored semantic index，不可用时安全 fallback。

Search QA 也可以跑 semantic/hybrid snapshot，但 QA 命令必须使用和 `vault semantic rebuild` 相同的 provider/model/dimension 与 vector kind。若使用 deterministic hash provider 做本地 smoke test，请在 rebuild 和 `vault search-qa run` 都传入相同的 `--allow-hash --hash-dim N`；hash vectors 只验证流程与 JSON 形状，不代表真实语义搜索质量。

完整 lifecycle（`warm`、`cache-prune`、`startup`、`daemon`、以及只供测试用的 `--allow-hash`）请看 [`docs/semantic_search.md`](docs/semantic_search.md)。

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
| `vault setup-agent` | 启动交互式 Agent 安装精灵，并可生成 Obsidian 自动同步模板 |
| `vault doctor` | 检查本地环境与可选依赖 |
| `vault add "Title" --content "..."` | 新增知识条目 |
| `vault add "Title" --file note.md` | 从 Markdown 文件新增条目 |
| `vault import long-doc.md` | 导入并分块长文档 |
| `vault import obsidian --vault /path/to/ObsidianVault --dry-run` | 预览把既有 Obsidian notes 导入 `raw/obsidian/` |
| `vault compile` | 编译 `raw/` 到 SQLite + `compiled/` |
| `vault search "query"` | 搜索知识库；可用 `--min-score` 调整弱匹配抑制 |
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
| `vault search-qa run` | 执行 Search QA snapshot、hard-negative 检查与召回指标 |
| `vault semantic rebuild` | 配置真 embedding provider 后重建 semantic vector rows |
| `vault semantic warm` | 预先计算 QA query embeddings，不写入 vector rows |
| `vault semantic smoke` | 一次执行 rebuild、warm 与 Search QA smoke snapshot |
| `vault semantic cache-stats` / `vault semantic cache-prune` | 检查或清理 durable embedding cache |
| `vault semantic startup` / `vault semantic daemon` | 执行 importable startup 或 bounded daemon lifecycle hooks |
| `vault skill search "query"` | 搜索本机实验性技能登记库条目 |

执行 `vault <command> --help` 可查看各命令参数。

### Agent 安装精灵

使用 `vault setup-agent` 或别名 `vault install-agent`，可以让 Agent 依序询问数据库 scope、optional features、既有 Obsidian vault 路径、是否做第一次导入，以及是否生成 cron、LaunchAgent 或 n8n 自动同步模板。

```bash
vault setup-agent

vault setup-agent \
  --non-interactive \
  --agent hermes \
  --scope shared \
  --agent-project-dir ~/Vaults/my-project \
  --features core,mcp,obsidian_import \
  --obsidian-vault ~/Documents/ObsidianVault \
  --import-obsidian \
  --obsidian-sync all
```

### Obsidian 导出

如果想让人类用 Obsidian 浏览已编译的 vault，又不想改动知识库 source of truth，可以使用：

```bash
vault export obsidian \
  --vault /path/to/ObsidianVault \
  --category technique \
  --dry-run
```

这个导出是刻意设计成单向、只读：只从 `vault.db` 读取，将 Markdown notes 写到 `00-Vault-Knowledge/`，包含 YAML frontmatter 与 `Vault #<id>` citation；不写回 `raw/`、`compiled/`、SQLite，也不触发任何 remote sync。重跑会覆盖同一组稳定路径，不会产生重复笔记。

### Obsidian 导入与同步

如果用户已经有很多 Obsidian 笔记，Agent 可以把这些 Markdown notes 反向导入 Vault：

```bash
vault import obsidian \
  --vault /path/to/ObsidianVault \
  --dry-run

vault import obsidian \
  --vault /path/to/ObsidianVault \
  --compile
```

导入流程会把用户自己写的 notes 复制到 `raw/obsidian/`，在 frontmatter 保留原始 Obsidian 路径与 content hash，并默认跳过 `.obsidian/`、`.trash/`、`.git/` 和 `00-Vault-Knowledge/`。这样 Vault 自己导出的浏览用笔记，不会又被吃回来当成 source。

第一次接上既有 Obsidian vault 时，建议先跑 `--dry-run`。重跑是 idempotent：没变的 note 会跳过，有变的 note 会更新同一个 raw path；只有加上 `--compile` 才会把导入内容写进 `vault.db`。如果要自动同步，可以用 cron、LaunchAgent、n8n 或 Agent installer 定期执行同一条命令；第一版不需要常驻 watcher。

---

## MCP 集成

安装 MCP extras 并启动 server：

```bash
pip install "vault-for-llm[mcp]"
vault-mcp --project-dir /path/to/your/project --tool-profile core
```

安全提醒：`vault-mcp` 是本机 stdio MCP server，没有内置网络认证或用户层级访问控制。只把它配置给你信任、且可以读写该 `--project-dir` 的 Agent；若要给共享或实验性 Agent 使用，建议使用独立 project directory。

MCP server 配置示例：

```json
{
  "mcpServers": {
    "vault": {
      "command": "vault-mcp",
      "args": ["--project-dir", "/path/to/your/project", "--tool-profile", "core"]
    }
  }
}
```

MCP 可以用 tool profiles 控制暴露给 Agent 的工具数量：

| Profile | 适合情境 |
|---|---|
| `core` | 日常 Agent 使用，只暴露 `vault_search`、`vault_read_range`、`vault_memory_propose`、`vault_stats` |
| `review` | 需要审核并 promote 候选记忆 |
| `remote` | 需要读取 Supabase 同步的跨主机记忆视图 |
| `maintenance` | 排程或人工整理 freshness/convergence |
| `full` | 完整兼容模式，包含 `vault_add` 等进阶/旧工具 |

`full` 仍是默认值以维持兼容；正式 Agent session 建议使用 `--tool-profile core` 以减少 tool schema token。

---

## 可选 Supabase sync

Vault-for-LLM 的核心用法是本地-only。Supabase 支持是给需要团队同步或远端读取的人使用。

本地 SQLite database 仍是 source of truth；Supabase 是可选的同步/远端读取目标。远端表名默认使用 Vault 品牌命名；接入既有私有 schema 时，可用 `VAULT_SUPABASE_*_TABLE` 环境变量覆盖。

这对“不同主机上的 Agent 要共享记忆”特别有用。例如 Hermes Agent 在工作站、Codex 在笔记本、OpenClaw 在另一台机器、n8n 在服务器上，都可以各自保留 local Vault，同时把已确认的记忆同步到同一个 Supabase project，形成跨主机可读的共同记忆视图。

知识与技能同步采用最小披露默认值：metadata、summary、hash、Document Map rows 与 claims 会同步，但不包含完整 `content_raw`。只有明确加上 `--include-content` 时才会同步全文；若 privacy scan 判定为 fail，仍不会上传全文。

```bash
# 可选整合依赖
pip install supabase

# 设置 Supabase credentials 后，按需执行 sync script
python scripts/sync_to_supabase.py --document-map
```

---

## 当前成熟度

Vault-for-LLM 是 CLI 优先的开发者工具：

- 核心本地命令（`init`、`add`、`compile`、`search`）是最稳定路径。
- Search QA、FTS5/BM25 关键词搜索、Document Map citation reads、语义 workflow 命令已可用，但仍会演进。
- Supabase sync、MCP、本机 skill registry 等可选整合在 1.0 前仍可能调整。
- 默认安装方式已可使用 PyPI；从源码安装主要给开发者使用。

如果你想走最稳路线，先从这四个命令开始：

```bash
vault init
vault add
vault compile
vault search
```

---

## 检索质量（Search QA 基准测试）

### 证据摘要

Vault-for-LLM 测量的是 retrieval 与项目记忆 QA 层，不只是笔记数据库。这些数字是证据探针，不是任何数据量都保证相同；换成更大或不同语料时，应该用 repo 内置 benchmark 重新测。

| Probe | 结果 | 注意事项 |
|---|---:|---|
| Repo onboarding fixture | Vault top-k/source/read-range guidance `28/28`；Codex transcript baseline `7/28`；Hermes/Nancy transcript baseline `3/28` | 28 题 source-aware project benchmark；private transcripts 不提交进 repo |
| Candidate-first memory | promotion 前 active-memory pollution 为 `0` | candidate proposals 不会自动进正式记忆 |
| LoCoMo hierarchical retrieval probe | official-scored categories 上 Any evidence@50 `97.7%`、All evidence@50 `90.5%` | 只代表 retrieval evidence score；不是官方 answer/judge leaderboard score |

可重跑的 repo fixture 与 exported-session 对照流程请看 [Agent Onboarding Benchmark](docs/agent_onboarding_benchmark.md)。

### Search QA fixture

Vault-for-LLM 提供确定性的 Search QA 基准测试，用于在代码变动前后测量检索质量。以下结果使用英文 fixtures（`benchmarks/search_qa/basic.en.json`），对照全新编译的数据库（keyword/FTS5 模式）：

| 指标 | 数值 |
|---|---|
| total_cases | 3 |
| top-1 recall | 2/3 ≈ **67%** |
| top-k recall | 2/3 ≈ **67%** |
| no-result precision | 1.0 |
| Mean Reciprocal Rank | 0.67 |

基准测试涵盖：
- `en_document_map_read_range` — "tool-gated reading map navigation read_range evidence" → 期望 "Tool-gated Reading"
- `en_citation_policy_boundary` — "citation policy boundary final answer support" → 期望 "Citation Policy Boundary"
- `en_no_result_control` — 随机字符串查询 → 期望无结果（假阳性检查）

简体中文版 fixture（`basic.zh-CN.json`）也存在，但因使用相同合成知识，指标相同。

在本地执行：

```bash
python -m pytest tests/test_search_quality_metrics.py -v
```

语义/混合模式需要 embedding 模型（CI smoke 用 `--allow-hash`）。
语义模式结果可能不同 — keyword search 是稳定的基准。

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

Apache-2.0
