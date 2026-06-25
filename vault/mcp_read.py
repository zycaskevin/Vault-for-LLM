"""Local MCP Document Map and bounded-read helpers."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from vault.access_policy import can_read_memory, normalize_read_policy


def _default_db_path() -> str:
    from vault import mcp as mcp_module

    return mcp_module.DB_PATH


def _open_readonly_db(db_path: str | None = None) -> sqlite3.Connection | None:
    """Open the local Vault DB read-only without creating missing files."""
    path = Path(db_path or _default_db_path())
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


def vault_map_show(knowledge_id: int, compact: bool = False) -> dict:
    """Return a knowledge entry's Document Map structure."""
    return _vault_map_show_payload(knowledge_id, compact=compact)


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
        return _error("db_not_found", f"vault.db not found at {db_path or _default_db_path()}")

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
        return _error("db_not_found", f"vault.db not found at {db_path or _default_db_path()}")

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
