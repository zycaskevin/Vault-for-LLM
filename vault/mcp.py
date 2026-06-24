#!/usr/bin/env python3
"""Vault-for-LLM MCP server with public ``vault_*`` tool names."""

import argparse
import hashlib
import json
import sqlite3
import sys
import os
import re
from pathlib import Path

try:
    from . import __version__
except Exception:  # pragma: no cover - direct script fallback
    __version__ = "0.1.0"

# 確保模組路徑
VAULT_DIR = str(Path(__file__).parent.parent)
if VAULT_DIR not in sys.path:
    sys.path.insert(0, VAULT_DIR)

from vault.access_policy import can_read_memory, normalize_read_policy

DB_PATH = os.path.join(
    os.environ.get("VAULT_PATH") or VAULT_DIR,
    "vault.db",
)
REMOTE_NODE_TABLE = "vault_knowledge_nodes"
REMOTE_CLAIM_TABLE = "vault_knowledge_claims"
REMOTE_KNOWLEDGE_TABLE = "vault_knowledge"
MCP_SEARCH_MAX_LIMIT = 50
MCP_SEARCH_MAX_OFFSET = 1000
REMOTE_ID_ERROR = "knowledge_id must be a positive integer or UUID"
REMOTE_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
MCP_ALLOWED_SEARCH_FIELDS = {
    "id",
    "title",
    "category",
    "layer",
    "trust",
    "tags",
    "best_claim",
    "best_span",
    "best_node",
    "node_uid",
    "path",
    "heading",
    "line_start",
    "line_end",
    "citation",
    "recommended_next_tool",
    "next_action",
    "next_actions",
    "rerank_score",
    "_score",
    "_original_score",
    "_snippet",
    "content_preview",
}
MCP_MEMORY_CANDIDATE_MAX_LIMIT = 100


def _set_project_dir(project_dir: str | os.PathLike[str]) -> None:
    """Point the MCP server at a project's local SQLite vault."""
    global DB_PATH
    project_path = Path(project_dir).expanduser().absolute()
    DB_PATH = str(project_path / "vault.db")


def _canonical_tool_name(name: str) -> str:
    """Return the public Vault MCP tool name unchanged."""
    return name


def _get_db():
    """取得資料庫連線。"""
    from vault.db import VaultDB
    db = VaultDB(DB_PATH)
    db.connect()
    return db


def _get_search():
    """取得搜尋引擎。"""
    from vault.db import VaultDB
    from vault.search import VaultSearch
    from vault.embed import create_embedding_provider

    db = VaultDB(DB_PATH)
    db.connect()

    embed = None
    try:
        provider_name = db.get_config("embedding_provider", "auto")
        model_key = db.get_config("embedding_model", "mix")
        if provider_name != "none":
            embed = create_embedding_provider(provider=provider_name, model_key=model_key)
    except Exception:
        pass

    return db, VaultSearch(db, embed_provider=embed)


