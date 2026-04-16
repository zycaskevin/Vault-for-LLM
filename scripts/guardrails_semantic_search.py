#!/usr/bin/env python3
"""
Guardrails 語義搜尋 — 輕量方案（不求人版）

不依賴嵌入模型，用三層搜尋實現近似語義搜尋：
1. 關鍵詞搜尋（ilike，已有）
2. 標籤搜尋（tags 列，已有但沒資料）
3. 同義詞擴充（內建中英對照表 + 行業術語）

用法：
  python3 guardrails_semantic_search.py "部署問題"
  python3 guardrails_semantic_search.py "memory system" --layer 3
  python3 guardrails_semantic_search.py "vLLM timeout" --category error
"""

import os
import sys
import json
import urllib.request
import urllib.parse
import argparse
from pathlib import Path
from datetime import datetime


# ============================================================
# 同義詞擴充表
# ============================================================
SYNONYMS = {
    # 中英對照
    '記憶': ['memory', '記憶體', 'memory system', '記憶系統'],
    'memory': ['記憶', '記憶系統', 'memory system', '記憶體'],
    '部署': ['deploy', 'deployment', '發佈', 'release', '佈署', 'vercel', 'Vercel'],
    'deploy': ['部署', '發佈', 'deployment', 'release'],
    '錯誤': ['error', 'bug', 'fault', '失敗', 'fail', '例外', 'exception'],
    'error': ['錯誤', 'bug', 'fault', '失敗', 'fail', 'exception'],
    '超時': ['timeout', 'time out', '逾時', '回應超時'],
    'timeout': ['超時', '逾時', 'time out'],
    '連線': ['connection', 'connect', '連接', '網路'],
    'connection': ['連線', '連接', 'connect', 'network'],
    '資料庫': ['database', 'db', 'supabase', 'SUPA', 'postgres'],
    'database': ['資料庫', 'db', 'supabase', 'postgres'],
    'supabase': ['SUPA', '資料庫', 'database', 'postgres'],
    'SUPA': ['supabase', '資料庫', 'database', 'postgres'],
    '搜尋': ['search', 'query', '查找', '查詢', '檢索'],
    'search': ['搜尋', '查詢', '查找', '檢索', 'query'],
    '壓縮': ['compress', 'compression', 'AAAK', 'abbreviate', '縮寫'],
    'compress': ['壓縮', 'compression', 'AAAK', '縮寫'],
    '知識': ['knowledge', '百科', 'encyclopedia', 'wiki', '知識庫'],
    'knowledge': ['知識', '百科', 'encyclopedia', 'wiki', '知識庫'],
    '代理': ['agent', 'assistant', '代理', '助手', 'bot', '機器人'],
    'agent': ['代理', 'assistant', '助手', 'bot', '機器人'],
    '性能': ['performance', 'speed', '速度', '效率', '效能'],
    'performance': ['性能', '速度', '效率', '效能', 'speed'],
    '安全': ['security', 'auth', '認證', '授權', '權限'],
    'security': ['安全', 'auth', '認證', '授權', '權限'],
    '配置': ['config', 'configuration', '設定', '組態'],
    'config': ['配置', '設定', 'configuration', '組態'],
    '監控': ['monitor', 'monitoring', 'observability', 'log', '日誌'],
    'monitor': ['監控', 'monitoring', 'observability', 'log', '日誌'],
    '模型': ['model', 'LLM', '語言模型', 'AI', '大模型'],
    'model': ['模型', 'LLM', '語言模型', 'AI', '大模型'],
    'vllm': ['vLLM', '推理', 'inference', 'GPU', '加速'],
    'ollama': ['Ollama', '推理', 'inference', '本地模型'],
    'telegram': ['TG', '電報', '機器人', 'bot', '通知'],
    'cron': ['定時', '排程', '排程器', 'scheduler', '定時任務'],
    '技能': ['skill', '技能', '能力', '工具'],
    'skill': ['技能', '能力', '工具'],
    'github': ['GH', 'git', '版本控制', 'repo'],
    '向量': ['vector', 'embedding', '嵌入', 'pgvector'],
    'docker': ['container', '容器', 'Docker', 'podman'],
    'api': ['API', '接口', '端點', 'endpoint'],
    'token': ['token', 'token 消耗', '成本', 'cost'],
    '成本': ['cost', 'token', '費用', '開銷'],
    '成本控制': ['cost control', '成本', '費用', '開銷'],
}


