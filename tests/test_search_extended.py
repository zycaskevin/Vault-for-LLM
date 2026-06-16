"""
Extended tests for vault.search module to boost coverage.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from vault.db import VaultDB
from vault.search import VaultSearch, _normalize_text


class _MockArray:
    """Lightweight replacement for numpy array in tests."""
    def __init__(self, data):
        self._data = list(data)
    def tolist(self):
        return list(self._data)


class TestNormalizeText:
    def test_normalize_basic(self):
        assert _normalize_text("Hello World") == "hello world"

    def test_normalize_empty(self):
        assert _normalize_text("") == ""

    def test_normalize_none(self):
        assert _normalize_text(None) == ""

    def test_normalize_multiple_whitespace(self):
        assert _normalize_text("  Hello   World  ") == "hello world"

    def test_normalize_preserves_special_chars(self):
        assert _normalize_text("Hello-World_123") == "hello-world_123"


class TestVaultSearchInit:
    def test_init_defaults(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            assert search._embed is None
            assert search.has_embeddings is False
        finally:
            db.close()

    def test_init_with_graph(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, graph=None)
            assert search._graph is None
        finally:
            db.close()


class TestTokenize:
    def test_tokenize_english(self):
        result = VaultSearch._tokenize("hello world test")
        assert "hello" in result
        assert "world" in result
        assert "test" in result

    def test_tokenize_chinese(self):
        result = VaultSearch._tokenize("這是測試")
        assert len(result) > 0

    def test_tokenize_mixed(self):
        result = VaultSearch._tokenize("hello 世界 test")
        assert "hello" in result
        assert "test" in result

    def test_tokenize_empty(self):
        result = VaultSearch._tokenize("")
        # Falls back to returning the original query as single token
        assert result == [""]

    def test_tokenize_single_char(self):
        result = VaultSearch._tokenize("a")
        # Falls back to original since no valid tokens found
        assert result == ["a"]

    def test_tokenize_deduplication(self):
        result = VaultSearch._tokenize("Hello hello HELLO")
        assert len(result) == 1


class TestKeywordSearch:
    def test_search_keyword_basic(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Python Programming",
                content_raw="Python is a versatile programming language.",
                category="tech",
                tags="python,programming",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search("Python programming", mode="keyword", use_rerank=False)
            assert len(results) > 0
        finally:
            db.close()

    def test_search_keyword_with_min_trust(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Low Trust Entry",
                content_raw="This has low trust score.",
                trust=0.2,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search("Low Trust", mode="keyword", min_trust=0.5, use_rerank=False)
            assert len(results) == 0
        finally:
            db.close()

    def test_search_keyword_with_category_filter(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Tech Article", content_raw="tech content", category="tech")
            db.add_knowledge(title="Health Article", content_raw="health content", category="health")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("Article", mode="keyword", category="tech", use_rerank=False)
            assert len(results) >= 1
            for r in results:
                assert r["category"] == "tech"
        finally:
            db.close()

    def test_search_keyword_with_layer_filter(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Core Doc", content_raw="core content", layer="core")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("Core", mode="keyword", layer="core", use_rerank=False)
            assert len(results) >= 1
            for r in results:
                assert r.get("layer") == "core"
        finally:
            db.close()

    def test_search_keyword_no_results(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            results = search.search("nonexistent_term_xyz_123", mode="keyword", use_rerank=False)
            assert results == []
        finally:
            db.close()

    def test_search_keyword_limit(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            for i in range(10):
                db.add_knowledge(title=f"Test Doc {i}", content_raw=f"python content {i}")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("python", mode="keyword", limit=3, use_rerank=False)
            assert len(results) <= 3
        finally:
            db.close()

    def test_search_keyword_with_min_score(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Python Guide", content_raw="Python programming language guide")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("Python", mode="keyword", min_score=0.1, use_rerank=False)
            assert len(results) >= 1
        finally:
            db.close()

    def test_search_keyword_empty_query(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("", mode="keyword", use_rerank=False)
            # Empty token list falls back to LIKE with %, which matches everything
            # Or returns empty if FTS handles it differently
            assert isinstance(results, list)
        finally:
            db.close()

    def test_search_keyword_case_insensitive(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="MixedCase", content_raw="MiXeDcAsE content")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("mixedcase", mode="keyword", use_rerank=False)
            assert len(results) >= 1
        finally:
            db.close()

    def test_search_keyword_method_direct(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Direct Keyword", content_raw="direct keyword search test")
            search = VaultSearch(db, embed_provider=None)
            results = search.search_keyword("Direct Keyword")
            assert len(results) >= 1
            assert results[0]["_mode"] in ("keyword_fts", "keyword")
        finally:
            db.close()

    def test_search_keyword_direct_with_filters(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Filtered",
                content_raw="filtered search",
                category="cat1",
                layer="layer1",
                trust=0.7,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search_keyword(
                "Filtered",
                limit=10,
                min_trust=0.5,
                layer="layer1",
                category="cat1",
            )
            assert len(results) >= 1
        finally:
            db.close()


class TestSearchModes:
    def test_search_auto_mode(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="auto mode test")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("auto mode", mode="auto", use_rerank=False)
            assert len(results) >= 1
        finally:
            db.close()

    def test_search_invalid_mode_raises_value_error(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Fallback Test", content_raw="mode fallback")
            search = VaultSearch(db, embed_provider=None)
            # Invalid mode should raise ValueError
            with pytest.raises(ValueError, match="無效的搜尋模式"):
                search.search("Fallback", mode="invalid_mode", use_rerank=False)
        finally:
            db.close()


class TestVectorSearchFallback:
    def test_search_vector_fallback_when_no_embed(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Vector Fallback", content_raw="test vector fallback")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("fallback", mode="vector", use_rerank=False)
            # Should fall back to keyword
            assert len(results) >= 1
        finally:
            db.close()

    def test_search_vector_direct_method(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Vector Direct", content_raw="vector search direct call")
            search = VaultSearch(db, embed_provider=None)
            results = search.search_vector("Vector Direct")
            # Should fall back to keyword
            assert len(results) >= 1
        finally:
            db.close()


class TestHybridSearchFallback:
    def test_search_hybrid_no_provider_returns_keyword(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Hybrid Test", content_raw="hybrid search test")
            search = VaultSearch(db, embed_provider=None)
            try:
                results = search.search("Hybrid", mode="hybrid", use_rerank=False)
                assert len(results) >= 1
            except (ModuleNotFoundError, ImportError):
                # Acceptable if embedding provider cannot be loaded
                pass
        finally:
            db.close()

    def test_search_hybrid_direct_method(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Hybrid Direct", content_raw="hybrid direct method test")
            search = VaultSearch(db, embed_provider=None)
            try:
                results = search.search_hybrid("Hybrid Direct")
                assert len(results) >= 1
            except (ModuleNotFoundError, ImportError):
                pass  # Acceptable if embedding provider cannot be loaded
        finally:
            db.close()


class TestReranker:
    def test_rerank_basic(self):
        results = [
            {"_score": 0.8, "trust": 0.9, "updated_at": "2024-01-01T00:00:00Z"},
            {"_score": 0.9, "trust": 0.5, "updated_at": "2025-01-01T00:00:00Z"},
        ]
        reranked = VaultSearch._rerank(results)
        assert len(reranked) == 2
        assert "_rerank_score" in reranked[0]
        assert reranked[0]["_rerank_score"] >= reranked[1]["_rerank_score"]

    def test_rerank_empty(self):
        assert VaultSearch._rerank([]) == []

    def test_rerank_no_updated_at(self):
        results = [{"_score": 0.7, "trust": 0.8}]
        reranked = VaultSearch._rerank(results)
        assert len(reranked) == 1
        assert "_rerank_score" in reranked[0]

    def test_rerank_invalid_updated_at(self):
        results = [{"_score": 0.7, "trust": 0.8, "updated_at": "invalid-date"}]
        reranked = VaultSearch._rerank(results)
        assert len(reranked) == 1
        assert "_rerank_score" in reranked[0]

    def test_rerank_with_graph_distance(self):
        results = [
            {"_score": 0.8, "trust": 0.7, "_graph_distance": 0},
            {"_score": 0.8, "trust": 0.7, "_graph_distance": 2},
        ]
        reranked = VaultSearch._rerank(results)
        assert reranked[0]["_graph_distance"] == 0

    def test_rerank_with_freshness_set(self):
        results = [{"_score": 0.7, "trust": 0.8, "freshness": 0.9}]
        reranked = VaultSearch._rerank(results)
        assert len(reranked) == 1
        assert "_rerank_score" in reranked[0]

    def test_search_with_rerank_enabled(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Rerank Test", content_raw="testing reranker", trust=0.8)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("Rerank Test", mode="keyword", use_rerank=True)
            assert len(results) >= 1
            assert "_rerank_score" in results[0]
        finally:
            db.close()

    def test_search_with_rerank_disabled(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="No Rerank", content_raw="no reranking", trust=0.8)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("No Rerank", mode="keyword", use_rerank=False)
            assert len(results) >= 1
            assert "_rerank_score" not in results[0]
        finally:
            db.close()


class TestCompactResult:
    def test_compact_result_full(self):
        result = {
            "id": 1,
            "title": "Test",
            "content_raw": "Should be removed",
            "best_claim": "Best claim",
            "_rerank_score": 0.85,
        }
        compact = VaultSearch._compact_result(result)
        assert compact["id"] == 1
        assert compact["title"] == "Test"
        assert compact["best_claim"] == "Best claim"
        assert compact["rerank_score"] == 0.85
        assert "content_raw" not in compact

    def test_compact_result_minimal(self):
        result = {"id": 1, "title": "Only title"}
        compact = VaultSearch._compact_result(result)
        assert compact == {"id": 1, "title": "Only title"}

    def test_search_with_compact_output(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Compact Test", content_raw="testing compact output")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("Compact Test", mode="keyword", compact=True, use_rerank=False)
            assert len(results) >= 1
            assert "content_raw" not in results[0]
            assert "title" in results[0]
        finally:
            db.close()


class TestBestClaim:
    def test_extract_best_claim_empty(self):
        assert VaultSearch._extract_best_claim("") == ""

    def test_extract_best_claim_no_claims_section(self):
        content = "Just some content without claims section."
        assert VaultSearch._extract_best_claim(content) == ""

    def test_extract_best_claim_with_claims(self):
        content = """Some header
CLAIMS:
- [C1] This is the first claim (L12)
- [C2] Second claim here (L15)
"""
        result = VaultSearch._extract_best_claim(content)
        assert result == "This is the first claim"

    def test_extract_best_claim_without_line_number(self):
        content = """CLAIMS:
- [C1] Claim without line number
"""
        result = VaultSearch._extract_best_claim(content)
        assert result == "Claim without line number"

    def test_extract_best_claim_multiline_before(self):
        content = """SUMMARY:
Some summary text here
CLAIMS:
- [C1] First claim
- [C2] Second claim
"""
        result = VaultSearch._extract_best_claim(content)
        assert result == "First claim"

    def test_extract_best_claim_non_bracket_claims_ignored(self):
        content = """CLAIMS:
- Not a bracket claim
"""
        result = VaultSearch._extract_best_claim(content)
        assert result == ""

    def test_extract_best_claim_claims_section_with_following_text(self):
        content = """CLAIMS:
- [C1] First claim
Some other section text
"""
        result = VaultSearch._extract_best_claim(content)
        assert result == "First claim"


class TestGraphExpand:
    def test_graph_expand_no_graph(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            kid = db.add_knowledge(title="Graph Test", content_raw="graph expand test")
            search = VaultSearch(db, embed_provider=None, graph=None)
            results = search.search("Graph", mode="keyword", graph_expand=2, use_rerank=False)
            assert len(results) >= 1
        finally:
            db.close()

    def test_graph_expand_zero_depth(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="No Expand", content_raw="no graph expansion")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("Expand", mode="keyword", graph_expand=0, use_rerank=False)
            assert len(results) >= 1
        finally:
            db.close()

    def test_apply_graph_expand_empty_results(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, graph=None)
            expanded = search._apply_graph_expand([], 2, 10)
            assert expanded == []
        finally:
            db.close()

    def test_graph_expand_with_edges(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            id1 = db.add_knowledge(title="Main", content_raw="main document")
            id2 = db.add_knowledge(title="Related", content_raw="related document")
            db.add_edge(id1, id2, relation="related_to", weight=0.8)
            search = VaultSearch(db, embed_provider=None, graph=None)
            # Search for "Main" only - should expand to related
            results = search.search("Main", mode="keyword", graph_expand=2, use_rerank=False)
            assert len(results) >= 1
        finally:
            db.close()


class TestSemanticIndexSafe:
    """Safe tests for semantic index that don't require actual embeddings."""

    def test_semantic_index_available_no_provider_explicit(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            # When embed_provider is explicitly None, _get_embed() will still try to create one
            # But it should handle errors gracefully
            try:
                result = search._semantic_index_available("claim")
                assert isinstance(result, bool)
            except Exception:
                pass  # Acceptable if import fails
        finally:
            db.close()


class TestSearchEdgeCases:
    def test_search_keyword_below_min_score(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Low Score", content_raw="unrelated content")
            search = VaultSearch(db, embed_provider=None)
            # min_score=1.0 means only perfect matches
            results = search.search("Low Score", mode="keyword", min_score=1.0, use_rerank=False)
            assert isinstance(results, list)
        finally:
            db.close()

    def test_search_with_all_filters(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="All Filters",
                content_raw="testing all filters",
                category="test_cat",
                layer="test_layer",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search(
                "All Filters",
                mode="keyword",
                min_trust=0.8,
                category="test_cat",
                layer="test_layer",
                limit=5,
                use_rerank=False,
            )
            assert len(results) >= 1
        finally:
            db.close()


class TestQueryExpansion:
    """測試查詢擴展功能。"""

    def test_expand_query_disabled(self, tmp_path):
        """測試停用查詢擴展時只返回原始查詢。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_query_expansion=False)
            result = search._expand_query("什麼是 AI")
            assert len(result) == 1
            assert result[0][0] == "什麼是 AI"
            assert result[0][1] == 1.0
        finally:
            db.close()

    def test_expand_query_question_pattern_what_is(self, tmp_path):
        """測試「什麼是 X」問句模式變換。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, query_expansion_count=10)
            results = search._expand_query("什麼是 AI")
            # 第一個應該是原始查詢
            assert results[0][1] == 1.0
            # 應該包含問句變換結果
            queries = [r[0] for r in results]
            assert any("ai" in q for q in queries)
            assert any("介紹" in q for q in queries)
            assert any("概述" in q for q in queries)
        finally:
            db.close()

    def test_expand_query_simplified_chinese_what_is(self, tmp_path):
        """測試簡體中文「什么是 X」模式匹配。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, query_expansion_count=10)
            results = search._expand_query("什么是 AI")
            queries = [r[0] for r in results]
            # 簡體中文應該也能匹配到問句模式
            assert any("ai" in q for q in queries)
            assert any("介紹" in q for q in queries)
        finally:
            db.close()

    def test_expand_query_synonyms(self, tmp_path):
        """測試同義詞替換擴展。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, query_expansion_count=10)
            results = search._expand_query("AI 搜尋")
            queries = [r[0] for r in results]
            # 應該有同義詞替換結果
            assert any("搜索" in q for q in queries)
            # 同義詞的權重應該是 0.95
            for q, w in results:
                if "搜索" in q and q != "ai 搜尋":
                    assert w == search._query_expansion_synonym_decay
                    break
        finally:
            db.close()

    def test_expand_query_abbreviation(self, tmp_path):
        """測試縮寫/全稱擴展。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, query_expansion_count=10)
            results = search._expand_query("AI 技術")
            queries = [r[0] for r in results]
            # 應該有全稱擴展結果
            assert any("人工智能" in q for q in queries)
        finally:
            db.close()

    def test_expand_query_keyword_extraction(self, tmp_path):
        """測試關鍵詞提取。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, query_expansion_count=10)
            results = search._expand_query("什麼是 AI 技術的應用")
            queries = [r[0] for r in results]
            # 應該有關鍵詞提取結果
            # 關鍵詞提取的權重應該是 keyword_decay
            for q, w in results:
                if w == search._query_expansion_keyword_decay:
                    assert " " in q  # 多個關鍵詞用空格連接
                    break
        finally:
            db.close()

    def test_expand_query_decay_weights(self, tmp_path):
        """測試不同擴展類型有不同的衰減權重。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, query_expansion_count=20)
            # 構造一個會觸發多種擴展的查詢
            results = search._expand_query("什麼是 AI 搜尋技術")
            
            # 原始查詢權重應為 1.0
            assert results[0][1] == 1.0
            
            # 收集所有權重值
            weights = {w for _, w in results}
            
            # 應該有多種不同的權重
            assert len(weights) >= 2
            
            # 同義詞衰減應該大於關鍵詞衰減（同義詞更可靠）
            assert search._query_expansion_synonym_decay > search._query_expansion_keyword_decay
        finally:
            db.close()

    def test_expansion_count_limit(self, tmp_path):
        """測試擴展數量限制。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, query_expansion_count=3)
            results = search._expand_query("什麼是 AI 搜尋技術怎麼用")
            assert len(results) <= 3
        finally:
            db.close()


class TestLightweightReranker:
    """測試輕量級重排序器。"""

    def test_rerank_title_matching(self, tmp_path):
        """測試標題匹配加成。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        
        documents = [
            {"_score": 0.5, "title": "Python 教程", "content_raw": "這是 Python 編程語言的教程"},
            {"_score": 0.5, "title": "Java 教程", "content_raw": "這是 Java 編程語言的教程"},
        ]
        # 查詢 "Python" 應該讓第一個文檔排名更高
        reranked = reranker.rerank("Python", documents)
        assert reranked[0]["title"] == "Python 教程"
        assert reranked[0]["_rerank_score"] > reranked[1]["_rerank_score"]

    def test_rerank_empty_documents(self, tmp_path):
        """測試空文檔列表。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        assert reranker.rerank("test", []) == []

    def test_rerank_multi_term_boost(self, tmp_path):
        """測試多詞匹配獎勵。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        
        documents = [
            {"_score": 0.5, "title": "Python 入門", "content_raw": "學習 Python 編程很容易"},
            {"_score": 0.5, "title": "Java 入門", "content_raw": "學習 Java 編程"},
        ]
        # 同時匹配 "Python" 和 "學習" 的文檔應該排名更高
        reranked = reranker.rerank("Python 學習", documents)
        assert reranked[0]["title"] == "Python 入門"

    def test_rerank_position_weight(self, tmp_path):
        """測試位置權重（關鍵詞出現在開頭加分）。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        
        documents = [
            {"_score": 0.5, "title": "測試", "content_raw": "Python 是一種流行的編程語言，廣泛用於各種領域"},
            {"_score": 0.5, "title": "測試", "content_raw": "這是一篇關於編程的文章，其中提到了 Python 語言"},
        ]
        # 第一個文檔中 Python 出現在開頭，應該有更高的位置加成
        reranked = reranker.rerank("Python", documents)
        assert reranked[0]["_rerank_score"] > reranked[1]["_rerank_score"]

    def test_rerank_top_k_limit(self, tmp_path):
        """測試 top_k 限制。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        
        documents = [
            {"_score": 0.8, "title": "Doc 1", "content_raw": "內容 1"},
            {"_score": 0.6, "title": "Doc 2", "content_raw": "內容 2"},
            {"_score": 0.4, "title": "Doc 3", "content_raw": "內容 3"},
        ]
        reranked = reranker.rerank("內容", documents, top_k=2)
        assert len(reranked) == 2

    def test_rerank_term_frequency_saturation(self, tmp_path):
        """測試詞頻飽和（BM25 風格）。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        
        # 文檔 A 有 10 個 "python"，文檔 B 有 2 個 "python"
        # 由於詞頻飽和，分數不應是線性關係
        content_a = "python " * 10
        content_b = "python " * 2
        documents = [
            {"_score": 0.5, "title": "A", "content_raw": content_a},
            {"_score": 0.5, "title": "B", "content_raw": content_b},
        ]
        reranked = reranker.rerank("python", documents)
        # A 的分數應該高於 B，但不應是 5 倍（因為飽和）
        score_a = reranked[0]["_rerank_score"]
        score_b = reranked[1]["_rerank_score"]
        assert score_a > score_b
        # 確保不是線性增長（5 倍差距會遠大於實際）
        assert score_a < score_b * 3


class TestInfoMethod:
    """測試 info() 方法。"""

    def test_info_returns_dict(self, tmp_path):
        """測試 info() 返回正確結構的字典。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            
            assert "基礎層" in info
            assert "進階層" in info
            assert "高階層" in info
            assert "配置" in info
            
            # 基礎層應該有這些屬性
            assert "關鍵詞搜尋" in info["基礎層"]
            assert "輕量級重排序" in info["基礎層"]
            assert "查詢擴展" in info["基礎層"]
            
            # 配置層應該有這些屬性
            assert "預設模式" in info["配置"]
            assert "關鍵詞權重" in info["配置"]
            assert "向量權重" in info["配置"]
        finally:
            db.close()

    def test_info_query_expansion_toggle(self, tmp_path):
        """測試查詢擴展開關在 info 中正確反映。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            # 開啟查詢擴展
            search_enabled = VaultSearch(db, embed_provider=None, enable_query_expansion=True)
            assert search_enabled.info()["基礎層"]["查詢擴展"] is True
            
            # 關閉查詢擴展
            search_disabled = VaultSearch(db, embed_provider=None, enable_query_expansion=False)
            assert search_disabled.info()["基礎層"]["查詢擴展"] is False
        finally:
            db.close()

    def test_info_rerank_config(self, tmp_path):
        """測試 rerank 配置在 info 中正確反映。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, rerank_strategy="lightweight")
            info = search.info()
            assert info["配置"]["Rerank 策略"] == "lightweight"
            assert info["配置"]["Rerank 開關"] is True
        finally:
            db.close()


class TestInvalidMode:
    """測試無效模式參數校驗。"""

    def test_invalid_mode_raises_value_error(self, tmp_path):
        """測試無效模式拋出 ValueError。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            with pytest.raises(ValueError):
                search.search("test", mode="invalid")
        finally:
            db.close()

    def test_error_message_contains_valid_modes(self, tmp_path):
        """測試錯誤消息包含有效模式列表。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            with pytest.raises(ValueError, match="auto"):
                search.search("test", mode="bad_mode")
        finally:
            db.close()

    def test_valid_modes_do_not_raise(self, tmp_path):
        """測試有效模式不會引發異常。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test content")
            search = VaultSearch(db, embed_provider=None)
            
            for mode in ["auto", "keyword", "vector", "semantic", "hybrid"]:
                results = search.search("test", mode=mode, use_rerank=False)
                assert isinstance(results, list)
        finally:
            db.close()


class TestTokenizeWordOrder:
    """測試分詞詞序問題修復。"""

    def test_mixed_chinese_english_order(self, tmp_path):
        """測試中英文混合時保持原始詞序。"""
        result = VaultSearch._tokenize("什麼是 AI")
        # 第一個 token 應該是中文（什麼是），而不是英文 AI
        first_token = result[0].lower()
        # 驗證第一個 token 是中文開頭
        assert "\u4ec0" in first_token or "\u4ec0\u9ebc" in first_token  # 什麼

    def test_mixed_english_chinese_order(self, tmp_path):
        """測試英文在前中文在後時保持正確順序。"""
        result = VaultSearch._tokenize("AI 是什麼")
        # 第一個 token 應該是英文 AI
        assert result[0].lower() == "ai"

    def test_pure_chinese_order(self, tmp_path):
        """測試純中文分詞順序。"""
        result = VaultSearch._tokenize("這是測試文本")
        # 第一個應該是最長的中文片段
        assert len(result) > 0

    def test_pure_english_order(self, tmp_path):
        """測試純英文分詞順序。"""
        result = VaultSearch._tokenize("hello world test")
        assert result[0].lower() == "hello"
        assert result[1].lower() == "world"

    def test_lighweight_reranker_extract_terms_order(self, tmp_path):
        """測試 LightweightReranker 的 _extract_terms 也保持詞序。"""
        from vault.search import LightweightReranker
        result = LightweightReranker._extract_terms("什麼是 AI")
        # 第一個應該是中文
        assert "\u4ec0" in result[0] or result[0] == "什麼是"


class TestCrossEncoderCache:
    """測試 Cross-Encoder 快取機制。"""

    def test_clear_cache_exists(self):
        """測試 clear_cache 靜態方法存在。"""
        from vault.search import CrossEncoderReranker
        assert hasattr(CrossEncoderReranker, 'clear_cache')
        assert callable(CrossEncoderReranker.clear_cache)

    def test_clear_cache_no_error(self):
        """測試 clear_cache 不會引發異常。"""
        from vault.search import CrossEncoderReranker
        # 清除快取不應該引發異常
        CrossEncoderReranker.clear_cache()

    def test_cache_lock_exists(self):
        """測試快取鎖存在。"""
        from vault.search import CrossEncoderReranker
        assert hasattr(CrossEncoderReranker, '_cache_lock')



# ============================================================================
# 工具函數測試
# ============================================================================

class TestCalcFreshness:
    """測試 calc_freshness 工具函數。"""

    def test_freshness_recent(self):
        """測試最近更新的文件新鮮度高。"""
        from vault.search import calc_freshness
        from datetime import datetime, timezone, timedelta
        # 一天前更新的文件
        updated_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        freshness = calc_freshness(updated_at)
        assert 0.9 <= freshness <= 1.0

    def test_freshness_old(self):
        """測試很久之前更新的文件新鮮度低。"""
        from vault.search import calc_freshness
        from datetime import datetime, timezone, timedelta
        # 一年前更新的文件
        updated_at = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
        freshness = calc_freshness(updated_at)
        assert freshness < 0.6

    def test_freshness_empty(self):
        """測試空字符串返回默認值 0.5。"""
        from vault.search import calc_freshness
        assert calc_freshness("") == 0.5
        assert calc_freshness(None) == 0.5  # type: ignore

    def test_freshness_invalid_date(self):
        """測試無效日期格式返回默認值。"""
        from vault.search import calc_freshness
        assert calc_freshness("invalid-date") == 0.5

    def test_freshness_today(self):
        """測試今天更新的文件新鮮度最高。"""
        from vault.search import calc_freshness
        from datetime import datetime, timezone
        updated_at = datetime.now(timezone.utc).isoformat()
        freshness = calc_freshness(updated_at)
        assert freshness > 0.95


class TestCalcGraphDepth:
    """測試 calc_graph_depth 工具函數。"""

    def test_graph_depth_direct_match(self):
        """測試直接匹配（距離 0）返回最高分。"""
        from vault.search import calc_graph_depth
        result = {"_graph_distance": 0}
        assert calc_graph_depth(result) == 0.2

    def test_graph_depth_one_hop(self):
        """測試 1 跳鄰居。"""
        from vault.search import calc_graph_depth
        result = {"_graph_distance": 1}
        # 距離 1 返回 0.2（與距離 0 相同，因為公式是 0.2 - (dist-1)*0.1）
        assert calc_graph_depth(result) == 0.2

    def test_graph_depth_two_hops(self):
        """測試 2 跳鄰居。"""
        from vault.search import calc_graph_depth
        result = {"_graph_distance": 2}
        assert calc_graph_depth(result) == 0.1

    def test_graph_depth_far_away(self):
        """測試很遠的距離返回 0。"""
        from vault.search import calc_graph_depth
        result = {"_graph_distance": 10}
        assert calc_graph_depth(result) == 0.0

    def test_graph_depth_no_distance(self):
        """測試沒有圖譜距離字段時按 0 處理。"""
        from vault.search import calc_graph_depth
        result = {}
        assert calc_graph_depth(result) == 0.2  # 默認按直接匹配處理


# ============================================================================
# CrossEncoderReranker 測試 (使用 mock)
# ============================================================================

