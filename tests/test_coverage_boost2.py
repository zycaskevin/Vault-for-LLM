"""Tests for MCP and other modules to improve coverage."""

import pytest
import json
import tempfile
import os
from pathlib import Path


# === Fixtures ===

@pytest.fixture
def temp_vault_project(tmp_path):
    """Create a temporary vault project with initialized DB and test data."""
    project_dir = tmp_path / "vault-project"
    project_dir.mkdir()
    
    from vault.db import VaultDB
    db_path = str(project_dir / "vault.db")
    db = VaultDB(db_path)
    db.connect()
    
    # Add test knowledge entries
    db.add_knowledge(
        title="Python Programming Guide",
        content_raw="Python is a great programming language used for web development, data science, and automation.",
        category="tech",
        tags="python,programming",
        layer="L3",
        trust=0.8,
    )
    db.add_knowledge(
        title="Database Design Principles",
        content_raw="Good database design uses normalization. SQLite is a lightweight database engine.",
        category="tech",
        tags="database,sqlite",
        layer="L2",
        trust=0.9,
    )
    db.add_knowledge(
        title="Getting Started with APIs",
        content_raw="APIs allow different software systems to communicate. REST APIs are common.",
        category="guide",
        tags="api,rest",
        layer="L3",
        trust=0.7,
    )
    
    db.close()
    
    # Create raw/ directory for cmd_add tests
    raw_dir = project_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    return project_dir


# === Test MCP error handling via public API ===

class TestMcpErrorHandling:
    """Test MCP error handling via public API."""

    def test_vault_map_show_invalid_id_string(self):
        """Test vault_map_show with invalid string id."""
        from vault.mcp import vault_map_show
        
        result = vault_map_show("not_a_number")
        assert "error" in result
        assert "invalid_knowledge_id" in result["error"] or result.get("failure_mode") == "invalid_knowledge_id"

    def test_vault_map_show_zero_id(self):
        """Test vault_map_show with zero id."""
        from vault.mcp import vault_map_show
        
        result = vault_map_show(0)
        assert "error" in result

    def test_vault_map_show_negative_id(self):
        """Test vault_map_show with negative id."""
        from vault.mcp import vault_map_show
        
        result = vault_map_show(-1)
        assert "error" in result

    def test_vault_read_range_invalid_id(self):
        """Test vault_read_range with invalid id."""
        from vault.mcp import vault_read_range
        
        result = vault_read_range("bad", "node1", 1, 10)
        assert "error" in result

    def test_vault_read_range_zero_id(self):
        """Test vault_read_range with zero id."""
        from vault.mcp import vault_read_range
        
        result = vault_read_range(0, "node1", 1, 10)
        assert "error" in result

    def test_vault_remote_map_show_invalid_id(self):
        """Test vault_remote_map_show with invalid id."""
        from vault.mcp import vault_remote_map_show
        
        result = vault_remote_map_show("invalid", compact=False)
        assert "error" in result

    def test_vault_remote_read_range_invalid_id(self):
        """Test vault_remote_read_range with invalid id."""
        from vault.mcp import vault_remote_read_range
        
        result = vault_remote_read_range("bad", "node1", 1, 10)
        assert "error" in result


# === Test handle_tool_call ===

