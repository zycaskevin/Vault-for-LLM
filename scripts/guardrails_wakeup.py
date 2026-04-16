#!/usr/bin/env python3
"""
Guardrails Wake-Up Script — Supabase 優先

分層策略：
- L0/L1: 本地檔案（每次對話都需要，本地讀最快）
- L2: Supabase 查詢（按需，支援語義搜尋）
- L3: Supabase 查詢（AAAK 格式，按需搜尋）
"""

import os
import sys
import json
import urllib.request
from pathlib import Path
from datetime import datetime

GUARDRAILS_DIR = Path(os.environ.get('GUARDRAILS_PATH', str(Path.home() / '.hermes' / 'Guardrails')))
L0_DIR = GUARDRAILS_DIR / 'L0-identity'
L1_DIR = GUARDRAILS_DIR / 'L1-core-facts'
L2_DIR = GUARDRAILS_DIR / 'L2-context'


def load_env():
    """多路徑 .env 讀取：環境變數 > .env.local > .env > ~/.hermes/.env"""
    env_paths = [
        Path.cwd() / '.env.local',
        Path.cwd() / '.env',
        Path.home() / '.hermes' / '.env',
    ]
    for env_file in env_paths:
        if env_file.exists():
            for line in env_file.read_text().split('\n'):
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k, v)
            break


