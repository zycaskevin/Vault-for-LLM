# Vault-for-LLM

給 AI Agent 使用的本地優先專案記憶層。

Vault-for-LLM 會把專案筆記、決策、錯誤修正、SOP、Obsidian 筆記，以及
Agent 提出的候選記憶，整理成一個可攜帶的 SQLite vault。Agent 可以搜尋、
按範圍閱讀、引用來源、測試召回、備份，必要時也能同步到 Supabase 讓不同主機讀取。

它不是要取代模型、wiki、Obsidian 或 hosted memory system。
它比較像中間那一層：讓 Agent 使用專案知識時，不只是「記得」，而是記得有來源、
有邊界、可審核，也能回復。

預設路徑是讓 Agent 代為安裝：先問資料庫要放哪裡、要 shared 還是 private，
再跑一個 search/read/propose smoke test。手動命令仍然保留，但不是新手的主路徑。

## 為什麼需要它

很多 Agent 問題不是模型不夠聰明，而是工作記憶太混亂：

- 新 session 又像第一天上班
- 舊文件和新決策混在一起
- 修過的 bug 留在聊天紀錄裡，下一次又重踩
- 私人觀察被誤放進共享專案記憶
- 團隊不知道搜尋到底有沒有找對來源

Vault-for-LLM 想解的是這個問題：

> 這個專案已經學到什麼？來源在哪裡？這個 Agent 可以使用它嗎？

## 你會得到什麼

- **本地優先**：核心功能只需要 Markdown 和 SQLite，不必先接雲端。
- **Agent 友善**：提供 CLI 和 MCP，支援搜尋、bounded read、候選記憶、Document Map。
- **候選制寫入**：Agent 先提出記憶，通過檢查後才進正式知識庫。
- **治理 metadata**：每筆記憶都可以帶 scope、sensitivity、owner agent、allowed agents、過期時間。
- **Obsidian 雙向工作流**：可匯入既有 Obsidian 筆記，也可匯出成 Obsidian 可讀格式。
- **可選遠端共享**：Supabase sync 和 read-only RPC 讓不同主機或 hosted agent 讀共享記憶。
- **Report-first 自動化**：可產生 cron、LaunchAgent、n8n 模板，定期整理記憶，但不會偷偷刪除或提升記憶。
- **可測試召回**：Search QA 和 onboarding benchmark 可以量化 Agent 是否找得到正確來源。

## 什麼時候適合用

適合你，如果：

- 你用 Claude Code、Codex、Hermes Agent、OpenClaw、OpenCode、n8n 或其他 Agent 做專案
- 你希望多個 Agent 共用專案知識，但不要互相讀到私人原始對話
- 你已經有 Markdown 或 Obsidian 筆記，希望 Agent 能查、能引用
- 你想本地保存記憶，但又需要 Supabase 讓其他主機讀取安全摘要
- 你在意召回品質，希望能測，而不是只靠感覺

如果你只需要 hosted vector database、普通筆記軟體，或完全自動的聊天記憶產品，
Vault-for-LLM 可能不是第一個該拿起來的工具。

## 安裝

### 讓 Agent 代為安裝

最推薦的方式，是直接把這段交給能執行本機指令的 Agent：

```text
幫這個專案安裝 Vault-for-LLM。使用 vault-for-llm[mcp]==0.6.121。
先問我要 shared、private、domain-specific 還是 temporary vault。
詢問穩定的 project directory，並為長期任務產生 stable venv script。
逐項詢問 MCP、semantic search、Supabase、Obsidian import、Headroom 壓縮、
memory-agent guidance。只安裝我同意的 optional dependencies。
最後跑 search/read/propose smoke test。
```

Agent 會使用安裝精靈：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install "vault-for-llm[mcp]==0.6.121"

