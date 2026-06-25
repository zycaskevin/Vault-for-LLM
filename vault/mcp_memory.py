"""MCP handlers for local memory write/review and session capture workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vault.mcp_security import check_write_allowed as _check_write_allowed

MCP_MEMORY_CANDIDATE_MAX_LIMIT = 100


def _db_path() -> str:
    from vault import mcp as mcp_module

    return mcp_module.DB_PATH


def _project_dir() -> Path:
    return Path(_db_path()).resolve().parent


def _get_db():
    from vault.db import VaultDB

    db = VaultDB(_db_path())
    db.connect()
    return db


def _json_result(payload: Any) -> dict:
    return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}


def _clamp_int(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


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


def _resolve_mcp_transcript_path(value: str, *, allow_absolute_path: bool = False) -> Path:
    project_dir = _project_dir()
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


def handle_memory_tool_call(name: str, arguments: dict) -> dict | None:
    """Handle MCP memory write/review/capture tools, or return None."""
    arguments = arguments or {}

    if name == "vault_add":
        from vault.docmap import build_document_map_for_entry
        from vault.privacy import scan_privacy

        write_denied = _check_write_allowed(
            "vault_add",
            arguments,
            {
                "scope": arguments.get("scope", "project"),
                "sensitivity": arguments.get("sensitivity", "low"),
                "owner_agent": arguments.get("owner_agent", ""),
                "allowed_agents": arguments.get("allowed_agents", []),
            },
        )
        if write_denied is not None:
            return _json_result(write_denied)
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

    if name == "vault_memory_propose":
        from vault.memory import propose_memory

        write_denied = _check_write_allowed(
            "vault_memory_propose",
            arguments,
            {
                "scope": arguments.get("scope", "project"),
                "sensitivity": arguments.get("sensitivity", "low"),
                "owner_agent": arguments.get("owner_agent", ""),
                "allowed_agents": arguments.get("allowed_agents", []),
            },
        )
        if write_denied is not None:
            return _json_result(write_denied)
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
        return _json_result(payload)

    if name == "vault_memory_promote":
        from vault.memory import promote_candidate

        db = _get_db()
        try:
            candidate_id = arguments.get("candidate_id", "")
            candidate = db.get_memory_candidate(candidate_id)
            if candidate:
                write_denied = _check_write_allowed(
                    "vault_memory_promote",
                    arguments,
                    {
                        "scope": candidate.get("scope", "project"),
                        "sensitivity": candidate.get("sensitivity", "low"),
                        "owner_agent": candidate.get("owner_agent", ""),
                        "allowed_agents": candidate.get("allowed_agents", []),
                    },
                )
                if write_denied is not None:
                    return _json_result(write_denied)
            payload = promote_candidate(
                db,
                candidate_id,
                confirm=bool(arguments.get("confirm", False)),
                project_dir=str(_project_dir()),
                compile=bool(arguments.get("compile", True)),
                build_map=bool(arguments.get("build_map", True)),
            )
        finally:
            db.close()
        return _json_result(payload)

    if name == "vault_memory_review":
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
        return _json_result(payload)

    if name == "vault_memory_candidates":
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
        return _json_result(payload)

    if name == "vault_capture_session":
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
        return _json_result(payload)

    if name == "vault_capture_discover":
        from vault.session_capture import discover_session_transcripts

        search_dirs = arguments.get("search_dirs") or []
        if not isinstance(search_dirs, list):
            search_dirs = []
        payload = discover_session_transcripts(
            _project_dir(),
            search_dirs=[str(item) for item in search_dirs if str(item).strip()] or None,
            source_system=str(arguments.get("source_system") or "auto"),
            limit=_clamp_int(arguments.get("limit", 10), default=10, minimum=1, maximum=50),
            max_depth=_clamp_int(arguments.get("max_depth", 3), default=3, minimum=0, maximum=8),
            max_file_mb=float(arguments.get("max_file_mb", 5.0) or 5.0),
            allow_absolute_paths=bool(arguments.get("allow_absolute_paths", False)),
        )
        return _json_result(payload)

    return None
