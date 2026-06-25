"""Extended CLI tests to cover more untested code paths in cli.py."""

import pytest
import os
import sys
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO


@pytest.fixture
def initialized_project(tmp_path):
    """Create a freshly initialized vault project with test data."""
    from vault.db import VaultDB
    
    project_dir = tmp_path / "vault-project"
    project_dir.mkdir()
    
    db_path = str(project_dir / "vault.db")
    db = VaultDB(db_path)
    db.connect()
    
    # Add test entries
    for i in range(5):
        db.add_knowledge(
            title=f"Test Entry {i}",
            content_raw=f"This is test entry number {i}. Content about testing.",
            category="test",
            tags=f"test,entry{i}",
            layer="L3",
            trust=0.5 + i * 0.1,
        )
    
    # Add some edges for graph tests
    db.add_edge(1, 2, "related", 0.7)
    db.add_edge(2, 3, "related", 0.5)
    
    db.close()
    
    (project_dir / "raw").mkdir(exist_ok=True)
    (project_dir / "compiled").mkdir(exist_ok=True)
    
    return project_dir


class TestCmdConfig:
    """Test cmd_config command."""
    
    def test_config_set(self, initialized_project, monkeypatch, capsys):
        """Test config set action."""
        from vault.cli import cmd_config
        
        monkeypatch.chdir(initialized_project)
        
        args = MagicMock()
        args.config_action = "set"
        args.config_args = ["test_key", "test_value"]
        cmd_config(args)
        captured = capsys.readouterr()
        
        assert "test_key" in captured.out
        assert "test_value" in captured.out
    
    def test_config_get(self, initialized_project, monkeypatch, capsys):
        """Test config get action."""
        from vault.cli import cmd_config
        
        monkeypatch.chdir(initialized_project)
        
        # First set a value
        args = MagicMock()
        args.config_action = "set"
        args.config_args = ["my_key", "my_value"]
        cmd_config(args)
        
        # Then get it
        args2 = MagicMock()
        args2.config_action = "get"
        args2.config_args = ["my_key"]
        cmd_config(args2)
        captured = capsys.readouterr()
        
        assert "my_key" in captured.out
        assert "my_value" in captured.out
    
    def test_config_list(self, initialized_project, monkeypatch, capsys):
        """Test config list action."""
        from vault.cli import cmd_config
        
        monkeypatch.chdir(initialized_project)
        
        args = MagicMock()
        args.config_action = "list"
        args.config_args = []
        cmd_config(args)
        captured = capsys.readouterr()
        
        # Should show at least schema_version
        assert "schema_version" in captured.out
    
    def test_config_usage(self, initialized_project, monkeypatch, capsys):
        """Test config with invalid action shows usage."""
        from vault.cli import cmd_config
        
        monkeypatch.chdir(initialized_project)
        
        args = MagicMock()
        args.config_action = "invalid"
        args.config_args = []
        cmd_config(args)
        captured = capsys.readouterr()
        
        assert "用法" in captured.out


