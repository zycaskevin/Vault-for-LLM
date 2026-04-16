# 模型路由

## 概述
模型路由是成本控制和性能優化的關鍵技術。

## 路由策略

### 1. 意圖分類
根據用戶輸入的意圖，自動選擇適合的模型。

### 2. 成本優先
簡單任務使用低成本模型。

### 3. 質量優先
複雜任務使用高質量模型。

## 實現方式

### AUTO 模式
```python
def route_model(intent, complexity):
    if complexity < 0.3:
        return "gemini-flash"  # 1 point
    elif complexity < 0.7:
        return "claude-sonnet"  # 5 points
    else:
        return "claude-opus"   # 20 points
```

## 價值
- 成本降低 60%+
- 響應速度提升
- 用戶體驗優化

[Metadata]: {"category": "core-concept", "author": "Eve", "timestamp": "2026-03-29T13:30:00Z"}
