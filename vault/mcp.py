#!/usr/bin/env python3
"""Vault-for-LLM MCP server with public ``vault_*`` tool names."""

import argparse
import hashlib
import json
import sqlite3
import sys
import os
from pathlib import Path

try:
    from . import __version__
except Exception:  # pragma: no cover - direct script fallback
    __version__ = "0.1.0"

# 確保模組路徑
VAULT_DIR = str(Path(__file__).parent.parent)
if VAULT_DIR not in sys.path:
    sys.path.insert(0, VAULT_DIR)

DB_PATH = os.path.join(
    os.environ.get("VAULT_PATH") or VAULT_DIR,
    "vault.db",
)
REMOTE_NODE_TABLE = "vault_knowledge_nodes"
REMOTE_CLAIM_TABLE = "vault_knowledge_claims"
REMOTE_KNOWLEDGE_TABLE = "vault_knowledge"
MCP_SEARCH_MAX_LIMIT = 50
MCP_SEARCH_MAX_OFFSET = 1000
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


def _format_citation(knowledge_id: int, title: str, line_start: int, line_end: int) -> str:
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
    if code in {"invalid_knowledge_id", "not_found", "remote_client_missing", "remote_read_failed"}:
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


def vault_remote_map_show(knowledge_id: int, compact: bool = False) -> dict:
    """Return a synced Supabase Document Map structure (read-only target)."""
    return _vault_remote_map_show_payload(knowledge_id, compact=compact)


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


def _remote_read_range_action(knowledge_id: int, node: dict) -> dict:
    args = {"knowledge_id": knowledge_id}
    if node.get("node_uid"):
        args["node_uid"] = node["node_uid"]
    if node.get("line_start") and node.get("line_end"):
        args["line_start"] = int(node["line_start"])
        args["line_end"] = int(node["line_end"])
    return {"tool": "vault_remote_read_range", "arguments": args}


def _supabase_rows(sb_client, table_name: str, columns: str = "*", filters: dict | None = None) -> list[dict]:
    query = sb_client.table(table_name).select(columns)
    for field, value in (filters or {}).items():
        query = query.eq(field, value)
    response = query.execute()
    return [dict(row) for row in (getattr(response, "data", None) or [])]


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
    knowledge_id: int,
    *,
    compact: bool = False,
    sb_client=None,
) -> dict:
    try:
        knowledge_id = int(knowledge_id)
    except (TypeError, ValueError):
        return _remote_error("invalid_knowledge_id", "knowledge_id must be a positive integer")
    if knowledge_id <= 0:
        return _remote_error("invalid_knowledge_id", "knowledge_id must be a positive integer")

    sb_client = sb_client or _get_supabase_client()
    if sb_client is None:
        return _remote_error(
            "remote_client_missing",
            "SUPABASE_URL and SUPABASE_ANON_KEY/SUPABASE_KEY are required for remote map reads.",
            knowledge_id=knowledge_id,
        )

    try:
        rows = _sort_remote_nodes(
            _supabase_rows(sb_client, REMOTE_NODE_TABLE, "*", {"knowledge_id": knowledge_id})
        )
    except Exception as exc:
        return _remote_error(
            "remote_read_failed",
            f"Unable to read remote Document Map nodes: {exc}",
            knowledge_id=knowledge_id,
        )

    title = next((str(row.get("knowledge_title") or "") for row in rows if row.get("knowledge_title")), "")
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
            payload["next_action"] = _remote_read_range_action(knowledge_id, preferred_node)
        payload["next_actions"] = [_remote_read_range_action(knowledge_id, node) for node in rows]
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
            "SELECT id, title FROM knowledge WHERE id=?",
            (knowledge_id,),
        ).fetchone()
        if entry is None:
            return _error("not_found", f"Knowledge id not found: {knowledge_id}")

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
    knowledge_id: int,
    node_uid: str = "",
    line_start: int = 0,
    line_end: int = 0,
) -> dict:
    """Return a bounded remote source/claim range with a fixed citation."""
    return _vault_remote_read_range_payload(
        knowledge_id,
        node_uid=node_uid,
        line_start=line_start,
        line_end=line_end,
    )