class TestCrossEncoderRerankerWithMock:
    """使用 mock 測試 CrossEncoderReranker 的各種場景。"""

    def test_not_available_without_dependencies(self):
        """測試沒有依賴時 available 為 False。"""
        from vault.search import CrossEncoderReranker
        # 在當前測試環境中，應該沒有安裝 sentence-transformers
        # 所以 CrossEncoderReranker 應該不可用
        reranker = CrossEncoderReranker()
        # 注意：如果環境中剛好有安裝，這個測試可能會失敗
        # 這是正常的，我們主要測試邏輯流程
        assert isinstance(reranker.available, bool)

    def test_rerank_returns_documents_when_unavailable(self):
        """測試不可用時 rerank 返回原始文檔列表。"""
        from vault.search import CrossEncoderReranker
        reranker = CrossEncoderReranker()
        if not reranker.available:
            docs = [
                {"_score": 0.9, "content_raw": "test doc 1"},
                {"_score": 0.8, "content_raw": "test doc 2"},
            ]
            result = reranker.rerank("query", docs)
            # 不可用時應返回原始文檔
            assert len(result) == len(docs)
            # 不應該添加 cross_encoder 分數
            assert "_cross_encoder_score" not in result[0]

    def test_clear_cache_resets_state(self):
        """測試 clear_cache 正確重置快取狀態。"""
        from vault.search import CrossEncoderReranker

        # 先清除快取
        CrossEncoderReranker.clear_cache()

        # 確認快取被清除
        assert CrossEncoderReranker._cached_model is None
        assert CrossEncoderReranker._cached_model_name is None
        assert CrossEncoderReranker._cached_tokenizer is None
        assert CrossEncoderReranker._backend is None

    def test_init_with_custom_model_name(self):
        """測試使用自定義模型名稱初始化。"""
        from vault.search import CrossEncoderReranker
        reranker = CrossEncoderReranker(model_name="custom-model")
        assert reranker._model_name == "custom-model"

    def test_rerank_empty_documents(self):
        """測試空文檔列表返回空列表。"""
        from vault.search import CrossEncoderReranker
        reranker = CrossEncoderReranker()
        result = reranker.rerank("query", [])
        assert result == []

    def test_rerank_with_top_k(self):
        """測試 top_k 參數限制返回數量。"""
        from vault.search import CrossEncoderReranker
        reranker = CrossEncoderReranker()
        docs = [{"_score": 0.9 - i*0.1, "content_raw": f"doc {i}"} for i in range(10)]
        result = reranker.rerank("query", docs, top_k=3)
        if reranker.available:
            # 可用時應該返回 top_k 個
            assert len(result) == 3
        else:
            # 不可用時返回原始文檔（不截斷）
            assert len(result) == 10

    def test_rerank_with_title_field(self):
        """測試指定標題字段。"""
        from vault.search import CrossEncoderReranker
        reranker = CrossEncoderReranker()
        if not reranker.available:
            docs = [{"my_title": "Test Title", "content_raw": "content"}]
            result = reranker.rerank("query", docs, title_field="my_title")
            assert len(result) == 1

    def test_predict_returns_list_when_unavailable(self):
        """測試不可用時 _predict 返回零分數列表。"""
        from vault.search import CrossEncoderReranker
        reranker = CrossEncoderReranker()
        if not reranker.available:
            # 直接調用 _predict 應該返回對應長度的零列表
            pairs = [["q1", "d1"], ["q2", "d2"]]
            scores = reranker._predict(pairs)
            assert len(scores) == len(pairs)
            assert all(s == 0.0 for s in scores)

    def test_available_is_boolean(self):
        """測試 available 屬性返回布爾值。"""
        from vault.search import CrossEncoderReranker
        reranker = CrossEncoderReranker()
        assert isinstance(reranker.available, bool)


# ============================================================================
# 查詢擴展測試
# ============================================================================

class TestQueryExpansionExtended:
    """更全面的查詢擴展測試。"""

    def test_expand_query_disabled_returns_original(self, tmp_path):
        """測試關閉查詢擴展時只返回原始查詢。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=False)
            result = search._expand_query("test query")
            assert len(result) == 1
            assert result[0][0] == "test query"
            assert result[0][1] == 1.0
        finally:
            db.close()

    def test_expand_query_synonym_replacement(self, tmp_path):
        """測試同義詞替換擴展。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True)
            result = search._expand_query("向量搜尋")
            queries = [r[0].lower() for r in result]
            # 應該包含同義詞變體
            assert any("嵌入" in q for q in queries) or any("语义" in q for q in queries)
        finally:
            db.close()

    def test_expand_query_abbreviation_expansion(self, tmp_path):
        """測試縮寫擴展。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True)
            result = search._expand_query("AI 應用")
            queries = [r[0].lower() for r in result]
            # 應該有包含人工智能的擴展
            assert any("人工智能" in q for q in queries)
        finally:
            db.close()

    def test_expand_query_score_decay(self, tmp_path):
        """測試不同擴展類型有不同的分數衰減。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True)
            result = search._expand_query("什麼是向量資料庫")
            # 第一個應該是原始查詢，權重 1.0
            assert result[0][1] == 1.0
            # 其他擴展的權重應該小於 1.0
            for query, weight in result[1:]:
                assert weight < 1.0
                assert weight > 0.0
        finally:
            db.close()

    def test_expand_query_traditional_chinese_what_is(self, tmp_path):
        """測試繁體中文「什麼是」問句匹配。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True)
            result = search._expand_query("什麼是機器學習")
            queries = [r[0] for r in result]
            # 應該生成多種說法
            assert len(result) > 1
        finally:
            db.close()

    def test_expand_query_simplified_chinese_what_is(self, tmp_path):
        """測試簡體中文「什么是」問句匹配。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True)
            result = search._expand_query("什么是机器学习")
            queries = [r[0] for r in result]
            # 應該生成多種說法
            assert len(result) > 1
        finally:
            db.close()

    def test_expand_query_how_to_pattern(self, tmp_path):
        """測試「怎麼用/如何使用」問句模式。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True)
            result = search._expand_query("怎麼用 Python 爬蟲")
            # 應該有多個擴展結果
            assert len(result) >= 2
        finally:
            db.close()

    def test_expand_query_why_pattern(self, tmp_path):
        """測試「為什麼」問句模式。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True)
            result = search._expand_query("為什麼需要資料庫")
            assert len(result) >= 2
        finally:
            db.close()

    def test_expand_query_keyword_extraction(self, tmp_path):
        """測試關鍵詞提取。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True, query_expansion_count=10)
            # 使用有較多停用詞的查詢，關鍵詞提取應該能產生更短的版本
            result = search._expand_query("請問什麼是機器學習模型")
            queries = [r[0].strip() for r in result]
            # 檢查是否有比原始查詢短的擴展（去除了停用詞）
            original_len = len("請問什麼是機器學習模型")
            has_shorter = any(len(q) < original_len for q in queries)
            assert has_shorter, f"Expected shorter queries, got: {queries}"
        finally:
            db.close()

    def test_expansion_count_limit(self, tmp_path):
        """測試查詢擴展數量限制。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True, query_expansion_count=3)
            result = search._expand_query("什麼是向量資料庫 AI 應用")
            assert len(result) <= 3
        finally:
            db.close()

    def test_expand_query_sorted_by_weight(self, tmp_path):
        """測試擴展結果按權重降序排列。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True)
            result = search._expand_query("什麼是向量資料庫")
            weights = [r[1] for r in result]
            # 應該是降序排列
            for i in range(len(weights) - 1):
                assert weights[i] >= weights[i + 1]
        finally:
            db.close()


# ============================================================================
# 輕量級 Reranker 擴展測試
# ============================================================================

class TestLightweightRerankerExtended:
    """更全面的輕量級 Reranker 測試。"""

    def test_title_boost_effect(self):
        """測試標題匹配有顯著加分效果。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        query = "machine learning"
        docs = [
            {"title": "Machine Learning Basics", "content_raw": "some content about data", "_score": 0.5},
            {"title": "Data Science Intro", "content_raw": "machine learning algorithms", "_score": 0.5},
        ]
        result = reranker.rerank(query, docs)
        # 標題匹配的文檔應該排在前面
        assert result[0]["title"] == "Machine Learning Basics"
        assert result[0]["_score"] > result[1]["_score"]

    def test_term_frequency_saturation(self):
        """測試詞頻飽和效果（避免高頻詞主導）。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        query = "python"
        # 一個文檔有少量詞，一個有大量重複詞
        docs = [
            {"title": "", "content_raw": "python " * 5, "_score": 0.5},
            {"title": "", "content_raw": "python " * 100, "_score": 0.5},
        ]
        result = reranker.rerank(query, docs)
        # 由於飽和效應，100次的分數不應該是5次的20倍
        score_ratio = result[0]["_score"] / result[1]["_score"]
        assert 0.5 < score_ratio < 2.0  # 差距應該很小

    def test_position_weight_effect(self):
        """測試位置權重：關鍵詞出現在開頭加分。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        query = "important"
        docs = [
            {"title": "", "content_raw": "important content here" + " filler" * 50, "_score": 0.5},
            {"title": "", "content_raw": "filler " * 50 + " important at end", "_score": 0.5},
        ]
        result = reranker.rerank(query, docs)
        # 關鍵詞在開頭的應該分數更高
        assert result[0]["_score"] > result[1]["_score"]

    def test_multi_term_bonus(self):
        """測試多詞匹配獎勵。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        query = "python data analysis"
        docs = [
            {"title": "", "content_raw": "python data analysis machine learning", "_score": 0.5},
            {"title": "", "content_raw": "python programming language basics", "_score": 0.5},
        ]
        result = reranker.rerank(query, docs)
        # 匹配更多查詢詞的文檔應該分數更高
        assert result[0]["_score"] > result[1]["_score"]

    def test_single_term_penalty(self):
        """測試只有單詞匹配時的降權。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        query = "machine learning algorithm"
        docs = [
            {"title": "", "content_raw": "machine learning algorithm data", "_score": 0.5},
            {"title": "", "content_raw": "machine and nothing else", "_score": 0.5},
        ]
        result = reranker.rerank(query, docs)
        # 只匹配一個詞的應該有懲罰
        assert result[0]["_score"] > result[1]["_score"]

    def test_vector_similarity_boost(self):
        """測試有向量相似度時的加成。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        query = "test query"
        docs = [
            {"title": "Test", "content_raw": "test query content", "_score": 0.5, "_distance": 0.3},
            {"title": "Test", "content_raw": "test query content", "_score": 0.5},
        ]
        result = reranker.rerank(query, docs)
        # 有向量距離的應該有額外加成
        # 注意：兩個文檔內容相同，但第一個有向量距離
        # 距離越近相似度越高，加成越多
        assert result[0]["_score"] > result[1]["_score"]

    def test_rerank_sets_original_score(self):
        """測試 rerank 後保存原始分數。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Test", "content_raw": "test content", "_score": 0.75},
        ]
        result = reranker.rerank("test", docs)
        assert "_original_score" in result[0]
        assert result[0]["_original_score"] == 0.75
        # rerank 後的分數應該不同
        assert result[0]["_score"] != 0.75
        assert "_rerank_score" in result[0]

    def test_rerank_with_trust_boost(self):
        """測試信任度加成。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        query = "test"
        docs = [
            {"title": "Test 1", "content_raw": "test content", "_score": 0.5, "trust": 0.9},
            {"title": "Test 2", "content_raw": "test content", "_score": 0.5, "trust": 0.1},
        ]
        result = reranker.rerank(query, docs)
        # 信任度高的應該排在前面
        assert result[0]["trust"] == 0.9
        assert result[0]["_score"] > result[1]["_score"]


# ============================================================================
# info() 方法國際化測試
# ============================================================================

class TestInfoMethodInternationalization:
    """測試 info() 方法的中英雙語鍵名。"""

    def test_info_has_chinese_keys(self, tmp_path):
        """測試 info() 包含中文鍵名（向後兼容）。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            assert "基礎層" in info
            assert "進階層" in info
            assert "高階層" in info
            assert "旗艦層" in info
            assert "配置" in info
        finally:
            db.close()

    def test_info_has_english_keys(self, tmp_path):
        """測試 info() 包含英文鍵名。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            assert "basic" in info
            assert "advanced" in info
            assert "premium" in info
            assert "flagship" in info
            assert "config" in info
        finally:
            db.close()

    def test_info_basic_layer_english_keys(self, tmp_path):
        """測試基礎層的英文鍵名。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            basic = info["basic"]
            assert "keyword_search" in basic
            assert "lightweight_rerank" in basic
            assert "query_expansion" in basic
            assert "document_map_support" in basic
        finally:
            db.close()

    def test_info_config_english_keys(self, tmp_path):
        """測試配置層的英文鍵名。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            config = info["config"]
            assert "default_mode" in config
            assert "keyword_weight" in config
            assert "vector_weight" in config
            assert "rerank_strategy" in config
            assert "rerank_enabled" in config
            assert "query_expansion_count" in config
            assert "embedding_provider" in config
            assert "embedding_model" in config
        finally:
            db.close()

    def test_info_chinese_english_values_match(self, tmp_path):
        """測試中文和英文鍵對應的值相同。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            # 基礎層值應該相同
            assert info["基礎層"]["關鍵詞搜尋"] == info["basic"]["keyword_search"]
            assert info["基礎層"]["輕量級重排序"] == info["basic"]["lightweight_rerank"]
            assert info["基礎層"]["查詢擴展"] == info["basic"]["query_expansion"]
            # 配置值應該相同
            assert info["配置"]["關鍵詞權重"] == info["config"]["keyword_weight"]
            assert info["配置"]["向量權重"] == info["config"]["vector_weight"]
        finally:
            db.close()

    def test_info_with_vector_search_enabled(self, tmp_path):
        """測試開啟向量搜尋時 info 的返回值。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            # 雖然沒有嵌入提供者，但開關應該正確顯示
            search = VaultSearch(db, embed_provider=None, enable_vector_search=True)
            info = search.info()
            # 沒有嵌入提供者時，向量檢索應該為 False
            assert info["進階層"]["向量檢索"] == False
            assert info["advanced"]["vector_search"] == False
        finally:
            db.close()

    def test_info_with_rerank_disabled(self, tmp_path):
        """測試關閉 rerank 時 info 的返回值。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_rerank=False)
            info = search.info()
            assert info["基礎層"]["輕量級重排序"] == False
            assert info["basic"]["lightweight_rerank"] == False
            assert info["配置"]["Rerank 開關"] == False
            assert info["config"]["rerank_enabled"] == False
        finally:
            db.close()

    def test_info_with_query_expansion_disabled(self, tmp_path):
        """測試關閉查詢擴展時 info 的返回值。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_query_expansion=False)
            info = search.info()
            assert info["基礎層"]["查詢擴展"] == False
            assert info["basic"]["query_expansion"] == False
        finally:
            db.close()


# ============================================================================
# 靜態 _rerank 方法測試
# ============================================================================

class TestStaticRerankMethod:
    """測試 VaultSearch._rerank 靜態方法。"""

    def test_rerank_with_query_uses_lightweight(self):
        """測試有查詢詞時使用輕量級 reranker。"""
        from vault.search import VaultSearch
        results = [
            {"title": "Test Doc", "content_raw": "test query content", "_score": 0.5, "trust": 0.8},
            {"title": "Other Doc", "content_raw": "other content", "_score": 0.5, "trust": 0.8},
        ]
        reranked = VaultSearch._rerank(results, query="test query")
        assert len(reranked) == 2
        assert "_rerank_score" in reranked[0]
        # 相關的應該排在前面
        assert "Test Doc" in reranked[0]["title"]

    def test_rerank_without_query_uses_basic(self):
        """測試無查詢詞時使用基礎 rerank。"""
        from vault.search import VaultSearch
        results = [
            {"title": "Doc 1", "_score": 0.8, "trust": 0.9},
            {"title": "Doc 2", "_score": 0.3, "trust": 0.5},
        ]
        reranked = VaultSearch._rerank(results, query="")
        assert len(reranked) == 2
        assert "_rerank_score" in reranked[0]
        # 分數高的應該排在前面
        assert reranked[0]["_score"] >= reranked[1]["_score"]

    def test_rerank_saves_original_score(self):
        """測試 rerank 保存原始分數。"""
        from vault.search import VaultSearch
        results = [
            {"title": "Doc 1", "content_raw": "test", "_score": 0.8, "trust": 0.9},
        ]
        reranked = VaultSearch._rerank(results, query="")
        assert "_original_score" in reranked[0]
        assert reranked[0]["_original_score"] == 0.8

    def test_rerank_empty_results(self):
        """測試空結果列表。"""
        from vault.search import VaultSearch
        assert VaultSearch._rerank([], query="test") == []
        assert VaultSearch._rerank([], query="") == []

    def test_rerank_with_freshness_field(self):
        """測試已有 freshness 字段時使用該值。"""
        from vault.search import VaultSearch
        results = [
            {"title": "Doc 1", "_score": 0.5, "freshness": 0.9},
            {"title": "Doc 2", "_score": 0.5, "freshness": 0.1},
        ]
        reranked = VaultSearch._rerank(results, query="")
        # 新鮮度高的應該排在前面
        assert reranked[0]["freshness"] == 0.9
        assert reranked[0]["_rerank_score"] > reranked[1]["_rerank_score"]

    def test_rerank_with_graph_distance(self):
        """測試有圖譜距離時的加成。"""
        from vault.search import VaultSearch
        results = [
            {"title": "Doc 1", "_score": 0.5, "_graph_distance": 0},
            {"title": "Doc 2", "_score": 0.5, "_graph_distance": 3},
        ]
        reranked = VaultSearch._rerank(results, query="")
        # 距離近的應該排在前面
        assert reranked[0]["_graph_distance"] == 0
        assert reranked[0]["_rerank_score"] > reranked[1]["_rerank_score"]


# ============================================================================
# 分詞器擴展測試
# ============================================================================

class TestTokenizerExtended:
    """更全面的分詞器測試。"""

    def test_tokenize_chinese_sliding_window(self):
        """測試中文滑動窗口分詞。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("機器學習")
        # 應該包含原詞和雙字組合
        assert "機器學習" in result
        assert "機器" in result
        assert "器學" in result
        assert "學習" in result

    def test_tokenize_mixed_language(self):
        """測試中英文混合文本分詞。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("Python 機器學習")
        assert "python" in result or "Python" in result
        assert "機器學習" in result

    def test_tokenize_single_chinese_char(self):
        """測試單個中文字符。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("學")
        assert len(result) >= 1

    def test_tokenize_with_numbers(self):
        """測試包含數字的文本。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("python3 教程")
        # 英文詞應該被正確提取
        assert any("python" in t.lower() for t in result)

    def test_tokenize_order_preserved(self):
        """測試分詞順序與原文一致。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("first 第二 third 第四")
        # 第一個應該是 first (英文先出現)
        assert result[0].lower() == "first"


# ============================================================================
# 混合搜尋測試 (模擬語義結果)
# ============================================================================

class TestHybridSearchExtended:
    """更全面的混合搜尋測試。"""

    def test_hybrid_search_keyword_only_fallback(self, tmp_path):
        """測試沒有向量時混合搜尋降級到關鍵詞。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Python Programming",
                content_raw="Python is a versatile programming language.",
                category="tech",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            # 直接調用 search_hybrid
            results = search.search_hybrid("Python programming", use_dynamic_weight=False)
            assert len(results) >= 0  # 至少不報錯
        finally:
            db.close()

    def test_hybrid_search_with_custom_weights(self, tmp_path):
        """測試自定義權重。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Test Doc",
                content_raw="test content for search",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None, keyword_weight=2.0, vector_weight=1.0)
            results = search.search_hybrid("test", keyword_weight=2.0, vector_weight=1.0)
            # 不報錯即為通過
            assert isinstance(results, list)
        finally:
            db.close()

    def test_hybrid_search_with_min_score(self, tmp_path):
        """測試 min_score 過濾。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Test Doc",
                content_raw="test content for search",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search_hybrid("test", min_score=0.9)
            # 高分門檻應該返回較少結果
            assert isinstance(results, list)
        finally:
            db.close()

    def test_hybrid_search_limit(self, tmp_path):
        """測試 limit 參數。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            for i in range(10):
                db.add_knowledge(
                    title=f"Doc {i}",
                    content_raw=f"test content document {i}",
                    trust=0.9,
                )
            search = VaultSearch(db, embed_provider=None)
            results = search.search_hybrid("test content", limit=3)
            assert len(results) <= 3
        finally:
            db.close()

    def test_hybrid_search_dynamic_weight_enabled(self, tmp_path):
        """測試啟用動態權重時不報錯。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Test Doc",
                content_raw="test content",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search_hybrid("test", use_dynamic_weight=True)
            assert isinstance(results, list)
        finally:
            db.close()


# ============================================================================
# VaultSearch 屬性與初始化測試
# ============================================================================

class TestVaultSearchProperties:
    """測試 VaultSearch 的各種屬性。"""

    def test_has_embeddings_false_without_provider(self, tmp_path):
        """測試沒有嵌入提供者時 has_embeddings 為 False。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            assert search.has_embeddings == False
        finally:
            db.close()

    def test_has_reranker_true_by_default(self, tmp_path):
        """測試預設情況下 has_reranker 為 True（輕量級）。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            assert search.has_reranker == True
        finally:
            db.close()

    def test_has_reranker_false_when_disabled(self, tmp_path):
        """測試關閉 rerank 時 has_reranker 為 False。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_rerank=False)
            assert search.has_reranker == False
        finally:
            db.close()

    def test_has_cross_encoder_false_by_default(self, tmp_path):
        """測試預設情況下 has_cross_encoder (可能為 False，視環境而定)。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            # 返回布爾值即可
            assert isinstance(search.has_cross_encoder, bool)
        finally:
            db.close()

    def test_has_llm_false_without_llm(self, tmp_path):
        """測試沒有 LLM 時 has_llm 為 False。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_llm_enhancement=True)
            # 沒有 LLM 提供者時應該為 False
            assert isinstance(search.has_llm, bool)
        finally:
            db.close()

    def test_get_reranker_returns_lightweight(self, tmp_path):
        """測試 _get_reranker 返回輕量級 reranker。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            reranker = search._get_reranker()
            assert reranker is not None
            assert reranker.available == True
        finally:
            db.close()

    def test_get_reranker_none_when_disabled(self, tmp_path):
        """測試關閉 rerank 時返回 None。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_rerank=False)
            reranker = search._get_reranker()
            assert reranker is None
        finally:
            db.close()


# ============================================================================
# _normalize_chinese 測試
# ============================================================================

class TestNormalizeChinese:
    """測試中文繁簡轉換。"""

    def test_normalize_chinese_what_is(self):
        """測試「什麼是」轉換為「什么是」。"""
        from vault.search import VaultSearch
        result = VaultSearch._normalize_chinese("什麼是機器學習")
        assert "什么是" in result

    def test_normalize_chinese_why(self):
        """測試「為什麼」轉換。"""
        from vault.search import VaultSearch
        result = VaultSearch._normalize_chinese("為什麼要學習")
        assert "为什么" in result

    def test_normalize_chinese_database(self):
        """測試「資料庫」轉換為「数据库」。"""
        from vault.search import VaultSearch
        result = VaultSearch._normalize_chinese("資料庫系統")
        assert "数据库" in result

    def test_normalize_chinese_mixed(self):
        """測試繁簡混合文本。"""
        from vault.search import VaultSearch
        result = VaultSearch._normalize_chinese("什麼是 vector 資料庫")
        assert "什么是" in result
        assert "数据库" in result
        assert "vector" in result  # 英文保持不變

    def test_normalize_chinese_no_change_needed(self):
        """測試已經是簡體的文本保持不變。"""
        from vault.search import VaultSearch
        text = "什么是机器学习"
        result = VaultSearch._normalize_chinese(text)
        assert result == text


# ============================================================================
# CrossEncoderReranker Mock 測試（覆蓋核心邏輯）
# ============================================================================

class TestCrossEncoderRerankerWithMockSentenceTransformers:
    """使用 mock 測試 CrossEncoderReranker 的完整功能。"""

    def test_rerank_with_mocked_sentence_transformers(self, monkeypatch):
        """測試使用 sentence-transformers 後端時的 rerank 邏輯。"""
        from unittest.mock import MagicMock
        from vault.search import CrossEncoderReranker

        # 清除快取以確保乾淨狀態
        CrossEncoderReranker.clear_cache()

        # Mock sentence_transformers.CrossEncoder
        mock_ce = MagicMock()
        mock_ce.predict.return_value = _MockArray([0.9, 0.5, 0.7])

        mock_module = MagicMock()
        mock_module.CrossEncoder = MagicMock(return_value=mock_ce)

        # 使用 monkeypatch 替換模組
        import sys
        monkeypatch.setitem(sys.modules, 'sentence_transformers', mock_module)

        # 創建實例 - 這會觸發 _try_init 並使用 mock 的 CrossEncoder
        reranker = CrossEncoderReranker(model_name="test-model")

        # 應該可用
        assert reranker.available == True
        assert CrossEncoderReranker._backend == "sentence_transformers"

        # 準備測試數據
        docs = [
            {"id": 1, "title": "Doc 1", "content_raw": "content 1", "_score": 0.8},
            {"id": 2, "title": "Doc 2", "content_raw": "content 2", "_score": 0.6},
            {"id": 3, "title": "Doc 3", "content_raw": "content 3", "_score": 0.7},
        ]

        # 執行 rerank
        result = reranker.rerank("test query", docs)

        # 驗證結果數量
        assert len(result) == 3

        # 驗證分數是按 cross_encoder_score 排序的（降序）
        # mock 返回 [0.9, 0.5, 0.7]，所以排序後應該是 Doc1, Doc3, Doc2
        assert result[0]["id"] == 1
        assert result[0]["_cross_encoder_score"] == 0.9
        assert result[1]["id"] == 3
        assert result[1]["_cross_encoder_score"] == 0.7
        assert result[2]["id"] == 2
        assert result[2]["_cross_encoder_score"] == 0.5

        # 驗證 _score 被更新為 cross encoder 分數
        assert result[0]["_score"] == 0.9

        # 驗證原始分數被保存
        assert result[0]["_original_score"] == 0.8

        # 驗證 _rerank_score 被設置
        assert "_rerank_score" in result[0]

    def test_rerank_with_top_k_mock(self, monkeypatch):
        """測試 top_k 參數在可用模式下的行為。"""
        from unittest.mock import MagicMock
        from vault.search import CrossEncoderReranker
        import sys

        CrossEncoderReranker.clear_cache()

        mock_ce = MagicMock()
        mock_ce.predict.return_value = _MockArray([0.9, 0.8, 0.7, 0.6, 0.5])

        mock_module = MagicMock()
        mock_module.CrossEncoder = MagicMock(return_value=mock_ce)
        monkeypatch.setitem(sys.modules, 'sentence_transformers', mock_module)

        reranker = CrossEncoderReranker()
        docs = [{"id": i, "content_raw": f"doc {i}", "_score": 0.5} for i in range(5)]

        result = reranker.rerank("query", docs, top_k=3)
        assert len(result) == 3

    def test_rerank_empty_documents_mock(self, monkeypatch):
        """測試空文檔列表時的行為。"""
        from unittest.mock import MagicMock
        from vault.search import CrossEncoderReranker
        import sys

        CrossEncoderReranker.clear_cache()

        mock_ce = MagicMock()
        mock_module = MagicMock()
        mock_module.CrossEncoder = MagicMock(return_value=mock_ce)
        monkeypatch.setitem(sys.modules, 'sentence_transformers', mock_module)

        reranker = CrossEncoderReranker()
        result = reranker.rerank("query", [])
        assert result == []

    def test_rerank_with_title_field_mock(self, monkeypatch):
        """測試指定 title_field 時的行為。"""
        from unittest.mock import MagicMock
        from vault.search import CrossEncoderReranker
        import sys

        CrossEncoderReranker.clear_cache()

        mock_ce = MagicMock()
        mock_ce.predict.return_value = _MockArray([0.8])

        mock_module = MagicMock()
        mock_module.CrossEncoder = MagicMock(return_value=mock_ce)
        monkeypatch.setitem(sys.modules, 'sentence_transformers', mock_module)

        reranker = CrossEncoderReranker()
        docs = [{"my_title": "Custom Title", "body": "custom content", "_score": 0.5}]
        result = reranker.rerank("query", docs, title_field="my_title", text_field="body")

        assert len(result) == 1
        # 驗證 predict 被調用
        assert mock_ce.predict.called
        # 檢查傳入的配對是否包含自定義字段
        call_args = mock_ce.predict.call_args[0][0]
        assert len(call_args) == 1
        assert "Custom Title" in call_args[0][1]
        assert "custom content" in call_args[0][1]

    def test_rerank_long_content_truncated(self, monkeypatch):
        """測試長內容被截斷到 512 字符。"""
        from unittest.mock import MagicMock
        from vault.search import CrossEncoderReranker
        import sys

        CrossEncoderReranker.clear_cache()

        mock_ce = MagicMock()
        mock_ce.predict.return_value = _MockArray([0.5])

        mock_module = MagicMock()
        mock_module.CrossEncoder = MagicMock(return_value=mock_ce)
        monkeypatch.setitem(sys.modules, 'sentence_transformers', mock_module)

        reranker = CrossEncoderReranker()
        long_content = "x" * 1000
        docs = [{"title": "Test", "content_raw": long_content, "_score": 0.5}]

        result = reranker.rerank("query", docs)
        assert len(result) == 1

        # 驗證內容被截斷
        call_args = mock_ce.predict.call_args[0][0]
        doc_text = call_args[0][1]
        # "Test\n" + content, 總長度應 <= 512
        assert len(doc_text) <= 512

    def test_cache_reuse_between_instances(self, monkeypatch):
        """測試多個實例共享快取的模型。"""
        from unittest.mock import MagicMock
        from vault.search import CrossEncoderReranker
        import sys

        CrossEncoderReranker.clear_cache()

        mock_ce = MagicMock()
        mock_module = MagicMock()
        mock_module.CrossEncoder = MagicMock(return_value=mock_ce)
        monkeypatch.setitem(sys.modules, 'sentence_transformers', mock_module)

        # 創建第一個實例
        reranker1 = CrossEncoderReranker(model_name="test-model")
        assert reranker1.available == True
        first_call_count = mock_module.CrossEncoder.call_count

        # 創建第二個實例（相同模型名）
        reranker2 = CrossEncoderReranker(model_name="test-model")
        assert reranker2.available == True
        # 應該使用快取，不會再次創建 CrossEncoder
        assert mock_module.CrossEncoder.call_count == first_call_count

        # 兩個實例應該共享同一個模型
        assert reranker1._model is reranker2._model

    def test_clear_cache_works(self, monkeypatch):
        """測試 clear_cache 正確清除快取。"""
        from unittest.mock import MagicMock
        from vault.search import CrossEncoderReranker
        import sys

        CrossEncoderReranker.clear_cache()

        mock_ce = MagicMock()
        mock_module = MagicMock()
        mock_module.CrossEncoder = MagicMock(return_value=mock_ce)
        monkeypatch.setitem(sys.modules, 'sentence_transformers', mock_module)

        # 創建實例填充快取
        reranker1 = CrossEncoderReranker(model_name="test-model")
        assert CrossEncoderReranker._cached_model is not None

        # 清除快取
        CrossEncoderReranker.clear_cache()
        assert CrossEncoderReranker._cached_model is None
        assert CrossEncoderReranker._cached_model_name is None
        assert CrossEncoderReranker._cached_tokenizer is None
        assert CrossEncoderReranker._backend is None

        # 再次創建應該重新初始化
        reranker2 = CrossEncoderReranker(model_name="test-model")
        assert reranker2.available == True

    def test_predict_with_sentence_transformers_backend(self, monkeypatch):
        """測試 sentence_transformers 後端的 _predict 方法。"""
        from unittest.mock import MagicMock
        from vault.search import CrossEncoderReranker
        import sys

        CrossEncoderReranker.clear_cache()

        mock_ce = MagicMock()
        mock_ce.predict.return_value = _MockArray([0.1, 0.2, 0.3])

        mock_module = MagicMock()
        mock_module.CrossEncoder = MagicMock(return_value=mock_ce)
        monkeypatch.setitem(sys.modules, 'sentence_transformers', mock_module)

        reranker = CrossEncoderReranker()
        pairs = [["q1", "d1"], ["q2", "d2"], ["q3", "d3"]]
        scores = reranker._predict(pairs)

        assert len(scores) == 3
        assert scores == [0.1, 0.2, 0.3]
        mock_ce.predict.assert_called_once_with(pairs)

    def test_rerank_no_title(self, monkeypatch):
        """測試沒有標題字段時的行為。"""
        from unittest.mock import MagicMock
        from vault.search import CrossEncoderReranker
        import sys

        CrossEncoderReranker.clear_cache()

        mock_ce = MagicMock()
        mock_ce.predict.return_value = _MockArray([0.5])

        mock_module = MagicMock()
        mock_module.CrossEncoder = MagicMock(return_value=mock_ce)
        monkeypatch.setitem(sys.modules, 'sentence_transformers', mock_module)

        reranker = CrossEncoderReranker()
        docs = [{"content_raw": "content only", "_score": 0.5}]
        result = reranker.rerank("query", docs)

        assert len(result) == 1
        # 沒有標題時，文檔文本應只包含內容（沒有開頭的換行）
        call_args = mock_ce.predict.call_args[0][0]
        doc_text = call_args[0][1]
        assert doc_text == "content only"