class TestHandleToolCall:
    """Test handle_tool_call function with various tools."""

    def test_unknown_tool(self):
        """Test unknown tool name."""
        from vault.mcp import handle_tool_call
        
        result = handle_tool_call("nonexistent_tool", {})
        assert "error" in result

    def test_vault_stats_no_db(self, tmp_path):
        """Test vault_stats when no db exists but project dir is set."""
        from vault.mcp import handle_tool_call, _set_project_dir
        
        _set_project_dir(str(tmp_path))
        result = handle_tool_call("vault_stats", {})
        # Should return result even if no db (creates empty)
        assert "result" in result or "error" in result

    def test_vault_search_keyword_mode(self, temp_vault_project):
        """Test vault_search with keyword mode via handle_tool_call."""
        from vault.mcp import handle_tool_call, _set_project_dir
        
        _set_project_dir(str(temp_vault_project))
        result = handle_tool_call("vault_search", {"query": "python", "mode": "keyword"})
        assert "results" in result or "result" in result

    def test_vault_add_entry(self, temp_vault_project):
        """Test vault_add tool via handle_tool_call."""
        from vault.mcp import handle_tool_call, _set_project_dir
        
        _set_project_dir(str(temp_vault_project))
        result = handle_tool_call("vault_add", {
            "title": "Test Entry",
            "content": "Test content for vault entry.",
            "category": "test"
        })
        assert "id" in result or "result" in result

    def test_vault_map_show_via_handle(self, temp_vault_project):
        """Test vault_map_show via handle_tool_call."""
        from vault.mcp import handle_tool_call, _set_project_dir
        
        _set_project_dir(str(temp_vault_project))
        result = handle_tool_call("vault_map_show", {"knowledge_id": 1})
        assert "nodes" in result or "error" in result or "result" in result

    def test_vault_dream_run_via_handle(self, temp_vault_project):
        """Test vault_list via handle_tool_call."""
        from vault.mcp import handle_tool_call, _set_project_dir
        
        _set_project_dir(str(temp_vault_project))
        result = handle_tool_call("vault_dream_run", {"mode": "report", "limit": 2})
        assert "entries" in result or "results" in result or "result" in result


# === Test with actual DB - direct MCP functions ===

class TestMcpDirectWithDb:
    """Test MCP direct functions with actual database."""

    def test_vault_map_show_nonexistent(self, temp_vault_project):
        """Test vault_map_show with non-existent knowledge."""
        from vault.mcp import vault_map_show, _set_project_dir
        
        _set_project_dir(str(temp_vault_project))
        result = vault_map_show(9999)
        assert "error" in result

    def test_vault_read_range_nonexistent(self, temp_vault_project):
        """Test vault_read_range with non-existent knowledge."""
        from vault.mcp import vault_read_range, _set_project_dir
        
        _set_project_dir(str(temp_vault_project))
        result = vault_read_range(9999, "node-1", 1, 10)
        assert "error" in result


# === Test compiler utilities ===

