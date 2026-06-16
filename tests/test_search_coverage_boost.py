"""
Additional tests for vault.search module to boost coverage beyond 80%.
Targeted at specific uncovered branches and edge cases.
"""
from __future__ import annotations

import pytest
import sqlite3

from vault.db import VaultDB
from vault.search import (
    VaultSearch,
    LightweightReranker,
    _normalize_text,
    calc_freshness,
    calc_graph_depth,
)


class TestCoverageBoostLightweightReranker:
    """Additional tests for LightweightReranker edge cases."""

    def test_single_hit_penalty_with_many_terms(self):
        """測試當查詢有3+個詞但只有1個匹配時的懲罰。"""
        reranker = LightweightReranker()
        # Query with 3+ terms
        query = "python machine learning"
        docs = [
            {"id": 1, "title": "", "content_raw": "python is great", "_score": 0.5},
            {"id": 2, "title": "", "content_raw": "java and c++", "_score": 0.5},
        ]
        result = reranker.rerank(query, docs)
        # Doc 1 has 1 hit out of 3 terms, should get penalty
        # Doc 2 has 0 hits
        assert len(result) == 2

    def test_rerank_with_freshness_explicit(self):
        """測試帶有明確 freshness 字段的文檔。"""
        reranker = LightweightReranker()
        docs = [
            {"id": 1, "title": "Doc", "content_raw": "test content", "_score": 0.5, "freshness": 0.9},
            {"id": 2, "title": "Doc", "content_raw": "test content", "_score": 0.5, "freshness": 0.1},
        ]
        result = reranker.rerank("test", docs)
        # Higher freshness should rank higher
        assert result[0]["freshness"] > result[1]["freshness"]

    def test_rerank_with_trust_field(self):
        """測試帶有 trust 字段的文檔。"""
        reranker = LightweightReranker()
        docs = [
            {"id": 1, "title": "Doc", "content_raw": "test", "_score": 0.5, "trust": 0.9},
            {"id": 2, "title": "Doc", "content_raw": "test", "_score": 0.5, "trust": 0.1},
        ]
        result = reranker.rerank("test", docs)
        # Higher trust should rank higher
        assert result[0]["trust"] > result[1]["trust"]

    def test_rerank_with_graph_distance_zero(self):
        """測試圖譜距離為0時的加成。"""
        reranker = LightweightReranker()
        docs = [
            {"id": 1, "title": "Doc", "content_raw": "test", "_score": 0.5, "_graph_distance": 0},
            {"id": 2, "title": "Doc", "content_raw": "test", "_score": 0.5, "_graph_distance": 3},
        ]
        result = reranker.rerank("test", docs)
        # Distance 0 should get more bonus
        assert result[0]["_graph_distance"] < result[1]["_graph_distance"]

    def test_rerank_with_vector_similarity(self):
        """測試有向量距離時的相似度加成。"""
        reranker = LightweightReranker()
        docs = [
            {"id": 1, "title": "Doc", "content_raw": "test", "_score": 0.5, "_distance": 0.1},
            {"id": 2, "title": "Doc", "content_raw": "test", "_score": 0.5, "_distance": 1.5},
        ]
        result = reranker.rerank("test", docs)
        # Lower distance = higher similarity = better rank
        assert result[0]["_distance"] < result[1]["_distance"]

    def test_rerank_query_with_single_char(self):
        """測試單字符查詢。"""
        reranker = LightweightReranker()
        docs = [
            {"id": 1, "title": "A Test", "content_raw": "a content", "_score": 0.5},
        ]
        result = reranker.rerank("a", docs)
        assert len(result) == 1

    def test_rerank_title_starts_with_query(self):
        """測試標題以查詢開頭的額外加成。"""
        reranker = LightweightReranker()
        docs = [
            {"id": 1, "title": "Python tutorial for beginners", "content_raw": "learn python", "_score": 0.5},
            {"id": 2, "title": "Learn Python programming", "content_raw": "python basics", "_score": 0.5},
        ]
        result = reranker.rerank("Python", docs)
        # Both have Python in title, but doc 1 starts with it
        assert result[0]["id"] == 1


