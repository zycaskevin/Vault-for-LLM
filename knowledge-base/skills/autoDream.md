---
name: autoDream
version: 1.0.0
description: |
  autoDream 記憶蒸餾系統 | Memory Distillation System
  自動蒸餾 MEMORY.md，保留高價值內容，壓縮記憶文件大小。
  根據配置策略（score、傷疤格式）過濾和濃縮記憶條目。
license: MIT
---

# autoDream | 記憶蒸餾系統

自動蒸餾 MEMORY.md，保持記憶系統高效運行。根據重要性和傷疤格式保留內容，將記憶文件壓縮至目標行數。

Automatically distill MEMORY.md to keep the memory system efficient. Retain content based on importance and scar patterns, compressing the memory file to the target line count.

---

## 依賴關係 / Dependencies

**本技能依賴 / This skill depends on**：
- `config/autoDream.yaml` - 蒸餾配置 / Distillation configuration

---

## 配置 / Configuration

`/workspace/projects/workspace/config/autoDream.yaml`：

```yaml
# 觸發條件 / Trigger Conditions
triggers:
  line_threshold: 500  # 超過 500 行時觸發
  schedule: "03:00"    # 每天 03:00 執行

# 保留策略 / Retention Policy
retention:
  verbatim:
    min_score: 9       # score >= 9 原樣保留
  summary:
    min_score: 7       # score >= 7 保留摘要
  scar:
    enabled: true      # 傷疤格式特殊保留
  archive:
    enabled: true      # 超過閾值自動歸檔

# 目標 / Target
target_lines: 200      # 目標行數
```

---

## 執行方式 / Usage

### 命令行 / Command Line

```bash
bash /workspace/projects/workspace/scripts/autoDream.sh
```

### 輸出 / Output

```
🔄 autoDream 記憶蒸餾開始...
📊 當前狀態：1021 行
⚙️ 蒸餾策略：score >=9 原樣，>=7 摘要，傷疤保留
✅ 蒸餾完成：82 行（93.6% 壓縮）
💾 備份已保存：memory/versions/2026-04-06_12-02-53_distill.md
```

---

## 蒸餾策略 / Distillation Strategy

| Score | 處理方式 | 說明 |
|-------|---------|------|
| >= 9 | 原樣保留 | 最高優先級，完整內容 |
| 7-8 | 摘要保留 | 提取核心信息 |
| < 7 | 濃縮或歸檔 | 簡化或移至歸檔 |

**特殊保留**：所有傷疤格式記憶（`[Situation]`...`[Activation]`）無條件保留

---

## 定時任務 / Scheduled Task

添加到 `HEARTBEAT.md`：

```
| Task | Frequency | Status | Token Mode |
|------|-----------|--------|------------|
| autoDream蒸餾 | Daily 03:00 或 >500行 | ✅ | Full |
```

---

## 版本歷史 / Changelog

- **v1.0.0**: 初始版本，實裝自動蒸餾系統 / Initial version with auto distillation system

---

## 實際案例 / Real Example

**2026-04-06 首次蒸餾**：
- 原始：1021 行（~51KB）
- 蒸餾後：82 行（~4KB）
- 壓縮率：93.6%
- 處理：19 條記憶，7 條原樣，2 條摘要，10 條濃縮，0 條歸檔
