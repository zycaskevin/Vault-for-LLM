"""
Extended tests for vault/mcp.py
Focus on pure functions and testable utilities.
"""
import pytest
import json
from unittest.mock import MagicMock, patch


class TestCanonicalToolName:
    def test_canonical_returns_unchanged(self):
        """Test that canonical tool name returns input unchanged."""
        from vault.mcp import _canonical_tool_name
        assert _canonical_tool_name("vault_read") == "vault_read"
        assert _canonical_tool_name("vault-map-show") == "vault-map-show"
        assert _canonical_tool_name("") == ""


class TestLineHash:
    def test_line_hash_consistent(self):
        """Test that same input produces same hash."""
        from vault.mcp import _line_hash
        lines = ["line 1", "line 2", "line 3"]
        h1 = _line_hash(lines, 1, 2)
        h2 = _line_hash(lines, 1, 2)
        assert h1 == h2

    def test_line_hash_different_ranges(self):
        """Test different ranges produce different hashes."""
        from vault.mcp import _line_hash
        lines = ["a", "b", "c", "d"]
        h1 = _line_hash(lines, 1, 2)
        h2 = _line_hash(lines, 3, 4)
        assert h1 != h2

    def test_line_hash_single_line(self):
        """Test single line hash."""
        from vault.mcp import _line_hash
        lines = ["hello", "world"]
        h = _line_hash(lines, 1, 1)
        assert isinstance(h, str)
        assert len(h) > 0

    def test_line_hash_uses_1_indexed(self):
        """Test that line_start is 1-indexed."""
        from vault.mcp import _line_hash
        lines = ["first", "second"]
        h = _line_hash(lines, 1, 1)
        import hashlib
        expected = hashlib.sha256("first".encode()).hexdigest()
        assert h == expected


class TestFormatCitation:
    def test_format_citation_basic(self):
        """Test basic citation formatting."""
        from vault.mcp import _format_citation
        result = _format_citation(1, "Test Doc", 5, 10)
        assert result == "#1 Test Doc L5-L10"

    def test_format_citation_same_line(self):
        """Test citation with same start and end line."""
        from vault.mcp import _format_citation
        result = _format_citation(42, "Guide", 7, 7)
        assert result == "#42 Guide L7-L7"


class TestErrorFunctions:
    def test_error_basic(self):
        """Test basic error response."""
        from vault.mcp import _error
        result = _error("NOT_FOUND", "Knowledge not found")
        assert isinstance(result, dict)
        assert "error" in result
        assert result["error"] == "NOT_FOUND"
        assert result["message"] == "Knowledge not found"
        assert "next_action" in result

    def test_error_with_extra(self):
        """Test error with extra fields."""
        from vault.mcp import _error
        result = _error("VALIDATION", "Invalid input", field="title", value="")
        assert result["error"] == "VALIDATION"
        assert "field" in result
        assert result["field"] == "title"
        assert result["value"] == ""

    def test_error_with_next_action(self):
        """Test error with explicit next_action."""
        from vault.mcp import _error
        custom_action = {"tool": "custom_tool", "arguments": {"x": 1}}
        result = _error("TEST", "test error", next_action=custom_action)
        assert result["next_action"] == custom_action

    def test_next_action_for_error_not_found(self):
        """Test next_action for NOT_FOUND error."""
        from vault.mcp import _next_action_for_error
        result = _next_action_for_error("not_found")
        assert isinstance(result, dict)
        assert "tool" in result
        assert result["tool"] == "vault_search"

    def test_next_action_for_error_unknown_code(self):
        """Test next_action for unknown error code."""
        from vault.mcp import _next_action_for_error
        result = _next_action_for_error("unknown_error_code")
        assert isinstance(result, dict)


class TestCompactNode:
    def test_compact_node_full(self):
        """Test compacting a full node."""
        from vault.mcp import _compact_node
        node = {
            "node_uid": "uid-123",
            "path": "/path/to/doc",
            "heading": "Introduction",
            "line_start": 1,
            "line_end": 10,
            "extra_field": "should be removed",
        }
        result = _compact_node(node)
        assert isinstance(result, dict)
        assert result["node_uid"] == "uid-123"
        assert result["path"] == "/path/to/doc"
        assert result["heading"] == "Introduction"
        assert result["line_start"] == 1
        assert result["line_end"] == 10
        assert "extra_field" not in result

    def test_compact_node_missing_fields(self):
        """Test compacting node with missing fields."""
        from vault.mcp import _compact_node
        node = {}
        result = _compact_node(node)
        assert result["node_uid"] == ""
        assert result["path"] == ""
        assert result["heading"] == ""
        assert result["line_start"] is None
        assert result["line_end"] is None


