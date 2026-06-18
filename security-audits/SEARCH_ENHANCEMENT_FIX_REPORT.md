# Vault-for-LLM 搜尋增強分支 - 紅隊審查修復報告

**版本**: 0.6.0  
**分支**: feat/search-enhancement  
**日期**: 2025

---

## 修復摘要

本報告詳細說明了針對 Vault-for-LLM 搜尋模組的紅隊審查問題的修復情況。共修復了 6 個主要問題，並添加了全面的單元測試來確保品質。

---

## 🎯 P0 修復（必須修復）

### 1. 修復 `_tokenize` 方法詞序問題

**問題描述**:
- 先提取英文再提取中文，導致中英文混合查詢的詞序顛倒
- 例如 "什麼是 AI" 會被分詞為 `['AI', '什麼是']` 而非 `['什麼是', 'AI']`

**影響範圍**:
- `vault/search.py` 中的 `VaultSearch._tokenize()` 靜態方法
- `LightweightReranker._extract_terms()` 靜態方法（同樣問題）

**修復方式**:
- 重寫分詞邏輯，使用 `re.finditer()` 同時提取中英文 token
- 每個 token 記錄其在原始文本中的起始位置
- 按位置排序後返回結果，保持原始詞序
- 中文片段仍然支持滑動窗口切分（保留原義 + 雙字詞）

**修改的檔案**:
- `vault/search.py` - `VaultSearch._tokenize()` 方法
- `vault/search.py` - `LightweightReranker._extract_terms()` 方法

**測試**:
- 添加了 `TestTokenizeWordOrder` 測試類別，包含 5 個測試用例
- 測試中英文混合、英文在前中文在後、純中文、純英文等場景
- 同時驗證 `LightweightReranker._extract_terms` 也保持正確詞序

---

### 2. 提升測試覆蓋率（重點功能）

**問題描述**:
- 核心新功能缺乏足夠的單元測試覆蓋

**修復方式**:
新增了 6 個測試類別，共 28 個測試用例：

| 測試類別 | 測試數量 | 覆蓋功能 |
|---------|---------|---------|
| `TestQueryExpansion` | 8 | 查詢擴展（同義詞、問句變換、縮寫擴展、關鍵詞提取） |
| `TestLightweightReranker` | 6 | 輕量級重排序器（標題匹配、詞頻飽和、位置權重、多詞獎勵） |
| `TestInfoMethod` | 3 | info() 方法及配置反映 |
| `TestInvalidMode` | 3 | 無效 mode 參數校驗 |
| `TestTokenizeWordOrder` | 5 | 分詞詞序正確性 |
| `TestCrossEncoderCache` | 3 | Cross-Encoder 快取機制 |

**測試結果**:
- 總測試數從 55 增加到 83
- 所有測試全部通過
- 核心新功能的測試覆蓋率顯著提升

---

## 🎯 P1 修復（強烈建議修復）

### 3. 增加簡體中文支援

**問題描述**:
- 問句模式、停用詞、同義詞僅支援繁體中文
- 簡體中文用戶的查詢無法正確匹配問句模式

**影響範圍**:
- `_expand_query()` 方法中的問句模式匹配
- 同義詞詞典 `_SYNONYM_MAP`
- 停用詞列表

**修復方式**:
1. **繁簡轉換輔助方法**: 添加了 `_normalize_chinese()` 靜態方法，將繁體中文轉換為簡體中文，用於模式匹配
2. **擴展同義詞詞典**: 在 `_SYNONYM_MAP` 中添加了簡體中文的同義詞條目（如「搜索」對應「搜尋」）
3. **更新問句模式匹配**: 使用標準化後的文本進行匹配，同時支援繁簡體
4. **擴展停用詞列表**: 添加了簡體中文停用詞（如「什么」、「怎么」、「这个」等）
5. **縮寫擴展**: 同時對原始文本和標準化文本進行縮寫匹配

**修改的檔案**:
- `vault/search.py` - `_normalize_chinese()` 新方法
- `vault/search.py` - `_SYNONYM_MAP` 詞典擴展
- `vault/search.py` - `_expand_query()` 方法更新

**測試**:
- `test_expand_query_simplified_chinese_what_is` - 驗證簡體中文「什么是」模式匹配
- `test_expand_query_synonyms` - 驗證同義詞雙向擴展

---

### 4. 添加 Cross-Encoder 線程安全機制

**問題描述**:
- `CrossEncoderReranker` 類的類級快取（`_cached_model`、`_cached_tokenizer`、`_backend`）無鎖保護
- 多執行緒環境下可能存在競態條件

