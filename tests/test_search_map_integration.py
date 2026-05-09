"""Search integration tests for Document Map enrichment."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vault.guardrails_db import GuardrailsDB
from vault.guardrails_map import build_document_map_for_entry
from vault.guardrails_search import GuardrailsSearch


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


def _create_entry(db, *, build_map: bool = True) -> int:
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
    return knowledge_id


def test_search_results_include_document_map_metadata_when_available(tmp_path):
    db = GuardrailsDB(tmp_path / "guardrails.db").connect()
    try:
        knowledge_id = _create_entry(db, build_map=True)
        search = GuardrailsSearch(db, embed_provider=None)

        results = search.search(
            "tool-gated reading",
            mode="keyword",
            limit=3,
            use_rerank=False,
        )

        assert len(results) == 1
        result = results[0]
        assert result["id"] == knowledge_id
        assert result["node_uid"]
        assert result["path"] == "Title/Tool-gated Reading"
        assert result["heading"] == "Tool-gated Reading"
        assert result["line_start"] == 3
        assert result["line_end"] == 4
        assert result["best_span"] == "L3-L4"
        assert result["best_node"]["path"] == "Title/Tool-gated Reading"
        assert result["citation"] == f"#{knowledge_id} Example L3-L4"
        assert result["recommended_next_tool"] == "guardrails_read_range"
        assert result["next_action"] == {
            "tool": "guardrails_map_show",
            "arguments": {"knowledge_id": knowledge_id},
        }
        assert result["next_actions"][-1] == {
            "tool": "guardrails_read_range",
            "arguments": {
                "knowledge_id": knowledge_id,
                "node_uid": result["node_uid"],
                "line_start": 3,
                "line_end": 4,
            },
        }

        compact_results = search.search(
            "tool-gated reading",
            mode="keyword",
            limit=3,
            use_rerank=False,
            compact=True,
        )
        compact = compact_results[0]
        assert compact["id"] == knowledge_id
        assert compact["citation"] == f"#{knowledge_id} Example L3-L4"
        assert compact["next_action"] == result["next_action"]
        assert "content_raw" not in compact
        assert "content_aaak" not in compact
    finally:
        db.close()


def test_search_results_stay_backward_compatible_without_document_map(tmp_path):
    db = GuardrailsDB(tmp_path / "guardrails.db").connect()
    try:
        knowledge_id = _create_entry(db, build_map=False)
        search = GuardrailsSearch(db, embed_provider=None)

        results = search.search(
            "tool-gated reading",
            mode="keyword",
            limit=3,
            use_rerank=False,
        )

        assert len(results) == 1
        result = results[0]
        assert result["id"] == knowledge_id
        assert "best_claim" in result
        assert "citation" not in result
        assert "recommended_next_tool" not in result
        assert "node_uid" not in result
    finally:
        db.close()
