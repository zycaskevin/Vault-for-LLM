"""
從 Supabase 匯入所有百科知識到本地 Guardrails Lite DB。

步驟：
1. 從 Supabase guardrails_knowledge 表抓取全部資料
2. 清除本地 DB 舊資料（保留 schema）
3. 逐筆寫入本地 DB
4. 產生嵌入
5. 建構圖譜
"""

import os
import json
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('/home/zycas/.hermes/.env')

from guardrails_lite.guardrails_db import GuardrailsDB
from guardrails_lite.guardrails_embed import create_embedding_provider
from guardrails_lite.guardrails_graph import GuardrailsGraph

# ── Supabase 連線 ──────────────────────────────────────────
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_ANON_KEY') or os.getenv('SUPABASE_KEY')
sb = create_client(url, key)

# ── 取得全部資料 ──────────────────────────────────────────
print("📥 從 Supabase 抓取 123 筆百科...")
result = sb.table('guardrails_knowledge').select('*').execute()
rows = result.data
print(f"   抓到 {len(rows)} 筆")

# ── 本地 DB ───────────────────────────────────────────────
db_path = "guardrails.db"
db = GuardrailsDB(db_path)
db.connect()

# 清除舊資料（保留 schema）
print("🗑️ 清除本地 DB 舊資料...")
db.conn.execute("DELETE FROM edges")
db.conn.execute("DELETE FROM entity_knowledge")
db.conn.execute("DELETE FROM entities")
db.conn.execute("DELETE FROM lint_cache")
db.conn.execute("DELETE FROM knowledge")
db.conn.execute("DELETE FROM knowledge_vec")
db.conn.commit()
print("   ✅ 舊資料已清除")

# ── 逐筆寫入 ────────────────────────────────────────────
print("📝 寫入本地 DB...")
errors = 0
for i, r in enumerate(rows):
    # 處理 tags：JSON 陣列 → 逗號分隔字串
    tags_raw = r.get('tags', '')
    if isinstance(tags_raw, list):
        tags = ','.join(str(t) for t in tags_raw)
    elif isinstance(tags_raw, str):
        # 嘗試 parse JSON array
        try:
            parsed = json.loads(tags_raw)
            tags = ','.join(str(t) for t in parsed) if isinstance(parsed, list) else tags_raw
        except (json.JSONDecodeError, TypeError):
            tags = tags_raw
    else:
        tags = ''

    # 處理 layer：數字 → L{N}
    layer_raw = r.get('layer', 3)
    if isinstance(layer_raw, (int, float)):
        layer = f"L{int(layer_raw)}"
    elif isinstance(layer_raw, str) and layer_raw.isdigit():
        layer = f"L{layer_raw}"
    else:
        layer = layer_raw or "L3"

    # 處理 trust
    trust = float(r.get('trust', 0.5) or 0.5)

    try:
        kid = db.add_knowledge(
            title=r.get('title', '').strip(),
            content_raw=r.get('content_raw', '') or '',
            layer=layer,
            category=r.get('category', 'general') or 'general',
            tags=tags,
            trust=trust,
            source=r.get('source', 'supabase') or 'supabase',
            content_aaak=r.get('content_aaak', '') or '',
        )
        if (i + 1) % 20 == 0:
            print(f"   {i+1}/{len(rows)}...")
    except Exception as e:
        errors += 1
        print(f"   ❌ 寫入失敗 ID={r.get('id')}: {e}")

print(f"   ✅ 寫入完成: {len(rows)-errors}/{len(rows)} 成功, {errors} 失敗")

# ── 產生嵌入 ────────────────────────────────────────────
print("\n🔨 產生嵌入向量...")
try:
    embed = create_embedding_provider(provider="onnx", model_key="mix")
    rows_local = db.conn.execute("SELECT id, content_aaak, content_raw FROM knowledge").fetchall()
    done = 0
    for row in rows_local:
        kid = row["id"]
        # 用 content_aaak 如果有，否則用 content_raw
        text = row["content_aaak"] or row["content_raw"] or ""
        if not text.strip():
            continue
        try:
            vec = embed.encode(text)[0]
            db.add_embedding(kid, vec)
            done += 1
            if done % 20 == 0:
                print(f"   嵌入 {done}/{len(rows_local)}...")
        except Exception as e:
            print(f"   ⚠️ 嵌入失敗 ID={kid}: {e}")
    print(f"   ✅ 嵌入完成: {done}/{len(rows_local)}")
except Exception as e:
    print(f"   ❌ 嵌入模組錯誤: {e}")

# ── 建構圖譜 ────────────────────────────────────────────
print("\n🕸️ 建構圖譜...")
graph = GuardrailsGraph(db)
result = graph.infer_all()
print(f"   掃描: {result['total_knowledge']} 條")
print(f"   實體: {result['entities_created']}")
print(f"   邊: {result['edges_created']}")

# ── 統計 ──────────────────────────────────────────────
stats = db.stats()
graph_stats = graph.stats()
print(f"\n📊 最終統計:")
print(f"   知識筆數: {stats['knowledge_count']}")
print(f"   嵌入筆數: {stats['embedding_count']}")
print(f"   圖譜邊數: {graph_stats['edges_total']}")
print(f"   圖譜實體: {graph_stats['entities_total']}")
print(f"   連通節點: {graph_stats['connected_nodes']}")
print(f"   DB 大小: {stats['db_size_mb']} MB")

db.close()
print("\n✅ 全部完成！")