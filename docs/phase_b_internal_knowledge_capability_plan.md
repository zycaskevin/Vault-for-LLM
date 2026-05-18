# Phase B — 內部百科真正能力建設計劃

> **For Hermes:** 這是 Guardrails 內部百科主線，不是 Vault-for-LLM public release 支線。實作時先用 `subagent-driven-development` 拆任務；每個子任務完成後更新本文件與 `PROGRESS.md` / handoff。

**Last updated:** 2026-05-18 10:34 CST

**Scope:** Nancy / Hermes / Guardrails 內部 dogfood 能力建設

**Not scope:** Vault-for-LLM public README、PyPI release hygiene、GitHub Release notes、開源包裝文案

---

## 0. 北極星

Phase B 的目的不是「把 Vault-for-LLM 包裝得更像產品」，而是：

> 讓 Nancy / Hermes / Guardrails 每天真正使用百科，在真實對話、真實寫入、真實搜尋、真實多 Agent 協作裡，逼出記憶治理問題。

核心壁壘：

1. 對話回寫治理
2. Document Map 強化
3. Search QA metrics
4. CJK 搜尋
5. session capture draft queue
6. privacy scanner
7. 多 Agent 寫入與收斂流程

這 7 件事是內部百科的真正能力；開源版 Vault-for-LLM 只能在這些能力被內部驗證後，輸出 public-safe、product-neutral、可安裝、可測試、可解釋的切片。

---

## 1. 與 Vault-for-LLM agentmemory roadmap 的關係

`/home/zycas/Vault-for-LLM/docs/agent_memory_qa_roadmap.md` 是 public open-source roadmap。它把 agentmemory 的優點拆成 public phases：

- Phase 2: Document Map as differentiator
- Phase 3: Search QA and benchmark fixtures
- Phase 4: FTS/BM25 + vector + graph + RRF
- Phase 5: Review-gated session capture
- Phase 6: Privacy and safety layer
- Phase 7: doctor/demo/connect onboarding

Guardrails 內部 Phase B 對應關係：

| 內部 Phase B | Public roadmap 對應 | 內部優先度 |
|---|---|---|
| B1 對話回寫治理 | Phase 5 + Phase 6 的前置治理 | P0 |
| B2 Document Map 強化 | Phase 2 | P0 — design complete |
| B3 Search QA metrics | Phase 3 | P0 |
| B4 CJK 搜尋 | Phase 3 + Phase 4 | P1 |
| B5 session capture draft queue | Phase 5 | P1 — design complete |
| B6 privacy scanner | Phase 6 | P0 — design complete |
| B7 多 Agent 寫入與收斂 | Phase 5/6 + Guardrails convergence/freshness | P1 |

Public roadmap 的 Phase 0/1/F release hygiene 已經在 Vault-for-LLM 0.4.1/0.4.2 期間處理一輪；後續仍重要，但不是內部百科主線。

---

## 2. 已有基礎

### 2.1 Document Map 基礎

已有設計文件：

- `docs/document_map_upgrade_plan.md`

已落地能力包含：

- `guardrails_map_show`
- `guardrails_read_range`
- local / remote read path
- citation policy harness
- Document Map health snapshot

目前問題：

- 部分高價值舊知識仍沒有 map nodes。
- 新寫入知識可用 `read_range` 精確讀回，但 semantic search 召回不一定命中。
- Agent 行為雖已有 citation policy，但主線任務需要把 coverage、health、缺口清單產品化。

### 2.2 Search QA / convergence / freshness 基礎

已有設計與部分實作：

- `docs/optimization_plan_v2.md`
- convergence / freshness 欄位與 scripts
- Search QA before/after metrics 經驗
- Document Map citation policy harness

目前問題：

- 內部百科缺一組持續維護的「真實查詢 QA set」。
- CJK 查詢召回不穩，例如「Phase B / 內部百科 / 對話回寫治理」未能精準召回剛寫入的 roadmap 條目。
- 新寫入後 search 召回延遲或 ranking 不命中，需要明確 backlog 與驗證流程。

### 2.3 寫入治理基礎

已有 SOUL / skill /百科規則：

- 對話 >5 tool calls 或架構決策後要問是否寫入百科。
- 寫入前要判斷 3 個月後是否有用、是否已存在、summary 是否清楚。
- 長期保存應 local add → compile → sync。

目前問題：

- 沒有正式 draft queue；寫入常直接進正式百科。
- 沒有對 session capture 做分級：shared knowledge / private draft / no-write。
- privacy scanner 尚未成為所有入口的硬 gate。

---

## 3. B1 — 對話回寫治理

**Status:** COMPLETE (design) — see `docs/session_writeback_governance.md`.

**Goal:** 從「做完問要不要寫」升級為「session → candidate → draft → review → promote」的治理流程。

### B1.1 分級模型

每條 session candidate 必須先分類：