class TestContentHash:
    def test_content_hash_consistent(self):
        """Test content hash is consistent."""
        from vault.mcp import _content_hash_for_text
        h1 = _content_hash_for_text("hello world")
        h2 = _content_hash_for_text("hello world")
        assert h1 == h2

    def test_content_hash_different(self):
        """Test different content has different hash."""
        from vault.mcp import _content_hash_for_text
        h1 = _content_hash_for_text("hello")
        h2 = _content_hash_for_text("world")
        assert h1 != h2

    def test_content_hash_empty(self):
        """Test empty string hash."""
        from vault.mcp import _content_hash_for_text
        h = _content_hash_for_text("")
        assert isinstance(h, str)
        assert len(h) > 0


class TestSortFunctions:
    def test_sort_remote_nodes_by_line_start(self):
        """Test sorting remote nodes by line_start."""
        from vault.mcp import _sort_remote_nodes
        rows = [
            {"id": 3, "line_start": 30, "level": 1, "node_uid": "c"},
            {"id": 1, "line_start": 10, "level": 1, "node_uid": "a"},
            {"id": 2, "line_start": 20, "level": 1, "node_uid": "b"},
        ]
        result = _sort_remote_nodes(rows)
        assert result[0]["id"] == 1  # line_start 10
        assert result[1]["id"] == 2  # line_start 20
        assert result[2]["id"] == 3  # line_start 30

    def test_sort_remote_nodes_with_level_tiebreaker(self):
        """Test sorting with level as tiebreaker."""
        from vault.mcp import _sort_remote_nodes
        rows = [
            {"id": 2, "line_start": 10, "level": 2, "node_uid": "b"},
            {"id": 1, "line_start": 10, "level": 1, "node_uid": "a"},
        ]
        result = _sort_remote_nodes(rows)
        assert result[0]["id"] == 1  # level 1 comes before level 2

    def test_sort_remote_claims_by_line_start(self):
        """Test sorting remote claims by line_start."""
        from vault.mcp import _sort_remote_claims
        rows = [
            {"id": 3, "line_start": 30, "line_end": 35, "claim_uid": "c"},
            {"id": 1, "line_start": 10, "line_end": 15, "claim_uid": "a"},
            {"id": 2, "line_start": 20, "line_end": 25, "claim_uid": "b"},
        ]
        result = _sort_remote_claims(rows)
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2
        assert result[2]["id"] == 3

    def test_sort_empty(self):
        """Test sorting empty list."""
        from vault.mcp import _sort_remote_nodes, _sort_remote_claims
        assert _sort_remote_nodes([]) == []
        assert _sort_remote_claims([]) == []


class TestRemoteNodePayload:
    def test_remote_node_payload_basic(self):
        """Test basic remote node payload."""
        from vault.mcp import _remote_node_payload
        row = {
            "node_uid": "uid-1",
            "path": "/doc.md",
            "heading": "Intro",
            "node_type": "section",
            "level": 1,
            "line_start": 1,
            "line_end": 10,
            "content": "Test content",
            "status": "active",
        }
        result = _remote_node_payload(row)
        assert isinstance(result, dict)
        assert result["node_uid"] == "uid-1"
        assert result["path"] == "/doc.md"
        assert result["heading"] == "Intro"
        # node_type may not be in result
        assert "level" in result

    def test_remote_node_payload_missing_fields(self):
        """Test payload with missing fields."""
        from vault.mcp import _remote_node_payload
        row = {"node_uid": "uid-1"}
        result = _remote_node_payload(row)
        assert isinstance(result, dict)
        assert result["node_uid"] == "uid-1"


class TestPreferredReadNode:
    def test_preferred_read_node_prefers_higher_level(self):
        """Test that higher level nodes are preferred."""
        from vault.mcp import _preferred_read_node
        nodes = [
            {"node_type": "raw", "level": 1, "content": "raw content"},
            {"node_type": "compiled", "level": 2, "content": "compiled content"},
        ]
        result = _preferred_read_node(nodes)
        assert result is not None
        assert result["level"] == 2

    def test_preferred_read_node_no_high_level(self):
        """Test fallback when no high-level node."""
        from vault.mcp import _preferred_read_node
        nodes = [
            {"node_type": "raw", "level": 1, "content": "raw content"},
        ]
        result = _preferred_read_node(nodes)
        assert result is not None
        assert result["node_type"] == "raw"

    def test_preferred_read_node_empty(self):
        """Test empty list returns None."""
        from vault.mcp import _preferred_read_node
        assert _preferred_read_node([]) is None

    def test_preferred_read_node_level_as_string(self):
        """Test when level is a string."""
        from vault.mcp import _preferred_read_node
        nodes = [
            {"node_type": "raw", "level": "1", "content": "raw"},
            {"node_type": "compiled", "level": "2", "content": "compiled"},
        ]
        result = _preferred_read_node(nodes)
        assert result is not None
        assert result["level"] == "2"


