#!/usr/bin/env python3
"""
Guardrails 收斂驗證 — KAL (Knowledge Acquisition Loop) 自問收斂檢查。

對每條知識自動生成 3 個自問問題，評估知識是否充足。
支援：
  - ollama 本地模型評分（免費）
  - OpenAI 相容 API 評分（vLLM / 雲端）
  - 關鍵詞匹配評分（fallback，不需要模型）

使用方式：
  python3 scripts/convergence_check.py              # 預覽模式（不修改 DB）
  python3 scripts/convergence_check.py --apply      # 實際更新 convergence_status
  python3 scripts/convergence_check.py --limit 5    # 只檢查 5 條
  python3 scripts/convergence_check.py --min-trust 0.3  # 只檢查 trust < 0.3
  python3 scripts/convergence_check.py --ollama qwen3  # 指定 ollama 模型
  python3 scripts/convergence_check.py --api http://localhost:8000/v1  # 用 API
"""

import os
import sys
import json
import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vault.guardrails_db import GuardrailsDB

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "guardrails.db")


def generate_questions(title: str, content_raw: str) -> list[dict]:
    """根據條目生成 3 個自問問題：定義、操作、邊界案例。"""
    questions = []

    # 從 title 提取核心概念
    core_concept = title.strip()
    # 去掉常見後綴
    for suffix in ["踩坑", "筆記", "指南", "整理", "總結", "心得", "技巧", "問題", "解法"]:
        core_concept = core_concept.replace(suffix, "").strip()

    # Q1: 定義題 — 這是什麼？
    questions.append({
        "type": "definition",
        "question": f"什麼是「{core_concept}」？它的核心用途是什麼？",
        "keywords": _extract_keywords(title, content_raw, max_keywords=5),
    })

    # Q2: 操作題 — 怎麼用？
    # 從 content_raw 找操作相關的行
    action_keywords = ["設定", "安裝", "配置", "執行", "命令", "步驟", "方法", "做法", "解法"]
    has_action = any(kw in content_raw.lower() for kw in action_keywords)
    if has_action:
        questions.append({
            "type": "operation",
            "question": f"「{core_concept}」的正確操作方式是什麼？有哪些常見錯誤？",
            "keywords": _extract_keywords(content_raw, "", max_keywords=5),
        })
    else:
        questions.append({
            "type": "operation",
            "question": f"「{core_concept}」的主要操作流程是什麼？",
            "keywords": _extract_keywords(title, content_raw, max_keywords=4),
        })

    # Q3: 邊界題 — 什麼情況會失敗？
    edge_keywords = ["錯誤", "失敗", "問題", "限制", "注意", "坑", "踩", "不能", "不要", "避免"]
    has_edge = any(kw in content_raw for kw in edge_keywords)
    if has_edge:
        questions.append({
            "type": "edge_case",
            "question": f"「{core_concept}」在什麼情況下會出問題？需要避免什麼？",
            "keywords": [kw for kw in edge_keywords if kw in content_raw][:3],
        })
    else:
        questions.append({
            "type": "edge_case",
            "question": f"使用「{core_concept}」有什麼限制或注意事項？",
            "keywords": _extract_keywords(title, content_raw, max_keywords=3),
        })

    return questions


def _extract_keywords(*texts: str, max_keywords: int = 5) -> list[str]:
    """從文本中提取關鍵詞（簡單版本，不依賴分詞）。"""
    combined = " ".join(texts)
    # 去停用詞
    stopwords = {"的", "是", "在", "有", "和", "與", "到", "為", "了", "能", "可",
                 "也", "就", "都", "而", "及", "或", "但", "如果", "因為", "所以",
                 "this", "the", "is", "are", "was", "were", "a", "an", "and", "or",
                 "to", "of", "for", "in", "on", "at", "by", "with", "from", "as"}
    # 簡單分詞：中文按字/詞組，英文按空格
    words = []
    # 英文詞
    en_words = re.findall(r'[a-zA-Z][a-zA-Z0-9_-]*', combined.lower())
    words.extend(en_words)
    # 中文詞組（2-4字）
    cn_texts = re.findall(r'[\u4e00-\u9fff]{2,4}', combined)
    words.extend(cn_texts)

    # 過濾停用詞、計數、取 top
    filtered = [w for w in words if w not in stopwords and len(w) > 1]
    from collections import Counter
    counter = Counter(filtered)
    return [w for w, _ in counter.most_common(max_keywords)]


