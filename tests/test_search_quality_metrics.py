"""Sprint 4E Search QA metrics and snapshot comparison tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vault.db import VaultDB
from vault.docmap import build_document_map_for_entry
from vault.search_qa import (
    _matches_expected,
    compare_search_qa_snapshots,
    evaluate_search_qa,
    format_search_qa_comparison,
    load_search_qa_set,
)


REPO_ROOT = Path(__file__).parent.parent
BENCHMARK_DIR = REPO_ROOT / "benchmarks" / "search_qa"


ALPHA_RAW = "\n".join(
    [
        "# Tool-gated Reading Guide",
        "Intro",
        "## Tool-gated Reading",
        "Tool-gated reading keeps agents from reading whole documents.",
        "It requires map navigation before read_range evidence.",
    ]
)
ALPHA_AAAK = "\n".join(
    [
        "TITLE: Tool-gated Reading Guide",
        "CLAIMS:",
        "- [C1] Tool-gated reading keeps agents from reading whole documents. (L4)",
    ]
)

BETA_RAW = "\n".join(
    [
        "# Citation Policy Boundary",
        "Search citations are navigation hints only, not final answer support.",
        "Final citations require read_range output.",
    ]
)

GAMMA_RAW = "\n".join(
    [
        "# 文件地圖閱讀指南",
        "簡介",
        "## 文件地圖與讀取範圍",
        "文件地圖幫助代理先查看章節，再使用讀取範圍取得證據。",
        "此流程避免一次讀完整份文件。",
    ]
)
GAMMA_AAAK = "\n".join(
    [
        "TITLE: 文件地圖閱讀指南",
        "CLAIMS:",
        "- [C1] 文件地圖幫助代理先查看章節，再使用讀取範圍取得證據。 (L4)",
    ]
)

DELTA_RAW = "\n".join(
    [
        "# 引用政策邊界",
        "搜尋引用只是導航提示，不是最終引用。",
        "最終引用需要來自讀取範圍的輸出。",
    ]
)


def _assert_baseline_metrics(actual: dict):
    expected_quality = {
        "total_cases": 3,
        "cases_with_results": 2,
        "top1_hits": 2,
        "topk_hits": 2,
        "no_result_cases": 1,
        "no_result_false_positives": 0,
        "no_result_precision": 1.0,
        "mean_reciprocal_rank": 2 / 3,
        "map_guidance_rate": 1 / 3,
        "read_range_guidance_rate": 1 / 3,
        "citation_policy_violations": 0,
    }
    for key, value in expected_quality.items():
        assert actual[key] == value
    for key in ("mean_latency_ms", "p95_latency_ms", "min_latency_ms", "max_latency_ms"):
        assert key in actual
        assert actual[key] >= 0
    assert actual["min_latency_ms"] <= actual["mean_latency_ms"] <= actual["max_latency_ms"]
    assert actual["min_latency_ms"] <= actual["p95_latency_ms"] <= actual["max_latency_ms"]



def _build_fixture_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "vault.db"
    db = VaultDB(db_path).connect()
    try:
        alpha_id = db.add_knowledge(
            "Tool-gated Reading Guide",
            ALPHA_RAW,
            content_aaak=ALPHA_AAAK,
            category="technique",
            tags="search,map,read_range",
            trust=0.9,
        )
        build_document_map_for_entry(db.conn, alpha_id)
        db.add_knowledge(
            "Citation Policy Boundary",
            BETA_RAW,
            category="decision",
            tags="citation,policy",
            trust=0.8,
        )
        gamma_id = db.add_knowledge(
            "文件地圖閱讀指南",
            GAMMA_RAW,
            content_aaak=GAMMA_AAAK,
            category="technique",
            tags="文件地圖,讀取範圍,證據",
            trust=0.87,
        )
        build_document_map_for_entry(db.conn, gamma_id)
        db.add_knowledge(
            "引用政策邊界",
            DELTA_RAW,
            category="decision",
            tags="引用,政策",
            trust=0.86,
        )
    finally:
        db.close()
    return db_path


def _write_qa_file(tmp_path: Path) -> Path:
    qa_file = tmp_path / "search_qa.json"
    qa_file.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {
                        "id": "tool_gated_reading",
                        "query": "tool-gated reading",
                        "expected_title_substrings": ["Tool-gated Reading"],
                    },
                    {
                        "id": "citation_policy",
                        "query": "citation policy boundary",
                        "expected_titles": ["Citation Policy Boundary"],
                    },
                    {
                        "id": "no_result_control",
                        "query": "zzznomatch qqqnomatch",
                        "expected_no_results": True,
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return qa_file


def test_load_search_qa_set_accepts_extendable_repo_fixture():
    fixture = Path(__file__).parent / "fixtures" / "search_qa_set.json"

    qa = load_search_qa_set(fixture)

    assert qa["version"] == 1
    assert qa["cases"]
    assert {"id", "query"}.issubset(qa["cases"][0])


def test_public_search_qa_repository_fixtures_load_from_repo_root_and_cover_english_and_cjk():
    en = load_search_qa_set(BENCHMARK_DIR / "basic.en.json")
    zh = load_search_qa_set(BENCHMARK_DIR / "basic.zh-Hant.json")

    assert en["version"] == 1
    assert zh["version"] == 1
    assert en["language"] == "en"
    assert zh["language"] == "zh-Hant"
    assert {case["id"] for case in en["cases"]} == {
        "en_document_map_read_range",
        "en_citation_policy_boundary",
        "en_no_result_control",
    }
    assert {case["id"] for case in zh["cases"]} == {
        "zh_document_map_read_range",
        "zh_citation_policy_boundary",
        "zh_no_result_control",
    }
    assert any("read_range" in case["query"] for case in en["cases"])
    assert any("讀取範圍" in case["query"] for case in zh["cases"])
    assert any(
        any("\u4e00" <= char <= "\u9fff" for char in case["query"])
        for case in zh["cases"]
    )


def test_public_search_qa_repository_fixtures_run_against_local_demo_db(tmp_path):
    db_path = _build_fixture_db(tmp_path)

    en_snapshot = evaluate_search_qa(
        db_path=db_path,
        qa_file=BENCHMARK_DIR / "basic.en.json",
        mode="keyword",
        limit=3,
        generated_at="2026-01-02T03:04:05+00:00",
    )
    zh_snapshot = evaluate_search_qa(
        db_path=db_path,
        qa_file=BENCHMARK_DIR / "basic.zh-Hant.json",
        mode="keyword",
        limit=3,
        generated_at="2026-01-02T03:04:05+00:00",
    )

    _assert_baseline_metrics(en_snapshot["aggregate"])
    _assert_baseline_metrics(zh_snapshot["aggregate"])

    zh_doc_case = next(
        case for case in zh_snapshot["cases"] if case["id"] == "zh_document_map_read_range"
    )
    assert zh_doc_case["top1_hit"] is True
    assert zh_doc_case["results"][0]["title"] == "文件地圖閱讀指南"
    assert zh_doc_case["has_map_guidance"] is True
    assert zh_doc_case["has_read_range_guidance"] is True
    assert zh_doc_case["citation_policy_violations"] == []

    assert all(
        case["citation_policy_violations"] == []
        for case in en_snapshot["cases"] + zh_snapshot["cases"]
    )


def test_expected_title_substrings_require_all_terms():
    case = {"expected_title_substrings": ["citation", "policy"]}

    assert _matches_expected(case, {"title": "Citation Policy Boundary"}) is True
    assert _matches_expected(case, {"title": "Citation Only"}) is False
    assert _matches_expected(case, {"title": "Policy Only"}) is False


def test_evaluate_search_qa_computes_deterministic_metrics(tmp_path):
    db_path = _build_fixture_db(tmp_path)
    qa_file = _write_qa_file(tmp_path)

    snapshot = evaluate_search_qa(
        db_path=db_path,
        qa_file=qa_file,
        mode="keyword",
        limit=3,
        generated_at="2026-01-02T03:04:05+00:00",
    )

    assert snapshot["qa_file"] == str(qa_file)
    assert snapshot["mode"] == "keyword"
    assert snapshot["limit"] == 3
    assert snapshot["min_score"] is None
    assert snapshot["generated_at"] == "2026-01-02T03:04:05+00:00"
    _assert_baseline_metrics(snapshot["aggregate"])
    assert [case["id"] for case in snapshot["cases"]] == [
        "tool_gated_reading",
        "citation_policy",
        "no_result_control",
    ]
    first = snapshot["cases"][0]
    assert first["top1_hit"] is True
    assert first["hit_rank"] == 1
    assert first["has_map_guidance"] is True
    assert first["has_read_range_guidance"] is True
    assert first["results"][0]["title"] == "Tool-gated Reading Guide"
    assert "citation" in first["results"][0]
    assert first["citation_policy_violations"] == []

    second = snapshot["cases"][1]
    assert second["top1_hit"] is True
    assert second["has_map_guidance"] is False
    assert second["has_read_range_guidance"] is False

    third = snapshot["cases"][2]
    assert third["expected_no_results"] is True
    assert third["no_result_hit"] is True
    assert third["no_result_false_positive"] is False
    assert third["result_count"] == 0
    assert third["reciprocal_rank"] == 0.0

    # Must be JSON serializable without custom encoders.
    json.dumps(snapshot, sort_keys=True)


def test_search_qa_flags_search_citation_without_read_range_guidance_conservatively(tmp_path, monkeypatch):
    db_path = _build_fixture_db(tmp_path)
    qa_file = _write_qa_file(tmp_path)

    from vault import search_qa as search_qa_module

    original_summary = search_qa_module._summarize_result

    def injected_bad_summary(result):
        summary = original_summary(result)
        if summary["title"] == "Citation Policy Boundary":
            summary["citation"] = "#2 Citation Policy Boundary L1-L2"
            summary["citation_role"] = "final"
        return summary

    monkeypatch.setattr(search_qa_module, "_summarize_result", injected_bad_summary)

    snapshot = evaluate_search_qa(db_path=db_path, qa_file=qa_file, mode="keyword", limit=3)

    policy_case = next(case for case in snapshot["cases"] if case["id"] == "citation_policy")
    assert policy_case["citation_policy_violations"] == [
        "search_result_labeled_as_final_citation",
        "search_result_citation_without_read_range_guidance",
    ]
    assert snapshot["aggregate"]["citation_policy_violations"] == 2


def test_search_qa_min_score_can_expose_no_result_false_positives(tmp_path):
    db_path = _build_fixture_db(tmp_path)
    qa_file = tmp_path / "weak_no_result.json"
    qa_file.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {
                        "id": "weak_no_result",
                        "query": "mars banana nonexistent policy",
                        "expected_no_results": True,
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    strict_snapshot = evaluate_search_qa(
        db_path=db_path,
        qa_file=qa_file,
        mode="keyword",
        limit=3,
        generated_at="2026-01-02T03:04:05+00:00",
    )
    loose_snapshot = evaluate_search_qa(
        db_path=db_path,
        qa_file=qa_file,
        mode="keyword",
        limit=3,
        min_score=0.0,
        generated_at="2026-01-02T03:04:05+00:00",
    )

    assert strict_snapshot["aggregate"]["no_result_false_positives"] == 0
    assert strict_snapshot["cases"][0]["no_result_hit"] is True
    assert loose_snapshot["min_score"] == 0.0
    assert loose_snapshot["aggregate"]["no_result_false_positives"] == 1
    assert loose_snapshot["cases"][0]["no_result_false_positive"] is True


def test_compare_search_qa_snapshots_computes_stable_deltas_and_text():
    before = {
        "aggregate": {
            "total_cases": 2,
            "cases_with_results": 1,
            "top1_hits": 0,
            "topk_hits": 1,
            "no_result_cases": 1,
            "no_result_false_positives": 1,
            "no_result_precision": 0.0,
            "mean_reciprocal_rank": 0.25,
            "map_guidance_rate": 0.0,
            "read_range_guidance_rate": 0.0,
            "citation_policy_violations": 1,
            "mean_latency_ms": 10.0,
            "p95_latency_ms": 15.0,
            "min_latency_ms": 5.0,
            "max_latency_ms": 15.0,
        }
    }
    after = {
        "aggregate": {
            "total_cases": 2,
            "cases_with_results": 2,
            "top1_hits": 1,
            "topk_hits": 2,
            "no_result_cases": 1,
            "no_result_false_positives": 0,
            "no_result_precision": 1.0,
            "mean_reciprocal_rank": 0.75,
            "map_guidance_rate": 0.5,
            "read_range_guidance_rate": 0.5,
            "citation_policy_violations": 0,
            "mean_latency_ms": 7.0,
            "p95_latency_ms": 12.0,
            "min_latency_ms": 4.0,
            "max_latency_ms": 12.0,
        }
    }

    comparison = compare_search_qa_snapshots(before, after)

    assert comparison["metrics"]["top1_hits"] == {
        "before": 0,
        "after": 1,
        "delta": 1,
    }
    assert comparison["metrics"]["mean_reciprocal_rank"] == {
        "before": 0.25,
        "after": 0.75,
        "delta": 0.5,
    }
    assert comparison["metrics"]["citation_policy_violations"]["delta"] == -1
    assert comparison["metrics"]["no_result_false_positives"]["delta"] == -1
    assert comparison["metrics"]["no_result_precision"]["delta"] == 1.0
    assert comparison["metrics"]["mean_latency_ms"] == {
        "before": 10.0,
        "after": 7.0,
        "delta": -3.0,
    }
    assert json.loads(json.dumps(comparison)) == comparison

    text = format_search_qa_comparison(comparison)
    assert "Search QA comparison" in text
    assert "top1_hits" in text
    assert "+1" in text
    assert "citation_policy_violations" in text
    assert "-1" in text


def test_search_qa_cli_run_and_compare_smoke(tmp_path):
    db_path = _build_fixture_db(tmp_path)
    qa_file = _write_qa_file(tmp_path)
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    compare_path = tmp_path / "compare.json"

    run_cmd = [
        sys.executable,
        "-m",
        "vault.cli",
        "search-qa",
        "run",
        "--db-path",
        str(db_path),
        "--qa-file",
        str(qa_file),
        "--output",
        str(after_path),
        "--mode",
        "keyword",
        "--limit",
        "3",
        "--min-score",
        "0.34",
    ]
    result = subprocess.run(run_cmd, cwd=Path(__file__).parent.parent, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert after_path.exists()
    snapshot = json.loads(after_path.read_text(encoding="utf-8"))
    assert snapshot["aggregate"]["top1_hits"] == 2
    assert snapshot["min_score"] == 0.34
    assert snapshot["aggregate"]["no_result_false_positives"] == 0
    assert "mean_latency_ms" in snapshot["aggregate"]
    assert "mean_latency_ms" in result.stdout
    assert "Search QA" in result.stdout

    before = dict(snapshot)
    before["aggregate"] = dict(snapshot["aggregate"], top1_hits=1)
    before_path.write_text(json.dumps(before), encoding="utf-8")

    compare_cmd = [
        sys.executable,
        "-m",
        "vault.cli",
        "search-qa",
        "compare",
        "--before",
        str(before_path),
        "--after",
        str(after_path),
        "--output",
        str(compare_path),
    ]
    result = subprocess.run(compare_cmd, cwd=Path(__file__).parent.parent, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert compare_path.exists()
    comparison = json.loads(compare_path.read_text(encoding="utf-8"))
    assert comparison["metrics"]["top1_hits"]["delta"] == 1
    assert "top1_hits" in result.stdout


def test_search_qa_cli_hybrid_allow_hash_uses_semantic_index(tmp_path):
    from vault.semantic import DeterministicHashEmbeddingProvider, rebuild_semantic_index

    db_path = _build_fixture_db(tmp_path)
    qa_file = _write_qa_file(tmp_path)
    output_path = tmp_path / "hybrid.json"
    db = VaultDB(db_path).connect()
    try:
        rebuild_semantic_index(db, provider=DeterministicHashEmbeddingProvider(dim=8), allow_hash=True)
    finally:
        db.close()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "vault.cli",
            "search-qa",
            "run",
            "--db-path",
            str(db_path),
            "--qa-file",
            str(qa_file),
            "--output",
            str(output_path),
            "--mode",
            "hybrid",
            "--allow-hash",
            "--hash-dim",
            "8",
            "--limit",
            "3",
        ],
        cwd=Path(__file__).parent.parent,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    snapshot = json.loads(output_path.read_text(encoding="utf-8"))
    modes = {item.get("mode") for case in snapshot["cases"] for item in case["results"]}
    assert "hybrid_semantic_hash" in modes


def test_search_qa_cli_auto_allow_hash_can_use_semantic_index(tmp_path):
    from vault.semantic import DeterministicHashEmbeddingProvider, rebuild_semantic_index

    db_path = _build_fixture_db(tmp_path)
    qa_file = _write_qa_file(tmp_path)
    output_path = tmp_path / "auto.json"
    db = VaultDB(db_path).connect()
    try:
        rebuild_semantic_index(db, provider=DeterministicHashEmbeddingProvider(dim=8), allow_hash=True)
    finally:
        db.close()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "vault.cli",
            "search-qa",
            "run",
            "--db-path",
            str(db_path),
            "--qa-file",
            str(qa_file),
            "--output",
            str(output_path),
            "--mode",
            "auto",
            "--allow-hash",
            "--hash-dim",
            "8",
            "--limit",
            "3",
        ],
        cwd=Path(__file__).parent.parent,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    snapshot = json.loads(output_path.read_text(encoding="utf-8"))
    modes = {item.get("mode") for case in snapshot["cases"] for item in case["results"]}
    assert "hybrid_semantic_hash" in modes