vault setup-agent
```

`setup-agent` 會把目前 Agent 登記到本機 registry：
`~/.vault-for-llm/agent-registry.json`，並產生一包 `agent-install/` 文件：

- MCP 啟動流程
- update-status 與 rollout doctor 模板
- Codex、Claude Code、OpenClaw、Hermes Agent 啟動模板
- 多 runtime 共用的 runtime update playbook
- hybrid shared/private vault layout manifest

檢查這包啟動文件是不是最新版：

```bash
vault agent startup-doctor --template-dir ./agent-install
```

每個 runtime 都可以讀自己的 focused startup view：

```bash
vault update-status --read-status --agent codex
```

如果要讓 Vault 安全地把某個 runtime 模板貼進目標檔案，先 preview，再 apply：

```bash
vault agent install-runtime-template --runtime codex --target ./AGENTS.md
vault agent install-runtime-template --runtime codex --target ./AGENTS.md --apply
```

套用命令預設是 dry-run，真的寫入時會先備份既有檔案。完整安裝細節放在
[`docs/agent_install.md`](docs/agent_install.md)。

非互動安裝範例：

```bash
vault setup-agent \
  --non-interactive \
  --agent codex \
  --scope shared \
  --agent-project-dir ~/Vaults/my-project \
  --memory-layout hybrid \
  --features core,mcp,supabase,headroom \
  --write-stable-venv-script \
  --supabase-setup simple \
  --remote-reader shell \
  --automation-schedule cron \
  --automation-write-workspace \
  --automation-include-transcripts \
  --automation-auto-promote-low-risk \
  --json
```

這會產生 `agent-install/setup-stable-venv.sh`，讓排程、Supabase sync、MCP command
不需要依賴重開機後可能消失的 `/tmp` virtualenv。

### 手動快速開始

```bash
pip install "vault-for-llm[mcp]==0.6.121"

vault init ~/Vaults/demo
vault add "First lesson" \
  --content "The bug was caused by a missing cache key. The fix was adding provider metadata." \
  --project-dir ~/Vaults/demo
