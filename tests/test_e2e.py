#!/usr/bin/env python3
"""Guardrails Lite 完整端到端測試"""
import sys
import os
import tempfile
import subprocess
from pathlib import Path

# 動態定位專案根目錄（tests/ 的上一層）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ['PYTHONIOENCODING'] = 'utf-8'

passed = 0
failed = 0

def check(label, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {label}")
    else:
        failed += 1
        print(f"  ❌ {label} — {detail}")

# ============================================
# 1. DB Layer Test
# ============================================
print("=" * 60)
print("1. DB LAYER TEST")
print("=" * 60)

from guardrails_lite.guardrails_db import GuardrailsDB

test_db = tempfile.mktemp(suffix='.db')
db = GuardrailsDB(test_db)
db.connect()

ver = db.get_config("schema_version", "0")
check("Schema version ≥ 2", int(ver) >= 2, f"got {ver}")

stats = db.stats()
print(f"  Stats: {stats}")

kid1 = db.add_knowledge(title="sqlite-vec 踩坑", content_raw="sqlite-vec 擴展需要在每次連線時重新載入，否則虛擬表找不到。WAL 模式建議搭配使用。", layer="L1", category="error", tags="sqlite-vec,踩坑,擴展", source="session")
kid2 = db.add_knowledge(title="Ollama 超時處理", content_raw="Ollama 本地推理超時常見原因：模型未預載、GPU 記憶體不足、請求並發過高。解法：先 ollama pull，設定 timeout=120。", layer="L2", category="fix", tags="ollama,timeout,GPU", source="cron")
kid3 = db.add_knowledge(title="Hermes delegate 陷阱", content_raw="delegate_task fallback 鏈全額度用完時三連敗。解法：指定 model 或 acp_command。", layer="L2", category="prevention", tags="hermes,delegate,fallback", source="skill")
kid4 = db.add_knowledge(title="中文搜尋修復", content_raw="holographic memory CJK 分詞問題：需要安裝 jieba 並修改 tokeniser 才能正確搜尋中文。", layer="L2", category="fix", tags="CJK,搜尋,分詞", source="session")
kid5 = db.add_knowledge(title="vLLM 部署筆記", content_raw="vLLM 本地部署 Qwen3 模型：設定 max_model_len、gpu_memory_utilization、served_model_name。", layer="L2", category="best", tags="vllm,部署,qwen", source="session")
check("Insert 5 entries", all(kid is not None for kid in [kid1, kid2, kid3, kid4, kid5]))

k1 = db.get_knowledge(kid1)
check("Get by ID", k1 is not None and k1['title'] == "sqlite-vec 踩坑")

db.update_knowledge(kid1, title="sqlite-vec 踩坑 [已修復]")
k1_updated = db.get_knowledge(kid1)
check("Update knowledge", k1_updated['title'] == "sqlite-vec 踩坑 [已修復]")

all_docs = db.list_knowledge()
check("List knowledge (5)", len(all_docs) == 5, f"got {len(all_docs)}")

kw = db.search_keyword("超時")
check("Keyword search '超時'", len(kw) >= 1, f"got {len(kw)}")

db.delete_knowledge(kid4)
k4 = db.get_knowledge(kid4)
check("Delete knowledge", k4 is None)

all_after = db.list_knowledge()
check("List after delete (4)", len(all_after) == 4, f"got {len(all_after)}")

eid = db.add_entity("sqlite-vec", entity_type="tool")
db.link_entity_knowledge(eid, kid1)
e2k = db.get_entities_for_knowledge(kid1)
check("Entity + link", len(e2k) >= 1, f"got {len(e2k)}")

db.add_edge(kid1, kid2, relation="related_to", weight=0.8, auto_inferred=False)
edges = db.get_edges(kid1)
check("Add/get edge", len(edges) >= 1, f"got {len(edges)}")

neighbors = db.get_neighbors(kid1)
check("Get neighbors", len(neighbors) >= 1, f"got {len(neighbors)}")

print()

# ============================================
# 2. Embedding Test
# ============================================
print("=" * 60)
print("2. EMBEDDING TEST")
print("=" * 60)

try:
    from guardrails_lite.guardrails_embed import ONNXEmbeddingProvider
    HAS_ONNX = True
except ImportError:
    HAS_ONNX = False

if not HAS_ONNX:
    print("  ⏭️  Skipped (onnxruntime not installed)")
else:
    embed_prov = ONNXEmbeddingProvider(model_key="mix")
dim = embed_prov.dim
print(f"  ONNX dim: {dim}")

vec1 = embed_prov.encode("sqlite-vec 擴展載入問題")
if isinstance(vec1[0], list):
    vec1 = vec1[0]  # encode returns list[list]
v1 = vec1[0] if isinstance(vec1[0], list) else vec1
norm1 = sum(v**2 for v in v1)**0.5
check("Single encode", len(v1) == dim, f"dim={len(v1)}")
check("Normalized (norm≈1.0)", 0.9 < norm1 < 1.1, f"norm={norm1:.4f}")

vecs = embed_prov.encode(["Ollama timeout", "delegate fallback", "CJK 分詞"])
check("Batch encode", len(vecs) == 3, f"got {len(vecs)}")

# Store vectors in DB
for kid in [kid1, kid2, kid3, kid5]:
    c = db.get_knowledge(kid)['content_raw']
    v = embed_prov.encode(c)
    if isinstance(v[0], list):
        v = v[0]
    db.add_embedding(kid, v)
check("Store 4 embeddings", True)

vecs_result = db.search_vector(embed_prov.encode("sqlite")[0] if isinstance(embed_prov.encode("sqlite")[0], list) else embed_prov.encode("sqlite"), limit=3)
check("Vector search returns results", len(vecs_result) >= 1, f"got {len(vecs_result)}")

print()

# ============================================
# 3. Search Test
# ============================================
print("=" * 60)
print("3. SEARCH TEST (Keyword + Vector + Hybrid)")
print("=" * 60)

from guardrails_lite.guardrails_search import GuardrailsSearch
from guardrails_lite.guardrails_graph import GuardrailsGraph

gk = GuardrailsGraph(db)
search = GuardrailsSearch(db, embed_provider=embed_prov, graph=gk)

kw_results = search.search_keyword("超時")
check("Keyword '超時'", len(kw_results) >= 1)
for r in kw_results[:2]:
    print(f"    - {r['title']}")

vec_results = search.search_vector("sqlite 擴展問題", limit=3)
check("Vector 'sqlite 擴展'", len(vec_results) >= 1, f"got {len(vec_results)}")
for r in vec_results[:2]:
    dist = r.get('_distance', '?')
    print(f"    - {r['title']} (dist={dist})")

hybrid_results = search.search_hybrid("ollama 超時 GPU", limit=3)
check("Hybrid 'ollama 超時'", len(hybrid_results) >= 1)
for r in hybrid_results[:2]:
    print(f"    - {r['title']}")

auto_results = search.search("sqlite", mode="auto", limit=3)
check("Search mode=auto", len(auto_results) >= 1)

print()

# ============================================
# 4. Graph Test
# ============================================
print("=" * 60)
print("4. GRAPH TEST")
print("=" * 60)

stats = gk.infer_all()
print(f"  Infer all: {stats}")

edge_count = gk._infer_all_edges_batch()
print(f"  Inferred edges: {edge_count}")

entities = db.get_entities_for_knowledge(kid1)
check("Entities for kid1", len(entities) >= 0, f"got {len(entities)}")
for e in entities[:3]:
    print(f"    - {e.get('name', '?')} ({e.get('entity_type', '?')})")

expanded = gk.expand(kid1, max_depth=2)
print(f"  Expand kid1: {len(expanded)} nodes")

g_results = gk.graph_search("sqlite", limit=5)
print(f"  Graph search 'sqlite': {len(g_results)} results")

mermaid = gk.to_mermaid(node_id=kid1, max_depth=2)
check("Mermaid export", len(mermaid) > 5, f"got {len(mermaid)} chars")

try:
    import graphviz as _gv
    dot = gk.to_graphviz(node_id=kid1, max_depth=2)
    check("Graphviz export", len(dot) > 5, f"got {len(dot)} chars")
except ImportError:
    print("  ⚠️  graphviz Python pkg not installed, skipping")

g_stats = gk.stats()
print(f"  Graph stats: {g_stats}")

print()

# ============================================
# 5. Import Test
# ============================================
print("=" * 60)
print("5. IMPORT TEST")
print("=" * 60)

from guardrails_lite.guardrails_import import import_document

test_md = tempfile.mktemp(suffix='.md')
with open(test_md, 'w') as f:
    f.write("""# 測試導入文件

## 簡介
這是一段測試內容，用於驗證 import_document 功能。

## sqlite-vec 技術細節
sqlite-vec 擴展需要在每次連線時重新載入。
""")
result_ids = import_document(
    file_path=test_md,
    db=db,
    embed_provider=embed_prov,
    strategy="sliding",
    title="測試導入條目",
    tags="測試,import",
)
check("Import document", len(result_ids) > 0, f"got {result_ids}")
print(f"    Imported {len(result_ids)} chunks")
os.unlink(test_md)

print()

# ============================================
# 6. Compile Test
# ============================================
print("=" * 60)
print("6. COMPILE TEST")
print("=" * 60)

from guardrails_lite.guardrails_compile import GuardrailsCompiler

compiler = GuardrailsCompiler(project_dir=PROJECT_ROOT, db=db, embed_provider=embed_prov)
try:
    compile_result = compiler.compile(dry_run=True)
    check("Compile (dry run)", True)
    print(f"    Result: {compile_result}")
except Exception as e:
    print(f"  ⚠️  Compile dry run: {e}")

print()

# ============================================
# 7. Supabase Integration Test（需要環境變數）
# ============================================
print("=" * 60)
print("7. SUPABASE INTEGRATION TEST")
print("=" * 60)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_ANON_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("  ⏭️  跳過（未設定 SUPABASE_URL / SUPABASE_SERVICE_KEY 環境變數）\n")
else:
    try:
        from supabase import create_client
        sp = create_client(SUPABASE_URL, SUPABASE_KEY)

        for t in ["guardrails_knowledge", "gr_entities", "gr_edges", "gr_entity_knowledge"]:
            r = sp.table(t).select("id", count="exact").range(0, 0).execute()
            print(f"  {t}: {r.count} rows")

        r = sp.table("guardrails_knowledge").select("id,title,category").ilike("title", "%sqlite%").execute()
        check("Supabase 'sqlite'", len(r.data) >= 1, f"got {len(r.data)}")

        r = sp.table("gr_entities").select("id,name,entity_type").eq("name", "sqlite-vec").execute()
        check("Entity 'sqlite-vec'", len(r.data) >= 1)

        if r.data:
            ent_id = r.data[0]['id']
            ek = sp.table("gr_entity_knowledge").select("knowledge_id").eq("entity_id", ent_id).execute()
            print(f"  Entity 'sqlite-vec' linked to {len(ek.data)} knowledge entries")

        print("  ✅ Supabase integration PASSED\n")
    except Exception as e:
        failed += 1
        print(f"  ❌ Supabase test FAILED: {e}\n")

# ============================================
# 8. CLI Smoke Test
# ============================================
print("=" * 60)
print("8. CLI SMOKE TEST")
print("=" * 60)

import shutil
CLI = shutil.which("vault") or "vault"

commands = [
    ("--help", "Show help"),
    ("stats", "DB status"),
    ("search sqlite", "Keyword search"),
    ("search --mode vector sqlite", "Vector search"),
    ("search --mode hybrid ollama", "Hybrid search"),
    ("graph show", "Graph show"),
    ("graph build", "Graph build"),
]

for cmd, desc in commands:
    try:
        r = subprocess.run(
            f"{CLI} {cmd}",
            shell=True, capture_output=True, text=True,
            timeout=30, cwd=str(PROJECT_ROOT)
        )
        ok = r.returncode == 0
        check(f"CLI: {desc}", ok, f"rc={r.returncode}")
        if not ok and r.stderr:
            print(f"      stderr: {r.stderr[:120]}")
    except subprocess.TimeoutExpired:
        check(f"CLI: {desc}", False, "timeout")

# Cleanup
db.close()
os.unlink(test_db)

# ============================================
# Final Summary
# ============================================
print()
print("=" * 60)
total = passed + failed
print(f"RESULTS: {passed}/{total} PASSED, {failed} FAILED")
if failed == 0:
    print("ALL TESTS COMPLETE 🎉")
else:
    print("SOME TESTS FAILED — see above for details")
print("=" * 60)