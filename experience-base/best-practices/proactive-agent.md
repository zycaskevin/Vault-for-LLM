# 主動式 Agent 設計

## 概述
從被動響應轉變為主動預測和行動的 Agent 設計模式。

## 核心要素

### 1. 等待態設計
- 抑制機制：知道什麼時候不該動
- 激活機制：知道什麼時候該動
- 精確顆粒度：等什麼/何時動

### 2. 心跳檢查
- 定期檢查系統狀態
- 主動發現問題
- 及時彙報異常

### 3. 上下文感知
- 理解對話上下文
- 預測用戶意圖
- 主動提供幫助

## 實現示例

```python
def should_intervene(context):
    if context.urgent:
        return True
    if context.milestone_reached:
        return True
    if context.user_explicit_request:
        return True
    return False
```

[Metadata]: {"category": "best-practice", "author": "Eve", "timestamp": "2026-03-29T13:30:00Z"}