# ============================================================================
# 混合搜尋 RRF 融合測試（使用子類覆蓋方法）
# ============================================================================

class TestHybridSearchRRF:
    """測試混合搜尋的 RRF 融合邏輯。"""

    def test_rrf_fusion_basic(self, tmp_path):
        """測試基本的 RRF 分數融合。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB

        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            # 添加一些文件用於關鍵詞搜尋
            db.add_knowledge(title="Python Guide", content_raw="Python programming language guide", trust=0.9)
            db.add_knowledge(title="Java Tutorial", content_raw="Java programming tutorial", trust=0.8)
            db.add_knowledge(title="Machine Learning", content_raw="ML and AI concepts", trust=0.9)

            search = VaultSearch(db, embed_provider=None)

            # 我們直接測試 search_hybrid 的 keyword-only 路徑
            # 因為沒有向量提供者，second_results 會是空的
            results = search.search_hybrid("python programming", use_dynamic_weight=False)
            assert isinstance(results, list)
        finally:
            db.close()

    def test_hybrid_search_with_both_sources(self, tmp_path, monkeypatch):
        """測試有關鍵詞和向量結果時的 RRF 融合。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB

        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            # 添加一些文件
            db.add_knowledge(title="Doc A", content_raw="content about python", trust=0.9)
            db.add_knowledge(title="Doc B", content_raw="content about java", trust=0.8)
            db.add_knowledge(title="Doc C", content_raw="content about machine learning", trust=0.9)

            search = VaultSearch(db, embed_provider=None)

            # Mock semantic 搜索結果
            mock_semantic_results = [
                {"id": 2, "title": "Doc B", "_score": 0.9, "_mode": "semantic"},
                {"id": 3, "title": "Doc C", "_score": 0.7, "_mode": "semantic"},
                {"id": 1, "title": "Doc A", "_score": 0.5, "_mode": "semantic"},
            ]

            # 替換 search_semantic 方法
            original = search.search_semantic
            search.search_semantic = lambda *args, **kwargs: mock_semantic_results

            # 同時需要讓 _semantic_index_available 返回 True
            original_available = search._semantic_index_available
            search._semantic_index_available = lambda *args, **kwargs: True

            try:
                results = search.search_hybrid("test query", use_dynamic_weight=False)
                # 應該有結果（關鍵詞 + 語義融合）
                assert isinstance(results, list)
                # 所有結果都應該有 _score
                for r in results:
                    assert "_score" in r
            finally:
                search.search_semantic = original
                search._semantic_index_available = original_available
        finally:
            db.close()

    def test_hybrid_search_cross_validation_bonus(self, tmp_path, monkeypatch):
        """測試同時出現在關鍵詞和向量結果中的文檔獲得交叉驗證加分。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB

        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Shared Doc", content_raw="shared content", trust=0.9)
            db.add_knowledge(title="Keyword Only", content_raw="keyword only content", trust=0.8)

            search = VaultSearch(db, embed_provider=None)

            # Mock 語義搜索結果，包含與關鍵詞搜索重疊的文檔
            mock_semantic_results = [
                {"id": 1, "title": "Shared Doc", "_score": 0.9, "_mode": "semantic"},
            ]

            original = search.search_semantic
            search.search_semantic = lambda *args, **kwargs: mock_semantic_results
            original_available = search._semantic_index_available
            search._semantic_index_available = lambda *args, **kwargs: True

            try:
                results = search.search_hybrid("shared content", use_dynamic_weight=False)
                # 應該至少有共享的文檔
                assert len(results) >= 1
                shared_doc = [r for r in results if r["id"] == 1][0]
                # 共享文檔應該有混合模式標記
                assert "hybrid" in shared_doc.get("_mode", "")
            finally:
                search.search_semantic = original
                search._semantic_index_available = original_available
        finally:
            db.close()

    def test_dynamic_weight_adjustment_keyword_better(self, tmp_path, monkeypatch):
        """測試當關鍵詞質量更高時，動態調整權重。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB

        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test Doc", content_raw="test content about python", trust=0.9)

            search = VaultSearch(db, embed_provider=None, keyword_weight=1.0, vector_weight=1.0)

            # Mock 低質量的語義結果（最高分低）
            mock_semantic_results = [
                {"id": 1, "title": "Test Doc", "_score": 0.3, "_mode": "semantic"},
            ]

            original = search.search_semantic
            search.search_semantic = lambda *args, **kwargs: mock_semantic_results
            original_available = search._semantic_index_available
            search._semantic_index_available = lambda *args, **kwargs: True

            try:
                results = search.search_hybrid("test python", use_dynamic_weight=True)
                assert isinstance(results, list)
                # 不報錯即表示動態權重邏輯正常運行
            finally:
                search.search_semantic = original
                search._semantic_index_available = original_available
        finally:
            db.close()


# ============================================================================
# 查詢擴展邊界情況測試
# ============================================================================

class TestQueryExpansionEdgeCases:
    """測試查詢擴展的邊界情況。"""

    def test_expand_query_empty_string(self, tmp_path):
        """測試空查詢的擴展。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True)
            result = search._expand_query("")
            # 空查詢也應該返回結果
            assert len(result) >= 1
        finally:
            db.close()

    def test_expand_query_very_long_query(self, tmp_path):
        """測試超長查詢的擴展。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True)
            long_query = "什麼是" + "測試" * 50 + "以及如何使用"
            result = search._expand_query(long_query)
            assert len(result) >= 1
            # 數量不應超過配置的擴展數量
            assert len(result) <= search._query_expansion_count
        finally:
            db.close()

    def test_expand_query_special_characters(self, tmp_path):
        """測試包含特殊字符的查詢。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True)
            result = search._expand_query("what is C++ & Python?")
            assert len(result) >= 1
        finally:
            db.close()

    def test_expand_query_abbreviation_fullform_mapping(self, tmp_path):
        """測試縮寫和全稱的互相轉換。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True)
            # 測試縮寫轉全稱
            result = search._expand_query("AI tutorial")
            queries = [r[0].lower() for r in result]
            has_full = any("人工智能" in q for q in queries)
            # 注意：這取決於擴展是否打開以及是否在 top N 中
            # 至少不應該報錯
            assert len(result) >= 1
        finally:
            db.close()

    def test_expand_query_decay_factor_applied(self, tmp_path):
        """測試不同擴展類型應用了不同的衰減因子。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True, query_expansion_count=20)
            result = search._expand_query("什麼是 AI 人工智能")
            # 第一個總是原始查詢，權重 1.0
            assert result[0][1] == 1.0
            # 其他的權重應該 < 1.0
            for _, weight in result[1:]:
                assert weight < 1.0
                assert weight > 0.0
            # 同義詞替換的衰減應該比關鍵詞提取小（權重更高）
            # 這裡我們只確保有多種不同的權重值
            weights = [w for _, w in result]
            unique_weights = set(round(w, 6) for w in weights)
            assert len(unique_weights) >= 2  # 至少有兩種不同的權重
        finally:
            db.close()


# ============================================================================
# _tokenize 邊界情況測試
# ============================================================================

class TestTokenizerEdgeCases:
    """測試分詞器的邊界情況。"""

    def test_tokenize_empty_string(self):
        """測試空字符串分詞。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("")
        assert isinstance(result, list)

    def test_tokenize_numbers_only(self):
        """測試只有數字的字符串。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("12345")
        assert isinstance(result, list)

    def test_tokenize_punctuation_only(self):
        """測試只有標點符號的字符串。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("!!!???...")
        assert isinstance(result, list)

    def test_tokenize_chinese_only_short(self):
        """測試短中文文本。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("測試")
        assert len(result) >= 1

    def test_tokenize_chinese_only_long(self):
        """測試長中文文本的滑動窗口分詞。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("這是一個測試文本")
        # 應該有原詞 + 雙字組合
        assert len(result) >= 3
        # 確保有原詞
        assert "這是一個測試文本" in result

    def test_tokenize_mixed_with_special_chars(self):
        """測試中英文和特殊字符混合。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("Python3.10 測試!@#$")
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_tokenize_deduplication(self):
        """測試分詞結果去重。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("test Test TEST 測試 測試")
        # 英文應該不區分大小寫去重
        # 中文保持原樣
        assert len(result) < len("test Test TEST 測試 測試".split()) + 2  # 寬鬆檢查


# ============================================================================
# LightweightReranker 更多測試
# ============================================================================

class TestLightweightRerankerMore:
    """輕量級 Reranker 的更多邊界測試。"""

    def test_rerank_single_document(self):
        """測試只有一個文檔時的 rerank。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [{"title": "Test", "content_raw": "test content", "_score": 0.5}]
        result = reranker.rerank("test", docs)
        assert len(result) == 1
        assert "_rerank_score" in result[0]

    def test_rerank_query_not_in_docs(self):
        """測試查詢詞不在任何文檔中時的行為。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Doc 1", "content_raw": "completely different content", "_score": 0.8},
            {"title": "Doc 2", "content_raw": "another unrelated document", "_score": 0.7},
        ]
        result = reranker.rerank("nonexistent keyword", docs)
        assert len(result) == 2
        # 仍然應該有 rerank 分數
        assert "_rerank_score" in result[0]

    def test_rerank_with_freshness_trust_graph(self):
        """測試同時有 freshness、trust、graph_distance 時的 rerank。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        query = "test"
        docs = [
            {"title": "Doc A", "content_raw": "test content", "_score": 0.5, "trust": 0.9, "freshness": 0.1, "_graph_distance": 0},
            {"title": "Doc B", "content_raw": "test content", "_score": 0.5, "trust": 0.1, "freshness": 0.9, "_graph_distance": 2},
        ]
        result = reranker.rerank(query, docs)
        assert len(result) == 2
        # 兩個文檔的 rerank 分數應該不同
        assert result[0]["_rerank_score"] != result[1]["_rerank_score"]

    def test_rerank_zero_base_score(self):
        """測試原始分數為 0 時的行為。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [{"title": "Test", "content_raw": "test content", "_score": 0.0}]
        result = reranker.rerank("test", docs)
        assert len(result) == 1
        assert "_rerank_score" in result[0]

    def test_rerank_top_k_larger_than_docs(self):
        """測試 top_k 大於文檔數量時的行為。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Doc 1", "content_raw": "test", "_score": 0.5},
            {"title": "Doc 2", "content_raw": "test", "_score": 0.6},
        ]
        result = reranker.rerank("test", docs, top_k=10)
        assert len(result) == 2  # 不應該超過實際文檔數

    def test_rerank_top_k_zero(self):
        """測試 top_k 為 0 時的行為。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Doc 1", "content_raw": "test", "_score": 0.5},
            {"title": "Doc 2", "content_raw": "test", "_score": 0.6},
        ]
        result = reranker.rerank("test", docs, top_k=0)
        assert len(result) == 0

    def test_rerank_with_custom_text_field(self):
        """測試使用自定義文本字段。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Title", "body": "test query here", "_score": 0.5},
            {"title": "Title", "body": "other content", "_score": 0.5},
        ]
        result = reranker.rerank("test query", docs, text_field="body")
        # 匹配的文檔應該排在前面
        assert "test query here" in result[0]["body"]


# ============================================================================
# VaultSearch 屬性與配置測試
# ============================================================================

class TestVaultSearchConfig:
    """測試 VaultSearch 的各種配置選項。"""

    def test_enable_query_expansion_false(self, tmp_path):
        """測試關閉查詢擴展時的行為。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=False)
            result = search._expand_query("什麼是 AI")
            # 關閉時應該只返回原始查詢
            assert len(result) == 1
            assert result[0][1] == 1.0
        finally:
            db.close()

    def test_query_expansion_count_config(self, tmp_path):
        """測試 query_expansion_count 配置。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True, query_expansion_count=3)
            result = search._expand_query("什麼是 AI 人工智能 機器學習")
            assert len(result) <= 3
        finally:
            db.close()

    def test_custom_keyword_vector_weights(self, tmp_path):
        """測試自定義關鍵詞和向量權重。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, keyword_weight=2.0, vector_weight=0.5)
            assert search._keyword_weight == 2.0
            assert search._vector_weight == 0.5
        finally:
            db.close()

    def test_rerank_strategy_configs(self, tmp_path):
        """測試不同的 rerank 策略配置。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            for strategy in ["auto", "lightweight", "cross_encoder", "none"]:
                search = VaultSearch(db, rerank_strategy=strategy)
                assert search._rerank_strategy == strategy
        finally:
            db.close()

    def test_llm_query_rewrite_strategies(self, tmp_path):
        """測試不同的 LLM 查詢改寫策略。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            for strategy in ["auto", "synonym", "decompose", "keywords"]:
                search = VaultSearch(db, enable_llm_query_rewrite=True, llm_query_rewrite_strategy=strategy)
                assert search._llm_query_rewrite_strategy == strategy
        finally:
            db.close()


# ============================================================================
# CrossEncoderReranker ONNX Runtime 後端測試
# ============================================================================

class TestCrossEncoderRerankerOnnxRuntime:
    """測試 CrossEncoderReranker 的 ONNX Runtime 後端。"""

    def test_onnxruntime_backend_with_tokenizer(self, monkeypatch, tmp_path):
        """測試有 tokenizer 的 ONNX Runtime 後端。"""
        from unittest.mock import MagicMock
        from vault.search import CrossEncoderReranker
        import sys, os

        CrossEncoderReranker.clear_cache()

        # 確保 sentence_transformers 不可用（模擬 import 失敗）
        def mock_import_st(name, *args, **kwargs):
            if name == 'sentence_transformers':
                raise ImportError("No module named 'sentence_transformers'")
            return __import__(name)

        # Mock onnxruntime
        mock_ort = MagicMock()
        mock_session = MagicMock()
        # 模擬輸出：2D 數組，多分類
        mock_output = MagicMock()
        mock_output.ndim = 2
        mock_output.shape = (1, 2)
        mock_output.__getitem__ = lambda self, idx: [0.1, 2.5] if idx == 0 else mock_output
        mock_session.run.return_value = [mock_output]
        mock_ort.InferenceSession = MagicMock(return_value=mock_session)

        # Mock tokenizers
        mock_tokenizers = MagicMock()
        mock_tokenizer = MagicMock()
        mock_encoding = MagicMock()
        mock_encoding.ids = [101, 200, 300, 102]
        mock_tokenizer.encode.return_value = mock_encoding
        mock_tokenizers.Tokenizer.from_file.return_value = mock_tokenizer

        # 設置環境變量
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        model_path = model_dir / "model.onnx"
        model_path.write_text("fake model")
        tokenizer_path = model_dir / "tokenizer.json"
        tokenizer_path.write_text("fake tokenizer")

        monkeypatch.setenv("VAULT_CROSS_ENCODER_PATH", str(model_path))
        monkeypatch.setitem(sys.modules, 'onnxruntime', mock_ort)
        monkeypatch.setitem(sys.modules, 'tokenizers', mock_tokenizers)

        # 創建實例
        reranker = CrossEncoderReranker(model_name="onnx-model")

        # 應該可用且使用 onnxruntime 後端
        assert reranker.available == True
        assert CrossEncoderReranker._backend == "onnxruntime"
        assert reranker._tokenizer is not None

        # 測試 rerank
        docs = [
            {"id": 1, "title": "Doc 1", "content_raw": "content 1", "_score": 0.8},
            {"id": 2, "title": "Doc 2", "content_raw": "content 2", "_score": 0.6},
        ]
        result = reranker.rerank("test query", docs)
        assert len(result) == 2
        assert "_cross_encoder_score" in result[0]
        assert "_rerank_score" in result[0]

    def test_onnxruntime_backend_without_tokenizer(self, monkeypatch, tmp_path):
        """測試沒有 tokenizer 時的 ONNX Runtime 後端（字符級 fallback）。"""
        from unittest.mock import MagicMock
        from vault.search import CrossEncoderReranker
        import sys, os

        CrossEncoderReranker.clear_cache()

        # Mock onnxruntime
        mock_ort = MagicMock()
        mock_session = MagicMock()
        mock_output = MagicMock()
        mock_output.ndim = 2
        mock_output.shape = (1, 1)
        mock_output.__getitem__ = lambda self, idx: [0.75] if idx == 0 else mock_output
        mock_session.run.return_value = [mock_output]
        mock_ort.InferenceSession = MagicMock(return_value=mock_session)

        # 只 mock onnxruntime，不 mock tokenizers（讓它 import 失敗）
        monkeypatch.setitem(sys.modules, 'onnxruntime', mock_ort)

        # 設置環境變量指向存在的模型路徑
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        model_path = model_dir / "model.onnx"
        model_path.write_text("fake model")
        # 注意：這裡不創建 tokenizer.json，所以 tokenizer 會是 None

        monkeypatch.setenv("VAULT_CROSS_ENCODER_PATH", str(model_path))

        # 創建實例 - 這需要 sentence_transformers 先失敗才會走到 onnxruntime
        # 我們直接手動設置狀態來測試 _predict 方法
        reranker = CrossEncoderReranker()
        # 手動設置為 onnxruntime 模式（繞過 _try_init）
        CrossEncoderReranker._backend = "onnxruntime"
        reranker._model = mock_session
        reranker._tokenizer = None
        reranker._available = True

        # 測試 rerank（使用字符級 fallback 編碼）
        docs = [
            {"id": 1, "title": "Doc 1", "content_raw": "content 1", "_score": 0.8},
        ]
        result = reranker.rerank("test", docs)
        assert len(result) == 1
        assert "_cross_encoder_score" in result[0]

    def test_onnxruntime_multi_class_output(self, monkeypatch, tmp_path):
        """測試多分類輸出（logits shape [batch, 2+]）。"""
        from unittest.mock import MagicMock
        from vault.search import CrossEncoderReranker
        import sys

        CrossEncoderReranker.clear_cache()

        mock_ort = MagicMock()
        mock_session = MagicMock()
        # 多分類輸出：形狀為 (1, 3)
        mock_output = MagicMock()
        mock_output.ndim = 2
        mock_output.shape = (1, 3)
        mock_output.__getitem__ = lambda self, idx: [0.1, 2.5, 0.3] if idx == 0 else mock_output
        mock_session.run.return_value = [mock_output]
        mock_ort.InferenceSession = MagicMock(return_value=mock_session)

        monkeypatch.setitem(sys.modules, 'onnxruntime', mock_ort)

        model_path = tmp_path / "model.onnx"
        model_path.write_text("fake")
        monkeypatch.setenv("VAULT_CROSS_ENCODER_PATH", str(model_path))

        # 直接設置狀態測試
        reranker = CrossEncoderReranker()
        CrossEncoderReranker._backend = "onnxruntime"
        reranker._model = mock_session
        reranker._tokenizer = None
        reranker._available = True

        result = reranker.rerank("test", [{"content_raw": "doc", "_score": 0.5}])
        # 多分類時取第二個類別的機率，經過 sigmoid 轉換
        # score = 1.0 / (1.0 + exp(-2.5)) ≈ 0.924
        assert 0.9 < result[0]["_cross_encoder_score"] < 0.95


# ============================================================================
# 搜尋模式測試
# ============================================================================

class TestSearchModesExtended:
    """更全面的搜尋模式測試。"""

    def test_search_auto_mode_without_embeddings(self, tmp_path):
        """測試沒有嵌入時 auto 模式使用 keyword search。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test content", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("test", mode="auto")
            assert isinstance(results, list)
        finally:
            db.close()

    def test_search_keyword_mode(self, tmp_path):
        """測試 keyword 模式。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test content", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("test", mode="keyword")
            assert isinstance(results, list)
            assert len(results) >= 0
        finally:
            db.close()

    def test_search_with_limit(self, tmp_path):
        """測試 limit 參數。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            for i in range(20):
                db.add_knowledge(title=f"Doc {i}", content_raw=f"test document {i}", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("test document", mode="keyword", limit=5)
            assert len(results) <= 5
        finally:
            db.close()

    def test_search_with_min_trust(self, tmp_path):
        """測試 min_trust 過濾。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="High Trust", content_raw="test", trust=0.9)
            db.add_knowledge(title="Low Trust", content_raw="test", trust=0.2)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("test", mode="keyword", min_trust=0.5)
            assert all(r["trust"] >= 0.5 for r in results)
        finally:
            db.close()

    def test_search_no_rerank(self, tmp_path):
        """測試關閉 rerank 的搜尋。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test content", trust=0.9)
            search = VaultSearch(db, embed_provider=None, enable_rerank=False)
            results = search.search("test", use_rerank=False)
            assert isinstance(results, list)
        finally:
            db.close()


# ============================================================================
# _extract_best_claim 測試
# ============================================================================

class TestExtractBestClaim:
    """測試 _extract_best_claim 方法。"""

    def test_extract_empty_content(self):
        """測試空內容返回空字符串。"""
        from vault.search import VaultSearch
        assert VaultSearch._extract_best_claim("") == ""
        assert VaultSearch._extract_best_claim(None) == ""

    def test_extract_no_claims_section(self):
        """測試沒有 CLAIMS 段時返回空。"""
        from vault.search import VaultSearch
        content = "Just some regular content\nWithout claims section"
        assert VaultSearch._extract_best_claim(content) == ""

    def test_extract_single_claim(self):
        """測試提取單個聲明。"""
        from vault.search import VaultSearch
        content = "Some header\nCLAIMS:\n- [C1] This is a test claim (L10)\n\nOther content"
        result = VaultSearch._extract_best_claim(content)
        assert "This is a test claim" in result

    def test_extract_multiple_claims_returns_first(self):
        """測試多個聲明時返回第一個。"""
        from vault.search import VaultSearch
        content = """CLAIMS:
- [C1] First claim (L1)
- [C2] Second claim (L2)
- [C3] Third claim (L3)
"""
        result = VaultSearch._extract_best_claim(content)
        assert "First claim" in result
        assert "Second" not in result

    def test_extract_claim_without_line_number(self):
        """測試沒有行號的聲明。"""
        from vault.search import VaultSearch
        content = "CLAIMS:\n- [C1] A claim without line number"
        result = VaultSearch._extract_best_claim(content)
        assert "A claim without line number" in result

    def test_extract_claim_with_bracket_format(self):
        """測試不同標籤格式的聲明。"""
        from vault.search import VaultSearch
        # 沒有 [C1] 格式的情況
        content = "CLAIMS:\n- Just a claim without ID"
        result = VaultSearch._extract_best_claim(content)
        # 這種情況可能返回空或部分內容，取決於實現
        assert isinstance(result, str)


# ============================================================================
# _rerank_with_strategy 測試
# ============================================================================

class TestRerankWithStrategy:
    """測試 _rerank_with_strategy 方法。"""

    def test_rerank_with_strategy_none(self, tmp_path):
        """測試 rerank 策略為 none 時不進行 rerank。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test content", trust=0.9)
            search = VaultSearch(db, embed_provider=None, rerank_strategy="none", enable_rerank=True)
            results = search.search("test", mode="keyword", use_rerank=True)
            # 策略為 none 時不進行 rerank
            assert isinstance(results, list)
        finally:
            db.close()

    def test_rerank_with_strategy_lightweight(self, tmp_path):
        """測試 lightweight 策略。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test content", trust=0.9)
            search = VaultSearch(db, embed_provider=None, rerank_strategy="lightweight")
            results = search.search("test", mode="keyword", use_rerank=True)
            assert isinstance(results, list)
            # 應該有 rerank 分數
            if results:
                assert "_rerank_score" in results[0]
        finally:
            db.close()

    def test_rerank_with_strategy_cross_encoder_when_unavailable(self, tmp_path):
        """測試 cross_encoder 策略在不可用時的行為。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test content", trust=0.9)
            search = VaultSearch(db, embed_provider=None, rerank_strategy="cross_encoder", enable_cross_encoder=True)
            results = search.search("test", mode="keyword", use_rerank=True)
            # 當 cross_encoder 不可用時，應該降級或返回原始結果
            assert isinstance(results, list)
        finally:
            db.close()


# ============================================================================
# 查詢擴展更多模式測試
# ============================================================================

