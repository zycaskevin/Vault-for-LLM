"""Extended tests for vault/semantic_lifecycle.py"""
import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestCloseProvider:
    def test_close_provider_with_close_method(self):
        from vault.semantic_lifecycle import close_provider
        
        mock_provider = MagicMock()
        mock_provider.close.return_value = None
        close_provider(mock_provider)
        mock_provider.close.assert_called_once()

    def test_close_provider_without_close_method(self):
        from vault.semantic_lifecycle import close_provider
        
        provider = object()  # No close method
        close_provider(provider)  # Should not raise

    def test_close_provider_close_raises(self):
        from vault.semantic_lifecycle import close_provider
        
        mock_provider = MagicMock()
        mock_provider.close.side_effect = RuntimeError("close failed")
        close_provider(mock_provider)  # Should not raise, exception is swallowed


class TestProviderPayload:
    def test_provider_payload_basic(self):
        from vault.semantic_lifecycle import _provider_payload
        
        provider = MagicMock()
        provider.provider_id = "test_provider"
        provider.is_semantic = True
        provider.dim = 32
        provider.cache_size = 100
        
        result = _provider_payload(provider)
        assert result["provider_id"] == "test_provider"
        assert result["is_semantic"] is True
        assert result["dimension"] == 32
        assert result["cache_size"] == 100

    def test_persistent_cache_payload_basic(self):
        from vault.semantic_lifecycle import _persistent_cache_payload
        
        provider = MagicMock()
        provider.cache_size = 50
        provider.persistent_hits = 10
        provider.persistent_misses = 5
        provider.writes = 3
        
        result = _persistent_cache_payload(provider)
        assert result["memory_rows"] == 50
        assert result["persistent_hits"] == 10
        assert result["persistent_misses"] == 5
        assert result["writes"] == 3


class TestLoadUniqueQAQueries:
    def test_load_unique_qa_queries_none(self):
        from vault.semantic_lifecycle import _load_unique_qa_queries
        assert _load_unique_qa_queries(None) == []

    def test_load_unique_qa_queries_with_file(self, tmp_path):
        from vault.semantic_lifecycle import _load_unique_qa_queries
        
        qa_content = {
            "cases": [
                {"id": "1", "query": "what is python?"},
                {"id": "2", "query": "what is python?"},  # Duplicate
                {"id": "3", "query": "how to test?"},
            ]
        }
        qa_file = tmp_path / "test_qa.json"
        qa_file.write_text(json.dumps(qa_content))
        
        result = _load_unique_qa_queries(qa_file)
        assert len(result) == 2
        assert "what is python?" in result
        assert "how to test?" in result


class TestCacheProvider:
    def test_cache_provider_persistent_new(self):
        from vault.semantic_lifecycle import _cache_provider
        from vault.semantic import DeterministicHashEmbeddingProvider
        
        provider = DeterministicHashEmbeddingProvider(dim=32)
        mock_db = MagicMock()
        
        result = _cache_provider(provider, mock_db, persist_cache=True)
        # Should wrap in PersistentCachedEmbeddingProvider
        assert hasattr(result, "persistent_hits") or hasattr(result, "writes")

    def test_cache_provider_persistent_already_persistent(self):
        from vault.semantic_lifecycle import _cache_provider
        from vault.semantic import PersistentCachedEmbeddingProvider, DeterministicHashEmbeddingProvider
        
        inner = DeterministicHashEmbeddingProvider(dim=32)
        mock_db = MagicMock()
        persistent = PersistentCachedEmbeddingProvider(inner, mock_db)
        
        result = _cache_provider(persistent, mock_db, persist_cache=True)
        # Should return the same provider since it's already persistent
        assert result is persistent

    def test_cache_provider_non_persistent(self):
        from vault.semantic_lifecycle import _cache_provider
        from vault.semantic import DeterministicHashEmbeddingProvider
        
        provider = DeterministicHashEmbeddingProvider(dim=32)
        mock_db = MagicMock()
        
        result = _cache_provider(provider, mock_db, persist_cache=False)
        # Should wrap in CachedEmbeddingProvider
        assert hasattr(result, "cache") or hasattr(result, "cache_size")

    def test_cache_provider_already_cached(self):
        from vault.semantic_lifecycle import _cache_provider
        from vault.semantic import CachedEmbeddingProvider, DeterministicHashEmbeddingProvider
        
        inner = DeterministicHashEmbeddingProvider(dim=32)
        cached = CachedEmbeddingProvider(inner)
        mock_db = MagicMock()
        
        result = _cache_provider(cached, mock_db, persist_cache=False)
        # Should return the same provider since it's already cached
        assert result is cached