**修復方式**:
1. **添加快取鎖**: 添加 `_cache_lock = threading.Lock()` 類變數
2. **雙重檢查鎖定模式**: 在 `_try_init()` 方法中使用雙重檢查鎖定（Double-Checked Locking）模式，兼顧效能與線程安全
3. **添加 `clear_cache()` 靜態方法**: 提供手動清理快取的能力，便於資源管理和測試
4. **更新文檔**: 在類 docstring 中添加了線程安全性說明

**修改的檔案**:
- `vault/search.py` - `CrossEncoderReranker` 類別

**測試**:
- `test_clear_cache_exists` - 驗證 `clear_cache()` 方法存在
- `test_clear_cache_no_error` - 驗證清除快取不會引發異常
- `test_cache_lock_exists` - 驗證快取鎖存在

---

### 5. 添加無效模式參數校驗

**問題描述**:
- 無效的 `mode` 參數會靜默降級為 auto 模式，用戶無法察覺
- 可能導致用戶困惑和調試困難

**修復方式**:
- 在 `search()` 方法開始處添加 mode 參數驗證
- 無效模式時拋出 `ValueError`，錯誤消息包含有效模式列表
- 有效模式: `auto`, `keyword`, `vector`, `semantic`, `hybrid`

**修改的檔案**:
- `vault/search.py` - `search()` 方法

**測試**:
- `test_invalid_mode_raises_value_error` - 驗證無效模式拋出異常
- `test_error_message_contains_valid_modes` - 驗證錯誤消息包含有效模式
- `test_valid_modes_do_not_raise` - 驗證所有有效模式正常工作

**向後兼容性**:
- 這是一個 **破壞性變更** - 之前無效模式會靜默降級，現在會拋出異常
- 但這是預期的行為改變，因為靜默降級被認為是一個 bug

---

### 6. 優化查詢擴展分數衰減機制

**問題描述**:
- 所有擴展查詢使用統一的 0.9 指數衰減
- 高質量擴展（如同義詞替換）被過度抑制
- 低質量擴展（如關鍵詞提取）衰減不足

**修復方式**:
1. **按類型設置衰減率**:
   - 同義詞替換: `0.95`（衰減最小，最可靠）
   - 問句變換: `0.85`（中等衰減）
   - 縮寫/全稱擴展: `0.90`（中等偏上）
   - 關鍵詞提取: `0.75`（衰減最大，最不可靠）

2. **可配置衰減參數**:
   - `query_expansion_synonym_decay`
   - `query_expansion_question_decay`
   - `query_expansion_abbr_decay`
   - `query_expansion_keyword_decay`

3. **改進擴展結果結構**:
   - `_expand_query()` 現在返回 `list[tuple[str, float]]`，每項包含查詢文本和對應權重
   - 按權重降序排列，確保最高質量的擴展優先被使用

4. **分數計算優化**:
   - 直接使用擴展查詢的權重乘以原始分數，代替之前的指數衰減
   - 同一查詢有多種擴展類型時，保留最高權重

**修改的檔案**:
- `vault/search.py` - `VaultSearch.__init__()` 添加衰減參數
- `vault/search.py` - `_expand_query()` 方法重寫
- `vault/search.py` - `search()` 方法更新衰減計算邏輯

**測試**:
- `test_expand_query_decay_weights` - 驗證不同擴展類型有不同權重
- `test_expansion_count_limit` - 驗證擴展數量限制
- `test_expand_query_disabled` - 驗證關閉擴展時行為正確

---

## 品質驗證

### 測試結果
- 所有 83 個搜尋相關測試全部通過
- 無迴歸問題
- 新增測試覆蓋所有修復點

### 向後兼容性
- ✅ `_tokenize()` 返回格式不變（list[str]）
- ✅ 大部分 API 保持不變
- ⚠️ `_expand_query()` 返回格式從 `list[str]` 改為 `list[tuple[str, float]]` - 這是私有方法，僅內部使用
- ⚠️ 無效 mode 參數現在會拋出 `ValueError` 而非靜默降級 - 這是預期的行為修正

### 代碼風格
- 與現有代碼風格保持一致
- 適當添加了註解說明關鍵邏輯
- 所有公開方法都有完整的 docstring

---

## 檔案變更清單

| 檔案 | 變更類型 | 說明 |
|------|---------|------|
| `vault/search.py` | 修改 | 主要修復檔案，包含所有 6 項修復 |
| `tests/test_search_extended.py` | 修改 | 添加 28 個新測試用例 |

---

## 建議後續工作

1. **混合搜尋動態權重測試**: 添加更多針對混合搜尋動態權重調整的測試（需要嵌入模型支援）
2. **交叉驗證加分測試**: 添加針對 hybrid search 交叉驗證加分邏輯的專門測試
3. **壓力測試**: 對 Cross-Encoder 快取進行並發壓力測試
4. **效能基準**: 量化查詢擴展對搜尋準確率的影響