| 分級 | 說明 | 可進 normal search? |
|---|---|---|
| shared knowledge | 可跨 agent 使用的技術/流程/決策知識 | 是，promote 後 |
| private draft | 含人生側寫、客戶上下文、內部環境細節，需人工整理 | 否 |
| no-write | token、密碼、原始私密心事、客戶個資、一次性任務流水 | 否 |

### B1.2 寫入決策樹

```text
session candidate
  ↓
有 token/secret/客戶個資？ → block / no-write
  ↓
是 Arthur 私密人生側寫？ → private draft，只提煉協作規則，不共享原文
  ↓
3 個月後還有用？ → 否：不寫
  ↓
能否用 1 句 summary 說清楚？ → 否：先提煉
  ↓
已有相同條目？ → 是：更新/merge，不新增
  ↓
shared knowledge draft
  ↓
review / promote
```

### B1.3 產物

- `docs/session_writeback_governance.md`
- draft candidate schema
- promote checklist
- merge/update policy

### B1 acceptance

- 任何 >5 tool call session 都能產生候選清單，但不會自動寫正式百科。
- `no-write` 類型有明確規則。
- private draft 與 shared knowledge 邊界清楚。
- 新寫入要能以 ID 精確讀回；search 不命中時要標記 indexing/search backlog，而不是誤判寫入失敗。

---

## 4. B2 — Document Map 強化

**Status:** COMPLETE (design) — see `docs/document_map_coverage_plan.md`.

**Goal:** 讓長知識可以先看 map，再局部 read_range；引用只來自 read_range。

### B2 work items

1. 列出高價值但 `no_document_map_nodes` 的知識。
2. 優先對以下類型 build map：
   - Guardrails 操作 SOP
   - release / repo hygiene SOP
   - Document Map / Search QA / privacy scanner 設計
   - Arthur 明確要求沉澱的決策
3. 建立 citation coverage 指標：
   - entries_with_nodes / total_entries
   - entries_with_claims / total_entries
   - read_range_over_limit violations
4. 將 search result 的 citation 標示為 navigation hint，不作 final evidence。

### B2 acceptance

- Top 50 高價值知識有 map nodes。
- 回答需要百科依據時，標準 trace 是 `search → map_show → read_range → answer`。
- 對無 map nodes 條目，工具回 actionable next step。

### B2 design artifact

- `docs/document_map_coverage_plan.md` defines local SQLite coverage snapshot, P0/P1 backlog, map/claim/citation metrics, build/verify workflow, trace policy, gap schema, B3 Search QA feed, edge cases, smoke checks, and implementation tasks.

---

## 5. B3 — Search QA metrics

**Goal:** 用數字衡量搜尋品質，而不是靠感覺。

### B3 work items

1. 建立內部 QA set：`qa/internal_guardrails_search_qa/*.json`。
2. 每個 case 至少包含：
   - query
   - expected_title_substrings
   - expected_knowledge_ids（若穩定）
   - should_have_map_guidance
   - should_require_read_range
   - language: en / zh-Hant / mixed
3. 指標：
   - top1 hit
   - hit@k
   - MRR
   - map/read guidance rate
   - citation-policy violations
   - CJK query recall
4. 建立 before/after comparison。

### B3 acceptance

- 每次調 search/ranking/tokenizer 前後都能跑同一套 QA。
- Search QA 不等於 agent end-to-end success，報告要明確標註。
- 新寫入知識若 ID 可讀但 search 不命中，要進 QA backlog。

---

## 6. B4 — CJK 搜尋

**Goal:** 繁中/中文查詢能穩定召回，不因 tokenizer 或中英混合而掉結果。

### B4 work items

1. 收集真實 CJK miss cases：
   - Phase B / 內部百科 / 對話回寫治理
   - Document Map 強化
   - 搜尋品質 / 召回
   - 隱私掃描 / 客戶個資
2. 增加 alias/synonym：
   - 對話回寫 = session writeback = conversation harvesting
   - 草稿隊列 = draft queue = capture queue
   - 百科 = Guardrails = knowledge base
3. 評估 SQLite FTS5 unicode61、trigram/ngram fallback 或 query rewrite。
4. CJK QA set 進 B3 gate。

### B4 acceptance

- 核心中文 roadmap query 能命中 #734 與相關條目。
- 中英混合 query 不顯著劣化。
- 無 tokenizer 依賴時有 graceful fallback。

---

## 7. B5 — Session capture draft queue

**Status:** COMPLETE (design) — see `docs/session_capture_draft_queue_design.md`.

**Goal:** 借鑑 agentmemory capture 的好處，但所有 capture 先進 draft，不直接污染正式百科。

### B5 pipeline

```text
session transcript / JSONL / Feishu conversation
  ↓
extract candidates
  ↓
privacy scan
  ↓
dedupe / classify
  ↓
capture_drafts table or drafts/ markdown
  ↓
review: promote / merge / discard
  ↓
raw/ + compile
  ↓
normal search
```

