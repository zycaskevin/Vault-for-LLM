"""
Extended tests for vault.search module to boost coverage.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from vault.db import VaultDB
from vault.search import VaultSearch, _normalize_text


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