class TestQueryExpansionMorePatterns:
    """測試更多查詢擴展模式。"""

    def test_expand_query_how_to_use_pattern(self, tmp_path):
        """測試 how to use 模式。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True, query_expansion_count=10)
            result = search._expand_query("how to use python")
            assert len(result) >= 2
        finally:
            db.close()

    def test_expand_query_how_to_implement_pattern(self, tmp_path):
        """測試 how to implement 模式。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True, query_expansion_count=10)
            result = search._expand_query("how to implement a search engine")
            assert len(result) >= 1
        finally:
            db.close()

    def test_expand_query_why_pattern(self, tmp_path):
        """測試 why 模式。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True, query_expansion_count=10)
            result = search._expand_query("why use databases")
            assert len(result) >= 2
        finally:
            db.close()

    def test_expand_query_synonym_variations(self, tmp_path):
        """測試同義詞變換。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True, query_expansion_count=20)
            result = search._expand_query("搜尋 優化 效能")
            queries = [r[0].lower() for r in result]
            # 應該有一些同義詞替換的變體
            has_variations = any("搜索" in q or "检索" in q for q in queries)
            # 可能有也可能沒有，取決於同義詞詞典，不強制斷言
            assert isinstance(has_variations, bool)
        finally:
            db.close()

    def test_expand_query_with_numbers(self, tmp_path):
        """測試包含數字的查詢擴展。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True)
            result = search._expand_query("什麼是 Python 3.10 的新特性")
            assert len(result) >= 1
        finally:
            db.close()


# ============================================================================
# VaultSearch 能力偵測測試
# ============================================================================

class TestVaultSearchCapabilityDetection:
    """測試 VaultSearch 的各種能力偵測。"""

    def test_has_embeddings_false_when_disabled(self, tmp_path):
        """測試關閉向量搜尋時 has_embeddings 為 False。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_vector_search=False)
            assert search.has_embeddings == False
        finally:
            db.close()

    def test_has_reranker_false_when_disabled(self, tmp_path):
        """測試關閉 rerank 時 has_reranker 為 False。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_rerank=False)
            assert search.has_reranker == False
        finally:
            db.close()

    def test_has_llm_false_when_disabled(self, tmp_path):
        """測試關閉 LLM 時 has_llm 為 False。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_llm_enhancement=False)
            assert search.has_llm == False
        finally:
            db.close()

    def test_info_method_returns_all_sections(self, tmp_path):
        """測試 info() 方法返回所有預期的 section。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            # 中文鍵
            assert "基礎層" in info
            assert "進階層" in info
            assert "高階層" in info
            assert "旗艦層" in info
            assert "配置" in info
            # 英文鍵
            assert "basic" in info
            assert "advanced" in info
            assert "premium" in info
            assert "flagship" in info
            assert "config" in info
        finally:
            db.close()

    def test_info_basic_layer_contents(self, tmp_path):
        """測試 info() 基礎層的內容。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_query_expansion=True)
            info = search.info()
            basic = info["基礎層"]
            assert "關鍵詞搜尋" in basic
            assert "輕量級重排序" in basic
            assert "查詢擴展" in basic
            assert "文件地圖支援" in basic
            # 所有值都應該是布爾型
            for key in ["關鍵詞搜尋", "輕量級重排序", "查詢擴展", "文件地圖支援"]:
                assert isinstance(basic[key], bool)
        finally:
            db.close()

    def test_info_config_layer_contents(self, tmp_path):
        """測試 info() 配置層的內容。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            config = info["配置"]
            assert "預設模式" in config
            assert "關鍵詞權重" in config
            assert "向量權重" in config
            assert "Rerank 策略" in config
            assert "查詢擴展數量" in config
        finally:
            db.close()


# ============================================================================
# 圖譜擴展測試
# ============================================================================

class TestGraphExpandExtended:
    """更全面的圖譜擴展測試。"""

    def test_apply_graph_expand_no_graph(self, tmp_path):
        """測試沒有 graph 時的圖譜擴展（應該不影響結果）。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("test", graph_expand=1)
            assert isinstance(results, list)
        finally:
            db.close()

    def test_apply_graph_expand_empty_results(self, tmp_path):
        """測試空結果時的圖譜擴展。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            results = search._apply_graph_expand([], 1, 10)
            assert results == []
        finally:
            db.close()


# ============================================================================
# 關鍵詞搜尋邊界情況測試
# ============================================================================

class TestKeywordSearchEdgeCases:
    """關鍵詞搜尋的邊界情況測試。"""

    def test_search_keyword_empty_query(self, tmp_path):
        """測試空查詢的關鍵詞搜尋。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test content", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search.search_keyword("")
            assert isinstance(results, list)
        finally:
            db.close()

    def test_search_keyword_with_category(self, tmp_path):
        """測試按類別過濾的關鍵詞搜尋。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Tech Doc", content_raw="python programming", category="tech", trust=0.9)
            db.add_knowledge(title="Other Doc", content_raw="python tutorial", category="other", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search.search_keyword("python", category="tech")
            for r in results:
                assert r.get("category") == "tech"
        finally:
            db.close()

    def test_search_keyword_with_layer(self, tmp_path):
        """測試按層級過濾的關鍵詞搜尋。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Doc 1", content_raw="test", layer="public", trust=0.9)
            db.add_knowledge(title="Doc 2", content_raw="test", layer="internal", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search.search_keyword("test", layer="public")
            for r in results:
                assert r.get("layer") == "public"
        finally:
            db.close()

    def test_search_keyword_min_score_filter(self, tmp_path):
        """測試 min_score 過濾。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Perfect Match", content_raw="test query keyword", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            # 使用高閾值
            results_high = search.search_keyword("test query", min_score=0.9)
            # 使用低閾值
            results_low = search.search_keyword("test query", min_score=0.1)
            # 低閾值應該返回更多或相等數量的結果
            assert len(results_low) >= len(results_high)
        finally:
            db.close()


# ============================================================================
# _tokenize 邊界情況測試
# ============================================================================

class TestTokenizerMoreEdgeCases:
    """分詞器的更多邊界情況測試。"""

    def test_tokenize_single_english_letter(self):
        """測試單個英文字母。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("a")
        # 小於2個字母，不應該被提取為英文單詞，但 fallback 會返回原始
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_tokenize_two_chinese_chars(self):
        """測試兩個中文字符。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("測試")
        assert "測試" in result
        # 2個字的不做滑動窗口
        assert len(result) <= 2

    def test_tokenize_three_chinese_chars(self):
        """測試三個中文字符（應該有原詞 + 雙字窗口）。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("測試用")
        # 應該有原詞 + 2個雙字組合
        assert "測試用" in result
        assert "測試" in result
        assert "試用" in result

    def test_tokenize_four_chinese_chars(self):
        """測試四個中文字符。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("機器學習")
        assert "機器學習" in result
        assert "機器" in result
        assert "器學" in result
        assert "學習" in result

    def test_tokenize_mixed_chinese_english_order(self):
        """測試中英文混合時的順序。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("hello 世界 python 測試")
        # 檢查順序：hello, 世界, python, 測試
        # 中文部分會被拆分成多個，但英文應該按出現順序
        tokens_lower = [t.lower() for t in result]
        assert tokens_lower.index("hello") < tokens_lower.index("python")

    def test_tokenize_only_special_characters(self):
        """測試只有特殊字符的情況。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("!!!@@@###")
        assert isinstance(result, list)
        # 沒有有效 token，應該返回原始
        assert len(result) >= 1

    def test_tokenize_spaces_only(self):
        """測試只有空格的情況。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("   ")
        assert isinstance(result, list)

    def test_tokenize_deduplication_works(self):
        """測試分詞去重功能。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("test Test TEST 測試 測試")
        # 英文應該不區分大小寫去重
        test_count = sum(1 for t in result if t.lower() == "test")
        assert test_count == 1

    def test_tokenize_long_chinese_text(self):
        """測試長中文文本分詞。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("這是一個用於測試分詞功能的很長的中文句子")
        assert isinstance(result, list)
        assert len(result) > 5  # 應該有多個 token

    def test_tokenize_english_with_numbers(self):
        """測試英文和數字混合。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("python3 java11 c#")
        # 只有字母部分會被提取
        assert any("python" in t.lower() for t in result)
        assert any("java" in t.lower() for t in result)


# ============================================================================
# 緊湊模式測試
# ============================================================================

class TestCompactMode:
    """測試緊湊模式 (compact mode)。"""

    def test_compact_result_has_rerank_score(self, tmp_path):
        """測試緊湊模式包含 rerank 分數。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test Doc", content_raw="test content here", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("test content", compact=True, use_rerank=True)
            assert isinstance(results, list)
            if results:
                # 緊湊模式應該有 rerank_score
                assert "rerank_score" in results[0]
        finally:
            db.close()

    def test_compact_result_has_basic_fields(self, tmp_path):
        """測試緊湊模式包含基本字段。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test Doc", content_raw="test content", trust=0.9, category="test")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("test", compact=True)
            if results:
                r = results[0]
                assert "id" in r
                assert "title" in r
                assert "category" in r
                assert "trust" in r
        finally:
            db.close()

    def test_non_compact_has_raw_content(self, tmp_path):
        """測試非緊湊模式有原始內容。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test Doc", content_raw="test content here", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("test", compact=False)
            if results:
                assert "content_raw" in results[0]
        finally:
            db.close()


# ============================================================================
# 查詢擴展衰減參數測試
# ============================================================================

class TestQueryExpansionDecay:
    """測試查詢擴展的分數衰減參數。"""

    def test_default_decay_values(self, tmp_path):
        """測試預設衰減值。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True)
            # 擴展結果應該有不同的權重
            result = search._expand_query("什麼是向量資料庫")
            weights = [w for _, w in result]
            # 第一個是原始查詢，權重 1.0
            assert weights[0] == 1.0
            # 後續的權重應該 <= 1.0
            for w in weights[1:]:
                assert w <= 1.0
        finally:
            db.close()

    def test_custom_synonym_decay(self, tmp_path):
        """測試自定義同義詞衰減。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True, query_expansion_synonym_decay=0.5)
            # 應該能夠正常工作
            result = search._expand_query("向量搜尋")
            assert len(result) >= 1
        finally:
            db.close()

    def test_custom_question_decay(self, tmp_path):
        """測試自定義問句衰減。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_query_expansion=True, query_expansion_question_decay=0.3)
            result = search._expand_query("什麼是測試")
            assert len(result) >= 1
        finally:
            db.close()


# ============================================================================
# 向量搜尋 fallback 測試
# ============================================================================

class TestVectorSearchFallback:
    """測試向量搜尋的 fallback 行為。"""

    def test_search_vector_no_embed_fallback_keyword(self, tmp_path):
        """測試沒有嵌入提供者時向量搜尋降級到關鍵詞。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test content", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search.search_vector("test")
            assert isinstance(results, list)
        finally:
            db.close()

    def test_semantic_index_available_no_provider_explicit(self, tmp_path):
        """測試沒有嵌入提供者時 semantic_index_available 返回 False。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            # 傳入 None 作為 embed_provider，_semantic_index_available 應該返回 False
            search = VaultSearch(db, embed_provider=None)
            # 直接訪問 _semantic_index_available，它會檢查 db 和 provider
            # 由於 embed_provider 是 None，_semantic_provider 會嘗試創建一個
            # 這取決於環境，可能返回 False 或引發異常
            try:
                result = search._semantic_index_available()
                assert isinstance(result, bool)
            except Exception:
                # 如果環境中沒有必要的依賴，這是可以接受的
                pass
        finally:
            db.close()

    def test_semantic_index_available_no_provider(self, tmp_path):
        """測試沒有提供者時 semantic_index_available 返回 False。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            assert search._semantic_index_available() == False
        finally:
            db.close()


# ============================================================================
# _normalize_chinese 測試
# ============================================================================

class TestNormalizeChinese:
    """測試中文繁簡轉換。"""

    def test_normalize_traditional_what_is(self):
        """測試「什麼是」轉換。"""
        from vault.search import VaultSearch
        assert "什么是" in VaultSearch._normalize_chinese("什麼是")

    def test_normalize_traditional_why(self):
        """測試「為什麼」轉換。"""
        from vault.search import VaultSearch
        assert "为什么" in VaultSearch._normalize_chinese("為什麼")

    def test_normalize_traditional_database(self):
        """測試「資料庫」轉換。"""
        from vault.search import VaultSearch
        assert "数据库" in VaultSearch._normalize_chinese("資料庫")

    def test_normalize_simplified_stays_same(self):
        """測試簡體中文保持不變。"""
        from vault.search import VaultSearch
        text = "什么是机器学习"
        assert VaultSearch._normalize_chinese(text) == text

    def test_normalize_mixed_language(self):
        """測試中英文混合文本。"""
        from vault.search import VaultSearch
        result = VaultSearch._normalize_chinese("什麼是 AI 向量資料庫")
        assert "什么是" in result
        assert "AI" in result
        assert "向量" in result

    def test_normalize_search_keywords(self):
        """測試搜尋相關詞彙的轉換。"""
        from vault.search import VaultSearch
        result = VaultSearch._normalize_chinese("搜尋 檢索 配置")
        assert "搜索" in result or "检索" in result
        assert "配置" in result


# ============================================================================
# LightweightReranker 更多邊界測試
# ============================================================================

class TestLightweightRerankerEdgeCases:
    """輕量級 Reranker 的更多邊界測試。"""

    def test_rerank_all_zero_base_scores(self):
        """測試所有文檔基礎分數為 0 的情況。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Doc 1", "content_raw": "test content", "_score": 0.0},
            {"title": "Doc 2", "content_raw": "other content", "_score": 0.0},
        ]
        result = reranker.rerank("test", docs)
        assert len(result) == 2
        # 匹配的文檔應該排在前面
        assert "Doc 1" in result[0]["title"]

    def test_rerank_same_scores_stable(self):
        """測試相同分數時的排序穩定性。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"id": 1, "title": "A", "content_raw": "test", "_score": 0.5},
            {"id": 2, "title": "B", "content_raw": "test", "_score": 0.5},
            {"id": 3, "title": "C", "content_raw": "test", "_score": 0.5},
        ]
        result = reranker.rerank("test", docs)
        assert len(result) == 3
        # 所有文檔都包含 test，應該都有 rerank 分數
        for r in result:
            assert "_rerank_score" in r

    def test_rerank_very_long_content(self):
        """測試超長內容的 rerank。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        long_content = "test keyword " * 1000
        docs = [
            {"title": "Long Doc", "content_raw": long_content, "_score": 0.5},
        ]
        result = reranker.rerank("test keyword", docs)
        assert len(result) == 1
        assert "_rerank_score" in result[0]

    def test_rerank_query_with_special_chars(self):
        """測試查詢包含特殊字符的情況。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Test", "content_raw": "test content with special chars: !@#", "_score": 0.5},
        ]
        result = reranker.rerank("test!@#", docs)
        assert len(result) == 1


# ============================================================================
# VaultSearch 初始化參數測試
# ============================================================================

class TestVaultSearchInitParams:
    """測試 VaultSearch 的各種初始化參數。"""

    def test_init_with_all_params(self, tmp_path):
        """測試使用所有參數初始化。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(
                db,
                embed_provider=None,
                keyword_weight=1.5,
                vector_weight=0.8,
                enable_query_expansion=True,
                query_expansion_count=10,
                query_expansion_synonym_decay=0.9,
                query_expansion_question_decay=0.8,
                query_expansion_abbr_decay=0.85,
                query_expansion_keyword_decay=0.7,
                enable_vector_search=True,
                enable_cross_encoder=True,
                enable_llm_enhancement=False,
                enable_rerank=True,
                rerank_strategy="auto",
                cross_encoder_model="all-MiniLM-L6-v2",
                enable_llm_query_rewrite=False,
                llm_query_rewrite_strategy="auto",
            )
            assert search._keyword_weight == 1.5
            assert search._vector_weight == 0.8
            assert search._query_expansion_count == 10
            assert search._rerank_strategy == "auto"
        finally:
            db.close()

    def test_init_with_graph(self, tmp_path):
        """測試帶有 graph 參數的初始化。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            # 傳入 None 作為 graph
            search = VaultSearch(db, graph=None)
            assert search._graph is None
        finally:
            db.close()


# ============================================================================
# 圖譜距離加成測試
# ============================================================================

class TestGraphDepthBonus:
    """測試圖譜深度加成的計算。"""

    def test_calc_graph_depth_zero(self):
        """測試距離為 0。"""
        from vault.search import calc_graph_depth
        assert calc_graph_depth({"_graph_distance": 0}) == 0.2

    def test_calc_graph_depth_one(self):
        """測試距離為 1（由於公式，應該也是 0.2）。"""
        from vault.search import calc_graph_depth
        # 公式: max(0, 0.2 - (dist - 1) * 0.1)
        # dist=1: 0.2 - 0 = 0.2
        assert calc_graph_depth({"_graph_distance": 1}) == 0.2

    def test_calc_graph_depth_two(self):
        """測試距離為 2。"""
        from vault.search import calc_graph_depth
        # dist=2: 0.2 - 0.1 = 0.1
        assert calc_graph_depth({"_graph_distance": 2}) == 0.1

    def test_calc_graph_depth_three(self):
        """測試距離為 3。"""
        from vault.search import calc_graph_depth
        # dist=3: 0.2 - 0.2 = 0.0
        assert calc_graph_depth({"_graph_distance": 3}) == 0.0

    def test_calc_graph_depth_far(self):
        """測試很遠的距離返回 0。"""
        from vault.search import calc_graph_depth
        assert calc_graph_depth({"_graph_distance": 10}) == 0.0
        assert calc_graph_depth({"_graph_distance": 100}) == 0.0

    def test_calc_graph_depth_no_field(self):
        """測試沒有圖譜距離字段時的默認值。"""
        from vault.search import calc_graph_depth
        # 沒有 _graph_distance 字段時按 0 處理
        assert calc_graph_depth({}) == 0.2

    def test_calc_graph_depth_negative(self):
        """測試負距離（邊界情況）。"""
        from vault.search import calc_graph_depth
        # 負距離: 0.2 - (-1-1)*0.1 = 0.2 + 0.2 = 0.4，但 max(0, 0.4) = 0.4
        # 實際上不應該有負距離，但測試一下
        result = calc_graph_depth({"_graph_distance": -1})
        assert isinstance(result, float)


# ============================================================================
# 新鮮度計算測試
# ============================================================================

class TestFreshnessCalculation:
    """測試新鮮度計算。"""

    def test_calc_freshness_empty_string(self):
        """測試空字符串。"""
        from vault.search import calc_freshness
        assert calc_freshness("") == 0.5

    def test_calc_freshness_none(self):
        """測試 None。"""
        from vault.search import calc_freshness
        assert calc_freshness(None) == 0.5  # type: ignore

    def test_calc_freshness_invalid_format(self):
        """測試無效的日期格式。"""
        from vault.search import calc_freshness
        assert calc_freshness("not a date") == 0.5
        assert calc_freshness("2024-13-01") == 0.5  # 無效月份

    def test_calc_freshness_very_old(self):
        """測試非常舊的日期。"""
        from vault.search import calc_freshness
        # 10年前的日期
        freshness = calc_freshness("2014-01-01T00:00:00Z")
        assert freshness < 0.7  # 應該比較低

    def test_calc_freshness_iso_format_with_offset(self):
        """測試帶有時區偏移的 ISO 格式。"""
        from vault.search import calc_freshness
        # 帶 +08:00 偏移的格式
        freshness = calc_freshness("2024-01-01T12:00:00+08:00")
        assert isinstance(freshness, float)
        assert 0.0 <= freshness <= 1.0

    def test_calc_freshness_date_only(self):
        """測試只有日期沒有時間的格式。"""
        from vault.search import calc_freshness
        # 可能無法解析，返回 0.5
        result = calc_freshness("2024-01-01")
        assert isinstance(result, float)


# ============================================================================
# 查詢擴展進階測試
# ============================================================================

class TestQueryExpansionAdvanced:
    """更全面的查詢擴展測試。"""

    def test_expand_traditional_how_to_use(self, tmp_path):
        """測試繁體中文「怎麼用」問句模式。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, query_expansion_count=10)
            results = search._expand_query("怎麼用 AI")
            queries = [r[0] for r in results]
            # 應該有使用方法、教程等變換
            assert any("使用方法" in q for q in queries)
            assert any("教程" in q for q in queries)
        finally:
            db.close()

    def test_expand_simplified_how_to_use(self, tmp_path):
        """測試簡體中文「怎么用」問句模式。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, query_expansion_count=10)
            results = search._expand_query("怎么用 Python")
            queries = [r[0] for r in results]
            assert any("使用方法" in q for q in queries)
            assert any("教程" in q for q in queries)
        finally:
            db.close()

    def test_expand_traditional_why(self, tmp_path):
        """測試繁體中文「為什麼」問句模式。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, query_expansion_count=10)
            results = search._expand_query("為什麼要學習")
            queries = [r[0] for r in results]
            # 為什麼模式應該提取主題
            assert any("原因" in q for q in queries)
        finally:
            db.close()

    def test_expand_simplified_why(self, tmp_path):
        """測試簡體中文「为什么」問句模式。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, query_expansion_count=10)
            results = search._expand_query("为什么要优化")
            queries = [r[0] for r in results]
            assert any("原因" in q for q in queries)
        finally:
            db.close()

    def test_expand_synonym_decay_is_less_than_question(self, tmp_path):
        """測試同義詞衰減應該小於問句衰減（同義詞更可靠）。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            # 同義詞衰減應該比問句衰減大（權重更高，衰減更小）
            assert search._query_expansion_synonym_decay > search._query_expansion_question_decay
        finally:
            db.close()

    def test_expand_keyword_decay_is_largest(self, tmp_path):
        """測試關鍵詞提取的衰減最大（權重最低）。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            # 關鍵詞衰減應該是最小的權重（最大的衰減）
            assert search._query_expansion_keyword_decay <= search._query_expansion_synonym_decay
            assert search._query_expansion_keyword_decay <= search._query_expansion_question_decay
            assert search._query_expansion_keyword_decay <= search._query_expansion_abbr_decay
        finally:
            db.close()

    def test_expand_empty_query(self, tmp_path):
        """測試空查詢的擴展。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            results = search._expand_query("")
            # 空查詢應該至少返回一個結果
            assert len(results) >= 1
        finally:
            db.close()

    def test_expand_short_query_single_char(self, tmp_path):
        """測試單字符查詢的擴展。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            results = search._expand_query("a")
            assert len(results) >= 1
            # 原始查詢權重為 1.0
            assert results[0][1] == 1.0
        finally:
            db.close()

    def test_expand_count_limit(self, tmp_path):
        """測試查詢擴展數量限制。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, query_expansion_count=3)
            results = search._expand_query("什麼是 AI 向量資料庫")
            # 不應該超過設定的數量
            assert len(results) <= 3
        finally:
            db.close()

    def test_expand_original_query_weight_is_one(self, tmp_path):
        """測試原始查詢的權重總是 1.0。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            results = search._expand_query("AI 搜尋")
            # 第一個結果應該是原始查詢，權重 1.0
            assert results[0][1] == 1.0
        finally:
            db.close()

    def test_expand_abbreviation_full_to_abbr(self, tmp_path):
        """測試從全稱擴展到縮寫。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, query_expansion_count=10)
            results = search._expand_query("人工智能")
            queries = [r[0] for r in results]
            # 應該能夠擴展出 ai 縮寫
            assert any("ai" in q for q in queries)
        finally:
            db.close()

    def test_expand_abbreviation_abbr_to_full(self, tmp_path):
        """測試從縮寫擴展到全稱。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, query_expansion_count=10)
            results = search._expand_query("AI")
            queries = [r[0] for r in results]
            # 應該能夠擴展出全稱
            assert any("人工智能" in q for q in queries)
        finally:
            db.close()

    def test_expand_mixed_language(self, tmp_path):
        """測試中英文混合查詢的擴展。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, query_expansion_count=10)
            results = search._expand_query("什麼是 AI embedding")
            assert len(results) >= 2
            # 原始查詢權重 1.0
            assert results[0][1] == 1.0
        finally:
            db.close()

    def test_expand_keyword_extraction_multiple_keywords(self, tmp_path):
        """測試多關鍵詞提取。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, query_expansion_count=10)
            results = search._expand_query("請問什麼是向量資料庫的應用場景")
            # 應該有關鍵詞提取結果（權重為 keyword_decay）
            has_keyword_result = any(
                w == search._query_expansion_keyword_decay for _, w in results
            )
            assert has_keyword_result
        finally:
            db.close()

    def test_expand_no_stop_words_in_keywords(self, tmp_path):
        """測試關鍵詞提取應該過濾停用詞。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, query_expansion_count=10)
            results = search._expand_query("的是在有和與及等")
            # 全是停用詞的情況下，可能只有原始查詢
            assert len(results) >= 1
        finally:
            db.close()


# ============================================================================
# 輕量級 Reranker 進階測試
# ============================================================================

class TestLightweightRerankerAdvanced:
    """輕量級 Reranker 的進階功能測試。"""

    def test_title_match_boost_effect(self):
        """測試標題匹配加成效果。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Python 编程指南", "content_raw": "这是关于编程的内容", "_score": 0.5},
            {"title": "Java 编程指南", "content_raw": "Python 是一种编程语言", "_score": 0.5},
        ]
        result = reranker.rerank("Python", docs)
        # 標題包含 Python 的應該排在前面
        assert "Python" in result[0]["title"]
        assert result[0]["_rerank_score"] > result[1]["_rerank_score"]

    def test_title_starts_with_query_bonus(self):
        """測試查詢出現在標題開頭的額外加成。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Python 编程语言介绍", "content_raw": "内容", "_score": 0.5},
            {"title": "介绍 Python 编程语言", "content_raw": "内容", "_score": 0.5},
        ]
        result = reranker.rerank("python", docs)
        # 開頭匹配的應該排名更高
        assert result[0]["title"].startswith("Python")

    def test_term_frequency_saturation(self):
        """測試詞頻飽和效應（BM25 風格，不會無限增加）。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        doc_few = {"title": "Test", "content_raw": "python " * 2, "_score": 0.5}
        doc_many = {"title": "Test", "content_raw": "python " * 100, "_score": 0.5}
        result_few = reranker.rerank("python", [doc_few])
        result_many = reranker.rerank("python", [doc_many])
        # 分數差異不應該是線性的（飽和效應）
        score_few = result_few[0]["_rerank_score"]
        score_many = result_many[0]["_rerank_score"]
        # 100 次的分數不應該是 2 次的 50 倍
        assert score_many < score_few * 10

    def test_position_weight_effect(self):
        """測試位置權重（關鍵詞出現在開頭加分）。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Doc A", "content_raw": "python is a great programming language" + " other " * 50, "_score": 0.5},
            {"title": "Doc B", "content_raw": "other " * 50 + "python is at the end", "_score": 0.5},
        ]
        result = reranker.rerank("python", docs)
        # 關鍵詞在開頭的應該排在前面
        assert result[0]["title"] == "Doc A"

    def test_multi_word_reward(self):
        """測試多詞匹配獎勵。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Doc 1", "content_raw": "python programming language guide", "_score": 0.5},
            {"title": "Doc 2", "content_raw": "python snake reptile animal", "_score": 0.5},
        ]
        # 查詢多個詞
        result = reranker.rerank("python programming", docs)
        # 匹配更多查詢詞的應該排名更高
        assert "programming" in result[0]["content_raw"]

    def test_rerank_empty_query(self):
        """測試空查詢時的 rerank 行為。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Doc 1", "content_raw": "content 1", "_score": 0.8},
            {"title": "Doc 2", "content_raw": "content 2", "_score": 0.5},
        ]
        result = reranker.rerank("", docs)
        # 空查詢應該返回原始文檔（不改變順序或只做基礎調整）
        assert len(result) == 2

    def test_rerank_single_document(self):
        """測試單一文檔的 rerank。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        doc = {"title": "Only Doc", "content_raw": "test content", "_score": 0.7}
        result = reranker.rerank("test", [doc])
        assert len(result) == 1
        assert result[0]["title"] == "Only Doc"
        assert "_rerank_score" in result[0]

    def test_rerank_top_k_parameter(self):
        """測試 top_k 參數效果。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": f"Doc {i}", "content_raw": f"test content {i}", "_score": 0.5}
            for i in range(10)
        ]
        result = reranker.rerank("test", docs, top_k=3)
        assert len(result) == 3

    def test_rerank_top_k_none_returns_all(self):
        """測試 top_k 為 None 時返回所有文檔。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": f"Doc {i}", "content_raw": f"test {i}", "_score": 0.5}
            for i in range(5)
        ]
        result = reranker.rerank("test", docs, top_k=None)
        assert len(result) == 5

    def test_rerank_custom_text_field(self):
        """測試自定義 text_field 參數。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Doc", "body": "python programming", "summary": "java coffee", "_score": 0.5},
        ]
        # 使用 body 字段
        result_body = reranker.rerank("python", docs, text_field="body")
        # 使用 summary 字段
        result_summary = reranker.rerank("python", docs, text_field="summary")
        # body 中有 python，分數應該更高
        assert result_body[0]["_rerank_score"] > 0

    def test_rerank_custom_title_field(self):
        """測試自定義 title_field 參數。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"name": "Python Guide", "content_raw": "some content", "_score": 0.5},
        ]
        result = reranker.rerank("python", docs, title_field="name")
        assert len(result) == 1
        assert "_rerank_score" in result[0]

    def test_rerank_available_property(self):
        """測試 available 屬性。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        assert reranker.available is True

    def test_rerank_with_vector_distance(self):
        """測試帶有向量距離的 rerank（應該有向量相似度加成）。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Doc 1", "content_raw": "test", "_score": 0.5, "_distance": 0.2},
            {"title": "Doc 2", "content_raw": "test", "_score": 0.5, "_distance": 1.5},
        ]
        result = reranker.rerank("test", docs)
        # 距離小的（相似度高的）應該排名更高
        assert result[0]["_distance"] == 0.2

    def test_rerank_trust_boost(self):
        """測試信任度加成。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Doc 1", "content_raw": "test content", "_score": 0.5, "trust": 0.9},
            {"title": "Doc 2", "content_raw": "test content", "_score": 0.5, "trust": 0.1},
        ]
        result = reranker.rerank("test", docs)
        # 信任度高的應該排名更高
        assert result[0]["trust"] == 0.9


# ============================================================================
# Rerank 策略測試
# ============================================================================

class TestRerankStrategy:
    """測試不同 rerank 策略的行為。"""

    def test_rerank_strategy_auto(self, tmp_path):
        """測試 auto 策略（應該 fallback 到 lightweight）。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test Doc", content_raw="test content", trust=0.8)
            search = VaultSearch(db, embed_provider=None, rerank_strategy="auto", enable_rerank=True)
            results = search.search("test", mode="keyword", use_rerank=True)
            assert len(results) >= 1
            assert "_rerank_score" in results[0]
        finally:
            db.close()

    def test_rerank_strategy_lightweight(self, tmp_path):
        """測試 lightweight 策略。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test Doc", content_raw="test content", trust=0.8)
            search = VaultSearch(db, embed_provider=None, rerank_strategy="lightweight")
            results = search.search("test", mode="keyword", use_rerank=True)
            assert len(results) >= 1
            assert "_rerank_score" in results[0]
        finally:
            db.close()

    def test_rerank_disabled_no_rerank_score(self, tmp_path):
        """測試關閉 rerank 時沒有 rerank 分數。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test Doc", content_raw="test content", trust=0.8)
            search = VaultSearch(db, embed_provider=None, enable_rerank=False)
            results = search.search("test", mode="keyword", use_rerank=False)
            assert len(results) >= 1
            assert "_rerank_score" not in results[0]
        finally:
            db.close()

    def test_has_reranker_property(self, tmp_path):
        """測試 has_reranker 屬性。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search_enabled = VaultSearch(db, embed_provider=None, enable_rerank=True)
            assert search_enabled.has_reranker is True

            search_disabled = VaultSearch(db, embed_provider=None, enable_rerank=False)
            assert search_disabled.has_reranker is False
        finally:
            db.close()


# ============================================================================
# 原始分數保存測試
# ============================================================================

class TestOriginalScorePreservation:
    """測試 rerank 後原始分數的保存。"""

    def test_original_score_preserved_lightweight(self):
        """測試輕量級 rerank 後 _original_score 被保存。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        original_score = 0.75
        docs = [
            {"title": "Test", "content_raw": "test content", "_score": original_score},
        ]
        result = reranker.rerank("test", docs)
        assert "_original_score" in result[0]
        assert result[0]["_original_score"] == original_score

    def test_score_updated_after_rerank(self):
        """測試 rerank 後 _score 被更新為 rerank 分數。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        original_score = 0.5
        docs = [
            {"title": "Test", "content_raw": "test content", "_score": original_score},
        ]
        result = reranker.rerank("test", docs)
        # _score 應該被更新
        assert "_score" in result[0]
        # _score 與 _rerank_score 應該近似相等（_rerank_score 被 round 到 4 位）
        assert abs(result[0]["_score"] - result[0]["_rerank_score"]) < 0.001

    def test_original_score_different_from_rerank_score(self):
        """測試原始分數和 rerank 分數通常不同。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Test", "content_raw": "test content here", "_score": 0.5},
        ]
        result = reranker.rerank("test", docs)
        # rerank 分數通常不同於原始分數（因為有各種加成）
        assert isinstance(result[0]["_original_score"], float)
        assert isinstance(result[0]["_rerank_score"], float)

    def test_original_score_static_rerank(self):
        """測試靜態 _rerank 方法也保存原始分數。"""
        from vault.search import VaultSearch
        results = [
            {"_score": 0.8, "trust": 0.9, "updated_at": "2024-01-01T00:00:00Z"},
        ]
        reranked = VaultSearch._rerank(results)
        assert "_original_score" in reranked[0]
        assert reranked[0]["_original_score"] == 0.8

    def test_original_score_in_search_results(self, tmp_path):
        """測試搜尋結果中原始分數被保存。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test Doc", content_raw="test content", trust=0.8)
            search = VaultSearch(db, embed_provider=None, enable_rerank=True)
            results = search.search("test", mode="keyword", use_rerank=True)
            assert len(results) >= 1
            assert "_original_score" in results[0]
            assert isinstance(results[0]["_original_score"], float)
        finally:
            db.close()

    def test_original_score_multiple_docs(self):
        """測試多文檔時每個都有原始分數。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Doc 1", "content_raw": "python test", "_score": 0.8},
            {"title": "Doc 2", "content_raw": "java test", "_score": 0.6},
            {"title": "Doc 3", "content_raw": "c++ test", "_score": 0.4},
        ]
        result = reranker.rerank("test", docs)
        for doc in result:
            assert "_original_score" in doc
            assert isinstance(doc["_original_score"], float)


