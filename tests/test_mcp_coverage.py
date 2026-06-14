"""Tests for MCP module pure functions to boost coverage."""

import pytest


class TestCanonicalToolName:
    """Test _canonical_tool_name function."""
    
    def test_canonical_name_passthrough(self):
        """Test that it returns the name unchanged."""
        from vault.mcp import _canonical_tool_name
        
        assert _canonical_tool_name("vault_search") == "vault_search"
        assert _canonical_tool_name("search") == "search"
        assert _canonical_tool_name("") == ""


class TestLineHash:
    """Test _line_hash function."""
    
    def test_line_hash_basic(self):
        """Test basic line hashing."""
        from vault.mcp import _line_hash
        
        lines = ["line 1", "line 2", "line 3"]
        hash1 = _line_hash(lines, 0, 2)
        hash2 = _line_hash(lines, 0, 2)
        
        # Same input should produce same hash
        assert hash1 == hash2
        assert isinstance(hash1, str)
    
    def test_line_hash_different_ranges(self):
        """Test different ranges produce different hashes."""
        from vault.mcp import _line_hash
        
        lines = ["line 1", "line 2", "line 3"]
        hash1 = _line_hash(lines, 0, 1)
        hash2 = _line_hash(lines, 1, 2)
        
        assert hash1 != hash2


class TestFormatCitation:
    """Test _format_citation function."""
    
    def test_format_citation_basic(self):
        """Test basic citation formatting."""
        from vault.mcp import _format_citation
        
        result = _format_citation(1, "Test Title", 0, 10)
        assert isinstance(result, str)
        assert "1" in result
        assert "Test Title" in result
    
    def test_format_citation_same_line(self):
        """Test citation with same start and end line."""
        from vault.mcp import _format_citation
        
        result = _format_citation(42, "Another Title", 5, 5)
        assert "42" in result
        assert "Another Title" in result


class TestErrorFunction:
    """Test _error function."""
    
    def test_error_basic(self):
        """Test basic error creation."""
        from vault.mcp import _error
        
        result = _error("TEST_ERROR", "Test message")
        assert "error" in result
        assert result["error"] == "TEST_ERROR"
        assert result["message"] == "Test message"
        assert "next_action" in result
    
    def test_error_with_extra(self):
        """Test error with extra fields."""
        from vault.mcp import _error
        
        result = _error("ERROR", "Msg", extra_field="value", count=42)
        assert result["extra_field"] == "value"
        assert result["count"] == 42
    
    def test_error_with_next_action(self):
        """Test error with custom next_action."""
        from vault.mcp import _error
        
        custom_action = {"tool": "custom_tool", "arguments": {"x": 1}}
        result = _error("ERROR", "Msg", next_action=custom_action)
        assert result["next_action"] == custom_action


class TestNextActionForError:
    """Test _next_action_for_error function."""
    
    def test_next_action_for_error_not_found(self):
        """Test with not_found error code."""
        from vault.mcp import _next_action_for_error
        
        result = _next_action_for_error("not_found")
        assert isinstance(result, dict)
        assert "tool" in result
        assert result["tool"] == "vault_search"
    
    def test_next_action_for_error_invalid_range(self):
        """Test with invalid_range error code."""
        from vault.mcp import _next_action_for_error
        
        result = _next_action_for_error("invalid_range", {"knowledge_id": 42})
        assert result["tool"] == "vault_map_show"
        assert result["arguments"]["knowledge_id"] == 42
    
    def test_next_action_for_error_range_too_large(self):
        """Test with range_too_large error code."""
        from vault.mcp import _next_action_for_error
        
        result = _next_action_for_error("range_too_large", {"knowledge_id": 10})
        assert result["tool"] == "vault_read_range"
        assert result["arguments"]["knowledge_id"] == 10
    
    def test_next_action_for_error_no_map_nodes(self):
        """Test with no_document_map_nodes error code."""
        from vault.mcp import _next_action_for_error
        
        result = _next_action_for_error("no_document_map_nodes", {"knowledge_id": 5})
        assert result["tool"] == "vault_map_build"
    
    def test_next_action_for_error_unknown(self):
        """Test with an unknown error code."""
        from vault.mcp import _next_action_for_error
        
        result = _next_action_for_error("UNKNOWN_ERROR_XYZ")
        assert isinstance(result, dict)
        assert "tool" in result
        # Falls back to vault_search
        assert result["tool"] == "vault_search"


class TestRemoteNextActionForError:
    """Test _remote_next_action_for_error function."""
    
    def test_remote_next_action_not_found(self):
        """Test remote not_found error."""
        from vault.mcp import _remote_next_action_for_error
        
        result = _remote_next_action_for_error("not_found")
        assert result["tool"] == "vault_search"
    
    def test_remote_next_action_invalid_range(self):
        """Test remote invalid_range error."""
        from vault.mcp import _remote_next_action_for_error
        
        result = _remote_next_action_for_error("invalid_range", {"knowledge_id": 1})
        assert result["tool"] == "vault_remote_map_show"
    
    def test_remote_next_action_range_too_large(self):
        """Test remote range_too_large error."""
        from vault.mcp import _remote_next_action_for_error
        
        result = _remote_next_action_for_error("range_too_large", {"knowledge_id": 2})
        assert result["tool"] == "vault_remote_read_range"
    
    def test_remote_next_action_unknown(self):
        """Test remote unknown error."""
        from vault.mcp import _remote_next_action_for_error
        
        result = _remote_next_action_for_error("SOMETHING_ELSE")
        assert result["tool"] == "vault_search"


