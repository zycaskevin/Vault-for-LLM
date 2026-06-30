"""Agent access presets for shared/private Vault installs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


AGENT_ACCESS_PRESETS: dict[str, dict[str, Any]] = {
    "personal-agent": {
        "label": "Personal Agent",
        "role": "profile",
        "scope": "private",
        "max_sensitivity": "high",
        "tool_profile": "review",
        "can_write_candidates": True,
        "can_promote": False,
        "can_write_shared": False,
        "can_write_private": True,
        "private_memory": True,
        "remote_reader": False,
        "memory_layout": "hybrid",
        "setup_scope": "private",
        "summary": "Keeps user profile, preferences, and private notes local unless reviewed summaries are shared.",
    },
    "work-agent": {
        "label": "Work Agent",
        "role": "work",
        "scope": "shared",
        "max_sensitivity": "medium",
        "tool_profile": "core",
        "can_write_candidates": True,
        "can_promote": False,
        "can_write_shared": True,
        "can_write_private": False,
        "private_memory": False,
        "remote_reader": False,
        "memory_layout": "hybrid",
        "setup_scope": "shared",
        "summary": "Uses reviewed project memory and proposes low/medium sensitivity work lessons.",
    },
    "review-agent": {
        "label": "Review Agent",
        "role": "observer",
        "scope": "shared",
        "max_sensitivity": "medium",
        "tool_profile": "review",
        "can_write_candidates": False,
        "can_promote": False,
        "can_write_shared": False,
        "can_write_private": False,
        "private_memory": False,
        "remote_reader": False,
        "memory_layout": "shared",
        "setup_scope": "shared",
        "summary": "Reads review queues, reports, and bounded evidence without mutating active memory.",
    },
    "automation-agent": {
        "label": "Automation Agent",
        "role": "automation",
        "scope": "shared",
        "max_sensitivity": "low",
        "tool_profile": "maintenance",
        "can_write_candidates": True,
        "can_promote": False,
        "can_write_shared": False,
        "can_write_private": False,
        "private_memory": False,
        "remote_reader": True,
        "memory_layout": "shared",
        "setup_scope": "shared",
        "summary": "Runs scheduled reports, sync, and candidate-first maintenance with low default sensitivity.",
    },
    "remote-readonly-agent": {
        "label": "Remote Read-Only Agent",
        "role": "remote",
        "scope": "shared",
        "max_sensitivity": "medium",
        "tool_profile": "remote",
        "can_write_candidates": False,
        "can_promote": False,
        "can_write_shared": False,
        "can_write_private": False,
        "private_memory": False,
        "remote_reader": True,
        "memory_layout": "shared",
        "setup_scope": "shared",
        "summary": "Reads Supabase-synced shared memory through scoped remote-reader paths only.",
    },
    "admin-agent": {
        "label": "Admin Agent",
        "role": "work",
        "scope": "shared",
        "max_sensitivity": "high",
        "tool_profile": "maintenance",
        "can_write_candidates": True,
        "can_promote": True,
        "can_write_shared": True,
        "can_write_private": False,
        "private_memory": False,
        "remote_reader": False,
        "memory_layout": "hybrid",
        "setup_scope": "shared",
        "summary": "Maintains the vault and can run explicit review/promote workflows; keep local and trusted.",
    },
}


ROLE_PRESET_ALIASES = {
    "profile": "personal-agent",
    "care": "personal-agent",
    "dream": "automation-agent",
    "work": "work-agent",
    "observer": "review-agent",
    "automation": "automation-agent",
    "remote": "remote-readonly-agent",
}


AGENT_ACCESS_OVERRIDE_FIELDS = {
    "scope",
    "max_sensitivity",
    "tool_profile",
    "can_write_candidates",
    "can_promote",
    "can_write_shared",
    "can_write_private",
    "private_memory",
    "remote_reader",
    "memory_layout",
}


def valid_agent_access_presets() -> set[str]:
    return set(AGENT_ACCESS_PRESETS)


def normalize_agent_access_preset(value: str | None) -> str:
    text = str(value or "").strip().lower().replace("_", "-")
    if not text:
        return ""
    aliases = {
        "personal": "personal-agent",
        "profile-agent": "personal-agent",
        "care-agent": "personal-agent",
        "work": "work-agent",
        "review": "review-agent",
        "observer": "review-agent",
        "automation": "automation-agent",
        "remote": "remote-readonly-agent",
        "remote-reader": "remote-readonly-agent",
        "readonly": "remote-readonly-agent",
        "read-only": "remote-readonly-agent",
        "admin": "admin-agent",
        "maintainer": "admin-agent",
    }
    text = aliases.get(text, text)
    if text not in AGENT_ACCESS_PRESETS:
        allowed = ", ".join(sorted(AGENT_ACCESS_PRESETS))
        raise ValueError(f"unknown agent access preset '{value}' (expected one of: {allowed})")
    return text


def agent_access_preset(value: str | None) -> dict[str, Any]:
    preset = normalize_agent_access_preset(value)
    if not preset:
        return {}
    item = deepcopy(AGENT_ACCESS_PRESETS[preset])
    item["preset"] = preset
    return item


def _custom_agent_access_base() -> dict[str, Any]:
    return {
        "preset": "custom",
        "label": "Custom Agent",
        "role": "custom",
        "scope": "shared",
        "max_sensitivity": "medium",
        "tool_profile": "core",
        "can_write_candidates": True,
        "can_promote": False,
        "can_write_shared": False,
        "can_write_private": False,
        "private_memory": False,
        "remote_reader": False,
        "memory_layout": "hybrid",
        "setup_scope": "shared",
        "summary": "Custom access settings selected manually by the installer.",
    }


def apply_agent_access_overrides(
    preset: dict[str, Any] | None,
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    clean = {
        key: value
        for key, value in (overrides or {}).items()
        if key in AGENT_ACCESS_OVERRIDE_FIELDS and value is not None and value != ""
    }
    if not preset and not clean:
        return {}
    result = deepcopy(preset) if preset else _custom_agent_access_base()
    base_preset = str(result.get("preset") or "")
    applied: list[str] = []
    for key in sorted(clean):
        if result.get(key) != clean[key]:
            result[key] = clean[key]
            applied.append(key)
    if applied:
        result["customized"] = True
        result["base_preset"] = base_preset
        result["overrides"] = applied
        if base_preset and base_preset != "custom":
            result["preset"] = f"{base_preset}+custom"
            result["summary"] = f"{result.get('summary', '').rstrip()} Manual overrides: {', '.join(applied)}."
    else:
        result["customized"] = False
        result["overrides"] = []
    return result


def preset_for_role(role: str | None) -> dict[str, Any]:
    preset = ROLE_PRESET_ALIASES.get(str(role or "work").strip().lower(), "work-agent")
    return agent_access_preset(preset)


def agent_access_preset_catalog() -> list[dict[str, Any]]:
    return [agent_access_preset(name) for name in sorted(AGENT_ACCESS_PRESETS)]


def render_agent_access_presets_markdown() -> str:
    lines = [
        "# Agent Access Presets",
        "",
        "Use presets when a user wants several agents to share one Vault without learning every access-control field.",
        "",
        "| Preset | Role | Scope | Max sensitivity | MCP profile | Candidate write | Promote | Shared write | Private write | Remote reader |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for item in agent_access_preset_catalog():
        lines.append(
            "| {preset} | {role} | {scope} | {max_sensitivity} | {tool_profile} | {can_write_candidates} | {can_promote} | {can_write_shared} | {can_write_private} | {remote_reader} |".format(
                **item
            )
        )
    lines.extend(
        [
            "",
            "Rules:",
            "",
            "- Start normal coding and project agents with `work-agent`.",
            "- Use `remote-readonly-agent` for Coze, n8n, browser, or hosted readers.",
            "- Use `personal-agent` for profile/care memory; share only reviewed summaries.",
            "- Use `admin-agent` only for trusted local maintenance, never for hosted tools.",
            "",
        ]
    )
    return "\n".join(lines)