def _format_memory_candidate(row: dict, *, include_content: bool = False, include_gates: bool = False) -> dict:
    item = {
        "id": row.get("id"),
        "title": row.get("title"),
        "status": row.get("status"),
        "layer": row.get("layer"),
        "category": row.get("category"),
        "tags": row.get("tags"),
        "trust": row.get("trust"),
        "scope": row.get("scope"),
        "sensitivity": row.get("sensitivity"),
        "owner_agent": row.get("owner_agent"),
        "allowed_agents": row.get("allowed_agents"),
        "memory_type": row.get("memory_type"),
        "expires_at": row.get("expires_at"),
        "source": row.get("source"),
        "source_ref": row.get("source_ref"),
        "reason": row.get("reason"),
        "privacy_status": row.get("privacy_status"),
        "duplicate_status": row.get("duplicate_status"),
        "quality_status": row.get("quality_status"),
        "promoted_knowledge_id": row.get("promoted_knowledge_id"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }
    content = row.get("content") or ""
    item["content_length"] = len(content)
    if include_content:
        item["content"] = content
    elif content:
        item["content_preview"] = " ".join(content.split())[:180]
    if include_gates:
        raw_gates = row.get("gate_payload_json") or "{}"
        try:
            item["gates"] = json.loads(raw_gates)
        except json.JSONDecodeError:
            item["gates"] = {"raw": raw_gates}
    return item


def _get_supabase_client():
    """Create a Supabase client lazily; tests inject fake clients into helpers."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None
    from supabase import create_client

    return create_client(url, key)


def _clamp_int(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _resolve_mcp_transcript_path(value: str, *, allow_absolute_path: bool = False) -> Path:
    project_dir = Path(DB_PATH).resolve().parent
    raw = Path(str(value or "")).expanduser()
    if not str(value or "").strip():
        raise ValueError("transcript_path is required")
    if raw.is_absolute():
        if not allow_absolute_path:
            raise ValueError("absolute transcript paths require allow_absolute_path=true")
        path = raw.resolve()
    else:
        path = (project_dir / raw).resolve()
    if not path.exists() or not path.is_file():
        raise ValueError("transcript_path must point to an existing file")
    try:
        path.relative_to(project_dir)
    except ValueError:
        if not allow_absolute_path:
            raise ValueError("transcript_path must stay inside the project directory")
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("transcript_path is too large for MCP capture; use CLI for large exports")
    return path


def _search_field_set(fields) -> set[str] | None:
    if not isinstance(fields, list):
        return None
    return {str(field) for field in fields if str(field) in MCP_ALLOWED_SEARCH_FIELDS}


# ── Document Map helpers ───────────────────────────────

def _open_readonly_db(db_path: str | None = None) -> sqlite3.Connection | None:
    """Open the local Vault DB read-only without creating missing files."""
    path = Path(db_path or DB_PATH)
    if not path.exists():
        return None
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _line_hash(lines: list[str], line_start: int, line_end: int) -> str:
    text = "\n".join(lines[line_start - 1 : line_end])
    return hashlib.sha256(text.encode()).hexdigest()


def _format_citation(knowledge_id: int | str, title: str, line_start: int, line_end: int) -> str:
    return f"#{knowledge_id} {title} L{line_start}-L{line_end}"


def _next_action_for_error(code: str, extra: dict | None = None) -> dict:
    extra = extra or {}
    knowledge_id = extra.get("knowledge_id") or extra.get("entry_id")
    if code in {"invalid_knowledge_id", "not_found", "db_not_found", "db_open_failed"}:
        return {"tool": "vault_search", "arguments": {}}
    if code == "no_document_map_nodes":
        return {
            "tool": "vault_map_build",
            "arguments": {"knowledge_id": knowledge_id} if knowledge_id else {},
        }
    if code in {"invalid_range", "node_not_found", "range_outside_node", "range_outside_content"}:
        return {
            "tool": "vault_map_show",
            "arguments": {"knowledge_id": knowledge_id} if knowledge_id else {},
        }
    if code == "range_too_large":
        return {
            "tool": "vault_read_range",
            "arguments": {"knowledge_id": knowledge_id} if knowledge_id else {},
        }
    return {"tool": "vault_search", "arguments": {}}


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


def _error(code: str, message: str, **extra) -> dict:
    next_action = extra.pop("next_action", None)
    failure_mode = extra.pop("failure_mode", code)
    payload = {
        "error": code,
        "message": message,
        "failure_mode": failure_mode,
        "next_action": next_action or _next_action_for_error(code, extra),
    }
    payload.update(extra)
    return payload


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


def vault_map_show(knowledge_id: int, compact: bool = False) -> dict:
    """Return a knowledge entry's Document Map structure."""
    return _vault_map_show_payload(knowledge_id, compact=compact)


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


def _read_range_action(knowledge_id: int, node: dict) -> dict:
    args = {"knowledge_id": knowledge_id}
    if node.get("node_uid"):
        args["node_uid"] = node["node_uid"]
    if node.get("line_start") and node.get("line_end"):
        args["line_start"] = int(node["line_start"])
        args["line_end"] = int(node["line_end"])
    return {"tool": "vault_read_range", "arguments": args}


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


def _vault_map_show_payload(
    knowledge_id: int,
    db_path: str | None = None,
    compact: bool = False,
    agent_id: str = "",
    include_private: bool = False,
    max_sensitivity: str = "",
) -> dict:
    try:
        knowledge_id = int(knowledge_id)
    except (TypeError, ValueError):
        return _error("invalid_knowledge_id", "knowledge_id must be a positive integer")
    if knowledge_id <= 0:
        return _error("invalid_knowledge_id", "knowledge_id must be a positive integer")

    try:
        conn = _open_readonly_db(db_path)
    except sqlite3.Error as exc:
        return _error("db_open_failed", f"Unable to open vault.db read-only: {exc}")
    if conn is None:
        return _error("db_not_found", f"vault.db not found at {db_path or DB_PATH}")

    try:
        entry = conn.execute(
            "SELECT * FROM knowledge WHERE id=?",
            (knowledge_id,),
        ).fetchone()
        if entry is None:
            return _error("not_found", f"Knowledge id not found: {knowledge_id}")
        policy = normalize_read_policy(
            agent_id=agent_id,
            include_private=include_private,
            max_sensitivity=max_sensitivity,
        )
        if not can_read_memory(dict(entry), policy):
            return _error(
                "access_denied",
                "Knowledge id is not readable under the provided agent policy.",
                knowledge_id=knowledge_id,
            )

        rows = conn.execute(
            """SELECT node_uid, path, heading, level, line_start, line_end,
                      summary, token_estimate
               FROM knowledge_nodes
               WHERE knowledge_id=?
               ORDER BY line_start, level, id""",
            (knowledge_id,),
        ).fetchall()
        nodes = [dict(row) for row in rows]
        output_nodes = [_compact_node(node) for node in nodes] if compact else nodes
        payload = {
            "entry_id": knowledge_id,
            "title": entry["title"],
            "nodes": output_nodes,
        }
        if nodes:
            preferred_node = _preferred_read_node(nodes)
            if preferred_node is not None:
                payload["next_action"] = _read_range_action(knowledge_id, preferred_node)
            payload["next_actions"] = [
                _read_range_action(knowledge_id, node) for node in nodes
            ]
        if not nodes:
            payload.update(
                _error(
                    "no_document_map_nodes",
                    "No document map nodes found. Run: "
                    f"vault map build {knowledge_id}",
                    knowledge_id=knowledge_id,
                )
            )
        return payload
    finally:
        conn.close()


def vault_read_range(
    knowledge_id: int,
    node_uid: str = "",
    line_start: int = 0,
    line_end: int = 0,
) -> dict:
    """Return a bounded, line-numbered source range with a fixed citation."""
    return _vault_read_range_payload(
        knowledge_id,
        node_uid=node_uid,
        line_start=line_start,
        line_end=line_end,
    )


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


def _vault_read_range_payload(
    knowledge_id: int,
    node_uid: str = "",
    line_start: int = 0,
    line_end: int = 0,
    *,
    max_lines: int = 80,
    agent_id: str = "",
    include_private: bool = False,
    max_sensitivity: str = "",
    db_path: str | None = None,
) -> dict:
    try:
        knowledge_id = int(knowledge_id)
    except (TypeError, ValueError):
        return _error("invalid_knowledge_id", "knowledge_id must be a positive integer")
    if knowledge_id <= 0:
        return _error("invalid_knowledge_id", "knowledge_id must be a positive integer")

    try:
        max_lines = int(max_lines)
    except (TypeError, ValueError):
        max_lines = 80
    if max_lines <= 0:
        max_lines = 80

    try:
        conn = _open_readonly_db(db_path)
    except sqlite3.Error as exc:
        return _error("db_open_failed", f"Unable to open vault.db read-only: {exc}")
    if conn is None:
        return _error("db_not_found", f"vault.db not found at {db_path or DB_PATH}")

    try:
        entry = conn.execute(
            "SELECT * FROM knowledge WHERE id=?",
            (knowledge_id,),
        ).fetchone()
        if entry is None:
            return _error("not_found", f"Knowledge id not found: {knowledge_id}")
        policy = normalize_read_policy(
            agent_id=agent_id,
            include_private=include_private,
            max_sensitivity=max_sensitivity,
        )
        if not can_read_memory(dict(entry), policy):
            return _error(
                "access_denied",
                "Knowledge id is not readable under the provided agent policy.",
                knowledge_id=knowledge_id,
            )

        node = None
        node_uid = (node_uid or "").strip()
        if node_uid:
            node = conn.execute(
                """SELECT node_uid, path, heading, line_start, line_end, content_hash
                   FROM knowledge_nodes
                   WHERE knowledge_id=? AND node_uid=?""",
                (knowledge_id, node_uid),
            ).fetchone()
            if node is None:
                return _error("node_not_found", f"Node not found: {node_uid}")

        try:
            line_start = int(line_start or 0)
            line_end = int(line_end or 0)
        except (TypeError, ValueError):
            return _error("invalid_range", "line_start and line_end must be integers")

        if node is not None and line_start == 0 and line_end == 0:
            line_start = int(node["line_start"])
            line_end = int(node["line_end"])
        elif line_start <= 0 or line_end <= 0:
            return _error(
                "invalid_range",
                "Provide a positive line_start and line_end, or provide node_uid alone.",
            )

        if line_start <= 0 or line_end <= 0 or line_end < line_start:
            return _error("invalid_range", "Range must be a positive START-END span")

        if node is not None and not (
            int(node["line_start"]) <= line_start <= line_end <= int(node["line_end"])
        ):
            return _error(
                "range_outside_node",
                f"Requested L{line_start}-L{line_end} is outside node "
                f"{node_uid} L{node['line_start']}-L{node['line_end']}.",
                node_uid=node_uid,
                node_range=f"L{node['line_start']}-L{node['line_end']}",
            )

        line_count = line_end - line_start + 1
        if line_count > max_lines:
            return _error(
                "range_too_large",
                f"Requested {line_count} lines exceeds max {max_lines}. "
                "Please split into smaller ranges.",
                max_lines=max_lines,
                requested_lines=line_count,
            )

        lines = (entry["content_raw"] or "").splitlines()
        total_lines = len(lines)
        if total_lines == 0:
            return _error("empty_content", "Knowledge entry has no content_raw lines")
        if line_start > total_lines or line_end > total_lines:
            return _error(
                "range_outside_content",
                f"Requested L{line_start}-L{line_end} exceeds content length L1-L{total_lines}",
                total_lines=total_lines,
            )

        if node is None:
            node = conn.execute(
                """SELECT node_uid, path, heading, line_start, line_end, content_hash
                   FROM knowledge_nodes
                   WHERE knowledge_id=? AND line_start <= ? AND line_end >= ?
                   ORDER BY level DESC, (line_end - line_start) ASC, id
                   LIMIT 1""",
                (knowledge_id, line_start, line_end),
            ).fetchone()

        content = "\n".join(
            f"{line_number}|{lines[line_number - 1]}"
            for line_number in range(line_start, line_end + 1)
        )
        exact_node_range = (
            node is not None
            and line_start == int(node["line_start"])
            and line_end == int(node["line_end"])
        )
        content_hash = (
            node["content_hash"]
            if exact_node_range and node["content_hash"]
            else _line_hash(lines, line_start, line_end)
        )

        citation = _format_citation(knowledge_id, entry["title"], line_start, line_end)
        return {
            "entry_id": knowledge_id,
            "title": entry["title"],
            "range": f"L{line_start}-L{line_end}",
            "line_start": line_start,
            "line_end": line_end,
            "citation": citation,
            "content": content,
            "content_hash": content_hash,
            "node_uid": node["node_uid"] if node is not None else "",
            "path": node["path"] if node is not None else "",
            "next_action": {
                "tool": "final_answer",
                "citation": citation,
                "instruction": "Use this exact citation when relying on this range.",
            },
        }
    finally:
        conn.close()


# ── MCP Server Implementation ──────────────────────────

TOOLS = [
    {
        "name": "vault_search",
        "description": "搜尋 Vault 百科知識庫。支援關鍵字、向量、混合搜尋。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜尋查詢（中英文皆可）"
                },
                "mode": {
                    "type": "string",
                    "enum": ["auto", "keyword", "vector", "semantic", "hybrid"],
                    "description": "搜尋模式（預設 auto）",
                    "default": "auto"
                },
                "limit": {
                    "type": "integer",
                    "description": "最多回傳幾筆（預設 10）",
                    "default": 10,
                    "minimum": 1,
                    "maximum": MCP_SEARCH_MAX_LIMIT
                },
                "offset": {
                    "type": "integer",
                    "description": "跳過前 N 筆（分頁用，預設 0）",
                    "default": 0,
                    "minimum": 0,
                    "maximum": MCP_SEARCH_MAX_OFFSET
                },
                "normalize_scores": {
                    "type": "boolean",
                    "description": "是否對分數進行標準化（預設 false）",
                    "default": False
                },
                "include_snippet": {
                    "type": "boolean",
                    "description": "是否在結果中包含內容片段（預設 false）",
                    "default": False
                },
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "指定回傳欄位（如 ['id', 'title', 'best_claim']），預設全欄位"
                },
                "compact": {
                    "type": "boolean",
                    "description": "回傳精簡 payload（MCP 預設 true；設為 false 可取得含 content_preview 的完整輸出）",
                    "default": True
                },
                "agent_id": {
                    "type": "string",
                    "description": "可選 Agent 身份；提供後套用 scope/sensitivity/allowed_agents 讀取過濾",
                    "default": ""
                },
                "include_private": {
                    "type": "boolean",
                    "description": "搭配 agent_id 使用；允許讀取 owner/allow-list 授權的 private 記憶",
                    "default": False
                },
                "max_sensitivity": {
                    "type": "string",
                    "enum": ["", "low", "medium", "high", "restricted"],
                    "description": "可選最高敏感度；例如 medium 會排除 high/restricted",
                    "default": ""
                },
            },
            "required": ["query"]
        }
    },
    {
        "name": "vault_add",
        "description": "Direct low-level add to active Vault knowledge. Prefer vault_memory_propose for autonomous agents and unreviewed memories.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "知識標題"
                },
                "content": {
                    "type": "string",
                    "description": "知識內容（Markdown 格式）"
                },
                "category": {
                    "type": "string",
                    "description": "分類（error/technique/architecture/concept/decision/general）",
                    "default": "general"
                },
                "tags": {
                    "type": "string",
                    "description": "標籤（逗號分隔，如 'sqlite,踩坑,擴展'）",
                    "default": ""
                },
                "trust": {
                    "type": "number",
                    "description": "信任分數（0.0-1.0，session 提取建議 0.4，手動驗證 0.8+）",
                    "default": 0.5
                },
                "layer": {
                    "type": "string",
                    "description": "知識層級（L0-L3）",
                    "default": "L3"
                },
                "scope": {"type": "string", "enum": ["private", "project", "shared", "public"], "default": "project"},
                "sensitivity": {"type": "string", "enum": ["low", "medium", "high", "restricted"], "default": "low"},
                "owner_agent": {"type": "string", "default": ""},
                "allowed_agents": {"type": "array", "items": {"type": "string"}, "default": []},
                "memory_type": {"type": "string", "default": "knowledge"},
                "expires_at": {"type": "string", "default": ""},
            },
            "required": ["title", "content"]
        }
    },
    {
        "name": "vault_memory_propose",
        "description": "Propose a possible memory through deterministic gates. Candidate-first; use this instead of vault_add for autonomous agents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "source": {"type": "string", "default": "mcp"},
                "source_ref": {"type": "string", "default": ""},
                "layer": {"type": "string", "enum": ["L0", "L1", "L2", "L3"], "default": "L3"},
                "category": {"type": "string", "default": "general"},
                "tags": {"type": "string", "default": ""},
                "trust": {"type": "number", "default": 0.5},
                "scope": {"type": "string", "enum": ["private", "project", "shared", "public"], "default": "project"},
                "sensitivity": {"type": "string", "enum": ["low", "medium", "high", "restricted"], "default": "low"},
                "owner_agent": {"type": "string", "default": ""},
                "allowed_agents": {"type": "array", "items": {"type": "string"}, "default": []},
                "memory_type": {"type": "string", "default": "knowledge"},
                "expires_at": {"type": "string", "default": ""},
                "reason": {"type": "string", "description": "Why this is worth remembering"},
                "mode": {"type": "string", "enum": ["candidate", "promote_if_safe"], "default": "candidate"},
            },
            "required": ["title", "content", "reason"]
        }
    },
    {
        "name": "vault_memory_promote",
        "description": "Promote a reviewed memory candidate into raw/ plus active SQLite knowledge. Requires confirm=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "string"},
                "confirm": {"type": "boolean", "default": True},
                "compile": {"type": "boolean", "default": True},
                "build_map": {"type": "boolean", "default": True},
            },
            "required": ["candidate_id", "confirm"]
        }
    },
    {
        "name": "vault_memory_review",
        "description": "Record a rejected or blocked candidate review outcome so automation can learn without promoting memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "string"},
                "outcome": {"type": "string", "enum": ["rejected", "blocked"]},
                "reason": {"type": "string", "description": "Why the candidate was rejected or blocked"},
                "score": {"type": "number", "description": "Optional 0..1 feedback score"},
            },
            "required": ["candidate_id", "outcome", "reason"]
        }
    },
    {
        "name": "vault_memory_candidates",
        "description": "List memory candidates for review. Defaults to pending candidates and omits full raw content unless requested.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Candidate status filter, for example candidate/promoted/rejected.",
                    "default": "candidate",
                },
                "all": {
                    "type": "boolean",
                    "description": "List all statuses instead of filtering by status.",
                    "default": False,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum candidates to return.",
                    "default": 50,
                    "minimum": 1,
                    "maximum": MCP_MEMORY_CANDIDATE_MAX_LIMIT,
                },
                "include_content": {
                    "type": "boolean",
                    "description": "Include full candidate content. Defaults false to keep MCP payloads small.",
                    "default": False,
                },
                "include_gates": {
                    "type": "boolean",
                    "description": "Include the full gate payload for review.",
                    "default": False,
                },
            },
        }
    },
    {
        "name": "vault_capture_session",
        "description": "Preview or write reviewable memory candidates from an agent session transcript. Dry-run by default; never promotes active memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "transcript_path": {
                    "type": "string",
                    "description": "Transcript path. Relative paths resolve under the current Vault project; absolute paths require allow_absolute_path=true.",
                },
                "format": {
                    "type": "string",
                    "enum": ["auto", "jsonl", "markdown", "text"],
                    "default": "auto",
                },
                "source_system": {
                    "type": "string",
                    "description": "Source system, for example codex/hermes/openclaw/claude-code.",
                    "default": "auto",
                },
                "agent_id": {"type": "string", "default": ""},
                "write_candidates": {
                    "type": "boolean",
                    "description": "Write gated candidates into memory_candidates. Defaults false for preview-only capture.",
                    "default": False,
                },
                "max_candidates": {
                    "type": "integer",
                    "description": "Maximum extracted candidates.",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                },
                "min_score": {
                    "type": "number",
                    "description": "Minimum deterministic capture score.",
                    "default": 0.55,
                },
                "scope": {
                    "type": "string",
                    "enum": ["private", "project", "shared", "public"],
                    "default": "project",
                },
                "sensitivity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "restricted"],
                    "default": "low",
                },
                "owner_agent": {"type": "string", "default": ""},
                "allowed_agents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
                "include_content": {
                    "type": "boolean",
                    "description": "Include redacted full candidate content. Defaults false.",
                    "default": False,
                },
                "allow_absolute_path": {
                    "type": "boolean",
                    "description": "Allow reading a transcript outside the current project directory.",
                    "default": False,
                },
            },
            "required": ["transcript_path"],
        }
    },
    {
        "name": "vault_capture_discover",
        "description": "Discover likely session transcript files without reading transcript contents. Use before vault_capture_session when the transcript path is unknown.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "search_dirs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional search directories. Relative paths resolve under the current Vault project.",
                    "default": [],
                },
                "source_system": {
                    "type": "string",
                    "description": "Preferred source system, for example codex/hermes/openclaw/claude-code.",
                    "default": "auto",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum transcript candidates to return.",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum directory depth to scan.",
                    "default": 3,
                    "minimum": 0,
                    "maximum": 8,
                },
                "max_file_mb": {
                    "type": "number",
                    "description": "Skip transcript-like files larger than this size.",
                    "default": 5.0,
                },
                "allow_absolute_paths": {
                    "type": "boolean",
                    "description": "Allow search directories outside the current project.",
                    "default": False,
                },
            },
        }
    },
    {
        "name": "vault_automation_inbox",
        "description": "Read the compact automation review inbox. Read-only by default; returns the shortest candidate/report queue without raw content unless requested.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum inbox items to return.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 50,
                },
                "include_content": {
                    "type": "boolean",
                    "description": "Include redacted candidate content. Defaults false.",
                    "default": False,
                },
                "write_handoff": {
                    "type": "boolean",
                    "description": "Write reports/automation/inbox-latest.json for scheduled handoff.",
                    "default": False,
                },
                "include_transcripts": {
                    "type": "boolean",
                    "description": "Include metadata-only transcript discovery hints. Defaults false.",
                    "default": False,
                },
                "transcript_limit": {
                    "type": "integer",
                    "description": "Maximum transcript discovery hints to include.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
            },
        }
    },
    {
        "name": "vault_obsidian_import",
        "description": "Import an existing Obsidian vault into raw/obsidian/. Run dry_run first; compile only after user confirmation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault_dir": {"type": "string", "description": "Obsidian vault directory"},
                "dry_run": {"type": "boolean", "default": True},
                "compile": {"type": "boolean", "default": False},
                "category": {"type": "string", "default": "obsidian"},
                "tags": {"type": "string", "default": "obsidian"},
                "layer": {"type": "string", "enum": ["L0", "L1", "L2", "L3"], "default": "L3"},
                "trust": {"type": "number", "default": 0.5},
                "allow_private": {"type": "boolean", "default": False},
            },
            "required": ["vault_dir"]
        }
    },
    {
        "name": "vault_dream_run",
        "description": "Run deterministic dream curation. Defaults to report-only and never deletes knowledge.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["report", "apply_safe"], "default": "report"},
                "checks": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["freshness", "dedup", "convergence", "metadata", "orphans"]},
                    "default": ["freshness", "dedup", "convergence", "metadata", "orphans"],
                },
                "limit": {"type": "integer", "default": 50},
                "write_report": {"type": "boolean", "default": True},
                "write_candidates": {
                    "type": "boolean",
                    "default": False,
                    "description": "Write Dream suggestions into the memory candidate queue. Never promotes automatically.",
                },
                "backup": {"type": "boolean", "default": True},
            }
        }
    },
    {
        "name": "vault_stats",
        "description": "取得 Vault 百科統計資訊。",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "vault_converge",
        "description": "執行收斂檢查 — 判斷哪些知識條目內容不夠完整。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "最多檢查幾條（0=全部）",
                    "default": 5
                },
                "min_trust": {
                    "type": "number",
                    "description": "只檢查 trust 低於此值（預設 1.0 = 檢查所有未收斂的）",
                    "default": 1.0
                },
            }
        }
    },
    {
        "name": "vault_freshness",
        "description": "檢查知識條目的新鮮度 — 哪些條目過期了。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "stale_only": {
                    "type": "boolean",
                    "description": "只顯示過期條目",
                    "default": True
                },
            }
        }
    },
    {
        "name": "vault_map_show",
        "description": "讀取指定知識的 Document Map 結構（章節、路徑、行號）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "knowledge_id": {
                    "type": "integer",
                    "description": "知識條目 ID"
                },
                "compact": {
                    "type": "boolean",
                    "description": "回傳精簡節點欄位（預設 false）",
                    "default": False
                },
                "agent_id": {"type": "string", "default": ""},
                "include_private": {"type": "boolean", "default": False},
                "max_sensitivity": {
                    "type": "string",
                    "enum": ["", "low", "medium", "high", "restricted"],
                    "default": ""
                },
            },
            "required": ["knowledge_id"]
        }
    },
    {
        "name": "vault_read_range",
        "description": "讀取指定知識的受限行號範圍；成功回傳固定 citation，預設最多 80 行。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "knowledge_id": {
                    "type": "integer",
                    "description": "知識條目 ID"
                },
                "node_uid": {
                    "type": "string",
                    "description": "Document Map node_uid；若省略行號，使用此 node 的行號範圍",
                    "default": ""
                },
                "line_start": {
                    "type": "integer",
                    "description": "起始行號（含）",
                    "default": 0
                },
                "line_end": {
                    "type": "integer",
                    "description": "結束行號（含）",
                    "default": 0
                },
                "agent_id": {"type": "string", "default": ""},
                "include_private": {"type": "boolean", "default": False},
                "max_sensitivity": {
                    "type": "string",
                    "enum": ["", "low", "medium", "high", "restricted"],
                    "default": ""
                },
            },
            "required": ["knowledge_id"]
        }
    },
    {
        "name": "vault_remote_search",
        "description": "透過 Supabase read-only RPC 搜尋可讀遠端記憶；預設只回傳安全 metadata 與摘要。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜尋字串；空字串會回傳最新可讀記憶",
                    "default": ""
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent 身份，用於 owner_agent / allowed_agents 過濾",
                    "default": ""
                },
                "include_private": {
                    "type": "boolean",
                    "description": "是否允許讀取此 agent 被授權的 private 記憶",
                    "default": False
                },
                "max_sensitivity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "restricted"],
                    "description": "最高可讀 sensitivity；預設 medium",
                    "default": "medium"
                },
                "limit": {
                    "type": "integer",
                    "description": "最多回傳幾筆，最高 50",
                    "default": 10
                },
                "compact": {
                    "type": "boolean",
                    "description": "回傳精簡欄位（預設 true）",
                    "default": True
                },
            },
        }
    },
    {
        "name": "vault_remote_map_show",
        "description": "從 Supabase 同步目標讀取 Document Map 結構（唯讀；SQLite 仍是 source of truth）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "knowledge_id": {
                    "oneOf": [{"type": "integer"}, {"type": "string"}],
                    "description": "Remote knowledge ID；可為本地同步的正整數 ID，或 Supabase UUID"
                },
                "compact": {
                    "type": "boolean",
                    "description": "回傳精簡節點欄位（預設 false）",
                    "default": False
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent 身份，用於 owner_agent / allowed_agents 過濾",
                    "default": ""
                },
                "include_private": {
                    "type": "boolean",
                    "description": "是否允許讀取此 agent 被授權的 private 記憶",
                    "default": False
                },
                "max_sensitivity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "restricted"],
                    "description": "最高可讀 sensitivity；預設 medium",
                    "default": "medium"
                },
            },
            "required": ["knowledge_id"]
        }
    },
    {
        "name": "vault_remote_read_range",
        "description": "從 Supabase 同步目標讀取受限行號範圍；成功回傳固定 citation，預設最多 80 行。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "knowledge_id": {
                    "oneOf": [{"type": "integer"}, {"type": "string"}],
                    "description": "Remote knowledge ID；可為本地同步的正整數 ID，或 Supabase UUID"
                },
                "node_uid": {
                    "type": "string",
                    "description": "Remote Document Map node_uid；若省略行號，使用此 node 的行號範圍",
                    "default": ""
                },
                "line_start": {
                    "type": "integer",
                    "description": "起始行號（含）",
                    "default": 0
                },
                "line_end": {
                    "type": "integer",
                    "description": "結束行號（含）",
                    "default": 0
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent 身份，用於 owner_agent / allowed_agents 過濾",
                    "default": ""
                },
                "include_private": {
                    "type": "boolean",
                    "description": "是否允許讀取此 agent 被授權的 private 記憶",
                    "default": False
                },
                "max_sensitivity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "restricted"],
                    "description": "最高可讀 sensitivity；預設 medium",
                    "default": "medium"
                },
            },
            "required": ["knowledge_id"]
        }
    },
]