class TestContentHashForText:
    """Test _content_hash_for_text function."""
    
    def test_content_hash_basic(self):
        """Test basic content hashing."""
        from vault.mcp import _content_hash_for_text
        
        hash1 = _content_hash_for_text("hello world")
        hash2 = _content_hash_for_text("hello world")
        
        assert hash1 == hash2
        assert isinstance(hash1, str)
    
    def test_content_hash_different(self):
        """Test different texts produce different hashes."""
        from vault.mcp import _content_hash_for_text
        
        hash1 = _content_hash_for_text("text one")
        hash2 = _content_hash_for_text("text two")
        
        assert hash1 != hash2
    
    def test_content_hash_empty(self):
        """Test empty string hash."""
        from vault.mcp import _content_hash_for_text
        
        result = _content_hash_for_text("")
        assert isinstance(result, str)
        assert len(result) > 0


class TestCompactNode:
    """Test _compact_node function."""
    
    def test_compact_node_basic(self):
        """Test basic node compacting."""
        from vault.mcp import _compact_node
        
        node = {
            "node_uid": "uid-123",
            "path": "/section/heading",
            "heading": "Test Heading",
            "line_start": 0,
            "line_end": 10,
            "extra_field": "should be removed",
        }
        result = _compact_node(node)
        
        assert isinstance(result, dict)
        assert result["node_uid"] == "uid-123"
        assert result["path"] == "/section/heading"
        assert result["heading"] == "Test Heading"
        assert result["line_start"] == 0
        assert result["line_end"] == 10
        # Extra fields should not be included
        assert "extra_field" not in result
    
    def test_compact_node_missing_fields(self):
        """Test compact with missing fields."""
        from vault.mcp import _compact_node
        
        node = {"line_start": 5, "line_end": 10}
        result = _compact_node(node)
        
        assert result["node_uid"] == ""
        assert result["path"] == ""
        assert result["heading"] == ""
        assert result["line_start"] == 5
        assert result["line_end"] == 10


class TestPreferredReadNode:
    """Test _preferred_read_node function."""
    
    def test_preferred_read_node_empty(self):
        """Test with empty list."""
        from vault.mcp import _preferred_read_node
        
        result = _preferred_read_node([])
        assert result is None
    
    def test_preferred_read_node_single(self):
        """Test with single node."""
        from vault.mcp import _preferred_read_node
        
        nodes = [{"type": "claim", "level": 1, "content": "test"}]
        result = _preferred_read_node(nodes)
        
        assert result == nodes[0]
    
    def test_preferred_read_node_prefers_higher_level(self):
        """Test that higher level nodes are preferred."""
        from vault.mcp import _preferred_read_node
        
        nodes = [
            {"type": "section", "level": 1, "content": "level 1"},
            {"type": "subsection", "level": 2, "content": "level 2"},
        ]
        result = _preferred_read_node(nodes)
        
        assert result["level"] == 2
    
    def test_preferred_read_node_no_high_level(self):
        """Test when all nodes are level 1 or less."""
        from vault.mcp import _preferred_read_node
        
        nodes = [
            {"type": "doc", "level": 0, "content": "level 0"},
            {"type": "section", "level": 1, "content": "level 1"},
        ]
        result = _preferred_read_node(nodes)
        
        # Falls back to first node
        assert result == nodes[0]


class TestSortRemoteNodes:
    """Test _sort_remote_nodes function."""
    
    def test_sort_remote_nodes_basic(self):
        """Test basic sorting of remote nodes."""
        from vault.mcp import _sort_remote_nodes
        
        rows = [
            {"line_start": 10, "id": 2},
            {"line_start": 5, "id": 1},
            {"line_start": 15, "id": 3},
        ]
        result = _sort_remote_nodes(rows)
        
        assert len(result) == 3
        assert result[0]["id"] == 1  # line_start=5
        assert result[1]["id"] == 2  # line_start=10
        assert result[2]["id"] == 3  # line_start=15


class TestSortRemoteClaims:
    """Test _sort_remote_claims function."""
    
    def test_sort_remote_claims_basic(self):
        """Test basic sorting of remote claims."""
        from vault.mcp import _sort_remote_claims
        
        rows = [
            {"line_start": 10, "id": 2},
            {"line_start": 5, "id": 1},
            {"line_start": 15, "id": 3},
        ]
        result = _sort_remote_claims(rows)
        
        assert len(result) == 3
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2
        assert result[2]["id"] == 3


class TestRemoteNodePayload:
    """Test _remote_node_payload function."""
    
    def test_remote_node_payload_full(self):
        """Test payload with all fields."""
        from vault.mcp import _remote_node_payload
        
        row = {
            "node_uid": "uid-1",
            "path": "/test/path",
            "heading": "Test Heading",
            "level": 2,
            "line_start": 0,
            "line_end": 10,
            "summary": "Test summary",
            "token_estimate": 100,
            "extra_field": "should be excluded",
        }
        result = _remote_node_payload(row)
        
        assert isinstance(result, dict)
        assert result["node_uid"] == "uid-1"
        assert result["path"] == "/test/path"
        assert result["heading"] == "Test Heading"
        assert result["level"] == 2
        assert result["line_start"] == 0
        assert result["line_end"] == 10
        assert result["summary"] == "Test summary"
        assert result["token_estimate"] == 100
        assert "extra_field" not in result
    
    def test_remote_node_payload_partial(self):
        """Test payload with partial fields."""
        from vault.mcp import _remote_node_payload
        
        row = {
            "node_uid": "uid-2",
            "line_start": 5,
            "line_end": 15,
        }
        result = _remote_node_payload(row)
        
        assert len(result) == 3  # only the keys that exist
        assert "heading" not in result  # not in row