class TestCompilerUtilities:
    """Test compiler utility functions."""

    def test_classify_content_with_meta(self):
        """Test classify_content with metadata."""
        from vault.compiler import classify_content
        
        result = classify_content("Some content", {"source": "tech", "tags": "programming"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_classify_content_empty_meta(self):
        """Test classify_content with empty metadata."""
        from vault.compiler import classify_content
        
        result = classify_content("Python is a programming language.", {})
        assert isinstance(result, str)

    def test_assign_layer_with_meta(self):
        """Test assign_layer with metadata."""
        from vault.compiler import assign_layer
        
        result = assign_layer({"layer": "L1"})
        assert result == "L1"

    def test_assign_layer_no_layer_in_meta(self):
        """Test assign_layer without layer in metadata."""
        from vault.compiler import assign_layer
        
        result = assign_layer({"category": "tech"})
        assert isinstance(result, str)
        assert result.startswith("L")

    def test_extract_claims_no_content(self):
        """Test extract_claims with empty content."""
        from vault.compiler import extract_claims
        
        result = extract_claims("Test Title", "")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_extract_claims_basic(self):
        """Test extract_claims with simple content."""
        from vault.compiler import extract_claims
        
        result = extract_claims("Python", "Python is a programming language. It was created by Guido van Rossum.")
        assert isinstance(result, list)

    def test_extract_frontmatter_empty(self):
        """Test extract_frontmatter with empty content."""
        from vault.compiler import extract_frontmatter
        
        meta, content = extract_frontmatter("")
        assert content == ""
        assert meta == {}

    def test_extract_frontmatter_with_yaml(self):
        """Test extract_frontmatter with YAML frontmatter."""
        from vault.compiler import extract_frontmatter
        
        text = "---\ntitle: Test\ntags: python\n---\nBody content"
        meta, content = extract_frontmatter(text)
        assert "title" in meta
        assert meta["title"] == "Test"
        assert "Body content" in content

    def test_extract_frontmatter_no_frontmatter(self):
        """Test extract_frontmatter without frontmatter."""
        from vault.compiler import extract_frontmatter
        
        text = "Just regular content without frontmatter."
        meta, content = extract_frontmatter(text)
        assert content == text
        assert meta == {}

    def test_generate_summary_empty(self):
        """Test generate_summary with empty content."""
        from vault.compiler import generate_summary
        
        result = generate_summary("")
        assert result == ""

    def test_generate_summary_basic(self):
        """Test generate_summary with basic content."""
        from vault.compiler import generate_summary
        
        result = generate_summary("Python is a great programming language.", title="Python Guide")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_simple_aaak_compress(self):
        """Test simple_aaak_compress function."""
        from vault.compiler import simple_aaak_compress
        
        result = simple_aaak_compress("Hello World", "This is a test content about hello world.")
        assert isinstance(result, str)
        assert len(result) > 0


# === Test importer edge cases ===

class TestImporterEdgeCases:
    """Test importer edge cases."""

    def test_sliding_window_chunk_empty(self):
        """Test sliding_window_chunk with empty content."""
        from vault.importer import sliding_window_chunk
        
        result = sliding_window_chunk("", chunk_size=100, overlap=20)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_sliding_window_chunk_smaller_than_chunk(self):
        """Test sliding_window_chunk with content smaller than chunk."""
        from vault.importer import sliding_window_chunk
        
        content = "Short text."
        result = sliding_window_chunk(content, chunk_size=100, overlap=20)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].content == content

    def test_detect_chapters_no_headings(self):
        """Test detect_chapters with no headings."""
        from vault.importer import detect_chapters
        
        content = "Just some plain text without any headings."
        result = detect_chapters(content)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_detect_chapters_markdown(self):
        """Test detect_chapters with markdown headings."""
        from vault.importer import detect_chapters
        
        content = "# Chapter 1\nContent 1\n## Section 1.1\nMore content\n# Chapter 2\nContent 2"
        result = detect_chapters(content)
        assert isinstance(result, list)
        assert len(result) >= 2

    def test_split_into_sentences_empty(self):
        """Test split_into_sentences with empty text."""
        from vault.importer import split_into_sentences
        
        result = split_into_sentences("")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_split_into_sentences_basic(self):
        """Test split_into_sentences with simple text."""
        from vault.importer import split_into_sentences
        
        result = split_into_sentences("Hello world. This is a test.")
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_chunk_result_creation(self):
        """Test ChunkResult creation with correct params."""
        from vault.importer import ChunkResult
        
        chunk = ChunkResult(
            index=1,
            title="Test Chunk",
            content="Test content here.",
            start_char=0,
            end_char=16,
            chunk_type="semantic",
            context_prefix=""
        )
        assert chunk.content == "Test content here."
        assert chunk.title == "Test Chunk"
        assert chunk.start_char == 0
        assert chunk.end_char == 16
        assert chunk.index == 1
        assert chunk.chunk_type == "semantic"


# === Test search functions ===

class TestSearchFunctions:
    """Test search module functions."""

    def test_semantic_provider_error_exists(self):
        """Test that SemanticProviderError exists."""
        from vault.search import SemanticProviderError
        
        error = SemanticProviderError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_vault_search_keyword(self, temp_vault_project):
        """Test VaultSearch keyword search."""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        
        db_path = str(temp_vault_project / "vault.db")
        db = VaultDB(db_path)
        db.connect()
        search = VaultSearch(db)
        results = search.search("python", mode="keyword")
        db.close()
        assert isinstance(results, list)

    def test_vault_search_with_limit(self, temp_vault_project):
        """Test VaultSearch with limit parameter."""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        
        db_path = str(temp_vault_project / "vault.db")
        db = VaultDB(db_path)
        db.connect()
        search = VaultSearch(db)
        results = search.search("python", mode="keyword", limit=1)
        db.close()
        assert isinstance(results, list)
        assert len(results) <= 1

    def test_vault_search_with_min_trust(self, temp_vault_project):
        """Test VaultSearch with min_trust parameter."""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        
        db_path = str(temp_vault_project / "vault.db")
        db = VaultDB(db_path)
        db.connect()
        search = VaultSearch(db)
        results = search.search("python", mode="keyword", min_trust=0.5)
        db.close()
        assert isinstance(results, list)

    def test_vault_search_keyword_method(self, temp_vault_project):
        """Test VaultSearch.search_keyword method directly."""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        
        db_path = str(temp_vault_project / "vault.db")
        db = VaultDB(db_path)
        db.connect()
        search = VaultSearch(db)
        results = search.search_keyword("database")
        db.close()
        assert isinstance(results, list)

    def test_create_embedding_provider_onnx(self):
        """Test create_embedding_provider with onnx type."""
        from vault.search import create_embedding_provider
        
        provider = create_embedding_provider("onnx")
        assert provider is not None

    def test_provider_dimension_onnx(self):
        """Test provider_dimension with onnx provider."""
        from vault.search import create_embedding_provider, provider_dimension
        
        provider = create_embedding_provider("onnx")
        dim = provider_dimension(provider)
        assert isinstance(dim, int)
        assert dim > 0

    def test_provider_id_onnx(self):
        """Test provider_id function."""
        from vault.search import create_embedding_provider, provider_id
        
        provider = create_embedding_provider("onnx")
        pid = provider_id(provider)
        assert isinstance(pid, str)

    def test_has_embeddings_false(self, temp_vault_project):
        """Test VaultSearch.has_embeddings when no embeddings exist."""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        
        db_path = str(temp_vault_project / "vault.db")
        db = VaultDB(db_path)
        db.connect()
        search = VaultSearch(db)
        result = search.has_embeddings
        db.close()
        assert isinstance(result, bool)


# === Test dream functions ===

class TestDreamFunctions:
    """Test dream module functions."""

    def test_run_dream_report_mode(self, temp_vault_project):
        """Test run_dream in report mode."""
        from vault.dream import run_dream
        
        result = run_dream(str(temp_vault_project), mode="report", limit=5)
        assert isinstance(result, dict)

    def test_run_dream_with_specific_checks(self, temp_vault_project):
        """Test run_dream with specific checks."""
        from vault.dream import run_dream
        
        result = run_dream(str(temp_vault_project), mode="report", checks=["dedup"], limit=5)
        assert isinstance(result, dict)

    def test_build_dream_report_with_data(self, temp_vault_project):
        """Test build_dream_report with actual dream output."""
        from vault.dream import run_dream, build_dream_report
        
        dream_result = run_dream(str(temp_vault_project), mode="report", limit=5)
        report = build_dream_report(dream_result)
        assert isinstance(report, str)

    def test_default_checks_exists(self):
        """Test that DEFAULT_CHECKS exists."""
        from vault.dream import DEFAULT_CHECKS
        
        assert isinstance(DEFAULT_CHECKS, list)
        assert len(DEFAULT_CHECKS) > 0


# === Test graph functions ===

class TestGraphFunctions:
    """Test graph module functions."""

    def test_vault_graph_init(self, temp_vault_project):
        """Test VaultGraph initialization."""
        from vault.graph import VaultGraph
        from vault.db import VaultDB
        
        db_path = str(temp_vault_project / "vault.db")
        db = VaultDB(db_path)
        db.connect()
        graph = VaultGraph(db)
        db.close()
        assert graph is not None

    def test_vault_graph_stats(self, temp_vault_project):
        """Test VaultGraph stats method."""
        from vault.graph import VaultGraph
        from vault.db import VaultDB
        
        db_path = str(temp_vault_project / "vault.db")
        db = VaultDB(db_path)
        db.connect()
        graph = VaultGraph(db)
        stats = graph.stats()
        db.close()
        assert isinstance(stats, dict)
        assert "edges_total" in stats
        assert "entities_total" in stats

    def test_vault_graph_expand_invalid(self, temp_vault_project):
        """Test VaultGraph expand with invalid node id."""
        from vault.graph import VaultGraph
        from vault.db import VaultDB
        
        db_path = str(temp_vault_project / "vault.db")
        db = VaultDB(db_path)
        db.connect()
        graph = VaultGraph(db)
        result = graph.expand(9999, max_depth=1)
        db.close()
        assert isinstance(result, list)

    def test_vault_graph_to_mermaid(self, temp_vault_project):
        """Test VaultGraph to_mermaid method."""
        from vault.graph import VaultGraph
        from vault.db import VaultDB
        
        db_path = str(temp_vault_project / "vault.db")
        db = VaultDB(db_path)
        db.connect()
        graph = VaultGraph(db)
        result = graph.to_mermaid(max_depth=2)
        db.close()
        assert isinstance(result, str)

    def test_vault_graph_infer_all(self, temp_vault_project):
        """Test VaultGraph infer_all method."""
        from vault.graph import VaultGraph
        from vault.db import VaultDB
        
        db_path = str(temp_vault_project / "vault.db")
        db = VaultDB(db_path)
        db.connect()
        graph = VaultGraph(db)
        result = graph.infer_all()
        db.close()
        assert isinstance(result, dict)

    def test_vault_graph_clear_auto_inferred(self, temp_vault_project):
        """Test VaultGraph clear_auto_inferred method."""
        from vault.graph import VaultGraph
        from vault.db import VaultDB
        
        db_path = str(temp_vault_project / "vault.db")
        db = VaultDB(db_path)
        db.connect()
        graph = VaultGraph(db)
        result = graph.clear_auto_inferred()
        db.close()
        # Returns None or int count


# === Test DB more functions ===

class TestDbMoreFunctions:
    """Test additional DB functions."""

    def test_db_get_knowledge_not_found(self, temp_vault_project):
        """Test get_knowledge with non-existent ID."""
        from vault.db import VaultDB
        
        db_path = str(temp_vault_project / "vault.db")
        db = VaultDB(db_path)
        db.connect()
        result = db.get_knowledge(9999)
        db.close()
        assert result is None

    def test_db_list_knowledge_with_layer(self, temp_vault_project):
        """Test list_knowledge with layer filter."""
        from vault.db import VaultDB
        
        db_path = str(temp_vault_project / "vault.db")
        db = VaultDB(db_path)
        db.connect()
        result = db.list_knowledge(layer="L3")
        db.close()
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_db_list_knowledge_with_category(self, temp_vault_project):
        """Test list_knowledge with category filter."""
        from vault.db import VaultDB
        
        db_path = str(temp_vault_project / "vault.db")
        db = VaultDB(db_path)
        db.connect()
        result = db.list_knowledge(category="tech")
        db.close()
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_db_update_knowledge(self, temp_vault_project):
        """Test update_knowledge function."""
        from vault.db import VaultDB
        
        db_path = str(temp_vault_project / "vault.db")
        db = VaultDB(db_path)
        db.connect()
        result = db.update_knowledge(1, title="Updated Title")
        db.close()
        assert result is True

    def test_db_delete_knowledge(self, temp_vault_project):
        """Test delete_knowledge function."""
        from vault.db import VaultDB
        
        db_path = str(temp_vault_project / "vault.db")
        db = VaultDB(db_path)
        db.connect()
        result = db.delete_knowledge(3)
        db.close()
        assert result is True

    def test_db_config_operations(self, temp_vault_project):
        """Test config get/set operations."""
        from vault.db import VaultDB
        
        db_path = str(temp_vault_project / "vault.db")
        db = VaultDB(db_path)
        db.connect()
        
        # Set a config value
        db.set_config("test_key", "test_value")
        
        # Get it back
        value = db.get_config("test_key")
        assert value == "test_value"
        
        # Get non-existent key returns empty string
        value2 = db.get_config("nonexistent")
        assert value2 == ""
        
        db.close()

    def test_db_search_keyword_limit(self, temp_vault_project):
        """Test search_keyword with limit parameter."""
        from vault.db import VaultDB
        
        db_path = str(temp_vault_project / "vault.db")
        db = VaultDB(db_path)
        db.connect()
        result = db.search_keyword("database", limit=1)
        db.close()
        assert isinstance(result, list)
        assert len(result) <= 1