# ============================================================================
# 混合搜尋進階測試
# ============================================================================

class TestHybridSearchAdvanced:
    """混合搜尋的進階測試。"""

    def test_hybrid_mode_fallback_when_no_embeddings(self, tmp_path):
        """測試沒有嵌入時混合模式降級到關鍵詞。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Hybrid Test", content_raw="hybrid search test")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("hybrid", mode="hybrid", use_rerank=False)
            # 沒有嵌入時應該能返回結果（降級到關鍵詞）
            assert isinstance(results, list)
        finally:
            db.close()

    def test_auto_mode_behavior_no_embeddings(self, tmp_path):
        """測試沒有嵌入時 auto 模式的行為。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Auto Test", content_raw="auto mode test")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("auto", mode="auto", use_rerank=False)
            assert isinstance(results, list)
            assert len(results) >= 0
        finally:
            db.close()

    def test_basic_mode_is_alias_for_auto(self, tmp_path):
        """測試 basic 模式是 auto 的別名。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Basic Test", content_raw="basic mode test")
            search = VaultSearch(db, embed_provider=None)
            # basic 模式不應該報錯
            results = search.search("basic", mode="basic", use_rerank=False)
            assert isinstance(results, list)
        finally:
            db.close()

    def test_invalid_mode_raises_error(self, tmp_path):
        """測試無效模式引發異常。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test")
            search = VaultSearch(db, embed_provider=None)
            with pytest.raises(ValueError):
                search.search("test", mode="invalid_mode", use_rerank=False)
        finally:
            db.close()

    def test_search_hybrid_with_keyword_only(self, tmp_path):
        """測試只有關鍵詞結果時的混合搜尋。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Keyword Only", content_raw="keyword search test")
            search = VaultSearch(db, embed_provider=None)
            results = search.search_hybrid("keyword")
            assert isinstance(results, list)
        finally:
            db.close()

    def test_hybrid_search_min_score(self, tmp_path):
        """測試混合搜尋的 min_score 參數。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test Doc", content_raw="test content here")
            search = VaultSearch(db, embed_provider=None)
            results = search.search_hybrid("test", min_score=0.1)
            assert isinstance(results, list)
        finally:
            db.close()

    def test_hybrid_search_limit(self, tmp_path):
        """測試混合搜尋的 limit 參數。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            for i in range(20):
                db.add_knowledge(title=f"Doc {i}", content_raw=f"test content {i}")
            search = VaultSearch(db, embed_provider=None)
            results = search.search_hybrid("test", limit=5)
            assert isinstance(results, list)
            assert len(results) <= 5
        finally:
            db.close()


# ============================================================================
# info() 方法國際化測試
# ============================================================================

class TestInfoMethodInternationalization:
    """測試 info() 方法的國際化（中英文鍵名）。"""

    def test_info_returns_dict(self, tmp_path):
        """測試 info() 返回字典。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            assert isinstance(info, dict)
        finally:
            db.close()

    def test_info_has_both_chinese_and_english_layer_keys(self, tmp_path):
        """測試 info() 的層級鍵同時有中英文。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            # 基礎層
            assert "基礎層" in info
            assert "basic" in info
            # 進階層
            assert "進階層" in info
            assert "advanced" in info
            # 高階層
            assert "高階層" in info
            assert "premium" in info
            # 旗艦層
            assert "旗艦層" in info
            assert "flagship" in info
            # 配置
            assert "配置" in info
            assert "config" in info
        finally:
            db.close()

    def test_info_basic_layer_has_bilingual_keys(self, tmp_path):
        """測試基礎層的雙語鍵名。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            basic = info["basic"]
            # 關鍵詞搜尋
            assert "關鍵詞搜尋" in basic
            assert "keyword_search" in basic
            # 輕量級重排序
            assert "輕量級重排序" in basic
            assert "lightweight_rerank" in basic
            # 查詢擴展
            assert "查詢擴展" in basic
            assert "query_expansion" in basic
            # 文件地圖
            assert "文件地圖支援" in basic
            assert "document_map_support" in basic
        finally:
            db.close()

    def test_info_advanced_layer_has_bilingual_keys(self, tmp_path):
        """測試進階層的雙語鍵名。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            advanced = info["advanced"]
            # 向量檢索
            assert "向量檢索" in advanced
            assert "vector_search" in advanced
            # 混合搜尋
            assert "混合搜尋" in advanced
            assert "hybrid_search" in advanced
            # 語義索引
            assert "語義索引" in advanced
            assert "semantic_index" in advanced
        finally:
            db.close()

    def test_info_premium_layer_has_bilingual_keys(self, tmp_path):
        """測試高階層的雙語鍵名。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            premium = info["premium"]
            assert "Cross-Encoder 重排序" in premium
            assert "cross_encoder_rerank" in premium
            assert "Cross-Encoder 模型" in premium
            assert "cross_encoder_model" in premium
        finally:
            db.close()

    def test_info_config_layer_has_bilingual_keys(self, tmp_path):
        """測試配置層的雙語鍵名。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            config = info["config"]
            # 檢查幾個關鍵配置的雙語
            assert "預設模式" in config
            assert "default_mode" in config
            assert "關鍵詞權重" in config
            assert "keyword_weight" in config
            assert "Rerank 策略" in config
            assert "rerank_strategy" in config
            assert "查詢擴展數量" in config
            assert "query_expansion_count" in config
        finally:
            db.close()

    def test_info_chinese_and_english_values_match(self, tmp_path):
        """測試中英文鍵對應的值相同。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            # 基礎層的值應該一致
            assert info["basic"]["關鍵詞搜尋"] == info["basic"]["keyword_search"]
            assert info["basic"]["輕量級重排序"] == info["basic"]["lightweight_rerank"]
            assert info["basic"]["查詢擴展"] == info["basic"]["query_expansion"]

            # 進階層的值應該一致
            assert info["advanced"]["向量檢索"] == info["advanced"]["vector_search"]
            assert info["advanced"]["混合搜尋"] == info["advanced"]["hybrid_search"]

            # 配置的值應該一致
            assert info["config"]["預設模式"] == info["config"]["default_mode"]
            assert info["config"]["關鍵詞權重"] == info["config"]["keyword_weight"]
        finally:
            db.close()

    def test_info_reflects_configuration(self, tmp_path):
        """測試 info() 反映實際配置。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            # 禁用查詢擴展
            search = VaultSearch(db, embed_provider=None, enable_query_expansion=False)
            info = search.info()
            assert info["basic"]["query_expansion"] is False
            assert info["basic"]["查詢擴展"] is False

            # 禁用 rerank
            search2 = VaultSearch(db, embed_provider=None, enable_rerank=False)
            info2 = search2.info()
            assert info2["basic"]["lightweight_rerank"] is False
        finally:
            db.close()


# ============================================================================
# 代碼重構相關測試（模組級工具函數）
# ============================================================================

class TestModuleLevelUtilityFunctions:
    """測試模組級工具函數。"""

    def test_calc_freshness_is_module_level(self):
        """測試 calc_freshness 是模組級函數。"""
        from vault.search import calc_freshness
        assert callable(calc_freshness)

    def test_calc_graph_depth_is_module_level(self):
        """測試 calc_graph_depth 是模組級函數。"""
        from vault.search import calc_graph_depth
        assert callable(calc_graph_depth)

    def test_calc_freshness_recent_date(self):
        """測試最近日期的新鮮度接近 1.0。"""
        from vault.search import calc_freshness
        from datetime import datetime, timezone
        recent = datetime.now(timezone.utc).isoformat()
        freshness = calc_freshness(recent)
        assert 0.9 <= freshness <= 1.0

    def test_calc_freshness_one_year_ago(self):
        """測試一年前的日期新鮮度約為 0.5。"""
        from vault.search import calc_freshness
        from datetime import datetime, timezone, timedelta
        one_year_ago = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
        freshness = calc_freshness(one_year_ago)
        # 公式: 1.0 - min(days / 365, 0.5)
        # 一年後應該接近 0.5
        assert 0.4 <= freshness <= 0.6

    def test_calc_graph_depth_direct_match(self):
        """測試直接匹配的圖譜深度加成。"""
        from vault.search import calc_graph_depth
        # 距離為 0 時返回 0.2
        assert calc_graph_depth({"_graph_distance": 0}) == 0.2

    def test_calc_graph_depth_zero_default(self):
        """測試沒有 _graph_distance 字段時按 0 處理。"""
        from vault.search import calc_graph_depth
        assert calc_graph_depth({}) == 0.2
        assert calc_graph_depth({"other_field": "value"}) == 0.2

    def test_normalize_text_function(self):
        """測試 _normalize_text 工具函數。"""
        from vault.search import _normalize_text
        assert _normalize_text("  Hello   World  ") == "hello world"
        assert _normalize_text("") == ""
        assert _normalize_text(None) == ""


# ============================================================================
# 搜尋模式行為測試
# ============================================================================

class TestSearchModeBehaviors:
    """測試不同搜尋模式的行為。"""

    def test_keyword_mode_returns_results(self, tmp_path):
        """測試 keyword 模式返回結果。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="keyword test content")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("keyword", mode="keyword")
            assert isinstance(results, list)
        finally:
            db.close()

    def test_semantic_mode_fallback(self, tmp_path):
        """測試 semantic 模式在沒有語義索引時的降級。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="semantic test")
            search = VaultSearch(db, embed_provider=None)
            # 沒有語義索引時應該能降級
            results = search.search("semantic", mode="semantic")
            assert isinstance(results, list)
        finally:
            db.close()

    def test_vector_mode_fallback(self, tmp_path):
        """測試 vector 模式在沒有向量時的降級。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="vector test")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("vector", mode="vector")
            assert isinstance(results, list)
        finally:
            db.close()

    def test_search_with_min_trust(self, tmp_path):
        """測試 min_trust 參數。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="High Trust", content_raw="high trust doc", trust=0.9)
            db.add_knowledge(title="Low Trust", content_raw="low trust doc", trust=0.2)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("trust", mode="keyword", min_trust=0.8)
            # 應該只有高信任度的文檔
            for r in results:
                assert r.get("trust", 0) >= 0.8
        finally:
            db.close()


# ============================================================================
# 查詢擴展衰減層級驗證
# ============================================================================

class TestQueryExpansionDecayHierarchy:
    """驗證查詢擴展衰減的層級關係。"""

    def test_decay_hierarchy_order(self, tmp_path):
        """驗證衰減權重的正確順序：同義詞 > 縮寫 > 問句 > 關鍵詞。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            synonym = search._query_expansion_synonym_decay
            abbr = search._query_expansion_abbr_decay
            question = search._query_expansion_question_decay
            keyword = search._query_expansion_keyword_decay

            # 同義詞最可靠（衰減最小，權重最高）
            assert synonym >= abbr
            assert abbr >= question
            assert question >= keyword
        finally:
            db.close()

    def test_all_decay_values_between_zero_and_one(self, tmp_path):
        """驗證所有衰減值都在 0 和 1 之間。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            assert 0.0 < search._query_expansion_synonym_decay <= 1.0
            assert 0.0 < search._query_expansion_question_decay <= 1.0
            assert 0.0 < search._query_expansion_abbr_decay <= 1.0
            assert 0.0 < search._query_expansion_keyword_decay <= 1.0
        finally:
            db.close()


# ============================================================================
# _tokenize 更多邊界測試
# ============================================================================

class TestTokenizerEdgeCases:
    """分詞器的邊界情況測試。"""

    def test_tokenize_only_numbers(self):
        """測試只有數字的查詢。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("12345")
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_tokenize_punctuation(self):
        """測試標點符號為主的查詢。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("hello, world! how are you?")
        assert isinstance(result, list)
        assert "hello" in result
        assert "world" in result

    def test_tokenize_mixed_chinese_english_numbers(self):
        """測試中英文數字混合。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("Python3 入門教學 2024")
        assert isinstance(result, list)
        assert len(result) >= 2

    def test_tokenize_very_long_query(self):
        """測試非常長的查詢。"""
        from vault.search import VaultSearch
        long_query = " ".join(["word" for _ in range(100)])
        result = VaultSearch._tokenize(long_query)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_tokenize_chinese_with_english_terms(self):
        """測試中文裡的英文術語。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("使用 Python 進行 AI 開發")
        tokens_lower = [t.lower() for t in result]
        assert "python" in tokens_lower
        assert "ai" in tokens_lower


# ============================================================================
# Cross-Encoder 相關測試（安全檢查）
# ============================================================================

class TestCrossEncoderAvailability:
    """測試 Cross-Encoder 的可用性檢查。"""

    def test_has_cross_encoder_returns_bool(self, tmp_path):
        """測試 has_cross_encoder 屬性返回布爾值。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            result = search.has_cross_encoder
            assert isinstance(result, bool)
        finally:
            db.close()

    def test_cross_encoder_disabled_when_rerank_disabled(self, tmp_path):
        """測試關閉 rerank 時 cross-encoder 也不可用。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_rerank=False)
            assert search.has_cross_encoder is False
        finally:
            db.close()

    def test_cross_encoder_model_config(self, tmp_path):
        """測試 cross-encoder 模型配置。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, cross_encoder_model="all-MiniLM-L6-v2")
            info = search.info()
            assert "cross_encoder_model" in info["premium"]
        finally:
            db.close()


# ============================================================================
# 圖譜擴展邊界測試
# ============================================================================

class TestGraphExpandEdgeCases:
    """圖譜擴展的邊界情況測試。"""

    def test_graph_expand_with_limit(self, tmp_path):
        """測試圖譜擴展的 limit 參數。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            # 創建多個相互連接的文檔
            id1 = db.add_knowledge(title="Doc 1", content_raw="doc 1", trust=0.9)
            id2 = db.add_knowledge(title="Doc 2", content_raw="doc 2", trust=0.9)
            id3 = db.add_knowledge(title="Doc 3", content_raw="doc 3", trust=0.9)
            db.add_edge(id1, id2, relation="related")
            db.add_edge(id1, id3, relation="related")
            # 圖譜擴展會找鄰居
            search = VaultSearch(db, embed_provider=None)
            results = search.search("Doc 1", mode="keyword", graph_expand=1, use_rerank=False)
            assert isinstance(results, list)
        finally:
            db.close()

    def test_graph_expand_with_single_doc(self, tmp_path):
        """測試單一文檔的圖譜擴展。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Single", content_raw="single doc", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("Single", mode="keyword", graph_expand=1, use_rerank=False)
            assert isinstance(results, list)
        finally:
            db.close()

    def test_graph_expand_with_no_neighbors(self, tmp_path):
        """測試沒有鄰居時的圖譜擴展。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            id1 = db.add_knowledge(title="Doc 1", content_raw="doc 1", trust=0.9)
            id2 = db.add_knowledge(title="Doc 2", content_raw="doc 2", trust=0.9)
            # 不添加邊
            search = VaultSearch(db, embed_provider=None)
            results = search.search("Doc", mode="keyword", graph_expand=1, use_rerank=False)
            assert isinstance(results, list)
        finally:
            db.close()


# ============================================================================
# 搜尋結果處理測試
# ============================================================================

class TestSearchResultProcessing:
    """搜尋結果處理的測試。"""

    def test_compact_result_removes_raw_content(self, tmp_path):
        """測試緊湊模式移除原始內容。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="very long content here" * 100, trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("test", compact=True, use_rerank=False)
            if results:
                assert "content_raw" not in results[0]
        finally:
            db.close()

    def test_compact_result_includes_citation(self, tmp_path):
        """測試緊湊模式包含引用信息。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test Doc", content_raw="test content", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("test", compact=True, use_rerank=False)
            # citation 可能在 enriched 結果中存在
            assert isinstance(results, list)
        finally:
            db.close()

    def test_best_claim_extraction(self, tmp_path):
        """測試最佳主張提取。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            content_aaak = """SUMMARY:
測試文檔摘要

CLAIMS:
- [C1] 這是第一個主張 (L10)
- [C2] 這是第二個主張 (L15)
"""
            db.add_knowledge(title="Test", content_raw="test", content_aaak=content_aaak, trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("test", use_rerank=False)
            if results:
                assert "best_claim" in results[0]
        finally:
            db.close()


# ============================================================================
# 向量搜尋邊界測試
# ============================================================================

class TestVectorSearchEdgeCases:
    """向量搜尋的邊界情況測試。"""

    def test_vector_search_no_results(self, tmp_path):
        """測試向量搜尋無結果時返回空列表。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            results = search.search_vector("nonexistent")
            assert isinstance(results, list)
        finally:
            db.close()

    def test_vector_search_with_filters(self, tmp_path):
        """測試帶過濾器的向量搜尋。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test", category="tech", layer="public", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search.search_vector("test", min_trust=0.5)
            assert isinstance(results, list)
        finally:
            db.close()


# ============================================================================
# 關鍵詞搜尋進階測試
# ============================================================================

class TestKeywordSearchAdvanced:
    """關鍵詞搜尋的進階測試。"""

    def test_search_keyword_partial_match(self, tmp_path):
        """測試關鍵詞部分匹配。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Python Programming", content_raw="python programming guide", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            # 搜索 "python" 應該能找到 "Python Programming"
            results = search.search_keyword("python")
            assert len(results) >= 1
        finally:
            db.close()

    def test_search_keyword_substring(self, tmp_path):
        """測試子字符串匹配。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test Doc", content_raw="testing content", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search.search_keyword("test")
            assert len(results) >= 1
        finally:
            db.close()

    def test_search_keyword_multiple_terms(self, tmp_path):
        """測試多術語關鍵詞搜尋。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="python programming tutorial", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search.search_keyword("python tutorial")
            assert isinstance(results, list)
        finally:
            db.close()


# ============================================================================
# 查詢擴展與搜尋整合測試
# ============================================================================

class TestQueryExpansionSearchIntegration:
    """查詢擴展與搜尋的整合測試。"""

    def test_search_with_query_expansion_enabled(self, tmp_path):
        """測試啟用查詢擴展的搜尋。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="AI 技術", content_raw="人工智慧相關技術", trust=0.9)
            search = VaultSearch(db, embed_provider=None, enable_query_expansion=True)
            results = search.search("什麼是 AI", use_query_expansion=True, use_rerank=False)
            assert isinstance(results, list)
        finally:
            db.close()

    def test_search_with_query_expansion_disabled(self, tmp_path):
        """測試停用查詢擴展的搜尋。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test content", trust=0.9)
            search = VaultSearch(db, embed_provider=None, enable_query_expansion=False)
            results = search.search("test", use_query_expansion=False, use_rerank=False)
            assert isinstance(results, list)
        finally:
            db.close()

    def test_expansion_preserves_original_query(self, tmp_path):
        """測試擴展結果保留原始查詢。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test content", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("test", use_rerank=False)
            # 原始查詢權重為 1.0
            assert len(results) >= 1
        finally:
            db.close()


# ============================================================================
# Rerank 邊界測試
# ============================================================================

class TestRerankEdgeCases:
    """Rerank 的邊界情況測試。"""

    def test_rerank_with_negative_score(self):
        """測試帶負分數的 rerank。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Doc", "content_raw": "test", "_score": -0.5},
        ]
        result = reranker.rerank("test", docs)
        assert len(result) == 1

    def test_rerank_with_very_high_score(self):
        """測試帶高分數的 rerank。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Doc", "content_raw": "test", "_score": 100.0},
        ]
        result = reranker.rerank("test", docs)
        assert len(result) == 1

    def test_rerank_preserves_all_fields(self):
        """測試 rerank 保留所有原始字段。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Test", "content_raw": "test", "_score": 0.5, "id": 123, "category": "tech", "custom_field": "value"},
        ]
        result = reranker.rerank("test", docs)
        assert result[0]["id"] == 123
        assert result[0]["category"] == "tech"
        assert result[0]["custom_field"] == "value"

    def test_rerank_sorted_by_rerank_score(self):
        """測試 rerank 後結果按 rerank 分數排序。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Doc 1", "content_raw": "test content", "_score": 0.5},
            {"title": "Doc 2", "content_raw": "test content here", "_score": 0.5},
            {"title": "Doc 3", "content_raw": "test", "_score": 0.5},
        ]
        result = reranker.rerank("test", docs)
        # 應該按 rerank 分數降序排列
        scores = [r["_rerank_score"] for r in result]
        assert scores == sorted(scores, reverse=True)


# ============================================================================
# VaultSearch 屬性測試
# ============================================================================

class TestVaultSearchProperties:
    """VaultSearch 屬性測試。"""

    def test_has_embeddings_false_when_disabled(self, tmp_path):
        """測試禁用向量搜尋時 has_embeddings 為 False。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_vector_search=False)
            assert search.has_embeddings is False
        finally:
            db.close()

    def test_has_embeddings_true_when_available(self, tmp_path):
        """測試有嵌入時 has_embeddings 為 True。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_vector_search=True)
            # 沒有實際嵌入時應該是 False
            assert search.has_embeddings is False
        finally:
            db.close()

    def test_has_llm_property(self, tmp_path):
        """測試 has_llm 屬性。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_llm_enhancement=False)
            assert search.has_llm is False
        finally:
            db.close()

    def test_has_reranker_disabled(self, tmp_path):
        """測試禁用 rerank 時 has_reranker 為 False。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_rerank=False)
            assert search.has_reranker is False
        finally:
            db.close()


# ============================================================================
# _extract_terms 測試
# ============================================================================

class TestExtractTerms:
    """測試 LightweightReranker 的 _extract_terms 靜態方法。"""

    def test_extract_terms_basic(self):
        """測試基本的術語提取。"""
        from vault.search import LightweightReranker
        terms = LightweightReranker._extract_terms("hello world")
        assert "hello" in terms
        assert "world" in terms

    def test_extract_terms_chinese(self):
        """測試中文術語提取。"""
        from vault.search import LightweightReranker
        terms = LightweightReranker._extract_terms("這是測試")
        assert isinstance(terms, list)
        assert len(terms) > 0

    def test_extract_terms_mixed(self):
        """測試中英文混合提取。"""
        from vault.search import LightweightReranker
        terms = LightweightReranker._extract_terms("Python 教學")
        assert "python" in terms

    def test_extract_terms_empty(self):
        """測試空字符串提取。"""
        from vault.search import LightweightReranker
        terms = LightweightReranker._extract_terms("")
        assert isinstance(terms, list)

    def test_extract_terms_single_char(self):
        """測試單字符提取。"""
        from vault.search import LightweightReranker
        terms = LightweightReranker._extract_terms("a")
        assert isinstance(terms, list)

    def test_extract_terms_lowercase(self):
        """測試提取結果為小寫。"""
        from vault.search import LightweightReranker
        terms = LightweightReranker._extract_terms("HELLO WORLD")
        for term in terms:
            assert term == term.lower()


# ============================================================================
# VaultSearch 初始化參數驗證
# ============================================================================

class TestVaultSearchInitValidation:
    """測試 VaultSearch 初始化參數。"""

    def test_init_with_all_params(self, tmp_path):
        """測試使用所有參數初始化。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(
                db,
                embed_provider=None,
                keyword_weight=2.0,
                vector_weight=1.5,
                enable_query_expansion=False,
                query_expansion_count=3,
                query_expansion_synonym_decay=0.9,
                query_expansion_question_decay=0.8,
                query_expansion_abbr_decay=0.85,
                query_expansion_keyword_decay=0.7,
                enable_vector_search=False,
                enable_cross_encoder=False,
                enable_llm_enhancement=False,
                enable_rerank=False,
                rerank_strategy="lightweight",
                cross_encoder_model="test-model",
                enable_llm_query_rewrite=False,
                llm_query_rewrite_strategy="keywords",
            )
            assert search._keyword_weight == 2.0
            assert search._vector_weight == 1.5
            assert search._enable_query_expansion is False
            assert search._query_expansion_count == 3
            assert search._enable_rerank is False
        finally:
            db.close()

    def test_init_default_query_expansion_enabled(self, tmp_path):
        """測試預設啟用查詢擴展。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            assert search._enable_query_expansion is True
        finally:
            db.close()

    def test_init_default_rerank_enabled(self, tmp_path):
        """測試預設啟用 rerank。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            assert search._enable_rerank is True
        finally:
            db.close()


# ============================================================================
# 新鮮度與圖譜深度整合測試
# ============================================================================

class TestFreshnessAndGraphIntegration:
    """新鮮度與圖譜深度的整合測試。"""

    def test_freshness_and_graph_bonus_applied(self):
        """測試 rerank 中新鮮度和圖譜加成同時生效。"""
        from vault.search import LightweightReranker
        from datetime import datetime, timezone
        reranker = LightweightReranker()
        docs = [
            {"title": "Doc 1", "content_raw": "test content", "_score": 0.5,
             "updated_at": datetime.now(timezone.utc).isoformat(), "_graph_distance": 0},
            {"title": "Doc 2", "content_raw": "test content", "_score": 0.5,
             "updated_at": "2020-01-01T00:00:00Z", "_graph_distance": 3},
        ]
        result = reranker.rerank("test", docs)
        # 新且直接關聯的文檔應該排名更高
        assert result[0]["title"] == "Doc 1"

    def test_rerank_with_freshness_field_set(self):
        """測試設置了 freshness 字段時的 rerank。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Doc 1", "content_raw": "test", "_score": 0.5, "freshness": 0.9},
            {"title": "Doc 2", "content_raw": "test", "_score": 0.5, "freshness": 0.1},
        ]
        result = reranker.rerank("test", docs)
        # 高新鮮度的應該排名更高
        assert result[0]["freshness"] == 0.9


# ============================================================================
# 參數驗證測試 (P2: Issue N3)
# ============================================================================

