# 社媒內容結構化 + 進化追蹤

## 流程
每篇文章產出後：
1. 寫入 guardrails_knowledge（category=content-log）→ 搜尋 + Lint
2. 寫入 content_log 表 → 追蹤發佈狀態 + 數據 + 審查評分
3. 用本地模型做 Adversarial Review → 寫入 guardrails_knowledge（category=content-review）
4. 審查評分存入 content_log.review_score（JSONB {hook:N, share:N, experience:N}）

## 進化機制
- evolution_tags 追蹤同一主題的演進（如 agent-four-paths → agent-four-paths-v2）
- 每篇新文自動比對同 evolution tag 的舊文，標注差異
- lessons 欄位記錄每篇學到的教訓，下次寫文自動參考

## 審查維度
1. Hook力道（1-10）：第一句話能不能3秒抓住注意力
2. 可共用性（1-10）：讀者看完會不會想轉發
3. 個人經驗（1-10）：有沒有具體真實故事

## 審查模型
- 快速審查：本地 qwen3（vLLM）零成本
- 深度審查：Ollama Cloud 大模型（需排程，避免限流）

## content_log 表
SQL 在 scripts/create_content_log.sql
需要在 Supabase Dashboard SQL Editor 執行建表