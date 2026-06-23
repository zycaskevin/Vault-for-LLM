"""Targeted CLI tests to cover specific untested code paths."""

import json
import pytest
import os
import sys
import tempfile
from pathlib import Path
from argparse import Namespace
from unittest.mock import patch, MagicMock
from io import StringIO


@pytest.fixture
def empty_project(tmp_path):
    """Create an empty project directory (no DB)."""
    return tmp_path


@pytest.fixture
def initialized_project(tmp_path):
    """Create a freshly initialized vault project."""
    from vault.db import VaultDB
    
    project_dir = tmp_path / "vault-project"
    project_dir.mkdir()
    
    # Initialize DB
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
    
    # Use hash embedding provider for tests (works without external dependencies)
    db.set_config("embedding_provider", "hash")
    
    db.close()
    
    # Create required dirs
    (project_dir / "raw").mkdir(exist_ok=True)
    (project_dir / "compiled").mkdir(exist_ok=True)
    
    return project_dir


class TestCmdInit:
    """Test cmd_init edge cases."""
    
    def test_init_with_existing_gitignore(self, tmp_path, monkeypatch, capsys):
        """Test init when .gitignore already exists."""
        from vault.cli import cmd_init
        
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        
        # Create pre-existing .gitignore
        gitignore = project_dir / ".gitignore"
        gitignore.write_text("*.log\n*.tmp\n")
        
        monkeypatch.chdir(tmp_path)
        args = MagicMock()
        args.project_dir = str(project_dir)
        cmd_init(args)
        captured = capsys.readouterr()
        
        # Check that gitignore was updated with vault entries
        content = gitignore.read_text()
        assert "*.db" in content
        assert "__pycache__/" in content
        assert "*.log" in content  # Original content preserved


class TestCmdAdd:
    """Test cmd_add edge cases."""
    
    def test_add_with_stdin_content(self, initialized_project, monkeypatch, capsys):
        """Test add when content comes from stdin."""
        from vault.cli import cmd_add
        
        monkeypatch.chdir(initialized_project)
        
        # Mock stdin
        input_content = "Content from stdin for testing."
        monkeypatch.setattr(sys, 'stdin', StringIO(input_content))
        
        args = MagicMock()
        args.title = "Stdin Test Entry"
        args.content = None
        args.category = "test"
        args.tags = "stdin,test"
        args.layer = "L3"
        args.trust = 0.5
        args.source = "cli"
        args.source_ref = None
        args.file = None
        args.edit = False
        
        cmd_add(args)
        captured = capsys.readouterr()
        
        # Verify entry was added
        from vault.db import VaultDB
        db = VaultDB(str(initialized_project / "vault.db"))
        db.connect()
        entries = db.list_knowledge()
        db.close()
        
        titles = [e["title"] for e in entries]
        assert "Stdin Test Entry" in titles

    def test_add_with_file(self, initialized_project, tmp_path, monkeypatch, capsys):
        """Test add with file input."""
        from vault.cli import cmd_add
        
        # Create a test file
        test_file = tmp_path / "test_content.md"
        test_file.write_text("Content from file for testing.")
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.title = "File Test Entry"
        args.content = None
        args.category = "test"
        args.tags = "file,test"
        args.layer = "L3"
        args.trust = 0.5
        args.source = "cli"
        args.source_ref = None
        args.file = str(test_file)
        args.edit = False
        
        cmd_add(args)
        captured = capsys.readouterr()
        
        from vault.db import VaultDB
        db = VaultDB(str(initialized_project / "vault.db"))
        db.connect()
        entries = db.list_knowledge()
        entry = next((e for e in entries if e["title"] == "File Test Entry"), None)
        db.close()
        
        assert entry is not None
        assert "Content from file" in entry["content_raw"]


