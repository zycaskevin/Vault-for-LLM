# 當前專案與任務

## 活躍專案

### 🛡️ Guardrails 百科系統（活躍開發中）
- **狀態**：L0-L4 完整運作，118 筆 Supabase，8 筆 raw/
- **核心**：四層分層 + AAAK 6x壓縮 + 信任分數 + Lint + 矛盾偵測
- **近期**：compiler fcntl.flock 防重跑、L2 從 state.db 讀、Lint 四功能上路
- **開源計畫**：Guardrails Lite（純本地）+ Guardrails Full（Supabase+pgvector）

### 📝 社媒內容系統（運作中）
- **狀態**：每日 10:00 自動生成 FB/Threads 文章
- **平台**：Facebook + Threads（手動貼文）
- **數據**：content_log 表 12 筆，全部有審查分數
- **風格**：Larry Hook 公式 + qwen3 本地審查 + 進化追蹤
- **模板庫**：article-templates.md（4 種模板）

### 🤖 Hermes Agent 生態（持續優化）
- **模型**：glm-5.1:cloud (主力) + deepseek-v3.2 (雲端) + qwen3 (本地 vLLM)
- **Cron**：17 個（9 個報告推 @Nancy_report_bot + 3 個互動 + 5 個系統維護）
- **報告 Bot**：@Nancy_report_bot 已上線，報告與主對話分離
- **開源**：Hermes-web-access (GitHub) + Guardrails（規劃中）

### 🎯 GitHub 戰術雷達（運作中）
- **狀態**：每日 09:00 自動掃描、翻譯、推送
- **架構**：4 層情報（動能/Reality Audit/論文/Tactical）

## 技術棧

| 類別 | 工具 | 備註 |
|------|------|------|
| 推理 | Ollama Cloud Pro | 3並發，$20/月，glm-5.1/deepseek-v3.2 |
| 本地 | vLLM + qwen3 8B | 零成本審查/輕量推理 |
| 資料庫 | Supabase | guardrails_knowledge + content_log |
| 語音 | GLM-TTS | 零樣本克隆，參考音 reference_final.wav |
| 瀏覽器 | Chrome CDP | WSL2 三層橋接 (cdp-bridge.py) |

## 待處理
- ⬜ Guardrails Lite 開源（GitHub repo + 文檔）
- ⬜ L2/L3 純文字備份機制
- ⬜ compiler 自動 git commit
- ⬜ content_log 填充歷史數據（發佈後回報觸及/互動）
- ⬜ 醫美接案探索（Fiverr + Tasker）

## 已歸檔
- ~~OpenClaw 遷移~~（已完成，04/14 移除）
- ~~ChromaDB 記憶~~（已替換為 Holographic）
- ~~Nancy/Coco/Eve~~（已清退，04/15 三清）

---
*最後更新：2026-04-16*