TOOL_PROFILES = {
    "core": [
        "vault_search",
        "vault_read_range",
        "vault_memory_propose",
        "vault_stats",
    ],
    "review": [
        "vault_search",
        "vault_read_range",
        "vault_memory_propose",
        "vault_memory_promote",
        "vault_memory_review",
        "vault_memory_candidates",
        "vault_capture_discover",
        "vault_capture_session",
        "vault_automation_inbox",
        "vault_dream_run",
        "vault_stats",
    ],
    "remote": [
        "vault_search",
        "vault_read_range",
        "vault_memory_propose",
        "vault_stats",
        "vault_remote_search",
        "vault_remote_map_show",
        "vault_remote_read_range",
    ],
    "maintenance": [
        "vault_search",
        "vault_read_range",
        "vault_memory_propose",
        "vault_memory_promote",
        "vault_memory_review",
        "vault_memory_candidates",
        "vault_capture_discover",
        "vault_capture_session",
        "vault_automation_inbox",
        "vault_obsidian_import",
        "vault_dream_run",
        "vault_stats",
        "vault_converge",
        "vault_freshness",
    ],
    "full": [tool["name"] for tool in TOOLS],
}

_ACTIVE_TOOLS = TOOLS


def _tool_names_from_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    names = [name.strip() for name in value.split(",") if name.strip()]
    return names or None


