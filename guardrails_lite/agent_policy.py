"""Deterministic policy checks for Guardrails agent reading loops.

The harness is intentionally small and pure: tests can feed simulated tool
calls plus a final answer and get a stable accept/reject payload. It enforces
that final-answer citations come from ``guardrails_read_range`` outputs, not
from search snippets.
"""

from __future__ import annotations

import json
import re
from typing import Any

CITATION_RE = re.compile(r"#(?P<id>\d+)\s+[^#\n]+?\s+L\d+-L\d+")
SEARCH_TOOLS = {"guardrails_search"}
MAP_SHOW_TOOLS = {"guardrails_map_show", "guardrails_remote_map_show"}
READ_RANGE_TOOLS = {"guardrails_read_range", "guardrails_remote_read_range"}


def _load_output(event: dict[str, Any]) -> Any:
    output = event.get("output", event.get("result"))
    if isinstance(output, str):
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return output
    if isinstance(output, dict) and isinstance(output.get("result"), str):
        try:
            return json.loads(output["result"])
        except json.JSONDecodeError:
            return output["result"]
    return output


def _tool_name(event: dict[str, Any]) -> str:
    return str(event.get("tool") or event.get("name") or "")


def _as_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _event_knowledge_ids(event: dict[str, Any]) -> set[int]:
    ids: set[int] = set()
    args = event.get("arguments") or event.get("args") or {}
    if isinstance(args, dict):
        parsed = _as_int(args.get("knowledge_id") or args.get("id"))
        if parsed is not None:
            ids.add(parsed)

    output = _load_output(event)
    items = output if isinstance(output, list) else [output]
    for item in items:
        if not isinstance(item, dict):
            continue
        parsed = _as_int(item.get("entry_id") or item.get("knowledge_id") or item.get("id"))
        if parsed is not None:
            ids.add(parsed)
    return ids


def _extract_citations(text: Any) -> list[str]:
    if not isinstance(text, str):
        return []
    citations: list[str] = []
    for match in CITATION_RE.finditer(text):
        citation = match.group(0).rstrip(".,;:)")
        if citation not in citations:
            citations.append(citation)
    return citations


def _read_range_citations(events: list[dict[str, Any]]) -> list[str]:
    citations: list[str] = []
    for event in events:
        if _tool_name(event) not in READ_RANGE_TOOLS:
            continue
        output = _load_output(event)
        if isinstance(output, dict) and output.get("citation"):
            citation = str(output["citation"])
            if citation not in citations:
                citations.append(citation)
    return citations


def _failure(
    mode: str,
    message: str,
    *,
    knowledge_id: int | None = None,
    citations: list[str] | None = None,
    unsupported_citations: list[str] | None = None,
) -> dict[str, Any]:
    next_action = _next_action(mode, knowledge_id)
    return {
        "ok": False,
        "failure_mode": mode,
        "message": message,
        "knowledge_id": knowledge_id,
        "citations": citations or [],
        "unsupported_citations": unsupported_citations or [],
        "next_action": next_action,
    }


def _next_action(mode: str, knowledge_id: int | None = None) -> dict[str, Any]:
    if mode in {"missing_search", "invalid_trace"}:
        return {"tool": "guardrails_search", "arguments": {}}
    if mode in {"missing_map_show", "missing_read_range"}:
        args = {"knowledge_id": knowledge_id} if knowledge_id else {}
        return {"tool": "guardrails_map_show", "arguments": args}
    if mode in {"missing_final_citation", "unsupported_citation", "wrong_tool_order", "knowledge_id_mismatch"}:
        args = {"knowledge_id": knowledge_id} if knowledge_id else {}
        return {"tool": "guardrails_read_range", "arguments": args}
    return {"tool": "guardrails_search", "arguments": {}}


def validate_agent_behavior(
    tool_events: list[dict[str, Any]],
    final_answer: str,
    *,
    requires_citation: bool = True,
) -> dict[str, Any]:
    """Validate an agent trace follows search → map_show → read_range.

    A passing trace must use the same ``knowledge_id`` across all three tools.
    If citations are required, every final-answer citation must exactly match a
    citation emitted by ``guardrails_read_range``.
    """
    events = tool_events or []
    final_citations = _extract_citations(final_answer)

    search_positions = [
        (idx, _event_knowledge_ids(event))
        for idx, event in enumerate(events)
        if _tool_name(event) in SEARCH_TOOLS
    ]
    map_positions = [
        (idx, _event_knowledge_ids(event))
        for idx, event in enumerate(events)
        if _tool_name(event) in MAP_SHOW_TOOLS
    ]
    read_positions = [
        (idx, _event_knowledge_ids(event))
        for idx, event in enumerate(events)
        if _tool_name(event) in READ_RANGE_TOOLS
    ]

    if not search_positions:
        return _failure(
            "missing_search",
            "Trace must begin with guardrails_search before citing knowledge.",
            citations=final_citations,
        )

    first_search_ids = set().union(*(ids for _, ids in search_positions))
    hinted_id = next(iter(first_search_ids), None)

    if not read_positions:
        return _failure(
            "missing_read_range",
            "Search citations are navigation hints only; call guardrails_read_range before final citation.",
            knowledge_id=hinted_id,
            citations=final_citations,
        )

    if not map_positions:
        return _failure(
            "missing_map_show",
            "Trace must inspect guardrails_map_show before guardrails_read_range.",
            knowledge_id=hinted_id,
            citations=final_citations,
        )

    all_search_ids = set().union(*(ids for _, ids in search_positions))
    all_map_ids = set().union(*(ids for _, ids in map_positions))
    all_read_ids = set().union(*(ids for _, ids in read_positions))
    common_ids = all_search_ids & all_map_ids & all_read_ids
    if not common_ids:
        return _failure(
            "knowledge_id_mismatch",
            "search, map_show, and read_range must operate on the same knowledge_id.",
            knowledge_id=hinted_id,
            citations=final_citations,
        )
    knowledge_id = min(common_ids)

    search_idx = min(idx for idx, ids in search_positions if knowledge_id in ids)
    map_idx = min(idx for idx, ids in map_positions if knowledge_id in ids)
    read_idx = min(idx for idx, ids in read_positions if knowledge_id in ids)
    if not (search_idx < map_idx < read_idx):
        return _failure(
            "wrong_tool_order",
            "Required order is guardrails_search → guardrails_map_show → guardrails_read_range.",
            knowledge_id=knowledge_id,
            citations=final_citations,
        )

    read_citations = _read_range_citations(events)
    if requires_citation and not final_citations:
        return _failure(
            "missing_final_citation",
            "Final answer must include a citation emitted by guardrails_read_range.",
            knowledge_id=knowledge_id,
            citations=[],
        )

    unsupported = [c for c in final_citations if c not in read_citations]
    if unsupported:
        return _failure(
            "unsupported_citation",
            "Final answer contains citations not emitted by guardrails_read_range.",
            knowledge_id=knowledge_id,
            citations=final_citations,
            unsupported_citations=unsupported,
        )

    return {
        "ok": True,
        "failure_mode": None,
        "message": "Trace satisfies Guardrails reading loop policy.",
        "knowledge_id": knowledge_id,
        "citations": final_citations,
        "read_range_citations": read_citations,
        "next_action": {"tool": "final_answer", "arguments": {}},
    }
