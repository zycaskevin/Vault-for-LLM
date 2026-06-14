"""
Extended tests for vault/dream.py
Focus on pure utility functions.
"""
import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestNormalizeChecks:
    def test_normalize_checks_none(self):
        """Test None checks returns default checks."""
        from vault.dream import _normalize_checks
        result = _normalize_checks(None)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_normalize_checks_empty_string(self):
        """Test empty string returns defaults."""
        from vault.dream import _normalize_checks
        result = _normalize_checks("")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_normalize_checks_single_string(self):
        """Test single check string."""
        from vault.dream import _normalize_checks
        result = _normalize_checks("freshness")
        assert result == ["freshness"]

    def test_normalize_checks_comma_separated(self):
        """Test comma-separated check string."""
        from vault.dream import _normalize_checks
        result = _normalize_checks("freshness, dedup, metadata")
        assert "freshness" in result
        assert "dedup" in result
        assert "metadata" in result
        assert len(result) == 3

    def test_normalize_checks_list(self):
        """Test list of checks."""
        from vault.dream import _normalize_checks
        result = _normalize_checks(["freshness", "dedup"])
        assert result == ["freshness", "dedup"]

    def test_normalize_checks_invalid_ignored(self):
        """Test invalid check names are ignored."""
        from vault.dream import _normalize_checks
        result = _normalize_checks("freshness, invalid_check, dedup")
        assert "freshness" in result
        assert "dedup" in result
        assert "invalid_check" not in result

    def test_normalize_checks_all_invalid_returns_default(self):
        """Test all invalid checks returns defaults."""
        from vault.dream import _normalize_checks
        result = _normalize_checks("invalid1, invalid2")
        assert isinstance(result, list)
        assert len(result) > 0  # falls back to defaults

    def test_normalize_checks_duplicates_removed(self):
        """Test duplicate checks are removed."""
        from vault.dream import _normalize_checks
        result = _normalize_checks("freshness, dedup, freshness")
        assert result.count("freshness") == 1
        assert "dedup" in result


class TestLimitRows:
    def test_limit_rows_positive(self):
        """Test positive limit returns first N rows."""
        from vault.dream import _limit_rows
        rows = [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}, {"id": 5}]
        result = _limit_rows(rows, 3)
        assert len(result) == 3
        assert result[0]["id"] == 1
        assert result[2]["id"] == 3

    def test_limit_rows_zero(self):
        """Test limit=0 returns all rows."""
        from vault.dream import _limit_rows
        rows = [{"id": 1}, {"id": 2}, {"id": 3}]
        result = _limit_rows(rows, 0)
        assert len(result) == 3

    def test_limit_rows_negative(self):
        """Test negative limit returns all rows."""
        from vault.dream import _limit_rows
        rows = [{"id": 1}, {"id": 2}]
        result = _limit_rows(rows, -1)
        assert len(result) == 2

    def test_limit_rows_larger_than_list(self):
        """Test limit larger than list size returns all."""
        from vault.dream import _limit_rows
        rows = [{"id": 1}, {"id": 2}]
        result = _limit_rows(rows, 100)
        assert len(result) == 2

    def test_limit_rows_empty(self):
        """Test empty list returns empty."""
        from vault.dream import _limit_rows
        assert _limit_rows([], 5) == []