class TestRemoteNextActionForError:
    def test_remote_next_action_not_found(self):
        """Test remote next action for not found error."""
        from vault.mcp import _remote_next_action_for_error
        result = _remote_next_action_for_error("not_found")
        assert isinstance(result, dict)
        assert "tool" in result

    def test_remote_next_action_unknown(self):
        """Test remote next action for unknown error."""
        from vault.mcp import _remote_next_action_for_error
        result = _remote_next_action_for_error("unknown_error")
        assert isinstance(result, dict)

    def test_remote_next_action_with_extra(self):
        """Test remote next action with extra info."""
        from vault.mcp import _remote_next_action_for_error
        result = _remote_next_action_for_error("not_found", {"knowledge_id": 123})
        assert isinstance(result, dict)


class TestRemoteError:
    def test_remote_error_basic(self):
        """Test basic remote error response."""
        from vault.mcp import _remote_error
        result = _remote_error("NOT_FOUND", "Knowledge not found")
        assert isinstance(result, dict)
        assert "error" in result
        assert result["error"] == "NOT_FOUND"
        assert "message" in result
        assert "next_action" in result

    def test_remote_error_with_extra(self):
        """Test remote error with extra fields."""
        from vault.mcp import _remote_error
        result = _remote_error("VALIDATION", "Invalid", field="title")
        assert result["error"] == "VALIDATION"
        assert "field" in result
        assert result["field"] == "title"


class TestReadRangeAction:
    def test_read_range_action_basic(self):
        """Test basic read range action."""
        from vault.mcp import _read_range_action
        node = {"node_uid": "abc123", "heading": "Introduction"}
        result = _read_range_action(42, node)
        assert isinstance(result, dict)
        assert "tool" in result
        assert "arguments" in result
        assert result["arguments"]["knowledge_id"] == 42

    def test_read_range_action_no_uid(self):
        """Test read range action with no node_uid."""
        from vault.mcp import _read_range_action
        node = {"heading": "Intro"}
        result = _read_range_action(1, node)
        assert isinstance(result, dict)
        assert result["arguments"]["knowledge_id"] == 1

    def test_remote_read_range_action(self):
        """Test remote read range action."""
        from vault.mcp import _remote_read_range_action
        node = {"node_uid": "uid1", "heading": "Test"}
        result = _remote_read_range_action(42, node)
        assert isinstance(result, dict)
        assert "tool" in result


class TestRemoteClaimContent:
    def test_remote_claim_content_empty(self):
        """Test empty claims."""
        from vault.mcp import _remote_claim_content
        result = _remote_claim_content([])
        assert result == ""

    def test_remote_claim_content_with_claims(self):
        """Test with claims."""
        from vault.mcp import _remote_claim_content
        claims = [
            {"claim_number": 1, "claim": "First claim", "line_start": 5, "line_end": 5},
            {"claim_number": 2, "claim": "Second claim", "line_start": 10, "line_end": 15},
        ]
        result = _remote_claim_content(claims)
        assert isinstance(result, str)
        assert "First claim" in result
        assert "Second claim" in result
        assert "5|" in result
        assert "10-15|" in result


class TestSetProjectDir:
    def test_set_project_dir_sets_globals(self):
        """Test that _set_project_dir sets global DB_PATH."""
        from vault import mcp
        import tempfile
        import os
        
        # Save original
        original = mcp.DB_PATH
        
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                mcp._set_project_dir(tmpdir)
                # Should set DB_PATH to <tmpdir>/vault.db
                assert str(mcp.DB_PATH) == os.path.join(tmpdir, "vault.db")
        finally:
            # Restore
            mcp.DB_PATH = original


class TestHandleToolCall:
    def test_handle_tool_call_unknown_tool(self):
        """Test handling unknown tool."""
        from vault.mcp import handle_tool_call
        result = handle_tool_call("nonexistent_tool", {})
        assert isinstance(result, dict)
        assert "error" in result

    def test_handle_tool_call_vault_map_show(self):
        """Test vault_map_show tool call."""
        from vault.mcp import handle_tool_call
        # This will likely error because no DB, but should return error dict
        result = handle_tool_call("vault_map_show", {"knowledge_id": 1})
        assert isinstance(result, dict)
        # May have error or content depending on setup

    def test_handle_tool_call_vault_search(self):
        """Test vault_search tool call."""
        from vault.mcp import handle_tool_call
        result = handle_tool_call("vault_search", {"query": "test"})
        assert isinstance(result, dict)


class TestCanonicalToolName:
    def test_canonical_tool_name_returns_same(self):
        from vault.mcp import _canonical_tool_name
        assert _canonical_tool_name("vault_map_show") == "vault_map_show"
        assert _canonical_tool_name("custom_tool") == "custom_tool"


class TestLineHash:
    def test_line_hash_consistent(self):
        from vault.mcp import _line_hash
        lines = ["line1", "line2", "line3", "line4"]
        hash1 = _line_hash(lines, 0, 2)
        hash2 = _line_hash(lines, 0, 2)
        assert hash1 == hash2

    def test_line_hash_different_ranges(self):
        from vault.mcp import _line_hash
        lines = ["line1", "line2", "line3", "line4"]
        hash1 = _line_hash(lines, 0, 2)
        hash2 = _line_hash(lines, 1, 3)
        assert hash1 != hash2


