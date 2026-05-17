"""
Vault-for-LLM 端到端測試。
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from vault.db import VaultDB
from vault.search import VaultSearch
from vault.compiler import VaultCompiler


def test_db_crud():
    """測試資料庫 CRUD"""
    db_path = tempfile.mktemp(suffix=".db")
    db = VaultDB(db_path)
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
    db = VaultDB(db_path)
    db.connect()

    db.add_knowledge("vLLM 超時", "vLLM timeout GPU retry", category="error", trust=0.9)
    db.add_knowledge("sqlite-vec 搜尋", "向量搜尋架構", category="architecture", trust=0.8)

    search = VaultSearch(db, embed_provider=None)
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

    db_path = Path(project_dir) / "vault.db"
    db = VaultDB(str(db_path))
    db.connect()

    compiler = VaultCompiler(project_dir, db=db, embed_provider=None)
    stats = compiler.compile()

    assert stats["total_files"] == 1, f"應該有1個檔案，實際{stats}"
    assert stats["new"] == 1, f"應該新增1筆，實際{stats}"

    # 搜尋
    search = VaultSearch(db, embed_provider=None)
    results = search.search("編譯", mode="keyword")
    assert len(results) > 0

    # 重複編譯應該跳過
    stats2 = compiler.compile()
    assert stats2["skipped"] == 1

    db.close()
    print("✅ test_compile_and_search")


def test_compile_skips_git_commit_hygiene_in_non_git_project(tmp_path, capfd, monkeypatch):
    """編譯非 Git 專案時不應洩漏 git stderr 或誤報 commit 成功。"""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))

    raw_dir = project_dir / "raw"
    raw_dir.mkdir()
    (raw_dir / "sample.md").write_text("""---
title: PyPI Smoke
category: test
layer: L3
tags: smoke
trust: 0.8
---
# PyPI Smoke

First-user flow in a non-Git temp directory should compile cleanly.
""", encoding="utf-8")

    db = VaultDB(str(project_dir / "vault.db"))
    db.connect()
    try:
        compiler = VaultCompiler(project_dir, db=db, embed_provider=None)
        capfd.readouterr()

        stats = compiler.compile()
        captured = capfd.readouterr()

        assert stats["total_files"] == 1
        assert stats["new"] == 1
        assert stats["updated"] == 0
        assert stats["errors"] == 0
        assert "unknown option 'cached'" not in captured.err
        assert "git diff --no-index" not in captured.err
        assert "Git commit" not in captured.out
    finally:
        db.close()


def test_lint():
    """測試 Lint"""
    db_path = tempfile.mktemp(suffix=".db")
    db = VaultDB(db_path)
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


def test_vector_dimension_mismatch_falls_back_to_keyword():
    """Vector/hybrid search should not crash on sqlite-vec dimension mismatch."""
    db_path = tempfile.mktemp(suffix=".db")
    db = VaultDB(db_path)
    db.connect()

    db.add_knowledge(
        "PyPI smoke test",
        "Vault-for-LLM installed from wheel and can add, compile, and search local knowledge.",
        category="test",
        trust=0.9,
    )
    db._vec_available = True

    class MismatchedEmbeddingProvider:
        def encode(self, texts):
            return [[0.0] * 768]

    def raise_dimension_mismatch(*args, **kwargs):
        raise sqlite3.OperationalError(
            'Dimension mismatch for query vector for the "embedding" column. '
            'Expected 384 dimensions but received 768.'
        )

    db.search_vector = raise_dimension_mismatch
    search = VaultSearch(db, embed_provider=MismatchedEmbeddingProvider())

    vector_results = search.search("installed from wheel", mode="vector")
    assert len(vector_results) > 0
    assert vector_results[0]["title"] == "PyPI smoke test"
    assert vector_results[0]["_mode"] == "keyword"

    hybrid_results = search.search("installed from wheel", mode="hybrid")
    assert len(hybrid_results) > 0
    assert hybrid_results[0]["title"] == "PyPI smoke test"

    auto_results = search.search("installed from wheel", mode="auto")
    assert len(auto_results) > 0
    assert auto_results[0]["title"] == "PyPI smoke test"

    db.close()
    os.unlink(db_path)
    print("✅ test_vector_dimension_mismatch_falls_back_to_keyword")


if __name__ == "__main__":
    test_db_crud()
    test_keyword_search()
    test_compile_and_search()
    test_lint()
    test_vector_dimension_mismatch_falls_back_to_keyword()
    print("\n🎉 All tests passed!")