def _find_remote_content_row(sb_client, title: str, content_hash: str) -> dict | None:
    lookups = []
    if content_hash:
        lookups.append({"content_hash": content_hash})
    if title:
        lookups.append({"title": title})
    for filters in lookups:
        rows = _supabase_rows(sb_client, REMOTE_KNOWLEDGE_TABLE, "title,content_raw,content_hash", filters)
        if rows:
            return rows[0]
    return None


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
    knowledge_id: int,
    node_uid: str = "",
    line_start: int = 0,
    line_end: int = 0,
    *,
    max_lines: int = 80,
    sb_client=None,
) -> dict:
    try:
        knowledge_id = int(knowledge_id)
    except (TypeError, ValueError):
        return _remote_error("invalid_knowledge_id", "knowledge_id must be a positive integer")
    if knowledge_id <= 0:
        return _remote_error("invalid_knowledge_id", "knowledge_id must be a positive integer")

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
        nodes = _sort_remote_nodes(
            _supabase_rows(sb_client, REMOTE_NODE_TABLE, "*", {"knowledge_id": knowledge_id})
        )
        claims = _sort_remote_claims(
            _supabase_rows(sb_client, REMOTE_CLAIM_TABLE, "*", {"knowledge_id": knowledge_id})
        )
    except Exception as exc:
        return _remote_error(
            "remote_read_failed",
            f"Unable to read remote Document Map rows: {exc}",
            knowledge_id=knowledge_id,
        )

    if not nodes and not claims:
        return _remote_error(
            "no_document_map_nodes",
            "No remote Document Map rows found for this knowledge_id.",
            knowledge_id=knowledge_id,
        )

    title = next(
        (
            str(row.get("knowledge_title") or "")
            for row in [*nodes, *claims]
            if row.get("knowledge_title")
        ),
        "",
    )
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
        content_row = _find_remote_content_row(sb_client, title, knowledge_content_hash)
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
            "SELECT id, title, content_raw FROM knowledge WHERE id=?",
            (knowledge_id,),
        ).fetchone()
        if entry is None:
            return _error("not_found", f"Knowledge id not found: {knowledge_id}")

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
            },
            "required": ["knowledge_id"]
        }
    },
    {
        "name": "vault_remote_map_show",
        "description": "從 Supabase 同步目標讀取 Document Map 結構（唯讀；SQLite 仍是 source of truth）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "knowledge_id": {
                    "type": "integer",
                    "description": "本地知識條目 ID（同步到 remote 的 knowledge_id）"
                },
                "compact": {
                    "type": "boolean",
                    "description": "回傳精簡節點欄位（預設 false）",
                    "default": False
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
                    "type": "integer",
                    "description": "本地知識條目 ID（同步到 remote 的 knowledge_id）"
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
        "vault_dream_run",
        "vault_stats",
    ],
    "remote": [
        "vault_search",
        "vault_read_range",
        "vault_memory_propose",
        "vault_stats",
        "vault_remote_map_show",
        "vault_remote_read_range",
    ],
    "maintenance": [
        "vault_search",
        "vault_read_range",
        "vault_memory_propose",
        "vault_memory_promote",
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
                    for field in ("title", "content", "category", "tags", "layer")
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
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_read_range":
            payload = _vault_read_range_payload(
                knowledge_id=arguments.get("knowledge_id", 0),
                node_uid=arguments.get("node_uid", ""),
                line_start=arguments.get("line_start", 0),
                line_end=arguments.get("line_end", 0),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_remote_map_show":
            payload = _vault_remote_map_show_payload(
                arguments.get("knowledge_id", 0),
                compact=bool(arguments.get("compact", False)),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "vault_remote_read_range":
            payload = _vault_remote_read_range_payload(
                knowledge_id=arguments.get("knowledge_id", 0),
                node_uid=arguments.get("node_uid", ""),
                line_start=arguments.get("line_start", 0),
                line_end=arguments.get("line_end", 0),
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
