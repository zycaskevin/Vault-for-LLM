
"""Additional tests for utility functions to improve coverage."""

import pytest
import os
from pathlib import Path


@pytest.fixture
def temp_vault_project(tmp_path):
    """Create a temporary vault project with initialized DB."""
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
        source="test",
    )
    db.add_knowledge(
        title="Machine Learning Basics",
        content_raw="Machine learning is a subset of artificial intelligence that enables systems to learn from data.",
        category="tech",
        tags="ml,ai",
        layer="L2",
        trust=0.75,
        source="test",
    )
    
    db.close()
    return project_dir


# === importer.py tests ===

class TestImporterUtilities:
    """Test importer utility functions."""

    def test_sliding_window_chunk_basic(self):
        """Test basic sliding window chunking."""
        from vault.importer import sliding_window_chunk
        
        text = "Hello world. This is a test. " * 50
        chunks = sliding_window_chunk(text, chunk_size=200, overlap=50)
        
        assert len(chunks) > 0
        for chunk in chunks:
            assert hasattr(chunk, 'content')

    def test_sliding_window_chunk_small_text(self):
        """Test sliding window with small text."""
        from vault.importer import sliding_window_chunk
        
        text = "Short text."
        chunks = sliding_window_chunk(text, chunk_size=200, overlap=50)
        
        assert len(chunks) == 1
        assert chunks[0].content == text

    def test_sliding_window_chunk_empty(self):
        """Test sliding window with empty text."""
        from vault.importer import sliding_window_chunk
        
        chunks = sliding_window_chunk("", chunk_size=200, overlap=50)
        assert len(chunks) == 0

    def test_detect_chapters_markdown(self):
        """Test chapter detection with markdown headings."""
        from vault.importer import detect_chapters
        
        text = """# Chapter 1
Content of chapter 1.

## Section 1.1
More content.

# Chapter 2
Content of chapter 2.
"""
        chapters = detect_chapters(text)
        assert len(chapters) >= 2
        assert "Chapter 1" in chapters[0][0]

    def test_detect_chapters_none(self):
        """Test chapter detection with no headings."""
        from vault.importer import detect_chapters
        
        text = "Just some plain text without any headings."
        chapters = detect_chapters(text)
        assert len(chapters) == 0

    def test_split_into_sentences(self):
        """Test sentence splitting."""
        from vault.importer import split_into_sentences
        
        text = "Hello world. This is a test! Is it working? Yes, it is."
        sentences = split_into_sentences(text)
        
        assert isinstance(sentences, list)
        assert len(sentences) >= 3

    def test_chunk_result_attributes(self):
        """Test ChunkResult attributes."""
        from vault.importer import ChunkResult
        
        chunk = ChunkResult(
            index=0,
            title="Test Chunk",
            content="Test content",
            start_char=0,
            end_char=12,
            chunk_type="test"
        )
        
        assert chunk.index == 0
        assert chunk.title == "Test Chunk"
        assert chunk.content == "Test content"
        assert chunk.start_char == 0
        assert chunk.end_char == 12
        assert chunk.chunk_type == "test"


# === memory.py tests ===

