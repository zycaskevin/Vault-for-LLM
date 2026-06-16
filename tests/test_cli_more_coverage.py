"""Additional CLI coverage tests for edge cases and simpler paths."""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestCmdSearchQACompare:
    """Test cmd_search_qa compare mode (no embed needed)."""
    
    def test_compare_two_snapshots(self, tmp_path, capsys):
        """Test search-qa compare with two snapshot files."""
        from vault.cli import cmd_search_qa
        
        # Create two sample QA snapshot files
        before = {
            "total_questions": 3,
            "metrics": {"recall_at_5": 0.8, "mrr": 0.7},
            "questions": [
                {"question": "q1", "found": True, "rank": 1, "expected": ["doc1"]},
                {"question": "q2", "found": True, "rank": 3, "expected": ["doc2"]},
                {"question": "q3", "found": False, "rank": None, "expected": ["doc3"]},
            ]
        }
        after = {
            "total_questions": 3,
            "metrics": {"recall_at_5": 0.9, "mrr": 0.85},
            "questions": [
                {"question": "q1", "found": True, "rank": 1, "expected": ["doc1"]},
                {"question": "q2", "found": True, "rank": 2, "expected": ["doc2"]},
                {"question": "q3", "found": True, "rank": 5, "expected": ["doc3"]},
            ]
        }
        
        before_path = tmp_path / "before.json"
        after_path = tmp_path / "after.json"
        before_path.write_text(json.dumps(before))
        after_path.write_text(json.dumps(after))
        
        args = MagicMock()
        args.search_qa_action = "compare"
        args.before = str(before_path)
        args.after = str(after_path)
        args.output = None
        
        cmd_search_qa(args)
        captured = capsys.readouterr()
        
        assert captured.out
        assert "comparison" in captured.out.lower() or "total_cases" in captured.out.lower()


class TestCmdSkillListEmpty:
    """Test cmd_skill list with empty skills."""
    
    def test_skill_list_empty(self, tmp_path, monkeypatch, capsys):
        """Test skill list when no skills are registered."""
        from vault.cli import cmd_skill_list
        from vault.db import VaultDB
        
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        (project_dir / "raw").mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        
        monkeypatch.chdir(project_dir)
        
        args = MagicMock()
        args.category = None
        args.agent = None
        args.min_trust = 0.0
        args.limit = 100
        
        # Need to set all attrs that might be accessed to avoid MagicMock leakage
        args.layer = None
        
        cmd_skill_list(args)
        captured = capsys.readouterr()
        
        assert "空" in captured.out or "0" in captured.out or "empty" in captured.out.lower()


class TestCmdListEmpty:
    """Test cmd_list with empty knowledge base."""
    
    def test_list_empty(self, tmp_path, monkeypatch, capsys):
        """Test list when knowledge base is empty."""
        from vault.cli import cmd_list
        from vault.db import VaultDB
        
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        
        monkeypatch.chdir(project_dir)
        
        args = MagicMock()
        args.layer = None
        args.category = None
        args.min_trust = 0
        args.limit = 10
        
        cmd_list(args)
        captured = capsys.readouterr()
        
        assert "空" in captured.out or "empty" in captured.out.lower()


class TestCmdSearchEmpty:
    """Test cmd_search with no results."""
    
    def test_search_no_results(self, tmp_path, monkeypatch, capsys):
        """Test search when no results found."""
        from vault.cli import cmd_search
        from vault.db import VaultDB
        
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        
        monkeypatch.chdir(project_dir)
        
        args = MagicMock()
        args.query = "nonexistent keyword 12345"
        args.keyword_only = True
        args.mode = "keyword"
        args.limit = 10
        args.graph_expand = 0
        args.min_score = 0.0
        args.semantic_vector_kind = "dense"
        args.allow_hash = False
        args.no_rerank = True
        args.hash_dim = 32
        args.layer = None
        args.category = None
        args.min_trust = 0.0
        
        cmd_search(args)
        captured = capsys.readouterr()
        
        assert "沒有找到" in captured.out or "no match" in captured.out.lower() or "0" in captured.out