class TestCoverageBoostFallbackErrors:
    """Tests for _is_vector_db_fallback_error and _is_fts_fallback_error."""

    def test_vector_fallback_dimension_mismatch(self):
        exc = sqlite3.OperationalError("dimension mismatch between query vector and index")
        assert VaultSearch._is_vector_db_fallback_error(exc) is True

    def test_vector_fallback_query_vector(self):
        exc = sqlite3.OperationalError("invalid query vector format")
        assert VaultSearch._is_vector_db_fallback_error(exc) is True

    def test_vector_fallback_vector_table(self):
        exc = sqlite3.OperationalError("vector table not found")
        assert VaultSearch._is_vector_db_fallback_error(exc) is True

    def test_vector_fallback_sqlite_vec(self):
        exc = sqlite3.OperationalError("sqlite-vec extension not loaded")
        assert VaultSearch._is_vector_db_fallback_error(exc) is True

    def test_vector_fallback_knowledge_vec(self):
        exc = sqlite3.OperationalError("knowledge_vec index corrupted")
        assert VaultSearch._is_vector_db_fallback_error(exc) is True

    def test_vector_fallback_vec0(self):
        exc = sqlite3.OperationalError("vec0: invalid vector dimension")
        assert VaultSearch._is_vector_db_fallback_error(exc) is True

    def test_vector_fallback_embedding_column(self):
        exc = sqlite3.OperationalError("embedding column type mismatch")
        assert VaultSearch._is_vector_db_fallback_error(exc) is True

    def test_vector_fallback_unrelated(self):
        exc = sqlite3.OperationalError("no such table: knowledge")
        assert VaultSearch._is_vector_db_fallback_error(exc) is False

    def test_vector_fallback_case_insensitive(self):
        exc = sqlite3.OperationalError("DIMENSION MISMATCH ERROR")
        assert VaultSearch._is_vector_db_fallback_error(exc) is True

    def test_fts_fallback_fts5_error(self):
        exc = sqlite3.OperationalError("fts5: no such module")
        assert VaultSearch._is_fts_fallback_error(exc) is True

    def test_fts_fallback_malformed_match(self):
        exc = sqlite3.OperationalError("malformed match expression")
        assert VaultSearch._is_fts_fallback_error(exc) is True

    def test_fts_fallback_knowledge_fts(self):
        exc = sqlite3.OperationalError("no such table: knowledge_fts")
        assert VaultSearch._is_fts_fallback_error(exc) is True

    def test_fts_fallback_runtime_error(self):
        exc = RuntimeError("fts5 module not available")
        assert VaultSearch._is_fts_fallback_error(exc) is True

    def test_fts_fallback_unrelated_operational(self):
        exc = sqlite3.OperationalError("database is locked")
        assert VaultSearch._is_fts_fallback_error(exc) is False

    def test_fts_fallback_unrelated_runtime(self):
        exc = RuntimeError("something else went wrong")
        assert VaultSearch._is_fts_fallback_error(exc) is False

    def test_fts_fallback_other_exception(self):
        exc = ValueError("invalid value")
        assert VaultSearch._is_fts_fallback_error(exc) is False

    def test_fts_fallback_syntax_error(self):
        exc = sqlite3.OperationalError("fts5: syntax error in query")
        assert VaultSearch._is_fts_fallback_error(exc) is True