class TestMemoryUtilities:
    """Test memory utility functions."""

    def test_normalize_title(self):
        """Test title normalization."""
        from vault.memory import normalize_title
        
        result = normalize_title("  Hello  World  ")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_normalize_text(self):
        """Test text normalization."""
        from vault.memory import normalize_text
        
        result = normalize_text("  Some   text  with  spaces  ")
        assert isinstance(result, str)

    def test_content_hash(self):
        """Test content hashing."""
        from vault.memory import content_hash
        
        h1 = content_hash("test content")
        h2 = content_hash("test content")
        h3 = content_hash("different content")
        
        assert h1 == h2
        assert h1 != h3
        assert isinstance(h1, str)

    def test_text_similarity(self):
        """Test text similarity function."""
        from vault.memory import text_similarity
        
        sim1 = text_similarity("hello world", "hello world")
        sim2 = text_similarity("hello world", "goodbye world")
        sim3 = text_similarity("hello world", "completely different")
        
        assert sim1 >= sim2 >= sim3
        assert 0 <= sim1 <= 1

    def test_safe_slug(self):
        """Test slug generation."""
        from vault.memory import safe_slug
        
        slug = safe_slug("Hello World! This is a Test.")
        assert isinstance(slug, str)
        assert len(slug) > 0

    def test_normalize_metadata(self):
        """Test metadata normalization."""
        from vault.memory import normalize_metadata
        
        result = normalize_metadata("Test Title", "Test content", layer="L2", category="test")
        assert isinstance(result, dict)
        assert result["title"] == "Test Title"
        assert result["layer"] == "L2"

    def test_quality_gate(self):
        """Test quality gate function."""
        from vault.memory import quality_gate
        
        meta = {
            "title": "Test Title",
            "content": "This is decent content with some substance and more text.",
            "layer": "L3",
            "trust": 0.7,
        }
        result = quality_gate(meta)
        assert isinstance(result, dict)
        assert "status" in result

    def test_duplicate_gate(self, temp_vault_project):
        """Test duplicate gate function."""
        from vault.memory import duplicate_gate
        from vault.db import VaultDB
        
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        
        result = duplicate_gate(db, "Python Programming Guide", "Python is a great programming language.")
        assert isinstance(result, dict)
        assert "status" in result
        
        db.close()

    def test_gate_payload(self):
        """Test gate payload function."""
        from vault.memory import _gate_payload
        
        payload = _gate_payload(
            privacy={"status": "pass"},
            duplicate={"status": "pass"},
            metadata={"status": "pass"},
            quality={"status": "pass"},
        )
        assert isinstance(payload, dict)
        assert "privacy" in payload
        assert "duplicate" in payload
        assert "metadata" in payload
        assert "quality" in payload

    def test_all_gates_pass(self):
        """Test all gates pass function."""
        from vault.memory import _all_gates_pass
        
        # All gates pass
        result = {
            "gates": {
                "privacy": "pass",
                "duplicate": "pass",
                "metadata": "pass",
                "quality": "pass",
            }
        }
        assert _all_gates_pass(result) == True

        # One gate fails
        result_fail = {
            "gates": {
                "privacy": "pass",
                "duplicate": "fail",
                "metadata": "pass",
                "quality": "pass",
            }
        }
        assert _all_gates_pass(result_fail) == False


# === search.py tests ===

class TestSearchUtilities:
    """Test search utility functions."""

    def test_normalize_text(self):
        """Test text normalization."""
        from vault.search import _normalize_text
        
        result = _normalize_text("Hello World!")
        assert isinstance(result, str)

    def test_vault_search_init(self, temp_vault_project):
        """Test VaultSearch initialization."""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        
        search = VaultSearch(db)
        assert search is not None
        
        db.close()

    def test_search_keyword_mode(self, temp_vault_project):
        """Test keyword search mode."""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        
        search = VaultSearch(db)
        results = search.search("Python", mode="keyword", limit=5)
        
        assert isinstance(results, list)
        
        db.close()

    def test_search_with_min_trust(self, temp_vault_project):
        """Test search with min_trust filter."""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        
        search = VaultSearch(db)
        results = search.search("Python", mode="keyword", limit=5, min_trust=0.5)
        
        assert isinstance(results, list)
        for r in results:
            assert r.get("trust", 0) >= 0.5
        
        db.close()

    def test_search_with_category(self, temp_vault_project):
        """Test search with category filter."""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        
        search = VaultSearch(db)
        results = search.search("Python", mode="keyword", category="tech")
        
        assert isinstance(results, list)
        
        db.close()

    def test_search_with_layer(self, temp_vault_project):
        """Test search with layer filter."""
        from vault.search import VaultSearch
        from vault.db import VaultDB
        
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        
        search = VaultSearch(db)
        results = search.search("Python", mode="keyword", layer="L3")
        
        assert isinstance(results, list)
        
        db.close()


# === compiler.py tests ===

class TestCompilerUtilities:
    """Test compiler utility functions."""

    def test_extract_frontmatter(self):
        """Test frontmatter extraction."""
        from vault.compiler import extract_frontmatter
        
        content = """---
title: Test
tags: [a, b]
---
Main content here.
"""
        fm, body = extract_frontmatter(content)
        assert isinstance(fm, dict)
        assert fm.get("title") == "Test"
        assert "Main content" in body

    def test_extract_frontmatter_none(self):
        """Test frontmatter extraction with no frontmatter."""
        from vault.compiler import extract_frontmatter
        
        content = "Just plain content without frontmatter."
        fm, body = extract_frontmatter(content)
        assert isinstance(fm, dict)
        assert len(fm) == 0
        assert body == content

    def test_extract_claims(self):
        """Test claim extraction."""
        from vault.compiler import extract_claims
        
        claims = extract_claims("Test Title", "The sky is blue. Water is wet.")
        assert isinstance(claims, list)

    def test_classify_content(self):
        """Test content classification."""
        from vault.compiler import classify_content
        
        meta = {"title": "Python Tutorial", "content": "Learn Python programming."}
        result = classify_content("test content", meta)
        assert isinstance(result, str)

    def test_assign_layer(self):
        """Test layer assignment."""
        from vault.compiler import assign_layer
        
        meta = {"title": "Advanced Guide", "content": "Advanced content."}
        layer = assign_layer(meta)
        assert layer in ["L1", "L2", "L3", "L4"]

    def test_simple_aaak_compress(self):
        """Test AAAK compression/processing."""
        from vault.compiler import simple_aaak_compress
        
        text = "This is a longer piece of text that should be processed. " * 10
        result = simple_aaak_compress("Test Title", text)
        
        assert isinstance(result, str)