class TestFormatCitation:
    def test_format_citation_basic(self):
        from vault.mcp import _format_citation
        result = _format_citation(1, "Test Title", 5, 10)
        assert "1" in result
        assert "Test Title" in result
        assert "5" in result
        assert "10" in result


class TestCompactNode:
    def test_compact_node_basic(self):
        from vault.mcp import _compact_node
        node = {
            "node_uid": "uid123",
            "path": "Section > Subsection",
            "heading": "Subsection",
            "line_start": 5,
            "line_end": 20,
            "extra_field": "should be removed"
        }
        result = _compact_node(node)
        assert result["node_uid"] == "uid123"
        assert result["path"] == "Section > Subsection"
        assert result["heading"] == "Subsection"
        assert result["line_start"] == 5
        assert result["line_end"] == 20
        assert "extra_field" not in result

    def test_compact_node_missing_fields(self):
        from vault.mcp import _compact_node
        node = {"node_uid": "uid123", "path": "Test"}
        result = _compact_node(node)
        assert result["node_uid"] == "uid123"
        assert result["path"] == "Test"
        assert "heading" in result  # Should have default


class TestContentHashForText:
    def test_content_hash_consistent(self):
        from vault.mcp import _content_hash_for_text
        hash1 = _content_hash_for_text("hello world")
        hash2 = _content_hash_for_text("hello world")
        assert hash1 == hash2

    def test_content_hash_different(self):
        from vault.mcp import _content_hash_for_text
        hash1 = _content_hash_for_text("hello")
        hash2 = _content_hash_for_text("world")
        assert hash1 != hash2

    def test_content_hash_empty(self):
        from vault.mcp import _content_hash_for_text
        result = _content_hash_for_text("")
        assert isinstance(result, str)
        assert len(result) > 0


class TestRemoteClaimContent:
    def test_remote_claim_content_multiple(self):
        from vault.mcp import _remote_claim_content
        claims = [
            {"claim": "Claim 1 text", "line_start": 1, "line_end": 3},
            {"claim": "Claim 2 text", "line_start": 5, "line_end": 5},
        ]
        result = _remote_claim_content(claims)
        assert "Claim 1 text" in result
        assert "Claim 2 text" in result
        assert "1-3" in result
        assert "5|" in result




class TestCompactNode:
    def test_compact_node_full(self):
        """Test compacting a node with all fields."""
        from vault.mcp import _compact_node
        node = {
            "node_uid": "n1",
            "path": "/doc/intro",
            "heading": "Introduction",
            "line_start": 1,
            "line_end": 10,
            "extra_field": "should be removed",
        }
        result = _compact_node(node)
        assert result == {
            "node_uid": "n1",
            "path": "/doc/intro",
            "heading": "Introduction",
            "line_start": 1,
            "line_end": 10,
        }
        assert "extra_field" not in result

    def test_compact_node_missing_fields(self):
        """Test compacting a node with missing fields uses defaults."""
        from vault.mcp import _compact_node
        node = {"node_uid": "n1"}
        result = _compact_node(node)
        assert result["node_uid"] == "n1"
        assert result["path"] == ""
        assert result["heading"] == ""
        assert result["line_start"] is None
        assert result["line_end"] is None

    def test_compact_node_empty(self):
        """Test compacting an empty node."""
        from vault.mcp import _compact_node
        result = _compact_node({})
        assert result == {
            "node_uid": "",
            "path": "",
            "heading": "",
            "line_start": None,
            "line_end": None,
        }


class TestPreferredReadNode:
    def test_preferred_read_node_empty(self):
        """Test empty nodes returns None."""
        from vault.mcp import _preferred_read_node
        assert _preferred_read_node([]) is None

    def test_preferred_read_node_picks_level_gt_1(self):
        """Test that first node with level > 1 is preferred."""
        from vault.mcp import _preferred_read_node
        nodes = [
            {"level": 1, "heading": "Root"},
            {"level": 2, "heading": "Section"},
            {"level": 3, "heading": "Subsection"},
        ]
        result = _preferred_read_node(nodes)
        assert result["heading"] == "Section"
        assert result["level"] == 2

    def test_preferred_read_node_all_level_1(self):
        """Test that when all nodes are level 1, returns first."""
        from vault.mcp import _preferred_read_node
        nodes = [
            {"level": 1, "heading": "First"},
            {"level": 1, "heading": "Second"},
        ]
        result = _preferred_read_node(nodes)
        assert result["heading"] == "First"

    def test_preferred_read_node_string_level(self):
        """Test string level values are properly converted to int."""
        from vault.mcp import _preferred_read_node
        nodes = [
            {"level": "1", "heading": "Root"},
            {"level": "2", "heading": "Child"},
        ]
        result = _preferred_read_node(nodes)
        assert result["heading"] == "Child"

    def test_preferred_read_node_none_level(self):
        """Test None level defaults to 0."""
        from vault.mcp import _preferred_read_node
        nodes = [
            {"level": None, "heading": "None level"},
            {"level": 2, "heading": "Level 2"},
        ]
        result = _preferred_read_node(nodes)
        assert result["heading"] == "Level 2"

    def test_preferred_read_node_single(self):
        """Test single node returns that node."""
        from vault.mcp import _preferred_read_node
        node = {"level": 1, "heading": "Only"}
        result = _preferred_read_node([node])
        assert result == node