class TestCmdCompile:
    """Test cmd_compile edge cases."""
    
    def test_compile_no_embed(self, initialized_project, monkeypatch, capsys):
        """Test compile with no_embed flag."""
        from vault.cli import cmd_compile
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.id = None
        args.all = True
        args.force = False
        args.no_embed = True
        args.strategy = "chapter"
        args.chunk_size = 500
        args.overlap = 100
        args.layer = None
        args.no_semantic = False
        args.dry_run = False
        
        cmd_compile(args)
        captured = capsys.readouterr()
        assert captured.out is not None

    def test_compile_specific_id(self, initialized_project, monkeypatch, capsys):
        """Test compile with specific entry ID."""
        from vault.cli import cmd_compile
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.id = 1
        args.all = False
        args.force = False
        args.no_embed = True
        args.strategy = "chapter"
        args.chunk_size = 500
        args.overlap = 100
        args.layer = None
        args.no_semantic = False
        args.dry_run = False
        
        cmd_compile(args)
        captured = capsys.readouterr()
        assert captured.out is not None

    def test_compile_dry_run(self, initialized_project, monkeypatch, capsys):
        """Test compile with dry_run flag."""
        from vault.cli import cmd_compile
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.id = None
        args.all = True
        args.force = False
        args.no_embed = True
        args.strategy = "chapter"
        args.chunk_size = 500
        args.overlap = 100
        args.layer = None
        args.no_semantic = False
        args.dry_run = True
        
        cmd_compile(args)
        captured = capsys.readouterr()
        assert captured.out is not None


class TestCmdSearch:
    """Test cmd_search edge cases."""
    
    def test_search_keyword_mode(self, initialized_project, monkeypatch, capsys):
        """Test search with keyword mode."""
        from vault.cli import cmd_search
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.query = "test"
        args.mode = "keyword"
        args.keyword_only = True
        args.no_embed = True
        args.graph_expand = 0
        args.limit = 10
        args.min_trust = 0.0
        args.layer = None
        args.category = None
        args.use_rerank = False
        args.compact = False
        args.semantic_vector_kind = "claim"
        
        cmd_search(args)
        captured = capsys.readouterr()
        assert captured.out is not None

    def test_search_with_min_trust(self, initialized_project, monkeypatch, capsys):
        """Test search with min_trust filter."""
        from vault.cli import cmd_search
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.query = "test"
        args.mode = "keyword"
        args.keyword_only = True
        args.no_embed = True
        args.graph_expand = 0
        args.limit = 10
        args.min_trust = 0.7
        args.layer = None
        args.category = None
        args.use_rerank = False
        args.compact = False
        args.semantic_vector_kind = "claim"
        
        cmd_search(args)
        captured = capsys.readouterr()
        assert captured.out is not None

    def test_search_compact_output(self, initialized_project, monkeypatch, capsys):
        """Test search with compact output."""
        from vault.cli import cmd_search
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.query = "entry"
        args.mode = "keyword"
        args.keyword_only = True
        args.no_embed = True
        args.graph_expand = 0
        args.limit = 5
        args.min_trust = 0.0
        args.layer = None
        args.category = None
        args.use_rerank = False
        args.compact = True
        args.semantic_vector_kind = "claim"
        
        cmd_search(args)
        captured = capsys.readouterr()
        assert captured.out is not None

    def test_search_json_output(self, initialized_project, monkeypatch, capsys):
        """Test machine-readable search output for agents."""
        from vault.cli import cmd_search

        monkeypatch.chdir(initialized_project)
        args = Namespace(
            query="test",
            mode="keyword",
            keyword_only=True,
            graph_expand=0,
            limit=3,
            min_trust=0.0,
            min_score=None,
            layer=None,
            category=None,
            semantic_vector_kind="claim",
            allow_hash=False,
            hash_dim=32,
            no_rerank=True,
            agent_id="",
            include_private=False,
            max_sensitivity="",
            json=True,
            pretty=True,
        )

        cmd_search(args)
        payload = json.loads(capsys.readouterr().out)

        assert payload["query"] == "test"
        assert payload["requested_mode"] == "keyword"
        assert payload["mode"] == "keyword_fts"
        assert payload["count"] <= 3
        assert payload["results"]
        assert payload["results"][0]["title"].startswith("Test Entry")