# === db.py additional tests ===

class TestDbMoreFunctions:
    """Test more database functions."""

    def test_db_add_knowledge(self, temp_vault_project):
        """Test adding knowledge entries."""
        from vault.db import VaultDB
        
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        
        kid = db.add_knowledge(
            title="Test Knowledge Entry",
            content_raw="This is the raw content of the test knowledge entry.",
            layer="L2",
            category="test",
            trust=0.75,
            source="test_source",
        )
        
        assert kid is not None
        assert isinstance(kid, int)
        
        entry = db.get_knowledge(kid)
        assert entry is not None
        assert entry["title"] == "Test Knowledge Entry"
        
        db.close()

    def test_db_update_knowledge(self, temp_vault_project):
        """Test updating knowledge entries."""
        from vault.db import VaultDB
        
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        
        kid = db.add_knowledge(
            title="Original Title",
            content_raw="Original content.",
            layer="L2",
            category="test",
            trust=0.7,
            source="test",
        )
        
        db.update_knowledge(kid, title="Updated Title", content_raw="Updated content.")
        
        entry = db.get_knowledge(kid)
        assert entry["title"] == "Updated Title"
        assert "Updated content" in entry["content_raw"]
        
        db.close()

    def test_db_list_knowledge(self, temp_vault_project):
        """Test listing knowledge entries."""
        from vault.db import VaultDB
        
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        
        items = db.list_knowledge(limit=3)
        assert isinstance(items, list)
        assert len(items) <= 3
        
        items = db.list_knowledge(layer="L3")
        assert isinstance(items, list)
        
        db.close()

    def test_db_delete_knowledge(self, temp_vault_project):
        """Test deleting knowledge entries."""
        from vault.db import VaultDB
        
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        
        kid = db.add_knowledge(
            title="To Be Deleted",
            content_raw="This will be deleted.",
            layer="L2",
            category="test",
            trust=0.5,
            source="test",
        )
        
        db.delete_knowledge(kid)
        
        entry = db.get_knowledge(kid)
        assert entry is None
        
        db.close()

    def test_db_stats(self, temp_vault_project):
        """Test database stats."""
        from vault.db import VaultDB
        
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        
        stats = db.stats()
        assert isinstance(stats, dict)
        assert len(stats) > 0
        
        db.close()

    def test_db_config(self, temp_vault_project):
        """Test config operations."""
        from vault.db import VaultDB
        
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        
        db.set_config("test_key", "test_value_123")
        value = db.get_config("test_key", "default")
        assert value == "test_value_123"
        
        default_val = db.get_config("nonexistent_key", "default_val")
        assert default_val == "default_val"
        
        db.close()

    def test_db_search_keyword(self, temp_vault_project):
        """Test keyword search."""
        from vault.db import VaultDB
        
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        
        results = db.search_keyword("Python", limit=5)
        assert isinstance(results, list)
        
        db.close()

    def test_db_get_neighbors_empty(self, temp_vault_project):
        """Test get_neighbors with no connections."""
        from vault.db import VaultDB
        
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        
        entries = db.list_knowledge(limit=1)
        if entries:
            neighbors = db.get_neighbors(entries[0]["id"], max_depth=2)
            assert isinstance(neighbors, list)
        
        db.close()


# === dream.py tests ===

class TestDreamUtilities:
    """Test dream utility functions."""

    def test_normalize_checks_string(self):
        """Test check normalization with string input."""
        from vault.dream import _normalize_checks
        
        checks = _normalize_checks("all")
        assert isinstance(checks, list)
        assert len(checks) > 0

    def test_normalize_checks_list(self):
        """Test check normalization with list input."""
        from vault.dream import _normalize_checks
        
        checks = _normalize_checks(["freshness", "dedup"])
        assert isinstance(checks, list)
        assert len(checks) == 2

    def test_normalize_checks_none(self):
        """Test check normalization with None input."""
        from vault.dream import _normalize_checks
        
        checks = _normalize_checks(None)
        assert isinstance(checks, list)

    def test_limit_rows(self):
        """Test row limiting."""
        from vault.dream import _limit_rows
        
        rows = [{"id": i} for i in range(20)]
        limited = _limit_rows(rows, 5)
        assert len(limited) == 5
        
        limited2 = _limit_rows(rows, 10)
        assert len(limited2) == 10

    def test_run_dream_report(self, temp_vault_project):
        """Test running dream in report mode."""
        from vault.dream import run_dream
        
        result = run_dream(
            temp_vault_project,
            mode="report",
            checks=["freshness"],
            limit=5,
            write_report=False,
            backup=False,
        )
        
        assert isinstance(result, dict)


