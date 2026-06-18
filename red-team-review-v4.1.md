# Vault-for-LLM v4.1 重新審查報告：功能、記憶召回、速率、代碼完整性與安全

**審查日期**: 2026-06-18  
**審查分支**: current working branch  
**審查方法**: 靜態審查核心模組與測試；執行 `pytest -q` 後針對阻斷錯誤做最小修復；重新執行目標測試。  
**重點模組**: `vault/search.py`, `vault/semantic.py`, `vault/docmap.py`, `vault/memory.py`, `vault/mcp.py`, `vault/db.py`, `vault/privacy.py`, `tests/test_semantic_index.py`。

---

## 1. 總評

本次大幅更新後，專案方向是正確的：搜尋已經從單純 keyword/vector/hybrid 推進到查詢擴展、LLM rewrite、rerank、Document Map citation、memory candidate gate 與 semantic index plumbing。這讓 Vault-for-LLM 更接近「可審計、可引用、可回收的 Agent 長期記憶層」。

不過，本次審查也證實有兩個「完整性阻斷」問題已進入主線：

1. `vault/mcp.py` 的 JSON schema 片段使用 JavaScript `false`，導致 Python import 直接失敗，整個 MCP 與相關測試無法載入。
2. `VaultDB.update_knowledge()` 的欄位白名單漏掉 `content_aaak`，使內容更新時 AAAK claim 未同步更新，進一步造成 semantic claim vectors 仍以舊 claims 重建，影響記憶召回正確性與 stale vector 清理。

本提交已修復以上兩點。

---

## 2. 評分摘要

| 維度 | 評分 | 狀態 | 說明 |
|---|---:|---|---|
| 功能完整性 | 4.2 / 5 | ⚠️ 可用但需收斂 | MCP schema 與 DB update 白名單曾阻斷測試；修復後主流程恢復。 |
| 記憶召回 | 4.1 / 5 | ⚠️ 架構佳但需量化 | semantic node/claim vectors、Document Map、rerank 有明顯提升；需補 recall@k/MRR 基準與 stale index CI。 |
| 速率與性能 | 3.9 / 5 | ⚠️ 功能增加帶來風險 | Query expansion + vector + graph expand + rerank 可能造成多倍放大；需要預算、timeout、rate limit。 |
| 代碼完整性 | 4.0 / 5 | ⚠️ 邊界需補測 | 大多數更新方向正確，但 schema literal、欄位白名單遺漏顯示仍缺 import-time 與 update path 測試。 |
| 安全 | 4.1 / 5 | ✅ 基線良好 | SQL 值參數化、隱私 gate、compact MCP 輸出有進展；仍需速率限制、最小披露與模型路徑防護。 |
| 可維護性 | 3.8 / 5 | ⚠️ 搜尋模組偏胖 | `vault/search.py` 同時承擔 keyword/vector/rerank/rewrite/cache/graph，建議拆分策略模組。 |

---

## 3. 已修復的阻斷錯誤

### F-001: MCP tools schema 使用 `false` 造成 import-time `NameError`

- **嚴重度**: P1 / 阻斷
- **影響**: `from vault.mcp import ...` 直接失敗；MCP 工具列表與 MCP memory/map 測試無法收集。
- **根因**: Python dict 內應使用 `False`，不是 JSON/JavaScript 的 `false`。
- **修復**: 將 schema default 改為 Python boolean。
- **預防方向**:
  - 增加 `python -m py_compile vault/*.py` 或 import smoke test 至 CI。
  - 所有 MCP tool schema 先以 Python dict 定義，再以 `json.dumps()` 驗證可序列化。

### F-002: `update_knowledge()` 白名單漏掉 `content_aaak`

- **嚴重度**: P1 / 記憶召回完整性
- **影響**: 更新 raw content 時，AAAK claim 可能沒有寫入；`rebuild_semantic_index()` 會重建過期 claim vectors，導致舊主張污染 recall。
- **根因**: SQL 注入修復後使用欄位白名單，但未納入既有可更新欄位 `content_aaak`。
- **修復**: 將 `content_aaak` 加入安全更新欄位。
- **預防方向**:
  - DB schema 欄位、add/update 方法、測試 fixture 應共用常數或至少有 parity 測試。
  - 對每個可更新內容欄位建立 regression test：`content_raw`, `content_aaak`, `summary`, `tags`, `trust`。

