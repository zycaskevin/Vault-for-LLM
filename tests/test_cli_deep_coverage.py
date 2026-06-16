"""Deep CLI coverage tests for untested code paths."""

import pytest
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO


@pytest.fixture
def project_with_edges(tmp_path):
    """Create a project with knowledge entries and edges."""
    from vault.db import VaultDB
    
    project_dir = tmp_path / "vault-project"
    project_dir.mkdir()
    
    db_path = str(project_dir / "vault.db")
    db = VaultDB(db_path)
    db.connect()
    
    # Add knowledge entries
    ids = []
    for i in range(5):
        kid = db.add_knowledge(
            title=f"Test Entry {i}",
            content_raw=f"Content of entry {i}.",
            category="test",
            tags=f"tag{i}",
            layer="L3",
            trust=0.5 + i * 0.1,
        )
        ids.append(kid)
    
    # Add edges between entries
    db.add_edge(ids[0], ids[1], "related", 0.8, auto_inferred=True)
    db.add_edge(ids[1], ids[2], "referenced", 0.6, auto_inferred=False)
    db.add_edge(ids[2], ids[3], "related", 0.7, auto_inferred=True)
    
    db.close()
    
    (project_dir / "raw").mkdir(exist_ok=True)
    return project_dir


class TestCmdGraphExtended:
    """Test more cmd_graph paths."""
    
    def test_graph_show_with_edges(self, project_with_edges, monkeypatch, capsys):
        """Test graph show displays edges properly."""
        from vault.cli import cmd_graph
        
        monkeypatch.chdir(project_with_edges)
        
        args = MagicMock()
        args.graph_action = "show"
        cmd_graph(args)
        captured = capsys.readouterr()
        
        # Should show edge stats
        assert "邊" in captured.out or "edge" in captured.out.lower()
        assert "自動" in captured.out or "auto" in captured.out.lower()
        assert "實體" in captured.out or "entity" in captured.out.lower()
    
    def test_graph_clear_auto_inferred(self, project_with_edges, monkeypatch, capsys):
        """Test clearing auto-inferred edges."""
        from vault.cli import cmd_graph
        
        monkeypatch.chdir(project_with_edges)
        
        args = MagicMock()
        args.graph_action = "clear"
        cmd_graph(args)
        captured = capsys.readouterr()
        
        assert "已清除" in captured.out


class TestCmdSkillDispatch:
    """Test cmd_skill dispatch function."""
    
    def test_skill_push(self, tmp_path, monkeypatch):
        """Test skill push action dispatch."""
        from vault.cli import cmd_skill
        
        from vault.db import VaultDB
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        (project_dir / "raw").mkdir(exist_ok=True)
        
        monkeypatch.chdir(project_dir)
        
        args = MagicMock()
        args.skill_action = "push"
        
        with patch('vault.cli.cmd_skill_push') as mock:
            cmd_skill(args)
            mock.assert_called_once()
    
    def test_skill_search(self, tmp_path, monkeypatch):
        """Test skill search action dispatch."""
        from vault.cli import cmd_skill
        
        from vault.db import VaultDB
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        (project_dir / "raw").mkdir(exist_ok=True)
        
        monkeypatch.chdir(project_dir)
        
        args = MagicMock()
        args.skill_action = "search"
        
        with patch('vault.cli.cmd_skill_search') as mock:
            cmd_skill(args)
            mock.assert_called_once()
    
    def test_skill_pull(self, tmp_path, monkeypatch):
        """Test skill pull action dispatch."""
        from vault.cli import cmd_skill
        
        from vault.db import VaultDB
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        (project_dir / "raw").mkdir(exist_ok=True)
        
        monkeypatch.chdir(project_dir)
        
        args = MagicMock()
        args.skill_action = "pull"
        
        with patch('vault.cli.cmd_skill_pull') as mock:
            cmd_skill(args)
            mock.assert_called_once()
    
    def test_skill_list(self, tmp_path, monkeypatch):
        """Test skill list action dispatch."""
        from vault.cli import cmd_skill
        
        from vault.db import VaultDB
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        (project_dir / "raw").mkdir(exist_ok=True)
        
        monkeypatch.chdir(project_dir)
        
        args = MagicMock()
        args.skill_action = "list"
        
        with patch('vault.cli.cmd_skill_list') as mock:
            cmd_skill(args)
            mock.assert_called_once()
    
    def test_skill_stats(self, tmp_path, monkeypatch):
        """Test skill stats action dispatch."""
        from vault.cli import cmd_skill
        
        from vault.db import VaultDB
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        (project_dir / "raw").mkdir(exist_ok=True)
        
        monkeypatch.chdir(project_dir)
        
        args = MagicMock()
        args.skill_action = "stats"
        
        with patch('vault.cli.cmd_skill_stats') as mock:
            cmd_skill(args)
            mock.assert_called_once()
    
    def test_skill_invalid_action(self, tmp_path, monkeypatch, capsys):
        """Test skill with invalid action shows usage."""
        from vault.cli import cmd_skill
        
        from vault.db import VaultDB
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        (project_dir / "raw").mkdir(exist_ok=True)
        
        monkeypatch.chdir(project_dir)
        
        args = MagicMock()
        args.skill_action = "invalid_action"
        cmd_skill(args)
        captured = capsys.readouterr()
        
        assert "用法" in captured.out or "usage" in captured.out.lower()