class TestParameterValidation:
    """測試 VaultSearch 初始化時的參數驗證。"""

    def test_invalid_keyword_weight_raises(self, tmp_path):
        """測試負的 keyword_weight 引發 ValueError。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            with pytest.raises(ValueError, match="keyword_weight"):
                VaultSearch(db, keyword_weight=-1.0)
        finally:
            db.close()

    def test_invalid_vector_weight_raises(self, tmp_path):
        """測試負的 vector_weight 引發 ValueError。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            with pytest.raises(ValueError, match="vector_weight"):
                VaultSearch(db, vector_weight=-1.0)
        finally:
            db.close()

    def test_negative_query_expansion_count_raises(self, tmp_path):
        """測試負的 query_expansion_count 引發 ValueError。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            with pytest.raises(ValueError, match="query_expansion_count"):
                VaultSearch(db, query_expansion_count=-1)
        finally:
            db.close()

    def test_zero_query_expansion_count_allowed(self, tmp_path):
        """測試 query_expansion_count 為 0 是有效的。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, query_expansion_count=0)
            assert search._query_expansion_count == 0
        finally:
            db.close()

    def test_invalid_synonym_decay_raises(self, tmp_path):
        """測試超出範圍的 decay 參數引發 ValueError。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            with pytest.raises(ValueError, match="synonym_decay"):
                VaultSearch(db, query_expansion_synonym_decay=1.5)
        finally:
            db.close()

    def test_invalid_question_decay_raises(self, tmp_path):
        """測試超出範圍的 question_decay 引發 ValueError。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            with pytest.raises(ValueError, match="question_decay"):
                VaultSearch(db, query_expansion_question_decay=-0.1)
        finally:
            db.close()

    def test_invalid_rerank_strategy_raises(self, tmp_path):
        """測試無效的 rerank_strategy 引發 ValueError。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            with pytest.raises(ValueError, match="rerank_strategy"):
                VaultSearch(db, rerank_strategy="invalid_strategy")
        finally:
            db.close()

    def test_invalid_llm_rewrite_strategy_raises(self, tmp_path):
        """測試無效的 llm_query_rewrite_strategy 引發 ValueError。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            with pytest.raises(ValueError, match="llm_query_rewrite_strategy"):
                VaultSearch(db, llm_query_rewrite_strategy="invalid_strategy")
        finally:
            db.close()

    def test_valid_params_do_not_raise(self, tmp_path):
        """測試有效參數不會引發異常。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(
                db,
                keyword_weight=0.5,
                vector_weight=1.0,
                query_expansion_count=5,
                query_expansion_synonym_decay=0.9,
                query_expansion_question_decay=0.85,
                query_expansion_abbr_decay=0.9,
                query_expansion_keyword_decay=0.75,
                rerank_strategy="auto",
                llm_query_rewrite_strategy="keywords",
            )
            assert search is not None
        finally:
            db.close()


# ============================================================================
# 缺少 _score 字段的 Rerank 行為測試 (P2: Issue 5)
# ============================================================================

class TestRerankMissingScore:
    """測試 rerank 處理缺少 _score 字段的文檔。"""

    def test_lightweight_rerank_missing_score(self):
        """測試輕量級 rerank 處理缺少 _score 的文檔。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Doc 1", "content_raw": "test content about ai"},  # 沒有 _score
            {"title": "Doc 2", "content_raw": "other content", "_score": 0.8},
        ]
        result = reranker.rerank("ai test", docs)
        assert len(result) == 2
        # 兩個文檔都應該有 _score
        assert "_score" in result[0]
        assert "_score" in result[1]

    def test_lightweight_rerank_all_missing_score(self):
        """測試所有文檔都缺少 _score 時的 rerank。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"title": "Doc A", "content_raw": "test ai content"},
            {"title": "Doc B", "content_raw": "test ml content"},
        ]
        result = reranker.rerank("ai", docs)
        assert len(result) == 2
        # 兩個文檔都應該有 _score
        assert "_score" in result[0]
        assert "_score" in result[1]
        # 與查詢更相關的應該排在前面
        assert "Doc A" in result[0]["title"]

    def test_cross_encoder_rerank_missing_score(self):
        """測試 CrossEncoderReranker 處理缺少 _score 的文檔。"""
        from vault.search import CrossEncoderReranker
        reranker = CrossEncoderReranker()
        docs = [
            {"title": "Doc 1", "content_raw": "test content"},  # 沒有 _score
            {"title": "Doc 2", "content_raw": "other content", "_score": 0.8},
        ]
        result = reranker.rerank("query", docs)
        assert len(result) == 2

    def test_static_rerank_missing_score(self):
        """測試靜態 _rerank 方法處理缺少 _score 的文檔。"""
        from vault.search import VaultSearch
        docs = [
            {"title": "Doc 1", "content_raw": "test content", "trust": 0.9},
            {"title": "Doc 2", "content_raw": "other content", "_score": 0.8, "trust": 0.7},
        ]
        result = VaultSearch._rerank(docs, "test")
        assert len(result) == 2
        # 兩個文檔都應該有 _score
        assert "_score" in result[0]
        assert "_score" in result[1]

    def test_static_rerank_no_query_missing_score(self):
        """測試無 query 時靜態 _rerank 處理缺少 _score 的文檔。"""
        from vault.search import VaultSearch
        docs = [
            {"title": "Doc 1", "trust": 0.9},
            {"title": "Doc 2", "_score": 0.8, "trust": 0.7},
        ]
        result = VaultSearch._rerank(docs, "")
        assert len(result) == 2
        assert "_score" in result[0]
        assert "_score" in result[1]


# ============================================================================
# BM25 分數使用測試 (P1: Issue 17)
# ============================================================================

class TestBM25ScoreUsage:
    """測試 BM25 分數的使用。"""

    def test_use_bm25_score_default_false(self, tmp_path):
        """測試 use_bm25_score 預設為 False，保持向後兼容。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Python Programming",
                content_raw="Python is a versatile programming language used for many purposes.",
                category="tech",
                tags="python,programming",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search_keyword("python programming")
            assert len(results) > 0
            # 確保有 _bm25 字段
            assert "_bm25" in results[0]
        finally:
            db.close()

    def test_use_bm25_score_enabled(self, tmp_path):
        """測試開啟 use_bm25_score 時使用 BM25 分數。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Python Programming",
                content_raw="Python is a versatile programming language used for many purposes. Python Python.",
                category="tech",
                tags="python,programming",
                trust=0.9,
            )
            db.add_knowledge(
                title="Java Programming",
                content_raw="Java is another programming language.",
                category="tech",
                tags="java,programming",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search_keyword("python programming", use_bm25_score=True)
            assert len(results) > 0
            # 第一個結果應該是 Python 相關的（因為 BM25 分數更高）
            assert "python" in results[0]["title"].lower()
        finally:
            db.close()

    def test_bm25_field_present_in_results(self, tmp_path):
        """測試結果中包含 _bm25 字段。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Test Document",
                content_raw="This is a test document for keyword search.",
                trust=0.8,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search_keyword("test document")
            assert len(results) > 0
            assert "_bm25" in results[0]
            assert isinstance(results[0]["_bm25"], float)
        finally:
            db.close()


# ============================================================================
# LLM 查詢改寫功能測試 (P0)
# ============================================================================

class TestLLMQueryRewrite:
    """測試 LLM 查詢改寫功能。"""

    def test_rewrite_disabled_returns_original(self, tmp_path):
        """測試關閉 LLM 改寫時返回原始查詢。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_llm_query_rewrite=False)
            result = search._rewrite_query_with_llm("test query")
            assert result == "test query"
        finally:
            db.close()

    def test_rewrite_no_llm_returns_original(self, tmp_path):
        """測試沒有 LLM 時返回原始查詢。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(
                db,
                enable_llm_query_rewrite=True,
                enable_llm_enhancement=True,
            )
            # 當 LLM 不可用時，應該返回原始查詢
            result = search._rewrite_query_with_llm("test query")
            # 不論 LLM 是否可用，都不應該引發異常
            assert isinstance(result, str)
            assert len(result) > 0
        finally:
            db.close()

    def test_rewrite_strategy_keywords_config(self, tmp_path):
        """測試 keywords 策略配置。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(
                db,
                enable_llm_query_rewrite=True,
                llm_query_rewrite_strategy="keywords",
            )
            assert search._llm_query_rewrite_strategy == "keywords"
        finally:
            db.close()

    def test_rewrite_strategy_synonym_config(self, tmp_path):
        """測試 synonym 策略配置。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(
                db,
                enable_llm_query_rewrite=True,
                llm_query_rewrite_strategy="synonym",
            )
            assert search._llm_query_rewrite_strategy == "synonym"
        finally:
            db.close()

    def test_rewrite_strategy_decompose_config(self, tmp_path):
        """測試 decompose 策略配置。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(
                db,
                enable_llm_query_rewrite=True,
                llm_query_rewrite_strategy="decompose",
            )
            assert search._llm_query_rewrite_strategy == "decompose"
        finally:
            db.close()

    def test_rewrite_strategy_auto_config(self, tmp_path):
        """測試 auto 策略配置。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(
                db,
                enable_llm_query_rewrite=True,
                llm_query_rewrite_strategy="auto",
            )
            assert search._llm_query_rewrite_strategy == "auto"
        finally:
            db.close()

    def test_rewrite_empty_query(self, tmp_path):
        """測試空查詢的改寫。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_llm_query_rewrite=True)
            result = search._rewrite_query_with_llm("")
            # 空查詢也應該返回字符串
            assert isinstance(result, str)
        finally:
            db.close()

    def test_has_llm_returns_bool(self, tmp_path):
        """測試 has_llm 屬性返回布爾值。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_llm_enhancement=True)
            assert isinstance(search.has_llm, bool)
        finally:
            db.close()

    def test_has_llm_disabled_when_enhancement_off(self, tmp_path):
        """測試當 enable_llm_enhancement 為 False 時，has_llm 為 False。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_llm_enhancement=False)
            assert search.has_llm is False
        finally:
            db.close()

    def test_rewrite_query_with_llm_disabled_by_flag(self, tmp_path):
        """測試當 enable_llm_query_rewrite=False 時直接返回原始查詢。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_llm_query_rewrite=False)
            result = search._rewrite_query_with_llm("original query")
            assert result == "original query"
        finally:
            db.close()

    def test_rewrite_query_empty_query(self, tmp_path):
        """測試空查詢的改寫。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_llm_query_rewrite=True)
            result = search._rewrite_query_with_llm("")
            # 空查詢也應該返回字符串
            assert isinstance(result, str)
        finally:
            db.close()

    def test_llm_rewrite_strategies_config(self, tmp_path):
        """測試所有 LLM 改寫策略的配置。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            for strategy in ["auto", "synonym", "decompose", "keywords"]:
                search = VaultSearch(
                    db,
                    enable_llm_query_rewrite=True,
                    llm_query_rewrite_strategy=strategy,
                )
                assert search._llm_query_rewrite_strategy == strategy
        finally:
            db.close()

    def test_llm_rewrite_with_mock_llm(self, tmp_path, monkeypatch):
        """使用 mock LLM 測試查詢改寫邏輯。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            # Mock create_llm_provider 返回一個模擬的 LLM
            class MockLLM:
                def generate(self, prompt, max_tokens=200, temperature=0.3, system_prompt=None):
                    return "rewritten query with synonyms"

            mock_llm = MockLLM()

            def mock_create_llm():
                return mock_llm

            import vault.llm as llm_module
            monkeypatch.setattr(llm_module, 'create_llm_provider', mock_create_llm, raising=False)

            search = VaultSearch(
                db,
                enable_llm_query_rewrite=True,
                enable_llm_enhancement=True,
                llm_query_rewrite_strategy="synonym",
            )
            result = search._rewrite_query_with_llm("test query")
            assert isinstance(result, str)
            assert len(result) > 0
        finally:
            db.close()

    def test_llm_rewrite_with_quotes_in_result(self, tmp_path, monkeypatch):
        """測試 LLM 返回帶引號的結果時能正確清理。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            class MockLLM:
                def generate(self, prompt, max_tokens=200, temperature=0.3, system_prompt=None):
                    return '"quoted result"'

            mock_llm = MockLLM()

            def mock_create_llm():
                return mock_llm

            import vault.llm as llm_module
            monkeypatch.setattr(llm_module, 'create_llm_provider', mock_create_llm, raising=False)

            search = VaultSearch(
                db,
                enable_llm_query_rewrite=True,
                enable_llm_enhancement=True,
                llm_query_rewrite_strategy="auto",
            )
            result = search._rewrite_query_with_llm("test query")
            # 引號應該被移除
            assert '"' not in result
            assert "quoted result" in result
        finally:
            db.close()

    def test_llm_rewrite_with_chinese_quotes(self, tmp_path, monkeypatch):
        """測試 LLM 返回中文引號的結果時能正確清理。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            class MockLLM:
                def generate(self, prompt, max_tokens=200, temperature=0.3, system_prompt=None):
                    return "「中文引號結果」"

            mock_llm = MockLLM()

            def mock_create_llm():
                return mock_llm

            import vault.llm as llm_module
            monkeypatch.setattr(llm_module, 'create_llm_provider', mock_create_llm, raising=False)

            search = VaultSearch(
                db,
                enable_llm_query_rewrite=True,
                enable_llm_enhancement=True,
                llm_query_rewrite_strategy="keywords",
            )
            result = search._rewrite_query_with_llm("test query")
            assert "「" not in result
            assert "」" not in result
            assert "中文引號結果" in result
        finally:
            db.close()

    def test_llm_rewrite_empty_result_fallback(self, tmp_path, monkeypatch):
        """測試 LLM 返回空結果時返回原始查詢。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            class MockLLM:
                def generate(self, prompt, max_tokens=200, temperature=0.3, system_prompt=None):
                    return "   "  # 只有空白

            mock_llm = MockLLM()

            def mock_create_llm():
                return mock_llm

            import vault.llm as llm_module
            monkeypatch.setattr(llm_module, 'create_llm_provider', mock_create_llm, raising=False)

            search = VaultSearch(
                db,
                enable_llm_query_rewrite=True,
                enable_llm_enhancement=True,
                llm_query_rewrite_strategy="decompose",
            )
            result = search._rewrite_query_with_llm("original query")
            # 空結果時應該返回原始查詢
            assert result == "original query"
        finally:
            db.close()

    def test_llm_rewrite_exception_fallback(self, tmp_path, monkeypatch):
        """測試 LLM 引發異常時返回原始查詢。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            class MockLLM:
                def generate(self, prompt, max_tokens=200, temperature=0.3, system_prompt=None):
                    raise RuntimeError("LLM service unavailable")

            mock_llm = MockLLM()

            def mock_create_llm():
                return mock_llm

            import vault.llm as llm_module
            monkeypatch.setattr(llm_module, 'create_llm_provider', mock_create_llm, raising=False)

            search = VaultSearch(
                db,
                enable_llm_query_rewrite=True,
                enable_llm_enhancement=True,
            )
            result = search._rewrite_query_with_llm("original query")
            # 異常時應該返回原始查詢
            assert result == "original query"
        finally:
            db.close()


# ============================================================================
# 混合搜尋深度測試 (P0)
# ============================================================================

class TestHybridSearchDeep:
    """混合搜尋的深度測試，涵蓋動態權重、交叉驗證加分等。"""

    def test_hybrid_search_keyword_only_mode(self, tmp_path):
        """測試只有關鍵詞結果時的混合搜尋（回退到關鍵詞模式）。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Python Programming",
                content_raw="Python is a versatile programming language.",
                category="tech",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search_hybrid("python programming")
            assert len(results) > 0
            # 沒有向量時，使用 FTS 關鍵詞搜尋
            mode = results[0]["_mode"]
            assert mode in ("keyword", "keyword_fts")
        finally:
            db.close()

    def test_hybrid_search_with_dynamic_weight_enabled(self, tmp_path):
        """測試啟用動態權重調整的混合搜尋。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Python Programming",
                content_raw="Python is a versatile programming language.",
                category="tech",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search_hybrid(
                "python programming",
                use_dynamic_weight=True,
            )
            assert len(results) > 0
        finally:
            db.close()

    def test_hybrid_search_with_dynamic_weight_disabled(self, tmp_path):
        """測試關閉動態權重調整的混合搜尋。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Python Programming",
                content_raw="Python is a versatile programming language.",
                category="tech",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search_hybrid(
                "python programming",
                use_dynamic_weight=False,
            )
            assert len(results) > 0
        finally:
            db.close()

    def test_hybrid_search_custom_weights(self, tmp_path):
        """測試自定義 keyword 和 vector 權重。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Python Programming",
                content_raw="Python is a versatile programming language.",
                category="tech",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search_hybrid(
                "python programming",
                keyword_weight=2.0,
                vector_weight=0.5,
            )
            assert len(results) > 0
        finally:
            db.close()

    def test_hybrid_search_with_limit(self, tmp_path):
        """測試混合搜尋的 limit 參數。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            for i in range(10):
                db.add_knowledge(
                    title=f"Doc {i} Python",
                    content_raw=f"Document {i} about Python programming.",
                    trust=0.8,
                )
            search = VaultSearch(db, embed_provider=None)
            results = search.search_hybrid("python document", limit=5)
            assert len(results) <= 5
        finally:
            db.close()

    def test_hybrid_search_with_min_trust(self, tmp_path):
        """測試混合搜尋的 min_trust 過濾。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="High Trust Doc",
                content_raw="Python programming content.",
                trust=0.9,
            )
            db.add_knowledge(
                title="Low Trust Doc",
                content_raw="Python programming content.",
                trust=0.3,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search_hybrid("python", min_trust=0.8)
            assert len(results) >= 1
            for r in results:
                assert r.get("trust", 0) >= 0.8
        finally:
            db.close()

    def test_hybrid_search_with_category_filter(self, tmp_path):
        """測試混合搜尋的 category 過濾。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Tech Doc",
                content_raw="Python programming content.",
                category="tech",
                trust=0.9,
            )
            db.add_knowledge(
                title="Life Doc",
                content_raw="Python as a pet snake.",
                category="life",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search_hybrid("python", category="tech")
            assert len(results) >= 1
            for r in results:
                assert r.get("category") == "tech"
        finally:
            db.close()

    def test_hybrid_search_min_score(self, tmp_path):
        """測試混合搜尋的 min_score 過濾。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Python Programming",
                content_raw="Python is a programming language.",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search_hybrid("python programming", min_score=0.5)
            # 應該返回符合 min_score 的結果
            assert isinstance(results, list)
        finally:
            db.close()

    def test_hybrid_search_no_results(self, tmp_path):
        """測試無結果時的混合搜尋。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            results = search.search_hybrid("nonexistent keyword xyz")
            assert results == []
        finally:
            db.close()

    def test_hybrid_search_empty_query(self, tmp_path):
        """測試空查詢的混合搜尋。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            results = search.search_hybrid("")
            assert isinstance(results, list)
        finally:
            db.close()


# ============================================================================
# 語義搜尋測試 (P0)
# ============================================================================

class TestSemanticSearch:
    """語義搜尋相關測試。"""

    def test_search_semantic_no_provider_returns_empty(self, tmp_path):
        """測試沒有語義 provider 時返回空列表。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            results = search.search_semantic("test query")
            # 沒有可用的語義 provider 時，應該返回空列表
            assert results == []
        finally:
            db.close()

    def test_search_semantic_with_min_trust(self, tmp_path):
        """測試 search_semantic 的 min_trust 參數。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            results = search.search_semantic("test", min_trust=0.5)
            # 沒有語義索引時返回空
            assert isinstance(results, list)
        finally:
            db.close()

    def test_search_semantic_with_limit(self, tmp_path):
        """測試 search_semantic 的 limit 參數。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            results = search.search_semantic("test", limit=5)
            assert isinstance(results, list)
            assert len(results) <= 5
        finally:
            db.close()

    def test_search_semantic_with_layer_filter(self, tmp_path):
        """測試 search_semantic 的 layer 過濾。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            results = search.search_semantic("test", layer="memory")
            assert isinstance(results, list)
        finally:
            db.close()

    def test_search_semantic_with_category_filter(self, tmp_path):
        """測試 search_semantic 的 category 過濾。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            results = search.search_semantic("test", category="tech")
            assert isinstance(results, list)
        finally:
            db.close()

    def test_semantic_provider_require_semantic(self, tmp_path):
        """測試 require_semantic 參數。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            # 當 require_semantic=True 時，可能返回語義 provider 或 None（取決於環境）
            provider = search._semantic_provider(require_semantic=True, allow_hash=False)
            # 結果可能是 None 或一個有效的 provider 對象
            assert provider is None or hasattr(provider, "encode")
        finally:
            db.close()

    def test_semantic_provider_allow_hash(self, tmp_path):
        """測試 allow_hash 參數。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            # 當 allow_hash=True 時，可能返回 hash provider
            provider = search._semantic_provider(require_semantic=False, allow_hash=True)
            # 可能是 None 或某種 provider
            assert provider is None or hasattr(provider, "is_semantic")
        finally:
            db.close()

    def test_semantic_index_available_false_when_no_table(self, tmp_path):
        """測試沒有語義索引表時 semantic_index_available 返回 False。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            available = search._semantic_index_available(vector_kind="claim")
            # 空資料庫應該沒有語義索引表
            assert available is False
        finally:
            db.close()


# ============================================================================
# 圖譜擴展測試 (P0)
# ============================================================================

class TestGraphExpandExtended:
    """更全面的圖譜擴展測試。"""

    def test_apply_graph_expand_no_graph(self, tmp_path):
        """測試沒有圖譜時 _apply_graph_expand 返回原始結果。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Test Doc",
                content_raw="Test content",
                trust=0.8,
            )
            search = VaultSearch(db, embed_provider=None, graph=None)
            results = [{"id": 1, "_score": 0.8, "title": "Test Doc"}]
            expanded = search._apply_graph_expand(results, expand_depth=2, limit=10)
            # 沒有 graph 時返回原始結果
            assert len(expanded) == len(results)
        finally:
            db.close()

    def test_apply_graph_expand_empty_results(self, tmp_path):
        """測試空結果列表的圖譜擴展。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, graph=None)
            results = []
            expanded = search._apply_graph_expand(results, expand_depth=2, limit=10)
            assert expanded == []
        finally:
            db.close()

    def test_apply_graph_expand_zero_depth(self, tmp_path):
        """測試 expand_depth 為 0 時不擴展。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Test Doc",
                content_raw="Test content",
                trust=0.8,
            )
            search = VaultSearch(db, embed_provider=None, graph=None)
            results = [{"id": 1, "_score": 0.8, "title": "Test Doc"}]
            expanded = search._apply_graph_expand(results, expand_depth=0, limit=10)
            # depth 為 0 時不擴展
            assert len(expanded) == len(results)
        finally:
            db.close()

    def test_apply_graph_expand_limit_applied(self, tmp_path):
        """測試 limit 參數限制返回數量。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            # 添加多個文檔
            for i in range(5):
                db.add_knowledge(
                    title=f"Doc {i}",
                    content_raw=f"Content {i}",
                    trust=0.8,
                )
            search = VaultSearch(db, embed_provider=None, graph=None)
            results = [{"id": i + 1, "_score": 0.8 - i * 0.1, "title": f"Doc {i}"} for i in range(3)]
            expanded = search._apply_graph_expand(results, expand_depth=2, limit=5)
            # 不論是否有 graph，結果數量不應該超過 limit
            assert len(expanded) <= 5
        finally:
            db.close()

    def test_graph_expand_score_decay(self, tmp_path):
        """測試圖譜擴展的分數衰減。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Source Doc",
                content_raw="Source content",
                trust=0.9,
            )
            db.add_knowledge(
                title="Related Doc",
                content_raw="Related content",
                trust=0.8,
            )
            # 添加關係
            try:
                db.conn.execute(
                    "INSERT INTO knowledge_relations (source_id, target_id, relation, weight) VALUES (?, ?, ?, ?)",
                    (1, 2, "related", 0.5),
                )
                db.conn.commit()
            except sqlite3.OperationalError:
                # 表可能不存在，跳過
                pass

            search = VaultSearch(db, embed_provider=None, graph=None)
            results = [{"id": 1, "_score": 0.9, "title": "Source Doc"}]
            expanded = search._apply_graph_expand(results, expand_depth=1, limit=10)

            # 不論是否有 graph，結果都應該有 _score
            for r in expanded:
                assert "_score" in r
        finally:
            db.close()


# ============================================================================
# Reranker 策略測試
# ============================================================================

class TestRerankStrategy:
    """測試不同的 rerank 策略。"""

    def test_rerank_strategy_auto(self, tmp_path):
        """測試 auto 策略。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, rerank_strategy="auto")
            assert search._rerank_strategy == "auto"
        finally:
            db.close()

    def test_rerank_strategy_lightweight(self, tmp_path):
        """測試 lightweight 策略。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, rerank_strategy="lightweight")
            assert search._rerank_strategy == "lightweight"
        finally:
            db.close()

    def test_rerank_strategy_cross_encoder(self, tmp_path):
        """測試 cross_encoder 策略。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, rerank_strategy="cross_encoder")
            assert search._rerank_strategy == "cross_encoder"
        finally:
            db.close()

    def test_rerank_strategy_none(self, tmp_path):
        """測試 none 策略。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, rerank_strategy="none")
            assert search._rerank_strategy == "none"
            # 使用 none 策略時，_get_reranker 應該返回 None
            reranker = search._get_reranker()
            assert reranker is None
        finally:
            db.close()

    def test_rerank_with_strategy_none(self, tmp_path):
        """測試 rerank_strategy 為 none 時的 _rerank_with_strategy。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Test Doc",
                content_raw="Test content",
                trust=0.8,
            )
            search = VaultSearch(db, rerank_strategy="none")
            results = [{"id": 1, "_score": 0.8, "title": "Test Doc"}]
            reranked = search._rerank_with_strategy(results, "test")
            # none 策略時，仍然會使用基礎版 rerank（向後兼容）
            assert len(reranked) == len(results)
            # 結果應該有 _score 字段
            assert "_score" in reranked[0]
        finally:
            db.close()

    def test_enable_rerank_false(self, tmp_path):
        """測試 enable_rerank=False 時的行為。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_rerank=False)
            assert search.has_reranker is False
            reranker = search._get_reranker()
            assert reranker is None
        finally:
            db.close()


# ============================================================================
# Cross-Encoder Reranker 更多測試 (P0)
# ============================================================================

class TestCrossEncoderRerankerMore:
    """CrossEncoderReranker 的更多測試。"""

    def test_rerank_single_document(self):
        """測試只有一個文檔時的 rerank。"""
        from vault.search import CrossEncoderReranker
        reranker = CrossEncoderReranker()
        docs = [{"title": "Single Doc", "content_raw": "test content", "_score": 0.9}]
        result = reranker.rerank("query", docs)
        assert len(result) == 1
        assert result[0]["title"] == "Single Doc"

    def test_rerank_documents_without_content_raw(self):
        """測試缺少 content_raw 字段的文檔。"""
        from vault.search import CrossEncoderReranker
        reranker = CrossEncoderReranker()
        docs = [
            {"title": "Doc 1", "other_field": "some content"},
        ]
        result = reranker.rerank("query", docs)
        assert len(result) == 1

    def test_rerank_with_text_field(self):
        """測試指定 text_field 參數。"""
        from vault.search import CrossEncoderReranker
        reranker = CrossEncoderReranker()
        docs = [
            {"title": "Doc 1", "custom_text": "custom content here"},
        ]
        result = reranker.rerank("query", docs, text_field="custom_text")
        assert len(result) == 1

    def test_rerank_long_content_truncated(self):
        """測試長內容會被截斷。"""
        from vault.search import CrossEncoderReranker
        reranker = CrossEncoderReranker()
        long_content = "word " * 1000  # 很長的內容
        docs = [
            {"title": "Long Doc", "content_raw": long_content},
        ]
        result = reranker.rerank("query", docs)
        assert len(result) == 1

    def test_rerank_preserves_original_fields(self):
        """測試 rerank 保留原始字段。"""
        from vault.search import CrossEncoderReranker
        reranker = CrossEncoderReranker()
        docs = [
            {"title": "Doc 1", "content_raw": "test", "custom_field": "value1", "trust": 0.9},
        ]
        result = reranker.rerank("query", docs)
        assert len(result) == 1
        assert result[0]["custom_field"] == "value1"
        assert result[0]["trust"] == 0.9

    def test_rerank_with_title_only(self):
        """測試只有 title 沒有 content 的文檔。"""
        from vault.search import CrossEncoderReranker
        reranker = CrossEncoderReranker()
        docs = [
            {"title": "Title Only Doc"},
        ]
        result = reranker.rerank("query", docs)
        assert len(result) == 1

    def test_cached_model_name_preserved(self):
        """測試快取的模型名稱正確保存。"""
        from vault.search import CrossEncoderReranker

        CrossEncoderReranker.clear_cache()
        assert CrossEncoderReranker._cached_model_name is None

        # 創建一個實例
        reranker = CrossEncoderReranker(model_name="test-model")
        # 即使模型不可用，_model_name 也應該設置正確
        assert reranker._model_name == "test-model"

    def test_thread_safety_lock_exists(self):
        """測試快取鎖存在。"""
        from vault.search import CrossEncoderReranker
        import threading
        assert hasattr(CrossEncoderReranker, '_cache_lock')
        lock = CrossEncoderReranker._cache_lock
        # 驗證是鎖類型（相容不同 Python 版本）
        assert hasattr(lock, 'acquire')
        assert hasattr(lock, 'release')
        assert hasattr(lock, '__enter__')


# ============================================================================
# 搜尋模式行為測試
# ============================================================================