### B5 work items

1. 設計 `capture_drafts` schema 或 `drafts/` 文件格式。
2. 支援來源：Hermes session、Feishu transcript、manual pasted notes。
3. draft 不進 normal search。
4. promote 時套用 B1/B6 規則。
5. 每個 draft 保留 source session metadata，但不要保存 secrets 原文。

### B5 acceptance

- capture 預設 dry-run。
- 未 promote 的 draft 不會被 `guardrails search` 命中。
- promote 走與手動 raw entry 同一套 compile/map/sync 流程。

### B5 design artifact

- `docs/session_capture_draft_queue_design.md` defines the dry-run-first capture pipeline, SQLite draft queue schema, optional Markdown review export, B1/B6 routing matrix, dedupe/merge/contradiction workflow, promotion path, normal-search invisibility proof, CLI/MCP/Feishu/cron boundaries, and deterministic smoke cases.

---

## 8. B6 — Privacy scanner

**Status:** COMPLETE (design) — see `docs/privacy_scanner_design.md`.

**Goal:** 任何寫入、capture、compile、sync 前，都先阻擋高風險資料。

### B6 scan scope

- API keys / bearer tokens / PyPI tokens / GitHub tokens
- private keys
- emails / phone / addresses
- 客戶姓名、療程、財務資訊
- Arthur 私密人生側寫原文
- 內部部署 URL / dashboard private paths / local credentials

### B6 work items

1. 共用 scanner module。
2. 掛到：
   - `guardrails add`
   - MCP add
   - capture import
   - compile
   - sync_to_supabase
3. 支援 redaction preview。
4. 支援 explicit override，但要記 audit trail。
5. 規則可 project-level config。

### B6 acceptance

- raw secrets 不會進 normal search。
- scanner 是 best-effort，文檔不做合規過度承諾。
- 對醫美/CRM/人生側寫有專門規則：原文不共享，只沉澱協作規則。

### B6 design artifact

- `docs/privacy_scanner_design.md` defines the shared scanner boundary, outcomes, finding categories, redaction preview, override/audit policy, CLI/MCP/capture/compile/sync integration points, and deterministic smoke cases.

---

## 9. B7 — 多 Agent 寫入與收斂

**Status:** COMPLETE (design) — see `docs/multi_agent_convergence_workflow.md`.

**Goal:** 多個 agent 可以共同貢獻知識，但不互相覆蓋、不重複、不污染。

### B7 work items

1. 寫入鎖 / append-only draft 流程。
2. 同名或近似標題去重。
3. merge policy：新條目 vs update note。
4. contradiction detection。
5. convergence/freshness queue。
6. local SQLite 為 source of truth，Supabase 為 sync target。
7. 多 agent 回寫時標記 source_agent / source_session / trust。

### B7 acceptance

- 同一知識不會因 MCP add + local sync 產生重複。
- sync 不會覆蓋新知識而無告警。
- partial / unknown 條目有固定收斂任務。
- 多 Agent 寫入能追溯來源。

### B7 design artifact

- `docs/multi_agent_convergence_workflow.md` defines the local-first multi-agent writing workflow, append-only provenance, draft/review/promote state model, duplicate and contradiction handling, convergence/freshness queues, safe Supabase sync boundaries, public-safe Vault-for-LLM export manifest, and deterministic smoke cases.

---

## 10. Recommended execution sequence

```text
B1 governance spec
  → B6 privacy scanner design
  → B5 draft queue design
  → B2 Document Map coverage pass
  → B3 Search QA internal set
  → B4 CJK retrieval improvements
  → B7 multi-agent convergence workflow
```

理由：

- 沒有 B1/B6，就不能放心做 capture。
- 沒有 B2/B3，就無法判斷搜尋/引用品質是否改善。
- B4 需要 B3 指標支撐。
- B7 需要 B1/B5 的 draft/promotion 流程作為基礎。

---

## 11. Immediate next task

Start the smallest safe B7 implementation slice: report-only duplicate/conflict detector plus convergence/freshness queue integration.

必須包含：

1. queue/audit schema or JSON report contract for duplicate, contradiction, convergence, freshness, and sync-drift items
2. exact-title, normalized-title, content-hash, semantic, and graph-neighbor duplicate signals
3. MCP/direct-add bypass detection for DB-only rows missing raw/compiled/map provenance
4. convergence/freshness outputs converted into fixed review queue items without rewriting knowledge content
5. safe sync dry-run boundaries: local SQLite/raw source of truth, Supabase as sync target only, no remote overwrite
6. deterministic smoke tests for draft invisibility, idempotent import, no-double-write, privacy block before sync, and queue creation

完成 report-only B7 slice 後，再決定是否進入 promotion lock/idempotency、safe sync planner，或 public-safe Vault-for-LLM slice exporter。