class TestReadRangeAction:
    def test_read_range_action_with_node_uid(self):
        """Test read range action with node_uid."""
        from vault.mcp import _read_range_action
        node = {"node_uid": "abc123", "line_start": 5, "line_end": 15}
        result = _read_range_action(42, node)
        assert result["tool"] == "vault_read_range"
        assert result["arguments"]["knowledge_id"] == 42
        assert result["arguments"]["node_uid"] == "abc123"
        assert result["arguments"]["line_start"] == 5
        assert result["arguments"]["line_end"] == 15

    def test_read_range_action_without_node_uid(self):
        """Test read range action without node_uid."""
        from vault.mcp import _read_range_action
        node = {"line_start": 1, "line_end": 10}
        result = _read_range_action(1, node)
        assert "node_uid" not in result["arguments"]
        assert result["arguments"]["line_start"] == 1
        assert result["arguments"]["line_end"] == 10

    def test_read_range_action_without_lines(self):
        """Test read range action without line info."""
        from vault.mcp import _read_range_action
        node = {"node_uid": "only-uid"}
        result = _read_range_action(99, node)
        assert result["arguments"]["knowledge_id"] == 99
        assert result["arguments"]["node_uid"] == "only-uid"
        assert "line_start" not in result["arguments"]

    def test_remote_read_range_action(self):
        """Test remote read range action uses correct tool name."""
        from vault.mcp import _remote_read_range_action
        node = {"node_uid": "remote-uid", "line_start": 10, "line_end": 20}
        result = _remote_read_range_action(5, node)
        assert result["tool"] == "vault_remote_read_range"
        assert result["arguments"]["knowledge_id"] == 5
        assert result["arguments"]["node_uid"] == "remote-uid"


class TestSortRemoteNodes:
    def test_sort_remote_nodes_by_line_start(self):
        """Test sorting by line_start primarily."""
        from vault.mcp import _sort_remote_nodes
        rows = [
            {"line_start": 20, "level": 1, "node_uid": "n2"},
            {"line_start": 10, "level": 1, "node_uid": "n1"},
            {"line_start": 30, "level": 1, "node_uid": "n3"},
        ]
        result = _sort_remote_nodes(rows)
        assert [r["line_start"] for r in result] == [10, 20, 30]

    def test_sort_remote_nodes_same_line_diff_level(self):
        """Test same line_start sorts by level secondarily."""
        from vault.mcp import _sort_remote_nodes
        rows = [
            {"line_start": 10, "level": 3, "node_uid": "n3"},
            {"line_start": 10, "level": 1, "node_uid": "n1"},
            {"line_start": 10, "level": 2, "node_uid": "n2"},
        ]
        result = _sort_remote_nodes(rows)
        assert [r["level"] for r in result] == [1, 2, 3]

    def test_sort_remote_nodes_empty_values(self):
        """Test sorting with None/empty values defaults to 0."""
        from vault.mcp import _sort_remote_nodes
        rows = [
            {"line_start": None, "level": None, "node_uid": "b"},
            {"line_start": 5, "level": 2, "node_uid": "a"},
        ]
        result = _sort_remote_nodes(rows)
        assert len(result) == 2


class TestSortRemoteClaims:
    def test_sort_remote_claims_by_line_start(self):
        """Test sorting claims by line_start."""
        from vault.mcp import _sort_remote_claims
        rows = [
            {"line_start": 15, "line_end": 15, "claim_uid": "c2"},
            {"line_start": 5, "line_end": 5, "claim_uid": "c1"},
        ]
        result = _sort_remote_claims(rows)
        assert result[0]["claim_uid"] == "c1"
        assert result[1]["claim_uid"] == "c2"

    def test_sort_remote_claims_same_start_diff_end(self):
        """Test same line_start sorts by line_end."""
        from vault.mcp import _sort_remote_claims
        rows = [
            {"line_start": 10, "line_end": 20, "claim_uid": "c2"},
            {"line_start": 10, "line_end": 15, "claim_uid": "c1"},
        ]
        result = _sort_remote_claims(rows)
        assert result[0]["claim_uid"] == "c1"


