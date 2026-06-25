"""Agent setup startup, update-status, and runtime adapter helpers."""

from __future__ import annotations

import json
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vault.agent_setup_templates import render_launchagent_plist, shell_join


def _safe_slug(value: object, default: str = "agent") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.-]+", "-", text)
    text = text.strip("-._")
    return text or default


def write_mcp_startup_guide(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    tool_profile: str,
    agent: str,
) -> dict[str, str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    project_path = Path(project_dir).expanduser().resolve()
    safe_agent = _safe_slug(agent, default="generic")
    payload = {
        "version": 1,
        "agent": safe_agent,
        "project_dir": str(project_path),
        "db_path": str(project_path / "vault.db"),
        "mcp_server": {
            "command": "vault-mcp",
            "args": [
                "--project-dir",
                str(project_path),
                "--tool-profile",
                tool_profile,
            ],
            "tool_profile": tool_profile,
        },
        "startup_sequence": [
            {
                "tool": "vault_update_status",
                "arguments": {
                    "read_status": True,
                    "agent_id": safe_agent,
                },
                "fallback_arguments": {
                    "latest_version": "",
                    "check_pypi": False,
                    "write_status": False,
                    "agent_id": safe_agent,
                },
                "purpose": "Read installed version, local Agent registry, shared/private vault paths, and startup commands.",
            },
            {
                "tool": "vault_automation_handoff",
                "arguments": {
                    "source": "auto",
                    "handoff_path": "",
                },
                "purpose": "Read the latest compact handoff when one exists.",
                "result_contract": {
                    "read_first": [
                        "fleet_health_content",
                        "review_summary_content",
                        "learning_health_content",
                        "content",
                    ],
                    "fleet_health_content": "Shared multi-Agent automation health preface when present.",
                    "review_summary_content": "The 5% human-review card deck when present.",
                    "learning_health_content": "Dashboard-safe feedback learning health when present.",
                    "content": "Selected cycle/inbox handoff content.",
                    "missing_ok": True,
                },
            },
            {
                "tool": "vault_search",
                "arguments": {
                    "query": "<user task or handoff keyword>",
                    "limit": 5,
                    "compact": True,
                },
                "purpose": "Search only when the handoff or task needs more context.",
            },
            {
                "tool": "vault_read_range",
                "arguments": {
                    "knowledge_id": "<id from search>",
                    "line_start": 1,
                    "line_end": 20,
                },
                "purpose": "Read bounded evidence before citing Vault memory.",
            },
            {
                "tool": "vault_memory_propose",
                "arguments": {
                    "title": "<short durable lesson>",
                    "content": "<reviewable memory>",
                    "reason": "<why this is worth remembering>",
                },
                "purpose": "Propose new durable memory as a candidate, not active knowledge.",
            },
        ],
        "safety": {
            "local_stdio_only": True,
            "check_pypi_default": False,
            "handoff_read_only": True,
            "auto_promote_memory": False,
            "read_raw_transcripts_by_default": False,
            "read_existing_update_status_first": True,
        },
    }
    json_path = out / "mcp-startup.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    readme_path = out / "README-mcp-startup.md"
    readme_path.write_text(
        "\n".join(
            [
                "# MCP Startup Guide",
                "",
                "Use this guide when an MCP-capable Agent connects to this Vault project.",
                "",
                "Server:",
                "",
                "```bash",
                f"vault-mcp --project-dir {shlex.quote(str(project_path))} --tool-profile {shlex.quote(tool_profile)}",
                "```",
                "",
                "Startup sequence:",
                "",
                f"1. `vault_update_status` with `read_status=true` and `agent_id={safe_agent}`",
                "2. `vault_automation_handoff`",
                "   - If `fleet_health_content` is present, read it before the main `content` handoff.",
                "   - If `review_summary_content` is present, read it before deeper reports.",
                "   - If `learning_health_content` is present, use it as the learning loop status.",
                "3. `vault_search` only when more context is needed",
                "4. `vault_read_range` before citing memory",
                "5. `vault_memory_propose` for new durable lessons",
                "",
                "Default safety:",
                "",
                "- first read the existing machine status file; if it is missing, call `vault_update_status` without `read_status`",
                "- keep `check_pypi=false` unless the user asks for a live update check",
                "- handoff reads are read-only and stay under `reports/automation`",
                "- handoff may include `fleet_health_content`; treat it as the shared multi-Agent startup health preface",
                "- handoff may include `review_summary_content`; treat it as the smallest human-review card deck",
                "- handoff may include `learning_health_content`; treat it as dashboard-safe learning status",
                "- do not read raw transcript contents by default",
                "- do not auto-promote memory",
                "- tool profiles reduce schema size but are not an authorization boundary",
                "",
                f"Machine-readable startup file: `{json_path.name}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"json": str(json_path), "readme": str(readme_path)}


def write_update_status_templates(
    *,
    output_dir: str | Path,
    agent: str = "generic",
    vault_executable: str = "vault",
    interval_minutes: int = 60,
) -> dict[str, str]:
    from vault.agent_registry import update_status_path

    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    safe_agent = _safe_slug(agent, default="generic")
    status_path = update_status_path()
    write_command = [vault_executable, "update-status", "--write-status", "--json"]
    read_command = [vault_executable, "update-status", "--read-status", "--agent", safe_agent, "--json"]
    focus_command = [vault_executable, "update-status", "--agent", safe_agent, "--json"]
    contract = {
        "version": 1,
        "agent": safe_agent,
        "status_path": str(status_path),
        "read_command": shell_join(read_command),
        "write_command": shell_join(write_command),
        "focus_command": shell_join(focus_command),
        "mcp_read": {
            "tool": "vault_update_status",
            "arguments": {"read_status": True, "agent_id": safe_agent},
        },
        "mcp_fallback": {
            "tool": "vault_update_status",
            "arguments": {"latest_version": "", "check_pypi": False, "write_status": False, "agent_id": safe_agent},
        },
        "mcp_doctor": {
            "tool": "vault_update_status",
            "arguments": {"doctor": True, "agent_id": safe_agent, "max_status_age_minutes": interval_minutes},
        },
        "mcp_write": {
            "tool": "vault_update_status",
            "arguments": {"write_status": True, "check_pypi": False},
        },
        "safety": {
            "metadata_only": True,
            "check_pypi_default": False,
            "auto_upgrade": False,
            "shared_machine_status": True,
        },
    }
    contract_path = out / "update-status-contract.json"
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    cron_path = out / "update-status.cron"
    cron_path.write_text(
        "\n".join(
            [
                "# Vault-for-LLM local Agent update status",
                f"*/{max(1, int(interval_minutes))} * * * * {shell_join(write_command)} >> $HOME/.vault-for-llm/update-status.log 2>&1",
                "",
            ]
        ),
        encoding="utf-8",
    )

    launchagent_path = out / "update-status.launchagent.plist"
    launchagent_path.write_text(
        render_launchagent_plist(
            command=write_command,
            label="com.zycaskevin.vault-for-llm.update-status",
            interval_minutes=interval_minutes,
            log_basename="update-status",
        ),
        encoding="utf-8",
    )

    refresh_script_path = out / "refresh-update-status.sh"
    refresh_script_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env sh",
                "set -eu",
                "",
                f"VAULT=${{VAULT:-{shlex.quote(vault_executable)}}}",
                "",
                "\"$VAULT\" update-status --write-status --json >/dev/null",
                f"\"$VAULT\" update-status --doctor --max-status-age-minutes {max(1, int(interval_minutes))} --json",
                "",
            ]
        ),
        encoding="utf-8",
    )
    refresh_script_path.chmod(0o755)

    rollout_path = out / "README-agent-update-rollout.md"
    rollout_path.write_text(
        "\n".join(
            [
                "# Agent Update Rollout",
                "",
                "Use this when one local runtime upgrades Vault-for-LLM and the other runtimes need to notice.",
                "",
                "After an upgrade or reinstall, refresh the shared machine notice:",
                "",
                "```bash",
                f"sh {shlex.quote(str(refresh_script_path))}",
                "```",
                "",
                "Manual equivalent:",
                "",
                "```bash",
                shell_join(write_command),
                f"{vault_executable} update-status --doctor --max-status-age-minutes {max(1, int(interval_minutes))}",
                "```",
                "",
                "What the doctor checks:",
                "",
                "- `update-status.json` exists",
                "- the notice is fresh enough for this install pack",
                "- every registered Agent appears in `agent_update_notices`",
                "- no registered Agent is behind the current runtime or latest known version",
                "",
                "Agents should still read with their own runtime id:",
                "",
                "```bash",
                shell_join(read_command),
                "```",
                "",
                "This is not an auto-upgrader. It is a shared local notice and a health check.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    readme_path = out / "README-update-status.md"
    readme_path.write_text(
        "\n".join(
            [
                "# Agent Update Status",
                "",
                "This install pack lets multiple local Agent runtimes share one Vault-for-LLM update notice.",
                "",
                "Shared status file:",
                "",
                f"- `{status_path}`",
                "",
                "Read existing status without recomputing:",
                "",
                "```bash",
                shell_join(read_command),
                "```",
                "",
                "Write fresh local status without contacting PyPI:",
                "",
                "```bash",
                shell_join(write_command),
                "```",
                "",
                "MCP startup:",
                "",
                f"1. call `vault_update_status` with `read_status=true` and `agent_id={safe_agent}`",
                "2. if the result has `missing=true`, call `vault_update_status` with `check_pypi=false`",
                "3. call `vault_update_status` with `doctor=true` after an upgrade or when status freshness is unclear",
                "4. only set `check_pypi=true` when the user asks for a live online version check",
                "",
                "Safety:",
                "",
                "- this is metadata only: versions, registered Agents, vault paths, and handoff commands",
                "- it is not an auto-upgrader",
                "- one updated runtime can write the status; other runtimes can read it",
                "- each runtime should pass its own `agent_id` to get `current_agent_notice` and `startup_checklist`",
                "- install or upgrade each Agent environment explicitly",
                "",
                f"Cron example: `{cron_path.name}`",
                f"LaunchAgent example: `{launchagent_path.name}`",
                f"Refresh script: `{refresh_script_path.name}`",
                f"Rollout guide: `{rollout_path.name}`",
                f"Machine-readable contract: `{contract_path.name}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "contract": str(contract_path),
        "readme": str(readme_path),
        "cron": str(cron_path),
        "launchagent": str(launchagent_path),
        "refresh_script": str(refresh_script_path),
        "rollout_readme": str(rollout_path),
    }


def write_agent_adapter_startup_templates(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    tool_profile: str,
    agent: str,
    vault_executable: str = "vault",
) -> dict[str, str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    project_path = Path(project_dir).expanduser().resolve()
    safe_agent = _safe_slug(agent, default="generic")
    read_status_command = [
        vault_executable,
        "update-status",
        "--read-status",
        "--agent",
        safe_agent,
        "--json",
    ]
    fallback_status_command = [
        vault_executable,
        "update-status",
        "--agent",
        safe_agent,
        "--json",
    ]
    handoff_command = [
        vault_executable,
        "automation",
        "handoff",
        "--project-dir",
        str(project_path),
    ]
    mcp_command = [
        "vault-mcp",
        "--project-dir",
        str(project_path),
        "--tool-profile",
        tool_profile,
    ]
    startup_sequence = [
        {
            "name": "read_update_status",
            "cli": shell_join(read_status_command),
            "mcp": {
                "tool": "vault_update_status",
                "arguments": {"read_status": True, "agent_id": safe_agent},
            },
            "fallback": {
                "cli": shell_join(fallback_status_command),
                "mcp": {
                    "tool": "vault_update_status",
                    "arguments": {
                        "latest_version": "",
                        "check_pypi": False,
                        "write_status": False,
                        "agent_id": safe_agent,
                    },
                },
            },
        },
        {
            "name": "read_automation_handoff",
            "cli": shell_join(handoff_command),
            "mcp": {
                "tool": "vault_automation_handoff",
                "arguments": {"source": "auto", "handoff_path": ""},
            },
            "result_contract": {
                "read_first": [
                    "fleet_health_content",
                    "review_summary_content",
                    "learning_health_content",
                    "content",
                ],
                "fleet_health_content": "Shared multi-Agent automation health preface when present.",
                "review_summary_content": "The 5% human-review card deck when present.",
                "learning_health_content": "Dashboard-safe feedback learning health when present.",
                "content": "Selected cycle/inbox handoff content.",
                "do_not_replace_content": True,
            },
        },
        {
            "name": "check_update_distribution_when_needed",
            "mcp": {
                "tool": "vault_update_status",
                "arguments": {"doctor": True, "agent_id": safe_agent, "max_status_age_minutes": 24 * 60},
            },
        },
        {
            "name": "search_when_needed",
            "mcp": {
                "tool": "vault_search",
                "arguments": {"query": "<task keyword>", "limit": 5, "compact": True},
            },
        },
        {
            "name": "read_bounded_evidence",
            "mcp": {
                "tool": "vault_read_range",
                "arguments": {"knowledge_id": "<id>", "line_start": 1, "line_end": 40},
            },
        },
        {
            "name": "propose_durable_memory",
            "mcp": {
                "tool": "vault_memory_propose",
                "arguments": {
                    "title": "<durable lesson>",
                    "content": "<reviewable memory>",
                    "reason": "<why this should be remembered>",
                },
            },
        },
    ]
    adapters = {
        "codex": {
            "file": "codex-startup.md",
            "where_to_put": "project AGENTS.md or Codex project instructions",
            "note": "Use before touching code so Codex sees update status and handoff context first.",
        },
        "claude_code": {
            "file": "claude-code-startup.md",
            "where_to_put": "project CLAUDE.md or Claude Code project memory",
            "note": "Keep Vault startup short: status, handoff, then bounded searches.",
        },
        "openclaw": {
            "file": "openclaw-startup.md",
            "where_to_put": "OpenClaw workspace bootstrap or skill instructions",
            "note": "If a compact latest-context.md exists, read it before deeper Vault searches.",
        },
        "hermes": {
            "file": "hermes-startup.md",
            "where_to_put": "Hermes profile AGENTS.md, MEMORY.md, or runtime bootstrap",
            "note": "Point each profile at the same shared project vault but keep profile identity private.",
        },
    }
    contract = {
        "version": 1,
        "agent": safe_agent,
        "project_dir": str(project_path),
        "db_path": str(project_path / "vault.db"),
        "tool_profile": tool_profile,
        "mcp_server": {
            "command": "vault-mcp",
            "args": [
                "--project-dir",
                str(project_path),
                "--tool-profile",
                tool_profile,
            ],
        },
        "commands": {
            "read_update_status": shell_join(read_status_command),
            "fallback_update_status": shell_join(fallback_status_command),
            "handoff": shell_join(handoff_command),
            "mcp_server": shell_join(mcp_command),
        },
        "startup_sequence": startup_sequence,
        "handoff_contract": {
            "source": "auto",
            "fleet_health_preface": True,
            "review_summary_preface": True,
            "learning_health_preface": True,
            "read_order": [
                "fleet_health_content",
                "review_summary_content",
                "learning_health_content",
                "content",
            ],
            "content_contract": "content remains the selected cycle/inbox handoff; startup prefaces are attached separately when present.",
        },
        "adapters": adapters,
        "safety": {
            "auto_upgrade": False,
            "check_pypi_default": False,
            "read_raw_transcripts_by_default": False,
            "auto_promote_memory": False,
            "candidate_first_memory": True,
            "bounded_reads_before_citation": True,
            "tool_profile_is_not_auth": True,
        },
    }
    contract_path = out / "adapter-startup-contract.json"
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    runtime_playbook = {
        "version": 1,
        "purpose": "Keep multiple local Agent runtimes on the same machine pointed at one shared Vault update notice.",
        "agent": safe_agent,
        "project_dir": str(project_path),
        "status_file": "~/.vault-for-llm/update-status.json",
        "startup_rule": [
            "Read existing update status for this runtime.",
            "If status is missing, compute local status without a live PyPI check.",
            "Run doctor mode when freshness or rollout state is unclear.",
            "Read automation handoff before searching deeper memory.",
            "If handoff includes fleet_health_content, read that shared health preface before the main handoff content.",
            "If handoff includes review_summary_content, read the 5% human-review cards before deeper reports.",
            "If handoff includes learning_health_content, use it as the learning loop status.",
            "Search/read only when the task needs more context.",
        ],
        "after_upgrade_rule": [
            "Only the runtime that upgraded Vault should refresh the shared notice.",
            "Run vault update-status --write-status.",
            "Run vault agent doctor or MCP doctor=true.",
            "Other runtimes should read their focused notice and restart or upgrade only with user approval.",
        ],
        "mcp": {
            "read": {
                "tool": "vault_update_status",
                "arguments": {"read_status": True, "agent_id": safe_agent},
            },
            "doctor": {
                "tool": "vault_update_status",
                "arguments": {"doctor": True, "agent_id": safe_agent, "max_status_age_minutes": 24 * 60},
            },
            "handoff": {
                "tool": "vault_automation_handoff",
                "arguments": {"source": "auto", "handoff_path": ""},
                "read_order": [
                    "fleet_health_content",
                    "review_summary_content",
                    "learning_health_content",
                    "content",
                ],
            },
        },
        "cli": {
            "read": shell_join(read_status_command),
            "fallback": shell_join(fallback_status_command),
            "refresh": f"{vault_executable} update-status --write-status",
            "doctor": f"{vault_executable} agent doctor",
            "handoff": shell_join(handoff_command),
        },
        "runtime_targets": {
            "codex": "project AGENTS.md or Codex project instructions",
            "claude_code": "project CLAUDE.md or Claude Code project memory",
            "openclaw": "OpenClaw workspace bootstrap or skill instructions",
            "hermes": "Hermes profile AGENTS.md, MEMORY.md, or runtime bootstrap",
        },
        "safety": {
            "auto_upgrade": False,
            "auto_restart": False,
            "check_pypi_default": False,
            "one_shared_project_vault": True,
            "private_agent_memory_stays_private": True,
            "fleet_health_preface_read_only": True,
            "review_summary_preface_read_only": True,
            "learning_health_preface_read_only": True,
        },
    }
    runtime_playbook_path = out / "runtime-update-playbook.json"
    runtime_playbook_path.write_text(
        json.dumps(runtime_playbook, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    runtime_playbook_readme_path = out / "README-runtime-update-playbook.md"
    runtime_playbook_readme_path.write_text(
        "\n".join(
            [
                "# Runtime Update Playbook",
                "",
                "Use this when Codex, Claude Code, OpenClaw, Hermes Agent, or another local runtime shares the same Vault project.",
                "",
                "Goal: every runtime can discover the same project vault, the same update notice, and the same compact handoff without each runtime inventing its own memory database.",
                "",
                "Startup rule:",
                "",
                f"1. Read this runtime's focused status: `{shell_join(read_status_command)}`.",
                f"2. If missing, compute local status without a live PyPI check: `{shell_join(fallback_status_command)}`.",
                "3. If the notice is stale, missing Agents, or upgrade state is unclear, run MCP doctor: `vault_update_status` with `doctor=true` and this runtime's `agent_id`.",
                f"4. Read the compact handoff: `{shell_join(handoff_command)}`.",
                "   If it includes `fleet_health_content`, read that shared health preface before the individual `content` handoff.",
                "   If it includes `review_summary_content`, read those 5% review cards before deeper reports.",
                "   If it includes `learning_health_content`, use it as the learning loop status.",
                "5. Search/read only when the task needs deeper context.",
                "",
                "After one runtime upgrades Vault:",
                "",
                f"1. Refresh the shared notice: `{vault_executable} update-status --write-status`.",
                f"2. Verify rollout health: `{vault_executable} agent doctor`.",
                "3. MCP-only runtimes use `vault_update_status` with `doctor=true` instead.",
                "4. Other runtimes may restart or upgrade only with user approval.",
                "",
                "Where to paste the matching startup template:",
                "",
                "| Runtime | Generated file | Suggested target |",
                "|---|---|---|",
                "| Codex | `codex-startup.md` | project `AGENTS.md` or Codex project instructions |",
                "| Claude Code | `claude-code-startup.md` | project `CLAUDE.md` or Claude Code project memory |",
                "| OpenClaw | `openclaw-startup.md` | OpenClaw workspace bootstrap or skill instructions |",
                "| Hermes Agent | `hermes-startup.md` | Hermes profile `AGENTS.md`, `MEMORY.md`, or runtime bootstrap |",
                "",
                "Safety boundary:",
                "",
                "- This playbook is not an auto-upgrader.",
                "- It does not restart another runtime.",
                "- It does not read raw transcripts by default.",
                "- It assumes one shared project vault plus optional private per-Agent memory.",
                "- Fleet health is a read-only startup preface, not private memory.",
                "- It keeps `check_pypi=false` unless the user asks for a live network version check.",
                "",
                f"Machine-readable playbook: `{runtime_playbook_path.name}`",
                "",
            ]
        ),
        encoding="utf-8",
    )

    def adapter_markdown(title: str, *, target: str, note: str, openclaw: bool = False) -> str:
        lines = [
            f"# {title}",
            "",
            f"Target location: {target}.",
            "",
            note,
            "",
            "Startup order:",
            "",
            f"1. Read update status: `{shell_join(read_status_command)}`.",
            f"2. If status is missing, run bounded fallback: `{shell_join(fallback_status_command)}`.",
            f"3. Read the compact automation handoff: `{shell_join(handoff_command)}`.",
            "4. If handoff includes `fleet_health_content`, read that shared health preface before the main handoff.",
            "5. If handoff includes `review_summary_content`, read those 5% review cards before deeper reports.",
            "6. If handoff includes `learning_health_content`, use it as the learning loop status.",
            "7. Run MCP doctor when status freshness or runtime updates are unclear.",
            "8. Search only when the task needs more context.",
            "9. Use bounded reads before citing memory.",
            "10. Propose durable lessons as candidates; do not auto-promote them.",
            "",
            "MCP server:",
            "",
            "```bash",
            shell_join(mcp_command),
            "```",
            "",
            "First MCP calls:",
            "",
            f"- `vault_update_status` with `read_status=true`, `agent_id={safe_agent}`.",
            "- `vault_update_status` with `doctor=true` when checking multi-Agent update distribution.",
            "- `vault_automation_handoff` with `source=auto`.",
            "  Read `fleet_health_content`, `review_summary_content`, and `learning_health_content` before the selected `content` handoff when present.",
            "- `vault_search` and `vault_read_range` only when needed.",
            "- `vault_memory_propose` for new durable lessons.",
            "",
            "Safety rules:",
            "",
            "- Do not auto-upgrade another Agent runtime.",
            "- Do not read raw transcript contents by default.",
            "- Do not auto-promote memory.",
            "- Treat tool profiles as schema-size filters, not permissions.",
            "",
        ]
        if openclaw:
            lines.extend(
                [
                    "OpenClaw note:",
                    "",
                    "- If `latest-context.md` exists in the workspace, read that compact context first.",
                    "- Use Vault search only when the compact context is not enough.",
                    "",
                ]
            )
        lines.extend(
            [
                f"Machine-readable contract: `{contract_path.name}`",
                "",
            ]
        )
        return "\n".join(lines)

    files: dict[str, str] = {
        "contract": str(contract_path),
        "runtime_playbook": str(runtime_playbook_path),
        "runtime_playbook_readme": str(runtime_playbook_readme_path),
    }
    for adapter_id, adapter in adapters.items():
        filename = adapter["file"]
        path = out / filename
        path.write_text(
            adapter_markdown(
                {
                    "codex": "Codex Startup Template",
                    "claude_code": "Claude Code Startup Template",
                    "openclaw": "OpenClaw Startup Template",
                    "hermes": "Hermes Agent Startup Template",
                }[adapter_id],
                target=adapter["where_to_put"],
                note=adapter["note"],
                openclaw=adapter_id == "openclaw",
            ),
            encoding="utf-8",
        )
        files[adapter_id] = str(path)

    readme_path = out / "README-agent-adapters.md"
    readme_path.write_text(
        "\n".join(
            [
                "# Agent Adapter Startup Templates",
                "",
                "Use these templates when one machine has multiple Agent runtimes connected to the same Vault project.",
                "",
                "The shared rule is simple: update-status -> automation handoff -> search/read/propose.",
                "The handoff is startup-aware: read `fleet_health_content`, `review_summary_content`, and `learning_health_content` first when present, then the selected cycle/inbox `content`.",
                "",
                "Generated files:",
                "",
                "- `codex-startup.md`",
                "- `claude-code-startup.md`",
                "- `openclaw-startup.md`",
                "- `hermes-startup.md`",
                "- `adapter-startup-contract.json`",
                "- `runtime-update-playbook.json`",
                "- `README-runtime-update-playbook.md`",
                "",
                "What each Agent should do at startup:",
                "",
                f"1. Read the shared update notice with `{shell_join(read_status_command)}`.",
                f"2. If no notice exists, run `{shell_join(fallback_status_command)}` without a live PyPI check.",
                f"3. Read `{shell_join(handoff_command)}` for the latest compact memory automation handoff.",
                "4. If the handoff includes fleet health, read that shared health preface before the individual handoff.",
                "5. If the handoff includes review-summary cards, read them before deeper reports.",
                "6. If the handoff includes learning-health, use it as the learning loop status.",
                "7. Use MCP doctor when checking whether every local runtime has the fresh shared notice.",
                "8. Search only when the task or handoff needs more detail.",
                "9. Read bounded evidence before citing memory.",
                "10. Propose new durable memory as candidates.",
                "",
                "Safety boundary:",
                "",
                "- no auto-upgrade",
                "- no raw transcript reads by default",
                "- no automatic memory promotion",
                "- one shared project vault can coexist with private per-Agent identity/profile memory",
                "- tool profiles reduce token/schema size but are not an authorization boundary",
                "",
                f"MCP server command: `{shell_join(mcp_command)}`",
                f"Runtime update playbook: `{runtime_playbook_readme_path.name}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    files["readme"] = str(readme_path)
    return files


def _runtime_template_filename(runtime: str) -> tuple[str, str]:
    normalized = _safe_slug(str(runtime or ""), default="")
    normalized = normalized.replace("_", "-")
    if normalized not in {"codex", "claude-code", "openclaw", "hermes"}:
        allowed = ", ".join(["codex", "claude-code", "openclaw", "hermes"])
        raise ValueError(f"unknown runtime '{runtime}' (expected one of: {allowed})")
    return normalized, f"{normalized}-startup.md"


def _runtime_template_markers(runtime: str) -> tuple[str, str]:
    normalized, _ = _runtime_template_filename(runtime)
    label = f"Vault-for-LLM runtime startup: {normalized}"
    return f"<!-- BEGIN {label} -->", f"<!-- END {label} -->"


def _replace_marked_block(existing: str, *, begin: str, end: str, block: str) -> tuple[str, str]:
    pattern = re.compile(
        rf"{re.escape(begin)}.*?{re.escape(end)}",
        flags=re.DOTALL,
    )
    if pattern.search(existing):
        return pattern.sub(block, existing, count=1), "replace"
    if existing.strip():
        separator = "\n\n"
        if existing.endswith("\n"):
            separator = "\n"
        return existing + separator + block + "\n", "append"
    return block + "\n", "create"


def install_runtime_template(
    *,
    runtime: str,
    template_dir: str | Path,
    target_path: str | Path,
    apply: bool = False,
    backup: bool = True,
) -> dict[str, Any]:
    """Preview or apply a generated runtime startup template to a target file.

    The write is intentionally conservative: dry-run by default, marker based,
    and backup-on-write for existing files.
    """
    normalized, filename = _runtime_template_filename(runtime)
    template_path = Path(template_dir).expanduser().resolve() / filename
    target = Path(target_path).expanduser().resolve()
    if not template_path.exists() or not template_path.is_file():
        raise FileNotFoundError(
            f"runtime template not found: {template_path}; run vault setup-agent first"
        )
    template = template_path.read_text(encoding="utf-8").strip()
    begin, end = _runtime_template_markers(normalized)
    block = "\n".join([begin, template, end])
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    new_content, action = _replace_marked_block(existing, begin=begin, end=end, block=block)
    changed = new_content != existing
    backup_path = ""

    if apply and changed:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and backup:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            backup_file = target.with_name(f"{target.name}.bak.{stamp}")
            backup_file.write_text(existing, encoding="utf-8")
            backup_path = str(backup_file)
        target.write_text(new_content, encoding="utf-8")

    return {
        "ok": True,
        "runtime": normalized,
        "source": str(template_path),
        "target": str(target),
        "target_exists": target.exists(),
        "apply": bool(apply),
        "changed": changed,
        "action": action if changed else "noop",
        "backup": backup_path,
        "marker_begin": begin,
        "marker_end": end,
        "next_step": (
            "Review the target file and restart/reload the runtime if needed."
            if apply
            else "Re-run with --apply to write the marked startup block."
        ),
    }


EXPECTED_HANDOFF_READ_ORDER = [
    "fleet_health_content",
    "review_summary_content",
    "learning_health_content",
    "content",
]
STARTUP_DOCTOR_JSON_FILES = {
    "mcp_startup": "mcp-startup.json",
    "adapter_contract": "adapter-startup-contract.json",
    "runtime_playbook": "runtime-update-playbook.json",
}
STARTUP_DOCTOR_TEMPLATE_FILES = {
    "codex": "codex-startup.md",
    "claude_code": "claude-code-startup.md",
    "openclaw": "openclaw-startup.md",
    "hermes": "hermes-startup.md",
}
STARTUP_DOCTOR_README_FILES = {
    "mcp_readme": "README-mcp-startup.md",
    "adapter_readme": "README-agent-adapters.md",
    "runtime_playbook_readme": "README-runtime-update-playbook.md",
}


def _startup_doctor_check(checks: list[dict[str, Any]], *, name: str, status: str, path: Path, detail: str) -> None:
    checks.append(
        {
            "name": name,
            "status": status,
            "path": str(path),
            "detail": detail,
        }
    )


def _startup_doctor_json(path: Path, checks: list[dict[str, Any]], *, name: str) -> dict[str, Any]:
    if not path.exists():
        _startup_doctor_check(checks, name=name, status="fail", path=path, detail="missing required file")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _startup_doctor_check(checks, name=name, status="fail", path=path, detail=f"invalid JSON: {exc}")
        return {}
    if not isinstance(payload, dict):
        _startup_doctor_check(checks, name=name, status="fail", path=path, detail="JSON root must be an object")
        return {}
    _startup_doctor_check(checks, name=name, status="pass", path=path, detail="file exists and is valid JSON")
    return payload


def _has_handoff_read_order(value: object) -> bool:
    return list(value or []) == EXPECTED_HANDOFF_READ_ORDER


def startup_contract_doctor(template_dir: str | Path) -> dict[str, Any]:
    """Check whether setup-agent startup files use the current fleet-aware contract."""
    root = Path(template_dir).expanduser().resolve()
    checks: list[dict[str, Any]] = []

    mcp_path = root / STARTUP_DOCTOR_JSON_FILES["mcp_startup"]
    adapter_path = root / STARTUP_DOCTOR_JSON_FILES["adapter_contract"]
    playbook_path = root / STARTUP_DOCTOR_JSON_FILES["runtime_playbook"]
    mcp = _startup_doctor_json(mcp_path, checks, name="mcp_startup_json")
    adapter = _startup_doctor_json(adapter_path, checks, name="adapter_startup_contract_json")
    playbook = _startup_doctor_json(playbook_path, checks, name="runtime_update_playbook_json")

    sequence = mcp.get("startup_sequence") if isinstance(mcp.get("startup_sequence"), list) else []
    tools = [step.get("tool") for step in sequence[:2] if isinstance(step, dict)]
    _startup_doctor_check(
        checks,
        name="mcp_startup_order",
        status="pass" if tools == ["vault_update_status", "vault_automation_handoff"] else "fail",
        path=mcp_path,
        detail=(
            "starts with update-status then automation handoff"
            if tools == ["vault_update_status", "vault_automation_handoff"]
            else "expected first two tools to be vault_update_status then vault_automation_handoff"
        ),
    )
    mcp_handoff = sequence[1] if len(sequence) > 1 and isinstance(sequence[1], dict) else {}
    mcp_read_order = (mcp_handoff.get("result_contract") or {}).get("read_first") if isinstance(mcp_handoff, dict) else []
    _startup_doctor_check(
        checks,
        name="mcp_handoff_result_contract",
        status="pass" if _has_handoff_read_order(mcp_read_order) else "fail",
        path=mcp_path,
        detail=(
            "handoff result_contract reads fleet_health_content before content"
            if _has_handoff_read_order(mcp_read_order)
            else "missing startup preface handoff result_contract read order"
        ),
    )

    adapter_order = (adapter.get("handoff_contract") or {}).get("read_order")
    _startup_doctor_check(
        checks,
        name="adapter_handoff_contract",
        status="pass" if _has_handoff_read_order(adapter_order) else "fail",
        path=adapter_path,
        detail=(
            "adapter contract is fleet-aware"
            if _has_handoff_read_order(adapter_order)
            else "missing handoff_contract.read_order startup prefaces -> content"
        ),
    )
    adapter_sequence = adapter.get("startup_sequence") if isinstance(adapter.get("startup_sequence"), list) else []
    adapter_handoff = next(
        (step for step in adapter_sequence if isinstance(step, dict) and step.get("name") == "read_automation_handoff"),
        {},
    )
    adapter_result = adapter_handoff.get("result_contract") if isinstance(adapter_handoff, dict) else {}
    adapter_result_order = (adapter_result or {}).get("read_first") if isinstance(adapter_result, dict) else []
    adapter_do_not_replace = bool((adapter_result or {}).get("do_not_replace_content")) if isinstance(adapter_result, dict) else False
    adapter_result_ok = _has_handoff_read_order(adapter_result_order) and adapter_do_not_replace
    _startup_doctor_check(
        checks,
        name="adapter_handoff_step_result_contract",
        status="pass" if adapter_result_ok else "fail",
        path=adapter_path,
        detail=(
            "adapter handoff step preserves selected content and reads startup prefaces first"
            if adapter_result_ok
            else "read_automation_handoff step is missing startup-preface result_contract"
        ),
    )

    playbook_order = ((playbook.get("mcp") or {}).get("handoff") or {}).get("read_order")
    playbook_safety = playbook.get("safety") or {}
    playbook_prefaces_read_only = all(
        bool(playbook_safety.get(name))
        for name in (
            "fleet_health_preface_read_only",
            "review_summary_preface_read_only",
            "learning_health_preface_read_only",
        )
    )
    playbook_ok = _has_handoff_read_order(playbook_order) and playbook_prefaces_read_only
    _startup_doctor_check(
        checks,
        name="runtime_playbook_handoff_contract",
        status="pass" if playbook_ok else "fail",
        path=playbook_path,
        detail=(
            "runtime playbook reads startup prefaces first and marks them read-only"
            if playbook_ok
            else "runtime playbook is missing startup-preface read order or read-only safety flag"
        ),
    )

    for name, filename in STARTUP_DOCTOR_TEMPLATE_FILES.items():
        path = root / filename
        if not path.exists():
            _startup_doctor_check(checks, name=f"{name}_startup_template", status="fail", path=path, detail="missing runtime template")
            continue
        text = path.read_text(encoding="utf-8")
        ok = (
            "fleet_health_content" in text
            and "review_summary_content" in text
            and "learning_health_content" in text
            and "vault_automation_handoff" in text
        )
        _startup_doctor_check(
            checks,
            name=f"{name}_startup_template",
            status="pass" if ok else "fail",
            path=path,
            detail=(
                "runtime template names the startup-preface handoff contract"
                if ok
                else "runtime template is missing startup-preface handoff guidance"
            ),
        )

    for name, filename in STARTUP_DOCTOR_README_FILES.items():
        path = root / filename
        if not path.exists():
            _startup_doctor_check(checks, name=name, status="warn", path=path, detail="missing generated README")
            continue
        text = path.read_text(encoding="utf-8")
        ok = (
            "fleet_health_content" in text
            and "review_summary_content" in text
            and "learning_health_content" in text
        )
        _startup_doctor_check(
            checks,
            name=name,
            status="pass" if ok else "warn",
            path=path,
            detail=(
                "README documents startup-preface handoff"
                if ok
                else "README is missing startup-preface guidance; regenerate setup files for clearer guidance"
            ),
        )

    fail_count = sum(1 for check in checks if check["status"] == "fail")
    warn_count = sum(1 for check in checks if check["status"] == "warn")
    status = "fail" if fail_count else "warn" if warn_count else "pass"
    recommended_actions: list[str] = []
    if fail_count:
        recommended_actions.append(
            "Re-run `vault setup-agent` for this project, then re-apply runtime templates where needed."
        )
    if warn_count:
        recommended_actions.append("Review generated README files; regenerate the install pack if startup guidance is stale.")
    if not recommended_actions:
        recommended_actions.append("No startup contract action needed.")
    return {
        "ok": fail_count == 0,
        "action": "startup-doctor",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "template_dir": str(root),
        "status": status,
        "summary": {
            "check_count": len(checks),
            "pass": sum(1 for check in checks if check["status"] == "pass"),
            "warn": warn_count,
            "fail": fail_count,
        },
        "checks": checks,
        "missing_files": [check["path"] for check in checks if "missing" in check["detail"].lower()],
        "outdated_files": [
            check["path"]
            for check in checks
            if check["status"] in {"fail", "warn"} and "missing" not in check["detail"].lower()
        ],
        "recommended_actions": recommended_actions,
        "next_action": recommended_actions[0],
        "safety": {
            "read_only": True,
            "does_not_touch_runtime_files": True,
            "does_not_read_private_memory": True,
            "does_not_promote_memory": True,
        },
    }