def supabase_query(params: str, limit: int = 20) -> list:
    """查詢 Supabase guardrails_knowledge 表"""
    url = os.environ.get('SUPABASE_URL', '')
    key = os.environ.get('SUPABASE_SERVICE_KEY', '')
    if not url or not key:
        return []
    
    table_url = f"{url}/rest/v1/guardrails_knowledge?{params}&limit={limit}"
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
    }
    
    try:
        req = urllib.request.Request(table_url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        print(f"Supabase 查詢失敗: {e}", file=sys.stderr)
        return []


# ============================================================
# L0: Identity（本地讀取，最快）
# ============================================================

def load_identity() -> str:
    identity_file = L0_DIR / 'identity.md'
    if identity_file.exists():
        content = identity_file.read_text(encoding='utf-8')
        return f"## L0: Identity\n{content[:500]}\n"
    
    return """## L0: Identity
# Arthur Liao (亞瑟)
- 技術總監，台北
- 繁體中文、條列式、直接務實
- Hermes Agent + Ollama Cloud
"""


# ============================================================
# L1: Core Facts（本地讀取）
# ============================================================

def load_core_facts() -> str:
    parts = []
    for f in sorted(L1_DIR.glob('*.md')):
        if f.name == 'README.md':
            continue
        content = f.read_text(encoding='utf-8')
        parts.append(f"### {f.stem}\n{content[:300]}...\n")
    
    if not parts:
        parts = ["（無核心事實）"]
    
    return f"## L1: Core Facts\n{''.join(parts)}\n"


# ============================================================
# L2: Context（Supabase 查詢）
# ============================================================

def load_context_supabase() -> str:
    """從 Supabase 載入 L2 層"""
    rows = supabase_query("layer=eq.2&order=updated_at.desc&select=title,category,content_aaak", limit=5)
    
    if not rows:
        # Fallback 到本地
        return load_context_local()
    
    parts = []
    for r in rows:
        parts.append(f"- [{r['category']}] {r['title']}")
    
    return f"## L2: Context\n{''.join(parts)}\n"


def load_context_local() -> str:
    """本地 fallback"""
    parts = []
    total = 0
    
    for sub in ['recent-sessions', 'active-skills', 'current-topics']:
        f = L2_DIR / sub / 'current.md' if sub != 'active-skills' else L2_DIR / sub / 'active.md'
        if f.exists():
            content = f.read_text(encoding='utf-8')
            if total + len(content) < 600:
                parts.append(f"### {sub}\n{content}\n")
                total += len(content)
    
    if not parts:
        return ""
    return f"## L2: Context\n{''.join(parts)}\n"


# ============================================================
# L3: Knowledge Search（Supabase 查詢）
# ============================================================

def search_knowledge(query: str, category: str = '', limit: int = 5) -> list:
    """搜尋 L3 知識庫（語義擴充 + 向量搜尋混合版）"""
    import urllib.parse
    
    # 同義詞擴充
    SYNONYMS = {
        '記憶': ['memory', '記憶體', 'memory system', '記憶系統'],
        'memory': ['記憶', '記憶系統', 'memory system', '記憶體'],
        '部署': ['deploy', 'deployment', '發佈', 'release', 'vercel', 'Vercel'],
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
        '知識': ['knowledge', '百科', 'encyclopedia', 'wiki', '知識庫'],
        'knowledge': ['知識', '百科', 'encyclopedia', 'wiki', '知識庫'],
        '代理': ['agent', 'assistant', '助手', 'bot', '機器人'],
        'agent': ['代理', 'assistant', '助手', 'bot', '機器人'],
        '配置': ['config', 'configuration', '設定', '組態'],
        'config': ['配置', '設定', 'configuration', '組態'],
        '模型': ['model', 'LLM', '語言模型', 'AI', '大模型'],
        '模型': ['model', 'LLM', '語言模型', 'AI', '大模型'],
        'vllm': ['vLLM', '推理', 'inference', 'GPU', '加速'],
        'ollama': ['Ollama', '推理', 'inference', '本地模型'],
        'telegram': ['TG', '電報', '機器人', 'bot', '通知'],
        'cron': ['定時', '排程', '排程器', 'scheduler', '定時任務'],
        '技能': ['skill', '能力', '工具'],
        'skill': ['技能', '能力', '工具'],
        'token': ['token消耗', '成本', 'cost', '費用'],
        '成本': ['cost', 'token', '費用', '開銷'],
        '成本控制': ['cost control', '成本', '費用', '開銷'],
    }
    
    # Step 1: 同義詞擴充搜尋（主要）
    terms = set([query])
    q_lower = query.lower()
    for key, synonyms in SYNONYMS.items():
        if key.lower() in q_lower or any(s.lower() in q_lower for s in synonyms if isinstance(s, str)):
            for s in synonyms:
                terms.add(str(s))
            terms.add(key)
    # Build OR conditions for all terms (title, content_aaak, tags)
    conditions = []
    for term in terms:
        encoded = urllib.parse.quote(term, safe='')
        conditions.append(f"title.ilike.*{encoded}*")
        conditions.append(f"content_aaak.ilike.*{encoded}*")
        conditions.append(f"tags.cs.{{{encoded}}}")
    
    or_clause = ','.join(conditions)
    params = f"layer=eq.3&or=({or_clause})&order=trust.desc&select=id,title,category,tags,content_aaak,trust,source&limit={limit * 2}"
    
    if category:
        params += f"&category=eq.{category}"
    
    results = supabase_query(params, limit=limit * 2)
    
    # Step 2: 向量搜尋（補充）— 如果有 python3.12 + sentence-transformers
    vector_results = []
    try:
        import subprocess
        vcmd = [
            'python3.12',
            str(Path.home() / '.hermes/Guardrails/scripts/guardrails_vector_search.py'),
            query, '--limit', str(3), '--threshold', '0.35'
        ]
        if category:
            vcmd.extend(['--category', category])
        vproc = subprocess.run(vcmd, capture_output=True, text=True, timeout=30)
        if vproc.returncode == 0:
            # Parse vector results from output
            for line in vproc.stdout.split('\n'):
                if line.strip().startswith('**'):
                    vector_results.append(line)
    except Exception:
        pass  # Vector search is optional, don't block
    
    # Deduplicate and score by relevance
    seen = set()
    scored = []
    for r in results:
        if r['title'] in seen:
            continue
        seen.add(r['title'])
        text = (r.get('title', '') + ' ' + (r.get('content_aaak', '') or '')).lower()
        score = sum(1 for t in terms if t.lower() in text) + r.get('trust', 0.5)
        r['_score'] = score
        r['_source'] = 'synonym'
        scored.append(r)
    
    scored.sort(key=lambda x: x['_score'], reverse=True)
    return scored[:limit]


def format_search_results(results: list) -> str:
    """格式化搜尋結果"""
    if not results:
        return "查無相關知識"
    
    output = []
    for i, r in enumerate(results, 1):
        output.append(f"**{i}. [{r['category']}] {r['title']}** (trust: {r.get('trust', 0.5)})")
        if r.get('content_aaak'):
            output.append(f"   {r['content_aaak'][:150]}...")
        if r.get('source'):
            output.append(f"   來源: {r['source']}")
        output.append("")
    
    return "\n".join(output)


# ============================================================
# 主程式
# ============================================================

def generate_wakeup_prompt(include_l2: bool = True) -> str:
    parts = []
    parts.append(load_identity())
    parts.append(load_core_facts())
    
    if include_l2:
        parts.append(load_context_supabase())
    
    result = "\n".join(parts)
    tokens = len(result) // 4
    
    header = f"""---
# Guardrails Wake-Up Prompt (Supabase)
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Estimated Tokens: ~{tokens}
Layers: L0 + L1{'+ L2' if include_l2 else ''}
---

"""
    return header + result


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Guardrails Wake-Up')
    parser.add_argument('--output', '-o', help='輸出檔案路徑')
    parser.add_argument('--print', '-p', action='store_true', help='直接列印')
    parser.add_argument('--no-l2', action='store_true', help='不載入 L2 層')
    parser.add_argument('--search', '-s', help='搜尋 L3 知識庫')
    parser.add_argument('--category', '-c', help='按分類搜尋')
    parser.add_argument('--stats', action='store_true', help='顯示 Supabase 統計')
    
    args = parser.parse_args()
    load_env()
    
    if args.stats:
        rows = supabase_query("select=layer,category&limit=1000", limit=1000)
        by_layer = {}
        by_cat = {}
        for r in rows:
            by_layer.setdefault(r['layer'], 0)
            by_layer[r['layer']] += 1
            by_cat.setdefault(r['category'], 0)
            by_cat[r['category']] += 1
        print(f"總計: {len(rows)} 筆")
        print("\n按層:")
        for l in sorted(by_layer):
            print(f"  L{l}: {by_layer[l]} 筆")
        print("\n按分類:")
        for c in sorted(by_cat):
            print(f"  {c}: {by_cat[c]} 筆")
        return
    
    if args.search:
        results = search_knowledge(args.search, args.category or '')
        kb_output = format_search_results(results)
        
        # Also search fact_store for related facts
        try:
            from pathlib import Path as _Path
            import sqlite3
            fs_db = _Path.home() / '.hermes/memory_store.db'
            if fs_db.exists():
                conn = sqlite3.connect(str(fs_db))
                c = conn.cursor()
                query_terms = args.search.lower().split()
                facts = []
                for row in c.execute("SELECT content, category, trust_score FROM facts").fetchall():
                    if any(t in row[0].lower() for t in query_terms):
                        facts.append(row)
                conn.close()
                if facts:
                    kb_output += "\n\n---\n**📌 事實記憶 (fact_store):**\n"
                    for content, cat, trust in facts[:3]:
                        kb_output += f"- [{cat}] {content} (trust: {trust})\n"
        except Exception:
            pass
        
        print(kb_output)
        return
    
    if args.print or not args.output:
        print(generate_wakeup_prompt(include_l2=not args.no_l2))
    else:
        content = generate_wakeup_prompt(include_l2=not args.no_l2)
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        print(f"Wake-up prompt 已儲存至：{path}")


if __name__ == '__main__':
    main()