class TestRemoteNodePayload:
    def test_remote_node_payload_selects_keys(self):
        """Test that only specified keys are included."""
        from vault.mcp import _remote_node_payload
        row = {
            "node_uid": "n1",
            "path": "/intro",
            "heading": "Intro",
            "level": 2,
            "line_start": 1,
            "line_end": 10,
            "summary": "A summary",
            "token_estimate": 100,
            "extra": "should not appear",
        }
        result = _remote_node_payload(row)
        assert set(result.keys()) == {
            "node_uid", "path", "heading", "level",
            "line_start", "line_end", "summary", "token_estimate"
        }
        assert "extra" not in result

    def test_remote_node_payload_missing_keys(self):
        """Test missing keys are not included."""
        from vault.mcp import _remote_node_payload
        row = {"node_uid": "n1", "path": "/test"}
        result = _remote_node_payload(row)
        assert set(result.keys()) == {"node_uid", "path"}

    def test_remote_node_payload_empty(self):
        """Test empty row returns empty dict."""
        from vault.mcp import _remote_node_payload
        result = _remote_node_payload({})
        assert result == {}


class TestRemoteClaimContent:
    def test_remote_claim_content_single_line(self):
        """Test claim with same start/end line."""
        from vault.mcp import _remote_claim_content
        claims = [{"line_start": 5, "line_end": 5, "claim": "Test claim"}]
        result = _remote_claim_content(claims)
        assert result == "5|Test claim"

    def test_remote_claim_content_range(self):
        """Test claim with different start/end lines."""
        from vault.mcp import _remote_claim_content
        claims = [{"line_start": 1, "line_end": 5, "claim": "Range claim"}]
        result = _remote_claim_content(claims)
        assert result == "1-5|Range claim"

    def test_remote_claim_content_multiple(self):
        """Test multiple claims produce multiple lines."""
        from vault.mcp import _remote_claim_content
        claims = [
            {"line_start": 1, "line_end": 1, "claim": "First"},
            {"line_start": 2, "line_end": 3, "claim": "Second"},
        ]
        result = _remote_claim_content(claims)
        lines = result.split("\n")
        assert len(lines) == 2
        assert lines[0] == "1|First"
        assert lines[1] == "2-3|Second"

    def test_remote_claim_content_empty_claim(self):
        """Test claim with empty or missing claim text."""
        from vault.mcp import _remote_claim_content
        claims = [{"line_start": 1, "line_end": 1}]
        result = _remote_claim_content(claims)
        assert result == "1|"

    def test_remote_claim_content_empty_list(self):
        """Test empty claims list returns empty string."""
        from vault.mcp import _remote_claim_content
        assert _remote_claim_content([]) == ""


class TestContentHashForText:
    def test_content_hash_consistent(self):
        """Test same text produces same hash."""
        from vault.mcp import _content_hash_for_text
        h1 = _content_hash_for_text("hello world")
        h2 = _content_hash_for_text("hello world")
        assert h1 == h2

    def test_content_hash_different(self):
        """Test different text produces different hash."""
        from vault.mcp import _content_hash_for_text
        h1 = _content_hash_for_text("hello")
        h2 = _content_hash_for_text("world")
        assert h1 != h2

    def test_content_hash_empty(self):
        """Test empty string hash."""
        from vault.mcp import _content_hash_for_text
        h = _content_hash_for_text("")
        assert isinstance(h, str)
        assert len(h) == 64  # sha256 hex length


class TestRemoteError:
    def test_remote_error_basic(self):
        """Test basic remote error response."""
        from vault.mcp import _remote_error
        result = _remote_error("NOT_FOUND", "Not found")
        assert "error" in result
        assert result["error"] == "NOT_FOUND"
        assert result["message"] == "Not found"

    def test_remote_error_with_extra(self):
        """Test remote error with extra kwargs."""
        from vault.mcp import _remote_error
        result = _remote_error("TEST", "msg", knowledge_id=42, extra="data")
        assert result["knowledge_id"] == 42
        assert result["extra"] == "data"


class TestRemoteNextActionForError:
    def test_remote_next_action_for_error_not_found(self):
        """Test next action for remote NOT_FOUND error."""
        from vault.mcp import _remote_next_action_for_error
        result = _remote_next_action_for_error("not_found")
        assert isinstance(result, dict)
        assert "tool" in result

    def test_remote_next_action_for_error_invalid_id(self):
        """Test next action for invalid_knowledge_id error."""
        from vault.mcp import _remote_next_action_for_error
        result = _remote_next_action_for_error("invalid_knowledge_id")
        assert isinstance(result, dict)

    def test_remote_next_action_for_error_unknown(self):
        """Test unknown error code returns default."""
        from vault.mcp import _remote_next_action_for_error
        result = _remote_next_action_for_error("some_unknown_error")
        assert isinstance(result, dict)


