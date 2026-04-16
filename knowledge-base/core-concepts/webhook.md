# Webhook 機制

## 概述
Webhook 是事件驅動的 HTTP 回調機制。

## 工作原理
1. 事件發生
2. 發送 HTTP 請求
3. 接收方處理
4. 返回響應

## 應用場景

### 1. 支付通知
Stripe Webhook 通知支付狀態。

### 2. 版本控制
GitHub Webhook 觸發 CI/CD。

### 3. 通信
飛書 Webhook 實現消息推送。

## 實現示例

```python
from flask import Flask, request

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    data = request.json
    # 處理 webhook 數據
    return {"status": "ok"}
```

## 安全
- 驗證簽名
- IP 白名單
- HTTPS

[Metadata]: {"category": "core-concept", "author": "Eve", "timestamp": "2026-03-29T13:30:00Z"}
