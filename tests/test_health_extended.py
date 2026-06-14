"""Extended tests for vault/health.py"""
import pytest
from pathlib import Path


class TestRatio:
    def test_ratio_normal(self):
        from vault.health import _ratio
        assert _ratio(5, 10) == 0.5

    def test_ratio_zero_denominator(self):
        from vault.health import _ratio
        assert _ratio(5, 0) == 0.0

    def test_ratio_negative_denominator(self):
        from vault.health import _ratio
        assert _ratio(5, -5) == 0.0

    def test_ratio_zero_numerator(self):
        from vault.health import _ratio
        assert _ratio(0, 10) == 0.0

    def test_ratio_one_to_one(self):
        from vault.health import _ratio
        assert _ratio(10, 10) == 1.0


class TestHasUsableBestSpan:
    def test_has_usable_best_span_full(self):
        from vault.health import _has_usable_best_span
        result = {
            "best_span": "some span",
            "best_node": {"node_uid": "abc"},
            "line_start": 5,
            "line_end": 10,
            "recommended_next_tool": "vault_read_range",
        }
        assert _has_usable_best_span(result) is True

    def test_has_usable_best_span_with_next_action(self):
        from vault.health import _has_usable_best_span
        result = {
            "best_span": "some span",
            "best_node": {"node_uid": "abc"},
            "line_start": 5,
            "line_end": 10,
            "next_action": "read",
        }
        assert _has_usable_best_span(result) is True

    def test_has_usable_best_span_with_read_action(self):
        from vault.health import _has_usable_best_span
        result = {
            "best_span": "some span",
            "best_node": {"node_uid": "abc"},
            "line_start": 5,
            "line_end": 10,
            "next_actions": [{"tool": "vault_read_range"}],
        }
        assert _has_usable_best_span(result) is True

    def test_has_usable_best_span_missing_best_span(self):
        from vault.health import _has_usable_best_span
        result = {
            "best_node": {"node_uid": "abc"},
            "line_start": 5,
            "line_end": 10,
            "recommended_next_tool": "vault_read_range",
        }
        assert _has_usable_best_span(result) is False

    def test_has_usable_best_span_missing_best_node(self):
        from vault.health import _has_usable_best_span
        result = {
            "best_span": "some span",
            "line_start": 5,
            "line_end": 10,
            "recommended_next_tool": "vault_read_range",
        }
        assert _has_usable_best_span(result) is False

    def test_has_usable_best_span_missing_lines(self):
        from vault.health import _has_usable_best_span
        result = {
            "best_span": "some span",
            "best_node": {"node_uid": "abc"},
            "recommended_next_tool": "vault_read_range",
        }
        assert _has_usable_best_span(result) is False

    def test_has_usable_best_span_no_next_action(self):
        from vault.health import _has_usable_best_span
        result = {
            "best_span": "some span",
            "best_node": {"node_uid": "abc"},
            "line_start": 5,
            "line_end": 10,
        }
        assert _has_usable_best_span(result) is False

    def test_has_usable_best_span_empty_dict(self):
        from vault.health import _has_usable_best_span
        assert _has_usable_best_span({}) is False

    def test_has_usable_best_span_next_actions_not_dict(self):
        from vault.health import _has_usable_best_span
        result = {
            "best_span": "some span",
            "best_node": {"node_uid": "abc"},
            "line_start": 5,
            "line_end": 10,
            "next_actions": ["not_a_dict"],
        }
        assert _has_usable_best_span(result) is False


class TestVaultHealthMetrics:
    def test_vault_health_metrics_creation(self):
        from vault.health import VaultHealthMetrics
        metrics = VaultHealthMetrics(
            total_entries=10,
            entries_with_nodes=8,
            entries_with_claims=6,
            entries_without_nodes=2,
            entries_without_claims=4,
            sampled_search_results=5,
            search_results_with_best_span=3,
            map_coverage=0.8,
            claim_coverage=0.6,
            citation_coverage=0.6,
            read_range_over_limit_violations=1,
        )
        assert metrics.total_entries == 10
        assert metrics.map_coverage == 0.8

    def test_vault_health_metrics_to_dict(self):
        from vault.health import VaultHealthMetrics
        metrics = VaultHealthMetrics(
            total_entries=10,
            entries_with_nodes=8,
            entries_with_claims=6,
            entries_without_nodes=2,
            entries_without_claims=4,
            sampled_search_results=5,
            search_results_with_best_span=3,
            map_coverage=0.8,
            claim_coverage=0.6,
            citation_coverage=0.6,
            read_range_over_limit_violations=1,
        )
        d = metrics.to_dict()
        assert isinstance(d, dict)
        assert d["total_entries"] == 10
        assert d["map_coverage"] == 0.8


