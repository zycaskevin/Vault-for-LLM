# Ollama Cloud API 限流踩坑

## 方案
Pro $20/月（2026/04）

## 限制
- 同時 3 個雲端模型並行（Max $100/月才 10 個）
- 每 5 小時 session limit 重置，每 7 天 weekly limit 重置
- 用量以 GPU 時間計算，不是 token 數
- 超過 concurrent 限制的請求排隊，排滿了就 reject（HTTP 429 或 timeout）
- 持續大量使用 5+ 天可能觸發 throttle（GitHub issue 有人回報被 throttle 4 天）

## 觸發條件
- 短時間連續呼叫 5+ 個大模型請求（如多模型辯論）
- 長 prompt + 大模型（deepseek-v3.2, kimi-k2.5, qwen3.5:397b）= 高 GPU 時間
- delegate_task 同時派 3+ 個子代理到 Ollama Cloud

## 症狀
- 請求 timeout（60s+ 無回應）
- 空回應（content 為空字串）
- HTTP 429 Too Many Requests
- 模型存在但回傳 400 bad request（可能是佇列滿了）

## 解法
- 辯論/共識模式用序列而非並行（一個接一個）
- 優先用本地 qwen3 (vLLM) 做 Adversarial Review
- Ollama Cloud 只在需要大模型推理時使用
- 長 prompt 拆短：只傳修改區域，不傳整個文件
- 遇到 timeout 等 5-10 分鐘再試
- 監控用量：https://ollama.com/settings

## delegate_task 陷阱
- model 參數只認 "custom" 或 "openrouter" provider
- 如果指定的模型在 Ollama Cloud 限流中，delegate_task 會 fallback 到其他模型
- 多個子代理同時打到 Ollama Cloud 會觸發 concurrent 限制