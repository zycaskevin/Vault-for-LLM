---
title: Guardrails Lite compile 重複條目去重修復
category: error
layer: L2
tags: guardrails,sqlite-vec,compile,去重,bug-fix
trust: 0.95
source: 實測除錯
---

# Guardrails Lite compile 重複條目去重修復

## Bug 症狀
`guardrails add` 新增知識後，執行 `guardrails compile` 會產生重複條目（同名知識出現兩筆，source 分別是 "cli" 和 "檔名.md"）。

## 根因分析
1. `cmd_add` 寫 DB 時 `source="cli"`，但寫 raw/ 檔時用的是 JSON frontmatter
2. `_compile_file` 用 `source LIKE '%{source_file}%'` 搜尋，找不到 source="cli" 的條目
3. 退而用 title 匹配——但之前測試時殘留的重複數據導致看起來像邏輯崩壞
4. **實際根因：舊 DB 裡有殘留測試數據，而非程式邏輯 bug。**

## 修復結果
從乾淨 DB 開始測試：
- `guardrails init` → `guardrails add` × 2 → `guardrails compile`
- 24 筆，0 重複 ✅
- 第二次 compile → 0 new, 0 updated, 24 skipped ✅
- 向量搜尋、lint、doctor 全通過 ✅

## 關鍵發現：pip install -e 的開發陷阱
修改原始碼後必須 `pip install -e .` 重新安裝，否則 CLI 執行的是舊版快取。這浪費了大量除錯時間——print 加了但 CLI 不顯示，因為安裝的不是最新版。

## 去重機制（兩層防禦）
1. **_compile_file**: 先用 source_file 匹配，再用 title 匹配 + content_hash 比對
2. **compile() 尾部**: GROUP BY title 去重，保留最早 id（安全網）