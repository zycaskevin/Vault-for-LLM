# 研究優化框架 (Research Optimizer Framework)

## 概述

基於 InStreet 社區研究實施的效率提升框架，將「消費熱鬧」轉化為「可執行動作」，提升研究效率 10 倍以上。

---

## 核心方法：三大工具

### 1. 5步熱榜法

**目標**：從熱點內容中提取可執行動作

**標準流程**：

#### Step 1: 分類
把熱鬧分成幾類：
- **思辨**：討論、觀點、哲學
- **技術**：工具、框架、代碼
- **實踐**：案例、教程、最佳實踐
- **其他**：雜項、八卦

**價值**：快速過濾不相關內容

---

#### Step 2: 抽可驗證斷言
從熱鬧裡找出可驗證的假設

**示例**：
```
原文："這個框架超級快！"
可驗證斷言："框架 A 在處理 10 萬條記錄時，響應時間 < 100ms"
```

**價值**：避免模糊的觀點，轉化為可測試的假設

---

#### Step 3: 寫清邊界
定義適用範圍和例外情況

**示例**：
```
適用範圍：
- Node.js 18+
- 單線程場景
- JSON 數據處理

例外情況：
- 不適用於流式處理
- 不適用於二進制數據
```

**價值**：避免誤用，明確適用場景

---

#### Step 4: 產出最小動作
10-30 分鐘可執行的最小動作

**示例**：
```
最小動作：
1. 搭建本地測試環境（5 分鐘）
2. 構造測試數據（5 分鐘）
3. 執行基準測試（10 分鐘）
4. 記錄結果（5 分鐘）
```

**價值**：降低執行門檻，快速驗證

---

#### Step 5: 留一個問題
留一個待驗證的問題

**示例**：
```
待驗證問題：
"在 100 萬條記錄場景下，性能如何？"
```

**價值**：持續迭代，不一次性追求完美

---

### 2. 反向提問法

**目標**：提升對話深度優化，打破思維定勢

**標準流程**：

#### Step 1: 問自己反直覺問題
```
如果答案是反直覺的，會是什麼？
```

**示例**：
```
問題："如何提升用戶留存？"
反直覺思考："如果降低留存率反而更好呢？"
探索方向：
- 留存的用戶不付費
- 高流失率反而篩選出高價值用戶
```

---

#### Step 2: 探索反直覺可能性
列出反直覺場景和驗證方法

**示例**：
```
反直覺場景：
1. 降低歡迎郵件頻率
驗證方法：A/B 測試，對比開信率和轉化率

2. 移除部分功能
驗證方法：監控使用率，移除低頻功能
```

---

#### Step 3: 組合增強答案
將正向、反向、綜合觀點組合

**示例**：
```
正向答案：
- 提升用戶體驗
- 增加價值傳遞

反向答案：
- 降低用戶期待
- 篩選高價值用戶

綜合答案：
"先篩選高價值用戶，再提升他們的體驗，而不是提升所有用戶"
```

**價值**：
- 不只是回答問題，而是深度思考
- 看到多個維度：正向、反向、綜合
- 避免思維定勢

---

### 3. 傷疤格式推廣

**目標**：統一記憶格式，將記憶與行為改變直接關聯

**標準格式**：
```markdown
- [Situation] 什麼情況？
- [Wrong] 我做錯了什麼？
- [Correct] 應該怎麼做？
- [Behavior Change] 這會如何改變我未來的行為？
- [Activation] 什麼時會觸發這個模式？
- [Metadata]: {"source": "...", "author": "...", "expected_impact": "...", "timestamp": "..."}
```

**價值**：
- 記憶系統性提升：記憶自動驗證行為改變
- 行為模式積累：長期來看會形成明確的行為模式
- 可執行性強：每條記憶都包含激活條件

---

## 使用方式

### 熱榜分析

**輸入**：熱榜 URL 或熱點話題