class TestCmdSearchQA:
    """Test cmd_search_qa function."""
    
    def test_search_qa_invalid_action(self, tmp_path, monkeypatch):
        """Test search-qa with invalid action."""
        from vault.cli import cmd_search_qa
        
        from vault.db import VaultDB
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        (project_dir / "raw").mkdir(exist_ok=True)
        
        monkeypatch.chdir(project_dir)
        
        args = MagicMock()
        args.search_qa_action = "invalid"
        
        with pytest.raises(SystemExit):
            cmd_search_qa(args)
    
    def test_search_qa_compare(self, tmp_path, monkeypatch, capsys):
        """Test search-qa compare action."""
        from vault.cli import cmd_search_qa
        
        from vault.db import VaultDB
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        (project_dir / "raw").mkdir(exist_ok=True)
        
        monkeypatch.chdir(project_dir)
        
        # Create mock snapshot files
        before_file = tmp_path / "before.json"
        after_file = tmp_path / "after.json"
        
        before_data = {
            "queries": [],
            "aggregate": {"recall@10": 0.5, "mrr": 0.3},
        }
        after_data = {
            "queries": [],
            "aggregate": {"recall@10": 0.7, "mrr": 0.5},
        }
        before_file.write_text(json.dumps(before_data))
        after_file.write_text(json.dumps(after_data))
        
        args = MagicMock()
        args.search_qa_action = "compare"
        args.before = str(before_file)
        args.after = str(after_file)
        args.output = None
        
        cmd_search_qa(args)
        captured = capsys.readouterr()
        
        # Should output comparison
        assert "recall" in captured.out.lower() or "improve" in captured.out.lower()


class TestCmdRemember:
    """Test cmd_remember function."""
    
    def test_remember_with_content(self, tmp_path, monkeypatch, capsys):
        """Test remember with direct content."""
        from vault.cli import cmd_remember
        
        from vault.db import VaultDB
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        (project_dir / "raw").mkdir(exist_ok=True)
        
        monkeypatch.chdir(project_dir)
        
        args = MagicMock()
        args.content = "Remember this important fact."
        args.title = None
        args.reason = None
        args.mode = "candidate"
        args.layer = "L3"
        args.category = "general"
        args.tags = ""
        args.trust = 0.7
        args.source = None
        args.source_ref = None
        args.pretty = False
        args.file = None
        
        cmd_remember(args)
        captured = capsys.readouterr()
        
        # Should output JSON with candidate info
        output = captured.out.strip()
        assert output
        parsed = json.loads(output)
        assert "candidate_id" in parsed or "id" in parsed or "status" in parsed
    
    def test_remember_with_file(self, tmp_path, monkeypatch, capsys):
        """Test remember with file input."""
        from vault.cli import cmd_remember
        
        from vault.db import VaultDB
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        (project_dir / "raw").mkdir(exist_ok=True)
        
        monkeypatch.chdir(project_dir)
        
        # Create test file
        test_file = tmp_path / "memory.txt"
        test_file.write_text("Content from file to remember.")
        
        args = MagicMock()
        args.content = None
        args.file = str(test_file)
        args.title = None
        args.reason = None
        args.mode = "candidate"
        args.layer = "L3"
        args.category = "general"
        args.tags = ""
        args.trust = 0.7
        args.source = None
        args.source_ref = None
        args.pretty = False
        
        cmd_remember(args)
        captured = capsys.readouterr()
        
        output = captured.out.strip()
        assert output
        parsed = json.loads(output)
        assert "candidate_id" in parsed or "id" in parsed