class TestBuildDreamReport:
    def test_build_dream_report_basic(self):
        """Test basic dream report generation."""
        from vault.dream import build_dream_report
        payload = {
            "generated_at": "2024-01-01T00:00:00",
            "mode": "dry_run",
            "checks": ["freshness", "dedup"],
            "summary": {
                "stale": 5,
                "duplicates": 3,
                "weak": 2,
                "metadata": 8,
                "orphans": 1,
                "actions_applied": 0,
            },
            "findings": {
                "freshness": [{"id": 1, "title": "Old doc"}],
                "dedup": [{"type": "title", "key": "test", "items": [{"id": 1}, {"id": 2}]}],
                "convergence": [],
                "metadata": [{"id": 3, "issues": ["missing_tags"]}],
                "orphans": [],
            },
            "proposed_actions": [],
            "applied_actions": [],
        }
        result = build_dream_report(payload)
        assert isinstance(result, str)
        assert "# Vault Dream Report" in result
        assert "freshness" in result
        assert "dedup" in result
        assert "stale: 5" in result
        assert "duplicates: 3" in result
        assert "Count: 1" in result  # freshness count

    def test_build_dream_report_many_findings_truncated(self):
        """Test that findings are truncated to 20 items per section."""
        from vault.dream import build_dream_report
        many_findings = [{"id": i, "title": f"Doc {i}"} for i in range(30)]
        payload = {
            "generated_at": "2024-01-01T00:00:00",
            "mode": "dry_run",
            "checks": ["freshness"],
            "summary": {
                "stale": 30, "duplicates": 0, "weak": 0,
                "metadata": 0, "orphans": 0, "actions_applied": 0,
            },
            "findings": {
                "freshness": many_findings,
                "dedup": [], "convergence": [], "metadata": [], "orphans": [],
            },
            "proposed_actions": [],
            "applied_actions": [],
        }
        result = build_dream_report(payload)
        # Should have at most 20 items listed in Freshness section
        lines = result.split("\n")
        freshness_start = None
        for i, line in enumerate(lines):
            if line == "## Freshness":
                freshness_start = i
                break
        
        bullet_count = 0
        if freshness_start:
            for line in lines[freshness_start:]:
                if line.startswith("## ") and line != "## Freshness":
                    break
                if line.startswith("- "):
                    bullet_count += 1
        
        assert bullet_count <= 20


class TestBuildSafeActions:
    def test_build_safe_actions_empty(self):
        """Test empty findings return empty actions."""
        from vault.dream import _build_safe_actions
        result = _build_safe_actions({})
        assert result == []

    def test_build_safe_actions_no_metadata(self):
        """Test findings without metadata section returns empty."""
        from vault.dream import _build_safe_actions
        findings = {"freshness": [{"id": 1}]}
        result = _build_safe_actions(findings)
        assert result == []

    def test_build_safe_actions_missing_tags(self):
        """Test missing_tags issue generates set_tags action."""
        from vault.dream import _build_safe_actions
        findings = {
            "metadata": [
                {"id": 42, "issues": ["missing_tags"]},
            ]
        }
        actions = _build_safe_actions(findings)
        assert len(actions) == 1
        assert actions[0]["type"] == "set_tags"
        assert actions[0]["knowledge_id"] == 42
        assert actions[0]["value"] == "needs-review"

    def test_build_safe_actions_weak_category(self):
        """Test weak_category issue generates set_category action."""
        from vault.dream import _build_safe_actions
        findings = {
            "metadata": [
                {"id": 10, "issues": ["weak_category"]},
            ]
        }
        actions = _build_safe_actions(findings)
        assert len(actions) == 1
        assert actions[0]["type"] == "set_category"
        assert actions[0]["value"] == "review"

    def test_build_safe_actions_multiple_issues(self):
        """Test multiple issues generate multiple actions."""
        from vault.dream import _build_safe_actions
        findings = {
            "metadata": [
                {"id": 1, "issues": ["missing_tags", "weak_category"]},
            ]
        }
        actions = _build_safe_actions(findings)
        assert len(actions) == 2
        action_types = {a["type"] for a in actions}
        assert action_types == {"set_tags", "set_category"}

    def test_build_safe_actions_skip_invalid_id(self):
        """Test items with invalid id (<= 0) are skipped."""
        from vault.dream import _build_safe_actions
        findings = {
            "metadata": [
                {"id": 0, "issues": ["missing_tags"]},
                {"id": -1, "issues": ["missing_tags"]},
                {"id": None, "issues": ["missing_tags"]},
            ]
        }
        actions = _build_safe_actions(findings)
        assert len(actions) == 0

    def test_build_safe_actions_multiple_items(self):
        """Test multiple metadata items generate multiple actions."""
        from vault.dream import _build_safe_actions
        findings = {
            "metadata": [
                {"id": 1, "issues": ["missing_tags"]},
                {"id": 2, "issues": ["weak_category"]},
                {"id": 3, "issues": ["missing_tags", "weak_category"]},
            ]
        }
        actions = _build_safe_actions(findings)
        assert len(actions) == 4  # 1 + 1 + 2

    def test_build_safe_actions_dedup(self):
        """Test duplicate (type, id) pairs are deduplicated."""
        from vault.dream import _build_safe_actions
        # Two items with same id and same issue type should only produce one action
        findings = {
            "metadata": [
                {"id": 1, "issues": ["missing_tags"]},
                {"id": 1, "issues": ["missing_tags"]},  # duplicate
            ]
        }
        actions = _build_safe_actions(findings)
        assert len(actions) == 1  # deduplicated


