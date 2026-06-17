# Changelog

## [0.6.19] — 2026-06-17

### Fixed
- **快取鍵值衝突風險**：將快取鍵生成方式從「字串拼接 + 分隔符」改為「JSON 序列化 + MD5 哈希」，徹底避免因查詢內容或參數值包含分隔符導致的快取鍵衝突問題。`sort_keys=True` 確保參數順序不影響鍵值一致性。

### Modules Affected
- `vault/search.py`：`VaultSearch._get_cache_key()`

### Impact
- 向後相容：快取鍵生成方式變更不影響外部 API，僅影響內部快取。
- 升級後舊快取會自動失效（因為鍵值格式不同），屬預期行為。

---

## [0.6.18] — 2026-06-17

### Added
- **安全模式**（`_safe_mode`）：可選的安全模式，捕獲搜尋過程中的非參數異常並返回空結果，避免內部錯誤信息洩露。預設關閉，可透過 `_safe_mode` 屬性手動開啟。

### Changed
- `search()` 方法重構為外層入口 + `_do_search()` 內部實現，安全模式邏輯與業務邏輯分離，結構更清晰。

### Modules Affected
- `vault/search.py`：`VaultSearch.search()`、`VaultSearch._do_search()`

### Impact
- 向後相容：安全模式預設關閉，不影響既有調用。
- 開啟安全模式後，運行時異常會被吞掉返回空結果，可能不利於除錯；建議僅在生產環境對外暴露時使用。
- 參數驗證錯誤（ValueError、TypeError）仍然會正常拋出，便於開發者發現調用問題。

---

## [0.6.17] — 2026-06-17

### Added
- **搜尋結果欄位過濾功能**（`fields` 參數）：允許調用者指定返回的欄位列表，僅返回所需欄位，顯著減少數據傳輸量。支援所有內部欄位（`_score`、`_snippet` 等）。

### Changed
- 快取鍵納入 `fields` 參數，確保不同欄位組合的查詢不會相互汙染快取。

### Modules Affected
- `vault/search.py`：`VaultSearch.search()`、快取相關方法

### Impact
- 向後相容：`fields` 預設為 `None`，返回所有欄位，不改變原有行為。

---

## [0.6.16] — 2026-06-17

### Fixed
- **XSS 漏洞修復**：`_generate_snippet` 方法在內容中插入高亮標籤前，先對文本內容進行 HTML 實體轉義，防止惡意內容透過搜尋結果片段進行 XSS 攻擊。
- **highlight_tag 白名單機制**：高亮標籤參數從自由輸入改為白名單驗證，僅允許 `em`、`strong`、`mark`、`span`、`b`、`i`、`u`、`s`、`code`、`kbd`、`var` 等安全內聯標籤，非法標籤自動降級為 `em`。

### Added
- **深分頁性能保護**（`MAX_SEARCH_WINDOW = 2000`）：限制 `limit + offset` 總量不超過 2000，防止深分頁查詢導致的性能問題。
- **快取鍵分隔符優化**：從 `|` 改為 `\x1F`（ASCII 單元分隔符），避免查詢內容包含 `|` 時導致的快取鍵衝突。

### Modules Affected
- `vault/search.py`：`_generate_snippet()`、`_get_cache_key()`、`search()` 分頁邏輯

### Impact
- 安全性提升：修復了潛在的 XSS 注入風險。
- 向後相容：`highlight_tag` 預設為 `em`（在白名單內），不影響正常使用。
- 深分頁限制可能影響超大偏移量的查詢場景，建議改用游標分頁或縮小查詢範圍。

---

## [0.6.15] — 2026-06-17

### Added
- **搜尋分頁支援**（`offset` 參數）：`search()` 方法新增 `offset` 參數，與 `limit` 配合實現分頁查詢。
  - 最大偏移量 `MAX_OFFSET = 9999`，防止過大的偏移值。
  - 負值 offset 自動修正為 0。
  - 快取鍵納入 `offset` 參數，確保分頁快取正確性。
  - 內部使用「搜尋階段擴大 limit + 最後切片」的策略確保分頁正確性。

