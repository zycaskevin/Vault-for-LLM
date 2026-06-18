"""Tests for the synthetic semantic-index benchmark harness."""

from __future__ import annotations


def test_semantic_index_benchmark_small_size_hits():
    from benchmarks.semantic_index_benchmark import run_one

    result = run_one(12, repeats=2, limit=5, dim=8)

    assert result["size"] == 12
    assert result["repeats"] == 2
    assert result["hit_rate"] == 1.0
    assert result["truncated_runs"] == 0
    assert result["mean_scanned_rows"] == 12
    assert result["p95_latency_ms"] >= 0


def test_semantic_index_benchmark_reports_truncation(monkeypatch):
    import vault.semantic as semantic_module
    from benchmarks.semantic_index_benchmark import run_one

    monkeypatch.setattr(semantic_module, "SEMANTIC_MAX_SCAN_ROWS", 5)

    result = run_one(8, repeats=1, limit=5, dim=8)

    assert result["hit_rate"] == 0.0
    assert result["hit_ranks"] == [None]
    assert result["truncated_runs"] == 1
    assert result["mean_scanned_rows"] == 5