class TestCmdGraph:
    """Test cmd_graph edge cases."""
    
    def test_graph_stats(self, initialized_project, monkeypatch, capsys):
        """Test graph stats."""
        from vault.cli import cmd_graph
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.db_action = "status"
        args.id = None
        args.depth = 2
        args.direction = "both"
        args.infer = False
        args.clear_auto = False
        args.output = "text"
        args.mermaid = False
        
        cmd_graph(args)
        captured = capsys.readouterr()
        assert captured.out is not None

    def test_graph_expand_with_id(self, initialized_project, monkeypatch, capsys):
        """Test graph expand with specific ID."""
        from vault.cli import cmd_graph
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.command = "expand"
        args.id = 1
        args.depth = 2
        args.direction = "both"
        args.infer = False
        args.clear_auto = False
        args.output = "text"
        args.mermaid = False
        
        cmd_graph(args)
        captured = capsys.readouterr()
        assert captured.out is not None

    def test_graph_infer_all(self, initialized_project, monkeypatch, capsys):
        """Test graph infer on all entries."""
        from vault.cli import cmd_graph
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.command = "infer"
        args.id = None
        args.depth = 2
        args.direction = "both"
        args.infer = True
        args.clear_auto = False
        args.output = "text"
        args.mermaid = False
        
        cmd_graph(args)
        captured = capsys.readouterr()
        assert captured.out is not None

    def test_graph_mermaid_output(self, initialized_project, monkeypatch, capsys):
        """Test graph with mermaid output."""
        from vault.cli import cmd_graph
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.command = "expand"
        args.id = 1
        args.depth = 2
        args.direction = "both"
        args.infer = False
        args.clear_auto = False
        args.output = "text"
        args.mermaid = True
        
        cmd_graph(args)
        captured = capsys.readouterr()
        assert captured.out is not None


class TestCmdMap:
    """Test cmd_map command."""
    
    def test_map_show(self, initialized_project, monkeypatch, capsys):
        """Test map show subcommand."""
        from vault.cli import cmd_map
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.action = "show"
        args.id = 1
        args.compact = False
        args.lines = None
        args.node = None
        
        cmd_map(args)
        captured = capsys.readouterr()
        assert captured.out is not None

    def test_map_show_compact(self, initialized_project, monkeypatch, capsys):
        """Test map show with compact mode."""
        from vault.cli import cmd_map
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.action = "show"
        args.id = 1
        args.compact = True
        args.lines = None
        args.node = None
        
        cmd_map(args)
        captured = capsys.readouterr()
        assert captured.out is not None

    def test_map_build(self, initialized_project, monkeypatch, capsys):
        """Test map build subcommand."""
        from vault.cli import cmd_map
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.action = "build"
        args.id = None
        args.compact = False
        args.lines = None
        args.node = None
        
        cmd_map(args)
        captured = capsys.readouterr()
        assert captured.out is not None


class TestCmdDb:
    """Test cmd_db command."""
    
    def test_db_stats(self, initialized_project, monkeypatch, capsys):
        """Test db stats subcommand."""
        from vault.cli import cmd_db
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.db_action = "status"
        
        cmd_db(args)
        captured = capsys.readouterr()
        assert captured.out is not None




class TestCmdLint:
    """Test cmd_lint command."""
    
    def test_lint_all(self, initialized_project, monkeypatch, capsys):
        """Test lint on all entries."""
        from vault.cli import cmd_lint
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.id = None
        args.all = True
        args.fix = False
        
        cmd_lint(args)
        captured = capsys.readouterr()
        assert captured.out is not None

    def test_lint_specific_id(self, initialized_project, monkeypatch, capsys):
        """Test lint on specific entry."""
        from vault.cli import cmd_lint
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.id = 1
        args.all = False
        args.fix = False
        
        cmd_lint(args)
        captured = capsys.readouterr()
        assert captured.out is not None


class TestCmdDoctor:
    """Test cmd_doctor command."""
    
    def test_doctor_no_fix(self, initialized_project, monkeypatch, capsys):
        """Test doctor without fix."""
        from vault.cli import cmd_doctor
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.fix = False
        
        cmd_doctor(args)
        captured = capsys.readouterr()
        assert captured.out is not None


