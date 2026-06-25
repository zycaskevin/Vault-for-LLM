#!/usr/bin/env python3
"""Remote MCP helpers for Supabase-backed Vault readers.

This module keeps remote search/map/read/doctor logic out of the main MCP
tool router while preserving the public ``vault_remote_*`` tool behavior.
"""

from __future__ import annotations

import hashlib
import os
import re

MCP_SEARCH_MAX_LIMIT = 50

REMOTE_NODE_TABLE = "vault_knowledge_nodes"
REMOTE_CLAIM_TABLE = "vault_knowledge_claims"
REMOTE_KNOWLEDGE_TABLE = "vault_knowledge"
REMOTE_ID_ERROR = "knowledge_id must be a positive integer or UUID"
REMOTE_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _clamp_int(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _line_hash(lines: list[str], line_start: int, line_end: int) -> str:
    text = "\n".join(lines[line_start - 1 : line_end])
    return hashlib.sha256(text.encode()).hexdigest()


def _format_citation(knowledge_id: int | str, title: str, line_start: int, line_end: int) -> str:
    return f"#{knowledge_id} {title} L{line_start}-L{line_end}"


def _compact_node(node: dict) -> dict:
    return {
        "node_uid": node.get("node_uid", ""),
        "path": node.get("path", ""),
        "heading": node.get("heading", ""),
        "line_start": node.get("line_start"),
        "line_end": node.get("line_end"),
    }

def _preferred_read_node(nodes: list[dict]) -> dict | None:
    if not nodes:
        return None
    for node in nodes:
        if int(node.get("level") or 0) > 1:
            return node
    return nodes[0]


def _get_supabase_client():
    """Create a Supabase client lazily; tests inject fake clients into helpers."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None
    from supabase import create_client

    return create_client(url, key)


def _remote_next_action_for_error(code: str, extra: dict | None = None) -> dict:
    extra = extra or {}
    knowledge_id = extra.get("knowledge_id") or extra.get("entry_id")
    if code in {
        "invalid_knowledge_id",
        "not_found",
        "access_denied",
        "remote_client_missing",
        "remote_read_failed",
        "remote_policy_missing",
    }:
        return {"tool": "vault_search", "arguments": {}}
    if code in {
        "invalid_range",
        "node_not_found",
        "range_outside_node",
        "range_outside_content",
        "source_content_unavailable",
        "no_document_map_nodes",
    }:
        return {
            "tool": "vault_remote_map_show",
            "arguments": {"knowledge_id": knowledge_id} if knowledge_id else {},
        }
    if code == "range_too_large":
        return {
            "tool": "vault_remote_read_range",
            "arguments": {"knowledge_id": knowledge_id} if knowledge_id else {},
        }
    return {"tool": "vault_search", "arguments": {}}


def _remote_error(code: str, message: str, **extra) -> dict:
    next_action = extra.pop("next_action", None)
    failure_mode = extra.pop("failure_mode", code)
    payload = {
        "error": code,
        "message": message,
        "failure_mode": failure_mode,
        "next_action": next_action or _remote_next_action_for_error(code, extra),
    }
    payload.update(extra)
    return payload


def _remote_read_range_action(
    knowledge_id: int | str,
    node: dict,
    *,
    agent_id: str = "",
    include_private: bool = False,
    max_sensitivity: str = "medium",
) -> dict:
    args = {"knowledge_id": knowledge_id}
    if node.get("node_uid"):
        args["node_uid"] = node["node_uid"]
    if node.get("line_start") and node.get("line_end"):
        args["line_start"] = int(node["line_start"])
        args["line_end"] = int(node["line_end"])
    if agent_id:
        args["agent_id"] = agent_id
    if include_private:
        args["include_private"] = True
    if max_sensitivity:
        args["max_sensitivity"] = max_sensitivity
    return {"tool": "vault_remote_read_range", "arguments": args}


def _supabase_rows(sb_client, table_name: str, columns: str = "*", filters: dict | None = None) -> list[dict]:
    query = sb_client.table(table_name).select(columns)
    for field, value in (filters or {}).items():
        query = query.eq(field, value)
    response = query.execute()
    return [dict(row) for row in (getattr(response, "data", None) or [])]


def _supabase_rpc(sb_client, function_name: str, params: dict) -> list[dict]:
    response = sb_client.rpc(function_name, params).execute()
    return [dict(row) for row in (getattr(response, "data", None) or [])]


def _remote_policy_params(
    *,
    agent_id: str = "",
    include_private: bool = False,
    max_sensitivity: str = "medium",
) -> dict:
    return {
        "p_agent_id": str(agent_id or ""),
        "p_include_private": bool(include_private),
        "p_max_sensitivity": str(max_sensitivity or "medium"),
    }


def _remote_policy_args(
    *,
    agent_id: str = "",
    include_private: bool = False,
    max_sensitivity: str = "medium",
) -> dict:
    args = {}
    if agent_id:
        args["agent_id"] = str(agent_id)
    if include_private:
        args["include_private"] = True
    if max_sensitivity:
        args["max_sensitivity"] = str(max_sensitivity)
    return args


def _normalize_remote_knowledge_id(knowledge_id: int | str) -> int | str | None:
    if isinstance(knowledge_id, int):
        return knowledge_id if knowledge_id > 0 else None
    text = str(knowledge_id or "").strip()
    if text.isdigit():
        normalized = int(text)
        return normalized if normalized > 0 else None
    if REMOTE_UUID_RE.match(text):
        return text.lower()
    return None


def _remote_readable_entry(
    sb_client,
    knowledge_id: int | str,
    *,
    agent_id: str = "",
    include_private: bool = False,
    max_sensitivity: str = "medium",
) -> dict | None:
    params = {
        **_remote_policy_params(
            agent_id=agent_id,
            include_private=include_private,
            max_sensitivity=max_sensitivity,
        ),
        "p_knowledge_id": knowledge_id,
    }
    rows = _supabase_rpc(sb_client, "vault_get_readable", params)
    return rows[0] if rows else None


def _remote_search_result(
    row: dict,
    *,
    compact: bool = True,
    agent_id: str = "",
    include_private: bool = False,
    max_sensitivity: str = "medium",
) -> dict:
    knowledge_id = row.get("id")
    policy_args = _remote_policy_args(
        agent_id=agent_id,
        include_private=include_private,
        max_sensitivity=max_sensitivity,
    )
    item = {
        "id": knowledge_id,
        "title": row.get("title"),
        "category": row.get("category"),
        "layer": row.get("layer"),
        "trust": row.get("trust"),
        "tags": row.get("tags"),
        "summary": row.get("summary"),
        "source": row.get("source"),
        "scope": row.get("scope"),
        "sensitivity": row.get("sensitivity"),
        "owner_agent": row.get("owner_agent"),
        "allowed_agents": row.get("allowed_agents"),
        "memory_type": row.get("memory_type"),
        "expires_at": row.get("expires_at"),
        "updated_at": row.get("updated_at"),
        "recommended_next_tool": "vault_remote_map_show",
    }
    if knowledge_id is not None:
        item["next_action"] = {
            "tool": "vault_remote_map_show",
            "arguments": {"knowledge_id": knowledge_id, "compact": True, **policy_args},
        }
    if compact:
        keep = {
            "id",
            "title",
            "summary",
            "source",
            "scope",
            "sensitivity",
            "memory_type",
            "recommended_next_tool",
            "next_action",
        }
        item = {key: value for key, value in item.items() if key in keep}
    return {key: value for key, value in item.items() if value is not None}


def _vault_remote_search_payload(
    query: str = "",
    *,
    agent_id: str = "",
    include_private: bool = False,
    max_sensitivity: str = "medium",
    limit: int = 10,
    compact: bool = True,
    sb_client=None,
) -> dict:
    limit = _clamp_int(limit, default=10, minimum=1, maximum=MCP_SEARCH_MAX_LIMIT)
    sb_client = sb_client or _get_supabase_client()
    if sb_client is None:
        return _remote_error(
            "remote_client_missing",
            "SUPABASE_URL and SUPABASE_ANON_KEY/SUPABASE_KEY are required for remote search.",
        )

    params = {
        "p_agent_id": str(agent_id or ""),
        "p_query": str(query or ""),
        "p_include_private": bool(include_private),
        "p_max_sensitivity": str(max_sensitivity or "medium"),
        "p_limit": limit,
    }
    try:
        rows = _supabase_rpc(sb_client, "vault_search_readable", params)
    except Exception as exc:
        return _remote_error(
            "remote_read_failed",
            "Unable to call Supabase RPC vault_search_readable. Apply docs/supabase_read_policy.sql first, then retry.",
        )

    return {
        "source": "supabase",
        "rpc": "vault_search_readable",
        "query": str(query or ""),
        "count": len(rows),
        "results": [
            _remote_search_result(
                row,
                compact=compact,
                agent_id=agent_id,
                include_private=include_private,
                max_sensitivity=max_sensitivity,
            )
            for row in rows
        ],
    }


def _remote_doctor_mark(payload: dict, name: str, status: str, detail: str = "") -> None:
    payload.setdefault("checks", {})[name] = status
    if detail:
        payload.setdefault("details", {})[name] = detail


def _remote_doctor_safe_detail(exc: Exception) -> str:
    detail = str(exc or "")
    try:
        from vault.privacy import redact_secrets

        detail = redact_secrets(detail)
    except Exception:
        detail = re.sub(r"(?i)(token|key|secret|password)=([^\s&]+)", r"\1=[REDACTED]", detail)
    detail = re.sub(r"https://[^\s]+\.supabase\.co", "https://[SUPABASE_PROJECT].supabase.co", detail)
    return detail[:300]


def _remote_doctor_fail(
    payload: dict,
    *,
    failure_mode: str,
    next_action: str,
    check: str = "",
    detail: str = "",
) -> dict:
    if check:
        _remote_doctor_mark(payload, check, "fail", detail)
    payload["ok"] = False
    payload["failure_mode"] = failure_mode
    payload["next_action"] = next_action
    return payload


def _remote_doctor_rpc(
    sb_client,
    function_name: str,
    params: dict,
) -> tuple[bool, list[dict], str]:
    try:
        rows = _supabase_rpc(sb_client, function_name, params)
        return True, rows, ""
    except Exception as exc:
        return False, [], _remote_doctor_safe_detail(exc)


def _vault_remote_doctor_payload(
    query: str = "",
    *,
    agent_id: str = "",
    include_private: bool = False,
    max_sensitivity: str = "medium",
    limit: int = 3,
    sb_client=None,
) -> dict:
    """Diagnose the complete Supabase remote reader path without exposing content."""
    limit = _clamp_int(limit, default=3, minimum=1, maximum=MCP_SEARCH_MAX_LIMIT)
    payload: dict = {
        "source": "supabase",
        "check": "remote_doctor",
        "ok": False,
        "query": str(query or ""),
        "agent_id": str(agent_id or ""),
        "checks": {},
        "counts": {},
    }

    sb_client = sb_client or _get_supabase_client()
    if sb_client is None:
        return _remote_doctor_fail(
            payload,
            failure_mode="remote_client_missing",
            next_action="Set SUPABASE_URL and SUPABASE_ANON_KEY/SUPABASE_KEY, then retry.",
            check="remote_client",
            detail="Supabase client could not be created.",
        )
    _remote_doctor_mark(payload, "remote_client", "pass")

    search = _vault_remote_search_payload(
        query,
        agent_id=agent_id,
        include_private=include_private,
        max_sensitivity=max_sensitivity,
        limit=limit,
        compact=True,
        sb_client=sb_client,
    )
    payload["counts"]["search_results"] = int(search.get("count") or 0)
    if search.get("error"):
        return _remote_doctor_fail(
            payload,
            failure_mode="remote_search_failed",
            next_action="Apply docs/supabase_read_policy.sql and verify vault_search_readable is granted to anon/authenticated.",
            check="remote_search",
            detail=str(search.get("message") or search.get("error") or ""),
        )
    _remote_doctor_mark(payload, "remote_search", "pass")

    results = search.get("results") or []
    if not results:
        return _remote_doctor_fail(
            payload,
            failure_mode="no_search_results",
            next_action="Try a broader --query or verify the agent policy can read at least one memory.",
            check="sample_result",
            detail="vault_search_readable returned zero rows.",
        )

    sample = results[0]
    remote_id = sample.get("id")
    normalized_id = _normalize_remote_knowledge_id(remote_id)
    if normalized_id is None:
        return _remote_doctor_fail(
            payload,
            failure_mode="invalid_remote_id",
            next_action="Upgrade to v0.6.61+ and ensure vault_search_readable returns an integer ID or UUID text.",
            check="sample_id",
            detail="Search returned an ID that remote map/read cannot use.",
        )
    remote_id = normalized_id
    id_type = "uuid" if isinstance(remote_id, str) and REMOTE_UUID_RE.match(remote_id) else "integer"
    payload["sample"] = {
        "id_type": id_type,
        "id_preview": f"{str(remote_id)[:8]}..." if isinstance(remote_id, str) else remote_id,
        "title": sample.get("title"),
    }
    _remote_doctor_mark(payload, "sample_id", "pass")
    _remote_doctor_mark(payload, "uuid_id" if id_type == "uuid" else "integer_id", "pass")

    policy_params = _remote_policy_params(
        agent_id=agent_id,
        include_private=include_private,
        max_sensitivity=max_sensitivity,
    )
    id_params = {**policy_params, "p_knowledge_id": remote_id}

    rpc_checks = [
        ("remote_get", "vault_get_readable", "missing_get_rpc"),
        ("remote_nodes_rpc", "vault_nodes_readable", "missing_nodes_rpc"),
        ("remote_claims_rpc", "vault_claims_readable", "missing_claims_rpc"),
        ("remote_content_rpc", "vault_content_readable", "missing_content_rpc"),
    ]
    rpc_rows: dict[str, list[dict]] = {}
    for check_name, function_name, failure_mode in rpc_checks:
        ok, rows, detail = _remote_doctor_rpc(sb_client, function_name, id_params)
        if not ok:
            return _remote_doctor_fail(
                payload,
                failure_mode=failure_mode,
                next_action="Reapply docs/supabase_read_policy.sql, then run `notify pgrst, 'reload schema';`.",
                check=check_name,
                detail=detail,
            )
        _remote_doctor_mark(payload, check_name, "pass")
        rpc_rows[function_name] = rows

    payload["counts"]["get_rows"] = len(rpc_rows["vault_get_readable"])
    payload["counts"]["nodes_for_sample"] = len(rpc_rows["vault_nodes_readable"])
    payload["counts"]["claims_for_sample"] = len(rpc_rows["vault_claims_readable"])
    payload["counts"]["content_rows"] = len(rpc_rows["vault_content_readable"])

    if not rpc_rows["vault_get_readable"]:
        return _remote_doctor_fail(
            payload,
            failure_mode="sample_not_readable",
            next_action="Check scope/sensitivity/owner_agent/allowed_agents for the sample memory.",
            check="remote_get_result",
            detail="vault_get_readable returned zero rows for the search result.",
        )
    _remote_doctor_mark(payload, "remote_get_result", "pass")

    if not rpc_rows["vault_nodes_readable"]:
        return _remote_doctor_fail(
            payload,
            failure_mode="missing_document_map_rows",
            next_action="Run Document Map sync/backfill so vault_knowledge_nodes has rows for remote map/read.",
            check="document_map_nodes",
            detail="vault_nodes_readable returned zero rows for the search result.",
        )
    _remote_doctor_mark(payload, "document_map_nodes", "pass")

    if not rpc_rows["vault_claims_readable"]:
        _remote_doctor_mark(
            payload,
            "document_map_claims",
            "warn",
            "vault_claims_readable returned zero rows for the sample; content_raw reads may still work.",
        )
    else:
        _remote_doctor_mark(payload, "document_map_claims", "pass")

    map_payload = _vault_remote_map_show_payload(
        remote_id,
        compact=True,
        agent_id=agent_id,
        include_private=include_private,
        max_sensitivity=max_sensitivity,
        sb_client=sb_client,
    )
    if map_payload.get("error"):
        return _remote_doctor_fail(
            payload,
            failure_mode=str(map_payload.get("failure_mode") or map_payload.get("error")),
            next_action="Check remote map/read RPC grants and Document Map sync state.",
            check="remote_map",
            detail=str(map_payload.get("message") or map_payload.get("error") or ""),
        )
    _remote_doctor_mark(payload, "remote_map", "pass")
    payload["counts"]["map_nodes"] = len(map_payload.get("nodes") or [])

    action_args = (map_payload.get("next_action") or {}).get("arguments") or {}
    if action_args:
        read_payload = _vault_remote_read_range_payload(
            action_args.get("knowledge_id", remote_id),
            node_uid=action_args.get("node_uid", ""),
            line_start=action_args.get("line_start", 0),
            line_end=action_args.get("line_end", 0),
            agent_id=agent_id,
            include_private=include_private,
            max_sensitivity=max_sensitivity,
            sb_client=sb_client,
        )
        if read_payload.get("error"):
            return _remote_doctor_fail(
                payload,
                failure_mode=str(read_payload.get("failure_mode") or read_payload.get("error")),
                next_action="Check vault_content_readable, vault_claims_readable, and synced line ranges.",
                check="remote_read",
                detail=str(read_payload.get("message") or read_payload.get("error") or ""),
            )
        _remote_doctor_mark(payload, "remote_read", "pass")
        payload["read"] = {
            "source": read_payload.get("source"),
            "range": read_payload.get("range"),
            "has_content": bool(read_payload.get("content")),
            "citation_preview": str(read_payload.get("citation") or "")[:120],
        }
    else:
        _remote_doctor_mark(payload, "remote_read", "warn", "remote map did not return a read next_action.")

    payload["ok"] = True
    payload["next_action"] = None
    return payload


def _sort_remote_nodes(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda row: (
            int(row.get("line_start") or 0),
            int(row.get("level") or 0),
            str(row.get("node_uid") or ""),
        ),
    )


def _sort_remote_claims(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda row: (
            int(row.get("line_start") or 0),
            int(row.get("line_end") or 0),
            str(row.get("claim_uid") or ""),
        ),
    )


def _remote_node_payload(row: dict) -> dict:
    keys = [
        "node_uid",
        "path",
        "heading",
        "level",
        "line_start",
        "line_end",
        "summary",
        "token_estimate",
    ]
    return {key: row.get(key) for key in keys if key in row}


def vault_remote_map_show(
    knowledge_id: int | str,
    compact: bool = False,
    agent_id: str = "",
    include_private: bool = False,
    max_sensitivity: str = "medium",
) -> dict:
    """Return a synced Supabase Document Map structure (read-only target)."""
    return _vault_remote_map_show_payload(
        knowledge_id,
        compact=compact,
        agent_id=agent_id,
        include_private=include_private,
        max_sensitivity=max_sensitivity,
    )


def _vault_remote_map_show_payload(
    knowledge_id: int | str,
    *,
    compact: bool = False,
    agent_id: str = "",
    include_private: bool = False,
    max_sensitivity: str = "medium",
    sb_client=None,
) -> dict:
    normalized_id = _normalize_remote_knowledge_id(knowledge_id)
    if normalized_id is None:
        return _remote_error("invalid_knowledge_id", REMOTE_ID_ERROR)
    knowledge_id = normalized_id

    sb_client = sb_client or _get_supabase_client()
    if sb_client is None:
        return _remote_error(
            "remote_client_missing",
            "SUPABASE_URL and SUPABASE_ANON_KEY/SUPABASE_KEY are required for remote map reads.",
            knowledge_id=knowledge_id,
        )

    try:
        entry = _remote_readable_entry(
            sb_client,
            knowledge_id,
            agent_id=agent_id,
            include_private=include_private,
            max_sensitivity=max_sensitivity,
        )
    except Exception:
        return _remote_error(
            "remote_policy_missing",
            "Remote Document Map reads require the guarded Supabase RPCs from docs/supabase_read_policy.sql.",
            knowledge_id=knowledge_id,
        )
    if not entry:
        return _remote_error(
            "not_found",
            "Remote knowledge id was not found or is not readable under the provided agent policy.",
            knowledge_id=knowledge_id,
        )

    policy_params = _remote_policy_params(
        agent_id=agent_id,
        include_private=include_private,
        max_sensitivity=max_sensitivity,
    )
    try:
        rows = _sort_remote_nodes(
            _supabase_rpc(
                sb_client,
                "vault_nodes_readable",
                {**policy_params, "p_knowledge_id": knowledge_id},
            )
        )
    except Exception:
        return _remote_error(
            "remote_read_failed",
            "Unable to read remote Document Map nodes through the guarded Supabase RPC.",
            knowledge_id=knowledge_id,
        )

    title = str(entry.get("title") or "")
    output_nodes = [_compact_node(row) for row in rows] if compact else [_remote_node_payload(row) for row in rows]
    payload = {
        "entry_id": knowledge_id,
        "title": title,
        "source": "supabase",
        "nodes": output_nodes,
    }
    if rows:
        preferred_node = _preferred_read_node(rows)
        if preferred_node is not None:
            payload["next_action"] = _remote_read_range_action(
                knowledge_id,
                preferred_node,
                agent_id=agent_id,
                include_private=include_private,
                max_sensitivity=max_sensitivity,
            )
        payload["next_actions"] = [
            _remote_read_range_action(
                knowledge_id,
                node,
                agent_id=agent_id,
                include_private=include_private,
                max_sensitivity=max_sensitivity,
            )
            for node in rows
        ]
        return payload

    payload.update(
        _remote_error(
            "no_document_map_nodes",
            "No remote Document Map nodes found. Sync local SQLite with scripts/sync_to_supabase.py --document-map after applying the Supabase DDL.",
            knowledge_id=knowledge_id,
        )
    )
    return payload


def vault_remote_read_range(
    knowledge_id: int | str,
    node_uid: str = "",
    line_start: int = 0,
    line_end: int = 0,
    agent_id: str = "",
    include_private: bool = False,
    max_sensitivity: str = "medium",
) -> dict:
    """Return a bounded remote source/claim range with a fixed citation."""
    return _vault_remote_read_range_payload(
        knowledge_id,
        node_uid=node_uid,
        line_start=line_start,
        line_end=line_end,
        agent_id=agent_id,
        include_private=include_private,
        max_sensitivity=max_sensitivity,
    )


def _find_remote_content_row(
    sb_client,
    knowledge_id: int | str,
    *,
    agent_id: str = "",
    include_private: bool = False,
    max_sensitivity: str = "medium",
) -> dict | None:
    params = {
        **_remote_policy_params(
            agent_id=agent_id,
            include_private=include_private,
            max_sensitivity=max_sensitivity,
        ),
        "p_knowledge_id": knowledge_id,
    }
    rows = _supabase_rpc(sb_client, "vault_content_readable", params)
    return rows[0] if rows else None


def _remote_claim_content(claims: list[dict]) -> str:
    lines = []
    for claim in claims:
        start = int(claim.get("line_start") or 0)
        end = int(claim.get("line_end") or start)
        prefix = f"{start}|" if start == end else f"{start}-{end}|"
        lines.append(f"{prefix}{claim.get('claim') or ''}")
    return "\n".join(lines)


def _content_hash_for_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _vault_remote_read_range_payload(
    knowledge_id: int | str,
    node_uid: str = "",
    line_start: int = 0,
    line_end: int = 0,
    *,
    max_lines: int = 80,
    agent_id: str = "",
    include_private: bool = False,
    max_sensitivity: str = "medium",
    sb_client=None,
) -> dict:
    normalized_id = _normalize_remote_knowledge_id(knowledge_id)
    if normalized_id is None:
        return _remote_error("invalid_knowledge_id", REMOTE_ID_ERROR)
    knowledge_id = normalized_id

    try:
        max_lines = int(max_lines)
    except (TypeError, ValueError):
        max_lines = 80
    if max_lines <= 0:
        max_lines = 80

    sb_client = sb_client or _get_supabase_client()
    if sb_client is None:
        return _remote_error(
            "remote_client_missing",
            "SUPABASE_URL and SUPABASE_ANON_KEY/SUPABASE_KEY are required for remote range reads.",
            knowledge_id=knowledge_id,
        )

    try:
        entry = _remote_readable_entry(
            sb_client,
            knowledge_id,
            agent_id=agent_id,
            include_private=include_private,
            max_sensitivity=max_sensitivity,
        )
    except Exception:
        return _remote_error(
            "remote_policy_missing",
            "Remote range reads require the guarded Supabase RPCs from docs/supabase_read_policy.sql.",
            knowledge_id=knowledge_id,
        )
    if not entry:
        return _remote_error(
            "not_found",
            "Remote knowledge id was not found or is not readable under the provided agent policy.",
            knowledge_id=knowledge_id,
        )

    policy_params = _remote_policy_params(
        agent_id=agent_id,
        include_private=include_private,
        max_sensitivity=max_sensitivity,
    )
    try:
        nodes = _sort_remote_nodes(
            _supabase_rpc(
                sb_client,
                "vault_nodes_readable",
                {**policy_params, "p_knowledge_id": knowledge_id},
            )
        )
        claims = _sort_remote_claims(
            _supabase_rpc(
                sb_client,
                "vault_claims_readable",
                {**policy_params, "p_knowledge_id": knowledge_id},
            )
        )
    except Exception:
        return _remote_error(
            "remote_read_failed",
            "Unable to read remote Document Map rows through the guarded Supabase RPC.",
            knowledge_id=knowledge_id,
        )

    if not nodes and not claims:
        return _remote_error(
            "no_document_map_nodes",
            "No remote Document Map rows found for this knowledge_id.",
            knowledge_id=knowledge_id,
        )

    title = str(entry.get("title") or "")
    knowledge_content_hash = next(
        (
            str(row.get("knowledge_content_hash") or "")
            for row in [*nodes, *claims]
            if row.get("knowledge_content_hash")
        ),
        "",
    )

    node = None
    node_uid = (node_uid or "").strip()
    if node_uid:
        node = next((row for row in nodes if str(row.get("node_uid") or "") == node_uid), None)
        if node is None:
            return _remote_error(
                "node_not_found",
                f"Remote node not found: {node_uid}",
                knowledge_id=knowledge_id,
                node_uid=node_uid,
            )

    try:
        line_start = int(line_start or 0)
        line_end = int(line_end or 0)
    except (TypeError, ValueError):
        return _remote_error(
            "invalid_range",
            "line_start and line_end must be integers",
            knowledge_id=knowledge_id,
        )

    if node is not None and line_start == 0 and line_end == 0:
        line_start = int(node["line_start"])
        line_end = int(node["line_end"])
    elif line_start <= 0 or line_end <= 0:
        return _remote_error(
            "invalid_range",
            "Provide a positive line_start and line_end, or provide node_uid alone.",
            knowledge_id=knowledge_id,
        )

    if line_start <= 0 or line_end <= 0 or line_end < line_start:
        return _remote_error(
            "invalid_range",
            "Range must be a positive START-END span",
            knowledge_id=knowledge_id,
        )

    if node is not None and not (
        int(node["line_start"]) <= line_start <= line_end <= int(node["line_end"])
    ):
        return _remote_error(
            "range_outside_node",
            f"Requested L{line_start}-L{line_end} is outside remote node "
            f"{node_uid} L{node['line_start']}-L{node['line_end']}.",
            knowledge_id=knowledge_id,
            node_uid=node_uid,
            node_range=f"L{node['line_start']}-L{node['line_end']}",
        )

    line_count = line_end - line_start + 1
    if line_count > max_lines:
        return _remote_error(
            "range_too_large",
            f"Requested {line_count} lines exceeds max {max_lines}. Please split into smaller ranges.",
            knowledge_id=knowledge_id,
            max_lines=max_lines,
            requested_lines=line_count,
        )

    if node is None:
        node = next(
            (
                row for row in reversed(nodes)
                if int(row.get("line_start") or 0) <= line_start
                and line_end <= int(row.get("line_end") or 0)
            ),
            None,
        )

    content = ""
    content_hash = ""
    source = "remote_claims"
    try:
        content_row = _find_remote_content_row(
            sb_client,
            knowledge_id,
            agent_id=agent_id,
            include_private=include_private,
            max_sensitivity=max_sensitivity,
        )
    except Exception:
        content_row = None
    if content_row and content_row.get("content_raw"):
        lines = str(content_row.get("content_raw") or "").splitlines()
        total_lines = len(lines)
        if line_start > total_lines or line_end > total_lines:
            return _remote_error(
                "range_outside_content",
                f"Requested L{line_start}-L{line_end} exceeds remote content length L1-L{total_lines}",
                knowledge_id=knowledge_id,
                total_lines=total_lines,
            )
        content = "\n".join(
            f"{line_number}|{lines[line_number - 1]}"
            for line_number in range(line_start, line_end + 1)
        )
        content_hash = _line_hash(lines, line_start, line_end)
        source = "remote_content_raw"
    else:
        range_claims = [
            claim for claim in claims
            if int(claim.get("line_start") or 0) >= line_start
            and int(claim.get("line_end") or claim.get("line_start") or 0) <= line_end
        ]
        if not range_claims:
            return _remote_error(
                "source_content_unavailable",
                "Remote content_raw is unavailable and no synced claims cover the requested range.",
                knowledge_id=knowledge_id,
            )
        content = _remote_claim_content(range_claims)
        content_hash = _content_hash_for_text(content)

    exact_node_range = (
        node is not None
        and line_start == int(node.get("line_start") or 0)
        and line_end == int(node.get("line_end") or 0)
    )
    if source == "remote_content_raw" and exact_node_range and node and node.get("content_hash"):
        content_hash = str(node["content_hash"])

    citation = _format_citation(knowledge_id, title, line_start, line_end)
    return {
        "entry_id": knowledge_id,
        "title": title,
        "source": source,
        "range": f"L{line_start}-L{line_end}",
        "line_start": line_start,
        "line_end": line_end,
        "citation": citation,
        "content": content,
        "content_hash": content_hash,
        "node_uid": node.get("node_uid", "") if node is not None else "",
        "path": node.get("path", "") if node is not None else "",
        "next_action": {
            "tool": "final_answer",
            "citation": citation,
            "instruction": "Use this exact citation when relying on this remote range.",
        },
    }
