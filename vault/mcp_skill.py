"""MCP handlers for the local Skill registry."""

from __future__ import annotations

import json
from typing import Any


MCP_SKILL_TOOL_NAMES = [
    "vault_skill_search",
    "vault_skill_list",
    "vault_skill_versions",
    "vault_skill_pull",
    "vault_skill_upgrade_plan",
]

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
]


def _json_result(payload: Any) -> dict[str, str]:
    return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


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
                min_trust=float(arguments.get("min_trust") or 0.0),
                agent_source=str(arguments.get("agent_source") or "") or None,
                limit=_clamp_int(arguments.get("limit"), default=20, minimum=1, maximum=100),
            )
            return _json_result({"ok": True, "skills": [_without_content(row) for row in rows]})

        if name == "vault_skill_list":
            rows = db.list_skills(
                agent_source=str(arguments.get("agent_source") or "") or None,
                category=str(arguments.get("category") or "") or None,
                min_trust=float(arguments.get("min_trust") or 0.0),
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

    return None


def _without_content(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item.pop("content_raw", None)
    return item