class TestCollectVaultHealthMetrics:
    def test_collect_with_empty_db(self, tmp_path):
        from vault.health import collect_vault_health_metrics
        from vault.db import VaultDB
        
        db_path = str(tmp_path / "test.db")
        db = VaultDB(db_path)
        db.connect()
        db.close()
        
        metrics = collect_vault_health_metrics(db_path)
        assert metrics.total_entries == 0
        assert metrics.map_coverage == 0.0
        assert metrics.claim_coverage == 0.0
        assert metrics.citation_coverage == 0.0

    def test_collect_with_data(self, tmp_path):
        from vault.health import collect_vault_health_metrics
        from vault.db import VaultDB
        from vault.docmap import build_document_map_for_entry
        
        db_path = str(tmp_path / "test.db")
        db = VaultDB(db_path)
        db.connect()
        
        kid = db.add_knowledge(
            title="Test Document",
            content_raw="# Section 1\n\nContent here.\n\n# Section 2\n\nMore content.",
            category="test",
            layer="L3",
        )
        build_document_map_for_entry(db.conn, kid)
        db.close()
        
        metrics = collect_vault_health_metrics(db_path, sample_limit=5)
        assert metrics.total_entries == 1
        assert metrics.entries_with_nodes >= 1
        assert metrics.sampled_search_results >= 0

    def test_collect_zero_sample_limit(self, tmp_path):
        from vault.health import collect_vault_health_metrics
        from vault.db import VaultDB
        
        db_path = str(tmp_path / "test.db")
        db = VaultDB(db_path)
        db.connect()
        db.add_knowledge(title="Test", content_raw="Hello", category="test", layer="L3")
        db.close()
        
        metrics = collect_vault_health_metrics(db_path, sample_limit=0)
        assert metrics.total_entries == 1
        assert metrics.sampled_search_results == 0
        assert metrics.citation_coverage == 0.0

    def test_collect_negative_sample_limit(self, tmp_path):
        from vault.health import collect_vault_health_metrics
        from vault.db import VaultDB
        
        db_path = str(tmp_path / "test.db")
        db = VaultDB(db_path)
        db.connect()
        db.add_knowledge(title="Test", content_raw="Hello", category="test", layer="L3")
        db.close()
        
        metrics = collect_vault_health_metrics(db_path, sample_limit=-5)
        assert metrics.total_entries == 1
        assert metrics.sampled_search_results == 0

    def test_collect_invalid_sample_limit(self, tmp_path):
        from vault.health import collect_vault_health_metrics
        from vault.db import VaultDB
        
        db_path = str(tmp_path / "test.db")
        db = VaultDB(db_path)
        db.connect()
        db.add_knowledge(title="Test", content_raw="Hello", category="test", layer="L3")
        db.close()
        
        metrics = collect_vault_health_metrics(db_path, sample_limit="invalid")
        assert metrics.total_entries == 1


class TestCollectVaultHealthMetricsFromDb:
    def test_raises_on_disconnected_db(self, tmp_path):
        from vault.health import collect_vault_health_metrics_from_db
        from vault.db import VaultDB
        
        db_path = str(tmp_path / "test.db")
        db = VaultDB(db_path)
        # db.connect() - intentionally not connected
        
        with pytest.raises(ValueError, match="must be connected"):
            collect_vault_health_metrics_from_db(db)

    def test_invalid_max_read_range_lines(self, tmp_path):
        from vault.health import collect_vault_health_metrics_from_db
        from vault.db import VaultDB
        
        db_path = str(tmp_path / "test.db")
        db = VaultDB(db_path)
        db.connect()
        db.add_knowledge(title="Test", content_raw="Hello", category="test", layer="L3")
        
        metrics = collect_vault_health_metrics_from_db(db, max_read_range_lines="invalid")
        assert metrics.total_entries == 1
        
        db.close()

    def test_negative_max_read_range_lines(self, tmp_path):
        from vault.health import collect_vault_health_metrics_from_db
        from vault.db import VaultDB
        
        db_path = str(tmp_path / "test.db")
        db = VaultDB(db_path)
        db.connect()
        db.add_knowledge(title="Test", content_raw="Hello", category="test", layer="L3")
        
        metrics = collect_vault_health_metrics_from_db(db, max_read_range_lines=-10)
        assert metrics.total_entries == 1
        
        db.close()
