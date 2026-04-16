---
name: task-batcher
version: 1.0.0
description: |
  task-batcher 任務批次系統 | Task Batching System
  合併相似任務，批量執行，節省 Token 消耗。
  智能分類任務，減少重複 API 調用。
license: MIT
---

# task-batcher | 任務批次系統

合併相似任務，批量執行，節省 Token 消耗。智能分類任務類型，減少重複 API 調用和上下文重複載入。

Merge similar tasks, execute in batches, save Token consumption. Intelligently classify task types, reduce duplicate API calls and context reloading.

---

## 依賴關係 / Dependencies

**本技能依賴 / This skill depends on**：
- `HEARTBEAT.md` - 任務調度配置 / Task scheduling configuration

---

## 執行方式 / Usage

### 命令行 / Command Line

```bash
bash /workspace/projects/workspace/scripts/task-batcher.sh
```

### 輸出 / Output

```
🔄 任務批次系統啟動...
📊 待處理任務：5 個
📦 批次分類：
  - API 調用：3 個 → 1 批次
  - 文件檢查：2 個 → 1 批次
✅ 執行完成：節省 3 次上下文載入
💾 預計節省 Token：~40%
```

---

## 批次策略 / Batching Strategy

| 任務類型 | 批次策略 | 節省效果 |
|---------|---------|---------|
| API 調用 | 合併相同端點 | ~30% |
| 文件檢查 | 批量讀取 | ~40% |
| 數據查詢 | 合併查詢條件 | ~50% |
| 消息發送 | 批量發送 | ~35% |

---

## 配置 / Configuration

### HEARTBEAT.md 配置

```markdown
## Token Mode 分類

| Mode | 用途 | 特徵 |
|------|------|------|
| Full | 重要任務 | 完整上下文 |
| Light | 常規檢查 | 最小上下文 |

## 任務頻率優化

| Task | 舊頻率 | 新頻率 | 節省 |
|------|-------|-------|------|
| Task Status | 15 min | 60 min | 75% |
| Supabase Tasks | 30 min | 60 min | 50% |
```

---

## 實際案例 / Real Example

**2026-04-06 令牌優化**：

| 優化項目 | 策略 | 成果 |
|---------|------|------|
| 檢查頻率 | 15/30分 → 60分 | 節省 75% / 50% |
| Token 模式 | 全部 Full → Full/Light | 節省 ~30% |
| 任務批次 | 新增系統 | 節省 ~40% |
| **總體** | **多維度優化** | **節省 60-70%** |

---

## 版本歷史 / Changelog

- **v1.0.0**: 初始版本，實裝任務批次系統 / Initial version with task batching system

---

## 效果驗證 / Effect Verification

使用前後對比：

```bash
# 使用前
每天 Token 消耗：~20 USD
心跳檢查頻率：15分鐘

# 使用後
每天 Token 消耗：~6-8 USD
心跳檢查頻率：60分鐘
預計節省：60-70%
```
