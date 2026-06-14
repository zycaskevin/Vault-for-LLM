"""
Extended tests for vault/search_qa.py
Focus on pure utility functions.
"""
import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock


class TestLoadSearchQaSet:
    def test_load_valid_qa_set(self, tmp_path):
        """Test loading a valid QA set."""
        from vault.search_qa import load_search_qa_set
        qa_file = tmp_path / "test_qa.json"
        data = {
            "name": "test",
            "cases": [
                {"id": "q1", "query": "What is Python?", "expected_ids": [1, 2]},
                {"id": "q2", "query": "How to code?", "expected_ids": [3]},
            ]
        }
        qa_file.write_text(json.dumps(data))
        result = load_search_qa_set(str(qa_file))
        assert result["name"] == "test"
        assert len(result["cases"]) == 2
        assert result["cases"][0]["id"] == "q1"

    def test_load_qa_set_missing_cases(self, tmp_path):
        """Test loading QA set without cases raises ValueError."""
        from vault.search_qa import load_search_qa_set
        qa_file = tmp_path / "bad_qa.json"
        qa_file.write_text(json.dumps({"name": "test"}))
        with pytest.raises(ValueError, match="must contain a cases list"):
            load_search_qa_set(str(qa_file))

    def test_load_qa_set_case_missing_id(self, tmp_path):
        """Test case without id raises ValueError."""
        from vault.search_qa import load_search_qa_set
        qa_file = tmp_path / "bad_qa.json"
        qa_file.write_text(json.dumps({"cases": [{"query": "test"}]}))
        with pytest.raises(ValueError, match="missing id"):
            load_search_qa_set(str(qa_file))

    def test_load_qa_set_not_dict(self, tmp_path):
        """Test non-dict JSON raises ValueError."""
        from vault.search_qa import load_search_qa_set
        qa_file = tmp_path / "bad_qa.json"
        qa_file.write_text(json.dumps([1, 2, 3]))
        with pytest.raises(ValueError, match="must contain a JSON object"):
            load_search_qa_set(str(qa_file))


class TestSummarizeResult:
    def test_summarize_result_copies_fields(self):
        """Test that _summarize_result copies specified fields."""
        from vault.search_qa import _summarize_result
        result = {
            "id": 42,
            "title": "Test Doc",
            "category": "tech",
            "layer": "L2",
            "trust": 0.8,
            "tags": "python,test",
            "citation": "Test L1-5",
            "_score": 0.95,
            "_mode": "semantic",
            "extra_field": "should not appear",
        }
        summary = _summarize_result(result)
        assert summary["id"] == 42
        assert summary["title"] == "Test Doc"
        assert summary["category"] == "tech"
        assert summary["layer"] == "L2"
        assert summary["trust"] == 0.8
        assert summary["tags"] == "python,test"
        assert summary["citation"] == "Test L1-5"
        assert summary["score"] == 0.95  # renamed from _score
        assert summary["mode"] == "semantic"  # renamed from _mode
        assert "extra_field" not in summary

    def test_summarize_result_empty(self):
        """Test summarizing empty result returns empty dict."""
        from vault.search_qa import _summarize_result
        summary = _summarize_result({})
        assert summary == {}


