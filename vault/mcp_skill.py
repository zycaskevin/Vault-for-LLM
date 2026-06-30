"""MCP handlers for the local Skill registry."""

from __future__ import annotations

import json
import re
from typing import Any


MCP_SKILL_READ_TOOL_NAMES = [
    "vault_skill_search",
    "vault_skill_list",
    "vault_skill_versions",
    "vault_skill_pull",
    "vault_skill_upgrade_plan",
]

MCP_SKILL_SYNC_TOOL_NAMES = [
    "vault_skill_sync_status",
    "vault_skill_sync_manifest",
]

MCP_SKILL_WRITE_TOOL_NAMES = [
    "vault_skill_push",
    "vault_skill_mark_synced",
]

MCP_SKILL_TOOL_NAMES = [
    *MCP_SKILL_READ_TOOL_NAMES,
    *MCP_SKILL_SYNC_TOOL_NAMES,
    *MCP_SKILL_WRITE_TOOL_NAMES,
]

_SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
_MAX_SKILL_CONTENT_CHARS = 200_000

MCP_SKILL_TOOLS = [
    {
        "name": "vault_skill_search",
        "description": "Search the local Skill registry without returning raw Skill content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "default": ""},
                "capabilities": {"type": "string", "default": ""},
                "category": {"type": "string", "default": ""},
                "agent_source": {"type": "string", "default": ""},
                "min_trust": {"type": "number", "default": 0.0},
                "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
            },
        },
    },
    {
        "name": "vault_skill_list",
        "description": "List local Skills without raw Skill content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "default": ""},
                "agent_source": {"type": "string", "default": ""},
                "min_trust": {"type": "number", "default": 0.0},
                "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 200},
            },
        },
    },
    {
        "name": "vault_skill_versions",
        "description": "List version history for one Skill.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "vault_skill_pull",
        "description": "Read one Skill from the registry. Content is bounded by max_chars.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "max_chars": {"type": "integer", "default": 12000, "minimum": 1000, "maximum": 50000},
            },
            "required": ["name"],
        },
    },
    {
        "name": "vault_skill_upgrade_plan",
        "description": "Compare caller-installed Skill versions to the local registry latest versions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "installed": {
                    "type": "object",
                    "description": "Map of skill name to installed version.",
                    "default": {},
                },
            },
        },
    },
    {
        "name": "vault_skill_sync_status",
        "description": "List Skill registry sync status without returning raw Skill content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "default": ""},
                "agent_source": {"type": "string", "default": ""},
                "min_trust": {"type": "number", "default": 0.0},
                "include_synced": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "default": 100, "minimum": 1, "maximum": 500},
            },
        },
    },
    {
        "name": "vault_skill_sync_manifest",
        "description": "Build a compact Skill sync manifest for a trusted external sync worker. Content is omitted unless explicitly allowed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "default": ""},
                "agent_source": {"type": "string", "default": ""},
                "min_trust": {"type": "number", "default": 0.0},
                "include_synced": {"type": "boolean", "default": False},
                "include_content": {"type": "boolean", "default": False},
                "allow_skill_content_export": {"type": "boolean", "default": False},
                "max_content_chars": {"type": "integer", "default": 12000, "minimum": 1000, "maximum": 50000},
                "limit": {"type": "integer", "default": 100, "minimum": 1, "maximum": 500},
            },
        },
    },
    {
        "name": "vault_skill_push",
        "description": "Write or revise a Skill in the local registry only. Requires allow_skill_write=true and never installs runtime Skill files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "content": {"type": "string"},
                "version": {"type": "string", "default": "1.0.0"},
                "agent_source": {"type": "string", "default": ""},
                "category": {"type": "string", "default": "general"},
                "capabilities": {"type": "string", "default": ""},
                "dependencies": {"type": "string", "default": ""},
                "trust": {"type": "number", "default": 0.5},
                "description": {"type": "string", "default": ""},
                "force": {"type": "boolean", "default": False},
                "allow_skill_write": {"type": "boolean", "default": False},
            },
            "required": ["name", "content", "allow_skill_write"],
        },
    },
    {
        "name": "vault_skill_mark_synced",
        "description": "Mark one Skill as synced after an external trusted sync worker succeeds. Requires allow_skill_sync_mark=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "allow_skill_sync_mark": {"type": "boolean", "default": False},
            },
            "required": ["name", "allow_skill_sync_mark"],
        },
    },
]


