"""Sprint 4E Search QA metrics and snapshot comparison tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vault.guardrails_db import GuardrailsDB
from vault.guardrails_map import build_document_map_for_entry
from vault.search_qa import (
    _matches_expected,
    compare_search_qa_snapshots,
    evaluate_search_qa,
    format_search_qa_comparison,
    load_search_qa_set,
)


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


def _build_fixture_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "guardrails.db"
    db = GuardrailsDB(db_path).connect()
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
                        "expected_titles": ["Not Present"],
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
    assert snapshot["generated_at"] == "2026-01-02T03:04:05+00:00"
    assert snapshot["aggregate"] == {
        "total_cases": 3,
        "cases_with_results": 2,
        "top1_hits": 2,
        "topk_hits": 2,
        "mean_reciprocal_rank": 2 / 3,
        "map_guidance_rate": 1 / 3,
        "read_range_guidance_rate": 1 / 3,
        "citation_policy_violations": 0,
    }
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


def test_compare_search_qa_snapshots_computes_stable_deltas_and_text():
    before = {
        "aggregate": {
            "total_cases": 2,
            "cases_with_results": 1,
            "top1_hits": 0,
            "topk_hits": 1,
            "mean_reciprocal_rank": 0.25,
            "map_guidance_rate": 0.0,
            "read_range_guidance_rate": 0.0,
            "citation_policy_violations": 1,
        }
    }
    after = {
        "aggregate": {
            "total_cases": 2,
            "cases_with_results": 2,
            "top1_hits": 1,
            "topk_hits": 2,
            "mean_reciprocal_rank": 0.75,
            "map_guidance_rate": 0.5,
            "read_range_guidance_rate": 0.5,
            "citation_policy_violations": 0,
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
        "vault.guardrails_cli",
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
    ]
    result = subprocess.run(run_cmd, cwd=Path(__file__).parent.parent, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert after_path.exists()
    snapshot = json.loads(after_path.read_text(encoding="utf-8"))
    assert snapshot["aggregate"]["top1_hits"] == 2
    assert "Search QA" in result.stdout

    before = dict(snapshot)
    before["aggregate"] = dict(snapshot["aggregate"], top1_hits=1)
    before_path.write_text(json.dumps(before), encoding="utf-8")

    compare_cmd = [
        sys.executable,
        "-m",
        "vault.guardrails_cli",
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