### Modules Affected
- `vault/search.py`：`search()` 方法、`_get_cache_key()` 方法

### Impact
- 向後相容：`offset` 預設為 0，不改變原有行為。
- 分頁功能可能略微增加內部查詢的數據量（需要多取 offset 筆進行切片），但對最終返回結果無影響。

---

## [0.6.14] — 2026-06-17

### Added
- **圖譜遍歷權限過濾前移**：將 category/layer 權限過濾從 BFS 完成後提前到 BFS 遍歷過程中，不符合權限的節點直接跳過，不進入隊列。
- **側信道風險緩解**：透過提前過濾減少無效節點的處理，同時降低透過查詢時間差異推斷隱藏節點存在的側信道攻擊風險。

### Modules Affected
- `vault/search.py`：`_expand_with_graph()` 方法

### Impact
- 性能優化：大圖譜下的權限過濾性能提升，減少無效遍歷。
- 安全性提升：緩解圖譜側信道洩露風險。
- 向後相容：功能邏輯不變，僅實現優化。

---

## [0.6.13] — 2026-06-17

### Added
- **搜尋片段關鍵詞高亮**：`_generate_snippet` 新增 `highlight` 參數，支援對匹配的查詢詞進行 HTML 標籤包裹。
- `search()` 方法新增 `highlight_snippet` 參數，與 `include_snippet` 配合使用，預設關閉。

### Modules Affected
- `vault/search.py`：`_generate_snippet()` 方法、`search()` 方法

### Impact
- 向後相容：`highlight_snippet` 預設為 `False`，不改變原有行為。
- 高亮功能使用 `<em>` 標籤（可配置），前端可透過 CSS 定制高亮樣式。

---

## [0.6.12] — 2026-06-17

### Added
- **可配置查詢結果快取**：新增 LRU 快取機制，快取大小和 TTL 可配置。
  - `set_cache_config(enable: bool, size: int = 128, ttl: int = 60)` 方法配置快取。
  - 快取鍵包含所有查詢參數（query、mode、limit、offset、min_trust、layer、category、graph_expand、use_rerank、compact、min_score、use_query_expansion、use_llm_rewrite、normalize_scores、include_snippet、highlight_snippet、fields）。
  - 快取命中率統計：`_cache_hits`、`_cache_misses` 屬性。
  - 快取清理：`clear_cache()` 方法。

### Modules Affected
- `vault/search.py`：快取相關方法、`search()` 方法

### Impact
- 向後相容：快取預設關閉，不改變原有行為。
- 開啟快取後可顯著提升重複查詢的響應速度，但會消耗額外記憶體。
- 快取僅在單個 `VaultSearch` 實例內有效，進程重啟後丟失。

---

## [0.6.11] — 2026-06-17

### Added
- **搜尋結果片段生成功能**：`_generate_snippet()` 方法，從文檔內容中提取與查詢相關的片段。
- `search()` 方法新增 `include_snippet` 參數，開啟後在結果中附加 `_snippet` 欄位。
  - 片段長度約 160 字元，自動定位到查詢詞出現的位置。
  - 優先使用 `content_aaak`，其次使用 `content_raw`。

### Modules Affected
- `vault/search.py`：新增 `_generate_snippet()` 方法、`search()` 方法

### Impact
- 向後相容：`include_snippet` 預設為 `False`，不改變原有行為。
- 片段生成會帶來少量額外計算開銷，僅在需要時開啟。

---

## [0.6.10] — 2026-06-17

### Added
- **分數標準化選項**（`normalize_scores`）：`search()` 方法新增 `normalize_scores` 參數，開啟後將分數歸一化到 [0, 1] 區間，方便不同搜尋模式的分數比較。
  - 關鍵詞搜尋：透過 BM25 最高分歸一化。
  - 向量搜尋：透過最大餘弦相似度歸一化。
  - 混合搜尋：根據權重置換算後歸一化。

### Modules Affected
- `vault/search.py`：`_normalize_scores()` 方法、`search()` 方法