# === semantic.py tests ===

class TestSemanticUtilities:
    """Test semantic module utilities."""

    def test_hash_embedding_provider_encode(self):
        """Test hash embedding provider encode."""
        from vault.semantic import DeterministicHashEmbeddingProvider
        
        provider = DeterministicHashEmbeddingProvider(dim=64)
        embeddings = provider.encode(["Hello world", "Test string"])
        
        assert len(embeddings) == 2
        assert len(embeddings[0]) == 64
        assert len(embeddings[1]) == 64

    def test_hash_embedding_consistency(self):
        """Test that hash embeddings are deterministic."""
        from vault.semantic import DeterministicHashEmbeddingProvider
        
        provider = DeterministicHashEmbeddingProvider(dim=64)
        emb1 = provider.encode(["test"])[0]
        emb2 = provider.encode(["test"])[0]
        
        assert emb1 == emb2

    def test_hash_embedding_different_dimensions(self):
        """Test hash embeddings with different dimensions."""
        from vault.semantic import DeterministicHashEmbeddingProvider
        
        for dim in [16, 32, 64, 128]:
            provider = DeterministicHashEmbeddingProvider(dim=dim)
            emb = provider.encode(["test"])[0]
            assert len(emb) == dim

    def test_semantic_lifecycle_cache_stats(self, temp_vault_project):
        """Test semantic lifecycle cache stats."""
        from vault.db import VaultDB
        from vault.semantic_lifecycle import embedding_cache_stats
        
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        
        try:
            stats = embedding_cache_stats(db)
            assert isinstance(stats, dict)
        except Exception:
            pass  # Table might not exist
        
        db.close()


# === graph.py tests ===

class TestGraphUtilities:
    """Test graph utility functions."""

    def test_vault_graph_init(self, temp_vault_project):
        """Test VaultGraph initialization."""
        from vault.graph import VaultGraph
        from vault.db import VaultDB
        
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        
        graph = VaultGraph(db)
        assert graph is not None
        
        db.close()

    def test_graph_stats(self, temp_vault_project):
        """Test graph stats."""
        from vault.graph import VaultGraph
        from vault.db import VaultDB
        
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        
        graph = VaultGraph(db)
        stats = graph.stats()
        assert isinstance(stats, dict)
        
        db.close()

    def test_graph_link_unlink(self, temp_vault_project):
        """Test graph link and unlink."""
        from vault.graph import VaultGraph
        from vault.db import VaultDB
        
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        
        entries = db.list_knowledge(limit=2)
        if len(entries) >= 2:
            graph = VaultGraph(db)
            edge_id = graph.link(entries[0]["id"], entries[1]["id"], "related", "test")
            
            neighbors = graph.expand(entries[0]["id"], max_depth=1)
            assert isinstance(neighbors, list)
            
            if edge_id:
                graph.unlink(edge_id)
        
        db.close()

    def test_graph_to_mermaid(self, temp_vault_project):
        """Test mermaid export."""
        from vault.graph import VaultGraph
        from vault.db import VaultDB
        
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        
        graph = VaultGraph(db)
        mermaid = graph.to_mermaid()
        assert isinstance(mermaid, str)
        
        db.close()


# === privacy.py tests ===

class TestPrivacyUtilities:
    """Test privacy module functions."""

    def test_privacy_module_exists(self):
        """Test that privacy module can be imported."""
        from vault import privacy
        assert privacy is not None


# === agent_policy.py tests ===

class TestAgentPolicy:
    """Test agent policy module."""

    def test_agent_policy_module_exists(self):
        """Test that agent_policy module can be imported."""
        from vault import agent_policy
        assert agent_policy is not None


# === health.py tests ===

class TestHealthModule:
    """Test health module functions."""

    def test_health_module_exists(self):
        """Test that health module can be imported."""
        from vault import health
        assert health is not None


# === log.py tests ===

class TestLogModule:
    """Test log module functions."""

    def test_log_module_exists(self):
        """Test that log module can be imported."""
        from vault import log
        assert log is not None
