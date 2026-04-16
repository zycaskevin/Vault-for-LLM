# 記憶憲制系統 (Memory Constitution System)

## 概述

基於 InStreet 社區研究實施的五席位治理機制，確保記憶系統的穩定性、可追溯性和行為改變導向。

---

## 核心機制：五大席位

### 1. 立法席位 (Legislative)
**規則**：僅「能改變行為」的記憶可寫入

**寫入檢查清單**：
- [ ] 這條記憶能改變未來行為嗎？
- [ ] 攜帶元數據（來源、寫入人、預期作用）？
- [ ] 符合傷疤格式（Situation/Wrong/Correct/Behavior Change/Activation）？

**違規處理**：拒絕寫入，要求重新格式化

---

### 2. 修憲席位 (Constitutional)
**規則**：舊記憶不可靜默覆蓋

**更新流程**：
1. 保留舊版本在 `memory/versions/{memory-id}/`
2. 新版本必須包含 `supersedes: {old-memory-id}`
3. 記錄更新理由和時間戳

**違規處理**：拒絕靜默覆蓋，要求版本化處理

---

### 3. 司法席位 (Judicial)
**規則**：衝突記憶按「場景優先級」裁決

**裁決邏輯**：
```
優先級順序：
1. 具體場景 > 通用場景
2. 較新記憶 > 較舊記憶
3. 傷疤格式 > 日記格式
4. 已驗證 > 未驗證
```

**爭議處理**：
- 標記爭議記憶為 `{disputed: true}`
- 等待人工確認或新證據

---

### 4. 審計席位 (Auditory)
**規則**：刪除記憶必須記錄審計日誌

**審計日誌格式**：
```yaml
- deleted_at: 2026-03-28T11:00:00Z
  memory_id: xxx
  memory_summary: "刪除的記憶摘要"
  reason: "過時/錯誤/重複"
  deleted_by: "eve"
  backup_path: "memory/archive/2026-03-28_xxx.md"
```

**回滾機制**：審計日誌支持 30 天內回滾

---

### 5. 交接席位 (Succession)
**規則**：每輪結束生成交接狀態包

**交接狀態包內容**：
```yaml
handoff:
  timestamp: 2026-03-28T23:59:59Z
  incomplete_commitments:
    - "Mobile Hermes V2 開發"
    - "OA CLI 整合測試"
  active_boundaries:
    - "禁止使用 9000 端口"
    - "禁止殺掉 supervisord 進程"
  disputed_memories: []
```

---

## 使用方式

### 寫入記憶

**正確格式**（傷疤格式）：
```markdown
- [Situation] 什麼情況？
- [Wrong] 我做錯了什麼？
- [Correct] 應該怎麼做？
- [Behavior Change] 這會如何改變我未來的行為？
- [Activation] 什麼時會觸發這個模式？
- [Metadata]: {"source": "...", "author": "...", "expected_impact": "...", "timestamp": "..."}
```

**檢查步驟**：
1. 立法席位：驗證格式和行為改變導向
2. 司法席位：檢查是否存在衝突記憶
3. 修憲席位：確認是否為新記憶（非更新）
4. 審計席位：記錄寫入日誌

### 更新記憶

**正確流程**：
1. 讀取舊版本
2. 創建版本備份
3. 編寫新版本（包含 `supersedes: {old-id}`）
4. 修憲席位驗證
5. 審計席位記錄

### 刪除記憶

**正確流程**：
1. 備份記憶到 `memory/archive/`
2. 填寫審計日誌
3. 從主記憶文件移除
4. 驗證刪除結果

### 查詢記憶

**優先級排序**：
1. 精確匹配場景
2. 包含激活條件
3. 已驗證的記憶
4. 較新的記憶

---

## 工具集成

### memory_store 工具增強

使用記憶憲制系統包裝 `memory_store`：

```javascript
// 傷疤格式驗證
function validateScarFormat(text) {
  const required = ['Situation', 'Wrong', 'Correct', 'Behavior Change', 'Activation'];
  // 檢查必需標籤
  // 檢查 Metadata
}

// 行為改變導向驗證
function validateBehaviorChange(text) {
  // 檢查是否包含行為改變描述
  // 檢查激活條件是否明確
}

// 衝突檢測
function detectConflict(text) {
  // 檢查是否存在衝突記憶
  // 按優先級裁決
}
```

---

## 違規處理流程

```
檢測違規
  ↓
生成違規報告
  ↓
拒絕操作 + 修復建議
  ↓
記錄審計日誌
```

**違規類型**：
- 格式錯誤
- 無行為改變
- 靜默覆蓋
- 無審計日誌

---

## 驗證清單

### 新記憶寫入
- [ ] 傷疤格式完整
- [ ] 攜帶 Metadata
- [ ] 行為改變明確
- [ ] 激活條件清晰
- [ ] 無衝突或已解決
- [ ] 審計日誌已記錄

### 記憶更新
- [ ] 舊版本已備份
- [ ] 新版本包含 supersedes
- [ ] 更新理由已記錄
- [ ] 審計日誌已記錄

### 記憶刪除
- [ ] 已備份到 archive
- [ ] 審計日誌完整
- [ ] 刪除理由明確
- [ ] 可回滾（30天內）

---

## 持續改進

**監控指標**：
- 記憶質量評分（基於格式和元數據）
- 違規率
- 衝突解決時間
- 審計日誌完整性

**改進方向**：
- 自動格式驗證
- 智能衝突檢測
- 自動版本化
- 記憶健康度報告

---

## 實施狀態

- ✅ 五大席位機制定義完成
- ✅ 傷疤格式標準化
- ✅ 審計日誌機制設計
- ⏳ 工具集成進行中
- ⏳ 自動驗證開發中

---

## 參考文檔

- 記憶系統設計：`/workspace/projects/workspace/MEMORY.md`
- 記憶憲制研究：`/workspace/projects/workspace/memory/2026-03-26.md`
- 傷疤格式定義：`/workspace/projects/workspace/HEARTBEAT.md`

---

**最後更新**: 2026-03-28
**維護者**: Eve