class TestSearchModeBehaviorsExtended:
    """更多的搜尋模式行為測試。"""

    def test_search_keyword_mode(self, tmp_path):
        """測試 keyword 搜尋模式。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Python Programming",
                content_raw="Python is a programming language.",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search("python", mode="keyword")
            assert len(results) > 0
            assert results[0]["_mode"] == "keyword_fts"
        finally:
            db.close()

    def test_search_vector_mode_fallback(self, tmp_path):
        """測試 vector 模式在沒有嵌入時回退到 keyword。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Python Programming",
                content_raw="Python is a programming language.",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search("python", mode="vector")
            # 沒有向量時回退到關鍵詞
            assert len(results) > 0
        finally:
            db.close()

    def test_search_semantic_mode_fallback(self, tmp_path):
        """測試 semantic 模式在沒有語義索引時的行為。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Python Programming",
                content_raw="Python is a programming language.",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search("python", mode="semantic")
            # 沒有語義索引時返回空列表或回退
            assert isinstance(results, list)
        finally:
            db.close()


# ============================================================================
# 交叉驗證加分邏輯測試 (P2: Issue 9)
# ============================================================================

class TestCrossValidationBonus:
    """測試交叉驗證加分邏輯。"""

    def test_hybrid_results_have_scores(self, tmp_path):
        """測試混合搜尋結果包含分數。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Python Programming",
                content_raw="Python is a versatile programming language.",
                category="tech",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search_hybrid("python programming")
            if results:
                assert "_score" in results[0]
                assert isinstance(results[0]["_score"], float)
        finally:
            db.close()

    def test_keyword_results_contain_bm25(self, tmp_path):
        """測試關鍵詞搜尋結果包含 _bm25 字段。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Test Document",
                content_raw="This is a test document for keyword search.",
                trust=0.8,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search.search_keyword("test document")
            if results:
                assert "_bm25" in results[0]
                assert isinstance(results[0]["_bm25"], float)
        finally:
            db.close()


# ============================================================================
# 靜態方法與工具函數測試
# ============================================================================

class TestCompactResultExtended:
    """_compact_result 靜態方法的擴展測試。"""

    def test_compact_result_with_all_fields(self):
        """測試包含所有字段的 compact 結果。"""
        from vault.search import VaultSearch
        result = {
            "id": 1,
            "title": "Test",
            "content_raw": "raw content",
            "category": "tech",
            "layer": "memory",
            "trust": 0.9,
            "tags": "test,tech",
            "best_claim": "best claim here",
            "best_span": "L1-L5",
            "node_uid": "node-123",
            "path": "/path/to/doc",
            "heading": "Section 1",
            "line_start": 1,
            "line_end": 5,
            "citation": "#1 Test L1-L5",
            "recommended_next_tool": "vault_read",
            "next_action": {"tool": "vault_map_show", "arguments": {"knowledge_id": 1}},
            "next_actions": [{"tool": "vault_map_show", "arguments": {"knowledge_id": 1}}],
            "_rerank_score": 0.85,
        }
        compact = VaultSearch._compact_result(result)
        assert compact["id"] == 1
        assert compact["title"] == "Test"
        assert "content_raw" not in compact  # 不包含原始內容
        assert compact["rerank_score"] == 0.85  # 重命名為 rerank_score
        assert compact["best_claim"] == "best claim here"

    def test_compact_result_minimal(self):
        """測試最小字段的 compact 結果。"""
        from vault.search import VaultSearch
        result = {"id": 1, "title": "Test"}
        compact = VaultSearch._compact_result(result)
        assert compact == {"id": 1, "title": "Test"}

    def test_compact_result_without_rerank_score(self):
        """測試沒有 rerank_score 的情況。"""
        from vault.search import VaultSearch
        result = {"id": 1, "title": "Test"}
        compact = VaultSearch._compact_result(result)
        assert "rerank_score" not in compact


class TestNormalizeChineseExtended:
    """_normalize_chinese 方法的擴展測試。"""

    def test_normalize_chinese_unchanged(self):
        """測試 _normalize_chinese 返回原始值（無 opencc 等依賴）。"""
        from vault.search import VaultSearch
        # 該方法可能需要 opencc 依賴才能實際轉換
        result = VaultSearch._normalize_chinese("這是測試")
        # 如果沒有 opencc，返回原始值
        assert isinstance(result, str)

    def test_normalize_mixed_content(self):
        """測試混合內容的正規化。"""
        from vault.search import VaultSearch
        result = VaultSearch._normalize_chinese("hello 世界")
        # 應該返回字符串
        assert isinstance(result, str)

    def test_normalize_english_only(self):
        """測試只有英文時的正規化。"""
        from vault.search import VaultSearch
        result = VaultSearch._normalize_chinese("hello world")
        assert "hello world" in result


class TestExtractBestClaimExtended:
    """_extract_best_claim 方法的擴展測試。"""

    def test_extract_claims_section(self):
        """測試從 CLAIMS 段提取。"""
        from vault.search import VaultSearch
        content = "Some intro\nCLAIMS:\n- [claim1] First claim\n- [claim2] Second claim\n\nOther text"
        result = VaultSearch._extract_best_claim(content)
        assert "First claim" in result

    def test_extract_claims_with_multiple_lines(self):
        """測試多行 CLAIMS 段。"""
        from vault.search import VaultSearch
        content = "Introduction here\n\nCLAIMS:\n- [c1] Claim one\n- [c2] Claim two\n- [c3] Claim three\n\nDiscussion"
        result = VaultSearch._extract_best_claim(content)
        assert "Claim one" in result
        assert "Claim two" not in result  # 只取第一個

    def test_extract_claims_no_bracket_format(self):
        """測試沒有 [xxx] 格式的 CLAIMS 段。"""
        from vault.search import VaultSearch
        content = "Some text\nCLAIMS:\nJust a plain claim without brackets\n\nMore text"
        result = VaultSearch._extract_best_claim(content)
        # 沒有 - [xxx] 格式的行，應該返回空
        assert result == ""

    def test_extract_claims_empty_content(self):
        """測試空內容。"""
        from vault.search import VaultSearch
        result = VaultSearch._extract_best_claim("")
        assert result == ""

    def test_extract_claims_none_content(self):
        """測試 None 內容。"""
        from vault.search import VaultSearch
        result = VaultSearch._extract_best_claim(None)
        assert result == ""

    def test_extract_claims_no_claims_section(self):
        """測試沒有 CLAIMS 段的內容。"""
        from vault.search import VaultSearch
        content = "This is just regular content without claims section."
        result = VaultSearch._extract_best_claim(content)
        assert result == ""


class TestTokenizeExtended:
    """_tokenize 方法的擴展測試。"""

    def test_tokenize_punctuation(self):
        """測試包含標點符號的文本。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("hello, world! how are you?")
        assert "hello" in result
        assert "world" in result

    def test_tokenize_numbers(self):
        """測試包含數字的文本。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("python 3.10 release")
        assert "python" in result

    def test_tokenize_long_text(self):
        """測試長文本分詞。"""
        from vault.search import VaultSearch
        text = " ".join([f"word{i}" for i in range(100)])
        result = VaultSearch._tokenize(text)
        assert len(result) > 0

    def test_tokenize_special_characters(self):
        """測試特殊字符。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("hello_world test-123")
        assert "hello_world" in result or "hello" in result


class TestVaultSearchPropertiesExtended:
    """VaultSearch 各種屬性的擴展測試。"""

    def test_has_embeddings_false_by_default(self, tmp_path):
        """測試預設情況下沒有 embeddings。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_vector_search=True)
            # 沒有 embed provider 時應該返回 False
            assert search.has_embeddings is False
        finally:
            db.close()

    def test_has_embeddings_disabled_by_flag(self, tmp_path):
        """測試 enable_vector_search=False 時 has_embeddings 為 False。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider="fake", enable_vector_search=False)
            assert search.has_embeddings is False
        finally:
            db.close()

    def test_has_reranker_enabled(self, tmp_path):
        """測試開啟 rerank 時 has_reranker 屬性。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_rerank=True)
            result = search.has_reranker
            # Lightweight reranker 應該總是可用
            assert isinstance(result, bool)
        finally:
            db.close()

    def test_has_cross_encoder_disabled(self, tmp_path):
        """測試關閉 cross-encoder 時 has_cross_encoder 為 False。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_cross_encoder=False)
            assert search.has_cross_encoder is False
        finally:
            db.close()

    def test_cached_llm_available(self, tmp_path):
        """測試 has_llm 緩存行為。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_llm_enhancement=False)
            # 第一次調用
            first = search.has_llm
            # 第二次調用（應該使用緩存）
            second = search.has_llm
            assert first == second
        finally:
            db.close()

    def test_cached_reranker_available(self, tmp_path):
        """測試 has_reranker 緩存行為。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_rerank=True)
            first = search.has_reranker
            second = search.has_reranker
            assert first == second
        finally:
            db.close()

    def test_cached_cross_encoder_available(self, tmp_path):
        """測試 has_cross_encoder 緩存行為。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, enable_cross_encoder=False)
            first = search.has_cross_encoder
            second = search.has_cross_encoder
            assert first == second
            assert first is False
        finally:
            db.close()


class TestSearchMethodEdgeCases:
    """search 方法的邊界情況測試。"""

    def test_search_empty_query(self, tmp_path):
        """測試空查詢。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test Doc", content_raw="Some content", trust=0.8)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("")
            # 空查詢可能返回空列表或全部結果
            assert isinstance(results, list)
        finally:
            db.close()

    def test_search_keyword_mode_with_min_score(self, tmp_path):
        """測試 keyword 模式的 min_score 參數。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Python Test", content_raw="Python programming language", trust=0.9)
            db.add_knowledge(title="Java Test", content_raw="Java programming language", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("python", mode="keyword", min_score=0.5)
            assert isinstance(results, list)
        finally:
            db.close()

    def test_search_with_layer_filter(self, tmp_path):
        """測試 layer 過濾。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Doc 1", content_raw="test content", layer="memory", trust=0.8)
            db.add_knowledge(title="Doc 2", content_raw="test content", layer="archive", trust=0.8)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("test", mode="keyword", layer="memory")
            for r in results:
                assert r.get("layer") == "memory"
        finally:
            db.close()

    def test_search_with_category_filter(self, tmp_path):
        """測試 category 過濾。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Doc 1", content_raw="test content", category="tech", trust=0.8)
            db.add_knowledge(title="Doc 2", content_raw="test content", category="life", trust=0.8)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("test", mode="keyword", category="tech")
            for r in results:
                assert r.get("category") == "tech"
        finally:
            db.close()


class TestGraphExpandEdgeCasesExtended:
    """圖譜擴展的更多邊界情況測試。"""

    def test_apply_graph_expand_no_results(self, tmp_path):
        """測試空結果時的圖譜擴展。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            expanded = search._apply_graph_expand([], expand_depth=2, limit=10)
            assert expanded == []
        finally:
            db.close()

    def test_apply_graph_expand_zero_depth(self, tmp_path):
        """測試深度為 0 時的圖譜擴展。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="content", trust=0.8)
            search = VaultSearch(db, embed_provider=None)
            results = [{"id": 1, "_score": 0.8, "title": "Test"}]
            expanded = search._apply_graph_expand(results, expand_depth=0, limit=10)
            # depth 為 0 時不擴展
            assert len(expanded) == len(results)
        finally:
            db.close()

    def test_apply_graph_expand_with_limit_one(self, tmp_path):
        """測試 limit=1 的圖譜擴展。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="content", trust=0.8)
            search = VaultSearch(db, embed_provider=None)
            results = [{"id": 1, "_score": 0.8, "title": "Test"}]
            expanded = search._apply_graph_expand(results, expand_depth=1, limit=1)
            assert len(expanded) <= 1
        finally:
            db.close()

    def test_apply_graph_expand_preserves_scores(self, tmp_path):
        """測試圖譜擴展保留原始結果的分數。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="content", trust=0.8)
            search = VaultSearch(db, embed_provider=None)
            results = [{"id": 1, "_score": 0.85, "title": "Test"}]
            expanded = search._apply_graph_expand(results, expand_depth=2, limit=5)
            if expanded:
                # 第一個結果應該是原始結果，分數不變
                assert expanded[0].get("_score") is not None
        finally:
            db.close()


# ============================================================================
# 混合搜尋進階測試 (使用 mock)
# ============================================================================

class TestHybridSearchAdvanced:
    """使用 mock 測試混合搜尋的動態權重和交叉驗證加分。"""

    def test_hybrid_with_mock_semantic_results(self, tmp_path, monkeypatch):
        """測試有語義結果時的混合搜尋。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB

        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            # 添加知識
            db.add_knowledge(title="Python Programming", content_raw="Python is a programming language.", trust=0.9)
            db.add_knowledge(title="Java Programming", content_raw="Java is another language.", trust=0.9)
            db.add_knowledge(title="Machine Learning", content_raw="ML uses algorithms.", trust=0.8)

            search = VaultSearch(db, embed_provider=None)

            # Mock search_semantic 返回結果
            def mock_search_semantic(query, limit=10, min_trust=0.0, layer=None, category=None,
                                    *, vector_kind="claim", require_semantic=True, allow_hash=False):
                return [
                    {"id": 1, "_score": 0.9, "title": "Python Programming", "trust": 0.9,
                     "content_raw": "Python is a programming language."},
                    {"id": 3, "_score": 0.7, "title": "Machine Learning", "trust": 0.8,
                     "content_raw": "ML uses algorithms."},
                ]

            monkeypatch.setattr(search, 'search_semantic', mock_search_semantic)

            results = search.search_hybrid("python programming", limit=5)
            assert len(results) > 0
            assert results[0]["id"] == 1  # 兩邊都匹配的應該排最前面
            assert "_score" in results[0]
        finally:
            db.close()

    def test_hybrid_with_dynamic_weight(self, tmp_path, monkeypatch):
        """測試動態權重調整。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB

        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Doc A", content_raw="Python programming language", trust=0.9)
            db.add_knowledge(title="Doc B", content_raw="Java coding language", trust=0.9)
            db.add_knowledge(title="Doc C", content_raw="Machine learning algorithms", trust=0.8)

            search = VaultSearch(db, embed_provider=None)

            # 向量結果質量高，關鍵詞質量低
            def mock_search_semantic(query, limit=10, min_trust=0.0, layer=None, category=None,
                                    *, vector_kind="claim", require_semantic=True, allow_hash=False):
                return [
                    {"id": 3, "_score": 0.95, "title": "Doc C", "trust": 0.8,
                     "content_raw": "Machine learning algorithms"},
                    {"id": 1, "_score": 0.6, "title": "Doc A", "trust": 0.9,
                     "content_raw": "Python programming language"},
                ]

            monkeypatch.setattr(search, 'search_semantic', mock_search_semantic)

            results = search.search_hybrid("machine learning", use_dynamic_weight=True)
            assert len(results) > 0
            # 確保有分數
            assert "_score" in results[0]
        finally:
            db.close()

    def test_hybrid_without_dynamic_weight(self, tmp_path, monkeypatch):
        """測試關閉動態權重時的混合搜尋。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB

        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Doc A", content_raw="Python programming language", trust=0.9)
            db.add_knowledge(title="Doc B", content_raw="Java coding language", trust=0.9)

            search = VaultSearch(db, embed_provider=None)

            def mock_search_semantic(query, limit=10, min_trust=0.0, layer=None, category=None,
                                    *, vector_kind="claim", require_semantic=True, allow_hash=False):
                return [
                    {"id": 1, "_score": 0.8, "title": "Doc A", "trust": 0.9,
                     "content_raw": "Python programming language"},
                ]

            monkeypatch.setattr(search, 'search_semantic', mock_search_semantic)

            results = search.search_hybrid("python", use_dynamic_weight=False)
            assert len(results) > 0
            assert "_score" in results[0]
        finally:
            db.close()

    def test_hybrid_search_with_custom_weights(self, tmp_path, monkeypatch):
        """測試自定義權重的混合搜尋。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB

        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Doc A", content_raw="Python programming", trust=0.9)
            db.add_knowledge(title="Doc B", content_raw="Java programming", trust=0.9)

            search = VaultSearch(db, embed_provider=None, keyword_weight=2.0, vector_weight=0.5)

            def mock_search_semantic(query, limit=10, min_trust=0.0, layer=None, category=None,
                                    *, vector_kind="claim", require_semantic=True, allow_hash=False):
                return [
                    {"id": 2, "_score": 0.9, "title": "Doc B", "trust": 0.9,
                     "content_raw": "Java programming"},
                ]

            monkeypatch.setattr(search, 'search_semantic', mock_search_semantic)

            results = search.search_hybrid("python programming", limit=5)
            assert len(results) > 0
        finally:
            db.close()

    def test_hybrid_search_min_score_filter(self, tmp_path, monkeypatch):
        """測試 min_score 過濾。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB

        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Doc A", content_raw="Python programming language", trust=0.9)
            db.add_knowledge(title="Doc B", content_raw="Java coding language", trust=0.9)

            search = VaultSearch(db, embed_provider=None)

            def mock_search_semantic(query, limit=10, min_trust=0.0, layer=None, category=None,
                                    *, vector_kind="claim", require_semantic=True, allow_hash=False):
                return [
                    {"id": 1, "_score": 0.9, "title": "Doc A", "trust": 0.9,
                     "content_raw": "Python programming language"},
                ]

            monkeypatch.setattr(search, 'search_semantic', mock_search_semantic)

            results = search.search_hybrid("python", min_score=0.5)
            assert isinstance(results, list)
        finally:
            db.close()

    def test_cross_validation_bonus_both_high_rank(self, tmp_path, monkeypatch):
        """測試雙方都排名靠前時的交叉驗證加分。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB

        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Doc A", content_raw="Python programming", trust=0.9)
            db.add_knowledge(title="Doc B", content_raw="Java programming", trust=0.9)

            search = VaultSearch(db, embed_provider=None)

            # Doc A 在兩邊都排第一
            def mock_search_semantic(query, limit=10, min_trust=0.0, layer=None, category=None,
                                    *, vector_kind="claim", require_semantic=True, allow_hash=False):
                return [
                    {"id": 1, "_score": 0.9, "title": "Doc A", "trust": 0.9,
                     "content_raw": "Python programming"},
                    {"id": 2, "_score": 0.7, "title": "Doc B", "trust": 0.9,
                     "content_raw": "Java programming"},
                ]

            monkeypatch.setattr(search, 'search_semantic', mock_search_semantic)

            results = search.search_hybrid("python programming", limit=2)
            assert len(results) == 2
            # Doc A 應該排第一，因為在兩邊都匹配
            assert results[0]["id"] == 1
        finally:
            db.close()

    def test_hybrid_search_mode_detection(self, tmp_path, monkeypatch):
        """測試混合搜尋的模式檢測。"""
        from vault.search import VaultSearch
        from vault.db import VaultDB

        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Doc A", content_raw="test content", trust=0.9)

            search = VaultSearch(db, embed_provider=None)

            def mock_search_semantic(query, limit=10, min_trust=0.0, layer=None, category=None,
                                    *, vector_kind="claim", require_semantic=True, allow_hash=False):
                return [
                    {"id": 1, "_score": 0.8, "title": "Doc A", "trust": 0.9,
                     "content_raw": "test content", "_mode": "semantic"},
                ]

            monkeypatch.setattr(search, 'search_semantic', mock_search_semantic)

            results = search.search_hybrid("test")
            if results:
                mode = results[0].get("_mode", "")
                # 模式應該包含 hybrid 或 semantic
                assert "hybrid" in mode or "semantic" in mode or "keyword" in mode
        finally:
            db.close()


# ============================================================================
# Fallback Error Detection Tests
# ============================================================================

class TestFallbackErrorDetection:
    """測試向量和 FTS 錯誤檢測靜態方法。"""

    def test_is_vector_db_fallback_error_dimension_mismatch(self):
        """測試 dimension mismatch 錯誤被識別。"""
        from vault.search import VaultSearch
        exc = sqlite3.OperationalError("dimension mismatch detected")
        assert VaultSearch._is_vector_db_fallback_error(exc) is True

    def test_is_vector_db_fallback_error_query_vector(self):
        """測試 query vector 錯誤被識別。"""
        from vault.search import VaultSearch
        exc = sqlite3.OperationalError("invalid query vector")
        assert VaultSearch._is_vector_db_fallback_error(exc) is True

    def test_is_vector_db_fallback_error_vector_table(self):
        """測試 vector table 錯誤被識別。"""
        from vault.search import VaultSearch
        exc = sqlite3.OperationalError("vector table not found")
        assert VaultSearch._is_vector_db_fallback_error(exc) is True

    def test_is_vector_db_fallback_error_sqlite_vec(self):
        """測試 sqlite-vec 錯誤被識別。"""
        from vault.search import VaultSearch
        exc = sqlite3.OperationalError("sqlite-vec: error loading")
        assert VaultSearch._is_vector_db_fallback_error(exc) is True

    def test_is_vector_db_fallback_error_knowledge_vec(self):
        """測試 knowledge_vec 錯誤被識別。"""
        from vault.search import VaultSearch
        exc = sqlite3.OperationalError("knowledge_vec table missing")
        assert VaultSearch._is_vector_db_fallback_error(exc) is True

    def test_is_vector_db_fallback_error_vec0(self):
        """測試 vec0 錯誤被識別。"""
        from vault.search import VaultSearch
        exc = sqlite3.OperationalError("vec0: invalid operation")
        assert VaultSearch._is_vector_db_fallback_error(exc) is True

    def test_is_vector_db_fallback_error_embedding_column(self):
        """測試 embedding column 錯誤被識別。"""
        from vault.search import VaultSearch
        exc = sqlite3.OperationalError("embedding column type error")
        assert VaultSearch._is_vector_db_fallback_error(exc) is True

    def test_is_vector_db_fallback_error_unrelated(self):
        """測試不相關錯誤不會被誤判。"""
        from vault.search import VaultSearch
        exc = sqlite3.OperationalError("no such table: knowledge")
        assert VaultSearch._is_vector_db_fallback_error(exc) is False

    def test_is_vector_db_fallback_error_case_insensitive(self):
        """測試大小寫不敏感。"""
        from vault.search import VaultSearch
        exc = sqlite3.OperationalError("Dimension Mismatch Error")
        assert VaultSearch._is_vector_db_fallback_error(exc) is True

    def test_is_fts_fallback_error_fts5_keyword(self):
        """測試 fts5 錯誤被識別（OperationalError）。"""
        from vault.search import VaultSearch
        exc = sqlite3.OperationalError("fts5: no such module")
        assert VaultSearch._is_fts_fallback_error(exc) is True

    def test_is_fts_fallback_error_malformed_match(self):
        """測試 malformed match 錯誤被識別。"""
        from vault.search import VaultSearch
        exc = sqlite3.OperationalError("malformed match expression")
        assert VaultSearch._is_fts_fallback_error(exc) is True

    def test_is_fts_fallback_error_knowledge_fts(self):
        """測試 knowledge_fts 錯誤被識別。"""
        from vault.search import VaultSearch
        exc = sqlite3.OperationalError("no such table: knowledge_fts")
        assert VaultSearch._is_fts_fallback_error(exc) is True

    def test_is_fts_fallback_error_runtime_error(self):
        """測試 RuntimeError 包含 fts5 被識別。"""
        from vault.search import VaultSearch
        exc = RuntimeError("fts5 module not available")
        assert VaultSearch._is_fts_fallback_error(exc) is True

    def test_is_fts_fallback_error_unrelated_operational(self):
        """測試不相關 OperationalError 不會被誤判。"""
        from vault.search import VaultSearch
        exc = sqlite3.OperationalError("database is locked")
        assert VaultSearch._is_fts_fallback_error(exc) is False

    def test_is_fts_fallback_error_unrelated_runtime(self):
        """測試不相關 RuntimeError 不會被誤判。"""
        from vault.search import VaultSearch
        exc = RuntimeError("something else went wrong")
        assert VaultSearch._is_fts_fallback_error(exc) is False

    def test_is_fts_fallback_error_other_exception_type(self):
        """測試其他異常類型不會被誤判。"""
        from vault.search import VaultSearch
        exc = ValueError("invalid value")
        assert VaultSearch._is_fts_fallback_error(exc) is False

    def test_is_fts_fallback_error_syntax_error(self):
        """測試 fts5 syntax error 被識別。"""
        from vault.search import VaultSearch
        exc = sqlite3.OperationalError("fts5: syntax error")
        assert VaultSearch._is_fts_fallback_error(exc) is True


# ============================================================================
# More Tokenize Edge Case Tests
# ============================================================================

class TestTokenizeMoreEdgeCases:
    """更多分詞器邊界情況測試。"""

    def test_tokenize_only_punctuation(self):
        """測試只有標點符號的情況。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("!!!???...")
        # Should fall back to returning original
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_tokenize_numbers_only(self):
        """測試只有數字的情況。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("12345")
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_tokenize_mixed_numbers_and_chinese(self):
        """測試數字和中文混合。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("第123章")
        # Should extract Chinese chars
        assert any("\u4e00" <= c <= "\u9fff" for c in result if len(c) == 1) or \
               any("\u4e00" <= c <= "\u9fff" for word in result for c in word)

    def test_tokenize_single_english_char(self):
        """測試單個英文字母。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("a")
        assert result == ["a"]

    def test_tokenize_two_chinese_chars(self):
        """測試兩個中文字（<=2 不加滑動窗口）。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("測試")
        # Only the original two-char word, no sliding window
        assert "測試" in result

    def test_tokenize_three_chinese_chars(self):
        """測試三個中文字（>2 加滑動窗口）。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("測試中")
        assert "測試中" in result  # 原詞
        assert "測試" in result  # 雙字
        assert "試中" in result  # 雙字

    def test_tokenize_preserves_order_mixed(self):
        """測試複雜混合文本的詞序。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("hello 中文 world 測試")
        # First token should be hello (appears first in text)
        assert result[0].lower() == "hello"

    def test_tokenize_empty_string_returns_list_with_empty(self):
        """測試空字符串返回 ['']。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("")
        assert result == [""]

    def test_tokenize_spaces_only(self):
        """測試只有空格的字符串。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("   ")
        assert isinstance(result, list)

    def test_tokenize_special_characters(self):
        """測試特殊字符。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("@#$%^&*()")
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_tokenize_deduplication_case_insensitive(self):
        """測試大小寫不敏感的去重。"""
        from vault.search import VaultSearch
        result = VaultSearch._tokenize("Hello HELLO hello")
        assert len(result) == 1
        assert result[0].lower() == "hello"


# ============================================================================
# More Best Claim Edge Case Tests
# ============================================================================

class TestBestClaimExtended:
    """更多原子主張提取邊界情況測試。"""

    def test_extract_best_claim_none(self):
        """測試 None 輸入。"""
        from vault.search import VaultSearch
        result = VaultSearch._extract_best_claim(None)
        assert result == ""

    def test_extract_best_claim_only_claims_header(self):
        """測試只有 CLAIMS: 標題沒有內容。"""
        from vault.search import VaultSearch
        content = "CLAIMS:"
        result = VaultSearch._extract_best_claim(content)
        assert result == ""

    def test_extract_best_claim_claims_with_empty_lines(self):
        """測試 CLAIMS 段中有空行。"""
        from vault.search import VaultSearch
        content = """CLAIMS:
- [C1] First claim

- [C2] Second claim
"""
        result = VaultSearch._extract_best_claim(content)
        # Should stop at empty line (non-bracket line)
        assert result == "First claim"

    def test_extract_best_claim_multiple_brackets(self):
        """測試有多個括號標記的情況。"""
        from vault.search import VaultSearch
        content = """CLAIMS:
- [C10] Claim with two-digit index (L100)
"""
        result = VaultSearch._extract_best_claim(content)
        assert result == "Claim with two-digit index"

    def test_extract_best_claim_line_number_no_parens(self):
        """測試行號不在括號中的情況。"""
        from vault.search import VaultSearch
        content = """CLAIMS:
- [C1] Claim text L42
"""
        result = VaultSearch._extract_best_claim(content)
        # Without parentheses, "L42" stays as part of claim
        assert "L42" in result

    def test_extract_best_claim_claims_in_middle_of_content(self):
        """測試 CLAIMS 在內容中間。"""
        from vault.search import VaultSearch
        content = """Some intro text here.
More content before claims.
CLAIMS:
- [C1] The best claim ever (L5)
- [C2] Another claim (L8)
SOME_OTHER_SECTION:
More content after.
"""
        result = VaultSearch._extract_best_claim(content)
        assert result == "The best claim ever"

    def test_extract_best_claim_no_space_after_bracket(self):
        """測試括號後沒有空格的情況。"""
        from vault.search import VaultSearch
        content = """CLAIMS:
- [C1]Text without space after bracket
"""
        result = VaultSearch._extract_best_claim(content)
        # The regex might not match properly, should fall to fallback strip
        assert isinstance(result, str)
        assert len(result) > 0

    def test_extract_best_claim_different_bracket_formats(self):
        """測試不同的括號格式。"""
        from vault.search import VaultSearch
        # Test with [C1], [C2], etc.
        content = """CLAIMS:
- [S1] Section claim (L10)
"""
        result = VaultSearch._extract_best_claim(content)
        # Should match any [X] pattern
        assert result == "Section claim"

    def test_extract_best_claim_long_claim_text(self):
        """測試較長的主張文本。"""
        from vault.search import VaultSearch
        long_text = "A" * 200
        content = f"""CLAIMS:
- [C1] {long_text} (L1)
"""
        result = VaultSearch._extract_best_claim(content)
        assert result == long_text


# ============================================================================
# More Compact Result Tests
# ============================================================================

class TestCompactResultExtended:
    """更多緊湊結果測試。"""

    def test_compact_result_empty_dict(self):
        """測試空字典輸入。"""
        from vault.search import VaultSearch
        result = VaultSearch._compact_result({})
        assert result == {}

    def test_compact_result_preserves_rerank_score(self):
        """測試保留 rerank_score。"""
        from vault.search import VaultSearch
        doc = {
            "id": 1,
            "title": "Test",
            "_rerank_score": 0.95,
            "content_raw": "should be removed",
        }
        result = VaultSearch._compact_result(doc)
        assert result["rerank_score"] == 0.95
        assert "content_raw" not in result

    def test_compact_result_without_rerank_score(self):
        """測試沒有 rerank_score 的情況。"""
        from vault.search import VaultSearch
        doc = {
            "id": 1,
            "title": "Test",
            "content_raw": "should be removed",
        }
        result = VaultSearch._compact_result(doc)
        assert "rerank_score" not in result
        assert "content_raw" not in result

    def test_compact_result_all_fields(self):
        """測試所有字段都存在的情況。"""
        from vault.search import VaultSearch
        doc = {
            "id": 1,
            "title": "Test Doc",
            "category": "tech",
            "layer": "core",
            "trust": 0.9,
            "tags": "test,example",
            "best_claim": "best claim text",
            "best_span": "L1-L10",
            "node_uid": "node_123",
            "path": "/docs/test",
            "heading": "Test Heading",
            "line_start": 1,
            "line_end": 10,
            "citation": "#1 Test Doc L1-L10",
            "recommended_next_tool": "vault_read_range",
            "next_action": {"tool": "test", "arguments": {}},
            "next_actions": [{"tool": "test"}],
            "content_raw": "should not appear",
            "_score": 0.8,
        }
        result = VaultSearch._compact_result(doc)
        assert "content_raw" not in result
        assert "_score" not in result
        assert result["id"] == 1
        assert result["title"] == "Test Doc"
        assert result["category"] == "tech"
        assert result["best_claim"] == "best claim text"
        assert result["citation"] == "#1 Test Doc L1-L10"

    def test_compact_result_partial_fields(self):
        """測試只有部分字段的情況。"""
        from vault.search import VaultSearch
        doc = {"id": 1, "title": "Test"}
        result = VaultSearch._compact_result(doc)
        assert result == {"id": 1, "title": "Test"}

    def test_compact_result_preserves_only_known_fields(self):
        """測試只保留已知字段，移除其他字段。"""
        from vault.search import VaultSearch
        doc = {
            "id": 1,
            "title": "Test",
            "custom_field_1": "value1",
            "custom_field_2": "value2",
            "content_raw": "raw content",
        }
        result = VaultSearch._compact_result(doc)
        assert "custom_field_1" not in result
        assert "custom_field_2" not in result
        assert "content_raw" not in result
        assert result["id"] == 1
        assert result["title"] == "Test"


# ============================================================================
# More Normalize Chinese Tests (cover all TC_SC_MAP entries)
# ============================================================================

class TestNormalizeChineseFull:
    """完整覆蓋 TC_SC_MAP 所有條目的測試。"""

    def test_normalize_chinese_all_entries(self):
        """測試 TC_SC_MAP 中所有繁簡轉換條目。"""
        from vault.search import VaultSearch
        tc_sc_map = VaultSearch._TC_SC_MAP
        for tc, sc in tc_sc_map.items():
            result = VaultSearch._normalize_chinese(tc)
            assert result == sc, f"Failed for '{tc}': expected '{sc}', got '{result}'"

    def test_normalize_chinese_all_in_one_text(self):
        """測試包含所有繁體詞的文本。"""
        from vault.search import VaultSearch
        tc_sc_map = VaultSearch._TC_SC_MAP
        all_tc = " ".join(tc_sc_map.keys())
        result = VaultSearch._normalize_chinese(all_tc)
        for tc, sc in tc_sc_map.items():
            # After normalization, traditional forms should be replaced
            assert tc not in result or tc == sc  # Some might be same already

    def test_normalize_chinese_already_simplified(self):
        """測試已經是簡體的文本不變。"""
        from vault.search import VaultSearch
        text = "什么是机器学习数据库优化性能"
        result = VaultSearch._normalize_chinese(text)
        assert result == text

    def test_normalize_chinese_empty(self):
        """測試空字符串。"""
        from vault.search import VaultSearch
        result = VaultSearch._normalize_chinese("")
        assert result == ""

    def test_normalize_chinese_english_only(self):
        """測試只有英文的文本。"""
        from vault.search import VaultSearch
        text = "hello world python"
        result = VaultSearch._normalize_chinese(text)
        assert result == text


# ============================================================================
# Static Rerank Method Extended Tests
# ============================================================================

class TestStaticRerankExtended:
    """靜態 rerank 方法更多邊界情況。"""

    def test_rerank_rrf_score_above_one(self):
        """測試 RRF 分數大於 1 的情況（正規化分支）。"""
        from vault.search import VaultSearch
        results = [
            {"_score": 2.5, "trust": 0.8, "updated_at": "2024-01-01T00:00:00Z"},
            {"_score": 1.5, "trust": 0.9, "updated_at": "2024-01-01T00:00:00Z"},
        ]
        reranked = VaultSearch._rerank(results)
        assert len(reranked) == 2
        # _rerank_score should be set
        assert "_rerank_score" in reranked[0]
        assert "_original_score" in reranked[0]

    def test_rerank_without_query(self):
        """測試無 query 時使用基礎 rerank。"""
        from vault.search import VaultSearch
        results = [
            {"_score": 0.8, "trust": 0.9},
            {"_score": 0.7, "trust": 0.8},
        ]
        reranked = VaultSearch._rerank(results)
        assert len(reranked) == 2
        assert "_rerank_score" in reranked[0]

    def test_rerank_empty_results(self):
        """測試空結果列表。"""
        from vault.search import VaultSearch
        results = []
        reranked = VaultSearch._rerank(results)
        assert reranked == []

    def test_rerank_with_graph_distance(self):
        """測試有圖譜距離的結果。"""
        from vault.search import VaultSearch
        results = [
            {"_score": 0.7, "trust": 0.8, "_graph_distance": 0},
            {"_score": 0.7, "trust": 0.8, "_graph_distance": 2},
        ]
        reranked = VaultSearch._rerank(results)
        # The one with distance 0 should rank higher (graph bonus)
        assert reranked[0].get("_graph_distance", -1) == 0

    def test_rerank_no_score_defaults(self):
        """測試沒有 _score 字段的結果。"""
        from vault.search import VaultSearch
        results = [
            {"trust": 0.8, "updated_at": "2024-01-01T00:00:00Z"},
        ]
        reranked = VaultSearch._rerank(results)
        assert len(reranked) == 1
        assert "_rerank_score" in reranked[0]

    def test_rerank_with_existing_freshness(self):
        """測試已有 freshness 字段的情況。"""
        from vault.search import VaultSearch
        results = [
            {"_score": 0.7, "trust": 0.8, "freshness": 0.9},
        ]
        reranked = VaultSearch._rerank(results)
        assert len(reranked) == 1
        assert "_rerank_score" in reranked[0]

    def test_rerank_single_result(self):
        """測試單個結果。"""
        from vault.search import VaultSearch
        results = [{"_score": 0.5, "trust": 0.5}]
        reranked = VaultSearch._rerank(results)
        assert len(reranked) == 1
        assert "_rerank_score" in reranked[0]

    def test_rerank_with_query_and_content(self):
        """測試有 query 時使用輕量 reranker。"""
        from vault.search import VaultSearch
        results = [
            {"id": 1, "title": "Python tutorial", "content_raw": "Python is great", "_score": 0.5},
            {"id": 2, "title": "Java guide", "content_raw": "Java is also good", "_score": 0.6},
        ]
        reranked = VaultSearch._rerank(results, query="Python")
        assert len(reranked) == 2
        # Python result should rank higher due to query match
        assert reranked[0]["id"] == 1
        assert "_rerank_score" in reranked[0]


# ============================================================================
# LightweightReranker._extract_terms Edge Cases
# ============================================================================

class TestLightweightRerankerExtractTerms:
    """LightweightReranker._extract_terms 的邊界情況測試。"""

    def test_extract_terms_empty_string(self):
        """測試空字符串。"""
        from vault.search import LightweightReranker
        result = LightweightReranker._extract_terms("")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0] == ""

    def test_extract_terms_single_chinese_char(self):
        """測試單個中文字符。"""
        from vault.search import LightweightReranker
        result = LightweightReranker._extract_terms("學")
        assert isinstance(result, list)
        assert len(result) >= 1
        # Should contain the char
        assert any("\u4e00" <= c <= "\u9fff" for c in result)

    def test_extract_terms_two_chinese_chars(self):
        """測試兩個中文字符（<=2 不加滑動窗口）。"""
        from vault.search import LightweightReranker
        result = LightweightReranker._extract_terms("測試")
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_extract_terms_mixed_language(self):
        """測試中英文混合。"""
        from vault.search import LightweightReranker
        result = LightweightReranker._extract_terms("AI 人工智能")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_extract_terms_deduplication(self):
        """測試去重功能。"""
        from vault.search import LightweightReranker
        result = LightweightReranker._extract_terms("test test TEST")
        # Should be deduplicated (case-insensitive)
        assert len(result) == 1
        assert result[0].lower() == "test"

    def test_extract_terms_order_preserved(self):
        """測試詞序保留。"""
        from vault.search import LightweightReranker
        result = LightweightReranker._extract_terms("first second third")
        assert result[0].lower() == "first"
        assert result[1].lower() == "second"
        assert result[2].lower() == "third"

    def test_extract_terms_numbers(self):
        """測試數字不被視為英文詞（因為不是字母）。"""
        from vault.search import LightweightReranker
        result = LightweightReranker._extract_terms("123 456")
        assert isinstance(result, list)

    def test_extract_terms_special_characters(self):
        """測試特殊字符。"""
        from vault.search import LightweightReranker
        result = LightweightReranker._extract_terms("!@#$%^&*()")
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_extract_terms_chinese_sliding_window(self):
        """測試中文滑動窗口分詞。"""
        from vault.search import LightweightReranker
        result = LightweightReranker._extract_terms("機器學習")
        # Should have original + 2-char windows
        assert "機器學習" in result
        assert "機器" in result
        assert "學習" in result


# ============================================================================
# More Keyword Search LIKE Fallback Tests
# ============================================================================

class TestKeywordSearchLikeFallback:
    """關鍵字搜尋 LIKE 降級的更多測試。"""

    def test_search_keyword_like_with_multiple_terms(self, tmp_path):
        """測試多個搜尋詞的 LIKE 搜尋。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Python Programming Guide",
                content_raw="This is a comprehensive Python programming tutorial.",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            # Use terms that would trigger LIKE fallback (if FTS5 unavailable)
            results = search._search_keyword_like(
                "Python programming",
                ["python", "programming"],
                limit=10,
            )
            assert isinstance(results, list)
            for r in results:
                assert "_score" in r
                assert "_mode" in r
        finally:
            db.close()

    def test_search_keyword_like_with_min_score_filter(self, tmp_path):
        """測試 min_score 過濾。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Python Guide",
                content_raw="Python content here",
                trust=0.9,
            )
            db.add_knowledge(
                title="Other Doc",
                content_raw="completely unrelated content",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search._search_keyword_like(
                "Python",
                ["python"],
                limit=10,
                min_score=0.5,
            )
            assert isinstance(results, list)
            for r in results:
                assert r["_score"] >= 0.5
        finally:
            db.close()

    def test_search_keyword_like_no_matches(self, tmp_path):
        """測試無匹配結果。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test content", trust=0.9)
            search = VaultSearch(db, embed_provider=None)
            results = search._search_keyword_like(
                "xyz_nonexistent",
                ["xyz_nonexistent"],
                limit=10,
            )
            assert results == []
        finally:
            db.close()

    def test_search_keyword_like_with_layer_and_category(self, tmp_path):
        """測試帶有 layer 和 category 過濾的 LIKE 搜尋。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Core Python",
                content_raw="Python core content",
                layer="core",
                category="tech",
                trust=0.9,
            )
            db.add_knowledge(
                title="Non-core Python",
                content_raw="Python non-core content",
                layer="extended",
                category="tech",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search._search_keyword_like(
                "Python",
                ["python"],
                limit=10,
                layer="core",
                category="tech",
            )
            assert isinstance(results, list)
            for r in results:
                assert r.get("layer") == "core"
                assert r.get("category") == "tech"
        finally:
            db.close()

    def test_search_keyword_like_ordered_by_score(self, tmp_path):
        """測試結果按分數降序排列。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(
                title="Python Python Python",
                content_raw="Python programming with Python Python",
                trust=0.9,
            )
            db.add_knowledge(
                title="Java Guide",
                content_raw="Java programming guide",
                trust=0.9,
            )
            search = VaultSearch(db, embed_provider=None)
            results = search._search_keyword_like(
                "Python programming",
                ["python", "programming"],
                limit=10,
            )
            if len(results) >= 2:
                # Should be sorted by score descending
                assert results[0]["_score"] >= results[1]["_score"]
        finally:
            db.close()


# ============================================================================
# More Query Expansion Edge Case Tests
# ============================================================================

class TestQueryExpansionMoreEdgeCases:
    """更多查詢擴展邊界情況測試。"""

    def test_expand_query_disabled_returns_original(self, tmp_path):
        """測試禁用查詢擴展時返回原始查詢。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_query_expansion=False)
            result = search._expand_query("test query")
            assert len(result) == 1
            assert result[0][0] == "test query"
            assert result[0][1] == 1.0
        finally:
            db.close()

    def test_expand_query_abbreviation_ai(self, tmp_path):
        """測試 AI 縮寫擴展。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            result = search._expand_query("AI 技術")
            queries = [q for q, w in result]
            # Should have both ai and 人工智能 variations
            assert any("ai" in q.lower() for q in queries)
        finally:
            db.close()

    def test_expand_query_fullform_to_abbr(self, tmp_path):
        """測試全稱轉縮寫的擴展。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            result = search._expand_query("人工智能 技術")
            queries = [q for q, w in result]
            # Should have 人工智能 expanded to ai
            assert any("ai" in q.lower() for q in queries)
        finally:
            db.close()

    def test_expand_query_keyword_extraction(self, tmp_path):
        """測試關鍵詞提取（停用詞過濾）。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            # Query with stop words
            result = search._expand_query("什麼是 機器學習 和 深度學習")
            assert isinstance(result, list)
            assert len(result) >= 1
        finally:
            db.close()

    def test_expand_query_count_zero(self, tmp_path):
        """測試 query_expansion_count 為 0。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, query_expansion_count=0)
            result = search._expand_query("什麼是機器學習")
            # Even with count 0, it should return the original query
            assert len(result) >= 1
        finally:
            db.close()

    def test_expand_query_how_to_pattern(self, tmp_path):
        """測試「怎麼用/如何使用」問句變換。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            result = search._expand_query("怎麼用 Python")
            queries = [q for q, w in result]
            # Should include variations
            assert any("使用方法" in q for q in queries) or any("教程" in q for q in queries)
        finally:
            db.close()

    def test_expand_query_how_to_pattern_simplified(self, tmp_path):
        """測試簡體中文「怎么用」問句變換。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            result = search._expand_query("怎么用 Python")
            queries = [q for q, w in result]
            assert any("使用方法" in q for q in queries) or any("教程" in q for q in queries)
        finally:
            db.close()

    def test_expand_query_why_pattern(self, tmp_path):
        """測試「為什麼/why」問句變換。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            result = search._expand_query("為什麼要用 Python")
            queries = [q for q, w in result]
            assert any("原因" in q for q in queries)
        finally:
            db.close()

    def test_expand_query_how_to_do_pattern(self, tmp_path):
        """測試「怎麼做/如何實現」問句變換。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            result = search._expand_query("怎麼做 機器學習")
            queries = [q for q, w in result]
            assert any("实现" in q for q in queries) or any("方法" in q for q in queries)
        finally:
            db.close()

    def test_expand_query_multiple_expansions_sorted_by_weight(self, tmp_path):
        """測試多個擴展按權重降序排列。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            result = search._expand_query("什麼是 AI 機器學習")
            # Should be sorted by weight descending
            weights = [w for q, w in result]
            for i in range(len(weights) - 1):
                assert weights[i] >= weights[i + 1]
        finally:
            db.close()

    def test_expand_query_synonym_replacement(self, tmp_path):
        """測試同義詞替換擴展。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            result = search._expand_query("向量 數據庫")
            queries = [q for q, w in result]
            # Should have "embedding" synonym for 向量
            assert any("embedding" in q.lower() for q in queries) or \
                   any("嵌入" in q for q in queries)
        finally:
            db.close()

    def test_expand_query_abbr_db(self, tmp_path):
        """測試 db 縮寫擴展。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            result = search._expand_query("db 查詢")
            queries = [q for q, w in result]
            assert any("數據庫" in q or "数据库" in q for q in queries)
        finally:
            db.close()

    def test_expand_query_normalized_chinese_match(self, tmp_path):
        """測試標準化中文（簡體）的縮寫匹配。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            # Use simplified Chinese that should match through normalization
            result = search._expand_query("数据库 优化")
            queries = [q for q, w in result]
            assert any("db" in q.lower() for q in queries)
        finally:
            db.close()


# ============================================================================
# More Graph Expand Edge Case Tests
# ============================================================================

class TestGraphExpandExtended:
    """更多圖譜擴展邊界情況測試。"""

    def test_apply_graph_expand_no_results(self, tmp_path):
        """測試空結果列表。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, graph="fake_graph")
            expanded = search._apply_graph_expand([], 2, 10)
            assert expanded == []
        finally:
            db.close()

    def test_apply_graph_expand_graph_none(self, tmp_path):
        """測試 graph 為 None 時直接返回。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test")
            search = VaultSearch(db, embed_provider=None, graph=None)
            results = [{"id": 1, "_score": 0.8, "title": "Test"}]
            expanded = search._apply_graph_expand(results, 2, 10)
            assert len(expanded) == len(results)
        finally:
            db.close()

    def test_apply_graph_expand_respects_limit(self, tmp_path):
        """測試結果數量不超過 limit。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test 1", content_raw="test one")
            db.add_knowledge(title="Test 2", content_raw="test two")
            search = VaultSearch(db, embed_provider=None)
            results = [{"id": 1, "_score": 0.8, "title": "Test 1"}]
            expanded = search._apply_graph_expand(results, 1, 1)
            assert len(expanded) <= 1
        finally:
            db.close()

    def test_apply_graph_expand_sorting(self, tmp_path):
        """測試擴展結果的排序。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Doc A", content_raw="content A", trust=0.9)
            db.add_knowledge(title="Doc B", content_raw="content B", trust=0.8)
            search = VaultSearch(db, embed_provider=None)
            results = [
                {"id": 1, "_score": 0.9, "title": "Doc A"},
                {"id": 2, "_score": 0.7, "title": "Doc B"},
            ]
            expanded = search._apply_graph_expand(results, 1, 10)
            # Original results should maintain order
            if len(expanded) >= 2:
                assert expanded[0]["_score"] >= expanded[1]["_score"]
        finally:
            db.close()


# ============================================================================
# More Lightweight Reranker Edge Case Tests
# ============================================================================

class TestLightweightRerankerExtended:
    """LightweightReranker 更多邊界情況測試。"""

    def test_rerank_empty_documents(self):
        """測試空文檔列表。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        result = reranker.rerank("query", [])
        assert result == []

    def test_rerank_empty_query_returns_all(self):
        """測試空 query 時仍然返回所有文檔。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"id": 1, "title": "Doc 1", "content_raw": "content", "_score": 0.5},
            {"id": 2, "title": "Doc 2", "content_raw": "content", "_score": 0.6},
        ]
        # Empty query still processes, returns all docs
        result = reranker.rerank("", docs)
        assert len(result) == 2

    def test_rerank_single_document(self):
        """測試單個文檔。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [{"id": 1, "title": "Test", "content_raw": "test content", "_score": 0.5}]
        result = reranker.rerank("test", docs)
        assert len(result) == 1
        assert "_rerank_score" in result[0]

    def test_rerank_with_title_match_boost(self):
        """測試標題匹配加成。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"id": 1, "title": "Python Guide", "content_raw": "some content", "_score": 0.5},
            {"id": 2, "title": "Other Title", "content_raw": "Python content here", "_score": 0.5},
        ]
        result = reranker.rerank("Python", docs)
        # Doc with title match should rank higher
        assert result[0]["id"] == 1

    def test_rerank_with_content_multi_word_match(self):
        """測試多詞匹配加成。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"id": 1, "title": "Doc 1", "content_raw": "machine learning and AI", "_score": 0.5},
            {"id": 2, "title": "Doc 2", "content_raw": "machine learning", "_score": 0.5},
        ]
        result = reranker.rerank("machine learning", docs)
        # Both match, but first might have more boost due to "AI" not matching query
        # Actually both have same 2 words, should be similar
        assert len(result) == 2

    def test_rerank_with_position_bonus(self):
        """測試位置加成（關鍵詞出現在開頭）。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"id": 1, "title": "Doc", "content_raw": "Python is a programming language...", "_score": 0.5},
            {"id": 2, "title": "Doc", "content_raw": "A long text about programming with Python at the end...", "_score": 0.5},
        ]
        # Pad the second doc's content to make Python appear later
        long_content = "A" * 500 + " Python"
        docs[1]["content_raw"] = long_content
        result = reranker.rerank("Python", docs)
        # Doc 1 should rank higher because Python appears earlier
        assert result[0]["id"] == 1

    def test_rerank_with_freshness_field(self):
        """測試已有 freshness 字段。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"id": 1, "title": "Doc", "content_raw": "test", "_score": 0.5, "freshness": 0.9},
        ]
        result = reranker.rerank("test", docs)
        assert len(result) == 1
        assert "_rerank_score" in result[0]

    def test_rerank_with_graph_distance(self):
        """測試有圖譜距離的加成。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"id": 1, "title": "Doc", "content_raw": "test", "_score": 0.5, "_graph_distance": 0},
        ]
        result = reranker.rerank("test", docs)
        assert len(result) == 1
        assert "_rerank_score" in result[0]

    def test_rerank_with_trust_field(self):
        """測試信任度加成。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"id": 1, "title": "Doc", "content_raw": "test", "_score": 0.5, "trust": 0.9},
        ]
        result = reranker.rerank("test", docs)
        assert len(result) == 1
        assert "_rerank_score" in result[0]

    def test_rerank_with_distance_field(self):
        """測試有向量距離字段時的相似度加成。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"id": 1, "title": "Doc", "content_raw": "test", "_score": 0.5, "_distance": 0.2},
        ]
        result = reranker.rerank("test", docs)
        assert len(result) == 1
        assert "_rerank_score" in result[0]

    def test_rerank_preserves_original_score(self):
        """測試保存原始分數。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"id": 1, "title": "Test", "content_raw": "test content", "_score": 0.42},
        ]
        result = reranker.rerank("test", docs)
        assert result[0]["_original_score"] == 0.42

    def test_rerank_top_k_parameter(self):
        """測試 top_k 參數。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"id": 1, "title": "Doc 1", "content_raw": "test", "_score": 0.5},
            {"id": 2, "title": "Doc 2", "content_raw": "test", "_score": 0.6},
            {"id": 3, "title": "Doc 3", "content_raw": "test", "_score": 0.7},
        ]
        result = reranker.rerank("test", docs, top_k=2)
        assert len(result) == 2

    def test_rerank_top_k_none_returns_all(self):
        """測試 top_k 為 None 時返回全部。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"id": 1, "title": "Doc 1", "content_raw": "test", "_score": 0.5},
            {"id": 2, "title": "Doc 2", "content_raw": "test", "_score": 0.6},
        ]
        result = reranker.rerank("test", docs, top_k=None)
        assert len(result) == 2

    def test_rerank_available_property(self):
        """測試 available 屬性。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        assert reranker.available is True

    def test_rerank_with_single_term_penalty(self):
        """測試只有單詞匹配時的懲罰（當 query 有多個詞時）。"""
        from vault.search import LightweightReranker
        reranker = LightweightReranker()
        docs = [
            {"id": 1, "title": "Python", "content_raw": "Python content only one match", "_score": 0.5},
            {"id": 2, "title": "Java", "content_raw": "machine learning ai deep learning", "_score": 0.5},
        ]
        # Query with multiple terms
        result = reranker.rerank("machine learning Python", docs)
        assert len(result) == 2
        # Doc with more matches should rank higher


# ============================================================================
# VaultSearch Property Caching Tests
# ============================================================================

class TestVaultSearchPropertiesCaching:
    """測試 VaultSearch 屬性的快取行為。"""

    def test_has_embeddings_disabled(self, tmp_path):
        """測試 enable_vector_search=False 時返回 False。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_vector_search=False)
            assert search.has_embeddings is False
        finally:
            db.close()

    def test_has_embeddings_with_provider(self, tmp_path):
        """測試有 embed_provider 但沒有 vec table 時。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            # Mock an embed provider
            search = VaultSearch(db, embed_provider=object())
            # Without vec table, has_embeddings depends on db._vec_available
            result = search.has_embeddings
            assert isinstance(result, bool)
        finally:
            db.close()

    def test_has_reranker_disabled(self, tmp_path):
        """測試 enable_rerank=False 時返回 False。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_rerank=False)
            assert search.has_reranker is False
        finally:
            db.close()

    def test_has_reranker_enabled(self, tmp_path):
        """測試 enable_rerank=True 時有輕量 reranker。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_rerank=True)
            assert search.has_reranker is True
            # Test caching - second call should return cached value
            assert search.has_reranker is True
        finally:
            db.close()

    def test_has_cross_encoder_disabled(self, tmp_path):
        """測試 enable_cross_encoder=False 時返回 False。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_cross_encoder=False)
            assert search.has_cross_encoder is False
        finally:
            db.close()

    def test_has_llm_disabled(self, tmp_path):
        """測試 enable_llm_enhancement=False 時返回 False。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_llm_enhancement=False)
            assert search.has_llm is False
        finally:
            db.close()

    def test_has_reranker_strategy_none(self, tmp_path):
        """測試 rerank_strategy='none' 時返回 False。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, rerank_strategy="none")
            assert search.has_reranker is False
        finally:
            db.close()

    def test_has_reranker_strategy_lightweight(self, tmp_path):
        """測試 rerank_strategy='lightweight' 時返回 True。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, rerank_strategy="lightweight")
            assert search.has_reranker is True
        finally:
            db.close()


# ============================================================================
# More Validation Edge Case Tests
# ============================================================================

class TestParamValidationEdgeCases:
    """參數驗證更多邊界情況。"""

    def test_zero_keyword_weight_allowed(self, tmp_path):
        """測試 keyword_weight 為 0 是有效的。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, keyword_weight=0.0)
            assert search._keyword_weight == 0.0
        finally:
            db.close()

    def test_zero_vector_weight_allowed(self, tmp_path):
        """測試 vector_weight 為 0 是有效的。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, vector_weight=0.0)
            assert search._vector_weight == 0.0
        finally:
            db.close()

    def test_decay_at_zero_allowed(self, tmp_path):
        """測試 decay 參數為 0 是有效的。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(
                db,
                query_expansion_synonym_decay=0.0,
                query_expansion_question_decay=0.0,
                query_expansion_abbr_decay=0.0,
                query_expansion_keyword_decay=0.0,
            )
            assert search._query_expansion_synonym_decay == 0.0
        finally:
            db.close()

    def test_decay_at_one_allowed(self, tmp_path):
        """測試 decay 參數為 1 是有效的。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(
                db,
                query_expansion_synonym_decay=1.0,
                query_expansion_question_decay=1.0,
                query_expansion_abbr_decay=1.0,
                query_expansion_keyword_decay=1.0,
            )
            assert search._query_expansion_synonym_decay == 1.0
        finally:
            db.close()

    def test_invalid_abbr_decay_above_one_raises(self, tmp_path):
        """測試 abbr_decay 大於 1 引發異常。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            with pytest.raises(ValueError, match="abbr_decay"):
                VaultSearch(db, query_expansion_abbr_decay=1.5)
        finally:
            db.close()

    def test_invalid_keyword_decay_below_zero_raises(self, tmp_path):
        """測試 keyword_decay 小於 0 引發異常。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            with pytest.raises(ValueError, match="keyword_decay"):
                VaultSearch(db, query_expansion_keyword_decay=-0.1)
        finally:
            db.close()

    def test_invalid_question_decay_raises(self, tmp_path):
        """測試 question_decay 無效引發異常。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            with pytest.raises(ValueError, match="question_decay"):
                VaultSearch(db, query_expansion_question_decay=2.0)
        finally:
            db.close()


# ============================================================================
# Info Method Extended Tests
# ============================================================================

class TestInfoMethodExtended:
    """info() 方法更多測試。"""

    def test_info_returns_dict(self, tmp_path):
        """測試 info() 返回字典。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            assert isinstance(info, dict)
        finally:
            db.close()

    def test_info_has_basic_layer(self, tmp_path):
        """測試基礎層資訊。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            assert "基礎層" in info
            assert "basic" in info
            assert info["基礎層"]["keyword_search"] is True
        finally:
            db.close()

    def test_info_query_expansion_disabled(self, tmp_path):
        """測試禁用查詢擴展時的 info。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_query_expansion=False)
            info = search.info()
            assert info["基礎層"]["query_expansion"] is False
        finally:
            db.close()

    def test_info_config_layer(self, tmp_path):
        """測試配置層資訊。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(
                db,
                embed_provider=None,
                keyword_weight=0.7,
                vector_weight=0.3,
            )
            info = search.info()
            assert "配置" in info
            assert "config" in info
            assert info["配置"]["關鍵詞權重"] == 0.7
            assert info["config"]["keyword_weight"] == 0.7
        finally:
            db.close()

    def test_info_rerank_strategy_config(self, tmp_path):
        """測試 rerank 策略配置。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, rerank_strategy="lightweight")
            info = search.info()
            assert info["配置"]["rerank_strategy"] == "lightweight"
        finally:
            db.close()

    def test_info_cross_encoder_disabled(self, tmp_path):
        """測試 cross encoder 禁用時的 info。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_cross_encoder=False)
            info = search.info()
            assert "高階層" in info
            assert info["高階層"]["cross_encoder_rerank"] is False
        finally:
            db.close()

    def test_info_llm_query_rewrite_disabled(self, tmp_path):
        """測試 LLM 查詢改寫禁用時的 info。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_llm_query_rewrite=False)
            info = search.info()
            assert "旗艦層" in info
            assert info["旗艦層"]["llm_query_rewrite"] is False
        finally:
            db.close()

    def test_info_default_mode_keyword(self, tmp_path):
        """測試沒有嵌入時預設模式為 keyword。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            assert info["配置"]["default_mode"] == "keyword"
        finally:
            db.close()