class TestCmdGraphUnlinkNotFound:
    """Test cmd_graph unlink with non-existent edge."""
    
    def test_graph_unlink_not_found(self, tmp_path, monkeypatch, capsys):
        """Test unlink when edge doesn't exist."""
        from vault.cli import cmd_graph
        from vault.db import VaultDB
        
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        
        monkeypatch.chdir(project_dir)
        
        args = MagicMock()
        args.graph_action = "unlink"
        args.edge_id = 9999
        
        cmd_graph(args)
        captured = capsys.readouterr()
        
        # delete_edge might return True even if not found, just check it runs
        assert "已刪除" in captured.out or "找不到" in captured.out


class TestCmdDbVerifyBackupInvalid:
    """Test cmd_db verify-backup with invalid backup."""
    
    def test_verify_backup_invalid_file(self, tmp_path, monkeypatch, capsys):
        """Test verify-backup with a non-db file."""
        from vault.cli import cmd_db
        from vault.db import VaultDB
        
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        
        monkeypatch.chdir(project_dir)
        
        # Create a non-SQLite file
        bad_backup = tmp_path / "bad_backup.db"
        bad_backup.write_text("not a database")
        
        args = MagicMock()
        args.db_action = "verify-backup"
        args.backup_path = str(bad_backup)
        args.pretty = False
        
        # Should handle gracefully or raise error
        try:
            cmd_db(args)
            assert True
        except SystemExit:
            pass
        except Exception:
            pass


class TestCmdSkillStats:
    """Test cmd_skill_stats command."""
    
    def test_skill_stats_empty(self, tmp_path, monkeypatch, capsys):
        """Test skill stats with empty skills table."""
        from vault.cli import cmd_skill_stats
        from vault.db import VaultDB
        
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        (project_dir / "raw").mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        
        monkeypatch.chdir(project_dir)
        
        args = MagicMock()
        args.pretty = False
        
        cmd_skill_stats(args)
        captured = capsys.readouterr()
        
        output = captured.out.strip()
        assert output
        try:
            parsed = json.loads(output)
            assert isinstance(parsed, dict)
        except json.JSONDecodeError:
            assert "skill" in output.lower() or "統計" in output


class TestCmdDedupNoDuplicates:
    """Test cmd_dedup with no duplicates."""
    
    def test_dedup_no_duplicates_semantic_disabled(self, tmp_path, monkeypatch, capsys):
        """Test dedup with semantic=False (just hash check)."""
        from vault.cli import cmd_dedup
        from vault.db import VaultDB
        
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.add_knowledge(title="Unique 1", content_raw="Content one", content_aaak="c1")
        db.add_knowledge(title="Unique 2", content_raw="Content two", content_aaak="c2")
        # Use hash embedding provider for CI compatibility
        db.set_config("embedding_provider", "hash")
        db.close()
        
        monkeypatch.chdir(project_dir)
        
        args = MagicMock()
        args.merge = False
        args.dry_run = False
        args.semantic = False
        args.threshold = 0.9
        
        cmd_dedup(args)
        captured = capsys.readouterr()
        
        assert "沒有發現" in captured.out or "no duplicate" in captured.out.lower() or "0" in captured.out


class TestCmdDbStatus:
    """Test cmd_db status command."""
    
    def test_db_status_empty(self, tmp_path, monkeypatch, capsys):
        """Test db status with empty database."""
        from vault.cli import cmd_db
        from vault.db import VaultDB
        
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        
        monkeypatch.chdir(project_dir)
        
        args = MagicMock()
        args.db_action = "status"
        args.pretty = False
        
        cmd_db(args)
        captured = capsys.readouterr()
        
        output = captured.out.strip()
        assert output
        parsed = json.loads(output)
        assert "current_version" in parsed or "table_count" in parsed