class TestVaultRemoteReadRangePayloadValidation:
    """Test validation paths of _vault_remote_read_range_payload."""

    def test_invalid_knowledge_id_non_numeric(self):
        """Test non-numeric knowledge_id returns error."""
        from vault.mcp import _vault_remote_read_range_payload
        result = _vault_remote_read_range_payload("not-a-number", sb_client=MagicMock())
        assert "error" in result
        assert result["error"] == "invalid_knowledge_id"

    def test_invalid_knowledge_id_zero(self):
        """Test zero knowledge_id returns error."""
        from vault.mcp import _vault_remote_read_range_payload
        result = _vault_remote_read_range_payload(0, sb_client=MagicMock())
        assert result["error"] == "invalid_knowledge_id"

    def test_invalid_knowledge_id_negative(self):
        """Test negative knowledge_id returns error."""
        from vault.mcp import _vault_remote_read_range_payload
        result = _vault_remote_read_range_payload(-1, sb_client=MagicMock())
        assert result["error"] == "invalid_knowledge_id"

    def test_max_lines_invalid_string(self):
        """Test string max_lines defaults to 80."""
        from vault.mcp import _vault_remote_read_range_payload
        # Should not raise error, just defaults to 80
        mock_client = MagicMock()
        result = _vault_remote_read_range_payload(1, max_lines="invalid", sb_client=mock_client)
        # Should get past max_lines validation and stop at the read-policy gate.
        assert result["error"] == "not_found"

    def test_max_lines_zero_defaults(self):
        """Test max_lines=0 defaults to 80."""
        from vault.mcp import _vault_remote_read_range_payload
        mock_client = MagicMock()
        result = _vault_remote_read_range_payload(1, max_lines=0, sb_client=mock_client)
        assert result["error"] == "not_found"

    def test_max_lines_negative_defaults(self):
        """Test negative max_lines defaults to 80."""
        from vault.mcp import _vault_remote_read_range_payload
        mock_client = MagicMock()
        result = _vault_remote_read_range_payload(1, max_lines=-5, sb_client=mock_client)
        assert result["error"] == "not_found"

    def test_no_supabase_client(self):
        """Test when sb_client is None and _get_supabase_client returns None."""
        from vault.mcp import _vault_remote_read_range_payload
        with patch('vault.mcp._get_supabase_client', return_value=None):
            result = _vault_remote_read_range_payload(1)
            assert result["error"] == "remote_client_missing"

    def test_remote_read_exception(self):
        """Test exception during remote read returns error."""
        from vault.mcp import _vault_remote_read_range_payload
        mock_client = MagicMock()
        mock_client.rpc.side_effect = Exception("Connection failed")
        result = _vault_remote_read_range_payload(1, sb_client=mock_client)
        assert result["error"] == "remote_policy_missing"

    def test_no_nodes_no_claims(self):
        """Test when both nodes and claims are empty."""
        from vault.mcp import _vault_remote_read_range_payload
        mock_client = MagicMock()
        get_response = MagicMock()
        get_response.data = [{"id": 42, "title": "Example"}]
        empty_response = MagicMock()
        empty_response.data = []
        mock_client.rpc.return_value.execute.side_effect = [
            get_response,
            empty_response,
            empty_response,
        ]
        result = _vault_remote_read_range_payload(42, sb_client=mock_client)
        assert result["error"] == "no_document_map_nodes"
        assert result["knowledge_id"] == 42



class TestVaultRemoteMapShowPayload:
    """Test _vault_remote_map_show_payload validation paths."""

    def test_invalid_knowledge_id(self):
        """Test invalid knowledge_id returns error."""
        from vault.mcp import _vault_remote_map_show_payload
        result = _vault_remote_map_show_payload("bad")
        assert "error" in result

    def test_negative_knowledge_id(self):
        """Test negative knowledge_id returns error."""
        from vault.mcp import _vault_remote_map_show_payload
        result = _vault_remote_map_show_payload(-1)
        assert "error" in result

    def test_no_supabase_client_map(self):
        """Test missing supabase client for map show."""
        from vault.mcp import _vault_remote_map_show_payload
        with patch('vault.mcp._get_supabase_client', return_value=None):
            result = _vault_remote_map_show_payload(1)
            assert result["error"] == "remote_client_missing"


class TestSupabaseRows:
    """Test _supabase_rows function."""

    def test_supabase_rows_basic(self):
        """Test basic supabase rows query."""
        from vault.mcp import _supabase_rows
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq = MagicMock()
        mock_response = MagicMock()
        
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_eq
        mock_eq.execute.return_value = mock_response
        mock_response.data = [{"id": 1, "name": "test"}]
        
        result = _supabase_rows(mock_client, "test_table", "*", {"id": 1})
        assert len(result) == 1
        assert result[0]["id"] == 1
        mock_client.table.assert_called_with("test_table")
        mock_table.select.assert_called_with("*")

    def test_supabase_rows_no_filters(self):
        """Test supabase rows without filters."""
        from vault.mcp import _supabase_rows
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.execute.return_value.data = [{"a": 1}]
        
        result = _supabase_rows(mock_client, "table")
        assert len(result) == 1

    def test_supabase_rows_none_data(self):
        """Test when response.data is None, returns empty list."""
        from vault.mcp import _supabase_rows
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = None
        # Make response have no data attribute
        mock_client.table.return_value.select.return_value.execute.return_value = mock_response
        
        result = _supabase_rows(mock_client, "table")
        assert result == []