class TestCmdRemember:
    """Test cmd_remember command."""
    
    def test_remember_basic(self, initialized_project, monkeypatch, capsys):
        """Test remember basic functionality."""
        from vault.cli import cmd_remember
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.content = "A test memory to remember."
        args.title = "Test Memory"
        args.category = "general"
        args.tags = "test,memory"
        args.source = "test"
        args.file = None
        args.reason = "testing purposes"
        args.source_ref = None
        
        cmd_remember(args)
        captured = capsys.readouterr()
        assert captured.out is not None


class TestCmdDream:
    """Test cmd_dream command."""
    
    def test_dream_report_mode(self, initialized_project, monkeypatch, capsys):
        """Test dream in report mode."""
        from vault.cli import cmd_dream
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.mode = "report"
        args.limit = 5
        args.checks = None
        args.write_report = False
        args.backup = False
        
        cmd_dream(args)
        captured = capsys.readouterr()
        assert captured.out is not None


class TestCmdFreshness:
    """Test cmd_freshness command."""
    
    def test_freshness_all(self, initialized_project, monkeypatch, capsys):
        """Test freshness check on all entries."""
        from vault.cli import cmd_freshness
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.id = None
        args.all = True
        args.days = 30
        args.apply = False
        args.limit = 0
        args.stale_only = False
        
        cmd_freshness(args)
        captured = capsys.readouterr()
        assert captured.out is not None


class TestCmdDedup:
    """Test cmd_dedup command."""
    
    def test_dedup_dry_run(self, initialized_project, monkeypatch, capsys):
        """Test dedup with dry run."""
        from vault.cli import cmd_dedup
        
        monkeypatch.chdir(initialized_project)
        args = MagicMock()
        args.dry_run = True
        args.threshold = 0.9
        
        cmd_dedup(args)
        captured = capsys.readouterr()
        assert captured.out is not None


class TestMiscHelpers:
    """Test miscellaneous CLI helper functions."""
    
    def test_positive_int_valid(self):
        """Test _positive_int with valid values."""
        from vault.cli import _positive_int
        assert _positive_int("1") == 1
        assert _positive_int("100") == 100
        assert _positive_int("999") == 999

    def test_positive_int_zero(self):
        """Test _positive_int with zero - should raise."""
        from vault.cli import _positive_int
        import argparse
        
        with pytest.raises(argparse.ArgumentTypeError):
            _positive_int("0")

    def test_positive_int_negative(self):
        """Test _positive_int with negative number."""
        from vault.cli import _positive_int
        import argparse
        
        with pytest.raises(argparse.ArgumentTypeError):
            _positive_int("-5")

    def test_positive_int_non_numeric(self):
        """Test _positive_int with non-numeric input."""
        from vault.cli import _positive_int
        import argparse
        
        with pytest.raises(argparse.ArgumentTypeError):
            _positive_int("abc")

    def test_json_print_dict(self, capsys):
        """Test _json_print with dict."""
        from vault.cli import _json_print
        
        _json_print({"key": "value", "number": 42}, pretty=False)
        captured = capsys.readouterr()
        assert "key" in captured.out
        assert "value" in captured.out

    def test_json_print_list(self, capsys):
        """Test _json_print with list."""
        from vault.cli import _json_print
        
        _json_print([{"id": 1}, {"id": 2}], pretty=False)
        captured = capsys.readouterr()
        assert "1" in captured.out
        assert "2" in captured.out

    def test_json_print_pretty(self, capsys):
        """Test _json_print with pretty mode."""
        from vault.cli import _json_print
        
        _json_print({"test": "value"}, pretty=True)
        captured = capsys.readouterr()
        assert "test" in captured.out
        assert "\n" in captured.out

    def test_find_project_dir_from_cwd(self, initialized_project, monkeypatch):
        """Test find_project_dir finds vault.db in cwd."""
        from vault.cli import find_project_dir
        
        monkeypatch.chdir(initialized_project)
        result = find_project_dir()
        assert result == initialized_project

    def test_find_project_dir_from_parent(self, initialized_project, monkeypatch):
        """Test find_project_dir looks in parent directories."""
        from vault.cli import find_project_dir
        
        # Create a subdirectory
        subdir = initialized_project / "subdir" / "nested"
        subdir.mkdir(parents=True)
        
        monkeypatch.chdir(subdir)
        result = find_project_dir()
        assert result == initialized_project