class TestAggregateCases:
    def test_aggregate_cases_basic(self):
        """Test basic case aggregation."""
        from vault.search_qa import _aggregate_cases
        cases = [
            {"result_count": 5, "top1_hit": True, "topk_hit": True,
             "reciprocal_rank": 1.0, "has_map_guidance": True,
             "has_read_range_guidance": False, "citation_policy_violations": [],
             "latency_ms": 100, "expected_no_results": False},
            {"result_count": 3, "top1_hit": False, "topk_hit": True,
             "reciprocal_rank": 0.5, "has_map_guidance": False,
             "has_read_range_guidance": True, "citation_policy_violations": ["v1"],
             "latency_ms": 200, "expected_no_results": False},
            {"result_count": 0, "top1_hit": False, "topk_hit": False,
             "reciprocal_rank": 0.0, "has_map_guidance": False,
             "has_read_range_guidance": False, "citation_policy_violations": [],
             "latency_ms": 50, "expected_no_results": True,
             "no_result_false_positive": False},
        ]
        agg = _aggregate_cases(cases)
        assert agg["total_cases"] == 3
        assert agg["cases_with_results"] == 2
        assert agg["top1_hits"] == 1
        assert agg["topk_hits"] == 2
        assert agg["mean_reciprocal_rank"] == pytest.approx((1.0 + 0.5 + 0.0) / 3)
        assert agg["map_guidance_rate"] == pytest.approx(1/3)
        assert agg["read_range_guidance_rate"] == pytest.approx(1/3)
        assert agg["citation_policy_violations"] == 1
        assert agg["mean_latency_ms"] == pytest.approx(350/3)
        assert agg["max_latency_ms"] == 200
        assert agg["min_latency_ms"] == 50

    def test_aggregate_cases_empty(self):
        """Test empty cases returns zeros."""
        from vault.search_qa import _aggregate_cases
        agg = _aggregate_cases([])
        assert agg["total_cases"] == 0
        assert agg["top1_hits"] == 0
        assert agg["mean_reciprocal_rank"] == 0.0


class TestHitRank:
    def test_hit_rank_first_position(self):
        """Test finding hit at first position (1-indexed)."""
        from vault.search_qa import _hit_rank
        case = {"expected_ids": [1, 2]}
        results = [{"id": 1}, {"id": 3}, {"id": 4}]
        assert _hit_rank(case, results) == 1

    def test_hit_rank_later_position(self):
        """Test finding hit at later position."""
        from vault.search_qa import _hit_rank
        case = {"expected_ids": [5]}
        results = [{"id": 1}, {"id": 2}, {"id": 5}, {"id": 3}]
        assert _hit_rank(case, results) == 3

    def test_hit_rank_no_match(self):
        """Test no matching result returns None."""
        from vault.search_qa import _hit_rank
        case = {"expected_ids": [99]}
        results = [{"id": 1}, {"id": 2}, {"id": 3}]
        assert _hit_rank(case, results) is None

    def test_hit_rank_empty_results(self):
        """Test empty results returns None."""
        from vault.search_qa import _hit_rank
        case = {"expected_ids": [1]}
        assert _hit_rank(case, []) is None


class TestMatchesExpected:
    def test_matches_expected_by_id(self):
        """Test matching by id field."""
        from vault.search_qa import _matches_expected
        case = {"expected_ids": [42]}
        result = {"id": 42, "title": "Test"}
        assert _matches_expected(case, result) is True

    def test_matches_expected_no_match(self):
        """Test non-matching result."""
        from vault.search_qa import _matches_expected
        case = {"expected_ids": [42]}
        result = {"id": 99, "title": "Other"}
        assert _matches_expected(case, result) is False

    def test_matches_expected_multiple_expected(self):
        """Test matching against multiple expected ids."""
        from vault.search_qa import _matches_expected
        case = {"expected_ids": [1, 2, 3]}
        result = {"id": 2}
        assert _matches_expected(case, result) is True

    def test_matches_expected_string_id(self):
        """Test string id matching."""
        from vault.search_qa import _matches_expected
        case = {"expected_ids": ["abc", "def"]}
        result = {"id": "def"}
        assert _matches_expected(case, result) is True

    def test_matches_expected_title_match(self):
        """Test matching by title when expected_titles is present."""
        from vault.search_qa import _matches_expected
        case = {"expected_titles": ["Python Guide"]}
        result = {"id": 99, "title": "Python Guide"}
        assert _matches_expected(case, result) is True


class TestCitationPolicyViolations:
    def test_no_violations(self):
        """Test results with no citation violations."""
        from vault.search_qa import _citation_policy_violations
        results = [
            {"id": 1, "citation": "Doc1 L1-5"},
            {"id": 2, "citation": "Doc2 L10-15"},
        ]
        violations = _citation_policy_violations(results)
        assert isinstance(violations, list)

    def test_empty_results(self):
        """Test empty results returns empty list."""
        from vault.search_qa import _citation_policy_violations
        assert _citation_policy_violations([]) == []


