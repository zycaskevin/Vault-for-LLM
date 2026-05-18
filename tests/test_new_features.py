#!/usr/bin/env python3
"""Test new features: convergence, freshness, claims, reranker"""
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from guardrails_lite.guardrails_db import GuardrailsDB
from guardrails_lite.guardrails_search import GuardrailsSearch
from guardrails_lite.guardrails_compile import simple_aaak_compress, extract_claims

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
# 1. DB Schema 升級測試
# ============================================
print("=" * 60)
print("1. CONVERGENCE + FRESHNESS FIELDS")
print("=" * 60)

db = GuardrailsDB(tempfile.mktemp(suffix='.db'))
db.connect()

kid = db.add_knowledge(title='Test convergence', content_raw='Test content for convergence check', category='concept', tags='test,convergence')

db.update_convergence(kid, 'complete', 0.85)
k = db.get_knowledge(kid)
check("convergence_status = complete", k['convergence_status'] == 'complete', f"got {k['convergence_status']}")
check("convergence_score = 0.85", k['convergence_score'] == 0.85, f"got {k['convergence_score']}")
check("convergence_checked_at not empty", k['convergence_checked_at'] != '', 'should not be empty')

db.update_freshness(kid, 0.7)
k = db.get_knowledge(kid)
check("freshness = 0.7", k['freshness'] == 0.7, f"got {k['freshness']}")
check("last_verified not empty", k['last_verified'] != '', 'should not be empty')

stats = db.stats()
check("stats has convergence", 'convergence' in stats, f"got {list(stats.keys())}")
check("stats has avg_freshness", 'avg_freshness' in stats, f"got {list(stats.keys())}")
check("convergence stats correct", stats['convergence'].get('complete', 0) >= 1, f"got {stats['convergence']}")

db.close()

# ============================================
# 2. Claims 提取測試
# ============================================
print("\n" + "=" * 60)
print("2. CLAIMS EXTRACTION")
print("=" * 60)

test_content = """# 測試知識

- sqlite-vec 擴展需要在每次連線時重新載入
- WAL 模式建議搭配使用，避免資料損壞
- 虛擬表找不到是常見錯誤

1. 先安裝 sqlite-vec
2. 然後執行載入指令
3. 最後設定 WAL 模式

普通段落：這是一個很長的測試段落，用於驗證原子主張提取功能是否正常運作。
"""

claims = extract_claims("sqlite-vec 測試", test_content)
check("Claims extracted", len(claims) > 0, f"got {len(claims)} claims")
check("Claims have IDs", all('id' in c for c in claims), "missing id field")
check("Claims have spans", all('span' in c for c in claims), "missing span field")
check("Claims have text", all('claim' in c for c in claims), "missing claim field")
check("First claim content", "sqlite-vec" in claims[0]['claim'] if claims else "", f"got {claims[0]['claim'] if claims else 'no claims'}")

# ============================================
# 3. AAAK 壓縮（含 CLAIMS 段）測試
# ============================================
print("\n" + "=" * 60)
print("3. AAAK COMPRESSION WITH CLAIMS")
print("=" * 60)

compressed = simple_aaak_compress("sqlite-vec 測試", test_content)
check("Compressed contains TITLE", "TITLE:sqlite-vec 測試" in compressed, compressed[:60])
check("Compressed contains CLAIMS", "CLAIMS:" in compressed, "no CLAIMS section")
check("Compressed contains claim IDs", "[C1]" in compressed, "no [C1]")
check("Compressed contains spans", "L" in compressed, "no L-span markers")

# 向後相容：舊格式（沒有 CLAIMS）仍然有效
old_content = "This is a simple test."
old_compressed = simple_aaak_compress("簡單測試", old_content)
check("Old format backward compatible", "TITLE:簡單測試" in old_compressed, old_compressed[:60])

# ============================================
# 4. 搜尋 Reranker 測試
# ============================================
print("\n" + "=" * 60)
print("4. SEARCH RERANKER")
print("=" * 60)

db2 = GuardrailsDB(tempfile.mktemp(suffix='.db2'))
db2.connect()

# 建立測試資料
kid1 = db2.add_knowledge(title="sqlite-vec 踩坑", content_raw="sqlite-vec 擴展需要每次連線重新載入", category="error", tags="sqlite-vec,踩坑", trust=0.9)
db2.update_freshness(kid1, 0.9)

kid2 = db2.add_knowledge(title="Ollama 超時處理", content_raw="Ollama 本地推理超時常見原因", category="error", tags="ollama,timeout", trust=0.5)
db2.update_freshness(kid2, 0.3)

search = GuardrailsSearch(db2)
results = search.search("sqlite", mode="keyword", limit=10, use_rerank=True)
check("Search with rerank works", len(results) > 0, f"got {len(results)} results")

if results:
    r = results[0]
    check("Rerank score present", "_rerank_score" in r, f"keys: {list(r.keys())}")
    check("Best claim present", "best_claim" in r, f"keys: {list(r.keys()) if r else 'no results'}")
    # 高 trust + 高 freshness 應排在前面
    check("Higher trust ranks higher", r['title'] == "sqlite-vec 踩坑",
          f"expected 'sqlite-vec 踩坑', got '{r['title']}'")

# 測試 no_rerank
results_no_rerank = search.search("sqlite", mode="keyword", limit=10, use_rerank=False)
check("Search without rerank works", len(results_no_rerank) > 0, f"got {len(results_no_rerank)} results")
if results_no_rerank:
    check("No rerank score when disabled", "_rerank_score" not in results_no_rerank[0],
          "rerank_score should not be present when disabled")

db2.close()

# ============================================
# 5. Convergence Check CLI 測試
# ============================================
print("\n" + "=" * 60)
print("5. CONVERGENCE CHECK (dry run)")
print("=" * 60)

# Quick dry run test
import subprocess
PROJECT_ROOT = Path(__file__).resolve().parent.parent
result = subprocess.run(
    [sys.executable,
     str(PROJECT_ROOT / "scripts" / "convergence_check.py"),
     "--limit", "1", "--min-trust", "0.9"],
    capture_output=True, text=True, timeout=30, cwd=str(PROJECT_ROOT)
)
check("convergence_check.py runs", result.returncode == 0, f"exit code: {result.returncode}")
check("convergence output has results", "找到" in result.stdout or "沒有" in result.stdout,
      f"stdout: {result.stdout[:200]}")

# ============================================
# RESULTS
# ============================================
print("\n" + "=" * 60)
print(f"RESULTS: {passed}/{passed+failed} PASSED, {failed} FAILED")
if failed == 0:
    print("ALL TESTS COMPLETE 🎉")
else:
    print("SOME TESTS FAILED — see above for details")
print("=" * 60)