### Impact
- 向後相容：`normalize_scores` 預設為 `False`，不改變原有行為。
- 標準化後的分數僅用於相對比較，不代表絕對相關性。

---

## [0.6.9] — 2026-06-17

### Added
- **代碼質量優化**：統一底層搜尋方法的空查詢防護，移除 `search()` 主方法中重複的空查詢檢查。
- **邊界防護增強**：為 `search_vector`、`search_semantic`、`search_hybrid` 等底層方法統一添加空查詢防護，確保在各種調用路徑下的健壯性。
- **清理重複代碼**：移除 `search()` 方法中重複的第二處空查詢檢查。

### Modules Affected
- `vault/search.py`：多個底層搜尋方法

### Impact
- 代碼可維護性提升，防禦更為嚴密。
- 向後相容：功能邏輯不變。

---

## [0.6.8] — 2026-06-17

### Fixed
- **P2: `_init_vec_table` SQL 注入修復**：修復向量表初始化時的參數拼接問題，改用參數化查詢或正確的標識符轉義。
- **P2: `search_keyword` LIKE 注入修復**：修復 LIKE 查詢中使用者輸入未正確轉義的問題，對 `%`、`_`、`\` 等特殊字元進行轉義。
- **P3: None 查詢空值檢查**：統一所有底層方法的 None/空字元串檢查，防止空查詢導致的異常。
- **P3: min_score 範圍驗證**：添加 min_score 參數的邊界驗證，防止無效的分數閾值。
- **P3: 圖譜側信道洩露緩解**：優化圖譜擴展的權限檢查時機，減少側信道資訊洩露。

### Added
- `_escape_like_pattern()` 工具方法：用於安全轉義 LIKE 模式中的特殊字元。
- `db.py` 中統一的輸入驗證機制。

### Modules Affected
- `vault/db.py`：`_init_vec_table()`、`search_keyword()`、`search_skills()`
- `vault/search.py`：參數驗證、圖譜擴展

### Impact
- 安全性顯著提升：修復了兩個 P2 級 SQL 注入漏洞。
- 向後相容：修復不改變正常使用行為，僅阻斷惡意輸入。

---

## [0.6.7] — 2026-06-17

### Fixed
- **db.py 初始化錯誤信息脫敏**：資料庫初始化失敗時，錯誤信息不再包含敏感的路徑或配置細節。
- **cross_encoder 格式驗證**：增強 Cross-Encoder 輸入的格式驗證，防止異常格式導致的崩潰。
- **向量搜尋維度驗證**：添加向量維度一致性驗證，防止因維度不匹配導致的運行時錯誤。
- **LIKE 萬用字元轉義**：全面檢查並修復所有 LIKE 查詢的注入風險。
- **向量搜尋側信道緩解**：向量搜尋第一步放大查詢量（5 倍），緩解透過查詢時間差異推斷向量存在的側信道風險。

### Added
- 圖遍歷優化：BFS 過程中提前剪枝無效節點，提升大圖譜下的查詢效率。
- LLM 注入防護升級：新增更多注入模式的檢測規則。

### Modules Affected
- `vault/db.py`：錯誤處理、向量搜尋、LIKE 查詢
- `vault/search.py`：Cross-Encoder 驗證、LLM 注入檢測、圖譜遍歷

### Impact
- 安全性提升：多項 P3 級安全問題修復。
- 性能優化：大圖譜查詢效率提升。
- 向後相容。

---

## [0.6.6] — 2026-06-17

### Added
- **FTS5 token 長度限制**：限制 FTS5 分詞的最大 token 長度，防止異常長詞導致的性能問題或崩潰。
- **錯誤信息脫敏（P3 防禦增強）**：部分對外介面的錯誤信息進行脫敏處理，避免洩露內部實現細節。

### Modules Affected
- `vault/db.py`：FTS5 搜尋相關方法

### Impact
- 健壯性提升：對異常輸入的容忍度增強。
- 向後相容。

---

## [0.6.5] — 2026-06-17

### Added
- **子搜尋方法 limit 上限保護**：為所有底層搜尋方法（`search_vector`、`search_keyword`、`search_semantic` 等）統一添加 limit 上限保護，防止過大的 limit 值導致性能問題或記憶體溢出。
- **get_neighbors 深度上限**：`get_neighbors` 方法新增 `max_depth` 參數，預設有合理上限，防止無限遞迴或遍歷過深。

### Modules Affected
- `vault/db.py`：`get_neighbors()`、多個搜尋方法
- `vault/search.py`：參數傳遞與驗證

### Impact
- 安全性提升：防止惡意構造的深層次圖譜查詢。
- 向後相容：上限值設置較大，不影響正常使用。

---

## [0.6.4] — 2026-06-17

### Fixed
- **SQL 級權限過濾**：將 category 和 layer 過濾邏輯前移到 SQL 查詢層面，而非查詢後再過濾，從根本上杜絕越權存取。
- **空查詢處理統一**：統一所有搜尋入口的空查詢 / None 查詢處理邏輯，確保一致返回空列表。
- **min_score 一致性**：修復不同搜尋模式下 min_score 語義不一致的問題，統一為「過濾低於該分數的結果」。

### Modules Affected
- `vault/db.py`：所有搜尋方法的 SQL 查詢
- `vault/search.py`：`search()` 方法、min_score 處理邏輯

### Impact
- 安全性提升：SQL 層過濾確保資料庫層面就進行權限控制。
- 正確性提升：min_score 行為在所有模式下一致。
- 向後相容。

---

## [0.6.3] — 2026-06-17

### Fixed
- **XML 注入漏洞**：修復在處理 XML 格式內容時的注入風險，確保所有輸入內容正確轉義。
- **category 過濾修復**：修復 category 參數為空列表或 None 時的邊界情況處理，避免誤刪除所有結果或不過濾。
- **limit 保護增強**：進一步強化 limit 參數的邊界檢查，負值或零值自動修正為預設值。
- **同義詞功能修復**：修復查詢擴展中同義詞替換的邊界 bug，確保替換邏輯正確。

### Modules Affected
- `vault/search.py`：XML 處理、category 過濾、limit 驗證、查詢擴展

### Impact
- 安全性提升：修復 XML 注入漏洞。
- 正確性提升：多項邊界情況修復。
- 向後相容。

---

## [0.6.2] — 2026-06-17

### Fixed
- **圖譜擴展權限漏洞**：修復 `graph_expand` 功能可能繞過 category/layer 權限限制的問題。現在圖譜擴展的每個節點都會經過權限驗證，僅保留有權存取的節點。
- **LLM 注入防護**：新增 LLM 查詢改寫功能的注入檢測機制，分為 override、impersonation、command、obfuscation、boundary 五大類，防止惡意查詢透過 LLM 改寫繞過安全限制。
- **查詢長度限制**：新增查詢長度上限（`MAX_INPUT_LEN = 2000`），防止過長的查詢導致性能問題或濫用。

### Added
- `_is_llm_injection_attempt()` 方法：檢測潛在的 LLM 注入攻擊。
- `_tokenize()` 方法中的長度限制檢查。

### Modules Affected
- `vault/search.py`：圖譜擴展、LLM 查詢改寫、分詞器

### Impact
- 安全性顯著提升：修復了 P1 級的越權漏洞和 LLM 注入風險。
- 向後相容：預設開啟安全防護，不改變正常使用行為。

---

## [0.6.1] — 2026-06-16

### Added
- **測試覆蓋率提升**：搜尋相關測試從 265 個增加到 378 個（+113），覆蓋率從 78% 提升到 81%。
- **Search QA 硬負樣本指標**：新增硬負樣本（hard-negative）的評估指標，更準確地衡量搜尋排序質量。
- **CI 修復**：修復私密測試文件的密鑰掃描排除規則，移除 numpy 測試依賴。
- **numpy 條件式測試**：numpy 相關測試在 numpy 不可用時自動跳過。
- **Lock isinstance 修復**：修復 Lock 類型檢查的兼容性問題。

### Changed
- README 更新：補充 PR27 記憶工作流的相關文件。

### Modules Affected
- `tests/`：大量新增測試用例
- `benchmarks/search_benchmark.py`：硬負樣本指標
- `.github/workflows/`：CI 配置修復

### Impact
- 程式碼質量提升：更全面的測試覆蓋。
- CI 穩定性提升：修復多個 CI 問題。
- 向後相容：無功能變更。

---

## [0.6.0] — 2026-06-16

### Added
- **Cross-Encoder 重排序**（P1）：支援 Cross-Encoder 模型進行精確的相關性評分，可選依賴 sentence-transformers 或 onnxruntime，自動偵測可用性，模型快取避免重複載入。
- **基準測試框架**（P1）：新增 `benchmarks/search_benchmark.py` 基準測試工具，可比較不同搜尋策略的效果（關鍵詞/混合/語義、有無 rerank、有無查詢擴展），指標包含精確率、召回率、NDCG、查詢延遲。
- **完善 info() 方法**（P1）：`VaultSearch.info()` 現在返回完整的能力分級資訊與配置參數，包含基礎層、進階層、高階層、旗艦層的可用性功能。
- **LLM 查詢改寫**（P2）：支援透過 LLM 將用戶查詢改寫為更適合檢索的形式，可選依賴 LLM provider，受 `enable_llm_enhancement` 控制，整合進 `search()` 方法。
- **rerank_strategy 參數**：支援 `auto`、`lightweight`、`cross_encoder`、`none` 四種策略，可靈活配置重排序方式。
- **cross_encoder_model 參數**：可指定 Cross-Encoder 模型名稱。
- **use_llm_rewrite 參數**：搜尋時可選擇是否使用 LLM 查詢改寫。

### Changed
- `_rerank` 靜態方法保留向後兼容，實例級 rerank 邏輯透過 `_rerank_with_strategy` 方法實現，支援策略選擇。
- `has_cross_encoder` 屬性現在會實際偵測 Cross-Encoder 模型的可用性，而非僅傳回 False。
- `has_llm` 屬性與 LLM 查詢改寫功能整合，提供更準確的能力偵測。

### Verification
- 所有原有測試通過（1317+）。
- Cross-Encoder 功能在有套件時自動啟用，無套件時優雅降級。
- 基準測試腳本可正常執行並輸出比較結果。
- LLM 查詢改寫功能在有可用 LLM provider 時正常工作。

---

## [0.5.0] — 2026-06-12

### Added
- Add deterministic Search QA baseline fixtures and metrics to measure retrieval quality and latency before retrieval changes.
- Add SQLite FTS5/BM25 keyword search with automatic fallback when FTS5 is unavailable or CJK matching needs the legacy LIKE path.
- Add semantic index plumbing with `semantic_vectors` rows for knowledge and claim-level citation-aware vectors.
- Add embedding provider metadata and fail-closed provider validation so production-like semantic paths require a real semantic provider.
- Add in-memory and persistent embedding caches keyed by provider identity, vector dimension, cache version, and text hash.
- Add `vault semantic rebuild`, `warm`, `smoke`, `cache-stats`, and `cache-prune` operator workflows.
- Add importable semantic lifecycle hooks plus `vault semantic startup` and bounded `daemon` commands for service integration.
- Add `docs/semantic_search.md`, README semantic workflow guidance in all README variants, and a README documented command smoke CI job.

### Changed
- Startup and daemon semantic workflows use the persistent embedding cache by default; pass `--no-persist-cache` for cold runs.
- The semantic daemon is bounded by default with `--repeat 1`; `--repeat 0` is reserved for supervisor-managed forever mode.
- Semantic test doubles are explicit: deterministic hash embeddings require `--allow-hash` and are documented as CI/local smoke only.

### Verification
- Full local test suite: `138 passed`.
- README documented command smoke: init/add/compile/search, Search QA, semantic smoke, and cache-stats commands pass in a clean temp project.
- Public-boundary gate and GitHub Release Readiness CI pass on `main`.

---

## [0.4.3] — 2026-05-24

### Added
- Add source-checkout repository hygiene tools for public release workflows:
