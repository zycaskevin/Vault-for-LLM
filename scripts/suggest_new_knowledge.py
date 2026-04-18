#!/usr/bin/env python3
"""
Guardrails 主動建議 — 掃描知識缺口，建議應補充的知識。

策略：
1. 掃描所有 tags，找出孤立標籤（只出現 1 次的）
2. 檢查常見技術主題是否有對應知識
3. 比對 error-base 和 knowledge-base，找「有踩坑但沒歸檔最佳實踐」的主題
4. 掃描 content_log 的已發佈文章，找尚未入庫的主題

使用方式：
  python3 scripts/suggest_new_knowledge.py           # 列出建議
  python3 scripts/suggest_new_knowledge.py --json     # JSON 格式輸出
"""

import os
import sys
import json
import argparse
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vault.guardrails_db import GuardrailsDB

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "guardrails.db")

# 已知技術主題（應該要有對應知識的）
EXPECTED_TOPICS = {
    "vllm": "vLLM 部署與推理",
    "ollama": "Ollama 本地推理",
    "supabase": "Supabase 資料庫",
    "messaging": "messaging platform 整合",
    "github": "GitHub 工作流",
    "cron": "Cron 定時任務",
    "tts": "語音合成",
    "embedding": "向量嵌入",
    "knowledge-graph": "知識圖譜",
    "n8n": "n8n 工作流自動化",
    "sqlite": "SQLite 操作",
    "docker": "Docker 容器化",
    "wsl": "WSL2 環境",
    "chrome": "Chrome CDP 自動化",
}


def analyze_tags(rows):
    """分析標籤，找孤立和缺失"""
    all_tags = []
    for row in rows:
        tags_str = row[4]  # tags column
        if tags_str and tags_str not in ("null", "", "[]"):
            try:
                tags = json.loads(tags_str) if tags_str.startswith("[") else tags_str.split(",")
                all_tags.extend([t.strip().lower() for t in tags if t.strip()])
            except (json.JSONDecodeError, TypeError):
                pass

    tag_counts = Counter(all_tags)
    isolated = {t: c for t, c in tag_counts.items() if c == 1}
    popular = {t: c for t, c in tag_counts.most_common(20)}

    return isolated, popular


def check_expected_topics(rows):
    """檢查預期主題是否都有對應知識"""
    titles = [row[1].lower() for row in rows if row[1]]
    contents = " ".join(row[6] or "" for row in rows).lower()

    missing = []
    for key, label in EXPECTED_TOPICS.items():
        found_in_title = any(key in t for t in titles)
        found_in_content = key in contents
        if not found_in_title and not found_in_content:
            missing.append({"topic": key, "label": label})

    return missing


def check_error_without_knowledge(rows):
    """找有 error 但沒有對應 knowledge/technique 的主題"""
    errors = [row for row in rows if row[3] == "error"]
    techniques = set()
    for row in rows:
        if row[3] in ("technique", "concept"):
            title_words = set((row[1] or "").lower().split())
            techniques.update(title_words)

    orphan_errors = []
    for err in errors:
        title = (err[1] or "").lower()
        # 檢查是否有對應的 technique
        has_fix = any(kw in title for kw in ["修復", "解決", "最佳實踐", "指南", "fix", "solution"])
        if not has_fix:
            orphan_errors.append({
                "id": err[0],
                "title": err[1][:60] if err[1] else "",
                "trust": err[2],
            })

    return orphan_errors


def suggest(db_path=DB_PATH):
    """主分析"""
    db = GuardrailsDB(db_path)
    db.connect()

    rows = db.conn.execute(
        "SELECT id, title, trust, category, tags, layer, content_raw "
        "FROM knowledge ORDER BY id"
    ).fetchall()

    suggestions = []

    # 1. 標籤分析
    isolated, popular = analyze_tags(rows)
    if isolated:
        suggestions.append({
            "type": "孤立標籤",
            "description": "只出現 1 次的標籤，可能需要補充同類知識或合併標籤",
            "count": len(isolated),
            "items": list(isolated.keys())[:15],
        })

    # 2. 預期主題缺失
    missing = check_expected_topics(rows)
    if missing:
        suggestions.append({
            "type": "主題缺口",
            "description": "預期應有但找不到對應知識的技術主題",
            "count": len(missing),
            "items": [m["label"] for m in missing],
        })

    # 3. 有 error 沒有 technique
    orphans = check_error_without_knowledge(rows)
    if orphans:
        suggestions.append({
            "type": "錯誤缺少解法",
            "description": "有錯誤記錄但缺少對應的解決方案/最佳實踐",
            "count": len(orphans),
            "items": [{"id": o["id"], "title": o["title"]} for o in orphans[:10]],
        })

    # 4. 低 trust 需要審核
    low_trust = [{"id": r[0], "title": (r[1] or "")[:50], "trust": r[2]}
                 for r in rows if r[2] < 0.4]
    if low_trust:
        suggestions.append({
            "type": "低信任待審",
            "description": "trust < 0.4 的知識，需要人工審核或補充",
            "count": len(low_trust),
            "items": low_trust[:10],
        })

    # 5. 統計
    by_category = Counter(r[3] or "未分類" for r in rows)
    by_layer = Counter(r[5] or "未分層" for r in rows)

    stats = {
        "total": len(rows),
        "by_category": dict(by_category),
        "by_layer": dict(by_layer),
    }

    db.close()
    return suggestions, stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Guardrails 主動建議")
    parser.add_argument("--json", action="store_true", help="JSON 格式輸出")
    args = parser.parse_args()

    suggestions, stats = suggest()

    if args.json:
        print(json.dumps({"suggestions": suggestions, "stats": stats},
                         ensure_ascii=False, indent=2))
    else:
        print(f"📚 知識庫總覽: {stats['total']} 筆")
        print(f"   分類: {dict(stats['by_category'])}")
        print(f"   分層: {dict(stats['by_layer'])}")
        print()

        if not suggestions:
            print("✅ 沒有發現知識缺口")
        else:
            print(f"🔍 發現 {len(suggestions)} 類建議:\n")
            for s in suggestions:
                print(f"  📌 {s['type']} ({s['count']} 筆)")
                print(f"     {s['description']}")
                if isinstance(s['items'], list) and s['items']:
                    for item in s['items'][:5]:
                        if isinstance(item, dict):
                            print(f"     - ID{item.get('id', '?')}「{item.get('title', item.get('label', '?'))[:50]}」")
                        else:
                            print(f"     - {item}")
                print()
# Trigger CI test
