"""Deterministic policy harness tests for agent reading behavior."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from guardrails_lite.agent_policy import validate_agent_behavior


def _search_event(knowledge_id: int = 42, citation: str = "#42 Example L3-L4") -> dict:
    return {
        "tool": "guardrails_search",
        "arguments": {"query": "tool-gated reading"},
        "output": [
            {
                "id": knowledge_id,
                "title": "Example",
                "citation": citation,
                "recommended_next_tool": "guardrails_read_range",
            }
        ],
    }


def _map_event(knowledge_id: int = 42, node_uid: str = "title-tool") -> dict:
    return {
        "tool": "guardrails_map_show",
        "arguments": {"knowledge_id": knowledge_id},
        "output": {
            "entry_id": knowledge_id,
            "title": "Example",
            "nodes": [
                {
                    "node_uid": node_uid,
                    "path": "Title/Tool-gated Reading",
                    "line_start": 3,
                    "line_end": 4,
                }
            ],
        },
    }


def _read_event(
    knowledge_id: int = 42,
    citation: str = "#42 Example L3-L4",
    node_uid: str = "title-tool",
) -> dict:
    return {
        "tool": "guardrails_read_range",
        "arguments": {"knowledge_id": knowledge_id, "node_uid": node_uid},
        "output": {
            "entry_id": knowledge_id,
            "title": "Example",
            "range": "L3-L4",
            "citation": citation,
            "content": "3|## Tool-gated Reading\n4|Tool-gated reading keeps agents bounded.",
        },
    }


def test_valid_loop_requires_search_map_read_and_read_range_citation():
    result = validate_agent_behavior(
        [_search_event(), _map_event(), _read_event()],
        "Tool-gated reading keeps agents bounded. #42 Example L3-L4",
    )

    assert result["ok"] is True
    assert result["failure_mode"] is None
    assert result["knowledge_id"] == 42
    assert result["citations"] == ["#42 Example L3-L4"]


def test_search_citation_alone_is_navigation_hint_not_final_support():
    result = validate_agent_behavior(
        [_search_event()],
        "Tool-gated reading keeps agents bounded. #42 Example L3-L4",
    )

    assert result["ok"] is False
    assert result["failure_mode"] == "missing_read_range"
    assert result["next_action"]["tool"] == "guardrails_map_show"


def test_citation_free_answer_fails_when_citation_required():
    result = validate_agent_behavior(
        [_search_event(), _map_event(), _read_event()],
        "Tool-gated reading keeps agents bounded.",
        requires_citation=True,
    )

    assert result["ok"] is False
    assert result["failure_mode"] == "missing_final_citation"
    assert result["next_action"]["tool"] == "guardrails_read_range"


def test_invented_final_citation_fails_even_after_read_range():
    result = validate_agent_behavior(
        [_search_event(), _map_event(), _read_event()],
        "Tool-gated reading keeps agents bounded. #42 Example L5-L6",
    )

    assert result["ok"] is False
    assert result["failure_mode"] == "unsupported_citation"
    assert result["unsupported_citations"] == ["#42 Example L5-L6"]


def test_loop_must_use_same_knowledge_id_across_tools():
    result = validate_agent_behavior(
        [_search_event(42), _map_event(42), _read_event(99, "#99 Other L3-L4")],
        "Tool-gated reading keeps agents bounded. #99 Other L3-L4",
    )

    assert result["ok"] is False
    assert result["failure_mode"] == "knowledge_id_mismatch"
    assert result["next_action"]["tool"] == "guardrails_read_range"