class TestToolGuidanceHelpers:
    def test_has_map_guidance_in_next_action(self):
        """Test detecting map guidance in next_action."""
        from vault.search_qa import _has_map_guidance
        result = {"next_action": {"tool": "vault_map_show", "knowledge_id": 1}}
        assert _has_map_guidance(result) is True

    def test_has_map_guidance_in_next_actions_list(self):
        """Test detecting map guidance in next_actions list."""
        from vault.search_qa import _has_map_guidance
        result = {"next_actions": [
            {"tool": "vault_search"},
            {"tool": "vault_map_show", "knowledge_id": 1},
        ]}
        assert _has_map_guidance(result) is True

    def test_has_map_guidance_false(self):
        """Test no map guidance."""
        from vault.search_qa import _has_map_guidance
        result = {"next_action": {"tool": "vault_search"}}
        assert _has_map_guidance(result) is False

    def test_has_map_guidance_no_guide(self):
        """Test result without next_action/next_actions fields."""
        from vault.search_qa import _has_map_guidance
        result = {"id": 1, "title": "Test"}
        assert _has_map_guidance(result) is False

    def test_has_read_range_guidance_recommended_next_tool(self):
        """Test read range guidance via recommended_next_tool."""
        from vault.search_qa import _has_read_range_guidance
        result = {"recommended_next_tool": "vault_read_range"}
        assert _has_read_range_guidance(result) is True

    def test_has_read_range_guidance_in_next_action(self):
        """Test read range guidance via next_action."""
        from vault.search_qa import _has_read_range_guidance
        result = {"next_action": {"tool": "vault_read_range"}}
        assert _has_read_range_guidance(result) is True

    def test_has_read_range_guidance_false(self):
        """Test no read range guidance."""
        from vault.search_qa import _has_read_range_guidance
        result = {"next_action": {"tool": "vault_search"}}
        assert _has_read_range_guidance(result) is False

    def test_has_tool_guidance(self):
        """Test generic tool guidance detection."""
        from vault.search_qa import _has_tool_guidance
        result = {"next_action": {"tool": "my_tool"}}
        assert _has_tool_guidance(result, "my_tool") is True
        assert _has_tool_guidance(result, "other_tool") is False


class TestUtilityFunctions:
    def test_number_int(self):
        """Test _number with int."""
        from vault.search_qa import _number
        assert _number(42) == 42

    def test_number_float(self):
        """Test _number with float."""
        from vault.search_qa import _number
        assert _number(3.14) == pytest.approx(3.14)

    def test_number_string(self):
        """Test _number with numeric string."""
        from vault.search_qa import _number
        assert _number("100") == 100
        assert _number("3.5") == pytest.approx(3.5)

    def test_number_invalid(self):
        """Test _number with invalid string returns 0."""
        from vault.search_qa import _number
        assert _number("not a number") == 0
        assert _number(None) == 0

    def test_normalize_id(self):
        """Test _normalize_id converts to string."""
        from vault.search_qa import _normalize_id
        assert _normalize_id(42) == "42"
        assert _normalize_id("abc") == "abc"
        assert _normalize_id(None) == "None"

    def test_as_list(self):
        """Test _as_list function."""
        from vault.search_qa import _as_list
        assert _as_list([1, 2, 3]) == [1, 2, 3]
        assert _as_list("single") == ["single"]
        assert _as_list(None) == []
        assert _as_list(42) == [42]

    def test_append_once(self):
        """Test _append_once only adds if not present."""
        from vault.search_qa import _append_once
        lst = ["a", "b", "c"]
        _append_once(lst, "d")
        assert lst == ["a", "b", "c", "d"]
        _append_once(lst, "b")  # already exists
        assert lst == ["a", "b", "c", "d"]

    def test_jsonable_primitive(self):
        """Test _jsonable with primitives."""
        from vault.search_qa import _jsonable
        assert _jsonable(42) == 42
        assert _jsonable("hello") == "hello"
        assert _jsonable(None) is None

    def test_jsonable_dict(self):
        """Test _jsonable with dict."""
        from vault.search_qa import _jsonable
        d = {"a": 1, "b": [2, 3]}
        result = _jsonable(d)
        assert result == {"a": 1, "b": [2, 3]}

    def test_jsonable_list(self):
        """Test _jsonable with list."""
        from vault.search_qa import _jsonable
        lst = [1, "two", 3.0]
        result = _jsonable(lst)
        assert result == [1, "two", 3.0]

    def test_stable_delta_int(self):
        """Test _stable_delta with ints."""
        from vault.search_qa import _stable_delta
        assert _stable_delta(10, 5) == 5
        assert _stable_delta(5, 10) == -5
        assert _stable_delta(0, 0) == 0

    def test_stable_delta_float(self):
        """Test _stable_delta with floats."""
        from vault.search_qa import _stable_delta
        result = _stable_delta(0.75, 0.5)
        assert result == pytest.approx(0.25)

    def test_format_delta_positive(self):
        """Test _format_delta with positive delta."""
        from vault.search_qa import _format_delta
        assert _format_delta(5) == "+5"
        assert _format_delta(0.1) == "+0.1"

    def test_format_delta_negative(self):
        """Test _format_delta with negative delta."""
        from vault.search_qa import _format_delta
        assert _format_delta(-3) == "-3"

    def test_format_delta_zero(self):
        """Test _format_delta with zero delta."""
        from vault.search_qa import _format_delta
        assert _format_delta(0) == "0"


