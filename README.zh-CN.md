# Vault-for-LLM

给 AI Agent 使用的本地优先项目记忆层。

Vault-for-LLM 会把项目笔记、决策、错误修复、SOP、Obsidian 笔记，以及
Agent 提出的候选记忆，整理成一个可携带的 SQLite vault。Agent 可以搜索、
按范围阅读、引用来源、测试召回、备份，必要时也能同步到 Supabase 让不同主机读取。

它不是要取代模型、wiki、Obsidian 或 hosted memory system。它更像中间那一层：
让 Agent 使用项目知识时，不只是“记得”，而是记得有来源、有边界、可审查，也能回滚。

默认路径是让 Agent 代为安装：先问数据库要放哪里、要 shared 还是 private，
再跑一个 search/read/propose smoke test。手动命令仍然保留，但不是新手的主路径。

## 为什么需要它

很多 Agent 问题不是模型不够聪明，而是工作记忆太混乱：

- 新 session 又像第一天上班
- 旧文件和新决策混在一起
- 修过的 bug 留在聊天记录里，下一次又重踩
- 私人观察被误放进共享项目记忆
- 团队不知道搜索到底有没有找对来源

Vault-for-LLM 想解决的是这个问题：

> 这个项目已经学到什么？来源在哪里？这个 Agent 可以使用它吗？

## 你会得到什么

- **本地优先**：核心功能只需要 Markdown 和 SQLite，不必先接云端。
- **Agent 友好**：提供 CLI 和 MCP，支持搜索、bounded read、候选记忆、Document Map。
- **候选制写入**：Agent 先提出记忆，通过检查后才进入正式知识库。
- **治理 metadata**：每条记忆都可以带 scope、sensitivity、owner agent、allowed agents、过期时间。
- **Obsidian 双向工作流**：可导入既有 Obsidian 笔记，也可导出成 Obsidian 可读格式。
- **可选远端共享**：Supabase sync 和 read-only RPC 让不同主机或 hosted agent 读共享记忆。
- **Report-first 自动化**：可生成 cron、LaunchAgent、n8n 模板，定期整理记忆，但不会偷偷删除或提升记忆。
- **可测试召回**：Search QA 和 onboarding benchmark 可以量化 Agent 是否找得到正确来源。

## 什么时候适合用

适合你，如果：

- 你用 Claude Code、Codex、Hermes Agent、OpenClaw、OpenCode、n8n 或其他 Agent 做项目
- 你希望多个 Agent 共用项目知识，但不要互相读到私人原始对话
- 你已经有 Markdown 或 Obsidian 笔记，希望 Agent 能查、能引用
- 你想本地保存记忆，但又需要 Supabase 让其他主机读取安全摘要
- 你在意召回质量，希望能测，而不是只靠感觉

如果你只需要 hosted vector database、普通笔记软件，或完全自动的聊天记忆产品，
Vault-for-LLM 可能不是第一个该拿起来的工具。

## 安装

### 让 Agent 代为安装

最推荐的方式，是直接把这段交给能执行本机命令的 Agent：

```text
帮这个项目安装 Vault-for-LLM。使用 vault-for-llm[mcp]==0.6.60。
先问我要 shared、private、domain-specific 还是 temporary vault。
询问稳定的 project directory，并为长期任务生成 stable venv script。
逐项询问 MCP、semantic search、Supabase、Obsidian import、Headroom 压缩、
memory-agent guidance。只安装我同意的 optional dependencies。
最后跑 search/read/propose smoke test。
```

Agent 会使用安装精灵：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install "vault-for-llm[mcp]==0.6.60"

vault setup-agent
```

非互动安装示例：

```bash
vault setup-agent \
  --non-interactive \
  --agent codex \
  --scope shared \
  --agent-project-dir ~/Vaults/my-project \
  --features core,mcp,supabase,headroom \
  --write-stable-venv-script \
  --supabase-setup simple \
  --remote-reader shell \
  --automation-schedule cron \
  --json
```

这会生成 `agent-install/setup-stable-venv.sh`，让排程、Supabase sync、MCP command
不依赖重启后可能消失的 `/tmp` virtualenv。

### 手动快速开始

```bash
pip install "vault-for-llm[mcp]==0.6.60"

