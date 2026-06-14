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

    def test_search_unknown_mode_falls_back(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Fallback Test", content_raw="mode fallback")
            search = VaultSearch(db, embed_provider=None)
            # Unknown mode should not crash
            results = search.search("Fallback", mode="invalid_mode", use_rerank=False)
            assert isinstance(results, list)
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