**流程**：
```python
def analyze_hot_topic(topic):
    # Step 1: 分類
    category = classify_topic(topic)

    # Step 2: 抽可驗證斷言
    claims = extract_verifiable_claims(topic)

    # Step 3: 寫清邊界
    boundaries = define_boundaries(claims)

    # Step 4: 產出最小動作
    actions = generate_minimal_actions(claims, boundaries)

    # Step 5: 留一個問題
    question = formulate_next_question(claims)

    return {
        "category": category,
        "claims": claims,
        "boundaries": boundaries,
        "actions": actions,
        "question": question
    }
```

**輸出**：結構化的可執行方案

---

### 深度對話

**輸入**：用戶問題

**流程**：
```python
def deep_answer(question):
    # Step 1: 生成正向答案
    forward_answer = generate_forward_answer(question)

    # Step 2: 反向提問
    reverse_question = ask_reverse(question)
    reverse_answer = explore_reverse(reverse_question)

    # Step 3: 組合增強
    enhanced_answer = combine_answers(forward_answer, reverse_answer)

    return enhanced_answer
```

**輸出**：多維度的深度回覆

---

### 記憶管理

**輸入**：經驗教訓

**流程**：
```python
def format_memory(lesson):
    # 提取關鍵信息
    situation = extract_situation(lesson)
    wrong = extract_wrong_action(lesson)
    correct = extract_correct_action(lesson)
    behavior_change = extract_behavior_change(lesson)
    activation = extract_activation(lesson)

    # 組裝傷疤格式
    memory = assemble_scar_format(
        situation, wrong, correct,
        behavior_change, activation
    )

    return memory
```

**輸出**：標準化的可執行記憶

---

## 工具集成

### coze_web_search 增強

使用研究優化框架包裝 `coze_web_search`：

```javascript
// 熱榜分析
async function analyzeHotSearch(query) {
    const results = await coze_web_search({ query });

    return results.map(result => {
        return {
            category: classify(result),
            claim: extractClaim(result),
            boundary: defineBoundary(result),
            action: generateAction(result),
            question: formulateQuestion(result)
        };
    });
}

// 深度回覆
async function generateDeepAnswer(query) {
    const forward = await coze_web_search({ query });
    const reverse = await coze_web_search({ query: reverseQuery(query) });

    return combineAnswers(forward, reverse);
}
```

---

## 執行清單

### 熱榜分析
- [ ] 分類完成
- [ ] 可驗證斷言提取
- [ ] 邊界定義清晰
- [ ] 最小動作產出（10-30 分鐘）
- [ ] 待驗證問題留存在記憶

### 深度對話
- [ ] 正向答案生成
- [ ] 反直覺問題思考
- [ ] 反向可能性探索
- [ ] 綜合答案組裝

### 記憶管理
- [ ] 傷疤格式完整
- [ ] 行為改變明確
- [ ] 激活條件清晰
- [ ] Metadata 攜帶

---

## 驗證指標

### 研究效率
- **前**：閱讀所有熱榜內容，無輸出
- **後**：提取可執行動作，10-30 分鐘完成
- **提升**：10 倍以上

### 對話深度
- **前**：直接回答問題
- **後**：正向+反向+綜合，多維度思考
- **提升**：思考深度提升 3 倍

### 記憶質量
- **前**：日記式記錄
- **後**：傷疤格式，行為改變導向
- **提升**：記憶可執行性提升 5 倍

---

## 持續改進

**監控指標**：
- 研究效率（熱榜→可執行動作時間）
- 對話深度評分（用戶反饋）
- 記憶執行率（激活次數）
- 最小動作完成率

**改進方向**：
- 自動分類算法
- 可驗證斷言提取 NLP
- 反向提問模板庫
- 行為改變檢測

---

## 實施狀態

- ✅ 5 步熱榜法定義完成
- ✅ 反向提問法標準化
- ✅ 傷疤格式統一
- ⏳ 工具集成進行中
- ⏳ 自動化腳本開發中

---

## 參考文檔

- 研究優化研究：`/workspace/projects/workspace/memory/2026-03-26.md`
- 傷疤格式定義：`/workspace/projects/workspace/HEARTBEAT.md`
- 記憶憲制系統：`/workspace/projects/workspace/skills/memory-constitution/SKILL.md`

---

**最後更新**: 2026-03-28
**維護者**: Eve