vault init ~/Vaults/demo
vault add "First lesson" \
  --content "The bug was caused by a missing cache key. The fix was adding provider metadata." \
  --project-dir ~/Vaults/demo
vault compile --project-dir ~/Vaults/demo --no-embed
vault search "cache key" --project-dir ~/Vaults/demo
```

## Agent 日常流程

建议 Agent 这样使用记忆：

1. **先搜索**：找可能相关的来源。
2. **再按范围读取**：不要整份文件塞进 context。
3. **回答时引用来源**：citation 要回到 Vault 原文，不要引用压缩摘要。
4. **提出候选记忆**：新的教训先进入候选区。
5. **审核后再提升**：保持正式记忆库干净、可追踪。

MCP-capable runtime 可以启动：

```bash
vault-mcp --project-dir ~/Vaults/my-project --tool-profile core
```

建议先开 core tool profile：

- `vault_search`
- `vault_read_range`
- `vault_memory_propose`
- `vault_stats`

MCP 文件：

- 工具参考：[docs/mcp_tool_reference.md](docs/mcp_tool_reference.md)
- workflow 与 token 预算：[docs/mcp_memory_workflow.md](docs/mcp_memory_workflow.md)

## 记忆分层

Vault 使用 L0-L3 表示记忆深度：

| Layer | 用途 |
|---|---|
| `L0` | 身份、项目定位、不可轻易改动的框架 |
| `L1` | 稳定事实、规则、偏好 |
| `L2` | 近期上下文、摘要、当前工作 |
| `L3` | 详细知识、SOP、bug、决策、来源笔记 |

权限不要只靠 layer 判断，请搭配治理 metadata：

- `scope`: private, project, shared, public
- `sensitivity`: low, medium, high, restricted
- `owner_agent`
- `allowed_agents`
- `memory_type`
- `expires_at`

搜索会记录轻量使用统计（`access_count`、`last_accessed_at`）。短期记忆若设置
`expires_at`，可以到期后移到 `status: archived`，不需要直接删除：

```bash
vault usage stats
vault usage archive-expired --apply
```

设计说明：[docs/memory_governance.md](docs/memory_governance.md)。

Policy-based automation 让 Agent 处理例行整理，但由人保留规则主权：

```bash
vault automation plan --write-policy
vault automation run
vault automation run --apply
vault automation cycle --apply
```

`vault automation cycle` 会先评估已审核的候选结果，写出 bounded
`learning_policy.json`，再跑一次安全自动化，让 Dream 用最新的整理提示排序候选。
它仍然不会自动 promote、硬删记忆，或绕过隐私与权限规则。

拒绝或阻挡候选也可以变成结构化反馈：

```bash
vault candidate-review mem_123 --outcome rejected --reason "太模糊，不值得长期保存。"
```

这让 Agent 知道「不要记这个」也是一种可学习信号，而不是散落在对话里。
当 Dream 发现重复记忆时，也可以生成 `consolidation_suggestion`
候选，请 reviewer 决定是否合并、保留或归档；它不会自己改正式知识库。

Agent 安装精灵可以用
`vault setup-agent --automation-schedule cron|launchagent|n8n|all` 生成 cron、
LaunchAgent 或 n8n 模板。排程默认跑 `vault automation cycle`，让长期
Agent 可以先从已审核结果写出 bounded learning policy，再整理记忆。排程仍然是
report-first；只有使用者明确加上 `--automation-apply`，才会执行 policy
允许的可逆归档。想要更单纯的维护排程，可以加 `--automation-command run`。

自动化细节：[docs/automation.md](docs/automation.md)。

## 记忆整理 Agent

Vault 可以生成 Profile、Dream、Forgetting agent 的使用指引。这些 agent
默认应该保守：Dream 先生成 report，cleanup 检查 stale entries、duplicates
和 weak metadata；若使用 `apply_safe`，应先建立 backup，让 rollback 保持可行。
promotion、deletion、archive、expiry 这类动作，在使用者批准策略前都应保持
candidate-only 或 report-only。

设置入口：[docs/agent_install.md](docs/agent_install.md)。
治理细节：[docs/memory_governance.md](docs/memory_governance.md)。

## 可整合的系统

| 系统 | 使用方式 |
|---|---|
| Claude Code / Codex / OpenCode | CLI 或 local stdio MCP |
| Hermes Agent / OpenClaw | CLI、MCP、生成的 agent install files |
| n8n | Supabase sync 和 remote-reader workflow templates |
| Coze 或 hosted agents | Supabase read-only RPC 和 OpenAPI template |
| Obsidian | 导入既有笔记，或导出 Vault 知识 |
| Headroom | Vault 筛出内容后，再做可选 context 压缩 |

整合文件入口：[docs/agent_integrations.md](docs/agent_integrations.md)。

## 可选：Supabase 共享

SQLite 仍然是 source of truth。Supabase 是可选的共享层。

当不同主机、n8n、Coze 或 hosted agent 需要读取共享记忆时，可以同步安全摘要：

```bash
pip install "vault-for-llm[supabase]==0.6.60"
python -m scripts.sync_to_supabase --db ~/Vaults/my-project/vault.db --document-map --health
```

设置指南：[docs/supabase_setup.md](docs/supabase_setup.md)。
Read policy template：[docs/supabase_read_policy.sql](docs/supabase_read_policy.sql)。

## Obsidian

导入既有 Obsidian vault：

```bash
vault import obsidian --vault ~/Documents/ObsidianVault --project-dir ~/Vaults/my-project --dry-run
vault import obsidian --vault ~/Documents/ObsidianVault --project-dir ~/Vaults/my-project --compile
```

导出 Vault 知识给 Obsidian 阅读：

```bash
vault export obsidian --project-dir ~/Vaults/my-project --vault ~/Documents/ObsidianVault
```

Importer 默认会跳过 `.obsidian`、`.trash`、`.git` 和 Vault 自己导出的文件夹。

## 搜索质量

Vault 内置 Search QA，让你测“Agent 有没有找对来源”：

```bash
vault search-qa run \
  --qa-file benchmarks/search_qa/basic.zh-Hant.json \
  --mode keyword \
  --output /tmp/vault-searchqa.json