class TestCmdStats:
    """Test cmd_stats command."""
    
    def test_stats_basic(self, initialized_project, monkeypatch, capsys):
        """Test basic stats output."""
        from vault.cli import cmd_stats
        
        monkeypatch.chdir(initialized_project)
        
        args = MagicMock()
        cmd_stats(args)
        captured = capsys.readouterr()
        
        assert "知識筆數" in captured.out
        assert "5" in captured.out
        assert "DB 大小" in captured.out

    def test_stats_reports_semantic_vectors_when_sqlite_vec_unavailable(
        self, initialized_project, monkeypatch, capsys
    ):
        """Stats should not hide JSON semantic vectors when sqlite-vec is unavailable."""
        from vault.cli import cmd_stats
        from vault.db import VaultDB

        db = VaultDB(str(initialized_project / "vault.db")).connect()
        db.conn.execute(
            """INSERT INTO semantic_vectors
               (knowledge_id, vector_kind, item_uid, provider_id, dimension, vector,
                source_text, content_hash, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (1, "claim", "claim-1", "hash-deterministic-v1", 8, "[0,0,0,0,0,0,0,1]", "text", "hash", "now"),
        )
        db.conn.commit()
        db.close()

        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        cmd_stats(args)
        captured = capsys.readouterr()

        assert "semantic_vectors: 1" in captured.out
        assert "嵌入筆數:   1 (semantic_vectors)" in captured.out
    
    def test_stats_no_db(self, tmp_path, monkeypatch, capsys):
        """Test stats when no db doesn't exist."""
        from vault.cli import cmd_stats
        
        monkeypatch.chdir(tmp_path)
        
        args = MagicMock()
        cmd_stats(args)
        captured = capsys.readouterr()
        
        assert "尚未初始化" in captured.out


class TestCmdDoctor:
    def test_doctor_reports_sqlite_vec_runtime_blocked(
        self, initialized_project, monkeypatch, capsys
    ):
        """Doctor should distinguish installed sqlite-vec from blocked extension loading."""
        import sqlite3
        import vault.db as db_module
        from vault.cli import cmd_doctor

        def blocked_load(_conn):
            raise sqlite3.OperationalError("not authorized")

        monkeypatch.setattr(db_module, "_VEC_AVAILABLE", True)
        monkeypatch.setattr(db_module.sqlite_vec, "load", blocked_load)
        monkeypatch.chdir(initialized_project)

        args = MagicMock()
        cmd_doctor(args)
        captured = capsys.readouterr()

        assert "sqlite-vec runtime" in captured.out
        assert "not authorized" in captured.out
        assert "keyword search" in captured.out


class TestCmdGraphExtended:
    """Test cmd_graph subcommands beyond basic stats."""
    
    def test_graph_link(self, initialized_project, monkeypatch, capsys):
        """Test graph link action."""
        from vault.cli import cmd_graph
        
        monkeypatch.chdir(initialized_project)
        
        args = MagicMock()
        args.graph_action = "link"
        args.source_id = 3
        args.target_id = 4
        args.relation = "test_relation"
        args.weight = 0.8
        cmd_graph(args)
        captured = capsys.readouterr()
        
        assert "已建立關聯" in captured.out
        assert "test_relation" in captured.out
    
    def test_graph_link_source_not_found(self, initialized_project, monkeypatch, capsys):
        """Test graph link with non-existent source."""
        from vault.cli import cmd_graph
        
        monkeypatch.chdir(initialized_project)
        
        args = MagicMock()
        args.graph_action = "link"
        args.source_id = 999
        args.target_id = 1
        args.relation = "test"
        args.weight = 0.5
        cmd_graph(args)
        captured = capsys.readouterr()
        
        assert "找不到" in captured.out
    
    def test_graph_link_target_not_found(self, initialized_project, monkeypatch, capsys):
        """Test graph link with non-existent target."""
        from vault.cli import cmd_graph
        
        monkeypatch.chdir(initialized_project)
        
        args = MagicMock()
        args.graph_action = "link"
        args.source_id = 1
        args.target_id = 999
        args.relation = "test"
        args.weight = 0.5
        cmd_graph(args)
        captured = capsys.readouterr()
        
        assert "找不到" in captured.out
    
    def test_graph_unlink(self, initialized_project, monkeypatch, capsys):
        """Test graph unlink action."""
        from vault.cli import cmd_graph
        
        monkeypatch.chdir(initialized_project)
        
        args = MagicMock()
        args.graph_action = "unlink"
        args.edge_id = 1
        cmd_graph(args)
        captured = capsys.readouterr()
        
        assert "已刪除邊" in captured.out
    
    def test_graph_clear(self, initialized_project, monkeypatch, capsys):
        """Test graph clear action."""
        from vault.cli import cmd_graph
        
        monkeypatch.chdir(initialized_project)
        
        args = MagicMock()
        args.graph_action = "clear"
        cmd_graph(args)
        captured = capsys.readouterr()
        
        assert "已清除" in captured.out
    
    def test_graph_export_mermaid(self, initialized_project, monkeypatch, capsys, tmp_path):
        """Test graph export to mermaid format."""
        from vault.cli import cmd_graph
        
        monkeypatch.chdir(initialized_project)
        
        output_file = tmp_path / "graph.mmd"
        args = MagicMock()
        args.graph_action = "export"
        args.node_id = None
        args.format = "mermaid"
        args.depth = 2
        args.output = str(output_file)
        cmd_graph(args)
        captured = capsys.readouterr()
        
        assert "已匯出" in captured.out
        assert output_file.exists()
        content = output_file.read_text()
        assert "graph" in content or "flowchart" in content
    
    def test_graph_export_dot(self, initialized_project, monkeypatch, capsys, tmp_path):
        """Test graph export to dot format."""
        from vault.cli import cmd_graph
        
        monkeypatch.chdir(initialized_project)
        
        output_file = tmp_path / "graph.dot"
        args = MagicMock()
        args.graph_action = "export"
        args.node_id = None
        args.format = "dot"
        args.depth = 2
        args.output = str(output_file)
        cmd_graph(args)
        captured = capsys.readouterr()
        
        assert "已匯出" in captured.out
        assert output_file.exists()
    
    def test_graph_export_invalid_format(self, initialized_project, monkeypatch, capsys):
        """Test graph export with invalid format."""
        from vault.cli import cmd_graph
        
        monkeypatch.chdir(initialized_project)
        
        args = MagicMock()
        args.graph_action = "export"
        args.node_id = None
        args.format = "invalid"
        args.depth = 2
        args.output = None
        cmd_graph(args)
        captured = capsys.readouterr()
        
        assert "不支援的格式" in captured.out
    
    def test_graph_expand(self, initialized_project, monkeypatch, capsys):
        """Test graph expand action."""
        from vault.cli import cmd_graph
        
        monkeypatch.chdir(initialized_project)
        
        args = MagicMock()
        args.graph_action = "expand"
        args.node_id = 1
        args.depth = 2
        cmd_graph(args)
        captured = capsys.readouterr()
        
        # Should find neighbors via edge 1->2->3
        assert "找到" in captured.out


class TestCmdImport:
    """Test cmd_import command (no_embed mode)."""
    
    def test_import_file_not_found(self, initialized_project, monkeypatch, capsys):
        """Test import with non-existent file."""
        from vault.cli import cmd_import
        
        monkeypatch.chdir(initialized_project)
        
        args = MagicMock()
        args.file = "/nonexistent/file.md"
        args.no_embed = True
        args.strategy = "sliding"
        args.title = None
        args.layer = "L3"
        args.category = "general"
        args.tags = ""
        args.trust = 0.5
        args.chunk_size = 1000
        args.overlap = 200
        args.contextualize = False
        args.ollama_model = "llama3"
        cmd_import(args)
        captured = capsys.readouterr()
        
        assert "檔案不存在" in captured.out
    
    def test_import_text_file(self, initialized_project, monkeypatch, capsys, tmp_path):
        """Test import a simple text file with no_embed."""
        from vault.cli import cmd_import
        
        monkeypatch.chdir(initialized_project)
        
        # Create a test file
        test_file = tmp_path / "test_import.md"
        test_file.write_text("# Test Title\n\nThis is test content for import.\n\n## Section 1\n\nMore content here.\n\n## Section 2\n\nEven more content to ensure we have enough text for chunking.")
        
        args = MagicMock()
        args.file = str(test_file)
        args.no_embed = True
        args.strategy = "sliding"
        args.title = None
        args.layer = "L3"
        args.category = "imported"
        args.tags = "import,test"
        args.trust = 0.6
        args.chunk_size = 500
        args.overlap = 50
        args.contextualize = False
        args.ollama_model = "llama3"
        cmd_import(args)
        captured = capsys.readouterr()
        
        assert "匯入完成" in captured.out or "分塊數" in captured.out


class TestCmdDb:
    """Test cmd_db subcommands."""
    
    def test_db_status(self, initialized_project, monkeypatch, capsys):
        """Test db status action."""
        from vault.cli import cmd_db
        
        monkeypatch.chdir(initialized_project)
        
        args = MagicMock()
        args.db_action = "status"
        args.db_path = None
        args.pretty = False
        cmd_db(args)
        captured = capsys.readouterr()
        
        output = captured.out.strip()
        parsed = json.loads(output)
        assert "current_version" in parsed
    
    def test_db_invalid_action(self, initialized_project, monkeypatch, capsys):
        """Test db with invalid action."""
        from vault.cli import cmd_db
        
        monkeypatch.chdir(initialized_project)
        
        args = MagicMock()
        args.db_action = "invalid"
        
        with pytest.raises(SystemExit):
            cmd_db(args)
    
    def test_db_backup(self, initialized_project, monkeypatch, capsys, tmp_path):
        """Test db backup action."""
        from vault.cli import cmd_db
        
        monkeypatch.chdir(initialized_project)
        
        backup_path = tmp_path / "backup.db"
        args = MagicMock()
        args.db_action = "backup"
        args.db_path = None
        args.output = str(backup_path)
        args.verify = False
        args.pretty = False
        cmd_db(args)
        captured = capsys.readouterr()
        
        output = captured.out.strip()
        parsed = json.loads(output)
        assert "ok" in parsed or "backup" in parsed.get("status", "")
        assert backup_path.exists()
    
    def test_db_verify_backup(self, initialized_project, monkeypatch, capsys, tmp_path):
        """Test db verify-backup action."""
        from vault.cli import cmd_db
        
        monkeypatch.chdir(initialized_project)
        
        backup_path = tmp_path / "backup.db"
        # First create a backup
        args_backup = MagicMock()
        args_backup.db_action = "backup"
        args_backup.db_path = None
        args_backup.output = str(backup_path)
        args_backup.verify = False
        args_backup.pretty = False
        cmd_db(args_backup)
        
        # Clear captured output
        capsys.readouterr()
        
        # Then verify it
        args_verify = MagicMock()
        args_verify.db_action = "verify-backup"
        args_verify.backup_path = str(backup_path)
        args_verify.pretty = False
        cmd_db(args_verify)
        captured = capsys.readouterr()
        
        output = captured.out.strip()
        parsed = json.loads(output)
        assert "valid" in parsed or "ok" in str(parsed)


class TestCmdExport:
    """Test cmd_export command."""
    
    def test_export_obsidian_dry_run(self, initialized_project, monkeypatch, capsys, tmp_path):
        """Test export obsidian with dry_run."""
        from vault.cli import cmd_export
        
        monkeypatch.chdir(initialized_project)
        
        vault_dir = tmp_path / "obsidian_vault"
        vault_dir.mkdir()
        
        args = MagicMock()
        args.export_target = "obsidian"
        args.vault = str(vault_dir)
        args.category = None
        args.tag = None
        args.layer = None
        args.limit = 10
        args.min_trust = 0.0
        args.source = "db"
        args.dry_run = True
        cmd_export(args)
        captured = capsys.readouterr()
        
        assert "Obsidian export" in captured.out
        assert "dry_run=True" in captured.out
    
    def test_export_invalid_target(self, initialized_project, monkeypatch, capsys):
        """Test export with invalid target."""
        from vault.cli import cmd_export
        
        monkeypatch.chdir(initialized_project)
        
        args = MagicMock()
        args.export_target = "invalid"
        args.vault = "/tmp/test"
        
        with pytest.raises(SystemExit):
            cmd_export(args)


class TestCmdDedup:
    """Test cmd_dedup command (with proper mocking of lazy imports)."""
    
    def test_dedup_no_duplicates(self, initialized_project, monkeypatch, capsys):
        """Test dedup with no duplicates using sys.modules mock."""
        from vault.cli import cmd_dedup
        
        monkeypatch.chdir(initialized_project)
        
        # Mock the scripts.deduplicate_semantic module
        mock_module = MagicMock()
        mock_module.find_duplicates.return_value = []
        mock_module.merge_duplicates.return_value = None
        
        # Patch sys.modules before calling the function
        with patch.dict('sys.modules', {'scripts.deduplicate_semantic': mock_module}):
            args = MagicMock()
            args.threshold = 0.9
            args.merge = False
            args.dry_run = False
            cmd_dedup(args)
            captured = capsys.readouterr()
            
            assert "沒有發現重複" in captured.out
    
    def test_dedup_with_duplicates_dry_run(self, initialized_project, monkeypatch, capsys):
        """Test dedup with duplicates in dry_run mode."""
        from vault.cli import cmd_dedup
        
        monkeypatch.chdir(initialized_project)
        
        mock_module = MagicMock()
        mock_module.find_duplicates.return_value = [
            {"id1": 1, "id2": 2, "similarity": 0.95}
        ]
        
        with patch.dict('sys.modules', {'scripts.deduplicate_semantic': mock_module}):
            args = MagicMock()
            args.threshold = 0.9
            args.merge = False
            args.dry_run = True
            cmd_dedup(args)
            captured = capsys.readouterr()
            
            assert "--merge" in captured.out or "預覽" in captured.out


class TestCmdFreshness:
    """Test cmd_freshness command (with proper mocking of lazy imports)."""
    
    def test_freshness_basic(self, initialized_project, monkeypatch, capsys):
        """Test freshness check basic."""
        from vault.cli import cmd_freshness
        
        monkeypatch.chdir(initialized_project)
        
        mock_module = MagicMock()
        mock_module.check_freshness.return_value = None
        
        with patch.dict('sys.modules', {'scripts.freshness_check': mock_module}):
            args = MagicMock()
            args.apply = False
            args.limit = 10
            args.stale_only = False
            cmd_freshness(args)
            # Should not raise
            assert True


class TestHelperFunctions:
    """Test helper functions in cli.py."""
    
    def test_positive_int_valid(self):
        """Test _positive_int with valid values."""
        from vault.cli import _positive_int
        
        assert _positive_int("5") == 5
        assert _positive_int("1") == 1
        assert _positive_int("100") == 100
    
    def test_positive_int_zero(self):
        """Test _positive_int with zero (should fail)."""
        from vault.cli import _positive_int
        import argparse
        
        with pytest.raises(argparse.ArgumentTypeError):
            _positive_int("0")
    
    def test_positive_int_negative(self):
        """Test _positive_int with negative value."""
        from vault.cli import _positive_int
        import argparse
        
        with pytest.raises(argparse.ArgumentTypeError):
            _positive_int("-1")
    
    def test_positive_int_invalid(self):
        """Test _positive_int with invalid values."""
        from vault.cli import _positive_int
        import argparse
        
        with pytest.raises(argparse.ArgumentTypeError):
            _positive_int("abc")
    
    def test_json_print_basic(self, capsys):
        """Test _json_print basic output."""
        from vault.cli import _json_print
        
        data = {"key": "value", "number": 42}
        _json_print(data, pretty=False)
        captured = capsys.readouterr()
        
        output = captured.out.strip()
        parsed = json.loads(output)
        assert parsed["key"] == "value"
        assert parsed["number"] == 42
    
    def test_json_print_pretty(self, capsys):
        """Test _json_print pretty output."""
        from vault.cli import _json_print
        
        data = {"key": "value"}
        _json_print(data, pretty=True)
        captured = capsys.readouterr()
        
        # Pretty print should have newlines and indentation
        assert "\n" in captured.out


class TestCmdSemantic:
    """Test cmd_semantic command (mocked since it requires embeddings)."""
    
    def test_semantic_invalid_action(self, initialized_project, monkeypatch, capsys):
        """Test semantic with invalid action."""
        from vault.cli import cmd_semantic
        
        monkeypatch.chdir(initialized_project)
        
        args = MagicMock()
        args.semantic_action = "invalid_action"
        args.db_path = None
        
        with pytest.raises(SystemExit):
            cmd_semantic(args)
    
    def test_semantic_cache_stats(self, initialized_project, monkeypatch, capsys):
        """Test semantic cache-stats action."""
        from vault.cli import cmd_semantic
        
        monkeypatch.chdir(initialized_project)
        
        args = MagicMock()
        args.semantic_action = "cache-stats"
        args.db_path = None
        args.provider_id = "test_provider"
        args.dimension = 384
        args.pretty = False
        
        # Mock embedding_cache_stats via sys.modules
        mock_semantic = MagicMock()
        mock_semantic.embedding_cache_stats.return_value = {
            "total_rows": 10,
            "total_size_bytes": 10240,
            "provider_count": 1,
        }
        
        with patch.dict('sys.modules', {'vault.semantic': mock_semantic}):
            cmd_semantic(args)
            captured = capsys.readouterr()
            
            output = captured.out.strip()
            parsed = json.loads(output)
            assert parsed["action"] == "cache-stats"
            assert parsed["total_rows"] == 10
    
    def test_semantic_cache_prune(self, initialized_project, monkeypatch, capsys):
        """Test semantic cache-prune action."""
        from vault.cli import cmd_semantic
        
        monkeypatch.chdir(initialized_project)
        
        args = MagicMock()
        args.semantic_action = "cache-prune"
        args.db_path = None
        args.provider_id = "test_provider"
        args.dimension = 384
        args.older_than_days = 30
        args.max_rows = 100
        args.pretty = False
        
        mock_semantic = MagicMock()
        mock_semantic.prune_embedding_cache.return_value = 5
        
        with patch.dict('sys.modules', {'vault.semantic': mock_semantic}):
            cmd_semantic(args)
            captured = capsys.readouterr()
            
            output = captured.out.strip()
            parsed = json.loads(output)
            assert parsed["action"] == "cache-prune"
            assert parsed["deleted_rows"] == 5


class TestCmdSearchQA:
    """Test cmd_search_qa command."""
    
    def test_search_qa_invalid_mode(self, initialized_project, monkeypatch, capsys):
        """Test search-qa with invalid mode."""
        from vault.cli import cmd_search_qa
        
        monkeypatch.chdir(initialized_project)
        
        args = MagicMock()
        args.search_qa_action = "invalid"
        
        with pytest.raises(SystemExit):
            cmd_search_qa(args)
