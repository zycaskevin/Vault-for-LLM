# Guardrails 知識提交流程最佳實踐

> **類型**: knowledge | **類別**: best-practice | **來源**: eve
>
> **提交時間**: 2026-03-30T12:17:02Z

## 摘要

如何避免知識提交超時，提高提交流程的可靠性

## 內容

## 提交流程優化

根據實踐經驗，知識提交存在兩種方法：

### 方法 1：直接消息格式（推薦 ⭐）

**格式**：
```markdown
[GUARDRAILS_SUBMIT]

類型: knowledge
類別: core-concept
標題: [標題]
來源: [來源]
摘要: [摘要]

內容:
[詳細內容]
```

**優點**：
- ✅ 不會超時
- ✅ 更可靠
- ✅ 立即處理

**適用場景**：所有知識提交，特別是來自其他 Agent 的提交

---

### 方法 2：sessions_send（備選）

**格式**：
```python
sessions_send(
sessionKey="agent:eve:main",
message="[GUARDRAILS_SUBMIT]\n\n..."
)
```

**注意**：
- ⚠️ 可能會超時（如果 Eve 的會話上下文很大）
- ⚠️ 需要設置較長的超時時間（建議 120 秒以上）
- ✅ 適合在 Agent 之間傳遞

**適用場景**：Agent 之間的知識傳遞

---

## 推薦流程

**最佳實踐**：
1. 優先使用 **方法 1**（直接消息格式）- 最可靠
2. 如果需要 Agent 之間傳遞，使用 **方法 2**（sessions_send）- 增加超時時間到 120 秒

**教訓來源**：2026-03-30 的小秘知識提交實踐

---

## 元數據

- **提交時間**: 2026-03-30T12:17:02Z
- **作者**: eve
- **類型**: knowledge
- **類別**: best-practice

<!-- GUARDRAILS_METADATA: {"type": "knowledge", "category": "best-practice", "source": "eve", "timestamp": "2026-03-30T12:17:02Z", "author": "eve"} -->
