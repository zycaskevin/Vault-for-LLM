# memory-lancedb-pro 插件鐵律

## 已安裝狀態
✅ memory-lancedb-pro 已安裝

## 核心鐵律

### Rule 6 — 雙層記憶存儲（鐵律）

**每次遇到坑/教訓時，必須立即存儲兩層記憶到 LanceDB：**

**技術層**（category: fact, importance ≥ 0.8）：
```
Pitfall: [症狀]
Cause: [根本原因]
Fix: [解決方案]
Prevention: [如何避免]
```

**原則層**（category: decision, importance ≥ 0.85）：
```
Decision principle ([標籤]): [行為規則]
Trigger: [何時適用]
Action: [該做什麼]
```

**要求**：
- 存儲後立即用關鍵詞 `memory_recall` 驗證檢索
- 如果沒找到，重寫並重新存儲
- 缺少任何一層 = 不完整
- 繼續下一個話題前必須確保兩層都已存儲並驗證
- 同時更新相關的 SKILL.md 文件以避免重複

---

### Rule 7 — LanceDB 衛生

**規則**：
- 條目必須簡短且原子化（< 500 字符）
- 永遠不要存儲原始對話摘要、大塊數據或重複內容
- 優先使用帶有關鍵詞的結構化格式以方便檢索

---

### Rule 8 — 重試前先檢索

**規則**：
- 任何工具失敗、重複錯誤或意外行為時
- **必須先**用相關關鍵詞（錯誤信息、工具名稱、症狀）`memory_recall`
- LanceDB 很可能已經有修復方案
- 盲目重試會浪費時間並重複已知錯誤

---

### Rule 10 — 編輯前確認目標代碼庫

**規則**：
- 處理記憶插件時，在進行更改前確認正在編輯的目標包
- 例如：`memory-lancedb-pro` vs 內置 `memory-lancedb`
- 使用 `memory_recall` + 文件系統搜索來避免修補錯誤的倉庫

---

### Rule 20 — 插件代碼變更必須清 jiti 緩存（強制）

**規則**：
- 修改 `plugins/` 下的 **任何** `.ts` 文件後
- **必須**在 `hermes gateway restart` 之前運行 `rm -rf /tmp/jiti/`
- jiti 緩存編譯的 TS；僅重啟會加載過時代碼
- 這已經多次導致靜默 Bug
- 僅配置更改不需要清除緩存

---

## 對我們 AI 無人公司的意義

### 每天 11 點自動總結機制
- ✅ 使用 Rule 6 的雙層存儲格式
- ✅ 驗證每個技能的檢索效果
- ✅ 更新相關 SKILL.md 文件

### 智能體協作記憶共享
- ✅ 使用 Rule 8，重試前先檢索記憶
- ✅ 避免重複錯誤
- ✅ 快速找到解決方案

### 代碼開發和優化
- ✅ 使用 Rule 10，編輯前確認目標
- ✅ 使用 Rule 20，修改代碼後清 jiti 緩存
- ✅ 確保修改生效

### 技能固化和優化
- ✅ 使用 Rule 7，保持簡短和原子化
- ✅ 優先結構化格式和關鍵詞
- ✅ 便於檢索和維護

## 工作流程整合

### 當遇到坑/教訓時：
1. 識別症狀和根本原因
2. 存儲技術層記憶（fact, importance ≥ 0.8）
3. 存儲原則層記憶（decision, importance ≥ 0.85）
4. 立即用關鍵詞檢索驗證
5. 更新相關 SKILL.md
6. 繼續下一個任務

### 當工具失敗時：
1. 用錯誤信息、工具名稱、症狀進行 `memory_recall`
2. 檢查是否已有解決方案
3. 如果有，應用解決方案
4. 如果沒有，記錄為新坑，遵循 Rule 6

### 當修改插件代碼時：
1. 確認目標代碼庫（Rule 10）
2. 修改代碼
3. 清除 jiti 緩存：`rm -rf /tmp/jiti/`（Rule 20）
4. 重啟 gateway：`sh /workspace/projects/scripts/restart.sh`
5. 驗證修改生效