---

## 4. 功能審查

### 強項

- MCP 工具面已涵蓋搜尋、記憶提案/提升、Document Map、range read、remote map read 等，功能面比上一輪完整。
- Document Map 將章節節點與 claims 拆分，支援固定 citation，是可審計 RAG 的正確方向。
- Memory curator 有 metadata/quality/duplicate/privacy gates，可降低低價值、重複與敏感記憶進入長期庫的機率。
- 搜尋層支援 keyword/vector/hybrid/semantic/rerank，具備自動降級能力。

### 主要風險與優化方向

1. **功能開關過多但缺少 profile**  
   建議提供 `fast`, `balanced`, `quality`, `private` 四種 profile，集中控制 query expansion、LLM rewrite、vector、rerank、graph expand、compact output。

2. **MCP 輸出契約需穩定化**  
   建議為每個 MCP tool 增加 snapshot contract test，至少驗證成功 payload、錯誤 payload、`next_action`、compact/full 欄位。

3. **remote Supabase read 與 local source-of-truth 邊界需更明確**  
   建議在 remote tools payload 中永遠回傳 `source="remote_readonly"`、同步時間與 content hash 驗證結果。

---

## 5. 記憶召回審查

### 強項

- Semantic index 同時索引 node 與 claim，對「找段落」與「找原子主張」都有幫助。
- Document Map line range 讓召回結果可以直接落到引用範圍，而不是只回傳整篇文件。
- Memory candidate quality gate 已開始管控 generic title、missing tags、low context 等低召回性問題。

### 主要風險與優化方向

1. **stale claim vectors 是高風險召回污染源**  
   本輪已修復 `content_aaak` 無法更新的根因。後續仍建議在 CI 加入「更新 raw + aaak 後重建 index，不得出現舊 claim」的固定測試。

2. **缺少召回品質基準**  
   建議把 `benchmarks/search_qa/*.json` 接到 CI 的 nightly job，至少追蹤：
   - Recall@1 / Recall@3 / Recall@5
   - MRR
   - citation hit rate
   - stale-answer rate
   - zh-Hant / zh-CN / English 分語言結果

3. **Rerank 分數校準需更透明**  
   `LightweightReranker` 將 freshness/trust/graph bonus 與 lexical hit 合併，可能讓新但弱相關文件壓過強相關文件。建議回傳 `_score_breakdown`（可 debug 模式開啟）。

4. **記憶提升策略可更保守**  
   `promote_if_safe` 要求 gates 全 pass 是好的，但 duplicate/quality 目前多為 warn；建議引入「同主題合併建議」而非只提示 warn。

---

## 6. 速率與性能審查

### 風險

- 單次 search 可能觸發 query expansion、多路檢索、vector encode、semantic scan、graph expansion、rerank，最壞情況成本被放大數倍。
- Cross-encoder rerank 若安裝可用，首次載入與推理成本高；目前雖有 cache lock，但仍需 timeout 與 batch size 上限。
- MCP/CLI 缺少全局 rate limit 與 operation budget。若被 Agent loop 誤用，容易產生本地 DoS。

### 優化方向

1. 增加 `SearchBudget`：限制 max_expanded_queries、max_vector_candidates、max_graph_nodes、max_rerank_docs、deadline_ms。
2. MCP tool 層加入 token bucket 或 per-process sliding window；本地 CLI 可預設寬鬆，server mode 預設嚴格。
3. 為 semantic scan 增加更清楚的 `MAX_SCAN_ROWS` telemetry，超過時回傳 degraded mode。
4. Cross-encoder 預設只 rerank top 20 或 top 50，並允許 `VAULT_DISABLE_CROSS_ENCODER=1`。
5. Cache metrics 應輸出到 health/report：query cache hit rate、embedding cache hit rate、rerank availability、avg latency。

---

## 7. 代碼完整性審查

### 已改善

