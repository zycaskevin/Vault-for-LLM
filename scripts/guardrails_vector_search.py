#!/usr/bin/env python3.12
"""
Guardrails 向量搜尋 — 用 pgvector 做語義搜尋
用法: python3.12 guardrails_vector_search.py "查詢" [--layer 3] [--category error] [--limit 5]
"""
import os, sys, json, urllib.request, argparse
from pathlib import Path
from sentence_transformers import SentenceTransformer

_model = None

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    return _model

def load_env():
    env_file = Path.home() / '.hermes' / '.env'
    if env_file.exists():
        for line in env_file.read_text().split('\n'):
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                os.environ.setdefault(k, v)

def vector_search(query, layer=None, category=None, limit=5, threshold=0.25):
    load_env()
    url = os.environ.get('SUPABASE_URL', '')
    key = os.environ.get('SUPABASE_SERVICE_KEY', '')
    headers = {'apikey': key, 'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    
    model = get_model()
    embedding = model.encode(query).tolist()
    
    params = {}
    params['query_embedding'] = embedding
    params['match_threshold'] = threshold
    params['match_count'] = limit
    if layer is not None:
        params['filter_layer'] = layer
    if category:
        params['filter_category'] = category
    
    data = json.dumps(params).encode('utf-8')
    req = urllib.request.Request(f'{url}/rest/v1/rpc/match_guardrails', data=data, headers=headers)
    
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f"Error: {e.code} {body}", file=sys.stderr)
        return []

def main():
    parser = argparse.ArgumentParser(description='Guardrails 向量搜尋')
    parser.add_argument('query', help='搜尋詞（支援中英文）')
    parser.add_argument('--layer', type=int, help='限制層級（0-3）')
    parser.add_argument('--category', help='限制分類')
    parser.add_argument('--limit', type=int, default=5, help='最大結果數')
    parser.add_argument('--threshold', type=float, default=0.25, help='相似度門檻（0-1）')
    args = parser.parse_args()
    
    results = vector_search(args.query, layer=args.layer, category=args.category, 
                           limit=args.limit, threshold=args.threshold)
    
    if not results:
        print(f"搜尋 '{args.query}' 無結果（門檻: {args.threshold}）")
        return
    
    print(f"搜尋 '{args.query}' — 找到 {len(results)} 筆：\n")
    for i, r in enumerate(results, 1):
        sim = r.get('similarity', 0)
        title = r.get('title', '?')[:50]
        cat = r.get('category', '?')
        layer = r.get('layer', '?')
        aaak = (r.get('content_aaak', '') or '')[:100]
        print(f"**{i}. [L{layer}/{cat}] {title}** (相似度: {sim:.3f})")
        if aaak:
            print(f"   {aaak}...")
        print()

if __name__ == '__main__':
    main()