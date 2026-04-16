# Guardrails 同步技能

## 功能
定時同步 Guardrails 知識庫，確保所有 agent 都能訪問最新的知識、記憶、經驗、錯誤記錄。

## 使用場景
- Agent 啟動時自動同步
- 每小時定時同步
- 手動觸發同步

## 適用範圍

### 當前 Agent（8 個）
1. **Eve**（大總管）：總管，協調所有任務
2. **CTO**：技術負責人
3. **開發員**：開發執行
4. **測試員**：測試驗證
5. **Instreet小秘**：市場研究
6. **招募HR**：人力資源
7. **股票能手**：投資分析
8. **小分析**：數據分析

### 未來員工
所有新 Agent 都可以通過配置模板快速加入 Guardrails 同步系統。

### 必備技能
- **find-skills**: 技能發現
- **clawsend**: A2A 加密通信
- **guardrails-sync**: Guardrails 知識庫同步

### 可選技能
- **firecrawl-skills**: 數據抓取
- **coze-web-search**: 網頁搜索
- **feishu-task**: 飛書任務管理
- **feishu-calendar**: 飛書日曆管理

## 實現方式

### 1. 自動同步
```bash
cd /workspace/projects/Guardrails
./scripts/auto-sync.sh
```

### 2. 快速添加知識
```bash
./scripts/quick-add.sh lesson
./scripts/quick-add.sh error
```

### 3. 生成索引
```bash
./scripts/generate-index.sh
```

## 配置

### 定時同步
```bash
# 添加到 crontab
crontab -e
# 添加：0 * * * * /workspace/projects/Guardrails/scripts/auto-sync.sh
```

### GitHub 倉庫
https://github.com/zycaskevin/Guardrails

## 搜索知識

### 搜索經驗教訓
```bash
# 在 experience-base/lessons-learned/ 中搜索
grep -r "關鍵詞" experience-base/lessons-learned/
```

### 搜索錯誤記錄
```bash
# 在 error-base/error-catalog/ 中搜索
grep -r "錯誤代碼" error-base/error-catalog/
```

### 搜索專案記憶
```bash
# 在 memory-base/project-memories/ 中搜索
grep -r "專案名稱" memory-base/project-memories/
```

## 添加新知識

### 添加經驗教訓
```bash
./scripts/quick-add.sh lesson
```

按照提示輸入：
- 情況（Situation）
- 錯誤（Wrong）
- 正確做法（Correct）
- 行為改變（Behavior Change）
- 觸發條件（Activation）

### 添加錯誤記錄
```bash
./scripts/quick-add.sh error
```

按照提示輸入：
- 錯誤代碼
- 錯誤信息
- 根本原因
- 解決方案
- 預防措施

## 格式要求

### 經驗教訓必須包含
- [Situation] 什麼情況？
- [Wrong] 我做錯了什麼？
- [Correct] 應該怎麼做？
- [Behavior Change] 這會如何改變我未來的行為？
- [Activation] 什麼時會觸發這個模式？
- [Metadata] 元數據

### 錯誤記錄必須包含
- ## 錯誤信息
- ## 根本原因
- ## 解決方案
- ## 預防措施
- [Metadata] 元數據

## 元數據格式

```json
{
  "author": "Agent 名稱",
  "timestamp": "ISO 8601 格式",
  "source": "來源",
  "expected_impact": "預期影響"
}
```

## 檢查日誌

```bash
# 查看同步日誌
tail -f /tmp/guardrails-sync.log

# 查看驗證日誌
tail -f /tmp/guardrails-check.log

# 查看備份日誌
tail -f /tmp/guardrails-backup.log
```

## 故障排除

### 問題：無法推送
**解決**：
1. 檢查 GitHub Token 是否過期
2. 檢查網絡連接
3. 檢查倉庫權限

### 問題：索引生成失敗
**解決**：
1. 檢查 Python 環境
2. 檢查索引腳本是否存在
3. 檢查文件權限

### 問題：格式驗證失敗
**解決**：
1. 使用 `check-format.py` 驗證
2. 修復缺失的必要字段
3. 確保格式正確

## 最佳實踐

1. **定時同步**：每小時自動同步一次
2. **即時添加**：發現問題立即添加到知識庫
3. **定期審核**：每週審核一次知識內容
4. **格式統一**：嚴格遵守格式要求
5. **元數據完整**：確保所有條目都有完整的元數據

## 相關文檔
- Guardrails README: https://github.com/zycaskevin/Guardrails
- 發布報告: /workspace/projects/workspace/projects/guardrails-launch-report.md