```

目前的 benchmark 数字只代表 retrieval evidence，不等于最终回答质量：

- project onboarding proof：在本地 proof run 中，Vault 对 28/28 任务找到 source-backed project memory
- LoCoMo retrieval probe：hierarchical session + local evidence-window retrieval 在官方计分类别有高 evidence recall
- 官方 answerer/judge score 需要另外接 model provider 跑

更多资料：[docs/agent_onboarding_benchmark.md](docs/agent_onboarding_benchmark.md)、
[docs/search_qa_benchmarking.md](docs/search_qa_benchmarking.md)。

## 成熟度

| 功能区 | 状态 |
|---|---|
| local SQLite、Markdown compile、keyword search | stable |
| CLI setup、候选记忆、bounded read | usable |
| MCP tools | usable，建议用 tool profile 控制 token |
| Obsidian import/export | usable |
| Supabase sync 和 remote read templates | advanced optional |
| policy-based memory automation | usable-alpha |
| semantic search、API/local embedding providers、rerank、benchmark adapters | evolving |
| Profile / Dream / Forgetting agents | guidance-first，不会自动删记忆 |

Vault-for-LLM 还没到 1.0。核心本地路径故意保持简单；进阶整合很有用，但应该由使用者明确开启。

## 文件地图

- Agent 安装手册：[docs/agent_install.md](docs/agent_install.md)
- CLI 参考：[docs/cli_reference.md](docs/cli_reference.md)
- Agent 整合：[docs/agent_integrations.md](docs/agent_integrations.md)
- 记忆自动化：[docs/automation.md](docs/automation.md)
- 记忆治理：[docs/memory_governance.md](docs/memory_governance.md)
- Supabase 设置：[docs/supabase_setup.md](docs/supabase_setup.md)
- MCP 工具参考：[docs/mcp_tool_reference.md](docs/mcp_tool_reference.md)
- MCP workflow：[docs/mcp_memory_workflow.md](docs/mcp_memory_workflow.md)
- PageIndex / Headroom 比较：[docs/comparisons/pageindex_headroom.md](docs/comparisons/pageindex_headroom.md)
- 愿景笔记：[docs/vision.md](docs/vision.md)

## 开发

```bash
git clone https://github.com/zycaskevin/Vault-for-LLM.git
cd Vault-for-LLM
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,mcp]"
pytest -q
```

## 授权

Apache-2.0。请见 [LICENSE](LICENSE)。
