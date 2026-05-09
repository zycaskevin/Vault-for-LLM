"""MCP helper tests for Guardrails Document Map tools."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from guardrails_lite.guardrails_db import GuardrailsDB
from guardrails_lite.guardrails_map import build_document_map_for_entry
from guardrails_lite import guardrails_mcp


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
    db_path = tmp_path / "guardrails.db"
    db = GuardrailsDB(db_path).connect()
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


def test_guardrails_map_show_returns_nodes_and_build_hint_when_empty(tmp_path):
    db_path, knowledge_id = _create_db_with_entry(tmp_path, build_map=False)

    empty = guardrails_mcp._guardrails_map_show_payload(knowledge_id, db_path=str(db_path))
    assert empty["entry_id"] == knowledge_id
    assert empty["title"] == "Example"
    assert empty["nodes"] == []
    assert empty["error"] == "no_document_map_nodes"
    assert f"guardrails map build {knowledge_id}" in empty["message"]

    db = GuardrailsDB(db_path).connect()
    try:
        build_document_map_for_entry(db.conn, knowledge_id)
    finally:
        db.close()

    payload = guardrails_mcp._guardrails_map_show_payload(knowledge_id, db_path=str(db_path))
    assert payload["entry_id"] == knowledge_id
    assert payload["title"] == "Example"
    assert len(payload["nodes"]) == 3
    assert payload["next_action"]["tool"] == "guardrails_read_range"
    assert payload["next_actions"][0]["tool"] == "guardrails_read_range"
    child = next(node for node in payload["nodes"] if node["heading"] == "Tool-gated Reading")
    assert child["node_uid"]
    assert child["path"] == "Title/Tool-gated Reading"
    assert child["level"] == 2
    assert child["line_start"] == 3
    assert child["line_end"] == 4
    assert "summary" in child
    assert "token_estimate" in child

    compact = guardrails_mcp._guardrails_map_show_payload(
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


def test_guardrails_read_range_by_lines_returns_citation_and_numbered_content(tmp_path):
    db_path, knowledge_id = _create_db_with_entry(tmp_path)

    payload = guardrails_mcp._guardrails_read_range_payload(
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


def test_guardrails_read_range_uses_node_uid_and_validates_subranges(tmp_path):
    db_path, knowledge_id = _create_db_with_entry(tmp_path)
    map_payload = guardrails_mcp._guardrails_map_show_payload(knowledge_id, db_path=str(db_path))
    node_uid = next(
        node["node_uid"]
        for node in map_payload["nodes"]
        if node["heading"] == "Tool-gated Reading"
    )

    payload = guardrails_mcp._guardrails_read_range_payload(
        knowledge_id,
        node_uid=node_uid,
        db_path=str(db_path),
    )
    assert payload["range"] == "L3-L4"
    assert payload["node_uid"] == node_uid

    invalid = guardrails_mcp._guardrails_read_range_payload(
        knowledge_id,
        node_uid=node_uid,
        line_start=2,
        line_end=4,
        db_path=str(db_path),
    )
    assert invalid["error"] == "range_outside_node"
    assert invalid["node_uid"] == node_uid


def test_guardrails_read_range_rejects_invalid_and_over_limit_ranges(tmp_path):
    db_path, knowledge_id = _create_db_with_entry(tmp_path)

    invalid_id = guardrails_mcp._guardrails_read_range_payload(0, db_path=str(db_path))
    assert invalid_id["error"] == "invalid_knowledge_id"
    assert invalid_id["failure_mode"] == "invalid_knowledge_id"
    assert invalid_id["next_action"]["tool"] == "guardrails_search"

    invalid_range = guardrails_mcp._guardrails_read_range_payload(
        knowledge_id,
        line_start=0,
        line_end=1,
        db_path=str(db_path),
    )
    assert invalid_range["error"] == "invalid_range"
    assert invalid_range["failure_mode"] == "invalid_range"
    assert invalid_range["next_action"]["tool"] == "guardrails_map_show"

    too_large = guardrails_mcp._guardrails_read_range_payload(
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
    assert too_large["next_action"]["tool"] == "guardrails_read_range"

    long_db_path = tmp_path / "long.db"
    db = GuardrailsDB(long_db_path).connect()
    try:
        long_id = db.add_knowledge(
            "Long Example",
            "\n".join(f"line {i}" for i in range(1, 101)),
            layer="L3",
            category="general",
        )
    finally:
        db.close()

    default_limit = guardrails_mcp._guardrails_read_range_payload(
        long_id,
        line_start=1,
        line_end=81,
        db_path=str(long_db_path),
    )
    assert default_limit["error"] == "range_too_large"
    assert default_limit["max_lines"] == 80


def test_handle_tool_call_routes_document_map_tools(tmp_path, monkeypatch):
    db_path, knowledge_id = _create_db_with_entry(tmp_path)
    monkeypatch.setattr(guardrails_mcp, "DB_PATH", str(db_path))

    show_response = guardrails_mcp.handle_tool_call(
        "guardrails_map_show",
        {"knowledge_id": knowledge_id, "compact": True},
    )
    show_payload = json.loads(show_response["result"])
    assert show_payload["entry_id"] == knowledge_id
    assert show_payload["nodes"]
    assert "summary" not in show_payload["nodes"][0]

    search_response = guardrails_mcp.handle_tool_call(
        "guardrails_search",
        {"query": "tool-gated reading", "mode": "keyword", "compact": True},
    )
    search_payload = json.loads(search_response["result"])
    assert search_payload[0]["id"] == knowledge_id
    assert search_payload[0]["next_action"]["tool"] == "guardrails_map_show"
    assert "content_preview" not in search_payload[0]
    assert "best_node" not in search_payload[0]

    read_response = guardrails_mcp.handle_tool_call(
        "guardrails_read_range",
        {"knowledge_id": knowledge_id, "line_start": 3, "line_end": 4},
    )
    read_payload = json.loads(read_response["result"])
    assert read_payload["citation"] == f"#{knowledge_id} Example L3-L4"
    assert "3|## Tool-gated Reading" in read_payload["content"]
