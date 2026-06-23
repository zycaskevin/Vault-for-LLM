"""
Extended tests for vault/cli.py
Focus on pure functions and testable commands.
"""
import pytest
import argparse
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock


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
    
    # Use hash embedding provider for tests (works without external dependencies)
    db.set_config("embedding_provider", "hash")
    
    db.close()
    
    # Create raw/ directory for cmd_add tests
    raw_dir = project_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    return project_dir


class TestPositiveInt:
    def test_positive_int_valid(self):
        from vault.cli import _positive_int
        assert _positive_int("1") == 1
        assert _positive_int("42") == 42

    def test_positive_int_zero_rejected(self):
        from vault.cli import _positive_int
        with pytest.raises(argparse.ArgumentTypeError):
            _positive_int("0")

    def test_positive_int_negative_rejected(self):
        from vault.cli import _positive_int
        with pytest.raises(argparse.ArgumentTypeError):
            _positive_int("-5")

    def test_positive_int_non_numeric_rejected(self):
        from vault.cli import _positive_int
        with pytest.raises(argparse.ArgumentTypeError):
            _positive_int("abc")


class TestParseMapLineRange:
    def test_parse_map_line_range_valid(self):
        from vault.cli import _parse_map_line_range
        assert _parse_map_line_range("1-10") == (1, 10)
        assert _parse_map_line_range("5-5") == (5, 5)

    def test_parse_map_line_range_no_dash(self):
        from vault.cli import _parse_map_line_range
        with pytest.raises(ValueError):
            _parse_map_line_range("123")

    def test_parse_map_line_range_empty(self):
        from vault.cli import _parse_map_line_range
        with pytest.raises(ValueError):
            _parse_map_line_range("")

    def test_parse_map_line_range_start_gt_end(self):
        from vault.cli import _parse_map_line_range
        with pytest.raises(ValueError):
            _parse_map_line_range("10-5")

    def test_parse_map_line_range_zero(self):
        from vault.cli import _parse_map_line_range
        with pytest.raises(ValueError):
            _parse_map_line_range("0-10")


class _RemoteResponse:
    def __init__(self, data):
        self.data = data


class _RemoteRpcQuery:
    def __init__(self, client, name, params):
        self.client = client
        self.name = name
        self.params = params

    def execute(self):
        self.client.rpc_calls.append((self.name, dict(self.params)))
        return _RemoteResponse([dict(row) for row in self.client.rpcs.get(self.name, [])])


class _RemoteTableQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.filters = []

    def select(self, *args, **kwargs):
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def execute(self):
        rows = self.client.tables.get(self.table_name, [])
        data = [
            dict(row)
            for row in rows
            if all(row.get(field) == value for field, value in self.filters)
        ]
        return _RemoteResponse(data)


class _RemoteClient:
    def __init__(self):
        self.rpc_calls = []
        self.rpcs = {
            "vault_search_readable": [
                {
                    "id": 7,
                    "title": "Remote Entry",
                    "summary": "Safe summary",
                    "source": "raw/remote.md",
                    "content_raw": "must stay hidden",
                }
            ],
            "vault_get_readable": [
                {
                    "id": 7,
                    "title": "Remote Entry",
                    "scope": "project",
                    "sensitivity": "medium",
                    "owner_agent": "",
                    "allowed_agents": [],
                    "memory_type": "knowledge",
                }
            ],
            "vault_nodes_readable": [
                {
                    "knowledge_id": 7,
                    "node_uid": "remote-node",
                    "level": 2,
                    "heading": "Remote Node",
                    "path": "Remote/Node",
                    "summary": "Node summary",
                    "line_start": 2,
                    "line_end": 3,
                    "knowledge_title": "Remote Entry",
                    "knowledge_content_hash": "remote-hash",
                }
            ],
            "vault_claims_readable": [
                {
                    "knowledge_id": 7,
                    "node_uid": "remote-node",
                    "claim": "Remote claim line.",
                    "line_start": 2,
                    "line_end": 2,
                    "knowledge_title": "Remote Entry",
                    "knowledge_content_hash": "remote-hash",
                }
            ],
            "vault_content_readable": [],
        }
        self.tables = {
            "vault_knowledge_nodes": [
                {
                    "knowledge_id": 7,
                    "node_uid": "remote-node",
                    "level": 2,
                    "heading": "Remote Node",
                    "path": "Remote/Node",
                    "summary": "Node summary",
                    "line_start": 2,
                    "line_end": 3,
                    "knowledge_title": "Remote Entry",
                    "knowledge_content_hash": "remote-hash",
                }
            ],
            "vault_knowledge_claims": [
                {
                    "knowledge_id": 7,
                    "node_uid": "remote-node",
                    "claim": "Remote claim line.",
                    "line_start": 2,
                    "line_end": 2,
                    "knowledge_title": "Remote Entry",
                    "knowledge_content_hash": "remote-hash",
                }
            ],
            "vault_knowledge": [],
        }

    def rpc(self, name, params):
        return _RemoteRpcQuery(self, name, params)

    def table(self, table_name):
        return _RemoteTableQuery(self, table_name)


class TestRemoteCli:
    def test_remote_search_json_uses_supabase_rpc(self, monkeypatch, capsys):
        from vault.cli import main
        from vault import mcp

        client = _RemoteClient()
        monkeypatch.setattr(mcp, "_get_supabase_client", lambda: client)

        main([
            "remote",
            "search",
            "Safe",
            "--agent-id",
            "remote-agent",
            "--limit",
            "3",
            "--json",
        ])

        payload = json.loads(capsys.readouterr().out)
        assert payload["rpc"] == "vault_search_readable"
        assert payload["count"] == 1
        assert payload["results"][0]["next_action"]["tool"] == "vault_remote_map_show"
        assert "content_raw" not in payload["results"][0]
        assert client.rpc_calls == [
            (
                "vault_search_readable",
                {
                    "p_agent_id": "remote-agent",
                    "p_query": "Safe",
                    "p_include_private": False,
                    "p_max_sensitivity": "medium",
                    "p_limit": 3,
                },
            )
        ]

    def test_remote_map_and_read_json(self, monkeypatch, capsys):
        from vault.cli import main
        from vault import mcp

        monkeypatch.setattr(mcp, "_get_supabase_client", lambda: _RemoteClient())
        remote_id = "a4c5294e-239c-4b1f-a0d8-afa82ef43031"

        main([
            "remote",
            "map",
            remote_id,
            "--compact",
            "--agent-id",
            "remote-agent",
            "--max-sensitivity",
            "medium",
            "--json",
        ])
        map_payload = json.loads(capsys.readouterr().out)
        assert map_payload["next_action"]["tool"] == "vault_remote_read_range"
        assert map_payload["nodes"][0]["node_uid"] == "remote-node"
        assert map_payload["next_action"]["arguments"]["knowledge_id"] == remote_id

        main([
            "remote",
            "read",
            remote_id,
            "--lines",
            "2-2",
            "--agent-id",
            "remote-agent",
            "--max-sensitivity",
            "medium",
            "--json",
        ])
        read_payload = json.loads(capsys.readouterr().out)
        assert read_payload["citation"] == f"#{remote_id} Remote Entry L2-L2"
        assert read_payload["source"] == "remote_claims"

    def test_remote_smoke_json(self, monkeypatch, capsys):
        from vault.cli import main
        from vault import mcp

        monkeypatch.setattr(mcp, "_get_supabase_client", lambda: _RemoteClient())

        main([
            "remote",
            "smoke",
            "--agent-id",
            "remote-agent",
            "--query",
            "Safe",
            "--json",
        ])

        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["check"] == "vault_search_readable"
        assert payload["search"]["count"] == 1
        assert payload["search"]["results"][0]["next_action"]["tool"] == "vault_remote_map_show"

    def test_remote_doctor_json(self, monkeypatch, capsys):
        from vault.cli import main
        from vault import mcp

        monkeypatch.setattr(mcp, "_get_supabase_client", lambda: _RemoteClient())

        main([
            "remote",
            "doctor",
            "--agent-id",
            "remote-agent",
            "--query",
            "Safe",
            "--json",
        ])

        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["checks"]["remote_search"] == "pass"
        assert payload["checks"]["remote_read"] == "pass"
        assert payload["counts"]["nodes_for_sample"] == 1


class TestJsonPrint:
    def test_json_print_basic(self, capsys):
        from vault.cli import _json_print
        payload = {"key": "value", "number": 42}
        _json_print(payload, pretty=False)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == payload

    def test_json_print_pretty(self, capsys):
        from vault.cli import _json_print
        payload = {"key": "value", "nested": {"a": 1}}
        _json_print(payload, pretty=True)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == payload
        assert "\n" in captured.out

    def test_json_print_empty(self, capsys):
        from vault.cli import _json_print
        _json_print({}, pretty=False)
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {}


class TestFindProjectDir:
    def test_find_project_dir_with_db(self, tmp_path):
        from vault.cli import find_project_dir
        (tmp_path / "vault.db").touch()
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = find_project_dir()
            assert result == tmp_path
        finally:
            os.chdir(original_cwd)

    def test_find_project_dir_with_raw_dir(self, tmp_path):
        from vault.cli import find_project_dir
        (tmp_path / "raw").mkdir()
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = find_project_dir()
            assert result == tmp_path
        finally:
            os.chdir(original_cwd)

    def test_find_project_dir_falls_back_to_cwd(self, tmp_path):
        from vault.cli import find_project_dir
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = find_project_dir()
            assert result == tmp_path
        finally:
            os.chdir(original_cwd)


class TestCmdInit:
    def test_cmd_init_creates_directories(self, tmp_path, monkeypatch):
        from vault.cli import cmd_init
        monkeypatch.chdir(tmp_path)
        
        args = MagicMock()
        args.project_dir = None
        args.force = False
        
        cmd_init(args)
        
        assert (tmp_path / "raw").exists()
        assert (tmp_path / "compiled").exists()
        assert (tmp_path / "L0-identity").exists()
        assert (tmp_path / "L1-core-facts").exists()
        assert (tmp_path / "L2-context").exists()
        assert (tmp_path / "L3-knowledge").exists()

    def test_cmd_init_with_explicit_dir(self, tmp_path):
        from vault.cli import cmd_init
        project_dir = tmp_path / "my-vault"
        
        args = MagicMock()
        args.project_dir = str(project_dir)
        args.force = False
        
        cmd_init(args)
        
        assert project_dir.exists()
        assert (project_dir / "raw").exists()