class TestDbFindings:
    """Test database-backed finding functions with mock DB."""

    def test_dedup_findings_with_duplicates(self):
        """Test _dedup_findings detects duplicate titles and hashes."""
        from vault.dream import _dedup_findings
        mock_db = MagicMock()
        mock_db.conn.execute.return_value.fetchall.return_value = [
            {"id": 1, "title": "Python Guide", "content_hash": "abc123"},
            {"id": 2, "title": "Python Guide", "content_hash": "def456"},  # same title
            {"id": 3, "title": "Rust Guide", "content_hash": "ghi789"},
            {"id": 4, "title": "Go Guide", "content_hash": "abc123"},  # same hash
        ]
        findings = _dedup_findings(mock_db, 10)
        assert isinstance(findings, list)
        # Should find at least title duplicates and hash duplicates
        assert len(findings) >= 1
        types_found = {f["type"] for f in findings}
        assert "title" in types_found
        assert "content_hash" in types_found

    def test_dedup_findings_no_duplicates(self):
        """Test _dedup_findings with no duplicates."""
        from vault.dream import _dedup_findings
        mock_db = MagicMock()
        mock_db.conn.execute.return_value.fetchall.return_value = [
            {"id": 1, "title": "Python", "content_hash": "a"},
            {"id": 2, "title": "Rust", "content_hash": "b"},
            {"id": 3, "title": "Go", "content_hash": "c"},
        ]
        findings = _dedup_findings(mock_db, 10)
        assert len(findings) == 0

    def test_dedup_findings_limit(self):
        """Test _dedup_findings respects limit."""
        from vault.dream import _dedup_findings
        mock_db = MagicMock()
        rows = []
        for i in range(10):
            rows.append({"id": i*2, "title": f"Doc {i}", "content_hash": f"hash{i}"})
            rows.append({"id": i*2+1, "title": f"Doc {i}", "content_hash": f"hash{i}_dup"})
        mock_db.conn.execute.return_value.fetchall.return_value = rows
        
        findings = _dedup_findings(mock_db, 3)
        assert len(findings) == 3

    def test_freshness_findings(self):
        """Test _freshness_findings with mock DB."""
        from vault.dream import _freshness_findings
        mock_db = MagicMock()
        mock_db.conn.execute.return_value.fetchall.return_value = [
            {"id": 1, "title": "Old", "freshness": 0.3, "last_verified": "", "updated_at": "2023-01-01"},
            {"id": 2, "title": "New", "freshness": 0.9, "last_verified": "2024-01-01", "updated_at": "2024-01-01"},
        ]
        findings = _freshness_findings(mock_db, 10)
        assert isinstance(findings, list)
        # Should only return stale ones (freshness < 0.5 or empty last_verified)

    def test_convergence_findings(self):
        """Test _convergence_findings with mock DB."""
        from vault.dream import _convergence_findings
        mock_db = MagicMock()
        mock_db.conn.execute.return_value.fetchall.return_value = [
            {"id": 1, "title": "Weak", "convergence_status": "weak", "convergence_score": 0.3, "trust": 0.5},
        ]
        findings = _convergence_findings(mock_db, 10)
        assert isinstance(findings, list)