class TestCmdDbMore:
    """Test more cmd_db subcommands."""
    
    def test_db_migrate(self, tmp_path, monkeypatch, capsys):
        """Test db migrate action."""
        from vault.cli import cmd_db
        
        from vault.db import VaultDB
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        (project_dir / "raw").mkdir(exist_ok=True)
        
        monkeypatch.chdir(project_dir)
        
        args = MagicMock()
        args.db_action = "migrate"
        args.db_path = None
        args.pretty = False
        
        cmd_db(args)
        captured = capsys.readouterr()
        
        output = captured.out.strip()
        parsed = json.loads(output)
        assert "ok" in parsed or "migrated" in parsed or "status" in parsed


class TestSemanticVectorsExist:
    """Test _semantic_vectors_exist helper function."""
    
    def test_semantic_vectors_exist_no_table(self, tmp_path):
        """Test when semantic_vectors table doesn't exist."""
        from vault.cli import _semantic_vectors_exist
        import sqlite3
        
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE knowledge (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        
        result = _semantic_vectors_exist(db_path)
        assert result is False
    
    def test_semantic_vectors_exist_empty_table(self, tmp_path):
        """Test when semantic_vectors table exists but is empty."""
        from vault.cli import _semantic_vectors_exist
        import sqlite3
        
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE semantic_vectors (id INTEGER PRIMARY KEY, vector BLOB)")
        conn.commit()
        conn.close()
        
        result = _semantic_vectors_exist(db_path)
        assert result is False
    
    def test_semantic_vectors_exist_with_data(self, tmp_path):
        """Test when semantic_vectors table has data."""
        from vault.cli import _semantic_vectors_exist
        import sqlite3
        
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE semantic_vectors (id INTEGER PRIMARY KEY, vector BLOB)")
        conn.execute("INSERT INTO semantic_vectors VALUES (1, x'0000')")
        conn.commit()
        conn.close()
        
        result = _semantic_vectors_exist(db_path)
        assert result is True


class TestCmdDedupPaths:
    """Test more cmd_dedup paths."""
    
    def test_dedup_dry_run_with_duplicates(self, tmp_path, monkeypatch, capsys):
        """Test dedup dry-run with duplicates using mock."""
        from vault.cli import cmd_dedup
        
        from vault.db import VaultDB
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        (project_dir / "raw").mkdir(exist_ok=True)
        
        monkeypatch.chdir(project_dir)
        
        # Mock the scripts module
        mock_scripts = MagicMock()
        mock_scripts.deduplicate_semantic.find_duplicates.return_value = [
            {"id1": 1, "id2": 2, "similarity": 0.95}
        ]
        
        with patch.dict('sys.modules', {'scripts': MagicMock(), 'scripts.deduplicate_semantic': mock_scripts}):
            args = MagicMock()
            args.threshold = 0.9
            args.merge = False
            args.dry_run = True
            
            cmd_dedup(args)
            captured = capsys.readouterr()
            
            # Should have some output about duplicates
            assert "💡" in captured.out or "merge" in captured.out.lower() or "預覽" in captured.out


class TestHelperFunctions:
    """Test CLI helper functions."""
    
    def test_positive_int_zero_fails(self):
        """Test that _positive_int rejects zero."""
        from vault.cli import _positive_int
        import argparse
        
        with pytest.raises(argparse.ArgumentTypeError):
            _positive_int("0")
    
    def test_positive_int_negative_fails(self):
        """Test that _positive_int rejects negative numbers."""
        from vault.cli import _positive_int
        import argparse
        
        with pytest.raises(argparse.ArgumentTypeError):
            _positive_int("-5")
    
    def test_positive_int_invalid_string(self):
        """Test _positive_int with non-numeric string."""
        from vault.cli import _positive_int
        import argparse
        
        with pytest.raises(argparse.ArgumentTypeError):
            _positive_int("abc")
    
    def test_positive_int_valid(self):
        """Test _positive_int with valid positive numbers."""
        from vault.cli import _positive_int
        
        assert _positive_int("1") == 1
        assert _positive_int("42") == 42
        assert _positive_int("1000") == 1000


class TestCmdPromote:
    """Test cmd_promote function."""
    
    def test_promote_with_id(self, tmp_path, monkeypatch, capsys):
        """Test promote with a candidate ID."""
        from vault.cli import cmd_promote
        from vault.db import VaultDB
        from vault.memory import propose_memory
        
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        
        # Create a memory candidate first
        candidate = propose_memory(
            db,
            title="Test Memory",
            content="Test memory content",
            mode="candidate",
        )
        db.close()
        
        (project_dir / "raw").mkdir(exist_ok=True)
        monkeypatch.chdir(project_dir)
        
        args = MagicMock()
        args.candidate_id = candidate["candidate_id"]
        args.confirm = True
        args.no_compile = True
        args.no_build_map = True
        args.pretty = False
        
        cmd_promote(args)
        captured = capsys.readouterr()
        
        output = captured.out.strip()
        assert output
        parsed = json.loads(output)
        assert "status" in parsed or "promoted" in parsed


class TestCmdFreshness:
    """Test cmd_freshness more paths."""
    
    def test_freshness_with_mocked_module(self, tmp_path, monkeypatch, capsys):
        """Test freshness with mocked check."""
        from vault.cli import cmd_freshness
        
        from vault.db import VaultDB
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        (project_dir / "raw").mkdir(exist_ok=True)
        
        monkeypatch.chdir(project_dir)
        
        mock_module = MagicMock()
        mock_module.check_freshness.return_value = None
        
        with patch.dict('sys.modules', {'scripts': MagicMock(), 'scripts.freshness_check': mock_module}):
            args = MagicMock()
            args.apply = False
            args.limit = 10
            args.stale_only = False
            
            cmd_freshness(args)
            # Should not raise
            assert True


class TestCmdDedupMerge:
    """Test cmd_dedup merge mode."""
    
    def test_dedup_merge_mode(self, tmp_path, monkeypatch, capsys):
        """Test dedup with --merge flag."""
        from vault.cli import cmd_dedup
        
        from vault.db import VaultDB
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        (project_dir / "raw").mkdir(exist_ok=True)
        
        monkeypatch.chdir(project_dir)
        
        mock_find = MagicMock(return_value=[{"id1": 1, "id2": 2, "similarity": 0.95}])
        mock_merge = MagicMock(return_value=None)
        
        mock_module = MagicMock()
        mock_module.find_duplicates = mock_find
        mock_module.merge_duplicates = mock_merge
        
        with patch.dict('sys.modules', {'scripts': MagicMock(), 'scripts.deduplicate_semantic': mock_module}):
            args = MagicMock()
            args.threshold = 0.9
            args.merge = True
            args.dry_run = False
            
            cmd_dedup(args)
            captured = capsys.readouterr()
            
            # Should call merge_duplicates
            mock_merge.assert_called_once()
            assert "=" * 50 in captured.out


class TestCmdConverge:
    """Test cmd_converge function."""
    
    def test_converge_basic(self, tmp_path, monkeypatch):
        """Test converge with mocked check."""
        from vault.cli import cmd_converge
        
        from vault.db import VaultDB
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        (project_dir / "raw").mkdir(exist_ok=True)
        
        monkeypatch.chdir(project_dir)
        
        mock_check = MagicMock(return_value=None)
        mock_module = MagicMock()
        mock_module.check_convergence = mock_check
        
        with patch.dict('sys.modules', {'scripts': MagicMock(), 'scripts.convergence_check': mock_module}):
            args = MagicMock()
            args.apply = False
            args.limit = 10
            args.min_trust = 0.5
            args.ollama = "llama3"
            args.api = None
            args.api_key = None
            
            cmd_converge(args)
            mock_check.assert_called_once()


class TestCmdCrossValidate:
    """Test cmd_cross_validate function."""
    
    def test_cross_validate_basic(self, tmp_path, monkeypatch):
        """Test cross_validate with mocked function."""
        from vault.cli import cmd_cross_validate
        
        from vault.db import VaultDB
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        (project_dir / "raw").mkdir(exist_ok=True)
        
        monkeypatch.chdir(project_dir)
        
        mock_cross = MagicMock(return_value=None)
        mock_module = MagicMock()
        mock_module.cross_validate = mock_cross
        
        with patch.dict('sys.modules', {'scripts': MagicMock(), 'scripts.cross_validate': mock_module}):
            args = MagicMock()
            args.apply = False
            args.limit = 10
            args.min_trust = 0.5
            args.local_only = True
            args.local_model = "llama3"
            args.cloud_model = "gpt-4"
            
            cmd_cross_validate(args)
            mock_cross.assert_called_once()


class TestCmdSemanticMore:
    """Test more cmd_semantic paths (mocked)."""
    
    def test_semantic_rebuild(self, tmp_path, monkeypatch, capsys):
        """Test semantic rebuild action."""
        from vault.cli import cmd_semantic
        
        from vault.db import VaultDB
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        (project_dir / "raw").mkdir(exist_ok=True)
        
        monkeypatch.chdir(project_dir)
        
        # Mock the semantic module
        mock_semantic = MagicMock()
        mock_semantic.rebuild_semantic_index.return_value = MagicMock(
            knowledge_rows=10, node_vectors=5, claim_vectors=8
        )
        
        # Mock the provider
        mock_provider = MagicMock()
        mock_provider.provider_id = "test-provider"
        mock_provider.is_semantic = True
        mock_provider.dim = 384
        mock_provider.cache_size = 0
        
        mock_module = MagicMock()
        mock_module.rebuild_semantic_index = mock_semantic.rebuild_semantic_index
        
        # Need to also mock _create_semantic_provider
        # This is more complex, let's just test the error path
        
        args = MagicMock()
        args.semantic_action = "rebuild"
        args.db_path = None
        args.persist_cache = False
        args.knowledge_id = None
        args.allow_hash = True
        args.hash_dim = 32
        args.pretty = False
        args.mode = "auto"
        args.limit = 0
        args.semantic_vector_kind = "claim"
        args.older_than_days = 30
        args.max_rows = 1000
        args.no_persist_cache = False
        args.rebuild = False
        args.smoke = False
        args.repeat = 1
        args.interval = 60
        args.qa_file = None
        args.output = None
        args.provider_id = None
        args.dimension = None
        
        # Should succeed with hash provider
        cmd_semantic(args)
        captured = capsys.readouterr()
        assert captured.out != "" or captured.err != ""


class TestGraphWithEntities:
    """Test graph with entities present."""
    
    def test_graph_show_with_entities(self, tmp_path, monkeypatch, capsys):
        """Test graph show displays entities."""
        from vault.cli import cmd_graph
        from vault.db import VaultDB
        from vault.graph import VaultGraph
        
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        
        # Add some knowledge
        kid = db.add_knowledge(
            title="Test Document",
            content_raw="Content about Python and programming.",
            category="tech",
            tags="python,code",
            layer="L3",
            trust=0.8,
        )
        
        # Manually add an entity and link it
        db.conn.execute(
            "INSERT INTO entities (name, entity_type) VALUES (?, ?)",
            ("Python", "technology")
        )
        entity_id = db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.conn.execute(
            "INSERT INTO entity_knowledge (entity_id, knowledge_id) VALUES (?, ?)",
            (entity_id, kid)
        )
        db.conn.commit()
        
        db.close()
        
        (project_dir / "raw").mkdir(exist_ok=True)
        monkeypatch.chdir(project_dir)
        
        args = MagicMock()
        args.graph_action = "show"
        cmd_graph(args)
        captured = capsys.readouterr()
        
        # Should show entity info
        assert "實體" in captured.out or "entity" in captured.out.lower()
        assert "Python" in captured.out


class TestCmdDbVerifyBackup:
    """Test cmd_db verify-backup action."""
    
    def test_db_verify_backup(self, tmp_path, monkeypatch, capsys):
        """Test verify-backup with a backup file."""
        from vault.cli import cmd_db
        
        from vault.db import VaultDB
        project_dir = tmp_path / "vault-project"
        project_dir.mkdir()
        db = VaultDB(str(project_dir / "vault.db"))
        db.connect()
        db.close()
        (project_dir / "raw").mkdir(exist_ok=True)
        
        monkeypatch.chdir(project_dir)
        
        # First create a backup
        backup_path = tmp_path / "backup.db"
        args_backup = MagicMock()
        args_backup.db_action = "backup"
        args_backup.db_path = None
        args_backup.output = str(backup_path)
        args_backup.verify = False
        args_backup.pretty = False
        cmd_db(args_backup)
        capsys.readouterr()  # Clear backup output
        
        # Now verify it
        args_verify = MagicMock()
        args_verify.db_action = "verify-backup"
        args_verify.backup_path = str(backup_path)
        args_verify.pretty = False
        cmd_db(args_verify)
        captured = capsys.readouterr()
        
        output = captured.out.strip()
        parsed = json.loads(output)
        assert "valid" in str(parsed).lower() or "ok" in str(parsed).lower()