- `update_knowledge()` 對欄位名使用白名單，修復了動態 SQL 欄位注入風險的主要來源。
- Search limit/offset 有上限保護。
- Semantic provider 有 `require_semantic` / `allow_hash` guard，能防止 hash test provider 誤進 production semantic flow。

### 仍需改善

1. **`_SAFE_COLUMNS` 過寬且混入多表欄位**  
   建議拆成 `KNOWLEDGE_UPDATE_COLUMNS`、`CLAIM_UPDATE_COLUMNS`、`NODE_UPDATE_COLUMNS` 等；目前把 claim/node 欄位放進 knowledge update 白名單，雖不一定可被利用，但會讓錯誤靜默忽略或 SQL runtime error 的機率升高。

2. **Search 模組職責過多**  
   建議拆分：
   - `query_expansion.py`
   - `rerank.py`
   - `hybrid.py`
   - `search_budget.py`
   - `snippet.py`

3. **broad `except Exception` 過多**  
   對 optional dependency 可接受，但需要 debug log 或 health degradation record，否則 production 很難知道是「不可用」還是「壞掉」。

4. **缺少 py_compile / import smoke gate**  
   本次 `false` 問題可由極低成本檢查提前擋下。

---

## 8. 安全審查

### 已具備的安全基線

- SQL 值大多使用參數化。
- 欄位名白名單降低動態 SQL 風險。
- Privacy scan/redaction gate 已進入 memory candidate flow。
- MCP search compact output 可降低過度披露風險。
- Read range 有行數限制與 citation/hash 驗證概念。

### 安全優先修復方向

1. **P2: MCP/Agent loop 速率限制**  
   在 tool dispatch 層加入 per-tool limit。對 `vault_search`, `vault_memory_propose`, `vault_map_build`, `vault_remote_read_range` 設不同成本權重。

2. **P2: Cross-encoder/local model path 防護**  
   `VAULT_CROSS_ENCODER_PATH` 應要求 resolve 後在 allowlisted model directory，並限制副檔名/大小；避免未來被服務化後形成任意本地模型載入面。

3. **P3: 最小披露預設**  
   MCP search 建議預設只回傳 `id,title,summary,best_claim,citation,_score,_mode`；完整 `content_raw` 只能透過 range read 或明確 `fields` 取得。

4. **P3: 日誌遮蔽**  
   將 `redact_secrets()` 套用到錯誤與 debug log，尤其是 LLM/Supabase/remote sync。

5. **P3: Remote content hash 驗證失敗策略**  
   若 remote content hash 與 node hash 不一致，應回傳 hard warning 或拒絕 citation，而不是只標記 degraded。

---

## 9. 建議 Roadmap

### 立即（1-2 天）

- 加入 `python -m py_compile vault/*.py scripts/*.py` 至 CI。
- 為 MCP `TOOLS` schema 加 json-serializable smoke test。
- 補 `update_knowledge(content_aaak=...)` regression test。
- 將 `_SAFE_COLUMNS` 拆成 knowledge 專用白名單。

### 短期（1-2 週）

- 實作 `SearchBudget` 並接入所有 search mode。
- 建立 search QA benchmark CI/nightly，輸出 recall@k/MRR/citation hit rate。
- MCP tool dispatch 加 rate limit / cost budget。
- 搜尋結果預設最小披露，完整內容走 `vault_read_range`。

### 中期（1 個月）

- 拆分 `vault/search.py`，降低單檔複雜度。
- 加入 observability：latency histogram、cache hit、degraded reasons。
- 增加 memory merge workflow：duplicate warn 時提供 merge candidate，而非只阻止或警告。
- 對 remote sync 加 end-to-end hash/citation verification tests。

---

## 10. 本次結論

本次更新後，Vault-for-LLM 的架構能力明顯變強，尤其在「可引用記憶」、「claim-level semantic recall」、「memory gate」上已經具備長期演進價值。但大幅更新也帶來典型整合風險：小型 schema literal 錯誤可阻斷 import；欄位白名單遺漏可直接污染 semantic recall。

本輪已修復兩個已確認阻斷問題。下一步最應優先投入的是：**CI import/schema gate、召回品質基準、SearchBudget/rate limit、最小披露 MCP 契約**。
