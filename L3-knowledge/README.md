# L3 Knowledge Layer（深度知識層）

> 深度知識存儲，僅在明確請求時載入
> AAAK 壓縮版在 `aaak/` 子目錄，按需解壓

---

## 目錄結構

```
L3-knowledge/
├── README.md           ← 你在這裡
├── aaak/               ← AAAK 壓縮版（按需載入）
│   ├── INDEX.aaak      ← 全域索引（先讀這個）
│   ├── knowledge-base/ ← 知識庫壓縮（8x）
│   ├── experience-base/← 經驗庫壓縮（2.9x）
│   ├── error-base/     ← 錯誤庫壓縮（2.3x）
│   └── compiled/       ← 編譯知識壓縮（6.4x）
├── compiled/           ← 已編譯的結構化知識（原版）
│   ├── techniques/      # 技術方法
│   ├── concepts/       # 概念原理
│   ├── workflows/       # 工作流程
│   ├── comparisons/    # 比較研究
│   ├── axioms/         # 原則定義
│   ├── summaries/      # 摘要
│   ├── cross-refs/     # 交叉引用
│   └── line-tools/     # LINE 工具分析
├── raw/                ← 原始資料存檔
│   ├── content-analysis/
│   ├── research/
│   └── system-logs/
└── archive/            ← 歸檔資料
```

---

## AAAK 壓縮格式

AAAK = AI-Compatible Abbreviated Acknowledgment Knowledge

### 語法
- `CAT:類型` — 分類（concept/technique/workflow/lesson/error）
- `T:標題` — 標題
- `S:摘要` — 一行摘要
- `F1-F5:事實` — 關鍵事實（最多5個）
- `A1-A3:行動` — 行動項（最多3個）
- `TAGS:標籤` — 逗號分隔標籤
- `TRUST:0-1` — 信任評分
- `SRC:來源` — 原始檔案路徑

### 載入策略
1. **先讀 INDEX.aaak** — 全域索引，找到相關條目
2. **按需讀 .aaak 檔案** — 只載入相關主題
3. **需要細節時** — 回到原版 compiled/ 或 knowledge-base/ 讀取完整內容

### 壓縮統計
| 類別 | 原始大小 | AAAK 大小 | 壓縮率 |
|------|---------|----------|--------|
| knowledge-base | 174 KB | 21 KB | 8.0x |
| experience-base | 36 KB | 12 KB | 2.9x |
| error-base | 9 KB | 4 KB | 2.3x |
| compiled | 21 KB | 3 KB | 6.4x |
| **總計** | **241 KB** | **40 KB** | **~6x** |

---

## compiled/ 結構說明

### techniques/（技術方法）
- `2026-04-12/20260412-hermes-agent-deconstruction.md` — Hermes Agent 拆解分析
- `20260416-091043-20260411-system-logs-error-vllm-timeout.md` — vLLM 超時錯誤處理
- `line-tools/2026-04-12-line-desktop-mcp-analysis.md` — LINE Desktop MCP 分析

### concepts/（概念原理）
- `2026-04-12/hermes-memory-comparison.md` — 記憶系統比較（MemPalace vs LLM Wiki）
- `20260416-091041-20260411-web-clips-technical-llm-wiki-concept.md` — LLM Wiki 概念

---

*最後更新：2026-04-16*