def score_with_keywords(content_raw: str, question: dict) -> float:
    """Fallback：用關鍵詞匹配評分。content_raw 中包含越多關鍵詞分數越高。"""
    if not content_raw or not question.get("keywords"):
        return 0.3

    keywords = question["keywords"]
    content_lower = content_raw.lower()

    # 計算關鍵詞命中率
    hits = sum(1 for kw in keywords if kw.lower() in content_lower)
    total = len(keywords)
    if total == 0:
        return 0.3

    hit_rate = hits / total

    # 根據問題類型給基本分
    base_scores = {
        "definition": 0.4,  # 定義題通常容易回答
        "operation": 0.3,  # 操作題需要更多細節
        "edge_case": 0.2,  # 邊界題最難
    }
    base = base_scores.get(question["type"], 0.3)

    # 最終分數 = 基本分 + 命中加成
    score = base + (1 - base) * hit_rate * 0.7
    return round(min(score, 1.0), 2)


def score_with_ollama(content_raw: str, question: dict, model: str = "qwen3") -> float:
    """用 ollama 本地模型評分。"""
    import subprocess
    prompt = f"""根據以下知識內容，回答問題並給出信心分數（0.0-1.0）。

知識內容：
{content_raw[:2000]}

問題：{question['question']}

請用 JSON 格式回答：
{{"can_answer": true/false, "confidence": 0.0-1.0, "missing": "缺少的資訊（如果無法完整回答）"}}

只輸出 JSON，不要其他內容。"""

    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout.strip()

        # 嘗試解析 JSON
        json_match = re.search(r'\{.*\}', output, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            confidence = float(data.get("confidence", 0.5))
            can_answer = data.get("can_answer", False)
            if can_answer:
                return min(confidence, 1.0)
            else:
                return min(confidence * 0.6, 0.9)  # 不能回答時壓低分數
        return 0.5  # 解析失敗，給中間分
    except Exception as e:
        print(f"  ⚠️ ollama 評分失敗：{e}")
        return -1  # 標記失敗，fallback 到關鍵詞


def score_with_api(content_raw: str, question: dict, api_url: str, api_key: str = "") -> float:
    """用 OpenAI 相容 API 評分。"""
    import requests

    prompt = f"""根據以下知識內容，回答問題並給出信心分數（0.0-1.0）。

知識內容：
{content_raw[:2000]}

問題：{question['question']}

請用 JSON 格式回答：
{{"can_answer": true/false, "confidence": 0.0-1.0, "missing": "缺少的資訊（如果無法完整回答）"}}

只輸出 JSON，不要其他內容。"""

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": "default",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 200,
    }

    try:
        resp = requests.post(
            f"{api_url.rstrip('/')}/chat/completions",
            json=payload, headers=headers, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        output = data["choices"][0]["message"]["content"].strip()

        json_match = re.search(r'\{.*\}', output, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            confidence = float(result.get("confidence", 0.5))
            can_answer = result.get("can_answer", False)
            if can_answer:
                return min(confidence, 1.0)
            else:
                return min(confidence * 0.6, 0.9)
        return 0.5
    except Exception as e:
        print(f"  ⚠️ API 評分失敗：{e}")
        return -1


def check_convergence(
    db_path: str = DB_PATH,
    apply: bool = False,
    limit: int = 0,
    min_trust: float = 1.0,
    ollama_model: str = "",
    api_url: str = "",
    api_key: str = "",
):
    """執行收斂檢查。"""

    db = GuardrailsDB(db_path)
    db.connect()

    # 篩選待檢查條目
    conditions = ["(convergence_status = 'unknown' OR convergence_status = 'partial')"]
    params: list = []

    if min_trust < 1.0:
        conditions.append("trust < ?")
        params.append(min_trust)

    where_clause = " AND ".join(conditions)
    query = f"SELECT id, title, content_raw, trust, convergence_status FROM knowledge WHERE {where_clause} ORDER BY trust ASC"

    if limit > 0:
        query += f" LIMIT {limit}"

    rows = db.conn.execute(query, params).fetchall()

    if not rows:
        print("✅ 沒有待檢查的條目（所有條目的收斂狀態皆為 complete）")
        db.close()
        return

    print(f"📊 找到 {len(rows)} 條待檢查條目")
    print("=" * 70)

    # 決定評分方法
    score_method = "keyword"  # default fallback
    if ollama_model:
        score_method = "ollama"
    elif api_url:
        score_method = "api"

    results = []
    complete_count = 0
    partial_count = 0

    for row in rows:
        kid = row[0]
        title = row[1]
        content_raw = row[2] or ""
        trust = row[3]
        current_status = row[4]

        print(f"\n🔍 [{kid}] {title} (trust={trust}, status={current_status})")

        # 生成 3 個自問問題
        questions = generate_questions(title, content_raw)

        # 對每個問題評分
        scores = []
        for i, q in enumerate(questions, 1):
            print(f"  Q{i} [{q['type']}]: {q['question']}")

            score = -1
            if score_method == "ollama":
                score = score_with_ollama(content_raw, q, ollama_model)
            elif score_method == "api":
                score = score_with_api(content_raw, q, api_url, api_key)

            # Fallback 到關鍵詞評分
            if score < 0:
                score = score_with_keywords(content_raw, q)
                method_tag = "keyword"
            else:
                method_tag = score_method

            scores.append(score)
            print(f"    → score={score:.2f} ({method_tag})")

        # 計算平均分
        avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0
        new_status = "complete" if avg_score >= 0.7 else "partial"

        if new_status == "complete":
            complete_count += 1
            emoji = "✅"
        else:
            partial_count += 1
            emoji = "⚠️"

        print(f"  {emoji} 平均分={avg_score:.2f} → status={new_status}")

        results.append({
            "id": kid,
            "title": title,
            "avg_score": avg_score,
            "status": new_status,
            "scores": scores,
        })

        # 更新 DB（如果 apply 模式）
        if apply:
            db.update_convergence(kid, new_status, avg_score)

    # 總結
    print("\n" + "=" * 70)
    print(f"📈 收斂檢查結果：")
    print(f"  ✅ Complete: {complete_count}")
    print(f"  ⚠️  Partial:  {partial_count}")
    print(f"  📊 總計:     {len(rows)}")

    if not apply:
        print("\n💡 這是預覽模式。使用 --apply 實際更新資料庫。")

    # 輸出 JSON 報告
    report_path = os.path.join(os.path.dirname(db_path), "convergence_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": score_method,
            "total": len(rows),
            "complete": complete_count,
            "partial": partial_count,
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"📄 報告已儲存：{report_path}")

    db.close()
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Guardrails 收斂檢查 — KAL 自問收斂")
    parser.add_argument("--apply", action="store_true", help="實際更新資料庫（預設為預覽模式）")
    parser.add_argument("--limit", type=int, default=0, help="最多檢查幾條（0=全部）")
    parser.add_argument("--min-trust", type=float, default=1.0, help="只檢查 trust 低於此值的條目")
    parser.add_argument("--ollama", type=str, default="", help="使用 ollama 模型評分（如 qwen3）")
    parser.add_argument("--api", type=str, default="", help="使用 OpenAI 相容 API 評分")
    parser.add_argument("--api-key", type=str, default="", help="API key（如需要）")
    args = parser.parse_args()

    check_convergence(
        apply=args.apply,
        limit=args.limit,
        min_trust=args.min_trust,
        ollama_model=args.ollama,
        api_url=args.api,
        api_key=args.api_key,
    )