vault compile --project-dir ~/Vaults/demo --no-embed
vault search "cache key" --project-dir ~/Vaults/demo
```

## Agent 日常流程

建議 Agent 這樣使用記憶：

1. **先搜尋**：找可能相關的來源。
2. **再按範圍讀取**：不要整份文件塞進 context。
3. **回答時引用來源**：citation 要回到 Vault 原文，不要引用壓縮摘要。
4. **提出候選記憶**：新的教訓先進候選區。
5. **審核後再提升**：保持正式記憶庫乾淨、可追蹤。

Agent 也可以把一次工作 session 轉成候選記憶：

```bash
vault capture discover --project-dir ~/Vaults/my-project --pretty
vault capture session codex-session.jsonl --project-dir ~/Vaults/my-project --pretty
vault capture session codex-session.jsonl --project-dir ~/Vaults/my-project --write-candidates
```

Discovery 只列出可能的 transcript 檔案，不讀取內容。Session capture
預設只預覽；`--write-candidates` 只寫入候選記憶，不會自動提升成正式知識。

MCP-capable runtime 可以啟動：

```bash
vault-mcp --project-dir ~/Vaults/my-project --tool-profile core
```

建議先開 core tool profile：

- `vault_search`
- `vault_read_range`
- `vault_memory_propose`
- `vault_stats`
- `vault_update_status`
- `vault_automation_handoff`

負責 review 或維護的 Agent 可以在 MCP `review` profile 使用
`vault_capture_discover` 和 `vault_capture_session` 跑同一套 session capture。
Capture 預設只預覽；必須明確設定 `write_candidates=true`，才會寫入候選記憶。

MCP 文件：

- 工具參考：[docs/mcp_tool_reference.md](docs/mcp_tool_reference.md)
- workflow 與 token 預算：[docs/mcp_memory_workflow.md](docs/mcp_memory_workflow.md)

## 記憶分層

Vault 使用 L0-L3 表示記憶深度：

| Layer | 用途 |
|---|---|
| `L0` | 身份、專案定位、不可輕易改動的框架 |
| `L1` | 穩定事實、規則、偏好 |
| `L2` | 近期上下文、摘要、目前工作 |
| `L3` | 詳細知識、SOP、bug、決策、來源筆記 |

權限不要只靠 layer 判斷，請搭配治理 metadata：

- `scope`: private, project, shared, public
- `sensitivity`: low, medium, high, restricted
- `owner_agent`
- `allowed_agents`
- `memory_type`
- `expires_at`

MCP 寫入也會走同一套治理邊界。低敏感度的 `project` 寫入維持相容；
但 `shared` / `public`、`private`、`high`、`restricted` 寫入需要呼叫端提供
`agent_id`，並明確打開對應的 `allow_shared`、`allow_private`、
`allow_high_sensitivity` 或 `allow_restricted`。這樣多個 runtime 接到同一個
shared vault 時，不會變成誰都可以直接改正式記憶。

搜尋會記錄輕量使用統計（`access_count`、`citation_count`、
`last_accessed_at`）。`vault automation brief` 會把這些訊號整理成可解釋的
`importance_score`，並列出 access、citation、recency、trust、freshness、TTL
pressure 與 protection hints。這個分數只用來排序和輔助審查，不會繞過治理規則，
也不會自己把候選記憶升格。短期記憶若設定 `expires_at`，可以到期後移到
`status: archived`，不需要直接刪除：

```bash
vault usage stats
vault usage archive-expired --apply
vault usage cold-store-expired --apply
```

`archive-expired` 適合沒有保護性使用訊號的到期記憶。
`cold-store-expired` 適合已到期、但仍常被查詢或引用的記憶：它會寫入短摘要，
把 row 移出日常召回（`status: archived`），保留原文方便稽核/回復，並跳過
private、high/restricted、L0/L1 記憶。
當 `cold_store_used_expired` 和 `--apply` 都啟用時，`vault automation run` /
`vault automation cycle` 也會走同一條 cold-store 路徑。
cold-store preview 和 automation ledger 也會使用同一個 `importance_score`
排序過期但仍被使用的記憶，讓審查從最可能需要刷新、摘要或保護性冷存的內容開始。
`vault automation inbox` 和 `vault automation brief` 會把這些 report-level
訊號整理成短版 review digest，讓人類審核面保持很小：先看受保護 TTL
決策、過期但仍被使用的記憶、cold-store 摘要與 promotion preview，再決定
是否打開原始候選內容。
`vault automation review-summary` 會再更短一層：把 brief、inbox 和最新 report
整理成幾張 approval cards，只留下真正需要人看的 5% 記憶決策。
`vault automation review-feedback` 則把這個小閉環接起來：記錄某張卡片被
接受、拒絕或延後，讓 `automation eval` 把長期結果轉成下一輪排序提示。
`vault automation learning-health` 會把這個閉環整理成 dashboard-safe 狀態：
目前還在冷啟動、健康、需要觀察，或需要人檢查。
當 `vault automation eval --write-learning-policy` 累積足夠已審核回饋後，
inbox/brief 也會用這份 bounded learning policy 來排序 review items。倍率會
明確顯示且有上限；它不是授權策略。

設計說明：[docs/memory_governance.md](docs/memory_governance.md)。

Policy-based automation 讓 Agent 處理例行整理，但由人保留規則主權：

```bash
vault automation plan --write-policy
vault automation run
vault automation run --apply
vault automation cycle --apply
vault automation cycle --apply --include-transcripts --capture-transcripts --write-workspace
vault automation inbox --limit 5
vault automation inbox --include-transcripts --write-handoff
```

`vault capture session` 是這個閉環的入口。它會從 Agent transcript 裡找出可重用的
決策、踩坑、流程、source-of-truth 訊號，先送進候選與安全 gate；後續 Dream 和
automation 可以排序與整理，但 promotion 仍然需要明確審核。

`vault automation cycle` 會先評估已審核的候選結果，寫出 bounded
`learning_policy.json`，再跑一次安全自動化，讓 Dream 用最新的整理提示排序候選。
它預設仍然不會自動 promote、硬刪記憶，或繞過隱私與權限規則。
加上 `--write-workspace` 時，會寫出
`reports/automation/cycle-latest.json`：一份給下一個 Agent 用的短版工作台，
包含候選審核、可選的 transcript 路徑，以及最新 curation policy 摘要。
同時也會寫出 `reports/automation/cycle-latest.md`，給人和下一個 Agent 先讀；
它會放 priority brief、suggested next tasks、agent start prompt，但不展開候選原文或
transcript 內容。
下一個 Agent 可以直接用這條指令讀取最新短版 handoff：

```bash
vault automation handoff
```

MCP-capable Agent 可以在 `core` profile 直接用 `vault_automation_handoff`
讀取同一份短版 handoff。

如果 `reports/automation/fleet-health-latest.md` 或 `.json` 已存在，
handoff 也會帶上這份多 Agent 共同健康面板。CLI 會先顯示 fleet health，
再顯示 cycle/inbox handoff；MCP 則保留原本主要 handoff 在 `content`，
並用 `fleet_health_content` 額外提供共同健康面板。

`vault automation inbox` 是這個閉環的短版審核入口。它不會修改記憶，只會把
privacy blocked、敏感、重複、品質不足、automation 產生的候選排出優先順序；
預設不顯示原始內容，只給人或可信任 Agent 一個最小必要的 review queue。
排程模板每次成功執行後，也會把同一份短版收件匣寫到
`reports/automation/inbox-latest.json`，方便下一個 Agent 接續。
`vault automation activity` 是同一個閉環的最短稽核入口：它只顯示最近
auto-promote 的 preview、實際提升、被擋原因，不顯示候選原文。MCP-capable
Agent 可以在 `core` profile 直接呼叫 `vault_automation_activity`。

`vault automation brief` 是每天最短的智慧總覽：它把 promote/reject feedback
學到的排序提示、可解釋的記憶重要度、遺忘壓力、多 Agent 健康狀態，以及 5% 需要
人看的 review queue 合在一起。先看這份，再決定要不要打開完整報告：

```bash
vault automation brief --pretty
vault automation review-summary --write-summary
vault automation review-feedback --kind memory_importance --card-id 12 \
  --decision accept --reason "正確保護了過期但仍被引用的記憶" \
  --write-learning-policy