def load_env():
    env_file = Path.home() / '.hermes' / '.env'
    if env_file.exists():
        for line in env_file.read_text().split('\n'):
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                os.environ.setdefault(k, v)


def expand_query(query: str) -> list:
    """用同義詞表擴充搜尋詞"""
    terms = set()
    terms.add(query)  # 原始查詢

    q_lower = query.lower()
    for key, synonyms in SYNONYMS.items():
        if key.lower() in q_lower or any(s.lower() in q_lower for s in synonyms if isinstance(s, str)):
            for s in synonyms:
                terms.add(str(s))
            terms.add(key)

    return list(terms)


def search_supabase(terms: list, layer: int = None, category: str = None, limit: int = 10):
    """在 Supabase 中搜尋，使用擴充的搜尋詞"""
    url = os.environ.get('SUPABASE_URL', '')
    key = os.environ.get('SUPABASE_SERVICE_KEY', '')
    if not url or not key:
        return []

    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
    }

    # Build OR conditions for all search terms
    conditions = []
    for term in terms:
        encoded = urllib.parse.quote(term, safe='')
        conditions.append(f"title.ilike.*{encoded}*")
        conditions.append(f"content_aaak.ilike.*{encoded}*")

    or_clause = ','.join(conditions)

    params = f"?or=({or_clause})&select=id,layer,category,title,content_aaak,trust,source&order=trust.desc"
    if layer is not None:
        params += f"&layer=eq.{layer}"
    if category:
        params += f"&category=eq.{category}"
    params += f"&limit={limit * 3}"  # Get more, then deduplicate

    req = urllib.request.Request(f"{url}/rest/v1/guardrails_knowledge{params}", headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        rows = json.loads(resp.read())
    except Exception as e:
        print(f"搜尋失敗: {e}", file=sys.stderr)
        return []

    # Deduplicate by id and calculate relevance
    seen = set()
    results = []
    for row in rows:
        if row['id'] in seen:
            continue
        seen.add(row['id'])

        # Simple relevance: count how many search terms appear in title/aaak
        text = (row.get('title', '') + ' ' + (row.get('content_aaak', '') or '')).lower()
        score = sum(1 for t in terms if t.lower() in text)
        if score == 0:
            score = 0.1  # Matched via ilike but not in expanded terms
        row['_score'] = score + row.get('trust', 0.5)
        results.append(row)

    # Sort by relevance
    results.sort(key=lambda x: x['_score'], reverse=True)
    return results[:limit]


def format_results(results: list, query: str, expanded: list):
    """格式化搜尋結果"""
    if not results:
        return f"搜尋 '{query}' 無結果\n（擴充詞: {', '.join(expanded[:10])}）"

    lines = [
        f"搜尋 '{query}'",
        f"擴充詞: {', '.join(expanded[:10])}{'...' if len(expanded) > 10 else ''}",
        f"找到 {len(results)} 筆相關知識：\n",
    ]

    for i, r in enumerate(results, 1):
        score = r.pop('_score', 0)
        lines.append(f"**{i}. [{r['category']}] {r['title'][:50]}** (trust: {r.get('trust', '?')}, relevance: {score:.1f})")
        if r.get('content_aaak'):
            aaak = r['content_aaak']
            lines.append(f"   {aaak[:120]}...")
        lines.append("")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Guardrails 語義搜尋（輕量版）')
    parser.add_argument('query', help='搜尋詞（支援中英文）')
    parser.add_argument('--layer', type=int, help='限制層級（0-3）')
    parser.add_argument('--category', help='限制分類')
    parser.add_argument('--limit', type=int, default=10, help='最大結果數')
    parser.add_argument('--expand', action='store_true', help='只顯示擴充詞，不搜尋')

    args = parser.parse_args()
    load_env()

    expanded = expand_query(args.query)

    if args.expand:
        print(f"原始: {args.query}")
        print(f"擴充: {', '.join(expanded)}")
        return

    results = search_supabase(expanded, layer=args.layer, category=args.category, limit=args.limit)
    output = format_results(results, args.query, expanded)
    print(output)


if __name__ == '__main__':
    main()