def _tools_for_names(names: list[str]) -> list[dict]:
    by_name = {tool["name"]: tool for tool in TOOLS}
    unknown = [name for name in names if name not in by_name]
    if unknown:
        raise ValueError(f"Unknown MCP tool(s): {', '.join(unknown)}")
    return [by_name[name] for name in names]


def select_tools(tool_profile: str = "full", tools: str | None = None) -> list[dict]:
    """Return the MCP tool schemas visible to the client."""
    custom_names = _tool_names_from_csv(tools)
    if custom_names:
        return _tools_for_names(custom_names)
    if tool_profile not in TOOL_PROFILES:
        allowed = ", ".join(sorted(TOOL_PROFILES))
        raise ValueError(f"Unknown MCP tool profile '{tool_profile}' (expected {allowed})")
    return _tools_for_names(TOOL_PROFILES[tool_profile])


def _set_active_tools(tool_profile: str = "full", tools: str | None = None) -> None:
    global _ACTIVE_TOOLS
    _ACTIVE_TOOLS = select_tools(tool_profile, tools)


def handle_tool_call(name: str, arguments: dict) -> dict:
    """處理 MCP tool call，回傳結果。"""
    name = _canonical_tool_name(name)
    try:
        if name == "vault_search":
            compact = bool(arguments.get("compact", True))
            field_set = _search_field_set(arguments.get("fields"))
            limit = _clamp_int(
                arguments.get("limit", 10),
                default=10,
                minimum=1,
                maximum=MCP_SEARCH_MAX_LIMIT,
            )
            offset = _clamp_int(
                arguments.get("offset", 0),
                default=0,
                minimum=0,
                maximum=MCP_SEARCH_MAX_OFFSET,
            )
            db, search = _get_search()
            results = search.search(
                query=arguments.get("query", ""),
                mode=arguments.get("mode", "auto"),
                limit=limit,
                offset=offset,
                normalize_scores=arguments.get("normalize_scores", False),
                include_snippet=arguments.get("include_snippet", False),
                fields=None,
                min_trust=0.0,
                compact=False,
                agent_id=arguments.get("agent_id", ""),
                include_private=bool(arguments.get("include_private", False)),
                max_sensitivity=arguments.get("max_sensitivity", ""),
            )
            # 簡化輸出
            output = []
            for r in results:
                if compact:
                    item = {
                        "id": r.get("id"),
                        "title": r.get("title"),
                        "best_claim": r.get("best_claim", ""),
                        "best_span": r.get("best_span"),
                        "node_uid": r.get("node_uid"),
                        "path": r.get("path"),
                        "heading": r.get("heading"),
                        "line_start": r.get("line_start"),
                        "line_end": r.get("line_end"),
                        "citation": r.get("citation"),
                        "recommended_next_tool": r.get("recommended_next_tool"),
                        "next_action": r.get("next_action"),
                        "next_actions": r.get("next_actions"),
                        "rerank_score": r.get("rerank_score", r.get("_rerank_score")),
                        "_score": r.get("_score"),
                        "_original_score": r.get("_original_score"),
                        "_snippet": r.get("_snippet"),
                    }
                    item = {k: v for k, v in item.items() if v is not None}
                    if field_set is not None:
                        item = {k: v for k, v in item.items() if k in field_set}
                    output.append(item)
                    continue
                item = {
                    "id": r.get("id"),
                    "title": r.get("title"),
                    "category": r.get("category"),
                    "layer": r.get("layer"),
                    "trust": r.get("trust"),
                    "tags": r.get("tags"),
                    "best_claim": r.get("best_claim", ""),
                    "best_span": r.get("best_span"),
                    "best_node": r.get("best_node"),
                    "node_uid": r.get("node_uid"),
                    "path": r.get("path"),
                    "heading": r.get("heading"),
                    "line_start": r.get("line_start"),
                    "line_end": r.get("line_end"),
                    "citation": r.get("citation"),
                    "recommended_next_tool": r.get("recommended_next_tool"),
                    "next_action": r.get("next_action"),
                    "next_actions": r.get("next_actions"),
                    "rerank_score": r.get("_rerank_score"),
                    "_score": r.get("_score"),
                    "_original_score": r.get("_original_score"),
                    "_snippet": r.get("_snippet"),
                }
                # 截斷 content_raw
                raw = r.get("content_raw", "")
                if raw and len(raw) > 200:
                    item["content_preview"] = raw[:200] + "..."
                else:
                    item["content_preview"] = raw
                if field_set is not None:
                    item = {k: v for k, v in item.items() if k in field_set}
                output.append(item)
            db.close()
            return {"result": json.dumps(output, ensure_ascii=False, indent=2)}

        elif name == "vault_add":
            from vault.docmap import build_document_map_for_entry
            from vault.privacy import scan_privacy

            privacy = scan_privacy(
                "\n".join(
                    str(arguments.get(field, ""))
                    for field in (
                        "title", "content", "category", "tags", "layer",
                        "scope", "sensitivity", "owner_agent", "allowed_agents", "memory_type",
                    )
                )
            )
            if privacy["status"] == "fail":
                return {"result": json.dumps({
                    "success": False,
                    "error": "privacy_gate_failed",
                    "privacy": privacy,
                    "message": "vault_add blocked secret-like content; use vault_memory_propose after removing secrets.",
                }, ensure_ascii=False)}
            db = _get_db()
            try:
                kid = db.add_knowledge(
                    title=arguments.get("title", ""),
                    content_raw=arguments.get("content", ""),
                    category=arguments.get("category", "general"),
                    tags=arguments.get("tags", ""),
                    trust=arguments.get("trust", 0.5),
                    layer=arguments.get("layer", "L3"),
                    source="mcp",
                    scope=arguments.get("scope", "project"),
                    sensitivity=arguments.get("sensitivity", "low"),
                    owner_agent=arguments.get("owner_agent", ""),
                    allowed_agents=arguments.get("allowed_agents", []),
                    memory_type=arguments.get("memory_type", "knowledge"),
                    expires_at=arguments.get("expires_at", ""),
                )
                try:
                    build_document_map_for_entry(db.conn, kid)
                    map_built = True
                except Exception:
                    map_built = False
            finally:
                db.close()
            return {"result": json.dumps({
                "success": True,
                "id": kid,
                "message": f"已新增知識 #{kid}: {arguments.get('title', '')}",
                "warning": "vault_add is a direct low-level active-DB write without a raw Markdown source; autonomous agents should prefer vault_memory_propose.",
                "document_map_built": map_built,
            }, ensure_ascii=False)}

        elif name == "vault_memory_propose":
            from vault.memory import propose_memory

            db = _get_db()
            try:
                payload = propose_memory(
                    db,
                    title=arguments.get("title", ""),
                    content=arguments.get("content", ""),
                    reason=arguments.get("reason", ""),
                    mode=arguments.get("mode", "candidate"),
                    layer=arguments.get("layer", "L3"),
                    category=arguments.get("category", "general"),
                    tags=arguments.get("tags", ""),
                    trust=arguments.get("trust", 0.5),
                    source=arguments.get("source", "mcp"),
                    source_ref=arguments.get("source_ref", ""),
                    scope=arguments.get("scope", "project"),
                    sensitivity=arguments.get("sensitivity", "low"),
                    owner_agent=arguments.get("owner_agent", ""),
                    allowed_agents=arguments.get("allowed_agents", []),
                    memory_type=arguments.get("memory_type", "knowledge"),
                    expires_at=arguments.get("expires_at", ""),
                )
            finally:
                db.close()
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_memory_promote":
            from vault.memory import promote_candidate

            project_dir = str(Path(DB_PATH).resolve().parent)
            db = _get_db()
            try:
                payload = promote_candidate(
                    db,
                    arguments.get("candidate_id", ""),
                    confirm=bool(arguments.get("confirm", False)),
                    project_dir=project_dir,
                    compile=bool(arguments.get("compile", True)),
                    build_map=bool(arguments.get("build_map", True)),
                )
            finally:
                db.close()
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_memory_review":
            from vault.memory import review_candidate

            db = _get_db()
            try:
                score_arg = arguments.get("score", None)
                payload = review_candidate(
                    db,
                    arguments.get("candidate_id", ""),
                    outcome=arguments.get("outcome", ""),
                    reason=arguments.get("reason", ""),
                    score=score_arg if score_arg is not None else None,
                )
            finally:
                db.close()
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_memory_candidates":
            limit = _clamp_int(
                arguments.get("limit", 50),
                default=50,
                minimum=1,
                maximum=MCP_MEMORY_CANDIDATE_MAX_LIMIT,
            )
            status = None if bool(arguments.get("all", False)) else arguments.get("status", "candidate")
            db = _get_db()
            try:
                rows = db.list_memory_candidates(status=status, limit=limit)
            finally:
                db.close()
            payload = {
                "count": len(rows),
                "status": status or "all",
                "candidates": [
                    _format_memory_candidate(
                        row,
                        include_content=bool(arguments.get("include_content", False)),
                        include_gates=bool(arguments.get("include_gates", False)),
                    )
                    for row in rows
                ],
            }
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_capture_session":
            from vault.session_capture import capture_session_candidates

            db = _get_db()
            try:
                transcript_path = _resolve_mcp_transcript_path(
                    str(arguments.get("transcript_path") or ""),
                    allow_absolute_path=bool(arguments.get("allow_absolute_path", False)),
                )
                payload = capture_session_candidates(
                    db,
                    transcript_path,
                    input_format=str(arguments.get("format") or "auto"),
                    source_system=str(arguments.get("source_system") or "auto"),
                    agent_id=str(arguments.get("agent_id") or ""),
                    write_candidates=bool(arguments.get("write_candidates", False)),
                    max_candidates=_clamp_int(
                        arguments.get("max_candidates", 20),
                        default=20,
                        minimum=1,
                        maximum=100,
                    ),
                    min_score=float(arguments.get("min_score", 0.55) or 0.55),
                    scope=str(arguments.get("scope") or "project"),
                    sensitivity=str(arguments.get("sensitivity") or "low"),
                    owner_agent=str(arguments.get("owner_agent") or ""),
                    allowed_agents=arguments.get("allowed_agents") or "",
                    include_content=bool(arguments.get("include_content", False)),
                )
            finally:
                db.close()
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_capture_discover":
            from vault.session_capture import discover_session_transcripts

            search_dirs = arguments.get("search_dirs") or []
            if not isinstance(search_dirs, list):
                search_dirs = []
            payload = discover_session_transcripts(
                Path(DB_PATH).resolve().parent,
                search_dirs=[str(item) for item in search_dirs if str(item).strip()] or None,
                source_system=str(arguments.get("source_system") or "auto"),
                limit=_clamp_int(arguments.get("limit", 10), default=10, minimum=1, maximum=50),
                max_depth=_clamp_int(arguments.get("max_depth", 3), default=3, minimum=0, maximum=8),
                max_file_mb=float(arguments.get("max_file_mb", 5.0) or 5.0),
                allow_absolute_paths=bool(arguments.get("allow_absolute_paths", False)),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_automation_inbox":
            from vault.automation import automation_inbox

            limit = _clamp_int(arguments.get("limit", 5), default=5, minimum=1, maximum=50)
            payload = automation_inbox(
                Path(DB_PATH).resolve().parent,
                limit=limit,
                include_content=bool(arguments.get("include_content", False)),
                include_transcripts=bool(arguments.get("include_transcripts", False)),
                transcript_limit=_clamp_int(
                    arguments.get("transcript_limit", 5),
                    default=5,
                    minimum=1,
                    maximum=20,
                ),
                write_handoff=bool(arguments.get("write_handoff", False)),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_obsidian_import":
            from vault.agent_setup import compile_project
            from vault.import_obsidian import sync_obsidian_vault

            project_dir = Path(DB_PATH).resolve().parent
            dry_run = bool(arguments.get("dry_run", True))
            payload = {
                "project_dir": str(project_dir),
                "vault_dir": arguments.get("vault_dir", ""),
                "dry_run": dry_run,
                "import": sync_obsidian_vault(
                    project_dir=project_dir,
                    vault_dir=arguments.get("vault_dir", ""),
                    category=arguments.get("category", "obsidian"),
                    tags=arguments.get("tags", "obsidian"),
                    layer=arguments.get("layer", "L3"),
                    trust=float(arguments.get("trust", 0.5)),
                    dry_run=dry_run,
                    allow_private=bool(arguments.get("allow_private", False)),
                ),
            }
            if bool(arguments.get("compile", False)) and not dry_run:
                payload["compile"] = compile_project(
                    project_dir,
                    allow_private=bool(arguments.get("allow_private", False)),
                )
            else:
                payload["next_action"] = {
                    "tool": "vault_obsidian_import",
                    "arguments": {
                        "vault_dir": arguments.get("vault_dir", ""),
                        "dry_run": False,
                        "compile": True,
                    },
                    "instruction": "Run only after the user confirms the dry-run result.",
                }
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_dream_run":
            from vault.dream import run_dream

            payload = run_dream(
                Path(DB_PATH).resolve().parent,
                mode=arguments.get("mode", "report"),
                checks=arguments.get("checks"),
                limit=arguments.get("limit", 50),
                write_report=bool(arguments.get("write_report", True)),
                write_candidates=bool(arguments.get("write_candidates", False)),
                backup=bool(arguments.get("backup", True)),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_stats":
            db = _get_db()
            stats = db.stats()
            db.close()
            return {"result": json.dumps(stats, ensure_ascii=False, indent=2)}

        elif name == "vault_converge":
            # 使用關鍵詞 fallback，不依賴 LLM
            from scripts.convergence_check import check_convergence
            results = check_convergence(
                db_path=DB_PATH,
                apply=False,  # MCP 只讀取，不自動更新
                limit=arguments.get("limit", 5),
                min_trust=arguments.get("min_trust", 1.0),
            )
            if results is None:
                return {"result": json.dumps({"message": "沒有待檢查的條目"}, ensure_ascii=False)}
            output = [{
                "id": r["id"],
                "title": r["title"],
                "avg_score": r["avg_score"],
                "status": r["status"],
            } for r in results]
            return {"result": json.dumps(output, ensure_ascii=False, indent=2)}

        elif name == "vault_freshness":
            from scripts.freshness_check import check_freshness
            results = check_freshness(
                db_path=DB_PATH,
                apply=False,  # MCP 只讀取
                stale_only=arguments.get("stale_only", True),
            )
            if results is None:
                return {"result": json.dumps({"message": "百科是空的"}, ensure_ascii=False)}
            output = [{
                "id": r["id"],
                "title": r["title"],
                "freshness": r["new_freshness"],
                "category": r["category"],
            } for r in results[:20]]  # 最多回傳 20 條
            return {"result": json.dumps(output, ensure_ascii=False, indent=2)}

        elif name == "vault_map_show":
            payload = _vault_map_show_payload(
                arguments.get("knowledge_id", 0),
                compact=bool(arguments.get("compact", False)),
                agent_id=arguments.get("agent_id", ""),
                include_private=bool(arguments.get("include_private", False)),
                max_sensitivity=arguments.get("max_sensitivity", ""),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_read_range":
            payload = _vault_read_range_payload(
                knowledge_id=arguments.get("knowledge_id", 0),
                node_uid=arguments.get("node_uid", ""),
                line_start=arguments.get("line_start", 0),
                line_end=arguments.get("line_end", 0),
                agent_id=arguments.get("agent_id", ""),
                include_private=bool(arguments.get("include_private", False)),
                max_sensitivity=arguments.get("max_sensitivity", ""),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_remote_search":
            payload = _vault_remote_search_payload(
                query=arguments.get("query", ""),
                agent_id=arguments.get("agent_id", ""),
                include_private=bool(arguments.get("include_private", False)),
                max_sensitivity=arguments.get("max_sensitivity", "medium"),
                limit=arguments.get("limit", 10),
                compact=bool(arguments.get("compact", True)),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_remote_map_show":
            payload = _vault_remote_map_show_payload(
                arguments.get("knowledge_id", 0),
                compact=bool(arguments.get("compact", False)),
                agent_id=arguments.get("agent_id", ""),
                include_private=bool(arguments.get("include_private", False)),
                max_sensitivity=arguments.get("max_sensitivity", "medium"),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_remote_read_range":
            payload = _vault_remote_read_range_payload(
                knowledge_id=arguments.get("knowledge_id", 0),
                node_uid=arguments.get("node_uid", ""),
                line_start=arguments.get("line_start", 0),
                line_end=arguments.get("line_end", 0),
                agent_id=arguments.get("agent_id", ""),
                include_private=bool(arguments.get("include_private", False)),
                max_sensitivity=arguments.get("max_sensitivity", "medium"),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        else:
            return {
                "error": f"Unknown tool: {name}",
                "failure_mode": "unknown_tool",
                "next_action": {"tool": "tools/list", "arguments": {}},
            }

    except Exception as e:
        return {
            "error": f"Error: {str(e)}",
            "failure_mode": "tool_execution_failed",
            "next_action": {"tool": name, "arguments": arguments or {}},
        }


# ── stdio MCP Server ──────────────────────────────────

def run_stdio():
    """作為 stdio MCP server 運行。"""
    # 讀取 MCP 協議訊息
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = message.get("method", "")
        msg_id = message.get("id")
        params = message.get("params", {})

        # Initialize
        if method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False},
                    },
                    "serverInfo": {
                        "name": "vault-mcp",
                        "version": __version__,
                    },
                },
            }
            print(json.dumps(response), flush=True)

        # List tools
        elif method == "tools/list":
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": _ACTIVE_TOOLS},
            }
            print(json.dumps(response), flush=True)

        # Call tool
        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = handle_tool_call(tool_name, arguments)

            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {"type": "text", "text": result.get("result", result.get("error", ""))}
                    ]
                },
            }
            print(json.dumps(response), flush=True)

        # Notifications (no response needed)
        elif method == "notifications/initialized":
            pass

        else:
            if msg_id is not None:
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
                print(json.dumps(response), flush=True)


