"""Agent setup startup, update-status, and runtime adapter helpers."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

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
                        "pipeline_receipt_content",
                        "review_summary_content",
                        "learning_health_content",
                        "content",
                    ],
                    "fleet_health_content": "Shared multi-Agent automation health preface when present.",
                    "pipeline_receipt_content": "The latest automatic memory-ingestion receipt when present.",
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
                "   - If `pipeline_receipt_content` is present, read it before review-summary cards.",
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
                "- handoff may include `pipeline_receipt_content`; treat it as the latest memory-ingestion receipt",
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
                    "pipeline_receipt_content",
                    "review_summary_content",
                    "learning_health_content",
                    "content",
                ],
                "fleet_health_content": "Shared multi-Agent automation health preface when present.",
                "pipeline_receipt_content": "The latest automatic memory-ingestion receipt when present.",
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
            "pipeline_receipt_preface": True,
            "review_summary_preface": True,
            "learning_health_preface": True,
            "read_order": [
                "fleet_health_content",
                "pipeline_receipt_content",
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
            "If handoff includes pipeline_receipt_content, read the memory-ingestion receipt before review cards.",
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
                    "pipeline_receipt_content",
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
            "pipeline_receipt_preface_read_only": True,
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
                "   If it includes `pipeline_receipt_content`, read the memory-ingestion receipt before review cards.",
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
            "5. If handoff includes `pipeline_receipt_content`, read the memory-ingestion receipt before review cards.",
            "6. If handoff includes `review_summary_content`, read those 5% review cards before deeper reports.",
            "7. If handoff includes `learning_health_content`, use it as the learning loop status.",
            "8. Run MCP doctor when status freshness or runtime updates are unclear.",
            "9. Search only when the task needs more context.",
            "10. Use bounded reads before citing memory.",
            "11. Propose durable lessons as candidates; do not auto-promote them.",
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
            "  Read `fleet_health_content`, `pipeline_receipt_content`, `review_summary_content`, and `learning_health_content` before the selected `content` handoff when present.",
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
                "The handoff is startup-aware: read `fleet_health_content`, `pipeline_receipt_content`, `review_summary_content`, and `learning_health_content` first when present, then the selected cycle/inbox `content`.",
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
