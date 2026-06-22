"""MCP helper tests for Vault Document Map tools."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vault.db import VaultDB
from vault.docmap import build_document_map_for_entry
from vault import mcp as vault_mcp


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeTableQuery:
    def __init__(self, client, table_name: str):
        self.client = client
        self.table_name = table_name
        self.filters = []

    def select(self, *args, **kwargs):
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def execute(self):
        rows = self.client.tables.setdefault(self.table_name, [])
        matches = [
            row for row in rows
            if all(row.get(field) == value for field, value in self.filters)
        ]
        return _FakeResponse([dict(row) for row in matches])


class _FakeRpcQuery:
    def __init__(self, client, function_name: str, params: dict):
        self.client = client
        self.function_name = function_name
        self.params = params

    def execute(self):
        self.client.rpc_calls.append((self.function_name, dict(self.params)))
        rows = self.client.rpcs.setdefault(self.function_name, [])
        return _FakeResponse([dict(row) for row in rows])


class _FakeSupabaseClient:
    def __init__(self, tables, rpcs=None):
        self.tables = tables
        self.rpcs = rpcs or {}
        self.rpc_calls = []

    def table(self, table_name: str):
        if table_name not in self.tables:
            raise RuntimeError(f"missing table: {table_name}")
        return _FakeTableQuery(self, table_name)

    def rpc(self, function_name: str, params: dict):
        if function_name not in self.rpcs:
            raise RuntimeError(f"missing rpc: {function_name}")
        return _FakeRpcQuery(self, function_name, params)


def _remote_fake_client():
    return _FakeSupabaseClient(
        {
            vault_mcp.REMOTE_NODE_TABLE: [
                {
                    "knowledge_id": 42,
                    "node_uid": "root",
                    "parent_uid": "",
                    "level": 1,
                    "heading": "Title",
                    "path": "Title",
                    "summary": "Root summary",
                    "line_start": 1,
                    "line_end": 6,
                    "token_estimate": 20,
                    "content_hash": "root-hash",
                    "knowledge_title": "Example",
                    "knowledge_source": "raw/example.md",
                    "knowledge_content_hash": "doc-hash",
                },
                {
                    "knowledge_id": 42,
                    "node_uid": "title-tool",
                    "parent_uid": "root",
                    "level": 2,
                    "heading": "Tool-gated Reading",
                    "path": "Title/Tool-gated Reading",
                    "summary": "Tool gate summary",
                    "line_start": 3,
                    "line_end": 4,
                    "token_estimate": 12,
                    "content_hash": "node-hash",
                    "knowledge_title": "Example",
                    "knowledge_source": "raw/example.md",
                    "knowledge_content_hash": "doc-hash",
                },
            ],
            vault_mcp.REMOTE_CLAIM_TABLE: [
                {
                    "knowledge_id": 42,
                    "node_uid": "title-tool",
                    "claim_uid": "c1",
                    "claim": "Tool-gated reading keeps agents from reading whole documents.",
                    "claim_type": "explicit",
                    "line_start": 4,
                    "line_end": 4,
                    "confidence": 0.9,
                    "source": "aaak",
                    "content_hash": "claim-hash",
                    "knowledge_title": "Example",
                    "knowledge_source": "raw/example.md",
                    "knowledge_content_hash": "doc-hash",
                }
            ],
            vault_mcp.REMOTE_KNOWLEDGE_TABLE: [
                {
                    "title": "Example",
                    "content_hash": "doc-hash",
                    "content_raw": RAW_CONTENT,
                }
            ],
        }
    )


RAW_CONTENT = "\n".join(
    [
        "# Title",
        "intro",
        "## Tool-gated Reading",
        "Tool-gated reading keeps agents from reading whole documents.",
        "## Other Section",
        "other detail",
    ]
)

AAAK_CONTENT = "\n".join(
    [
        "TITLE: Example",
        "CLAIMS:",
        "- [C1] Tool-gated reading keeps agents from reading whole documents. (L3-L4)",
    ]
)


def _create_db_with_entry(tmp_path, *, build_map: bool = True):
    db_path = tmp_path / "vault.db"
    db = VaultDB(db_path).connect()
    try:
        knowledge_id = db.add_knowledge(
            "Example",
            RAW_CONTENT,
            content_aaak=AAAK_CONTENT,
            layer="L3",
            category="technique",
            trust=0.9,
        )
        if build_map:
            build_document_map_for_entry(db.conn, knowledge_id)
    finally:
        db.close()
    return db_path, knowledge_id


def test_vault_map_show_returns_nodes_and_build_hint_when_empty(tmp_path):
    db_path, knowledge_id = _create_db_with_entry(tmp_path, build_map=False)

    empty = vault_mcp._vault_map_show_payload(knowledge_id, db_path=str(db_path))
    assert empty["entry_id"] == knowledge_id
    assert empty["title"] == "Example"
    assert empty["nodes"] == []
    assert empty["error"] == "no_document_map_nodes"
    assert f"vault map build {knowledge_id}" in empty["message"]

    db = VaultDB(db_path).connect()
    try:
        build_document_map_for_entry(db.conn, knowledge_id)
    finally:
        db.close()

    payload = vault_mcp._vault_map_show_payload(knowledge_id, db_path=str(db_path))
    assert payload["entry_id"] == knowledge_id
    assert payload["title"] == "Example"
    assert len(payload["nodes"]) == 3
    assert payload["next_action"]["tool"] == "vault_read_range"
    assert payload["next_actions"][0]["tool"] == "vault_read_range"
    child = next(node for node in payload["nodes"] if node["heading"] == "Tool-gated Reading")
    assert child["node_uid"]
    assert child["path"] == "Title/Tool-gated Reading"
    assert child["level"] == 2
    assert child["line_start"] == 3
    assert child["line_end"] == 4
    assert "summary" in child
    assert "token_estimate" in child

    compact = vault_mcp._vault_map_show_payload(
        knowledge_id,
        db_path=str(db_path),
        compact=True,
    )
    compact_child = next(
        node for node in compact["nodes"] if node["heading"] == "Tool-gated Reading"
    )
    assert compact_child == {
        "node_uid": child["node_uid"],
        "path": "Title/Tool-gated Reading",
        "heading": "Tool-gated Reading",
        "line_start": 3,
        "line_end": 4,
    }
    assert compact["next_action"]["arguments"]["node_uid"] == child["node_uid"]


def test_vault_read_range_by_lines_returns_citation_and_numbered_content(tmp_path):
    db_path, knowledge_id = _create_db_with_entry(tmp_path)

    payload = vault_mcp._vault_read_range_payload(
        knowledge_id,
        line_start=3,
        line_end=4,
        db_path=str(db_path),
    )

    assert payload["entry_id"] == knowledge_id
    assert payload["title"] == "Example"
    assert payload["range"] == "L3-L4"
    assert payload["citation"] == f"#{knowledge_id} Example L3-L4"
    assert payload["content"] == (
        "3|## Tool-gated Reading\n"
        "4|Tool-gated reading keeps agents from reading whole documents."
    )
    assert payload["content_hash"]
    assert payload["node_uid"]
    assert payload["path"] == "Title/Tool-gated Reading"


def test_vault_read_range_uses_node_uid_and_validates_subranges(tmp_path):
    db_path, knowledge_id = _create_db_with_entry(tmp_path)
    map_payload = vault_mcp._vault_map_show_payload(knowledge_id, db_path=str(db_path))
    node_uid = next(
        node["node_uid"]
        for node in map_payload["nodes"]
        if node["heading"] == "Tool-gated Reading"
    )

    payload = vault_mcp._vault_read_range_payload(
        knowledge_id,
        node_uid=node_uid,
        db_path=str(db_path),
    )
    assert payload["range"] == "L3-L4"
    assert payload["node_uid"] == node_uid

    invalid = vault_mcp._vault_read_range_payload(
        knowledge_id,
        node_uid=node_uid,
        line_start=2,
        line_end=4,
        db_path=str(db_path),
    )
    assert invalid["error"] == "range_outside_node"
    assert invalid["node_uid"] == node_uid


def test_vault_read_range_rejects_invalid_and_over_limit_ranges(tmp_path):
    db_path, knowledge_id = _create_db_with_entry(tmp_path)

    invalid_id = vault_mcp._vault_read_range_payload(0, db_path=str(db_path))
    assert invalid_id["error"] == "invalid_knowledge_id"
    assert invalid_id["failure_mode"] == "invalid_knowledge_id"
    assert invalid_id["next_action"]["tool"] == "vault_search"

    invalid_range = vault_mcp._vault_read_range_payload(
        knowledge_id,
        line_start=0,
        line_end=1,
        db_path=str(db_path),
    )
    assert invalid_range["error"] == "invalid_range"
    assert invalid_range["failure_mode"] == "invalid_range"
    assert invalid_range["next_action"]["tool"] == "vault_map_show"

    too_large = vault_mcp._vault_read_range_payload(
        knowledge_id,
        line_start=1,
        line_end=6,
        max_lines=5,
        db_path=str(db_path),
    )
    assert too_large["error"] == "range_too_large"
    assert too_large["failure_mode"] == "range_too_large"
    assert too_large["max_lines"] == 5
    assert "split into smaller ranges" in too_large["message"]
    assert too_large["next_action"]["tool"] == "vault_read_range"

    long_db_path = tmp_path / "long.db"
    db = VaultDB(long_db_path).connect()
    try:
        long_id = db.add_knowledge(
            "Long Example",
            "\n".join(f"line {i}" for i in range(1, 101)),
            layer="L3",
            category="general",
        )
    finally:
        db.close()

    default_limit = vault_mcp._vault_read_range_payload(
        long_id,
        line_start=1,
        line_end=81,
        db_path=str(long_db_path),
    )
    assert default_limit["error"] == "range_too_large"
    assert default_limit["max_lines"] == 80


def test_handle_tool_call_routes_document_map_tools(tmp_path, monkeypatch):
    db_path, knowledge_id = _create_db_with_entry(tmp_path)
    monkeypatch.setattr(vault_mcp, "DB_PATH", str(db_path))

    show_response = vault_mcp.handle_tool_call(
        "vault_map_show",
        {"knowledge_id": knowledge_id, "compact": True},
    )
    show_payload = json.loads(show_response["result"])
    assert show_payload["entry_id"] == knowledge_id
    assert show_payload["nodes"]
    assert "summary" not in show_payload["nodes"][0]

    search_response = vault_mcp.handle_tool_call(
        "vault_search",
        {"query": "tool-gated reading", "mode": "keyword"},
    )
    search_payload = json.loads(search_response["result"])
    assert search_payload[0]["id"] == knowledge_id
    assert search_payload[0]["next_action"]["tool"] == "vault_map_show"
    assert search_payload[0]["next_actions"][1]["tool"] == "vault_read_range"
    assert search_payload[0]["recommended_next_tool"] == "vault_read_range"
    assert "content_preview" not in search_payload[0]
    assert "content_raw" not in search_payload[0]
    assert "content_aaak" not in search_payload[0]
    assert "best_node" not in search_payload[0]

    full_search_response = vault_mcp.handle_tool_call(
        "vault_search",
        {"query": "tool-gated reading", "mode": "keyword", "compact": False},
    )
    full_search_payload = json.loads(full_search_response["result"])
    assert full_search_payload[0]["id"] == knowledge_id
    assert "content_preview" in full_search_payload[0]
    assert "Tool-gated reading keeps agents" in full_search_payload[0]["content_preview"]
    assert "best_node" in full_search_payload[0]

    read_response = vault_mcp.handle_tool_call(
        "vault_read_range",
        {"knowledge_id": knowledge_id, "line_start": 3, "line_end": 4},
    )
    read_payload = json.loads(read_response["result"])
    assert read_payload["citation"] == f"#{knowledge_id} Example L3-L4"
    assert "3|## Tool-gated Reading" in read_payload["content"]


def test_public_vault_mcp_tools_are_listed_and_routed(tmp_path, monkeypatch):
    db_path, knowledge_id = _create_db_with_entry(tmp_path)
    monkeypatch.setattr(vault_mcp, "DB_PATH", str(db_path))

    tool_names = {tool["name"] for tool in vault_mcp.TOOLS}
    assert "vault_search" in tool_names
    search_tool = next(tool for tool in vault_mcp.TOOLS if tool["name"] == "vault_search")
    assert search_tool["inputSchema"]["properties"]["compact"]["default"] is True
    assert "vault_add" in tool_names
    assert "vault_stats" in tool_names
    assert "vault_map_show" in tool_names
    assert "vault_read_range" in tool_names
    assert all(name.startswith("vault_") for name in tool_names)

    show_response = vault_mcp.handle_tool_call(
        "vault_map_show",
        {"knowledge_id": knowledge_id, "compact": True},
    )
    show_payload = json.loads(show_response["result"])
    assert show_payload["entry_id"] == knowledge_id

    read_response = vault_mcp.handle_tool_call(
        "vault_read_range",
        {"knowledge_id": knowledge_id, "line_start": 3, "line_end": 4},
    )
    read_payload = json.loads(read_response["result"])
    assert read_payload["citation"] == f"#{knowledge_id} Example L3-L4"


def test_set_project_dir_points_mcp_at_project_db(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    original = vault_mcp.DB_PATH
    try:
        vault_mcp._set_project_dir(project)
        assert vault_mcp.DB_PATH == str((project / "vault.db").resolve())
    finally:
        vault_mcp.DB_PATH = original


def test_mcp_server_info_uses_public_vault_name(capsys, monkeypatch):
    messages = iter([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
    ])
    monkeypatch.setattr("sys.stdin", messages)
    vault_mcp.run_stdio()
    response = json.loads(capsys.readouterr().out.strip())
    assert response["result"]["serverInfo"]["name"] == "vault-mcp"



def test_vault_remote_map_show_uses_synced_supabase_nodes():
    payload = vault_mcp._vault_remote_map_show_payload(42, sb_client=_remote_fake_client())

    assert payload["entry_id"] == 42
    assert payload["title"] == "Example"
    assert payload["source"] == "supabase"
    assert [node["node_uid"] for node in payload["nodes"]] == ["root", "title-tool"]
    assert payload["next_action"]["tool"] == "vault_remote_read_range"
    assert payload["next_action"]["arguments"]["node_uid"] == "title-tool"

    compact = vault_mcp._vault_remote_map_show_payload(
        42,
        compact=True,
        sb_client=_remote_fake_client(),
    )
    assert compact["nodes"][1] == {
        "node_uid": "title-tool",
        "path": "Title/Tool-gated Reading",
        "heading": "Tool-gated Reading",
        "line_start": 3,
        "line_end": 4,
    }


def test_vault_remote_search_uses_readable_rpc_without_raw_content():
    fake = _remote_fake_client()
    fake.rpcs["vault_search_readable"] = [
        {
            "id": 42,
            "title": "Example",
            "summary": "Safe remote summary",
            "source": "raw/example.md",
            "scope": "project",
            "sensitivity": "medium",
            "memory_type": "knowledge",
            "content_raw": "must not be exposed",
        }
    ]

    payload = vault_mcp._vault_remote_search_payload(
        "summary",
        agent_id="coco",
        include_private=False,
        max_sensitivity="medium",
        limit=5,
        sb_client=fake,
    )

    assert payload["rpc"] == "vault_search_readable"
    assert payload["count"] == 1
    assert fake.rpc_calls == [
        (
            "vault_search_readable",
            {
                "p_agent_id": "coco",
                "p_query": "summary",
                "p_include_private": False,
                "p_max_sensitivity": "medium",
                "p_limit": 5,
            },
        )
    ]
    result = payload["results"][0]
    assert result["id"] == 42
    assert result["summary"] == "Safe remote summary"
    assert "content_raw" not in result
    assert result["next_action"]["tool"] == "vault_remote_map_show"


def test_vault_remote_search_tool_is_in_remote_profile():
    remote_tools = {tool["name"] for tool in vault_mcp.select_tools("remote")}
    assert "vault_remote_search" in remote_tools


def test_vault_remote_read_range_uses_content_raw_when_available():
    payload = vault_mcp._vault_remote_read_range_payload(
        42,
        node_uid="title-tool",
        sb_client=_remote_fake_client(),
    )

    assert payload["entry_id"] == 42
    assert payload["title"] == "Example"
    assert payload["source"] == "remote_content_raw"
    assert payload["range"] == "L3-L4"
    assert payload["citation"] == "#42 Example L3-L4"
    assert payload["content"] == (
        "3|## Tool-gated Reading\n"
        "4|Tool-gated reading keeps agents from reading whole documents."
    )
    assert payload["node_uid"] == "title-tool"
    assert payload["path"] == "Title/Tool-gated Reading"
    assert payload["content_hash"] == "node-hash"
    assert payload["next_action"]["tool"] == "final_answer"


def test_vault_remote_read_range_falls_back_to_claim_rows_and_bounds_ranges():
    fake = _remote_fake_client()
    fake.tables[vault_mcp.REMOTE_KNOWLEDGE_TABLE] = []

    payload = vault_mcp._vault_remote_read_range_payload(
        42,
        line_start=4,
        line_end=4,
        sb_client=fake,
    )
    assert payload["source"] == "remote_claims"
    assert payload["citation"] == "#42 Example L4-L4"
    assert payload["content"] == "4|Tool-gated reading keeps agents from reading whole documents."

    too_large = vault_mcp._vault_remote_read_range_payload(
        42,
        line_start=1,
        line_end=81,
        sb_client=fake,
    )
    assert too_large["error"] == "range_too_large"
    assert too_large["next_action"]["tool"] == "vault_remote_read_range"

    missing_claim = vault_mcp._vault_remote_read_range_payload(
        42,
        line_start=3,
        line_end=3,
        sb_client=fake,
    )
    assert missing_claim["error"] == "source_content_unavailable"
    assert missing_claim["next_action"]["tool"] == "vault_remote_map_show"


def test_vault_remote_read_range_claim_fallback_hashes_returned_content():
    fake = _remote_fake_client()
    fake.tables[vault_mcp.REMOTE_KNOWLEDGE_TABLE] = []

    payload = vault_mcp._vault_remote_read_range_payload(
        42,
        node_uid="title-tool",
        sb_client=fake,
    )

    assert payload["source"] == "remote_claims"
    assert payload["content_hash"] == vault_mcp._content_hash_for_text(payload["content"])
    assert payload["content_hash"] != "node-hash"


def test_handle_tool_call_routes_remote_document_map_tools(monkeypatch):
    monkeypatch.setattr(vault_mcp, "_get_supabase_client", _remote_fake_client)

    show_response = vault_mcp.handle_tool_call(
        "vault_remote_map_show",
        {"knowledge_id": 42, "compact": True},
    )
    show_payload = json.loads(show_response["result"])
    assert show_payload["source"] == "supabase"
    assert show_payload["next_action"]["tool"] == "vault_remote_read_range"

    read_response = vault_mcp.handle_tool_call(
        "vault_remote_read_range",
        {"knowledge_id": 42, "node_uid": "title-tool"},
    )
    read_payload = json.loads(read_response["result"])
    assert read_payload["citation"] == "#42 Example L3-L4"
    assert "4|Tool-gated reading" in read_payload["content"]


def test_handle_tool_call_routes_vault_remote_search(monkeypatch):
    fake = _remote_fake_client()
    fake.rpcs["vault_search_readable"] = [{"id": 42, "title": "Example", "summary": "Safe"}]
    monkeypatch.setattr(vault_mcp, "_get_supabase_client", lambda: fake)

    response = vault_mcp.handle_tool_call(
        "vault_remote_search",
        {"query": "Safe", "agent_id": "mori", "limit": 3},
    )

    payload = json.loads(response["result"])
    assert payload["count"] == 1
    assert payload["results"][0]["next_action"]["tool"] == "vault_remote_map_show"
