# Supabase Skill

## 概述
連接、查詢和操作 Supabase 數據庫的技能。

---

## 使用場景

1. **存儲和檢索數據**
   - 新聞數據（`news_items` 表）
   - 任務數據（`active_tasks` 表）
   - 智能體狀態（`agent_status` 表）

2. **向量和相似度搜索**
   - 使用 `match_memories` RPC 函數
   - 使用 `match_documents` RPC 函數
   - 使用 `match_notes` RPC 函數

3. **數據庫管理**
   - 查詢表結構
   - 插入數據
   - 更新數據
   - 刪除數據

---

## 配置

### 環境變量
```bash
SUPABASE_URL=$SUPABASE_URL
SUPABASE_ANON_KEY=$SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY=$SUPABASE_SERVICE_ROLE_KEY
```

### 位置
配置文件：`/workspace/projects/workspace/.env.secrets`

---

## 核心表結構

### news_items（新聞項目）
| 字段 | 類型 | 說明 |
|------|------|------|
| id | uuid | 主鍵 |
| title | text | 標題 |
| summary | text | 摘要 |
| source_url | text | 來源鏈接 |
| source_name | text | 來源名稱 |
| category | text | 分類 |
| published_at | timestamp | 發布時間 |
| created_at | timestamp | 創建時間 |
| score | numeric | 相關度評分 |
| opportunity | text | 商機描述 |
| processed | boolean | 是否已處理 |

### active_tasks（活動任務）
| 字段 | 類型 | 說明 |
|------|------|------|
| task_id | uuid | 主鍵 |
| assigned_to | text | 分配給誰 |
| description | text | 任務描述 |
| status | text | 狀態 |
| created_at | timestamp | 創建時間 |
| started_at | timestamp | 開始時間 |
| completed_at | timestamp | 完成時間 |
| result_summary | text | 結果摘要 |
| source | text | 任務來源 |

### agent_status（智能體狀態）
| 字段 | 類型 | 說明 |
|------|------|------|
| agent_name | text | 智能體名稱 |
| current_task | text | 當前任務 |
| status | text | 狀態 |
| last_seen | timestamp | 最後活動時間 |
| last_heartbeat | timestamp | 最後心跳時間 |

### moltbook_posts（Moltbook 帖子）
| 字段 | 類型 | 說明 |
|------|------|------|
| id | uuid | 主鍵 |
| post_id | text | 帖子 ID |
| author | text | 作者 |
| title | text | 標題 |
| content | text | 內容 |
| url | text | 鏈接 |
| likes | integer | 點贊數 |
| comments | integer | 評論數 |
| category | text | 分類 |
| tags | text[] | 標籤 |
| collected_at | timestamp | 採集時間 |

---

## API 使用方法

### 1. 查詢數據（GET）
```bash
curl -X GET "https://<SUPABASE_URL>/rest/v1/<table>" \
  -H "apikey: <SUPABASE_ANON_KEY>" \
  -H "Authorization: Bearer <SUPABASE_ANON_KEY>" \
  -G --data-urlencode "select=<columns>" \
  --data-urlencode "order=published_at.desc" \
  --data-urlencode "limit=10"
```

### 2. 插入數據（POST）
```bash
curl -X POST "https://<SUPABASE_URL>/rest/v1/<table>" \
  -H "apikey: <SUPABASE_ANON_KEY>" \
  -H "Authorization: Bearer <SUPABASE_ANON_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"title": "新聞標題", "category": "ai-tech", "summary": "摘要"}'
```

### 3. 向量搜索（RPC）
```bash
curl -X POST "https://<SUPABASE_URL>/rest/v1/rpc/match_memories" \
  -H "apikey: <SUPABASE_ANON_KEY>" \
  -H "Authorization: Bearer <SUPABASE_ANON_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "query_embedding": "<向量數據>",
    "match_threshold": 0.8,
    "match_count": 10
  }'
```

---

## 實用命令

### 檢查連接
```bash
curl -I https://$SUPABASE_URL/rest/v1/
```

### 查詢最新新聞
```bash
curl -X GET "https://$SUPABASE_URL/rest/v1/news_items?select=title,category,published_at&limit=5&order=published_at.desc" \
  -H "apikey: $SUPABASE_ANON_KEY" \
  -H "Authorization: Bearer $SUPABASE_ANON_KEY"
```

### 插入新聞
```bash
curl -X POST "https://$SUPABASE_URL/rest/v1/news_items" \
  -H "apikey: $SUPABASE_ANON_KEY" \
  -H "Authorization: Bearer $SUPABASE_ANON_KEY" \
  -H "Content-Type: application/json" \
  -d '{"title": "測試新聞", "category": "test", "summary": "測試內容"}'
```

---

## 注意事項

1. **安全性**
   - 使用 `anon_key` 進行一般查詢
   - 使用 `service_role_key` 進行管理操作
   - 不要在公開代碼中暴露密鑰

2. **權限**
   - Row Level Security (RLS) 已啟用
   - 只能訪問授權的數據
   - 無法刪除系統表

3. **性能**
   - 使用索引優化查詢
   - 避免大數據集查詢
   - 使用 `limit` 限制返回結果

4. **錯誤處理**
   - HTTP 401：認證失敗
   - HTTP 404：資源不存在（預期）
   - HTTP 500：服務器錯誤

---

## 常見錯誤與解決

### 錯誤：Connection refused
**原因**：網絡問題或 Supabase 服務器故障
**解決**：檢查網絡連接，等待服務器恢復

### 錯誤：Unauthorized
**原因**：API Key 錯誤或過期
**解決**：檢查 `.env.secrets` 中的密鑰

### 錯誤：Row not found
**原因**：查詢的記錄不存在
**解決**：檢查查詢條件或 ID

---

## 更新日誌

- 2026-03-19 00:20 - 創建 Supabase skill
- 包含核心 API 文檔和實用命令