vault automation learning-health --write-health
vault automation fleet-health --write-health
```

MCP-capable Agent 可以在 `core` profile 直接呼叫 `vault_automation_brief`。
多 Agent 安裝時，`vault automation fleet-health` 會把本機 Agent registry、
learning-health 狀態和 update-distribution health 合成
`reports/automation/fleet-health-latest.json` 與 `.md`。它只讀 registry
metadata 和短報告，不讀私人記憶、raw candidate content 或 raw feedback reason。
`vault automation handoff` 會在檔案存在時，把這份共同健康面板放在個別
cycle/inbox handoff 前面。
如果安裝時加上 `--automation-include-transcripts`，排程 handoff 也會列出尚未
capture 的 transcript 候選路徑。這只包含 metadata，不讀 transcript 內容，也不會
自動把對話變成正式記憶。
如果明確加上 `--capture-transcripts --apply`，cycle 可以把 discovered
transcript 轉成通過 gate 的候選記憶。它仍然不會自動提升成正式記憶，產生的
handoff 也不會包含 transcript 原文或候選內容。

如果你真的想讓「候選記憶」自動進入「正式記憶」，需要在
Agent 安裝時明確開啟低風險 auto-promote：

```bash
vault setup-agent \
  --automation-schedule cron \
  --automation-apply \
  --automation-auto-promote-low-risk
