"""JSON shape helpers for the local Vault GUI."""

from __future__ import annotations

import json
from typing import Any

from .db import VaultDB

def compact_knowledge(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "title": row.get("title", ""),
        "category": row.get("category", ""),
        "layer": row.get("layer", ""),
        "trust": row.get("trust", 0),
        "summary": row.get("summary", ""),
        "tags": row.get("tags", ""),
        "source": row.get("source", ""),
        "scope": row.get("scope", "project"),
        "sensitivity": row.get("sensitivity", "low"),
        "owner_agent": row.get("owner_agent", ""),
        "memory_type": row.get("memory_type", ""),
        "valid_from": row.get("valid_from", ""),
        "valid_until": row.get("valid_until", ""),
        "expires_at": row.get("expires_at", ""),
        "best_span": row.get("best_span", ""),
        "line_start": row.get("line_start"),
        "line_end": row.get("line_end"),
        "_score": row.get("_score"),
        "_snippet": row.get("_snippet", ""),
        "usage_count": row.get("usage_count", 0),
        "last_accessed_at": row.get("last_accessed_at", ""),
    }


def compact_candidate(
    row: dict[str, Any],
    *,
    include_content: bool = False,
    include_preview: bool = False,
    include_gates: bool = False,
) -> dict[str, Any]:
    content = row.get("content") or ""
    item = {
        "id": row.get("id"),
        "title": row.get("title", ""),
        "status": row.get("status", ""),
        "layer": row.get("layer", ""),
        "category": row.get("category", ""),
        "tags": row.get("tags", ""),
        "trust": row.get("trust", 0),
        "scope": row.get("scope", "project"),
        "sensitivity": row.get("sensitivity", "low"),
        "owner_agent": row.get("owner_agent", ""),
        "allowed_agents": row.get("allowed_agents", ""),
        "memory_type": row.get("memory_type", ""),
        "expires_at": row.get("expires_at", ""),
        "valid_from": row.get("valid_from", ""),
        "valid_until": row.get("valid_until", ""),
        "supersedes_id": row.get("supersedes_id"),
        "source": row.get("source", ""),
        "source_ref": row.get("source_ref", ""),
        "reason": row.get("reason", ""),
        "privacy_status": row.get("privacy_status", ""),
        "duplicate_status": row.get("duplicate_status", ""),
        "quality_status": row.get("quality_status", ""),
        "promoted_knowledge_id": row.get("promoted_knowledge_id"),
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
        "content_length": len(content),
    }
    if include_preview:
        item["content_preview"] = " ".join(content.split())[:220]
    if include_content:
        item["content"] = content
    if include_gates:
        item["gates"] = parse_json(row.get("gate_payload_json") or "{}")
    return item


def compact_task(row: dict[str, Any]) -> dict[str, Any]:
    """Return a GUI-safe Task Ledger item without raw event payload expansion."""
    return {
        "id": row.get("id", ""),
        "title": row.get("title", "") or row.get("id", ""),
        "goal": row.get("goal", ""),
        "status": row.get("status", ""),
        "priority": row.get("priority", "P2"),
        "due_at": row.get("due_at", ""),
        "current_plan": row.get("current_plan", []),
        "completed": row.get("completed", []),
        "hard_decisions": row.get("hard_decisions", []),
        "blockers": row.get("blockers", []),
        "open_questions": row.get("open_questions", []),
        "next_actions": row.get("next_actions", []),
        "continuation_note": row.get("continuation_note", ""),
        "evidence_refs": row.get("evidence_refs", []),
        "events": row.get("events", []),
        "scope": row.get("scope", "project"),
        "sensitivity": row.get("sensitivity", "low"),
        "owner_agent": row.get("owner_agent", ""),
        "allowed_agents": row.get("allowed_agents", ""),
        "source": row.get("source", ""),
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
        "completed_at": row.get("completed_at", ""),
    }


def compact_review_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": payload.get("status"),
        "candidate_id": payload.get("candidate_id"),
        "knowledge_id": payload.get("knowledge_id"),
        "outcome": payload.get("outcome"),
        "score": payload.get("score"),
        "reason": payload.get("reason"),
        "raw_path": payload.get("raw_path"),
        "gates": payload.get("gates", {}),
        "next_action": payload.get("next_action", ""),
    }


def compact_brief(brief: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": brief.get("status", ""),
        "summary": brief.get("summary", {}),
        "human_review": brief.get("human_review_5_percent", {}),
        "learning": brief.get("learning", {}),
        "forgetting_strategy": brief.get("forgetting_strategy", {}),
        "agent_health": brief.get("agent_health", {}),
        "next_action": brief.get("next_action", ""),
    }


def compact_inbox(inbox: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": inbox.get("status", ""),
        "summary": inbox.get("summary", {}),
        "review_digest": inbox.get("review_digest", {}),
        "review_queue": inbox.get("review_queue", []),
        "next_action": inbox.get("next_action", ""),
    }


def graph_edges_for_entry(db: VaultDB, knowledge_id: int) -> dict[str, Any]:
    edges = db.get_edges(node_id=knowledge_id)
    shaped = []
    for edge in edges[:20]:
        other_id = edge.get("target_id") if edge.get("source_id") == knowledge_id else edge.get("source_id")
        other = db.get_knowledge(int(other_id)) if other_id else None
        shaped.append(
            {
                "relation": edge.get("relation", ""),
                "weight": edge.get("weight", 0),
                "auto_inferred": bool(edge.get("auto_inferred")),
                "other_id": other_id,
                "other_title": (other or {}).get("title", ""),
            }
        )
    return {"edge_count": len(edges), "edges": shaped}


def timeline_for(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "valid_from": row.get("valid_from", ""),
        "valid_until": row.get("valid_until", ""),
        "expires_at": row.get("expires_at", ""),
        "supersedes_id": row.get("supersedes_id"),
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
    }


def governance_for(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": row.get("scope", "project"),
        "sensitivity": row.get("sensitivity", "low"),
        "owner_agent": row.get("owner_agent", ""),
        "allowed_agents": row.get("allowed_agents", ""),
        "memory_type": row.get("memory_type", ""),
        "trust": row.get("trust", 0),
    }


def usage_for(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "usage_count": row.get("usage_count", 0),
        "last_accessed_at": row.get("last_accessed_at", ""),
        "source": row.get("source", ""),
        "status": row.get("status", "active"),
    }


def parse_json(raw: str) -> Any:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"raw": raw}


def confirmation_token(candidate_id: str, action: str) -> str:
    return f"{candidate_id}:{action}"


def _str_arg(query: dict[str, list[str]], name: str, default: str) -> str:
    values = query.get(name)
    return values[0] if values else default


def _int_arg(query: dict[str, list[str]], name: str, default: int) -> int:
    try:
        return int(_str_arg(query, name, str(default)))
    except (TypeError, ValueError):
        return default


def _path_int(path: str, prefix: str) -> int:
    try:
        return int(path[len(prefix) :].strip("/"))
    except (TypeError, ValueError):
        return 0


def _path_str(path: str, prefix: str) -> str:
    return path[len(prefix) :].strip("/")