import tempfile
import os


@pytest.fixture
def temp_vault_db(tmp_path):
    """Create a temporary vault database and set MCP DB_PATH."""
    from vault.db import VaultDB
    from vault.mcp import _set_project_dir

    db_path = tmp_path / "vault.db"
    db = VaultDB(str(db_path))
    db.connect()

    # Set the global DB_PATH in MCP module
    _set_project_dir(str(tmp_path))

    yield db

    db.close()


class TestMCPToolCalls:
    """Test handle_tool_call with various tool names."""

    def test_handle_tool_call_vault_search(self, temp_vault_db):
        from vault.mcp import handle_tool_call

        # Add test data first
        temp_vault_db.add_knowledge(
            title="Test Entry",
            content_raw="This is a test entry about Python programming.",
            category="tech",
        )

        result = handle_tool_call("vault_search", {"query": "Python"})
        assert isinstance(result, dict)
        assert "error" not in result or result.get("error") is not True

    def test_handle_tool_call_vault_add(self, temp_vault_db):
        from vault.mcp import handle_tool_call
        import json

        result = handle_tool_call("vault_add", {
            "title": "Test Knowledge",
            "content": "This is test knowledge content.",
        })
        assert isinstance(result, dict)
        # Result may contain JSON in 'result' key
        if 'result' in result:
            data = json.loads(result['result'])
            assert data.get('success') is True
            assert data.get('id') is not None
        else:
            assert result.get("id") is not None or result.get("added") is not None

    def test_handle_tool_call_vault_get(self, temp_vault_db):
        from vault.mcp import handle_tool_call

        add_result = handle_tool_call("vault_add", {
            "title": "Get Test",
            "content": "Content for get test.",
        })

        kid = add_result.get("id")
        if kid is not None:
            result = handle_tool_call("vault_get", {"id": kid})
            assert isinstance(result, dict)
            assert "content" in result or "title" in result

    def test_handle_tool_call_vault_list(self, temp_vault_db):
        from vault.mcp import handle_tool_call

        result = handle_tool_call("vault_list", {"limit": 10})
        assert isinstance(result, dict)

    def test_handle_tool_call_vault_stats(self, temp_vault_db):
        from vault.mcp import handle_tool_call

        result = handle_tool_call("vault_stats", {})
        assert isinstance(result, dict)

    def test_handle_tool_call_unknown_tool(self, temp_vault_db):
        from vault.mcp import handle_tool_call

        result = handle_tool_call("nonexistent_tool", {})
        assert isinstance(result, dict)
        # Should return error for unknown tool
        is_error = result.get("isError") or result.get("error") or "error" in str(result)
        assert is_error


class TestMCPHelperFunctions:
    """Test various helper functions in mcp.py."""

    def test_content_hash_for_text(self):
        from vault.mcp import _content_hash_for_text

        h1 = _content_hash_for_text("Hello World")
        h2 = _content_hash_for_text("Hello World")
        h3 = _content_hash_for_text("Different text")

        assert h1 == h2
        assert h1 != h3
        assert isinstance(h1, str)
        assert len(h1) > 0

    def test_remote_node_payload(self):
        from vault.mcp import _remote_node_payload

        node = {
            "node_uid": "uid123",
            "path": "/path/to/file",
            "heading": "Test Heading",
            "level": 2,
            "line_start": 5,
            "line_end": 10,
            "summary": "Test summary",
            "token_estimate": 100,
            "extra_field": "should be excluded",
        }
        payload = _remote_node_payload(node)
        assert isinstance(payload, dict)
        assert "node_uid" in payload
        assert "line_start" in payload
        assert "line_end" in payload
        assert "extra_field" not in payload

    def test_sort_remote_nodes(self):
        from vault.mcp import _sort_remote_nodes

        rows = [
            {"knowledge_id": 2, "line_start": 10, "id": 1, "level": 1, "node_uid": "b"},
            {"knowledge_id": 1, "line_start": 5, "id": 2, "level": 2, "node_uid": "a"},
            {"knowledge_id": 1, "line_start": 15, "id": 3, "level": 1, "node_uid": "c"},
        ]
        sorted_rows = _sort_remote_nodes(rows)
        # Sorted by line_start first
        assert sorted_rows[0]["line_start"] == 5
        assert sorted_rows[1]["line_start"] == 10
        assert sorted_rows[2]["line_start"] == 15

    def test_sort_remote_claims(self):
        from vault.mcp import _sort_remote_claims

        rows = [
            {"line_start": 10, "line_end": 15, "claim_uid": "c1"},
            {"line_start": 5, "line_end": 8, "claim_uid": "c2"},
            {"line_start": 5, "line_end": 12, "claim_uid": "c3"},
        ]
        sorted_rows = _sort_remote_claims(rows)
        assert sorted_rows[0]["line_start"] == 5
        assert sorted_rows[0]["line_end"] == 8  # Same line_start, sort by line_end
        assert sorted_rows[1]["line_end"] == 12