```

這會替你寫入 `automation_policy.yaml`。內容等同於：

```yaml
auto_promote_low_risk_candidates: true
auto_promote_allowed_sources: [session_capture]
auto_promote_allowed_memory_types: [session_lesson]
auto_promote_allowed_sensitivities: [low]
auto_promote_min_trust: 0.65
auto_promote_max_per_run: 3
auto_promote_requires_source_ref: true
```

開啟後，`vault automation cycle --apply` 只會提升同時符合這些條件的候選：
來自 session capture、類型是 session lesson、低敏感度、有 source reference、
trust 達標，而且 privacy、duplicate、metadata、quality 四個 gate 全部通過。
沒有 `--apply` 時只會預覽，不會真的提升。private、高敏感、重複、品質不足或
缺來源的候選仍然留在 review queue。

拒絕或阻擋候選也可以變成結構化回饋：

```bash
vault candidate-review mem_123 --outcome rejected --reason "太模糊，不值得長期保存。"
```

這讓 Agent 知道「不要記這個」也是一種可學習訊號，而不是散落在對話裡。
當 Dream 發現重複記憶時，也可以產生 `consolidation_suggestion`
候選，請 reviewer 決定是否合併、保留或歸檔；它不會自己改正式知識庫。

Agent 安裝精靈可以用
`vault setup-agent --automation-schedule cron|launchagent|n8n|all` 產生 cron、
LaunchAgent 或 n8n 模板。排程預設跑 `vault automation cycle`，讓長期
Agent 可以先從已審核結果寫出 bounded learning policy，再整理記憶。排程仍然是
report-first；只有使用者明確加上 `--automation-apply`，才會執行 policy
允許的可逆歸檔。想要更單純的維護排程，可以加 `--automation-command run`。
產生的排程每次跑完也會寫出
`reports/automation/learning-health-latest.json` 和 `.md`，讓人類和不同
Agent 看到同一份很短的學習健康狀態：還在 cold start、運作健康、需要觀察，
或有太多 reject 需要檢查。
如果希望排程自動寫出每日記憶工作台，加上 `--automation-write-workspace`，
它會產生 `reports/automation/cycle-latest.json` 和
`reports/automation/cycle-latest.md`，讓下一個 Agent 先看短版工作台，不用翻完整報告。
產生的排程 README 也會寫入 `vault automation handoff --project-dir ...`，提醒下一個
Agent 啟動時先用這條 read-only 指令接手。
如果希望排程 handoff 同時提示「有哪些對話匯出還沒 capture」，加上
`--automation-include-transcripts`；它只列路徑與檔案 metadata，不讀原文。
如果希望安裝精靈直接寫入低風險 auto-promote policy，加上
`--automation-auto-promote-low-risk`。要讓排程真的提升符合條件的候選，仍然必須
搭配 `--automation-apply`；沒有 `--apply` 時只會預覽。

自動化細節：[docs/automation.md](docs/automation.md)。

## 記憶整理 Agent

Vault 可以產生 Profile、Dream、Forgetting agent 的使用指引。這些 agent
預設應該保守：Dream 先產生 report，cleanup 檢查 stale entries、duplicates
和 weak metadata；若使用 `apply_safe`，應先建立 backup，讓 rollback 保持可行。
promotion、deletion、archive、expiry 這類動作，在使用者核准策略前都應維持
candidate-only 或 report-only。

設定入口：[docs/agent_install.md](docs/agent_install.md)。
治理細節：[docs/memory_governance.md](docs/memory_governance.md)。

## 可整合的系統

| 系統 | 使用方式 |
|---|---|
| Claude Code / Codex / OpenCode | CLI 或 local stdio MCP |
| Hermes Agent / OpenClaw | CLI、MCP、產生的 agent install files |
| n8n | Supabase sync 和 remote-reader workflow templates |
| Coze 或 hosted agents | Supabase read-only RPC 和 OpenAPI template |
| Obsidian | 匯入既有筆記，或匯出 Vault 知識 |
| Headroom | Vault 篩出內容後，再做可選 context 壓縮 |

整合文件入口：[docs/agent_integrations.md](docs/agent_integrations.md)。

## 可選：Supabase 共享

SQLite 仍然是 source of truth。Supabase 是可選的共享層。

當不同主機、n8n、Coze 或 hosted agent 需要讀取共享記憶時，可以同步安全摘要：
Remote reader 應該直接把搜尋結果的 `id` 傳給 map/read；它可能是整數，也可能是 Supabase UUID。

```bash
pip install "vault-for-llm[supabase]==0.6.121"
python -m scripts.sync_to_supabase --db ~/Vaults/my-project/vault.db --document-map --health
```

設定指南：[docs/supabase_setup.md](docs/supabase_setup.md)。
Read policy template：[docs/supabase_read_policy.sql](docs/supabase_read_policy.sql)。

## Obsidian

匯入既有 Obsidian vault：

```bash
vault import obsidian --vault ~/Documents/ObsidianVault --project-dir ~/Vaults/my-project --dry-run
vault import obsidian --vault ~/Documents/ObsidianVault --project-dir ~/Vaults/my-project --compile
```

匯出 Vault 知識給 Obsidian 閱讀：

```bash
vault export obsidian --project-dir ~/Vaults/my-project --vault ~/Documents/ObsidianVault
```

Importer 預設會跳過 `.obsidian`、`.trash`、`.git` 和 Vault 自己匯出的資料夾。

## 搜尋品質

Vault 內建 Search QA，讓你測「Agent 有沒有找對來源」：

```bash
vault search-qa run \
  --qa-file benchmarks/search_qa/basic.zh-Hant.json \
  --mode keyword \
  --output /tmp/vault-searchqa.json
