# Guardrails Knowledge Graph — Wiki Index

> 自動生成自 Graphify 圖譜。Agent 用此頁快速定位知識群落。
> 圖譜路徑: `/home/zycas/.hermes/Guardrails/graphify-out/`
> 更新: 每次 Guardrails 變更後自動重建（cron 每小時檢查）

---

## 圖譜概覽

- **765 nodes · 802 edges · 33 communities**
- 最活躍的核心概念見下方 God Nodes

---

## God Nodes（核心概念，連結最多）

| # | 概念 | 連結數 | 入口檔案 |
|---|------|--------|----------|
| 1 | 2026-03-25 歷史記憶 | 71 | `memory-base/daily/2026-03-25.md` |
| 2 | proactive-agent | 59 | `knowledge-base/skills/proactive-agent.md` |
| 3 | clawsend 加密通訊 | 44 | `knowledge-base/skills/clawsend.md` |
| 4 | AGENT_GUIDE | 41 | `AGENT_GUIDE.md` |
| 5 | DISTRIBUTED_WRITING_PROTOCOL | 39 | `schema/DISTRIBUTED_WRITING_PROTOCOL.md` |
| 6 | 2026-03-28 歷史記憶 | 36 | `memory-base/daily/2026-03-28.md` |
| 7 | agent-browser | 35 | `knowledge-base/skills/agent-browser.md` |
| 8 | 2026-04-02 歷史記憶 | 34 | `memory-base/daily/2026-04-02.md` |
| 9 | 2026-03-30 歷史記憶 | 32 | `memory-base/daily/2026-03-30.md` |
| 10 | k8s-debug | 31 | `knowledge-base/skills/k8s-debug.md` |

---

## 知識群落導航

### 🧠 記記憶群落（歷史決策與日常記錄）

| 群落 | 節點數 | 主題 | 入口 |
|------|--------|------|------|
| C0 | 72 | 3/25 高強度工作日 | `memory-base/daily/2026-03-25.md` |
| C5 | 37 | 3/28 維護轉型期 | `memory-base/daily/2026-03-28.md` |
| C7 | 35 | 4/02 系統穩定期 | `memory-base/daily/2026-04-02.md` |
| C8 | 33 | 3/30 基礎設施投資 | `memory-base/daily/2026-03-30.md` |
| C11 | 29 | 3/29 技能總結 | `memory-base/daily/2026-03-29-skills-summary.md` |
| C13 | 28 | 3/31 維護日 | `memory-base/daily/2026-03-31.md` |
| C15 | 24 | 3/26 API參數教訓 | `memory-base/daily/2026-03-26.md` |

### 🔧 技能群落

| 群落 | 節點數 | 技能 | 入口 |
|------|--------|------|------|
| C1 | 60 | proactive-agent 主動式代理 | `knowledge-base/skills/proactive-agent.md` |
| C2 | 45 | clawsend 加密通訊 | `knowledge-base/skills/clawsend.md` |
| C6 | 36 | agent-browser 瀏覽器自動化 | `knowledge-base/skills/agent-browser.md` |
| C10 | 32 | k8s-debug K8s除錯 | `knowledge-base/skills/k8s-debug.md` |
| C12 | 28 | research-optimizer 研究優化 | `knowledge-base/skills/research-optimizer.md` |
| C16 | 24 | openclaw-updater OC更新 | `knowledge-base/skills/openclaw-updater.md` |
| C20 | 14 | firecrawl-skills 爬蟲 | `knowledge-base/skills/firecrawl-skills.md` |

### 🏗️ 架構與規範群落

| 群落 | 節點數 | 主題 | 入口 |
|------|--------|------|------|
| C3 | 42 | Agent 使用指南 | `AGENT_GUIDE.md` |
| C4 | 40 | 分散式寫作協議 | `schema/DISTRIBUTED_WRITING_PROTOCOL.md` |
| C14 | 27 | 軍團宣言 | `ARMY_MANIFESTO.md` |

### 🔬 深度知識群落

| 群落 | 節點數 | 主題 | 入口 |
|------|--------|------|------|
| C17 | 23 | MemPalace vs LLM Wiki 比較 | `raw/research/2026-04-12/mempalace-vs-llmwiki-comparison.md` |
| C19 | 17 | Guardrails 增強版設定 | `L3-knowledge/compiled/techniques/guardrails-enhanced-setup.md` |
| C22 | 12 | LINE Desktop MCP 分析 | `compiled/techniques/line-tools/2026-04-12-line-desktop-mcp-analysis.md` |

### ⚙️ 系統腳本群落

| 群落 | 節點數 | 主題 | 入口 |
|------|--------|------|------|
| C9 | 32 | Compiler + FeatureExtractor | `scripts/basic_compiler.py` |
| C18 | 18 | AAAK 壓縮格式 | `scripts/aaak_compress.py` |
| C21 | 12 | Data Collector | `scripts/data_collector.py` |
| C24 | 8 | Guardrails Wakeup | `scripts/guardrails_wakeup.py` |
| C26 | 6 | 同步腳本 | `tools/sync-scripts/sync-from-workspace.py` |

---

## 查詢方式

```bash
# BFS 搜尋（預設）
cd /home/zycas/.hermes/Guardrails && graphify query "你的問題" --budget 1000

# DFS 搜尋（深入特定分支）
graphify query "你的問題" --dfs --budget 2000

# 直接 grep 搜知識
grep -rl "關鍵詞" knowledge-base/ experience-base/ error-base/
```

---

*最後重建: 2026-04-16 | 節點: 765 | 群落: 33*
