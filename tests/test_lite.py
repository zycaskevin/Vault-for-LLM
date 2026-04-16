"""
Guardrails Lite 端到端測試。
"""

import os
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from guardrails_lite.guardrails_db import GuardrailsDB
from guardrails_lite.guardrails_search import GuardrailsSearch
from guardrails_lite.guardrails_compile import GuardrailsCompiler


def test_db_crud():
    """測試資料庫 CRUD"""
    db_path = tempfile.mktemp(suffix=".db")
    db = GuardrailsDB(db_path)
    db.connect()

    # 新增
    kid = db.add_knowledge(
        title="測試知識",
        content_raw="這是測試內容",
        category="test",
        tags="test,unit",
        trust=0.8,
    )
    assert kid > 0, f"新增失敗，kid={kid}"

    # 讀取
    k = db.get_knowledge(kid)
    assert k["title"] == "測試知識"
    assert k["category"] == "test"

    # 更新
    db.update_knowledge(kid, title="更新後的知識")
    k = db.get_knowledge(kid)
    assert k["title"] == "更新後的知識"

    # 列表
    items = db.list_knowledge(min_trust=0.5)
    assert len(items) == 1

    # 刪除
    assert db.delete_knowledge(kid)
    items = db.list_knowledge()
    assert len(items) == 0

    db.close()
    os.unlink(db_path)
    print("✅ test_db_crud")


def test_keyword_search():
    """測試關鍵字搜尋"""
    db_path = tempfile.mktemp(suffix=".db")
    db = GuardrailsDB(db_path)
    db.connect()

    db.add_knowledge("vLLM 超時", "vLLM timeout GPU retry", category="error", trust=0.9)
    db.add_knowledge("sqlite-vec 搜尋", "向量搜尋架構", category="architecture", trust=0.8)

    search = GuardrailsSearch(db, embed_provider=None)
    results = search.search("GPU", mode="keyword")
    assert len(results) > 0, "關鍵字搜尋應該有結果"
    assert "vLLM" in results[0]["title"]

    results = search.search("向量", mode="keyword")
    assert len(results) > 0

    db.close()
    os.unlink(db_path)
    print("✅ test_keyword_search")


def test_compile_and_search():
    """測試編譯 + 搜尋"""
    project_dir = tempfile.mkdtemp()
    raw_dir = Path(project_dir) / "raw"
    raw_dir.mkdir()

    # 寫測試 raw 檔案
    (raw_dir / "test.md").write_text("""---
title: 編譯測試
category: test
layer: L3
tags: test,compile
trust: 0.7
---
# 編譯測試
這是編譯測試內容。
""", encoding="utf-8")

    db_path = Path(project_dir) / "guardrails.db"
    db = GuardrailsDB(str(db_path))
    db.connect()

    compiler = GuardrailsCompiler(project_dir, db=db, embed_provider=None)
    stats = compiler.compile()

    assert stats["total_files"] == 1, f"應該有1個檔案，實際{stats}"
    assert stats["new"] == 1, f"應該新增1筆，實際{stats}"

    # 搜尋
    search = GuardrailsSearch(db, embed_provider=None)
    results = search.search("編譯", mode="keyword")
    assert len(results) > 0

    # 重複編譯應該跳過
    stats2 = compiler.compile()
    assert stats2["skipped"] == 1

    db.close()
    print("✅ test_compile_and_search")


def test_lint():
    """測試 Lint"""
    db_path = tempfile.mktemp(suffix=".db")
    db = GuardrailsDB(db_path)
    db.connect()

    # 正常知識
    db.add_knowledge("正常知識", "有內容", trust=0.8)

    # 空內容知識
    db.add_knowledge("空知識", "", trust=0.5)

    # 信任度過低
    db.add_knowledge("低信任", "有內容但信任度低", trust=0.1)

    items = db.list_knowledge(min_trust=0.0)
    assert len(items) == 3

    db.close()
    os.unlink(db_path)
    print("✅ test_lint")


if __name__ == "__main__":
    test_db_crud()
    test_keyword_search()
    test_compile_and_search()
    test_lint()
    print("\n🎉 All tests passed!")