```

目前的 benchmark 數字只代表 retrieval evidence，不等於最終回答品質：

- project onboarding proof：在本地 proof run 中，Vault 對 28/28 任務找到 source-backed project memory
- LoCoMo retrieval probe：hierarchical session + local evidence-window retrieval 在官方計分類別有高 evidence recall
- 官方 answerer/judge score 需要另外接 model provider 跑

更多資料：[docs/agent_onboarding_benchmark.md](docs/agent_onboarding_benchmark.md)、
[docs/search_qa_benchmarking.md](docs/search_qa_benchmarking.md)。

## 成熟度

| 功能區 | 狀態 |
|---|---|
| local SQLite、Markdown compile、keyword search | stable |
| CLI setup、候選記憶、bounded read | usable |
| MCP tools | usable，建議用 tool profile 控制 token |
| Obsidian import/export | usable |
| Supabase sync 和 remote read templates | advanced optional |
| policy-based memory automation | usable-alpha |
| semantic search、API/local embedding providers、rerank、benchmark adapters | evolving |
| Profile / Dream / Forgetting agents | guidance-first，不會自動刪記憶 |

Vault-for-LLM 還沒到 1.0。核心本地路徑故意保持簡單；進階整合很有用，但應該由使用者明確開啟。

## 文件地圖

- Agent 安裝手冊：[docs/agent_install.md](docs/agent_install.md)
- CLI 參考：[docs/cli_reference.md](docs/cli_reference.md)
- Agent 整合：[docs/agent_integrations.md](docs/agent_integrations.md)
- 記憶自動化：[docs/automation.md](docs/automation.md)
- 記憶治理：[docs/memory_governance.md](docs/memory_governance.md)
- Supabase 設定：[docs/supabase_setup.md](docs/supabase_setup.md)
- MCP 工具參考：[docs/mcp_tool_reference.md](docs/mcp_tool_reference.md)
- MCP workflow：[docs/mcp_memory_workflow.md](docs/mcp_memory_workflow.md)
- PageIndex / Headroom 比較：[docs/comparisons/pageindex_headroom.md](docs/comparisons/pageindex_headroom.md)
- 願景筆記：[docs/vision.md](docs/vision.md)

## 開發

```bash
git clone https://github.com/zycaskevin/Vault-for-LLM.git
cd Vault-for-LLM
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,mcp]"
pytest -q
```

## 授權

Apache-2.0。請見 [LICENSE](LICENSE)。
