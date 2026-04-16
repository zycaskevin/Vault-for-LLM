# PM 去中心化協調模式

## 概述
PM 去中心化協調模式是一種高效的多智能體協作方式。

## 核心原則
- Main session = coordinator ONLY
- 所有執行通過子代理完成
- STATE.yaml 作為協調中心

## 工作流
1. 新任務到達
2. 檢查 PROJECT_REGISTRY.md
3. 有 PM → sessions_send
4. 新專案 → sessions_spawn
5. PM 執行並更新 STATE.yaml
6. Main agent 匯總

## 標籤約定
- PM: `pm-{project}-{scope}`
- 子代理: `{scope}-{task-id}`

## 優勢
- 並行執行效率高
- 職責分離清晰
- 狀態可追蹤

[Metadata]: {"category": "best-practice", "author": "Eve", "timestamp": "2026-03-29T13:30:00Z"}
