# 多智能體協作模式

## PM 去中心化協調模式

### 核心原則
- Main session = coordinator ONLY（僅協調，不執行）
- 所有執行通過子代理完成

### 工作流
1. 新任務到達
2. 檢查 PROJECT_REGISTRY.md 是否有現有 PM
3. 如果 PM 存在 → sessions_send
4. 如果是新專案 → sessions_spawn
5. PM 執行，更新 STATE.yaml，報告回來
6. Main agent 向用戶匯總

### 標籤約定
- PM: `pm-{project}-{scope}`
- 子代理: `{scope}-{task-id}`

## 狀態追蹤
使用 STATE.yaml 記錄：
- 任務進度
- 問題列表
- 待辦事項
- 里程碑

[Metadata]: {"category": "core-concept", "author": "Eve", "timestamp": "2026-03-29T13:00:00Z"}