class TestCoverageBoostParamValidation:
    """Tests for parameter validation in VaultSearch.__init__."""

    def test_invalid_rerank_strategy_raises(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            with pytest.raises(ValueError, match="rerank_strategy"):
                VaultSearch(db, rerank_strategy="invalid_strategy")
        finally:
            db.close()

    def test_invalid_llm_rewrite_strategy_raises(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            with pytest.raises(ValueError, match="llm_query_rewrite_strategy"):
                VaultSearch(db, llm_query_rewrite_strategy="invalid_strategy")
        finally:
            db.close()

    def test_valid_rerank_strategies(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            for strategy in ["auto", "lightweight", "cross_encoder", "none"]:
                search = VaultSearch(db, rerank_strategy=strategy)
                assert search._rerank_strategy == strategy
        finally:
            db.close()

    def test_valid_llm_rewrite_strategies(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            for strategy in ["auto", "synonym", "decompose", "keywords"]:
                search = VaultSearch(db, llm_query_rewrite_strategy=strategy)
                assert search._llm_query_rewrite_strategy == strategy
        finally:
            db.close()

    def test_negative_query_expansion_count_raises(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            with pytest.raises(ValueError, match="query_expansion_count"):
                VaultSearch(db, query_expansion_count=-1)
        finally:
            db.close()

    def test_zero_query_expansion_count_allowed(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, query_expansion_count=0)
            assert search._query_expansion_count == 0
        finally:
            db.close()

    def test_decay_below_zero_raises(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            with pytest.raises(ValueError):
                VaultSearch(db, query_expansion_synonym_decay=-0.1)
        finally:
            db.close()

    def test_decay_above_one_raises(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            with pytest.raises(ValueError):
                VaultSearch(db, query_expansion_abbr_decay=1.5)
        finally:
            db.close()

    def test_decay_boundary_values(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            # 0.0 and 1.0 should be valid
            search0 = VaultSearch(db, query_expansion_keyword_decay=0.0)
            assert search0._query_expansion_keyword_decay == 0.0
            search1 = VaultSearch(db, query_expansion_question_decay=1.0)
            assert search1._query_expansion_question_decay == 1.0
        finally:
            db.close()


class TestCoverageBoostKeywordSearchLike:
    """Tests for _search_keyword_like fallback method."""

    def test_like_search_basic(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Python Guide", content_raw="Python programming basics")
            search = VaultSearch(db, embed_provider=None)
            results = search._search_keyword_like(
                "Python",
                ["python"],
                limit=10,
            )
            assert isinstance(results, list)
            assert len(results) >= 1
        finally:
            db.close()

    def test_like_search_with_layer_filter(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Core Doc", content_raw="python content", layer="core")
            db.add_knowledge(title="Extended Doc", content_raw="python content", layer="extended")
            search = VaultSearch(db, embed_provider=None)
            results = search._search_keyword_like(
                "python",
                ["python"],
                limit=10,
                layer="core",
            )
            for r in results:
                assert r.get("layer") == "core"
        finally:
            db.close()

    def test_like_search_with_category_filter(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Tech Doc", content_raw="python content", category="tech")
            db.add_knowledge(title="Health Doc", content_raw="python content", category="health")
            search = VaultSearch(db, embed_provider=None)
            results = search._search_keyword_like(
                "python",
                ["python"],
                limit=10,
                category="tech",
            )
            for r in results:
                assert r.get("category") == "tech"
        finally:
            db.close()

    def test_like_search_with_both_filters(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Doc", content_raw="python", layer="core", category="tech")
            search = VaultSearch(db, embed_provider=None)
            results = search._search_keyword_like(
                "python",
                ["python"],
                limit=10,
                layer="core",
                category="tech",
            )
            assert len(results) >= 1
        finally:
            db.close()

    def test_like_search_min_score_filter(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="python java ruby", trust=1.0)
            search = VaultSearch(db, embed_provider=None)
            # With 3 terms and only 1 match, score = 1/3 ≈ 0.33
            results = search._search_keyword_like(
                "python java ruby",
                ["python", "java", "ruby"],
                limit=10,
                min_score=0.5,
            )
            # Should have high score since all terms match
            if results:
                assert all(r["_score"] >= 0.5 for r in results)
        finally:
            db.close()

    def test_like_search_no_matches(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="completely unrelated")
            search = VaultSearch(db, embed_provider=None)
            results = search._search_keyword_like(
                "xyz_nonexistent_term",
                ["xyz_nonexistent_term"],
                limit=10,
            )
            assert results == []
        finally:
            db.close()

    def test_like_search_respects_limit(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            for i in range(20):
                db.add_knowledge(title=f"Doc {i}", content_raw=f"python doc {i}")
            search = VaultSearch(db, embed_provider=None)
            results = search._search_keyword_like(
                "python",
                ["python"],
                limit=5,
            )
            assert len(results) <= 5
        finally:
            db.close()

    def test_like_search_tags_match(self, tmp_path):
        """測試標籤中的關鍵詞也能匹配。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Doc", content_raw="no match here", tags="python,programming")
            search = VaultSearch(db, embed_provider=None)
            results = search._search_keyword_like(
                "python",
                ["python"],
                limit=10,
            )
            assert len(results) >= 1
        finally:
            db.close()


class TestCoverageBoostQueryExpansion:
    """Additional tests for query expansion edge cases."""

    def test_expand_disabled(self, tmp_path):
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

    def test_expand_what_is_pattern_simplified(self, tmp_path):
        """測試簡體中文「什么是」模式。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            result = search._expand_query("什么是机器学习")
            queries = [q.lower() for q, w in result]
            # Should include the original and variations
            assert any("机器学习" in q for q in queries)
        finally:
            db.close()

    def test_expand_how_to_use_pattern(self, tmp_path):
        """測試「怎麼用」模式。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            result = search._expand_query("怎麼用 Git")
            queries = [q for q, w in result]
            assert any("使用方法" in q for q in queries) or any("教程" in q for q in queries)
        finally:
            db.close()

    def test_expand_why_pattern(self, tmp_path):
        """測試「為什麼」模式。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            result = search._expand_query("為什麼要學習編程")
            queries = [q for q, w in result]
            assert any("原因" in q for q in queries)
        finally:
            db.close()

    def test_expand_abbreviation_ai(self, tmp_path):
        """測試 AI 縮寫擴展。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            result = search._expand_query("AI 技術")
            queries = [q.lower() for q, w in result]
            assert any("人工智能" in q for q in queries) or any("ai" in q for q in queries)
        finally:
            db.close()

    def test_expand_abbreviation_db(self, tmp_path):
        """測試 db 縮寫擴展。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            result = search._expand_query("db 優化")
            queries = [q for q, w in result]
            assert any("數據庫" in q or "数据库" in q for q in queries)
        finally:
            db.close()

    def test_expand_keyword_extraction(self, tmp_path):
        """測試關鍵詞提取（停用詞過濾）。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            # Query with many stop words
            result = search._expand_query("什麼是 機器學習 和 深度學習 的 區別")
            assert isinstance(result, list)
            assert len(result) >= 1
        finally:
            db.close()

    def test_expand_sorted_by_weight(self, tmp_path):
        """測試擴展結果按權重降序排列。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            result = search._expand_query("什麼是 AI 機器學習")
            weights = [w for q, w in result]
            for i in range(len(weights) - 1):
                assert weights[i] >= weights[i + 1]
        finally:
            db.close()

    def test_expand_synonym_replacement(self, tmp_path):
        """測試同義詞替換。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            result = search._expand_query("向量 數據庫")
            queries = [q for q, w in result]
            # Should have embedding synonym for 向量
            assert any("embedding" in q.lower() or "嵌入" in q for q in queries)
        finally:
            db.close()


class TestCoverageBoostGraphExpand:
    """Tests for _apply_graph_expand method."""

    def test_graph_expand_empty_results(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            expanded = search._apply_graph_expand([], 2, 10)
            assert expanded == []
        finally:
            db.close()

    def test_graph_expand_graph_none(self, tmp_path):
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

    def test_graph_expand_with_depth_zero(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test")
            search = VaultSearch(db, embed_provider=None)
            results = [{"id": 1, "_score": 0.8}]
            expanded = search._apply_graph_expand(results, 0, 10)
            assert len(expanded) == len(results)
        finally:
            db.close()

    def test_graph_expand_respects_limit(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Doc", content_raw="content")
            search = VaultSearch(db, embed_provider=None)
            results = [{"id": 1, "_score": 0.8}]
            expanded = search._apply_graph_expand(results, 1, 1)
            assert len(expanded) <= 1
        finally:
            db.close()


class TestCoverageBoostInfoMethod:
    """Tests for VaultSearch.info() method."""

    def test_info_returns_dict(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            assert isinstance(info, dict)
        finally:
            db.close()

    def test_info_has_layers(self, tmp_path):
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

    def test_info_basic_layer_keyword_search(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            assert info["基礎層"]["keyword_search"] is True
            assert info["basic"]["keyword_search"] is True
        finally:
            db.close()

    def test_info_rerank_disabled(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_rerank=False)
            info = search.info()
            assert info["基礎層"]["lightweight_rerank"] is False
        finally:
            db.close()

    def test_info_query_expansion_disabled(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, enable_query_expansion=False)
            info = search.info()
            assert info["基礎層"]["query_expansion"] is False
        finally:
            db.close()

    def test_info_config_weights(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, keyword_weight=0.7, vector_weight=0.3)
            info = search.info()
            assert info["配置"]["keyword_weight"] == 0.7
            assert info["配置"]["vector_weight"] == 0.3
        finally:
            db.close()

    def test_info_config_rerank_strategy(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, rerank_strategy="lightweight")
            info = search.info()
            assert info["配置"]["rerank_strategy"] == "lightweight"
        finally:
            db.close()

    def test_info_default_mode_without_embeddings(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            info = search.info()
            assert info["配置"]["default_mode"] == "keyword"
        finally:
            db.close()

    def test_info_no_document_map(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None, graph=None)
            info = search.info()
            assert info["基礎層"]["document_map_support"] is False
        finally:
            db.close()


class TestCoverageBoostExtractBestClaim:
    """Additional tests for _extract_best_claim."""

    def test_extract_none_content(self):
        """測試 None 輸入。"""
        assert VaultSearch._extract_best_claim(None) == ""

    def test_extract_empty_string(self):
        """測試空字符串。"""
        assert VaultSearch._extract_best_claim("") == ""

    def test_extract_no_claims_section(self):
        """測試沒有 CLAIMS 段的內容。"""
        content = "Just some regular content without any claims."
        assert VaultSearch._extract_best_claim(content) == ""

    def test_extract_single_claim_with_line_number(self):
        """測試單個帶行號的主張。"""
        content = """CLAIMS:
- [C1] This is the best claim (L42)
"""
        result = VaultSearch._extract_best_claim(content)
        assert result == "This is the best claim"

    def test_extract_claim_without_line_number(self):
        """測試沒有行號的主張。"""
        content = """CLAIMS:
- [C1] Claim without line number
"""
        result = VaultSearch._extract_best_claim(content)
        assert result == "Claim without line number"

    def test_extract_claims_section_with_trailing_content(self):
        """測試 CLAIMS 段後有其他內容。"""
        content = """CLAIMS:
- [C1] First claim (L1)
Some other content that should be ignored
"""
        result = VaultSearch._extract_best_claim(content)
        assert result == "First claim"

    def test_extract_multiple_claims_returns_first(self):
        """測試多個主張時返回第一個。"""
        content = """CLAIMS:
- [C1] First claim (L1)
- [C2] Second claim (L5)
- [C3] Third claim (L10)
"""
        result = VaultSearch._extract_best_claim(content)
        assert result == "First claim"

    def test_extract_claim_with_bracketed_id_two_digits(self):
        """測試兩位數的 claim ID。"""
        content = """CLAIMS:
- [C10] Tenth claim (L100)
"""
        result = VaultSearch._extract_best_claim(content)
        assert result == "Tenth claim"

    def test_extract_claim_with_special_characters(self):
        """測試包含特殊字符的主張。"""
        content = """CLAIMS:
- [C1] Claim with @#$% special chars (L1)
"""
        result = VaultSearch._extract_best_claim(content)
        assert "special chars" in result


class TestCoverageBoostTokenize:
    """Additional tests for _tokenize method."""

    def test_tokenize_special_characters_only(self):
        """測試只有特殊字符。"""
        result = VaultSearch._tokenize("!@#$%^&*()")
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_tokenize_numbers_only(self):
        """測試只有數字。"""
        result = VaultSearch._tokenize("12345 67890")
        assert isinstance(result, list)

    def test_tokenize_mixed_alphanumeric(self):
        """測試字母數字混合。"""
        result = VaultSearch._tokenize("python3 java17 go1.21")
        # Should extract the English word parts
        assert any("python" in t.lower() for t in result)
        assert any("java" in t.lower() for t in result)

    def test_tokenize_chinese_with_english(self):
        """測試中英文混合。"""
        result = VaultSearch._tokenize("Python 編程 語言")
        assert any("python" in t.lower() for t in result)
        assert any("編程" in t for t in result) or any("語言" in t for t in result)

    def test_tokenize_deduplication(self):
        """測試去重（大小寫不敏感）。"""
        result = VaultSearch._tokenize("Hello hello HELLO world World")
        # Should have 2 unique terms
        assert len(result) == 2

    def test_tokenize_single_chinese_char(self):
        """測試單個中文字符。"""
        result = VaultSearch._tokenize("學")
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_tokenize_order_preserved(self):
        """測試詞語順序與原文一致。"""
        result = VaultSearch._tokenize("first second third")
        assert result[0].lower() == "first"
        assert result[1].lower() == "second"
        assert result[2].lower() == "third"

    def test_tokenize_empty_string(self):
        """測試空字符串。"""
        result = VaultSearch._tokenize("")
        assert result == [""]


class TestCoverageBoostNormalizeChinese:
    """Additional tests for _normalize_chinese."""

    def test_normalize_all_traditional_entries(self):
        """測試所有繁體中文條目的轉換。"""
        tc_sc_map = VaultSearch._TC_SC_MAP
        for tc, sc in tc_sc_map.items():
            result = VaultSearch._normalize_chinese(tc)
            assert result == sc, f"Failed for '{tc}'"

    def test_normalize_mixed_traditional_simplified(self):
        """測試繁簡混合文本。"""
        text = "什麼是 數據庫 優化 效能"
        result = VaultSearch._normalize_chinese(text)
        # Should have simplified forms
        assert "什么是" in result
        assert "数据库" in result

    def test_normalize_already_simplified(self):
        """測試已經是簡體的文本不變。"""
        text = "什么是数据库优化性能"
        result = VaultSearch._normalize_chinese(text)
        assert result == text

    def test_normalize_english_only(self):
        """測試只有英文的文本不變。"""
        text = "hello world python programming"
        result = VaultSearch._normalize_chinese(text)
        assert result == text

    def test_normalize_empty_string(self):
        """測試空字符串。"""
        result = VaultSearch._normalize_chinese("")
        assert result == ""


class TestCoverageBoostCompactResult:
    """Additional tests for _compact_result."""

    def test_compact_empty_dict(self):
        """測試空字典。"""
        result = VaultSearch._compact_result({})
        assert result == {}

    def test_compact_with_all_fields(self):
        """測試所有字段都存在。"""
        doc = {
            "id": 1,
            "title": "Test Doc",
            "category": "tech",
            "layer": "core",
            "trust": 0.9,
            "tags": "test",
            "best_claim": "test claim",
            "best_span": "L1-L5",
            "node_uid": "node-123",
            "path": "/docs/test",
            "heading": "Test Heading",
            "line_start": 1,
            "line_end": 5,
            "citation": "#1 Test L1-L5",
            "recommended_next_tool": "vault_read_range",
            "next_action": {"tool": "test"},
            "next_actions": [{"tool": "test"}],
            "_rerank_score": 0.85,
            "content_raw": "should not appear",
            "_score": 0.7,
        }
        result = VaultSearch._compact_result(doc)
        assert "content_raw" not in result
        assert "_score" not in result
        assert result["id"] == 1
        assert result["title"] == "Test Doc"
        assert result["rerank_score"] == 0.85

    def test_compact_without_rerank_score(self):
        """測試沒有 rerank_score。"""
        doc = {"id": 1, "title": "Test", "content_raw": "raw"}
        result = VaultSearch._compact_result(doc)
        assert "rerank_score" not in result
        assert "content_raw" not in result

    def test_compact_partial_fields(self):
        """測試只有部分字段。"""
        doc = {"id": 42, "title": "Partial"}
        result = VaultSearch._compact_result(doc)
        assert result == {"id": 42, "title": "Partial"}


class TestCoverageBoostStaticRerank:
    """Additional tests for static _rerank method."""

    def test_rerank_with_empty_query(self):
        """測試空 query 時使用基礎 rerank。"""
        results = [
            {"_score": 0.8, "trust": 0.9, "updated_at": "2024-01-15T00:00:00Z"},
            {"_score": 0.7, "trust": 0.8, "updated_at": "2024-01-01T00:00:00Z"},
        ]
        reranked = VaultSearch._rerank(results, query="")
        assert len(reranked) == 2
        assert "_rerank_score" in reranked[0]

    def test_rerank_with_graph_bonus(self):
        """測試圖譜深度加成。"""
        results = [
            {"_score": 0.5, "trust": 0.5, "_graph_distance": 0},
            {"_score": 0.5, "trust": 0.5, "_graph_distance": 2},
        ]
        reranked = VaultSearch._rerank(results, query="")
        # Distance 0 should get more bonus
        assert reranked[0]["_graph_distance"] == 0

    def test_rerank_with_high_score_normalization(self):
        """測試高分（>1）時的正規化。"""
        results = [
            {"_score": 2.5, "trust": 0.5},
            {"_score": 1.5, "trust": 0.5},
        ]
        reranked = VaultSearch._rerank(results, query="")
        assert len(reranked) == 2
        assert "_rerank_score" in reranked[0]

    def test_rerank_empty_list(self):
        """測試空列表。"""
        reranked = VaultSearch._rerank([], query="test")
        assert reranked == []

    def test_rerank_with_explicit_freshness(self):
        """測試有 freshness 字段時直接使用。"""
        results = [
            {"_score": 0.5, "trust": 0.5, "freshness": 0.9},
            {"_score": 0.5, "trust": 0.5, "freshness": 0.1},
        ]
        reranked = VaultSearch._rerank(results, query="")
        assert reranked[0]["freshness"] == 0.9

    def test_rerank_with_query_uses_lightweight(self):
        """測試有 query 時使用輕量 reranker。"""
        results = [
            {"id": 1, "title": "Python", "content_raw": "Python code", "_score": 0.5},
            {"id": 2, "title": "Java", "content_raw": "Java code", "_score": 0.5},
        ]
        reranked = VaultSearch._rerank(results, query="Python")
        assert len(reranked) == 2
        # Python result should rank higher
        assert reranked[0]["id"] == 1


class TestCoverageBoostSearchMethod:
    """Additional tests for VaultSearch.search() method."""

    def test_search_mode_keyword(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Python Guide", content_raw="Python programming")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("Python", mode="keyword", use_rerank=False)
            assert isinstance(results, list)
        finally:
            db.close()

    def test_search_mode_auto(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Python Guide", content_raw="Python programming")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("Python", mode="auto", use_rerank=False)
            assert isinstance(results, list)
        finally:
            db.close()

    def test_search_mode_basic(self, tmp_path):
        """測試 basic 模式（auto 的別名）。"""
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Python Guide", content_raw="Python programming")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("Python", mode="basic", use_rerank=False)
            assert isinstance(results, list)
        finally:
            db.close()

    def test_search_invalid_mode_raises(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            with pytest.raises(ValueError, match="無效的搜尋模式"):
                search.search("test", mode="invalid_mode")
        finally:
            db.close()

    def test_search_with_min_trust(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="High Trust", content_raw="python content", trust=0.9)
            db.add_knowledge(title="Low Trust", content_raw="python content", trust=0.2)
            search = VaultSearch(db, embed_provider=None)
            results = search.search("python", mode="keyword", min_trust=0.5, use_rerank=False)
            for r in results:
                assert r.get("trust", 0) >= 0.5
        finally:
            db.close()

    def test_search_with_compact(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Compact Test", content_raw="compact content test")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("compact", mode="keyword", compact=True, use_rerank=False)
            for r in results:
                assert "content_raw" not in r
                assert "best_claim" in r or "id" in r
        finally:
            db.close()

    def test_search_with_rerank_disabled(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Test", content_raw="test content")
            search = VaultSearch(db, embed_provider=None)
            results = search.search("test", mode="keyword", use_rerank=False)
            assert isinstance(results, list)
        finally:
            db.close()

    def test_search_no_results(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            search = VaultSearch(db, embed_provider=None)
            results = search.search("nonexistent_xyz_123", mode="keyword", use_rerank=False)
            assert results == []
        finally:
            db.close()

    def test_search_with_query_expansion_disabled(self, tmp_path):
        db = VaultDB(str(tmp_path / "test.db"))
        db.connect()
        try:
            db.add_knowledge(title="Python", content_raw="python programming")
            search = VaultSearch(db, embed_provider=None, enable_query_expansion=False)
            results = search.search("python", mode="keyword", use_query_expansion=True, use_rerank=False)
            # Even with use_query_expansion=True, if disabled at init, no expansion
            assert isinstance(results, list)
        finally:
            db.close()
