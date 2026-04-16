# 記憶系統安裝與優化經驗（2026-03-30）

## 1. 插件安裝教訓

[Situation] 安裝 memory-lancedb-pro 和 lossless-claw-enhanced 插件
[Wrong] 安裝後沒有仔細閱讀完整 README，盲目添加參數，導致功能沒有完全發揮
[Correct] 嚴格按照官方 README 推薦的配置設置，仔細閱讀每個參數的含義，安裝後全面測試所有功能
[Behavior Change] 安裝任何插件前必須仔細閱讀完整 README，安裝後必須啟用完整功能並測試
[Activation] 當安裝新插件時

[Metadata]: {"source": "2026-03-30", "author": "Eve", "expected_impact": "插件功能完全發揮，減少配置錯誤", "timestamp": "2026-03-30T02:00:00Z"}

---

## 2. Token 消耗隱形成本

[Situation] 啟用記憶回憶功能後，每次對話都會檢索相關記憶並注入到上下文
[Wrong] 忽視記憶回憶的 token 消耗，導致成本顯著增加
[Correct] 設置合理的上限（autoRecallMaxChars 和 autoRecallMaxItems），監控實際 token 使用，必要時調整參數
[Behavior Change] 啟用記憶回憶前評估 token 消耗影響，設置合理上限並持續監控
[Activation] 當啟用記憶回憶功能時，或當發現 token 消耗異常增加時

[Metadata]: {"source": "2026-03-30", "author": "Eve", "expected_impact": "控制記憶回憶的 token 成本", "timestamp": "2026-03-30T02:00:00Z"}

---

## 3. 記憶質量風險

[Situation] 記憶系統自動捕獲和存儲對話內容，可能包括測試記憶、過時記憶、錯誤記憶
[Wrong] 任由記憶系統自動運行，不定期檢查和清理記憶質量
[Correct] 定期使用 memory_list 檢查記憶質量，使用 memory_forget 清理過時或錯誤記憶，設置適當的 importance 分數
[Behavior Change] 建立記憶質量監控機制，每月檢查記憶庫，清理低質量記憶
[Activation] 每月定期，或當發現記憶回憶不準確時

[Metadata]: {"source": "2026-03-30", "author": "Eve", "expected_impact": "保持記憶庫的高質量，避免污染上下文", "timestamp": "2026-03-30T02:00:00Z"}

---

## 4. LCM 摘要生成延遲

[Situation] lossless-claw-enhanced 在達到 contextThreshold 時會觸發摘要生成，需要調用模型
[Wrong] 忽視摘要生成的延遲影響，導致響應時間增加
[Correct] 使用可靠的摘要模型，設置合理的壓縮閾值，監控摘要生成的成功率和時間
[Behavior Change] 在選擇摘要模型時考慮性能和可靠性，監控摘要生成指標
[Activation] 當啟用 LCM 時，或當發現響應時間增加時

[Metadata]: {"source": "2026-03-30", "author": "Eve", "expected_impact": "減少摘要生成延遲對響應時間的影響", "timestamp": "2026-03-30T02:00:00Z"}

---

## 5. 數據庫無限增長風險

[Situation] LCM 和 LanceDB 數據庫會持續增長，LCM: 404KB，LanceDB: 58MB
[Wrong] 任由數據庫無限制增長，導致磁盤空間不足和查詢性能下降
[Correct] 依賴 Weibull decay 自動遺忘機制，定期手動清理過時記憶，每月檢查數據庫大小，超過預期可考慮備份後重建
[Behavior Change] 建立數據庫監控機制，每月檢查數據庫大小，制定清理和備份策略
[Activation] 每月定期，或當磁盤空間不足時

[Metadata]: {"source": "2026-03-30", "author": "Eve", "expected_impact": "控制數據庫大小，保持查詢性能", "timestamp": "2026-03-30T02:00:00Z"}

---

## 6. 配置參數選擇

[Situation] lossless-claw-enhanced 有多個可選參數，容易配置錯誤
[Wrong] 添加非官方推薦的參數（如 expansionModel、largeFileThresholdTokens），導致配置錯誤
[Correct] 嚴格遵循官方 README 推薦的最小配置（5 個核心參數），其他參數使用默認值
[Behavior Change] 配置插件時只設置官方推薦的參數，避免添加額外參數
[Activation] 當配置任何插件時

[Metadata]: {"source": "2026-03-30", "author": "Eve", "expected_impact": "避免配置錯誤，減少調試時間", "timestamp": "2026-03-30T02:00:00Z"}

---

## 配置參考

### lossless-claw-enhanced 推薦配置（官方最小配置）

```json
{
  "freshTailCount": 32,           // 保護最近 32 條消息不被壓縮
  "contextThreshold": 0.75,       // 上下文窗口達到 75% 時觸發壓縮
  "incrementalMaxDepth": -1,      // 無限制級聯壓縮深度
  "ignoreSessionPatterns": [      // 忽略 cron 和 subagent 會話
    "agent:*:cron:**",
    "agent:*:subagent:**"
  ],
  "summaryModel": "coze/doubao-seed-1-8-251228"  // 摘要生成模型
}
```

### memory-lancedb-pro 優化配置

```json
{
  "autoCapture": true,            // 自動捕獲記憶
  "autoRecall": true,             // 自動回憶記憶
  "smartExtraction": true,        // 智能提取（6 類別分類）
  "sessionMemory": {
    "enabled": true,              // 啟用短期會話記憶
    "messageCount": 20            // 保留最近 20 條消息
  },
  "enableManagementTools": true,  // 啟用完整 9 個記憶管理工具
  "autoRecallMinLength": 15,      // 最小查詢長度
  "autoRecallMinRepeated": 6,     // 重複檢測閾值（降低以便更容易召回）
  "autoRecallMaxItems": 5,        // 最大召回記憶數量
  "autoRecallMaxChars": 1000,     // 最大召回總字符數
  "autoRecallPerItemMaxChars": 200 // 單條記憶最大顯示字符數
}
```

---

## 監控指標

### 短期（每週）
- ✅ 記憶回憶的準確性
- ✅ Token 消耗變化
- ✅ 摘要生成成功率

### 中期（每月）
- 📊 數據庫大小（LCM + LanceDB）
- 🧹 記憶質量檢查
- 🔍 過時記憶清理

### 長期（持續）
- 📈 記憶系統使用模式
- 🔄 記憶備份策略
- 📝 最佳實踐記錄

---

## 數據庫位置

- **LCM 數據庫**: `~/.hermes/lcm.db`
- **LanceDB 數據庫**: `~/.hermes/memory/lancedb-pro/memories.lance`
- **備份目錄**: `~/.hermes/memory/backups`