def _json_result(payload: Any) -> dict[str, str]:
    return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _clamp_float(value: Any, *, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _bool_arg(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def handle_skill_tool_call(name: str, arguments: dict[str, Any], *, db_path: str) -> dict[str, str] | None:
    """Handle MCP Skill registry calls, or return ``None`` if unknown."""
    if name not in MCP_SKILL_TOOL_NAMES:
        return None

    from vault.db import VaultDB

    arguments = arguments or {}
    with VaultDB(db_path) as db:
        if name == "vault_skill_search":
            rows = db.search_skills(
                query=str(arguments.get("query") or ""),
                capabilities=str(arguments.get("capabilities") or "") or None,
                category=str(arguments.get("category") or "") or None,
                min_trust=_clamp_float(arguments.get("min_trust"), default=0.0, minimum=0.0, maximum=1.0),
                agent_source=str(arguments.get("agent_source") or "") or None,
                limit=_clamp_int(arguments.get("limit"), default=20, minimum=1, maximum=100),
            )
            return _json_result({"ok": True, "skills": [_without_content(row) for row in rows]})

        if name == "vault_skill_list":
            rows = db.list_skills(
                agent_source=str(arguments.get("agent_source") or "") or None,
                category=str(arguments.get("category") or "") or None,
                min_trust=_clamp_float(arguments.get("min_trust"), default=0.0, minimum=0.0, maximum=1.0),
                limit=_clamp_int(arguments.get("limit"), default=50, minimum=1, maximum=200),
            )
            return _json_result({"ok": True, "skills": rows})

        if name == "vault_skill_versions":
            skill_name = str(arguments.get("name") or "").strip()
            if not skill_name:
                return _json_result({"ok": False, "error": "name is required"})
            return _json_result({"ok": True, "name": skill_name, "versions": db.list_skill_versions(skill_name)})

        if name == "vault_skill_pull":
            skill_name = str(arguments.get("name") or "").strip()
            if not skill_name:
                return _json_result({"ok": False, "error": "name is required"})
            skill = db.get_skill(skill_name)
            if not skill:
                return _json_result({"ok": False, "error": "skill_not_found", "name": skill_name})
            max_chars = _clamp_int(arguments.get("max_chars"), default=12000, minimum=1000, maximum=50000)
            content = str(skill.get("content_raw") or "")
            return _json_result(
                {
                    "ok": True,
                    "skill": {
                        **_without_content(skill),
                        "content": content[:max_chars],
                        "truncated": len(content) > max_chars,
                    },
                }
            )

        if name == "vault_skill_upgrade_plan":
            installed = arguments.get("installed")
            installed_map = {
                str(key): str(value)
                for key, value in (installed or {}).items()
            } if isinstance(installed, dict) else {}
            return _json_result(db.skill_upgrade_plan(installed=installed_map))

        if name == "vault_skill_sync_status":
            rows = _sync_rows(db, arguments)
            counts = _sync_counts(rows)
            include_synced = _bool_arg(arguments.get("include_synced", False))
            if not include_synced:
                rows = [row for row in rows if row["sync_state"] != "synced"]
            return _json_result({"ok": True, "counts": counts, "skills": rows})

        if name == "vault_skill_sync_manifest":
            rows = _sync_rows(db, arguments)
            include_synced = _bool_arg(arguments.get("include_synced", False))
            include_content = _bool_arg(arguments.get("include_content", False))
            if include_content and not _bool_arg(arguments.get("allow_skill_content_export", False)):
                return _json_result(
                    {
                        "ok": False,
                        "error": "skill_content_export_not_allowed",
                        "next_action": "Set allow_skill_content_export=true only inside a trusted sync worker.",
                    }
                )
            if not include_synced:
                rows = [row for row in rows if row["sync_state"] != "synced"]
            max_chars = _clamp_int(arguments.get("max_content_chars"), default=12000, minimum=1000, maximum=50000)
            manifest = [_manifest_item(db, row, include_content=include_content, max_chars=max_chars) for row in rows]
            return _json_result(
                {
                    "ok": True,
                    "include_content": include_content,
                    "writes_runtime_files": False,
                    "items": manifest,
                    "counts": _sync_counts(rows),
                }
            )

        if name == "vault_skill_push":
            if not _bool_arg(arguments.get("allow_skill_write", False)):
                return _json_result(
                    {
                        "ok": False,
                        "error": "skill_write_not_allowed",
                        "next_action": "Set allow_skill_write=true only for trusted registry writes.",
                    }
                )
            skill_name = str(arguments.get("name") or "").strip()
            content = str(arguments.get("content") or "")
            validation = _validate_skill_payload(skill_name, content)
            if validation:
                return _json_result(validation)

            from vault.privacy import scan_privacy

            scan_text = "\n".join(
                [
                    skill_name,
                    str(arguments.get("description") or ""),
                    str(arguments.get("capabilities") or ""),
                    str(arguments.get("dependencies") or ""),
                    content,
                ]
            )
            privacy = scan_privacy(scan_text)
            if privacy.get("status") == "fail":
                return _json_result(
                    {
                        "ok": False,
                        "error": "privacy_gate_failed",
                        "privacy": privacy,
                        "next_action": "Remove secrets or private tokens before writing this Skill to the registry.",
                    }
                )

            before = db.get_skill(skill_name)
            skill_id = db.add_skill(
                name=skill_name,
                version=str(arguments.get("version") or "1.0.0").strip() or "1.0.0",
                content_raw=content,
                agent_source=str(arguments.get("agent_source") or ""),
                category=str(arguments.get("category") or "general") or "general",
                capabilities=str(arguments.get("capabilities") or ""),
                dependencies=str(arguments.get("dependencies") or ""),
                trust=_clamp_float(arguments.get("trust"), default=0.5, minimum=0.0, maximum=1.0),
                description=str(arguments.get("description") or ""),
                force=_bool_arg(arguments.get("force", False)),
            )
            after = db.get_skill(skill_name) or {}
            if not before:
                status = "created"
            elif skill_id == -1:
                status = "revision_stored_not_latest"
            else:
                status = "latest_updated"
            return _json_result(
                {
                    "ok": True,
                    "status": status,
                    "skill": _without_content(after),
                    "privacy_status": privacy.get("status"),
                    "writes_runtime_files": False,
                    "next_action": "Use vault_skill_sync_manifest for external sync, then vault_skill_mark_synced after the sync worker succeeds.",
                }
            )

        if name == "vault_skill_mark_synced":
            if not _bool_arg(arguments.get("allow_skill_sync_mark", False)):
                return _json_result(
                    {
                        "ok": False,
                        "error": "skill_sync_mark_not_allowed",
                        "next_action": "Set allow_skill_sync_mark=true only after a trusted sync worker has completed.",
                    }
                )
            skill_name = str(arguments.get("name") or "").strip()
            if not skill_name:
                return _json_result({"ok": False, "error": "name is required"})
            if not db.get_skill(skill_name):
                return _json_result({"ok": False, "error": "skill_not_found", "name": skill_name})
            db.mark_skill_synced(skill_name)
            synced = db.get_skill(skill_name) or {}
            return _json_result({"ok": True, "skill": _without_content(synced), "sync_state": "synced"})

    return None


def _without_content(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item.pop("content_raw", None)
    return item


def _validate_skill_payload(skill_name: str, content: str) -> dict[str, Any] | None:
    if not skill_name:
        return {"ok": False, "error": "name is required"}
    if not _SKILL_NAME_RE.match(skill_name) or ".." in skill_name or skill_name.startswith(("/", "\\")):
        return {
            "ok": False,
            "error": "invalid_skill_name",
            "next_action": "Use a stable registry name like review-helper or codex/review-helper.",
        }
    if not content.strip():
        return {"ok": False, "error": "content is required"}
    if len(content) > _MAX_SKILL_CONTENT_CHARS:
        return {
            "ok": False,
            "error": "skill_content_too_large",
            "max_chars": _MAX_SKILL_CONTENT_CHARS,
        }
    return None


def _sync_rows(db: Any, arguments: dict[str, Any]) -> list[dict[str, Any]]:
    rows = db.list_skills(
        agent_source=str(arguments.get("agent_source") or "") or None,
        category=str(arguments.get("category") or "") or None,
        min_trust=_clamp_float(arguments.get("min_trust"), default=0.0, minimum=0.0, maximum=1.0),
        limit=_clamp_int(arguments.get("limit"), default=100, minimum=1, maximum=500),
    )
    out = []
    for row in rows:
        item = _without_content(row)
        item["sync_state"] = _skill_sync_state(item)
        out.append(item)
    return out


def _skill_sync_state(row: dict[str, Any]) -> str:
    updated_at = str(row.get("updated_at") or "")
    last_synced = str(row.get("last_synced") or "")
    if not last_synced:
        return "never_synced"
    if updated_at and updated_at > last_synced:
        return "pending"
    return "synced"


def _sync_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"never_synced": 0, "pending": 0, "synced": 0}
    for row in rows:
        state = str(row.get("sync_state") or "never_synced")
        counts[state] = counts.get(state, 0) + 1
    return counts


def _manifest_item(db: Any, row: dict[str, Any], *, include_content: bool, max_chars: int) -> dict[str, Any]:
    item = dict(row)
    if not include_content:
        return item
    skill = db.get_skill(str(row.get("name") or "")) or {}
    content = str(skill.get("content_raw") or "")

    from vault.privacy import scan_privacy

    privacy = scan_privacy(content)
    item["privacy_status"] = privacy.get("status")
    if privacy.get("status") == "fail":
        item["content_export_blocked"] = True
        item["privacy"] = privacy
        return item
    item["content"] = content[:max_chars]
    item["truncated"] = len(content) > max_chars
    return item