class TestWriteJson:
    def test_write_json_basic(self, tmp_path):
        """Test writing JSON to file."""
        from vault.search_qa import write_json
        out_file = tmp_path / "output.json"
        payload = {"key": "value", "number": 42}
        write_json(str(out_file), payload)
        
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert data["key"] == "value"
        assert data["number"] == 42


class TestFormatSearchQaSnapshot:
    def test_format_snapshot_basic(self):
        """Test formatting a QA snapshot produces string output."""
        from vault.search_qa import format_search_qa_snapshot
        snapshot = {
            "aggregate": {
                "total_cases": 10,
                "cases_with_results": 8,
                "top1_hits": 7,
                "topk_hits": 8,
                "mean_reciprocal_rank": 0.75,
            }
        }
        result = format_search_qa_snapshot(snapshot)
        assert isinstance(result, str)
        assert "total_cases" in result
        assert "10" in result
        assert "mean_reciprocal_rank" in result

    def test_format_snapshot_empty(self):
        """Test formatting empty snapshot."""
        from vault.search_qa import format_search_qa_snapshot
        result = format_search_qa_snapshot({})
        assert isinstance(result, str)


class TestSnapshotHelpers:
    def test_load_snapshot_dict(self):
        """Test _load_snapshot with dict input."""
        from vault.search_qa import _load_snapshot
        d = {"a": 1, "b": 2}
        result = _load_snapshot(d)
        assert result == d

    def test_load_snapshot_from_file(self, tmp_path):
        """Test _load_snapshot from file path."""
        from vault.search_qa import _load_snapshot
        f = tmp_path / "snap.json"
        f.write_text(json.dumps({"x": 100}))
        result = _load_snapshot(str(f))
        assert result["x"] == 100

    def test_snapshot_ref(self):
        """Test _snapshot_ref extracts reference info."""
        from vault.search_qa import _snapshot_ref
        snap = {
            "qa_file": "test_qa.json",
            "mode": "semantic",
            "limit": 20,
            "generated_at": "2024-01-01T00:00:00",
            "extra": "ignored",
        }
        ref = _snapshot_ref(snap)
        assert ref["qa_file"] == "test_qa.json"
        assert ref["mode"] == "semantic"
        assert ref["limit"] == 20
        assert ref["generated_at"] == "2024-01-01T00:00:00"
        assert "extra" not in ref

    def test_snapshot_ref_defaults(self):
        """Test _snapshot_ref with missing fields uses defaults."""
        from vault.search_qa import _snapshot_ref
        ref = _snapshot_ref({})
        assert ref["qa_file"] == ""
        assert ref["mode"] == ""
        assert ref["limit"] == 0
        assert ref["generated_at"] == ""
