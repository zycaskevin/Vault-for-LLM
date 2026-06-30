"""Agent setup roster, layout, and validation-pack helpers."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from vault.agent_access import (
    agent_access_preset,
    preset_for_role,
    render_agent_access_presets_markdown,
)
from vault.agent_setup_templates import shell_join


VALID_VALIDATION_PACK_TARGETS = {"none", "remote", "n8n", "coze", "all"}
VALID_AGENT_ROLES = {"work", "profile", "care", "dream", "remote", "automation", "observer"}


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _safe_slug(value: object, default: str = "agent") -> str:
    text = str(value or default).strip().lower()
    cleaned = []
    for char in text:
        if char.isalnum() or char in {"-", "_"}:
            cleaned.append(char)
        elif char in {" ", ".", "/"}:
            cleaned.append("-")
    slug = "".join(cleaned).strip("-_")
    return slug or default


def _role_defaults(role: str) -> dict[str, Any]:
    normalized = str(role or "work").strip().lower()
    preset = preset_for_role(normalized)
    if normalized == "care":
        preset["max_sensitivity"] = "medium"
        preset["tool_profile"] = "core"
    if normalized == "dream":
        preset["scope"] = "private"
        preset["private_memory"] = True
    if normalized == "observer":
        preset["max_sensitivity"] = "low"
    return preset


def normalize_agent_roster(raw: str | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if raw is None:
        return []
    entries: list[dict[str, Any]] = []
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        for part in parts:
            fields = [field.strip() for field in part.split(":")]
            agent = fields[0] if fields else ""
            role = fields[1] if len(fields) > 1 and fields[1] else "work"
            scope = fields[2] if len(fields) > 2 and fields[2] else None
            max_sensitivity = fields[3] if len(fields) > 3 and fields[3] else None
            entries.append(
                {
                    "agent_id": agent,
                    "role": role,
                    **({"scope": scope} if scope else {}),
                    **({"max_sensitivity": max_sensitivity} if max_sensitivity else {}),
                }
            )
    else:
        entries = [dict(item) for item in raw]

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in entries:
        agent_id = _safe_slug(item.get("agent_id") or item.get("agent") or item.get("name"), default="")
        if not agent_id:
            raise ValueError("agent roster entries require an agent id")
        if agent_id in seen:
            continue
        seen.add(agent_id)
        role = str(item.get("role") or "work").strip().lower()
        if role not in VALID_AGENT_ROLES:
            allowed = ", ".join(sorted(VALID_AGENT_ROLES))
            raise ValueError(f"unknown agent role '{role}' (expected one of: {allowed})")
        preset_name = str(item.get("access_preset") or item.get("preset") or "").strip()
        defaults = agent_access_preset(preset_name) if preset_name else _role_defaults(role)
        scope = str(item.get("scope") or defaults["scope"]).strip().lower()
        if scope not in {"private", "project", "shared", "public"}:
            raise ValueError("agent roster scope must be private, project, shared, or public")
        max_sensitivity = str(item.get("max_sensitivity") or defaults["max_sensitivity"]).strip().lower()
        if max_sensitivity not in {"low", "medium", "high", "restricted"}:
            raise ValueError("agent roster max_sensitivity must be low, medium, high, or restricted")
        normalized.append(
            {
                "agent_id": agent_id,
                "role": role,
                "access_preset": str(defaults.get("preset") or preset_name or ""),
                "summary": str(defaults.get("summary") or ""),
                "scope": scope,
                "max_sensitivity": max_sensitivity,
                "tool_profile": str(item.get("tool_profile") or defaults["tool_profile"]),
                "can_write_candidates": bool(item.get("can_write_candidates", defaults["can_write_candidates"])),
                "can_promote": bool(item.get("can_promote", defaults.get("can_promote", False))),
                "can_write_shared": bool(item.get("can_write_shared", defaults.get("can_write_shared", False))),
                "can_write_private": bool(item.get("can_write_private", defaults.get("can_write_private", False))),
                "private_memory": bool(item.get("private_memory", defaults.get("private_memory", role in {"profile", "care", "dream"}))),
                "remote_reader": bool(item.get("remote_reader", defaults.get("remote_reader", role in {"remote", "automation", "observer"}))),
            }
        )
    return normalized


def render_agent_access_matrix(roster: list[dict[str, Any]]) -> str:
    lines = [
        "# Vault-for-LLM Agent Access Matrix",
        "",
        "Use this file as the reviewed roster for multi-agent memory sharing.",
        "",
        "| Agent | Preset | Role | Scope | Max sensitivity | Tool profile | Candidate write | Promote | Shared write | Private write | Private memory | Remote reader |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for item in roster:
        lines.append(
            "| {agent_id} | {access_preset} | {role} | {scope} | {max_sensitivity} | {tool_profile} | {can_write_candidates} | {can_promote} | {can_write_shared} | {can_write_private} | {private_memory} | {remote_reader} |".format(
                **item
            )
        )
    lines.extend(
        [
            "",
            "Rules:",
            "",
            "- Persona files, raw private chats, and high-sensitivity profile notes stay in each agent's private memory.",
            "- Shared project memory should be reviewed, source-backed, and usually `sensitivity: low` or `medium`.",
            "- Care/profile agents may publish reviewed L2 summaries, not raw private conversations.",
            "- Remote readers use `SUPABASE_ANON_KEY` or a scoped authenticated token, never the service role key.",
            "",
        ]
    )
    return "\n".join(lines)


def write_agent_roster_templates(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    roster: str | list[dict[str, Any]],
) -> dict[str, Any]:
    normalized = normalize_agent_roster(roster)
    if not normalized:
        return {}
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    env_dir = out / "agent-env"
    env_dir.mkdir(parents=True, exist_ok=True)
    project_path = Path(project_dir).expanduser()

    roster_path = out / "agent-roster.json"
    roster_path.write_text(json.dumps({"agents": normalized}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    matrix_path = out / "AGENT_ACCESS_MATRIX.md"
    matrix_path.write_text(render_agent_access_matrix(normalized), encoding="utf-8")
    presets_path = out / "AGENT_ACCESS_PRESETS.md"
    presets_path.write_text(render_agent_access_presets_markdown(), encoding="utf-8")

    command_lines = ["#!/usr/bin/env sh", "set -eu", ""]
    env_paths: dict[str, str] = {}
    for item in normalized:
        agent_id = item["agent_id"]
        env_path = env_dir / f"{agent_id}.env.example"
        env_path.write_text(
            "\n".join(
                [
                    f"VAULT_AGENT_ID={agent_id}",
                    f"VAULT_AGENT_ROLE={item['role']}",
                    f"VAULT_SCOPE={item['scope']}",
                    f"VAULT_MAX_SENSITIVITY={item['max_sensitivity']}",
                    f"VAULT_TOOL_PROFILE={item['tool_profile']}",
                    f"VAULT_AGENT_ACCESS_PRESET={item['access_preset']}",
                    f"VAULT_CAN_WRITE_CANDIDATES={str(item['can_write_candidates']).lower()}",
                    f"VAULT_CAN_PROMOTE={str(item['can_promote']).lower()}",
                    f"VAULT_PROJECT_DIR={project_path}",
                    "SUPABASE_URL=https://YOUR_PROJECT.supabase.co",
                    "SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        env_paths[agent_id] = str(env_path)
        command_lines.append(
            shell_join(
                [
                    "vault",
                    "setup-agent",
                    "--non-interactive",
                    "--agent",
                    agent_id,
                    "--scope",
                    "private" if item["private_memory"] else "shared",
                    "--agent-project-dir",
                    str(project_path),
                    "--features",
                    "core,mcp",
                    "--tool-profile",
                    item["tool_profile"],
                    "--agent-preset",
                    item["access_preset"] or "work-agent",
                    "--max-sensitivity",
                    item["max_sensitivity"],
                    "--can-write-candidates" if item["can_write_candidates"] else "--no-can-write-candidates",
                    "--can-promote" if item["can_promote"] else "--no-can-promote",
                    "--can-write-shared" if item["can_write_shared"] else "--no-can-write-shared",
                    "--can-write-private" if item["can_write_private"] else "--no-can-write-private",
                    "--private-memory" if item["private_memory"] else "--no-private-memory",
                    "--agent-remote-reader" if item["remote_reader"] else "--no-agent-remote-reader",
                    "--json",
                ]
            )
        )

    commands_path = out / "agent-setup-commands.sh"
    commands_path.write_text("\n".join(command_lines) + "\n", encoding="utf-8")

    readme_path = out / "README-agent-roster.md"
    readme_path.write_text(
        "\n".join(
            [
                "# Vault-for-LLM Multi-Agent Roster",
                "",
                "Generated files:",
                "",
                "- `agent-roster.json`: machine-readable roster.",
                "- `AGENT_ACCESS_MATRIX.md`: human-reviewed sharing policy.",
                "- `AGENT_ACCESS_PRESETS.md`: preset catalog for common Agent roles.",
                "- `agent-env/*.env.example`: per-agent environment examples.",
                "- `agent-setup-commands.sh`: local setup commands for each agent.",
                "",
                "Review the matrix before using these settings in production. This generator does not grant access by itself; it writes policy files and setup helpers.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "count": len(normalized),
        "roster": str(roster_path),
        "matrix": str(matrix_path),
        "presets": str(presets_path),
        "commands": str(commands_path),
        "readme": str(readme_path),
        "env": env_paths,
    }


def write_memory_layout_manifest(
    *,
    output_dir: str | Path,
    agent: str,
    memory_layout: str,
    shared_project_dir: str | Path,
    private_project_dir: str | Path | None = None,
) -> dict[str, str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    safe_agent = _safe_slug(agent, default="generic")
    shared_path = Path(shared_project_dir).expanduser().resolve()
    private_path = Path(private_project_dir).expanduser().resolve() if private_project_dir else None
    payload: dict[str, Any] = {
        "version": 1,
        "agent": safe_agent,
        "memory_layout": memory_layout,
        "shared_project_dir": str(shared_path),
        "shared_db_path": str(shared_path / "vault.db"),
        "private_project_dir": str(private_path) if private_path else "",
        "private_db_path": str(private_path / "vault.db") if private_path else "",
        "rules": {
            "shared": "Reviewed project knowledge, SOPs, fixes, release process, benchmark evidence, and safety rules.",
            "private": "Agent identity, private preferences, personal notes, and agent-specific working style. Local-only by default.",
        },
        "startup_commands": [
            "vault update-status",
            f"vault automation handoff --project-dir {shared_path}",
        ],
    }
    manifest_path = out / "hybrid-vault-layout.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    readme_path = out / "README-hybrid-vault-layout.md"
    readme_path.write_text(
        "\n".join(
            [
                "# Hybrid Vault Layout",
                "",
                "This setup separates shared project memory from private Agent memory.",
                "",
                f"- Agent: `{safe_agent}`",
                f"- Layout: `{memory_layout}`",
                f"- Shared project vault: `{shared_path}`",
                f"- Private Agent vault: `{private_path or ''}`",
                "",
                "Shared project memory is for reviewed project knowledge, SOPs, fixes, release process, benchmark evidence, and safety rules.",
                "Private Agent memory is local-only by default and is for identity, private preferences, personal notes, and agent-specific working style.",
                "",
                "Startup:",
                "",
                "```bash",
                "vault update-status",
                f"vault automation handoff --project-dir {shlex.quote(str(shared_path))}",
                "```",
                "",
                "This manifest is a coordination file. It is not an authorization policy and does not sync private memory.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return {"manifest": str(manifest_path), "readme": str(readme_path)}


def _normalize_validation_pack_targets(raw: str | list[str] | None) -> set[str]:
    if raw is None:
        return set()
    if isinstance(raw, str):
        parts = [part.strip().lower() for part in raw.split(",") if part.strip()]
    else:
        parts = [str(part).strip().lower() for part in raw if str(part).strip()]
    if not parts or "none" in parts:
        return set()
    unknown = [part for part in parts if part not in VALID_VALIDATION_PACK_TARGETS]
    if unknown:
        allowed = ", ".join(sorted(VALID_VALIDATION_PACK_TARGETS))
        raise ValueError(f"unknown validation pack target '{unknown[0]}' (expected one of: {allowed})")
    if "all" in parts:
        return {"remote", "n8n", "coze"}
    return set(parts)


def write_live_validation_pack(
    *,
    output_dir: str | Path,
    agent: str,
    targets: str | list[str] = "all",
    query: str = "deployment SOP",
) -> dict[str, str]:
    selected = _normalize_validation_pack_targets(targets)
    if not selected:
        return {}
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    safe_agent = _safe_slug(agent, default="generic")
    safe_query = str(query or "deployment SOP")
    written: dict[str, str] = {}

    if "remote" in selected:
        path = out / "validate-remote-reader.sh"
        path.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env sh",
                    "set -eu",
                    ": \"${SUPABASE_URL:?Set SUPABASE_URL first}\"",
                    ": \"${SUPABASE_ANON_KEY:?Set SUPABASE_ANON_KEY first}\"",
                    shell_join(["vault", "remote", "smoke", "--agent-id", safe_agent, "--query", safe_query, "--json"]),
                    shell_join(["vault", "remote", "search", safe_query, "--agent-id", safe_agent, "--json"]),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        written["remote"] = str(path)

    if "n8n" in selected:
        path = out / "VALIDATE-n8n.md"
        path.write_text(
            "\n".join(
                [
                    "# Validate n8n Remote Reader",
                    "",
                    "1. Import `n8n-remote-reader.workflow.json` from the same `agent-install/` directory.",
                    "2. Ensure the n8n host can run the `vault` CLI.",
                    "3. Set `SUPABASE_URL` and `SUPABASE_ANON_KEY` in the n8n process environment.",
                    "4. Run the manual trigger and confirm the command output contains `vault_search_readable` results.",
                    "5. Do not place `SUPABASE_SERVICE_ROLE_KEY` in n8n unless n8n is the trusted sync host.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        written["n8n"] = str(path)

    if "coze" in selected:
        path = out / "VALIDATE-coze.md"
        path.write_text(
            "\n".join(
                [
                    "# Validate Coze Remote Reader",
                    "",
                    "1. Import `coze-supabase-vault-openapi.json` as the Coze connector schema.",
                    "2. Replace `https://YOUR_PROJECT.supabase.co/rest/v1` with your Supabase REST endpoint.",
                    "3. Configure the Supabase anon key as both the `apikey` header and the bearer value for the authorization header.",
                    "4. Call `vaultRemoteSearch` with `p_agent_id`, `p_query`, `p_include_private=false`, `p_max_sensitivity=medium`, and `p_limit=5`.",
                    "5. Confirm responses contain safe summaries and do not expose `content_raw`.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        written["coze"] = str(path)

    readme = out / "README-live-validation.md"
    readme.write_text(
        "\n".join(
            [
                "# Vault-for-LLM Live Validation Pack",
                "",
                "Use this after the local setup, Supabase schema, read policy, and first sync are complete.",
                "",
                "Validation order:",
                "",
                "1. Run `validate-remote-reader.sh` on a trusted machine.",
                "2. Import and run the n8n workflow if n8n is part of the deployment.",
                    "3. Import and call the Coze OpenAPI connector if Coze or another hosted agent is part of the deployment.",
                "",
                "Passing local tests does not prove remote credentials or hosted platform settings. This pack verifies the external deployment without exposing service-role credentials to hosted agents.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    written["readme"] = str(readme)
    return written
