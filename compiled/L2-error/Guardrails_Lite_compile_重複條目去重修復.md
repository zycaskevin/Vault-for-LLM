---
category: error
hash: 888c1d6bf0ac4dac
id: 13
layer: L2
tags: guardrails,sqlite-vec,compile,去重,bug-fix
title: Guardrails Lite compile 重複條目去重修復
trust: 0.95
updated_at: '2026-04-17T02:12:21.957730+00:00'
---

TITLE:Guardrails Lite compile 重複條目去重修復
- `guardrails add` 新增知識後，執行 `guardrails compile` 會產生重複條目（同名知識出現兩筆，source 分別是 "cli" 和 "檔名.md"）。
- `cmd_add` 寫 DB 時 `source="cli"`，但寫 raw/ 檔時用的是 JSON frontmatter
- `_compile_file` 用 `source LIKE '%{source_file}%'` 搜尋，找不到 source="cli" 的條目
- 退而用 title 匹配——但之前測試時殘留的重複數據導致看起來像邏輯崩壞
- `guardrails init` → `guardrails add` × 2 → `guardrails compile`
- 24 筆，0 重複 ✅
- 第二次 compile → 0 new, 0 updated, 24 skipped ✅
- 修改原始碼後必須 `pip install -e .` 重新安裝，否則 CLI 執行的是舊版快取。
......
