# Coze 集成

## 概述
Coze 是字節跳動的 AI 平台，提供聊天機器人和工作流自動化能力。

## API 配置

### 認證
- 使用 API Key 進行認證
- 支持 OAuth 2.0

### 端點
- API Base: https://api.coze.com
- API Version: v1

## 可用功能

### 1. ASR (語音轉文字)
- 將語音轉換為文字
- 支持多種語言

### 2. TTS (文字轉語音)
- 將文字轉換為語音
- 支持多種音色

### 3. Image Generation
- 根據文字提示生成圖片
- 支持多變體生成

### 4. Workflow
- 執行自定義工作流
- 支持參數傳遞

## 使用示例

```python
import coze

coze.api_key = "your-api-key"
result = coze.chat.completions.create(
    model="coze-旗舰模型",
    messages=[{"role": "user", "content": "你好"}]
)
```

[Metadata]: {"category": "ai-provider", "author": "Eve", "timestamp": "2026-03-29T13:30:00Z"}