# ── Direct CLI (for testing) ──────────────────────────

def main(argv: list[str] | None = None):
    """Entry point for the vault-mcp command."""
    parser = argparse.ArgumentParser(
        prog="vault-mcp",
        description="Vault-for-LLM MCP server",
    )
    parser.add_argument(
        "--project-dir",
        help="Project directory containing vault.db (defaults to VAULT_PATH or package root)",
    )
    parser.add_argument(
        "--tool-profile",
        choices=sorted(TOOL_PROFILES),
        default=os.environ.get("VAULT_MCP_TOOL_PROFILE", "full"),
        help=(
            "MCP tool visibility profile. Use 'core' to reduce agent tool-schema tokens. "
            "Default: full for backward compatibility."
        ),
    )
    parser.add_argument(
        "--tools",
        default=os.environ.get("VAULT_MCP_TOOLS"),
        help="Comma-separated explicit MCP tool allowlist; overrides --tool-profile.",
    )
    parser.add_argument(
        "--cli",
        nargs=argparse.REMAINDER,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    if args.project_dir:
        _set_project_dir(args.project_dir)

    try:
        _set_active_tools(args.tool_profile, args.tools)
    except ValueError as exc:
        parser.error(str(exc))

    if args.cli is not None:
        cli_args = args.cli
        tool_name = cli_args[0] if cli_args else "stats"
        tool_args = {}

        if tool_name == "search" and len(cli_args) > 1:
            tool_args = {"query": cli_args[1], "mode": "auto", "limit": 5}
        elif tool_name == "add" and len(cli_args) > 2:
            tool_args = {"title": cli_args[1], "content": cli_args[2]}
        elif tool_name == "stats":
            tool_args = {}
        elif tool_name == "converge":
            tool_args = {"limit": 5}
        elif tool_name == "freshness":
            tool_args = {"stale_only": True}

        result = handle_tool_call(f"vault_{tool_name}", tool_args)
        print(result.get("result", result.get("error", "")))
    else:
        run_stdio()


if __name__ == "__main__":
    main()