class TestRunSemanticStartup:
    def test_run_semantic_startup_basic(self, tmp_path):
        from vault.semantic_lifecycle import run_semantic_startup
        from vault.db import VaultDB
        
        # Create a test database with some knowledge
        db_path = tmp_path / "test.db"
        db = VaultDB(str(db_path))
        db.connect()
        db.add_knowledge(
            title="Test Doc",
            content_raw="This is a test document with some content.",
            category="test",
            layer="L3",
        )
        db.close()
        
        result = run_semantic_startup(
            db_path=str(db_path),
            allow_hash=True,
            hash_dim=8,
            persist_cache=False,
        )
        assert result["action"] == "startup"
        assert result["success"] is True
        assert "provider" in result
        assert "cache_before" in result
        assert "cache_after" in result

    def test_run_semantic_startup_with_rebuild(self, tmp_path):
        from vault.semantic_lifecycle import run_semantic_startup
        from vault.db import VaultDB
        
        db_path = tmp_path / "test.db"
        db = VaultDB(str(db_path))
        db.connect()
        kid = db.add_knowledge(
            title="Test Doc",
            content_raw="This is a test document with content for rebuild.",
            category="test",
            layer="L3",
        )
        from vault.docmap import build_document_map_for_entry
        build_document_map_for_entry(db.conn, kid)
        db.close()
        
        result = run_semantic_startup(
            db_path=str(db_path),
            allow_hash=True,
            hash_dim=8,
            persist_cache=False,
            rebuild=True,
        )
        assert result["rebuild"] is not None
        assert "knowledge_rows" in result["rebuild"]
        assert "node_vectors" in result["rebuild"]

    def test_run_semantic_startup_with_queries(self, tmp_path):
        from vault.semantic_lifecycle import run_semantic_startup
        from vault.db import VaultDB
        
        db_path = tmp_path / "test.db"
        db = VaultDB(str(db_path))
        db.connect()
        db.add_knowledge(
            title="Python Guide",
            content_raw="Python is a programming language.",
            category="tech",
            layer="L3",
        )
        db.close()
        
        # Create QA file
        qa_file = tmp_path / "qa.json"
        qa_file.write_text(json.dumps({
            "cases": [
                {"id": "1", "query": "what is python?", "answer": "programming language"},
                {"id": "2", "query": "another query", "answer": "answer"},
            ]
        }))
        
        result = run_semantic_startup(
            db_path=str(db_path),
            qa_file=str(qa_file),
            allow_hash=True,
            hash_dim=8,
            persist_cache=False,
        )
        assert result["warmed_queries"] == 2

    def test_run_semantic_startup_with_prune(self, tmp_path):
        from vault.semantic_lifecycle import run_semantic_startup
        from vault.db import VaultDB
        
        db_path = tmp_path / "test.db"
        db = VaultDB(str(db_path))
        db.connect()
        db.add_knowledge(
            title="Test Doc",
            content_raw="Test content for pruning.",
            category="test",
            layer="L3",
        )
        db.close()
        
        result = run_semantic_startup(
            db_path=str(db_path),
            allow_hash=True,
            hash_dim=8,
            persist_cache=False,
            older_than_days=30,
            max_rows=100,
        )
        assert "prune_deleted_rows" in result

    def test_run_semantic_startup_smoke(self, tmp_path):
        from vault.semantic_lifecycle import run_semantic_startup
        from vault.db import VaultDB
        
        db_path = tmp_path / "test.db"
        db = VaultDB(str(db_path))
        db.connect()
        db.add_knowledge(
            title="Test Doc",
            content_raw="This is test content for smoke test.",
            category="test",
            layer="L3",
        )
        db.close()
        
        qa_file = tmp_path / "qa.json"
        qa_file.write_text(json.dumps({
            "cases": [
                {"id": "1", "query": "test query", "answer": "test answer"},
            ]
        }))
        
        result = run_semantic_startup(
            db_path=str(db_path),
            qa_file=str(qa_file),
            allow_hash=True,
            hash_dim=8,
            persist_cache=False,
            smoke=True,
            mode="keyword",
            limit=3,
        )
        assert result["smoke"] is not None
        assert "aggregate" in result["smoke"]


class TestRunSemanticDaemon:
    def test_run_semantic_daemon_single_iteration(self, tmp_path):
        from vault.semantic_lifecycle import run_semantic_daemon
        from vault.db import VaultDB
        
        db_path = tmp_path / "test.db"
        db = VaultDB(str(db_path))
        db.connect()
        db.add_knowledge(title="Test", content_raw="content", category="test", layer="L3")
        db.close()
        
        result = run_semantic_daemon(
            repeat=1,
            interval=0,
            db_path=str(db_path),
            allow_hash=True,
            hash_dim=8,
            persist_cache=False,
        )
        assert result["action"] == "daemon"
        assert result["success"] is True
        assert result["repeat"] == 1
        assert len(result["iterations"]) == 1

    def test_run_semantic_daemon_multiple_iterations(self, tmp_path):
        from vault.semantic_lifecycle import run_semantic_daemon
        from vault.db import VaultDB
        
        db_path = tmp_path / "test.db"
        db = VaultDB(str(db_path))
        db.connect()
        db.add_knowledge(title="Test", content_raw="content", category="test", layer="L3")
        db.close()
        
        result = run_semantic_daemon(
            repeat=3,
            interval=0,  # No delay for test
            db_path=str(db_path),
            allow_hash=True,
            hash_dim=8,
            persist_cache=False,
        )
        assert len(result["iterations"]) == 3
        assert result["iterations"][0]["iteration"] == 1
        assert result["iterations"][2]["iteration"] == 3

    def test_run_semantic_daemon_negative_repeat(self):
        from vault.semantic_lifecycle import run_semantic_daemon
        
        with pytest.raises(ValueError, match="repeat must be >= 0"):
            run_semantic_daemon(repeat=-1, interval=0)

    def test_run_semantic_daemon_negative_interval(self):
        from vault.semantic_lifecycle import run_semantic_daemon
        
        with pytest.raises(ValueError, match="interval must be >= 0"):
            run_semantic_daemon(repeat=1, interval=-1)