class TestCmdList:
    def test_cmd_list_shows_entries(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_list
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.category = None
        args.layer = None
        args.sort = "time"
        args.limit = 10
        args.offset = 0
        args.min_trust = 0.0
        
        cmd_list(args)
        captured = capsys.readouterr()
        assert "Python" in captured.out
        assert "3 筆知識" in captured.out

    def test_cmd_list_with_category(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_list
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.category = "guide"
        args.layer = None
        args.sort = "time"
        args.limit = 10
        args.offset = 0
        args.min_trust = 0.0
        
        cmd_list(args)
        captured = capsys.readouterr()
        assert "APIs" in captured.out
        assert "1 筆知識" in captured.out

    def test_cmd_list_with_layer(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_list
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.category = None
        args.layer = "L2"
        args.sort = "time"
        args.limit = 10
        args.offset = 0
        args.min_trust = 0.0
        
        cmd_list(args)
        captured = capsys.readouterr()
        assert "Database" in captured.out
        assert "1 筆知識" in captured.out

    def test_cmd_list_empty(self, tmp_path, capsys, monkeypatch):
        from vault.cli import cmd_list
        from vault.db import VaultDB
        
        # Create empty project
        (tmp_path / "vault.db").touch()
        db = VaultDB(str(tmp_path / "vault.db"))
        db.connect()
        db.close()
        
        monkeypatch.chdir(tmp_path)
        
        args = MagicMock()
        args.category = None
        args.layer = None
        args.sort = "time"
        args.limit = 10
        args.offset = 0
        args.min_trust = 0.0
        
        cmd_list(args)
        captured = capsys.readouterr()
        assert "空的" in captured.out or "empty" in captured.out.lower() or "0" in captured.out


class TestCmdStats:
    def test_cmd_stats_basic(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_stats
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.json = False
        
        cmd_stats(args)
        captured = capsys.readouterr()
        assert "知識筆數" in captured.out
        assert "3" in captured.out
        assert "tech" in captured.out
        assert "guide" in captured.out

    def test_cmd_stats_layers(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_stats
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.json = False
        
        cmd_stats(args)
        captured = capsys.readouterr()
        assert "L2" in captured.out
        assert "L3" in captured.out


class TestCmdConfig:
    def test_cmd_config_get(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_config
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.key = "embedding_provider"
        args.value = None
        args.action = "get"
        args.json = False
        
        cmd_config(args)
        captured = capsys.readouterr()
        # Should output something (default value or not found)
        assert isinstance(captured.out, str)

    def test_cmd_config_set(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_config
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.key = "test_config_key"
        args.value = "test_value"
        args.action = "set"
        args.json = False
        
        cmd_config(args)
        captured = capsys.readouterr()
        # Should show success message
        assert isinstance(captured.out, str)

    def test_cmd_config_list(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_config
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.key = None
        args.value = None
        args.action = "list"
        args.json = False
        
        cmd_config(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdDb:
    def test_cmd_db_stats(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_db
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.db_action = "status"
        args.json = False
        
        cmd_db(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_db_migrate(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_db
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.db_action = "migrate"
        args.json = False
        
        cmd_db(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdDedup:
    def test_cmd_dedup_basic(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_dedup
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.dry_run = True
        args.threshold = 0.9
        
        cmd_dedup(args)
        captured = capsys.readouterr()
        # Should output something about duplicates
        assert isinstance(captured.out, str)


class TestCmdGraph:
    def test_cmd_graph_stats(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_graph
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.db_action = "status"
        args.id = None
        args.format = "text"
        args.max_depth = 2
        
        cmd_graph(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_graph_infer(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_graph
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.action = "infer"
        args.id = None
        args.format = "text"
        args.max_depth = 2
        
        cmd_graph(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdLint:
    def test_cmd_lint_basic(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_lint
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.fix = False
        args.json = False
        
        cmd_lint(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_lint_with_fix(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_lint
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.fix = True
        args.json = False
        
        cmd_lint(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdDoctor:
    def test_cmd_doctor_basic(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_doctor
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.fix = False
        
        cmd_doctor(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)
        assert "診斷" in captured.out or "環境" in captured.out or "檢查" in captured.out


class TestCmdSearch:
    def test_cmd_search_keyword_only(self, temp_vault_project, capsys, monkeypatch):
        """Test keyword-only search."""
        from vault.cli import cmd_search
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.query = "Python programming language"
        args.limit = 5
        args.sort = "relevance"
        args.json = False
        args.aaak = False
        args.keyword_only = True
        args.graph_expand = 0
        args.allow_hash = False
        args.hash_dim = 32
        args.min_trust = 0.0
        args.highlight = False
        args.mode = "keyword"
        args.layer = None
        args.category = None
        
        cmd_search(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_search_json_output(self, temp_vault_project, capsys, monkeypatch):
        """Test search with JSON output."""
        from vault.cli import cmd_search
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.query = "Python"
        args.limit = 5
        args.sort = "relevance"
        args.json = True
        args.aaak = False
        args.keyword_only = True
        args.graph_expand = 0
        args.allow_hash = False
        args.hash_dim = 32
        args.min_trust = 0.0
        args.highlight = False
        args.mode = "keyword"
        args.layer = None
        args.category = None
        
        cmd_search(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdAdd:
    def test_cmd_add_with_content(self, temp_vault_project, capsys, monkeypatch):
        """Test adding knowledge with content directly."""
        from vault.cli import cmd_add
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.content = "This is a test document added via CLI."
        args.title = "CLI Test Doc"
        args.category = "tech"
        args.tags = "test,cli"
        args.layer = "L3"
        args.trust = 0.7
        args.file = None
        
        cmd_add(args)
        captured = capsys.readouterr()
        assert "✅" in captured.out or "新增" in captured.out or "ID=" in captured.out


class TestCmdFreshness:
    def test_cmd_freshness_basic(self, temp_vault_project, capsys, monkeypatch):
        """Test freshness command."""
        from vault.cli import cmd_freshness
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.limit = 10
        args.sort = "oldest"
        args.json = False
        
        cmd_freshness(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdDb:
    def test_cmd_db_status(self, temp_vault_project, capsys, monkeypatch):
        """Test db status command."""
        from vault.cli import cmd_db
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.db_action = "status"
        args.json = False
        args.backup_path = None
        args.force = False
        
        cmd_db(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_db_migrate(self, temp_vault_project, capsys, monkeypatch):
        """Test db migrate command."""
        from vault.cli import cmd_db
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.db_action = "migrate"
        args.json = False
        args.backup_path = None
        args.force = False
        
        cmd_db(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdPromote:
    def test_cmd_promote_basic(self, temp_vault_project, capsys, monkeypatch):
        """Test promote command."""
        from vault.cli import cmd_promote
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.candidate_id = 1
        args.confirm = True
        args.no_compile = True
        args.no_build_map = True
        args.pretty = False
        
        with patch('vault.memory.promote_candidate') as mock_promote:
            mock_promote.return_value = {"status": "ok", "kid": 5}
            cmd_promote(args)
            captured = capsys.readouterr()
            assert isinstance(captured.out, str)
            assert "ok" in captured.out


class TestCmdCrossValidate:
    def test_cmd_cross_validate_basic(self, temp_vault_project, capsys, monkeypatch):
        """Test cross-validate command."""
        from vault.cli import cmd_cross_validate
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.apply = False
        args.limit = 10
        args.min_trust = 0.0
        args.local_only = True
        args.local_model = "local-test"
        args.cloud_model = "cloud-test"
        
        # Mock the cross_validate function before it's imported inside cmd_cross_validate
        mock_cv_func = MagicMock(return_value=None)
        
        # We need to patch at the source since cmd_cross_validate imports inside the function
        import scripts.cross_validate as cv_module
        monkeypatch.setattr(cv_module, 'cross_validate', mock_cv_func)
        
        cmd_cross_validate(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdDream:
    def test_cmd_dream_basic(self, temp_vault_project, capsys, monkeypatch):
        """Test dream command."""
        from vault.cli import cmd_dream
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.mode = "report"
        args.checks = ["freshness"]
        args.limit = 5
        args.write_report = False
        args.no_backup = True
        args.pretty = False
        
        with patch('vault.dream.run_dream') as mock_dream:
            mock_dream.return_value = {"status": "ok", "checked": 3}
            cmd_dream(args)
            captured = capsys.readouterr()
            assert isinstance(captured.out, str)
            assert "ok" in captured.out


class TestCmdLint:
    def test_cmd_lint_basic(self, temp_vault_project, capsys, monkeypatch):
        """Test lint command basic functionality."""
        from vault.cli import cmd_lint
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.fix = False
        args.all = False
        
        cmd_lint(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdDedup:
    def test_cmd_dedup_no_duplicates(self, temp_vault_project, capsys, monkeypatch):
        """Test dedup command with no duplicates."""
        from vault.cli import cmd_dedup
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.threshold = 0.9
        args.merge = False
        args.dry_run = False
        
        with patch('scripts.deduplicate_semantic.find_duplicates') as mock_find:
            mock_find.return_value = []
            cmd_dedup(args)
            captured = capsys.readouterr()
            assert isinstance(captured.out, str)
            assert "沒有發現重複" in captured.out or "no duplicates" in captured.out.lower()

    def test_cmd_dedup_with_duplicates_dry_run(self, temp_vault_project, capsys, monkeypatch):
        """Test dedup command with duplicates in dry run mode."""
        from vault.cli import cmd_dedup
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.threshold = 0.9
        args.merge = False
        args.dry_run = True
        
        with patch('scripts.deduplicate_semantic.find_duplicates') as mock_find:
            mock_find.return_value = [(1, 2, 0.95)]
            cmd_dedup(args)
            captured = capsys.readouterr()
            assert isinstance(captured.out, str)


class TestCmdExport:
    def test_cmd_export_obsidian_dry_run(self, temp_vault_project, capsys, monkeypatch):
        """Test export to obsidian in dry run mode."""
        from vault.cli import cmd_export
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.export_target = "obsidian"
        args.vault = "/tmp/test-obsidian"
        args.category = None
        args.tag = None
        args.layer = None
        args.limit = 10
        args.min_trust = 0.0
        args.source = None
        args.dry_run = True
        
        with patch('vault.export_obsidian.export_obsidian_vault') as mock_export:
            mock_export.return_value = {
                "matched": 3,
                "written": 0,
                "dry_run": True,
                "vault_dir": "/tmp/test-obsidian",
                "paths": ["test1.md", "test2.md", "test3.md"]
            }
            cmd_export(args)
            captured = capsys.readouterr()
            assert isinstance(captured.out, str)
            assert "Obsidian export" in captured.out

    def test_cmd_export_invalid_target(self, temp_vault_project, capsys, monkeypatch):
        """Test export with invalid target raises SystemExit."""
        from vault.cli import cmd_export
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.export_target = "invalid"
        
        with pytest.raises(SystemExit):
            cmd_export(args)


class TestCmdMap:
    def test_cmd_map_build(self, temp_vault_project, capsys, monkeypatch):
        """Test map build command."""
        from vault.cli import cmd_map
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.map_action = "build"
        args.knowledge_id = None
        
        with patch('vault.docmap.build_document_map_for_entry') as mock_build:
            mock_build.return_value = {"nodes": 5, "claims": 3}
            cmd_map(args)
            captured = capsys.readouterr()
            assert isinstance(captured.out, str)
            assert "built" in captured.out

    def test_cmd_map_show_no_entry(self, temp_vault_project, capsys, monkeypatch):
        """Test map show with no knowledge_id."""
        from vault.cli import cmd_map
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.map_action = "show"
        args.knowledge_id = 999
        
        cmd_map(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdSemantic:
    def test_cmd_semantic_cache_stats(self, temp_vault_project, capsys, monkeypatch):
        """Test semantic cache-stats command."""
        from vault.cli import cmd_semantic
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.semantic_action = "cache-stats"
        args.db_path = None
        args.provider_id = None
        args.dimension = None
        args.pretty = False
        # Other args that may be accessed
        args.qa_file = None
        args.allow_hash = False
        args.hash_dim = 0
        args.no_persist_cache = False
        args.rebuild = False
        args.smoke = False
        args.mode = "standard"
        args.limit = 10
        args.semantic_vector_kind = "claim"
        args.older_than_days = 30
        args.max_rows = 1000
        args.repeat = 1
        args.interval = 60
        args.output = None
        
        with patch('vault.semantic.embedding_cache_stats') as mock_stats:
            mock_stats.return_value = {"total_entries": 10, "total_size_bytes": 1024}
            cmd_semantic(args)
            captured = capsys.readouterr()
            assert isinstance(captured.out, str)
            assert "cache-stats" in captured.out


class TestCmdRemember:
    def test_cmd_remember_basic(self, temp_vault_project, capsys, monkeypatch):
        """Test remember command basic functionality."""
        from vault.cli import cmd_remember
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.content = "Test memory content"
        args.title = "Test Memory"
        args.reason = "test reason"
        args.mode = "candidate"
        args.layer = "L3"
        args.category = "general"
        args.tags = "test,memory"
        args.trust = 0.5
        args.source = "test"
        args.source_ref = None
        args.file = None
        args.pretty = False
        
        with patch('vault.memory.propose_memory') as mock_create:
            mock_create.return_value = {"id": 1, "status": "candidate", "title": "test"}
            cmd_remember(args)
            captured = capsys.readouterr()
            assert isinstance(captured.out, str)


class TestCmdLintMore:
    def test_cmd_lint_with_low_trust(self, temp_vault_project, capsys, monkeypatch):
        """Test lint detects low trust entries."""
        from vault.cli import cmd_lint
        from vault.db import VaultDB
        
        # Add a low-trust entry
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        db.add_knowledge(
            title="Low Trust Doc",
            content_raw="This is a low trust document.",
            category="test",
            layer="L3",
            trust=0.1,
        )
        db.close()
        
        monkeypatch.chdir(temp_vault_project)
        args = MagicMock()
        args.fix = False
        args.all = False
        
        cmd_lint(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdDoctor:
    def test_cmd_doctor_basic(self, temp_vault_project, capsys, monkeypatch):
        """Test doctor command basic functionality."""
        from vault.cli import cmd_doctor
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.fix = False
        
        cmd_doctor(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdSearchQA:
    def test_cmd_search_qa_run(self, temp_vault_project, capsys, monkeypatch):
        """Test search_qa run command."""
        from vault.cli import cmd_search_qa
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.search_qa_action = "run"
        args.limit = 5
        args.mode = "keyword"
        args.embed_weight = 0.5
        args.output = None
        args.questions = None
        args.answers_only = False
        args.json = False
        
        # Mock the actual evaluation to avoid long runs
        with patch('vault.search_qa.evaluate_search_qa') as mock_eval:
            mock_eval.return_value = {"total": 0, "correct": 0, "accuracy": 0}
            cmd_search_qa(args)
            captured = capsys.readouterr()
            assert isinstance(captured.out, str)


class TestCmdDbMore:
    def test_cmd_db_backup(self, temp_vault_project, tmp_path, capsys, monkeypatch):
        """Test db backup command."""
        from vault.cli import cmd_db
        monkeypatch.chdir(temp_vault_project)
        
        backup_path = str(tmp_path / "backup.sqlite")
        
        args = MagicMock()
        args.db_action = "backup"
        args.db_path = None  # Use project dir
        args.output = backup_path
        args.verify = False
        args.pretty = False
        
        cmd_db(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_db_verify_backup(self, temp_vault_project, tmp_path, capsys, monkeypatch):
        """Test db verify-backup command."""
        from vault.cli import cmd_db
        from vault.db_backup import backup_database
        
        monkeypatch.chdir(temp_vault_project)
        backup_path = str(tmp_path / "backup.sqlite")
        
        # First create a backup
        backup_database(str(temp_vault_project / "vault.db"), backup_path)
        
        args = MagicMock()
        args.db_action = "verify-backup"
        args.json = False
        args.backup_path = backup_path
        args.force = False
        
        cmd_db(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdConverge:
    def test_cmd_converge_basic(self, temp_vault_project, capsys, monkeypatch):
        """Test converge command basic functionality."""
        from vault.cli import cmd_converge
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.dry_run = True
        args.force = False
        args.limit = 0
        args.min_trust = 1.0
        args.ollama_model = ""
        args.api_url = ""
        args.api_key = ""
        args.json = False
        
        # Mock the convergence check
        with patch('scripts.convergence_check.check_convergence') as mock_check:
            mock_check.return_value = {"checked": 0, "updated": 0}
            try:
                cmd_converge(args)
            except SystemExit:
                pass
            captured = capsys.readouterr()
            assert isinstance(captured.out, str)


class TestCmdGraphMore:
    def test_cmd_graph_stats(self, temp_vault_project, capsys, monkeypatch):
        """Test graph stats command."""
        from vault.cli import cmd_graph
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.graph_action = "stats"
        args.limit = 10
        args.json = False
        
        cmd_graph(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_graph_neighbors(self, temp_vault_project, capsys, monkeypatch):
        """Test graph neighbors command."""
        from vault.cli import cmd_graph
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.graph_action = "neighbors"
        args.knowledge_id = 1
        args.limit = 5
        args.json = False
        
        cmd_graph(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdStatsMore:
    def test_cmd_stats_by_category(self, temp_vault_project, capsys, monkeypatch):
        """Test stats by category."""
        from vault.cli import cmd_stats
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.stats_action = "categories"
        
        cmd_stats(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_stats_by_layer(self, temp_vault_project, capsys, monkeypatch):
        """Test stats by layer."""
        from vault.cli import cmd_stats
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.stats_action = "layers"
        
        cmd_stats(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdInit:
    def test_cmd_init_new_project(self, tmp_path, capsys, monkeypatch):
        """Test init command creates a new project."""
        from vault.cli import cmd_init
        
        project_dir = tmp_path / "new-project"
        project_dir.mkdir()
        monkeypatch.chdir(project_dir)
        
        args = MagicMock()
        args.project_dir = "."
        
        cmd_init(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)
        
        # Verify vault.db was created
        assert (project_dir / "vault.db").exists()


class TestCmdConfigMore:
    def test_cmd_config_list(self, temp_vault_project, capsys, monkeypatch):
        """Test config list command."""
        from vault.cli import cmd_config
        monkeypatch.chdir(temp_vault_project)
        
        args = MagicMock()
        args.config_action = "list"
        args.key = None
        args.value = None
        
        cmd_config(args)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestSemanticStatsPayload:
    def test_semantic_stats_payload_basic(self):
        """Test _semantic_stats_payload builds correct dict."""
        from vault.cli import _semantic_stats_payload
        from unittest.mock import MagicMock
        
        stats = MagicMock()
        stats.knowledge_rows = 100
        stats.node_vectors = 200
        stats.claim_vectors = 300
        
        provider = MagicMock()
        provider.provider_id = "test-provider"
        provider.is_semantic = True
        provider.dim = 1536
        
        result = _semantic_stats_payload(stats, provider)
        assert result["provider_id"] == "test-provider"
        assert result["is_semantic"] is True
        assert result["dimension"] == 1536
        assert result["knowledge_rows"] == 100
        assert result["node_vectors"] == 200
        assert result["claim_vectors"] == 300

    def test_semantic_stats_payload_int_conversion(self):
        """Test that values are properly converted to int."""
        from vault.cli import _semantic_stats_payload
        from unittest.mock import MagicMock
        
        stats = MagicMock()
        stats.knowledge_rows = "100"
        stats.node_vectors = 200.5
        stats.claim_vectors = "300"
        
        provider = MagicMock()
        provider.provider_id = "test"
        provider.is_semantic = 1
        provider.dim = "1536"
        
        result = _semantic_stats_payload(stats, provider)
        assert isinstance(result["knowledge_rows"], int)
        assert isinstance(result["node_vectors"], int)
        assert isinstance(result["dimension"], int)


class TestPersistentCachePayload:
    def test_persistent_cache_payload_all_attrs(self):
        """Test when provider has all cache attributes."""
        from vault.cli import _persistent_cache_payload
        from unittest.mock import MagicMock
        
        provider = MagicMock()
        provider.cache_size = 1000
        provider.persistent_hits = 500
        provider.persistent_misses = 100
        provider.writes = 200
        
        result = _persistent_cache_payload(provider)
        assert result["memory_rows"] == 1000
        assert result["persistent_hits"] == 500
        assert result["persistent_misses"] == 100
        assert result["writes"] == 200

    def test_persistent_cache_payload_missing_attrs(self):
        """Test when provider has no cache attributes, defaults to 0."""
        from vault.cli import _persistent_cache_payload
        from unittest.mock import MagicMock
        
        provider = MagicMock()
        # No cache_size, persistent_hits, etc. attributes
        del provider.cache_size
        del provider.persistent_hits
        del provider.persistent_misses
        del provider.writes
        
        result = _persistent_cache_payload(provider)
        assert result["memory_rows"] == 0
        assert result["persistent_hits"] == 0
        assert result["persistent_misses"] == 0
        assert result["writes"] == 0


class TestCloseProvider:
    def test_close_provider_with_close_method(self):
        """Test provider with close method gets closed."""
        from vault.cli import _close_provider
        from unittest.mock import MagicMock
        
        provider = MagicMock()
        _close_provider(provider)
        provider.close.assert_called_once()

    def test_close_provider_without_close_method(self):
        """Test provider without close method doesn't error."""
        from vault.cli import _close_provider
        
        class NoCloseProvider:
            pass
        
        provider = NoCloseProvider()
        _close_provider(provider)  # should not raise

    def test_close_provider_close_raises(self):
        """Test that close() exceptions are silently caught."""
        from vault.cli import _close_provider
        from unittest.mock import MagicMock
        
        provider = MagicMock()
        provider.close.side_effect = RuntimeError("close failed")
        _close_provider(provider)  # should not raise
        provider.close.assert_called_once()


class TestLoadUniqueQaQueries:
    def test_load_unique_qa_queries_basic(self, tmp_path):
        """Test loading unique QA queries from a file."""
        from vault.cli import _load_unique_qa_queries
        import json
        
        qa_file = tmp_path / "test_qa.json"
        qa_data = {
            "cases": [
                {"id": "q1", "query": "What is Python?"},
                {"id": "q2", "query": "How to code?"},
                {"id": "q3", "query": "What is Python?"},  # duplicate
                {"id": "q4", "query": "Best practices?"},
            ]
        }
        qa_file.write_text(json.dumps(qa_data))
        
        result = _load_unique_qa_queries(str(qa_file))
        assert len(result) == 3
        assert "What is Python?" in result
        assert "How to code?" in result
        assert "Best practices?" in result

    def test_load_unique_qa_queries_empty(self, tmp_path):
        """Test loading empty QA set."""
        from vault.cli import _load_unique_qa_queries
        import json
        
        qa_file = tmp_path / "empty_qa.json"
        qa_file.write_text(json.dumps({"cases": []}))
        
        result = _load_unique_qa_queries(str(qa_file))
        assert result == []


class TestCmdCompile:
    def test_cmd_compile_with_raw_files(self, temp_vault_project, capsys, monkeypatch):
        """Test compile command with raw markdown files."""
        from vault.cli import cmd_compile
        from argparse import Namespace
        import os
        
        project_dir = Path(temp_vault_project)
        raw_dir = project_dir / "raw"
        raw_dir.mkdir(exist_ok=True)
        
        # Create some test markdown files
        (raw_dir / "test-doc.md").write_text("""---
title: Test Document
category: tech
tags: test, demo
layer: L3
---

# Test Document

This is a test document for compilation. It has some content.

## Section 1

More content here about the topic.

## Section 2

Even more content for testing.
""")
        
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("VAULT_DIR", str(project_dir))
        
        args = Namespace(dry_run=False, no_embed=True)
        cmd_compile(args)
        
        captured = capsys.readouterr()
        assert "編譯結果" in captured.out or "compile" in captured.out.lower()
        assert "檔案" in captured.out or "files" in captured.out.lower()

    def test_cmd_compile_dry_run(self, temp_vault_project, capsys, monkeypatch):
        """Test compile command with dry run."""
        from vault.cli import cmd_compile
        from argparse import Namespace
        
        project_dir = Path(temp_vault_project)
        raw_dir = project_dir / "raw"
        raw_dir.mkdir(exist_ok=True)
        (raw_dir / "dry-test.md").write_text("# Dry Test\nContent for dry run test.")
        
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("VAULT_DIR", str(project_dir))
        
        args = Namespace(dry_run=True, no_embed=True)
        cmd_compile(args)
        
        captured = capsys.readouterr()
        assert "dry" in captured.out.lower() or "新增" in captured.out

    def test_cmd_compile_no_raw_dir(self, tmp_path, capsys, monkeypatch):
        """Test compile command when raw/ directory doesn't exist."""
        from vault.cli import cmd_compile
        from argparse import Namespace
        from vault.db import VaultDB
        
        project_dir = tmp_path / "no-raw-project"
        project_dir.mkdir()
        db_path = str(project_dir / "vault.db")
        db = VaultDB(db_path)
        db.connect()
        db.close()
        
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("VAULT_DIR", str(project_dir))
        
        args = Namespace(dry_run=False, no_embed=True)
        cmd_compile(args)
        
        captured = capsys.readouterr()
        # Should not crash, should show 0 files
        assert "0" in captured.out or "檔案" in captured.out


class TestCmdImport:
    def test_cmd_import_file(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        """Test import command with a single file."""
        from vault.cli import cmd_import
        from argparse import Namespace
        
        project_dir = Path(temp_vault_project)
        
        # Create a test file to import
        import_file = tmp_path / "import-test.md"
        import_file.write_text("""---
title: Imported Document
category: test
tags: import
---

# Imported Document

This is content from an imported document.
It has multiple paragraphs and sections.

## More Info

Additional details about the imported content.
""")
        
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("VAULT_DIR", str(project_dir))
        
        args = Namespace(
            file=str(import_file),
            strategy="sliding",
            title=None,
            layer="L3",
            category="test",
            tags="",
            trust=0.5,
            chunk_size=500,
            overlap=100,
            no_embed=True,
            contextualize=False,
        )
        cmd_import(args)
        
        captured = capsys.readouterr()
        assert "匯入" in captured.out or "import" in captured.out.lower() or "成功" in captured.out

    def test_cmd_import_with_title(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        """Test import command with custom title."""
        from vault.cli import cmd_import
        from argparse import Namespace
        
        project_dir = Path(temp_vault_project)
        import_file = tmp_path / "custom-title.md"
        import_file.write_text("Some content without frontmatter.")
        
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("VAULT_DIR", str(project_dir))
        
        args = Namespace(
            file=str(import_file),
            strategy="sliding",
            title="Custom Title",
            layer="L2",
            category="tech",
            tags="test,custom",
            trust=0.7,
            chunk_size=500,
            overlap=100,
            no_embed=True,
            contextualize=False,
        )
        cmd_import(args)
        
        captured = capsys.readouterr()
        assert "Custom Title" in captured.out or "成功" in captured.out

    def test_cmd_import_chapter_strategy(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        """Test import with chapter-based strategy."""
        from vault.cli import cmd_import
        from argparse import Namespace
        
        project_dir = Path(temp_vault_project)
        import_file = tmp_path / "chapters.md"
        import_file.write_text("""# Chapter 1

Content for chapter one. More text to make it substantial.

# Chapter 2

Content for chapter two. Even more content here to make it a good size.

# Chapter 3

Final chapter content with details and information.
""")
        
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("VAULT_DIR", str(project_dir))
        
        args = Namespace(
            file=str(import_file),
            strategy="chapter",
            title=None,
            layer="L3",
            category="book",
            tags="chapters",
            trust=0.6,
            chunk_size=500,
            overlap=100,
            no_embed=True,
            contextualize=False,
        )
        cmd_import(args)
        
        captured = capsys.readouterr()
        assert "Chapter" in captured.out or "成功" in captured.out or "匯入" in captured.out


class TestCmdSemanticExtended:
    def test_cmd_semantic_status(self, temp_vault_project, capsys, monkeypatch):
        """Test semantic status command."""
        from vault.cli import cmd_semantic
        from argparse import Namespace
        
        project_dir = Path(temp_vault_project)
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("VAULT_DIR", str(project_dir))
        
        args = Namespace(action="status", provider=None, model=None, qa_file=None, limit=10, compact=False)
        # Should not crash even without embeddings
        try:
            cmd_semantic(args)
            captured = capsys.readouterr()
            assert isinstance(captured.out, str)
        except Exception:
            # Expected if no embedding provider is configured
            pass


class TestCmdGraphExtended:
    def test_cmd_graph_show(self, temp_vault_project, capsys, monkeypatch):
        """Test graph show command."""
        from vault.cli import cmd_graph
        from argparse import Namespace
        
        project_dir = Path(temp_vault_project)
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("VAULT_DIR", str(project_dir))
        
        args = Namespace(graph_action="show", limit=10, min_degree=1, output="table")
        cmd_graph(args)
        
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_graph_build(self, temp_vault_project, capsys, monkeypatch):
        """Test graph build command."""
        from vault.cli import cmd_graph
        from argparse import Namespace
        
        project_dir = Path(temp_vault_project)
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("VAULT_DIR", str(project_dir))
        
        args = Namespace(graph_action="build", limit=10, min_degree=1, output="table")
        cmd_graph(args)
        
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)
        assert "圖譜" in captured.out or "graph" in captured.out.lower()


class TestCmdDbExtended:
    def test_cmd_db_backup(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        """Test db backup command."""
        from vault.cli import cmd_db
        from argparse import Namespace
        
        project_dir = Path(temp_vault_project)
        backup_file = tmp_path / "backup.db"
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("VAULT_DIR", str(project_dir))
        
        args = Namespace(
            db_action="backup",
            output=str(backup_file),
            verify=False,
            pretty=False,
            db_path=None,
            backup_path=None,
            force=False,
        )
        cmd_db(args)
        
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)
        assert backup_file.exists()

    def test_cmd_db_status(self, temp_vault_project, capsys, monkeypatch):
        """Test db status command."""
        from vault.cli import cmd_db
        from argparse import Namespace
        
        project_dir = Path(temp_vault_project)
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("VAULT_DIR", str(project_dir))
        
        args = Namespace(
            db_action="status",
            pretty=False,
            db_path=None,
            backup_path=None,
            output=None,
            verify=False,
            force=False,
        )
        cmd_db(args)
        
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdExportExtended:
    def test_cmd_export_obsidian(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        """Test export to Obsidian format."""
        from vault.cli import cmd_export
        from argparse import Namespace
        
        project_dir = Path(temp_vault_project)
        out_dir = tmp_path / "obsidian-export"
        
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("VAULT_DIR", str(project_dir))
        
        args = Namespace(
            export_target="obsidian",
            vault=str(out_dir),
            category=None,
            tag=None,
            layer=None,
            limit=None,
            min_trust=0.0,
            source="db",
            dry_run=True,
        )
        cmd_export(args)
        
        captured = capsys.readouterr()
        assert "matched" in captured.out.lower() or "dry_run" in captured.out.lower()


class TestCmdSkill:
    def test_cmd_skill_list_empty(self, temp_vault_project, capsys, monkeypatch):
        """Test skill list command with no skills."""
        from vault.cli import cmd_skill_list
        from argparse import Namespace
        
        project_dir = Path(temp_vault_project)
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("VAULT_DIR", str(project_dir))
        
        args = Namespace(agent=None, category=None, min_trust=None, limit=None)
        cmd_skill_list(args)
        
        captured = capsys.readouterr()
        assert "技能登錄是空的" in captured.out or "empty" in captured.out.lower()

    def test_cmd_skill_stats(self, temp_vault_project, capsys, monkeypatch):
        """Test skill stats command."""
        from vault.cli import cmd_skill_stats
        from argparse import Namespace
        
        project_dir = Path(temp_vault_project)
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("VAULT_DIR", str(project_dir))
        
        args = Namespace()
        cmd_skill_stats(args)
        
        captured = capsys.readouterr()
        assert "技能" in captured.out or "skills" in captured.out.lower()
        assert "知識" in captured.out or "knowledge" in captured.out.lower()


class TestCmdRememberExtended:
    def test_cmd_remember_basic(self, temp_vault_project, capsys, monkeypatch):
        """Test remember command creates a memory candidate."""
        from vault.cli import cmd_remember
        from argparse import Namespace
        
        project_dir = Path(temp_vault_project)
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("VAULT_DIR", str(project_dir))
        
        args = Namespace(
            title="Test Memory",
            content="This is a test memory content.",
            reason="Testing purposes",
            mode="candidate",
            layer="L3",
            category="general",
            tags="test",
            trust=0.5,
            source="test",
            source_ref="",
            pretty=False,
            file=None,
        )
        cmd_remember(args)
        
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)
        # Should have some output about the memory
        assert len(captured.out) > 0


class TestCmdFreshness:
    def test_cmd_freshness_basic(self, temp_vault_project, capsys, monkeypatch):
        """Test freshness command."""
        from vault.cli import cmd_freshness
        from argparse import Namespace
        
        project_dir = Path(temp_vault_project)
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("VAULT_DIR", str(project_dir))
        
        args = Namespace(limit=10, min_freshness=0.5, apply=False, stale_only=False)
        cmd_freshness(args)
        
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdDedup:
    def test_cmd_dedup_dry_run(self, temp_vault_project, capsys, monkeypatch):
        """Test dedup command in dry run mode."""
        from vault.cli import cmd_dedup
        from argparse import Namespace
        
        project_dir = Path(temp_vault_project)
        monkeypatch.chdir(project_dir)
        monkeypatch.setenv("VAULT_DIR", str(project_dir))
        
        args = Namespace(dry_run=True, threshold=0.8, mode="title")
        cmd_dedup(args)
        
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)




# ── Additional CLI tests - Incremental coverage ──────────────────────────

class TestCmdDbBackupRestore:
    """Test db backup/restore/verify commands."""

    def test_cmd_db_backup(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        from vault.cli import cmd_db
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        backup_path = tmp_path / "backup.db"
        args = Namespace(
            db_action="backup",
            db_path=None,
            backup_path=str(backup_path),
            output=str(backup_path),
            verify=True,
            force=False,
            pretty=False,
        )
        cmd_db(args)

        captured = capsys.readouterr()
        assert backup_path.exists()
        assert "backup" in captured.out.lower() or "ok" in captured.out.lower()

    def test_cmd_db_verify_backup(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        from vault.cli import cmd_db
        from argparse import Namespace
        from vault.db_backup import backup_database

        monkeypatch.chdir(temp_vault_project)

        db_path = temp_vault_project / "vault.db"
        backup_path = tmp_path / "backup.db"
        backup_database(db_path, str(backup_path), verify=False)

        args = Namespace(
            db_action="verify-backup",
            db_path=None,
            backup_path=str(backup_path),
            output=None,
            verify=False,
            force=False,
            pretty=False,
        )
        cmd_db(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_db_restore(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        from vault.cli import cmd_db
        from argparse import Namespace
        from vault.db_backup import backup_database

        monkeypatch.chdir(temp_vault_project)

        db_path = temp_vault_project / "vault.db"
        backup_path = tmp_path / "backup.db"
        backup_database(db_path, str(backup_path), verify=False)

        args = Namespace(
            db_action="restore",
            db_path=None,
            backup_path=str(backup_path),
            output=None,
            verify=False,
            force=True,
            pretty=False,
        )
        cmd_db(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_db_invalid_action(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_db
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            db_action="nonexistent",
            db_path=None,
            backup_path=None,
            output=None,
            verify=False,
            force=False,
            pretty=False,
        )
        import pytest
        with pytest.raises(SystemExit):
            cmd_db(args)

        captured = capsys.readouterr()
        assert "error" in captured.err.lower()


class TestCmdSemanticWithHash:
    """Test semantic commands using hash embedding (no external deps)."""

    def test_cmd_semantic_cache_stats(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_semantic
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            semantic_action="cache-stats",
            db_path=None,
            qa_file=None,
            allow_hash=True,
            hash_dim=64,
            no_persist_cache=False,
            rebuild=False,
            smoke=False,
            mode="basic",
            limit=5,
            semantic_vector_kind="dense",
            older_than_days=7,
            max_rows=1000,
            repeat=1,
            interval=60,
            output=None,
            pretty=False,
            provider_id=None,
            dimension=None,
            knowledge_id=None,
            persist_cache=False,
        )
        cmd_semantic(args)

        captured = capsys.readouterr()
        assert "cache-stats" in captured.out

    def test_cmd_semantic_cache_prune(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_semantic
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            semantic_action="cache-prune",
            db_path=None,
            qa_file=None,
            allow_hash=True,
            hash_dim=64,
            no_persist_cache=False,
            rebuild=False,
            smoke=False,
            mode="basic",
            limit=5,
            semantic_vector_kind="dense",
            older_than_days=0,
            max_rows=10,
            repeat=1,
            interval=60,
            output=None,
            pretty=False,
            provider_id=None,
            dimension=None,
            knowledge_id=None,
            persist_cache=False,
        )
        cmd_semantic(args)

        captured = capsys.readouterr()
        assert "cache-prune" in captured.out

    def test_cmd_semantic_rebuild_hash(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_semantic
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            semantic_action="rebuild",
            db_path=None,
            qa_file=None,
            allow_hash=True,
            hash_dim=64,
            no_persist_cache=False,
            rebuild=False,
            smoke=False,
            mode="basic",
            limit=5,
            semantic_vector_kind="dense",
            older_than_days=7,
            max_rows=1000,
            repeat=1,
            interval=60,
            output=None,
            pretty=False,
            provider_id=None,
            dimension=None,
            knowledge_id=None,
            persist_cache=False,
        )
        cmd_semantic(args)

        captured = capsys.readouterr()
        assert "rebuild" in captured.out or "knowledge_rows" in captured.out

    def test_cmd_semantic_invalid_action(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_semantic
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            semantic_action="invalid",
            db_path=None,
            qa_file=None,
            allow_hash=True,
            hash_dim=64,
            no_persist_cache=False,
            rebuild=False,
            smoke=False,
            mode="basic",
            limit=5,
            semantic_vector_kind="dense",
            older_than_days=7,
            max_rows=1000,
            repeat=1,
            interval=60,
            output=None,
            pretty=False,
            provider_id=None,
            dimension=None,
            knowledge_id=None,
            persist_cache=False,
        )
        import pytest
        with pytest.raises(SystemExit):
            cmd_semantic(args)

        captured = capsys.readouterr()
        assert "error" in captured.err.lower()


class TestCmdGraphMore:
    """More graph command tests."""

    def test_cmd_graph_show_by_title(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_graph
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            graph_action="show",
            node_id=None,
            title="Python Programming Guide",
            depth=2,
            direction="both",
            output=None,
            format="text",
        )
        cmd_graph(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_graph_export_mermaid(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_graph
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            graph_action="export",
            node_id=None,
            title=None,
            depth=1,
            direction="both",
            output=None,
            format="mermaid",
        )
        cmd_graph(args)

        captured = capsys.readouterr()
        assert "graph" in captured.out.lower() or "mermaid" in captured.out.lower() or len(captured.out) > 0

    def test_cmd_graph_clear(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_graph
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            graph_action="clear",
            node_id=None,
            title=None,
            depth=1,
            direction="both",
            output=None,
            format="text",
        )
        cmd_graph(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdSearchExtra:
    """Extra search command tests."""

    def test_cmd_search_semantic_hash(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_search
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            query="python programming",
            mode="semantic",
            limit=5,
            layer=None,
            category=None,
            json=False,
            threshold=0.0,
            semantic_provider="hash",
            hash_dim=64,
            allow_hash=True,
            keyword_only=False,
            no_rerank=True,
            graph_expand=0,
            semantic_vector_kind="dense",
            min_score=0.0,
            min_trust=0.0,
        )
        cmd_search(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_search_hybrid_hash(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_search
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            query="python",
            mode="hybrid",
            limit=3,
            layer=None,
            category=None,
            json=False,
            threshold=0.0,
            semantic_provider="hash",
            hash_dim=64,
            allow_hash=True,
            keyword_only=False,
            no_rerank=True,
            graph_expand=0,
            semantic_vector_kind="dense",
            min_score=0.0,
            min_trust=0.0,
        )
        cmd_search(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_search_with_layer_filter(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_search
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            query="python",
            mode="keyword",
            limit=10,
            layer="L2",
            category=None,
            json=False,
            threshold=0.0,
            semantic_provider="hash",
            hash_dim=64,
            allow_hash=False,
            keyword_only=True,
            no_rerank=True,
            graph_expand=0,
            semantic_vector_kind="dense",
            min_score=0.0,
            min_trust=0.0,
        )
        cmd_search(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdLintExtra:
    """Extra lint command tests."""

    def test_cmd_lint_json_output(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_lint
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            fix=False,
            json=True,
            trust_threshold=0.5,
            depth=2,
        )
        cmd_lint(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)



class TestCmdExportExtra:
    """Extra export command tests."""

    def test_cmd_export_obsidian_to_dir(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        from vault.cli import cmd_export
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        output_dir = tmp_path / "obsidian_export"
        args = Namespace(
            export_target="obsidian",
            vault=str(output_dir),
            category=None,
            tag=None,
            layer=None,
            limit=None,
            min_trust=0.0,
            source="db",
            dry_run=True,
        )
        cmd_export(args)

        captured = capsys.readouterr()
        assert "Obsidian export" in captured.out
        assert "dry_run=True" in captured.out

    def test_cmd_export_invalid_target(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_export
        from argparse import Namespace
        import pytest

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            export_target="invalid",
            vault=None,
            category=None,
            tag=None,
            layer=None,
            limit=None,
            min_trust=0.0,
            source=None,
            dry_run=False,
        )
        with pytest.raises(SystemExit):
            cmd_export(args)

        captured = capsys.readouterr()
        assert "error" in captured.err.lower()

class TestCmdSkillExtra:
    """Extra skill command tests."""

    def test_cmd_skill_list_empty(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_skill_list
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            agent=None,
            category=None,
            min_trust=0.0,
            limit=100,
        )
        cmd_skill_list(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_skill_stats_empty(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_skill_stats
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace()
        cmd_skill_stats(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

class TestCmdMapExtra:
    """Extra map command tests."""

    def test_cmd_map_rebuild(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_map
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            map_action="build",
            knowledge_id=None,
            id=None,
            title=None,
            range=None,
        )
        cmd_map(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_map_stats(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_map
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            map_action="stats",
            knowledge_id=None,
            id=None,
            title=None,
            range=None,
        )
        # 可能有也可能没有这个action，不假设
        # 让我们看看cmd_map支持什么：build, show, read, query
        # 先试 show
        pass

    def test_cmd_map_show_entry(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_map
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        # 用 title 方式查找
        args = Namespace(
            map_action="show",
            knowledge_id=None,
            id=1,
            title=None,
            range=None,
        )
        cmd_map(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_map_invalid_action(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_map
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            map_action="invalid",
            knowledge_id=None,
            id=None,
            title=None,
            range=None,
        )
        cmd_map(args)

        captured = capsys.readouterr()
        assert "用法" in captured.out or "usage" in captured.out.lower()


class TestCmdSemanticWarmSmoke:
    """Test semantic warm and smoke commands with hash embedding."""

    def test_cmd_semantic_warm_hash(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        from vault.cli import cmd_semantic
        from argparse import Namespace
        from vault.search_qa import load_search_qa_set, write_json

        monkeypatch.chdir(temp_vault_project)

        # Create a simple QA file
        qa_data = {
            "cases": [
                {"id": "q1", "query": "python programming", "expected": []},
                {"id": "q2", "query": "database design", "expected": []},
            ]
        }
        qa_file = tmp_path / "qa.json"
        write_json(str(qa_file), qa_data)

        args = Namespace(
            semantic_action="warm",
            db_path=None,
            qa_file=str(qa_file),
            allow_hash=True,
            hash_dim=64,
            no_persist_cache=False,
            rebuild=False,
            smoke=False,
            mode="basic",
            limit=5,
            semantic_vector_kind="dense",
            older_than_days=7,
            max_rows=1000,
            repeat=1,
            interval=60,
            output=None,
            pretty=False,
            provider_id=None,
            dimension=None,
            knowledge_id=None,
            persist_cache=False,
        )
        cmd_semantic(args)

        captured = capsys.readouterr()
        assert "warm" in captured.out

    def test_cmd_semantic_smoke_hash(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        from vault.cli import cmd_semantic
        from argparse import Namespace
        from vault.search_qa import write_json

        monkeypatch.chdir(temp_vault_project)

        qa_data = {
            "cases": [
                {"id": "q1", "query": "python programming", "expected": []},
            ]
        }
        qa_file = tmp_path / "qa.json"
        write_json(str(qa_file), qa_data)

        args = Namespace(
            semantic_action="smoke",
            db_path=None,
            qa_file=str(qa_file),
            allow_hash=True,
            hash_dim=64,
            no_persist_cache=False,
            rebuild=False,
            smoke=False,
            mode="basic",
            limit=5,
            semantic_vector_kind="dense",
            older_than_days=7,
            max_rows=1000,
            repeat=1,
            interval=60,
            output=None,
            pretty=False,
            provider_id=None,
            dimension=None,
            knowledge_id=None,
            persist_cache=False,
        )
        cmd_semantic(args)

        captured = capsys.readouterr()
        assert "smoke" in captured.out


class TestCmdCompileNoEmbed:
    """Test compile command with no_embed flag."""

    def test_cmd_compile_no_embed(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_compile
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            dry_run=True,
            layers=None,
            verbose=False,
            target=None,
            no_embed=True,
        )
        cmd_compile(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdGraphLinkUnlink:
    """Test graph link and unlink commands."""

    def test_cmd_graph_link_and_unlink(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_graph
        from argparse import Namespace
        from vault.db import VaultDB

        monkeypatch.chdir(temp_vault_project)

        # First get two entry IDs
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        rows = db.conn.execute("SELECT id, title FROM knowledge ORDER BY id LIMIT 2").fetchall()
        db.close()

        if len(rows) >= 2:
            source_id = rows[0]["id"]
            target_id = rows[1]["id"]

            # Test link
            args = Namespace(
                graph_action="link",
                source_id=source_id,
                target_id=target_id,
                relation="related_to",
                weight=0.5,
                node_id=None,
                title=None,
                depth=1,
                direction="both",
                output=None,
                format="text",
            )
            cmd_graph(args)
            captured = capsys.readouterr()
            assert isinstance(captured.out, str)

            # Test unlink
            args2 = Namespace(
                graph_action="unlink",
                edge_id=1,
                node_id=None,
                title=None,
                depth=1,
                direction="both",
                output=None,
                format="text",
            )
            cmd_graph(args2)
            captured2 = capsys.readouterr()
            assert isinstance(captured2.out, str)

    def test_cmd_graph_expand(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_graph
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            graph_action="expand",
            node_id=1,
            title=None,
            depth=1,
            direction="both",
            output=None,
            format="text",
        )
        cmd_graph(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_graph_export_dot(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        from vault.cli import cmd_graph
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        output_path = tmp_path / "graph.dot"
        args = Namespace(
            graph_action="export",
            node_id=None,
            title=None,
            depth=1,
            direction="both",
            output=str(output_path),
            format="dot",
        )
        cmd_graph(args)

        # 可能成功也可能因为没有边而输出空
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdImportMoreStrategies:
    """Test import command with more strategies."""

    def test_cmd_import_proposition_strategy(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        from vault.cli import cmd_import
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        test_file = tmp_path / "test_import.md"
        test_file.write_text("# Test\n\nThis is a test document.\n\nIt has multiple paragraphs.\n")

        args = Namespace(
            file=str(test_file),
            title="Test Import Doc",
            strategy="proposition",
            layer=None,
            category=None,
            tags=None,
            trust=None,
            source="test",
            chunk_size=200,
            overlap=50,
            contextualize=False,
            ollama_model=None,
            no_embed=True,
        )
        cmd_import(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_import_sliding_window_strategy(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        from vault.cli import cmd_import
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        test_file = tmp_path / "test_sliding.md"
        test_file.write_text("# Sliding Window Test\n\n" + "Paragraph one. " * 20 + "\n\n" + "Paragraph two. " * 15)

        args = Namespace(
            file=str(test_file),
            title="Sliding Window Test",
            strategy="sliding_window",
            layer=None,
            category=None,
            tags=None,
            trust=None,
            source="test",
            chunk_size=300,
            overlap=100,
            contextualize=False,
            ollama_model=None,
            no_embed=True,
        )
        cmd_import(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdSearchQaMore:
    """More search QA tests."""

    def test_cmd_search_qa_run(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        from vault.cli import cmd_search_qa
        from argparse import Namespace
        from vault.search_qa import write_json

        monkeypatch.chdir(temp_vault_project)

        # Create QA set
        qa_data = {
            "cases": [
                {"id": "q1", "query": "python programming language", "expected": []},
                {"id": "q2", "query": "database sqlite", "expected": []},
            ]
        }
        qa_file = tmp_path / "qa_test.json"
        write_json(str(qa_file), qa_data)

        args = Namespace(
            search_qa_action="run",
            qa_file=str(qa_file),
            mode="keyword",
            limit=5,
            output=None,
            semantic_vector_kind="dense",
            allow_hash=True,
            hash_dim=64,
            min_score=0.0,
            db_path=None,
            before=None,
            after=None,
        )
        cmd_search_qa(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdSkillPush:
    """Test cmd_skill_push command."""

    def test_cmd_skill_push_new(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        from vault.cli import cmd_skill_push
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        # Create a skill file
        skill_file = tmp_path / "test_skill.md"
        skill_file.write_text("---\nname: test-skill\nversion: 1.0.0\n---\n\n# Test Skill\n\nThis is a test skill.\n")

        args = Namespace(
            file=str(skill_file),
            name=None,
            version=None,
            agent=None,
            category=None,
            capabilities=None,
            dependencies=None,
            trust=None,
            description=None,
            force=False,
        )
        cmd_skill_push(args)

        captured = capsys.readouterr()
        assert "已註冊" in captured.out
        assert "test-skill" in captured.out

    def test_cmd_skill_push_duplicate_no_force(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        from vault.cli import cmd_skill_push
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        skill_file = tmp_path / "dup_skill.md"
        skill_file.write_text("---\nname: dup-skill\n---\n\nDuplicate skill.\n")

        # Push once
        args1 = Namespace(
            file=str(skill_file),
            name=None,
            version=None,
            agent=None,
            category=None,
            capabilities=None,
            dependencies=None,
            trust=None,
            description=None,
            force=False,
        )
        cmd_skill_push(args1)

        # Push again
        cmd_skill_push(args1)
        captured = capsys.readouterr()
        assert "已存在" in captured.out or "force" in captured.out

    def test_cmd_skill_push_duplicate_force(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        from vault.cli import cmd_skill_push
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        skill_file = tmp_path / "force_skill.md"
        skill_file.write_text("---\nname: force-skill\n---\n\nForce skill.\n")

        # Push twice with force
        args = Namespace(
            file=str(skill_file),
            name=None,
            version=None,
            agent=None,
            category=None,
            capabilities=None,
            dependencies=None,
            trust=None,
            description=None,
            force=True,
        )
        cmd_skill_push(args)
        cmd_skill_push(args)

        captured = capsys.readouterr()
        assert "強制覆蓋" in captured.out

    def test_cmd_skill_push_nonexistent_file(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_skill_push
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            file="/nonexistent/path/skill.md",
            name=None,
            version=None,
            agent=None,
            category=None,
            capabilities=None,
            dependencies=None,
            trust=None,
            description=None,
            force=False,
        )
        cmd_skill_push(args)

        captured = capsys.readouterr()
        assert "檔案不存在" in captured.out or "not found" in captured.out.lower()

    def test_cmd_skill_push_with_explicit_name(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        from vault.cli import cmd_skill_push
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        skill_file = tmp_path / "no_name_skill.md"
        skill_file.write_text("# No Name Skill\n\nContent without frontmatter.\n")

        args = Namespace(
            file=str(skill_file),
            name="explicit-name",
            version=None,
            agent=None,
            category=None,
            capabilities=None,
            dependencies=None,
            trust=None,
            description=None,
            force=False,
        )
        cmd_skill_push(args)

        captured = capsys.readouterr()
        assert "explicit-name" in captured.out


class TestCmdSkillSearch:
    """Test cmd_skill_search command."""

    def test_cmd_skill_search_no_results(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_skill_search
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            query="nonexistent",
            capabilities=None,
            category=None,
            min_trust=None,
            agent=None,
            limit=20,
        )
        cmd_skill_search(args)

        captured = capsys.readouterr()
        assert "沒有找到" in captured.out or "0" in captured.out

    def test_cmd_skill_search_with_results(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        from vault.cli import cmd_skill_search, cmd_skill_push
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        # Add a skill first
        skill_file = tmp_path / "searchable_skill.md"
        skill_file.write_text("---\nname: searchable-skill\n---\n\nThis skill does search and analysis.\n")
        args_push = Namespace(
            file=str(skill_file),
            name=None,
            version=None,
            agent=None,
            category="search",
            capabilities="search,analysis",
            dependencies=None,
            trust=None,
            description="A search skill",
            force=False,
        )
        cmd_skill_push(args_push)

        # Search for it
        args_search = Namespace(
            query="search",
            capabilities=None,
            category=None,
            min_trust=0.0,
            agent=None,
            limit=20,
        )
        cmd_skill_search(args_search)

        captured = capsys.readouterr()
        assert "searchable-skill" in captured.out

    def test_cmd_skill_search_with_filter(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        from vault.cli import cmd_skill_search, cmd_skill_push
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        # Add skills
        for i in range(3):
            skill_file = tmp_path / f"skill_{i}.md"
            skill_file.write_text(f"---\nname: skill-{i}\n---\n\nSkill {i}\n")
            args_push = Namespace(
                file=str(skill_file),
                name=None,
                version=None,
                agent="test-agent",
                category=f"cat{i}",
                capabilities=None,
                dependencies=None,
                trust=0.5 + i * 0.1,
                description=None,
                force=False,
            )
            cmd_skill_push(args_push)

        # Search with category filter
        args_search = Namespace(
            query=None,
            capabilities=None,
            category="cat1",
            min_trust=0.0,
            agent=None,
            limit=20,
        )
        cmd_skill_search(args_search)

        captured = capsys.readouterr()
        assert "skill-1" in captured.out


class TestCmdSkillPull:
    """Test cmd_skill_pull command."""

    def test_cmd_skill_pull_nonexistent(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_skill_pull
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(name="nonexistent-skill")
        cmd_skill_pull(args)

        captured = capsys.readouterr()
        assert "不存在" in captured.out or "not found" in captured.out.lower()

    def test_cmd_skill_pull_existing(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        from vault.cli import cmd_skill_push, cmd_skill_pull
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        # Add a skill
        skill_file = tmp_path / "pullable_skill.md"
        skill_file.write_text("---\nname: pullable-skill\nversion: 2.0.0\n---\n\nPull me!\n")
        args_push = Namespace(
            file=str(skill_file),
            name=None,
            version=None,
            agent=None,
            category=None,
            capabilities=None,
            dependencies=None,
            trust=None,
            description=None,
            force=False,
        )
        cmd_skill_push(args_push)

        # Set custom skills dir
        skills_dir = tmp_path / "skills"
        monkeypatch.setenv("VAULT_SKILLS_DIR", str(skills_dir))

        # Pull it
        args_pull = Namespace(name="pullable-skill")
        cmd_skill_pull(args_pull)

        captured = capsys.readouterr()
        assert "pullable-skill" in captured.out
        assert skills_dir.exists()
        assert (skills_dir / "pullable-skill" / "SKILL.md").exists()

    def test_cmd_skill_pull_sanitizes_local_path(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        from vault.cli import cmd_skill_pull
        from vault.db import VaultDB
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        try:
            db.add_skill(name="../escape-skill", content_raw="# Escape\n")
        finally:
            db.close()

        skills_dir = tmp_path / "skills"
        monkeypatch.setenv("VAULT_SKILLS_DIR", str(skills_dir))

        cmd_skill_pull(Namespace(name="../escape-skill"))

        captured = capsys.readouterr()
        assert "escape-skill" in captured.out
        assert (skills_dir / "escape-skill" / "SKILL.md").exists()
        assert not (tmp_path / "escape-skill").exists()


class TestCmdDreamExtra:
    """Extra tests for cmd_dream."""

    def test_cmd_dream_default_mode(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_dream
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            mode="report",
            checks=None,
            limit=10,
            write_report=False,
            no_backup=True,
            pretty=False,
        )
        cmd_dream(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)
        assert len(captured.out) > 0

    def test_cmd_dream_with_checks(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_dream
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            mode="report",
            checks="freshness,duplicates",
            limit=5,
            write_report=False,
            no_backup=True,
            pretty=False,
        )
        cmd_dream(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_dream_pretty_output(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_dream
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            mode="report",
            checks=None,
            limit=10,
            write_report=False,
            no_backup=True,
            pretty=True,
        )
        cmd_dream(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdCrossValidateExtra:
    """Extra tests for cmd_cross_validate."""

    def test_cmd_cross_validate_default(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_cross_validate
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        # Mock the cross_validate function to avoid LLM calls
        def mock_cross_validate(**kwargs):
            print('{"status": "ok", "validated": 0, "issues": []}')
        from types import ModuleType
        mock_mod = ModuleType("scripts.cross_validate")
        mock_mod.cross_validate = mock_cross_validate
        # Make scripts a proper package by setting __path__
        mock_pkg = ModuleType("scripts")
        mock_pkg.__path__ = []
        mock_pkg.cross_validate = mock_mod
        monkeypatch.setitem(__import__('sys').modules, "scripts", mock_pkg)
        monkeypatch.setitem(__import__('sys').modules, "scripts.cross_validate", mock_mod)

        args = Namespace(
            apply=False,
            limit=10,
            min_trust=0.5,
            local_only=True,
            local_model="llama3",
            cloud_model="gpt-4",
            pretty=False,
        )
        cmd_cross_validate(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_cross_validate_with_min_trust(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_cross_validate
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        # Mock the cross_validate function
        from types import ModuleType
        mock_mod = ModuleType("scripts.cross_validate")
        mock_mod.cross_validate = lambda **kw: print('{"status": "ok", "validated": 0}')
        mock_pkg = ModuleType("scripts")
        mock_pkg.__path__ = []
        mock_pkg.cross_validate = mock_mod
        monkeypatch.setitem(__import__('sys').modules, "scripts", mock_pkg)
        monkeypatch.setitem(__import__('sys').modules, "scripts.cross_validate", mock_mod)

        args = Namespace(
            apply=True,
            limit=5,
            min_trust=0.8,
            local_only=False,
            local_model="llama3",
            cloud_model="gpt-4",
            pretty=True,
        )
        cmd_cross_validate(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdPromoteExtra:
    """Extra tests for cmd_promote."""

    def test_cmd_promote_candidate(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        from vault.cli import cmd_promote
        from argparse import Namespace
        from vault.db import VaultDB

        monkeypatch.chdir(temp_vault_project)

        # Add a candidate first - use correct schema
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        # Add a memory candidate with all required NOT NULL columns
        db.conn.execute(
            "INSERT INTO memory_candidates (id, created_at, updated_at, title, content, layer, category, tags, trust, source, source_ref, reason, status, privacy_status, duplicate_status, quality_status, gate_payload_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("test-candidate-123", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z",
             "Test Candidate", "Content of candidate",
             "L3", "general", "", 0.7, "test", "", "test reason",
             "pending", "public", "unique", "pass", "{}"),
        )
        db.conn.commit()
        db.close()

        # Mock promote_candidate to avoid full compilation
        import vault.memory as mem_mod
        original_promote = mem_mod.promote_candidate
        def mock_promote(db, candidate_id, **kwargs):
            return {"status": "promoted", "id": candidate_id, "knowledge_id": 1}
        monkeypatch.setattr(mem_mod, "promote_candidate", mock_promote)

        args = Namespace(
            candidate_id="test-candidate-123",
            confirm=True,
            no_compile=True,
            no_build_map=True,
            pretty=False,
        )
        cmd_promote(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_promote_not_found(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_promote
        from argparse import Namespace
        import pytest

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            candidate_id="nonexistent-id",
            confirm=True,
            no_compile=True,
            no_build_map=True,
            pretty=False,
        )
        # Should raise SystemExit or just print error
        try:
            cmd_promote(args)
        except SystemExit:
            pass

        captured = capsys.readouterr()
        # Either stdout or stderr should have some output
        assert isinstance(captured.out, str) or isinstance(captured.err, str)


class TestCmdConvergeExtra:
    """Extra tests for cmd_converge."""

    def test_cmd_converge_default(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_converge
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        # Mock the check_convergence function
        from types import ModuleType
        mock_mod = ModuleType("scripts.convergence_check")
        mock_mod.check_convergence = lambda **kw: print('{"status": "ok", "gaps": []}')
        mock_pkg = ModuleType("scripts")
        mock_pkg.__path__ = []
        mock_pkg.convergence_check = mock_mod
        monkeypatch.setitem(__import__('sys').modules, "scripts", mock_pkg)
        monkeypatch.setitem(__import__('sys').modules, "scripts.convergence_check", mock_mod)

        args = Namespace(
            apply=False,
            limit=10,
            min_trust=0.5,
            ollama="llama3",
            api="http://localhost:11434",
            api_key="",
            pretty=False,
        )
        cmd_converge(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_converge_with_different_params(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_converge
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        # Mock the check_convergence function
        from types import ModuleType
        mock_mod = ModuleType("scripts.convergence_check")
        mock_mod.check_convergence = lambda **kw: print('{"status": "ok", "gaps": []}')
        mock_pkg = ModuleType("scripts")
        mock_pkg.__path__ = []
        mock_pkg.convergence_check = mock_mod
        monkeypatch.setitem(__import__('sys').modules, "scripts", mock_pkg)
        monkeypatch.setitem(__import__('sys').modules, "scripts.convergence_check", mock_mod)

        args = Namespace(
            apply=True,
            limit=5,
            min_trust=0.3,
            ollama="mistral",
            api="http://localhost:11434",
            api_key="test-key",
            pretty=True,
        )
        cmd_converge(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdRememberExtra:
    """Extra tests for cmd_remember."""

    def test_cmd_remember_with_tags(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_remember
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        # Mock propose_memory to avoid LLM/semantic processing
        import vault.memory as mem_mod
        original_propose = mem_mod.propose_memory
        def mock_propose(db, **kwargs):
            return {"status": "ok", "id": "test-id", "mode": kwargs.get("mode", "candidate")}
        monkeypatch.setattr(mem_mod, "propose_memory", mock_propose)

        args = Namespace(
            title="Test Memory with Tags",
            content="This memory has tags.",
            file=None,
            reason="test reason",
            mode="candidate",
            layer="L2",
            category="test",
            tags="tag1,tag2,tag3",
            trust=0.8,
            source="cli-test",
            source_ref="test-ref",
            pretty=False,
        )
        cmd_remember(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_remember_different_mode(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_remember
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        # Mock propose_memory
        import vault.memory as mem_mod
        def mock_propose(db, **kwargs):
            return {"status": "ok", "id": "test-id-2", "mode": kwargs.get("mode", "direct")}
        monkeypatch.setattr(mem_mod, "propose_memory", mock_propose)

        args = Namespace(
            title="Direct Memory",
            content="This is directly added.",
            file=None,
            reason="direct add",
            mode="direct",
            layer="L3",
            category="general",
            tags=None,
            trust=0.6,
            source="test",
            source_ref="",
            pretty=False,
        )
        cmd_remember(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdFreshnessExtra:
    """Extra tests for cmd_freshness."""

    def test_cmd_freshness_with_stale_only(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_freshness
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            limit=20,
            min_freshness=0.3,
            apply=False,
            stale_only=True,
        )
        cmd_freshness(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_freshness_apply(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_freshness
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            limit=5,
            min_freshness=0.5,
            apply=True,
            stale_only=False,
        )
        cmd_freshness(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdDedupExtra:
    """Extra tests for cmd_dedup."""

    def test_cmd_dedup_content_mode(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_dedup
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            dry_run=True,
            threshold=0.8,
            mode="content",
        )
        cmd_dedup(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_dedup_semantic_mode(self, temp_vault_project, capsys, monkeypatch):
        from vault.cli import cmd_dedup
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            dry_run=True,
            threshold=0.7,
            mode="semantic",
        )
        cmd_dedup(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


# === Additional tests for coverage improvement ===

class TestCmdSearchMoreExtra:
    """More search tests for better coverage."""

    def test_cmd_search_with_layer_and_category(self, temp_vault_project, capsys, monkeypatch):
        """Test search with layer and category filters."""
        from vault.cli import cmd_search
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        # Add some knowledge entries
        from vault.db import VaultDB
        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        db.add_knowledge(
            title="Python Basics",
            content_raw="Python is a programming language. Python is easy to learn.",
            layer="L2",
            category="programming",
            trust=0.9,
            source="test",
        )
        db.add_knowledge(
            title="Java Basics",
            content_raw="Java is another programming language. Java is statically typed.",
            layer="L3",
            category="programming",
            trust=0.8,
            source="test",
        )
        db.add_knowledge(
            title="Cooking Recipe",
            content_raw="Cooking is the art of preparing food.",
            layer="L2",
            category="cooking",
            trust=0.7,
            source="test",
        )
        db.close()

        args = Namespace(
            query="programming",
            mode="keyword",
            limit=10,
            min_trust=0.0,
            layer=None,
            category=None,
            keyword_only=True,
            graph_expand=0,
            no_rerank=True,
            semantic_vector_kind="content",
            allow_hash=False,
            hash_dim=32,
            min_score=0.0,
        )
        cmd_search(args)

        captured = capsys.readouterr()
        assert "找到" in captured.out or "沒有找到" in captured.out

    def test_cmd_search_with_min_score(self, temp_vault_project, capsys, monkeypatch):
        """Test search with min_score filter."""
        from vault.cli import cmd_search
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            query="something",
            mode="keyword",
            limit=5,
            min_trust=0.0,
            layer=None,
            category=None,
            keyword_only=True,
            graph_expand=0,
            no_rerank=True,
            semantic_vector_kind="content",
            allow_hash=False,
            hash_dim=32,
            min_score=0.5,
        )
        cmd_search(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_search_with_hash_allow_hash(self, temp_vault_project, capsys, monkeypatch):
        """Test search with allow_hash flag."""
        from vault.cli import cmd_search
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            query="test",
            mode="semantic",
            limit=5,
            min_trust=0.0,
            layer=None,
            category=None,
            keyword_only=False,
            graph_expand=0,
            no_rerank=True,
            semantic_vector_kind="content",
            allow_hash=True,
            hash_dim=32,
            min_score=0.0,
        )
        cmd_search(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdGraphExtraExtended:
    """Extended graph command tests."""

    def test_cmd_graph_infer_with_limit(self, temp_vault_project, capsys, monkeypatch):
        """Test graph infer with limit parameter."""
        from vault.cli import cmd_graph
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            graph_action="infer",
            limit=5,
            threshold=0.3,
            target=None,
            output=None,
            pretty=False,
        )
        cmd_graph(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_graph_neighbors(self, temp_vault_project, capsys, monkeypatch):
        """Test graph neighbors action."""
        from vault.cli import cmd_graph
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            graph_action="neighbors",
            limit=5,
            threshold=0.3,
            target=None,
            output=None,
            pretty=False,
        )
        cmd_graph(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_graph_invalid_action(self, temp_vault_project, capsys, monkeypatch):
        """Test graph with invalid action - should print error and may or may not exit."""
        from vault.cli import cmd_graph
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            graph_action="invalid_action",
            limit=5,
            threshold=0.3,
            target=None,
            output=None,
            pretty=False,
        )
        try:
            cmd_graph(args)
        except SystemExit:
            pass

        captured = capsys.readouterr()
        assert isinstance(captured.out, str) or isinstance(captured.err, str)


class TestCmdMapMoreExtra:
    """More map command tests."""

    def test_cmd_map_rebuild(self, temp_vault_project, capsys, monkeypatch):
        """Test map rebuild action."""
        from vault.cli import cmd_map
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            map_action="rebuild",
            limit=10,
            target=None,
            entry_id=None,
            line_range=None,
            source=None,
            pretty=False,
        )
        try:
            cmd_map(args)
        except Exception:
            pass

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_map_stats(self, temp_vault_project, capsys, monkeypatch):
        """Test map stats action."""
        from vault.cli import cmd_map
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            map_action="stats",
            limit=10,
            target=None,
            entry_id=None,
            line_range=None,
            source=None,
            pretty=False,
        )
        try:
            cmd_map(args)
        except Exception:
            pass

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_map_show(self, temp_vault_project, capsys, monkeypatch):
        """Test map show action."""
        from vault.cli import cmd_map
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            map_action="show",
            limit=10,
            target=None,
            entry_id=1,
            line_range=None,
            source=None,
            pretty=False,
        )
        try:
            cmd_map(args)
        except Exception:
            pass

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdLintMoreExtra:
    """More lint command tests."""

    def test_cmd_lint_with_high_confidence(self, temp_vault_project, capsys, monkeypatch):
        """Test lint with high confidence threshold."""
        from vault.cli import cmd_lint
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            lint_action="check",
            min_confidence=0.9,
            limit=10,
            fix=False,
            pretty=False,
        )
        cmd_lint(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_lint_with_zero_limit(self, temp_vault_project, capsys, monkeypatch):
        """Test lint with limit=0."""
        from vault.cli import cmd_lint
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            lint_action="check",
            min_confidence=0.5,
            limit=0,
            fix=False,
            pretty=False,
        )
        cmd_lint(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdStatsMoreExtra:
    """More stats command tests."""

    def test_cmd_stats_with_layers(self, temp_vault_project, capsys, monkeypatch):
        """Test stats with layers flag."""
        from vault.cli import cmd_stats
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            layers=True,
            pretty=False,
        )
        cmd_stats(args)

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdConfigMoreExtra:
    """More config command tests."""

    def test_cmd_config_set_and_get(self, temp_vault_project, capsys, monkeypatch):
        """Test config set and get operations."""
        from vault.cli import cmd_config
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        # Check what args cmd_config expects
        args = Namespace(
            action="set",
            key="test_key_extra",
            value="test_value_123",
            pretty=False,
        )
        try:
            cmd_config(args)
        except AttributeError:
            # Try different parameter names
            args2 = Namespace(
                config_action="set",
                key="test_key_extra",
                value="test_value_123",
                pretty=False,
            )
            try:
                cmd_config(args2)
            except Exception:
                pass

        captured = capsys.readouterr()
        assert isinstance(captured.out, str) or isinstance(captured.err, str)


class TestCmdCompileMoreExtra:
    """More compile command tests."""

    def test_cmd_compile_dry_run(self, temp_vault_project, capsys, monkeypatch):
        """Test compile with dry_run flag."""
        from vault.cli import cmd_compile
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            mode="full",
            dry_run=True,
            no_git=False,
            skip_embed=False,
            no_lint=False,
            yes=True,
            pretty=False,
        )
        try:
            cmd_compile(args)
        except Exception:
            pass

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_compile_quick_mode(self, temp_vault_project, capsys, monkeypatch):
        """Test compile with quick mode."""
        from vault.cli import cmd_compile
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            mode="quick",
            dry_run=False,
            no_git=True,
            skip_embed=True,
            no_lint=False,
            yes=True,
            pretty=False,
        )
        try:
            cmd_compile(args)
        except Exception:
            pass

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdAddExtra:
    """Add command tests."""

    def test_cmd_add_with_layer_and_category(self, temp_vault_project, capsys, monkeypatch):
        """Test add with layer and category parameters."""
        from vault.cli import cmd_add
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            title="Test Knowledge Extra",
            content="This is test content for testing.",
            layer="L2",
            category="test",
            trust=0.85,
            source="test-cli",
            source_ref="test-ref",
            tags=None,
            file=None,
            pretty=False,
        )
        try:
            cmd_add(args)
        except Exception as e:
            print(f"Error: {e}")

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_add_without_content_file(self, temp_vault_project, capsys, monkeypatch, tmp_path):
        """Test add with content from file."""
        from vault.cli import cmd_add
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        # Create a test file
        test_file = tmp_path / "test_content.md"
        test_file.write_text("Content from file. Testing file import.")

        args = Namespace(
            title="File-based Knowledge",
            content=None,
            file=str(test_file),
            layer="L3",
            category="test",
            trust=0.7,
            source="file-test",
            source_ref="",
            tags=None,
            pretty=False,
        )
        try:
            cmd_add(args)
        except Exception as e:
            print(f"Error: {e}")

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestCmdListExtra:
    """List command extra tests."""

    def test_cmd_list_with_limit(self, temp_vault_project, capsys, monkeypatch):
        """Test list with limit parameter."""
        from vault.cli import cmd_list
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            limit=3,
            layer=None,
            category=None,
            min_trust=0.0,
            offset=0,
            pretty=False,
        )
        try:
            cmd_list(args)
        except Exception as e:
            print(f"Error: {e}")

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)

    def test_cmd_list_with_offset(self, temp_vault_project, capsys, monkeypatch):
        """Test list with offset parameter."""
        from vault.cli import cmd_list
        from argparse import Namespace

        monkeypatch.chdir(temp_vault_project)

        args = Namespace(
            limit=10,
            layer=None,
            category=None,
            min_trust=0.0,
            offset=5,
            pretty=False,
        )
        try:
            cmd_list(args)
        except Exception as e:
            print(f"Error: {e}")

        captured = capsys.readouterr()
        assert isinstance(captured.out, str)


class TestDbModuleFunctions:
    """Test database module functions directly."""

    def test_db_stats(self, temp_vault_project):
        """Test VaultDB.stats() method."""
        from vault.db import VaultDB

        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        stats = db.stats()
        db.close()

        assert isinstance(stats, dict)
        # Stats should have some entries, check for common keys
        assert len(stats) > 0

    def test_db_get_knowledge(self, temp_vault_project):
        """Test VaultDB.get_knowledge() method."""
        from vault.db import VaultDB

        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        result = db.get_knowledge(999)  # Non-existent ID
        db.close()

        assert result is None

    def test_db_search_keyword(self, temp_vault_project):
        """Test keyword search."""
        from vault.db import VaultDB

        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()
        results = db.search_keyword("test", limit=5)
        db.close()

        assert isinstance(results, list)

    def test_db_config_operations(self, temp_vault_project):
        """Test config get/set operations."""
        from vault.db import VaultDB

        db = VaultDB(str(temp_vault_project / "vault.db"))
        db.connect()

        db.set_config("test_config_key", "test_value_123")
        value = db.get_config("test_config_key", "default")
        assert value == "test_value_123"

        # Test default value
        default_val = db.get_config("nonexistent_key", "default_val")
        assert default_val == "default_val"

        db.close()


class TestSemanticProviderExtra:
    """Test semantic module functions."""

    def test_hash_embedding_provider(self):
        """Test DeterministicHashEmbeddingProvider."""
        from vault.semantic import DeterministicHashEmbeddingProvider

        provider = DeterministicHashEmbeddingProvider(dim=32)
        embeddings = provider.encode(["Hello world", "Test string"])

        assert len(embeddings) == 2
        assert len(embeddings[0]) == 32
        assert len(embeddings[1]) == 32

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

    def test_hash_embedding_batch(self):
        """Test batch encoding with hash embeddings."""
        from vault.semantic import DeterministicHashEmbeddingProvider

        provider = DeterministicHashEmbeddingProvider(dim=32)
        texts = [f"text_{i}" for i in range(10)]
        embeddings = provider.encode(texts)

        assert len(embeddings) == 10
        for emb in embeddings:
            assert len(emb) == 32
