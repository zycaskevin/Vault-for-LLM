"""Agent setup schedule, sync, and remote-reader template helpers."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

from vault import __version__
from vault.agent_setup_supabase import _normalize_setup_language


VALID_SYNC_TARGETS = {"none", "cron", "launchagent", "n8n", "realtime", "all"}
VALID_REMOTE_READER_TARGETS = {"none", "shell", "n8n", "coze", "all"}
VALID_AUTOMATION_MODES = {"conservative", "balanced", "autonomous"}
VALID_AUTOMATION_COMMANDS = {"run", "cycle"}
DEFAULT_SUPABASE_SYNC_INTERVAL_MINUTES = 24 * 60
DEFAULT_AUTOMATION_INTERVAL_MINUTES = 24 * 60

def _normalize_sync_targets(targets: str | list[str]) -> set[str]:
    if isinstance(targets, str):
        selected = {part.strip() for part in targets.split(",") if part.strip()}
    else:
        selected = {str(part).strip() for part in targets if str(part).strip()}
    if not selected or "none" in selected:
        return set()
    if "all" in selected:
        expanded = {"cron", "launchagent", "n8n"}
        if "realtime" in selected:
            expanded.add("realtime")
        return expanded
    unknown = selected - VALID_SYNC_TARGETS
    if unknown:
        raise ValueError(f"unknown sync target(s): {', '.join(sorted(unknown))}")
    return selected


def shell_join(parts: list[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)


def obsidian_sync_command(
    *,
    project_dir: str | Path,
    obsidian_vault: str | Path,
    vault_executable: str = "vault",
) -> list[str]:
    return [
        vault_executable,
        "import",
        "obsidian",
        "--vault",
        str(Path(obsidian_vault).expanduser()),
        "--project-dir",
        str(Path(project_dir).expanduser()),
        "--compile",
        "--no-embed",
    ]


def render_cron_template(*, command: list[str], interval_minutes: int = 15) -> str:
    interval = max(1, int(interval_minutes))
    return "\n".join(
        [
            "# Vault-for-LLM Obsidian sync",
            f"*/{interval} * * * * {shell_join(command)} >> $HOME/.vault-for-llm/obsidian-sync.log 2>&1",
            "",
        ]
    )


def render_daily_cron_template(*, command: list[str], hour: int = 3, minute: int = 0) -> str:
    safe_hour = max(0, min(23, int(hour)))
    safe_minute = max(0, min(59, int(minute)))
    return "\n".join(
        [
            "# Vault-for-LLM daily sync",
            f"{safe_minute} {safe_hour} * * * {shell_join(command)} >> $HOME/.vault-for-llm/supabase-sync.log 2>&1",
            "",
        ]
    )


def _parse_daily_time(value: str | None, *, default_hour: int = 3, default_minute: int = 0) -> tuple[int, int]:
    text = str(value or "").strip()
    if not text:
        return default_hour, default_minute
    if ":" not in text:
        try:
            return max(0, min(23, int(text))), 0
        except ValueError:
            return default_hour, default_minute
    hour_text, minute_text = text.split(":", 1)
    try:
        hour = max(0, min(23, int(hour_text)))
        minute = max(0, min(59, int(minute_text)))
    except ValueError:
        return default_hour, default_minute
    return hour, minute


def _format_daily_time(value: str | None) -> str:
    hour, minute = _parse_daily_time(value)
    return f"{hour:02d}:{minute:02d}"


def render_launchagent_plist(
    *,
    command: list[str],
    label: str = "com.zycaskevin.vault-for-llm.obsidian-sync",
    interval_minutes: int = 15,
    log_basename: str = "obsidian-sync",
) -> str:
    interval_seconds = max(60, int(interval_minutes) * 60)
    program = command[0]
    args = command[1:]
    arg_lines = "\n".join(f"    <string>{_xml_escape(arg)}</string>" for arg in args)
    safe_log_basename = str(log_basename or "vault-sync").strip().replace("/", "-")
    stdout_path = Path.home() / ".vault-for-llm" / f"{safe_log_basename}.log"
    stderr_path = Path.home() / ".vault-for-llm" / f"{safe_log_basename}.err.log"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{_xml_escape(label)}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{_xml_escape(program)}</string>
{arg_lines}
  </array>
  <key>StartInterval</key>
  <integer>{interval_seconds}</integer>
  <key>StandardOutPath</key>
  <string>{_xml_escape(str(stdout_path))}</string>
  <key>StandardErrorPath</key>
  <string>{_xml_escape(str(stderr_path))}</string>
</dict>
</plist>
"""


def _xml_escape(value: object) -> str:
    text = str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def render_n8n_workflow(*, command: list[str], interval_minutes: int = 15) -> str:
    workflow = {
        "name": "Vault-for-LLM Obsidian Sync",
        "nodes": [
            {
                "parameters": {
                    "rule": {
                        "interval": [{"field": "minutes", "minutesInterval": max(1, int(interval_minutes))}]
                    }
                },
                "id": "schedule",
                "name": "Every interval",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [0, 0],
            },
            {
                "parameters": {"command": shell_join(command)},
                "id": "vault-obsidian-sync",
                "name": "Vault Obsidian Sync",
                "type": "n8n-nodes-base.executeCommand",
                "typeVersion": 1,
                "position": [260, 0],
            },
        ],
        "connections": {
            "Every interval": {"main": [[{"node": "Vault Obsidian Sync", "type": "main", "index": 0}]]}
        },
        "active": False,
        "settings": {"executionOrder": "v1"},
    }
    return json.dumps(workflow, ensure_ascii=False, indent=2) + "\n"


def render_n8n_automation_workflow(*, command: list[str], interval_minutes: int = DEFAULT_AUTOMATION_INTERVAL_MINUTES) -> str:
    workflow = {
        "name": "Vault-for-LLM Memory Automation",
        "nodes": [
            {
                "parameters": {
                    "rule": {
                        "interval": [{"field": "minutes", "minutesInterval": max(1, int(interval_minutes))}]
                    }
                },
                "id": "schedule",
                "name": "Every interval",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [0, 0],
            },
            {
                "parameters": {"command": shell_join(command)},
                "id": "vault-memory-automation",
                "name": "Vault Memory Automation",
                "type": "n8n-nodes-base.executeCommand",
                "typeVersion": 1,
                "position": [280, 0],
            },
        ],
        "connections": {
            "Every interval": {"main": [[{"node": "Vault Memory Automation", "type": "main", "index": 0}]]}
        },
        "active": False,
        "settings": {"executionOrder": "v1"},
    }
    return json.dumps(workflow, ensure_ascii=False, indent=2) + "\n"


def render_n8n_remote_reader_workflow(
    *,
    agent_id: str,
    query: str = "deployment SOP",
    vault_executable: str = "vault",
) -> str:
    command = [
        vault_executable,
        "remote",
        "search",
        query,
        "--agent-id",
        agent_id,
        "--json",
    ]
    workflow = {
        "name": "Vault-for-LLM Remote Reader",
        "nodes": [
            {
                "parameters": {},
                "id": "manual-trigger",
                "name": "Manual trigger",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [0, 0],
            },
            {
                "parameters": {"command": shell_join(command)},
                "id": "vault-remote-search",
                "name": "Vault Remote Search",
                "type": "n8n-nodes-base.executeCommand",
                "typeVersion": 1,
                "position": [260, 0],
            },
        ],
        "connections": {
            "Manual trigger": {"main": [[{"node": "Vault Remote Search", "type": "main", "index": 0}]]}
        },
        "active": False,
        "settings": {"executionOrder": "v1"},
    }
    return json.dumps(workflow, ensure_ascii=False, indent=2) + "\n"


def render_coze_supabase_openapi_template(*, agent_id: str) -> str:
    spec = {
        "openapi": "3.1.0",
        "info": {
            "title": "Vault-for-LLM Supabase Remote Reader",
            "version": __version__,
            "description": "Read safe Vault-for-LLM memory summaries through the Supabase vault_search_readable RPC.",
        },
        "servers": [
            {
                "url": "https://YOUR_PROJECT.supabase.co/rest/v1",
                "description": "Replace with your Supabase Project URL plus /rest/v1.",
            }
        ],
        "paths": {
            "/rpc/vault_search_readable": {
                "post": {
                    "operationId": "vaultRemoteSearch",
                    "summary": "Search reviewed Vault-for-LLM remote memory summaries",
                    "description": "Use an anon/authenticated key. Do not expose SUPABASE_SERVICE_ROLE_KEY to Coze or browser clients.",
                    "security": [{"SupabaseApiKey": []}, {"SupabaseBearer": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "p_agent_id": {"type": "string", "default": agent_id},
                                        "p_query": {"type": "string", "default": "deployment SOP"},
                                        "p_include_private": {"type": "boolean", "default": False},
                                        "p_max_sensitivity": {
                                            "type": "string",
                                            "enum": ["low", "medium", "high", "restricted"],
                                            "default": "medium",
                                        },
                                        "p_limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
                                    },
                                    "required": ["p_agent_id", "p_query"],
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Safe metadata and summary rows. This RPC intentionally does not return content_raw.",
                            "content": {"application/json": {"schema": {"type": "array", "items": {"type": "object"}}}},
                        }
                    },
                }
            }
        },
        "components": {
            "securitySchemes": {
                "SupabaseApiKey": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "apikey",
                    "description": "Use SUPABASE_ANON_KEY or an authenticated user token.",
                },
                "SupabaseBearer": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Use the same anon/authenticated token as a Bearer token.",
                },
            }
        },
    }
    return json.dumps(spec, ensure_ascii=False, indent=2) + "\n"


def supabase_sync_command(
    *,
    project_dir: str | Path,
    python_executable: str | Path | None = None,
    document_map: bool = True,
    health: bool = True,
    include_content: bool = False,
) -> list[str]:
    command = [
        str(python_executable or sys.executable),
        "-m",
        "scripts.sync_to_supabase",
        "--db",
        str(Path(project_dir).expanduser() / "vault.db"),
    ]
    if include_content:
        command.append("--include-content")
    if document_map:
        command.append("--document-map")
    if health:
        command.append("--health")
    return command


def supabase_realtime_sync_command(
    *,
    project_dir: str | Path,
    python_executable: str | Path | None = None,
    interval_seconds: int = 5,
    debounce_seconds: int = 10,
) -> list[str]:
    return [
        str(python_executable or sys.executable),
        "-m",
        "scripts.watch_supabase_sync",
        "--db",
        str(Path(project_dir).expanduser() / "vault.db"),
        "--interval-seconds",
        str(max(1, int(interval_seconds))),
        "--debounce-seconds",
        str(max(0, int(debounce_seconds))),
        "--sync-on-start",
        "--document-map",
        "--health",
    ]


def write_supabase_sync_templates(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    targets: str | list[str] = "all",
    interval_minutes: int = DEFAULT_SUPABASE_SYNC_INTERVAL_MINUTES,
    python_executable: str | Path | None = None,
) -> dict[str, str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    selected = _normalize_sync_targets(targets)
    command = supabase_sync_command(
        project_dir=project_dir,
        python_executable=python_executable,
    )
    realtime_command = supabase_realtime_sync_command(
        project_dir=project_dir,
        python_executable=python_executable,
        interval_seconds=max(5, min(int(interval_minutes or 5), 60)),
        debounce_seconds=10,
    )

    written: dict[str, str] = {}
    if "cron" in selected:
        path = out / "supabase-sync.cron"
        path.write_text(render_daily_cron_template(command=command), encoding="utf-8")
        written["cron"] = str(path)
    if "launchagent" in selected:
        path = out / "com.zycaskevin.vault-for-llm.supabase-sync.plist"
        path.write_text(
            render_launchagent_plist(
                command=command,
                label="com.zycaskevin.vault-for-llm.supabase-sync",
                interval_minutes=interval_minutes,
                log_basename="supabase-sync",
            ),
            encoding="utf-8",
        )
        written["launchagent"] = str(path)
    if "n8n" in selected:
        path = out / "n8n-supabase-sync.workflow.json"
        path.write_text(render_n8n_workflow(command=command, interval_minutes=interval_minutes), encoding="utf-8")
        written["n8n"] = str(path)
    if "realtime" in selected:
        path = out / "supabase-realtime-sync.sh"
        path.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env sh",
                    "set -eu",
                    "",
                    "# Near-realtime push sync. Local vault.db remains the source of truth.",
                    "# Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY on this trusted machine.",
                    shell_join(realtime_command),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        try:
            path.chmod(0o755)
        except OSError:
            pass
        written["realtime"] = str(path)

    readme = out / "README-supabase-sync.md"
    readme.write_text(
        "\n".join(
            [
                "# Vault-for-LLM Supabase Sync Templates",
                "",
                "Generated command:",
                "",
                f"```bash\n{shell_join(command)}\n```",
                "",
                "Review `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` before enabling any scheduled job.",
                "The local SQLite database remains the source of truth.",
                "Use `supabase-realtime-sync.sh` for near-realtime local-to-Supabase push sync.",
                "This is not bidirectional sync: Supabase remains a read copy unless you build a separate reviewed merge workflow.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    written["readme"] = str(readme)
    return written


def _normalize_automation_mode(mode: str | None) -> str:
    value = str(mode or "balanced").strip().lower()
    if value not in VALID_AUTOMATION_MODES:
        allowed = ", ".join(sorted(VALID_AUTOMATION_MODES))
        raise ValueError(f"unknown automation mode '{mode}' (expected one of: {allowed})")
    return value


def _normalize_automation_command(command: str | None) -> str:
    value = str(command or "cycle").strip().lower()
    if value not in VALID_AUTOMATION_COMMANDS:
        allowed = ", ".join(sorted(VALID_AUTOMATION_COMMANDS))
        raise ValueError(f"unknown automation command '{command}' (expected one of: {allowed})")
    return value


def automation_schedule_command(
    *,
    project_dir: str | Path,
    mode: str = "balanced",
    apply: bool = False,
    command: str = "cycle",
    vault_executable: str = "vault",
    write_workspace: bool = False,
    inbox_limit: int = 5,
    include_transcripts: bool = False,
    transcript_limit: int = 5,
    capture_transcripts: bool = False,
    capture_transcript_limit: int = 3,
) -> list[str]:
    normalized_command = _normalize_automation_command(command)
    command_args = [
        vault_executable,
        "automation",
        normalized_command,
        "--project-dir",
        str(Path(project_dir).expanduser()),
        "--mode",
        _normalize_automation_mode(mode),
        "--pretty",
    ]
    if apply:
        command_args.append("--apply")
    if normalized_command == "cycle" and write_workspace:
        command_args.append("--write-workspace")
        command_args.extend(["--inbox-limit", str(max(1, min(int(inbox_limit or 5), 50)))])
        if include_transcripts:
            command_args.extend(
                [
                    "--include-transcripts",
                    "--transcript-limit",
                    str(max(1, min(int(transcript_limit or 5), 20))),
                ]
            )
        if capture_transcripts:
            command_args.extend(
                [
                    "--capture-transcripts",
                    "--capture-transcript-limit",
                    str(max(1, min(int(capture_transcript_limit or 3), 20))),
                ]
            )
    return command_args


def automation_inbox_handoff_command(
    *,
    project_dir: str | Path,
    vault_executable: str = "vault",
    limit: int = 5,
    include_transcripts: bool = False,
    transcript_limit: int = 5,
) -> list[str]:
    command = [
        vault_executable,
        "automation",
        "inbox",
        "--project-dir",
        str(Path(project_dir).expanduser()),
        "--limit",
        str(max(1, min(int(limit or 5), 50))),
        "--write-handoff",
        "--pretty",
    ]
    if include_transcripts:
        command.extend(
            [
                "--include-transcripts",
                "--transcript-limit",
                str(max(1, min(int(transcript_limit or 5), 20))),
            ]
        )
    return command


def automation_learning_health_command(
    *,
    project_dir: str | Path,
    vault_executable: str = "vault",
) -> list[str]:
    return [
        vault_executable,
        "automation",
        "learning-health",
        "--project-dir",
        str(Path(project_dir).expanduser()),
        "--write-health",
        "--pretty",
    ]


def automation_review_summary_command(
    *,
    project_dir: str | Path,
    vault_executable: str = "vault",
) -> list[str]:
    return [
        vault_executable,
        "automation",
        "review-summary",
        "--project-dir",
        str(Path(project_dir).expanduser()),
        "--write-summary",
        "--pretty",
    ]


def memory_pipeline_command(
    *,
    project_dir: str | Path,
    vault_executable: str = "vault",
    transcript_limit: int = 3,
) -> list[str]:
    return [
        vault_executable,
        "memory",
        "pipeline",
        "--project-dir",
        str(Path(project_dir).expanduser()),
        "--write-candidates",
        "--transcript-limit",
        str(max(1, min(int(transcript_limit or 3), 20))),
        "--write-report",
        "--pretty",
    ]


def memory_reflection_command(
    *,
    project_dir: str | Path,
    vault_executable: str = "vault",
) -> list[str]:
    return [
        vault_executable,
        "memory",
        "reflection",
        "--project-dir",
        str(Path(project_dir).expanduser()),
        "--write-candidates",
        "--pretty",
    ]


def daily_report_command(
    *,
    project_dir: str | Path,
    vault_executable: str = "vault",
    language: str = "en",
) -> list[str]:
    return [
        vault_executable,
        "daily-report",
        "--project-dir",
        str(Path(project_dir).expanduser()),
        "--language",
        _normalize_setup_language(language),
        "--write-report",
        "--pretty",
    ]


def automation_schedule_with_inbox_command(
    *,
    project_dir: str | Path,
    mode: str = "balanced",
    apply: bool = False,
    command: str = "cycle",
    vault_executable: str = "vault",
    write_workspace: bool = False,
    inbox_limit: int = 5,
    include_transcripts: bool = False,
    transcript_limit: int = 5,
    capture_transcripts: bool = False,
    capture_transcript_limit: int = 3,
    write_daily_report: bool = False,
    language: str = "en",
) -> list[str]:
    primary = automation_schedule_command(
        project_dir=project_dir,
        mode=mode,
        apply=apply,
        command=command,
        vault_executable=vault_executable,
        write_workspace=write_workspace,
        inbox_limit=inbox_limit,
        include_transcripts=include_transcripts,
        transcript_limit=transcript_limit,
        capture_transcripts=False,
        capture_transcript_limit=capture_transcript_limit,
    )
    inbox = automation_inbox_handoff_command(
        project_dir=project_dir,
        vault_executable=vault_executable,
        include_transcripts=include_transcripts,
        transcript_limit=transcript_limit,
    )
    health = automation_learning_health_command(
        project_dir=project_dir,
        vault_executable=vault_executable,
    )
    review_summary = automation_review_summary_command(
        project_dir=project_dir,
        vault_executable=vault_executable,
    )
    pipeline = memory_pipeline_command(
        project_dir=project_dir,
        vault_executable=vault_executable,
        transcript_limit=capture_transcript_limit,
    )
    reflection = memory_reflection_command(
        project_dir=project_dir,
        vault_executable=vault_executable,
    )
    daily = daily_report_command(project_dir=project_dir, vault_executable=vault_executable, language=language)
    commands = [
        shell_join(pipeline),
        shell_join(reflection),
        shell_join(primary),
        shell_join(inbox),
        shell_join(review_summary),
        shell_join(health),
    ]
    if write_daily_report:
        commands.append(shell_join(daily))
    return [
        "sh",
        "-lc",
        " && ".join(commands),
    ]


def write_automation_schedule_templates(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    targets: str | list[str] = "all",
    interval_minutes: int = DEFAULT_AUTOMATION_INTERVAL_MINUTES,
    mode: str = "balanced",
    apply: bool = False,
    command: str = "cycle",
    vault_executable: str = "vault",
    write_workspace: bool = False,
    workspace_inbox_limit: int = 5,
    include_transcripts: bool = False,
    transcript_limit: int = 5,
    capture_transcripts: bool = False,
    capture_transcript_limit: int = 3,
    auto_promote_low_risk: bool = False,
    write_daily_report: bool = False,
    daily_report_time: str = "",
    language: str = "en",
) -> dict[str, str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    selected = _normalize_sync_targets(targets)
    normalized_mode = _normalize_automation_mode(mode)
    normalized_command = _normalize_automation_command(command)
    command_args = automation_schedule_command(
        project_dir=project_dir,
        mode=normalized_mode,
        apply=apply,
        command=normalized_command,
        vault_executable=vault_executable,
        write_workspace=write_workspace,
        inbox_limit=workspace_inbox_limit,
        include_transcripts=include_transcripts,
        transcript_limit=transcript_limit,
        capture_transcripts=capture_transcripts,
        capture_transcript_limit=capture_transcript_limit,
    )
    scheduled_args = automation_schedule_with_inbox_command(
        project_dir=project_dir,
        mode=normalized_mode,
        apply=apply,
        command=normalized_command,
        vault_executable=vault_executable,
        write_workspace=write_workspace,
        inbox_limit=workspace_inbox_limit,
        include_transcripts=include_transcripts,
        transcript_limit=transcript_limit,
        capture_transcripts=capture_transcripts,
        capture_transcript_limit=capture_transcript_limit,
        write_daily_report=write_daily_report,
        language=language,
    )
    inbox_args = automation_inbox_handoff_command(
        project_dir=project_dir,
        vault_executable=vault_executable,
        include_transcripts=include_transcripts,
        transcript_limit=transcript_limit,
    )
    health_args = automation_learning_health_command(
        project_dir=project_dir,
        vault_executable=vault_executable,
    )
    review_summary_args = automation_review_summary_command(
        project_dir=project_dir,
        vault_executable=vault_executable,
    )
    pipeline_args = memory_pipeline_command(
        project_dir=project_dir,
        vault_executable=vault_executable,
        transcript_limit=capture_transcript_limit,
    )
    reflection_args = memory_reflection_command(
        project_dir=project_dir,
        vault_executable=vault_executable,
    )
    daily_report_args = daily_report_command(
        project_dir=project_dir,
        vault_executable=vault_executable,
        language=language,
    )
    handoff_args = [
        vault_executable,
        "automation",
        "handoff",
        "--project-dir",
        str(Path(project_dir).expanduser()),
    ]

    written: dict[str, str] = {}
    if "cron" in selected:
        path = out / "memory-automation.cron"
        interval = max(1, int(interval_minutes))
        hour, minute = _parse_daily_time(daily_report_time)
        schedule = f"*/{interval} * * * *" if interval < 60 else f"{minute} {hour} * * *"
        path.write_text(
            "\n".join(
                [
                    "# Vault-for-LLM memory automation",
                    f"{schedule} {shell_join(scheduled_args)} >> $HOME/.vault-for-llm/memory-automation.log 2>&1",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        written["cron"] = str(path)
    if "launchagent" in selected:
        path = out / "com.zycaskevin.vault-for-llm.memory-automation.plist"
        path.write_text(
            render_launchagent_plist(
                command=scheduled_args,
                label="com.zycaskevin.vault-for-llm.memory-automation",
                interval_minutes=interval_minutes,
                log_basename="memory-automation",
            ),
            encoding="utf-8",
        )
        written["launchagent"] = str(path)
    if "n8n" in selected:
        path = out / "n8n-memory-automation.workflow.json"
        path.write_text(
            render_n8n_automation_workflow(command=scheduled_args, interval_minutes=interval_minutes),
            encoding="utf-8",
        )
        written["n8n"] = str(path)

    readme = out / "README-memory-automation.md"
    readme.write_text(
        "\n".join(
            [
                "# Vault-for-LLM Memory Automation Schedule",
                "",
                "Generated command:",
                "",
                f"```bash\n{shell_join(command_args)}\n```",
                "",
                "Scheduled templates run this command and then write an inbox handoff:",
                "",
                f"```bash\n{shell_join(inbox_args)}\n```",
                "",
                "Scheduled templates also write the shortest human-review card deck:",
                "",
                f"```bash\n{shell_join(review_summary_args)}\n```",
                "",
                "Scheduled templates also run the automatic memory pipeline and reflection pass before the handoff:",
                "",
                f"```bash\n{shell_join(pipeline_args)}\n{shell_join(reflection_args)}\n```",
                "",
                "Scheduled templates also write the compact learning-health dashboard:",
                "",
                f"```bash\n{shell_join(health_args)}\n```",
                "",
                "Scheduled templates can also write the human daily report:",
                "",
                f"```bash\n{shell_join(daily_report_args)}\n```",
                "",
                "Next agent startup handoff:",
                "",
                f"```bash\n{shell_join(handoff_args)}\n```",
                "",
                "Run this at the start of the next agent session. It is read-only and prefers",
                "`reports/automation/cycle-latest.md` before falling back to JSON handoffs.",
                "",
                "Recommended first step:",
                "",
                "```bash",
                f"vault automation plan --project-dir {shlex.quote(str(Path(project_dir).expanduser()))} --mode {normalized_mode} --write-policy --pretty",
                "```",
                "",
                "Safety defaults:",
                "",
                f"- scheduled command: `vault automation {normalized_command}`",
                f"- mode: `{normalized_mode}`",
                f"- apply reversible archival: `{str(bool(apply)).lower()}`",
                "- `cycle` first writes a bounded learning policy from reviewed candidate outcomes, then runs automation",
                "- automation never hard-deletes memory",
                "- expired memories with usage are protected and sent to human review",
                "- scheduled runs write `reports/automation/inbox-latest.json` as the next-agent handoff",
                "- scheduled runs write `reports/automation/review-summary-latest.json` and `.md` as the 5% human-review card deck",
                "- scheduled runs write `reports/automation/learning-health-latest.json` and `.md` as the short learning dashboard",
                f"- scheduled runs write `reports/daily/daily-report-latest.json` and `.md`: `{str(bool(write_daily_report)).lower()}`",
                f"- daily report time for cron templates: `{_format_daily_time(daily_report_time)}`",
                "- scheduled runs write session lessons as candidate memories through `vault memory pipeline`",
                "- scheduled runs write `reports/automation/pipeline-latest.json` and `.md` as the memory-ingestion receipt",
                "- scheduled runs write reflection review cards through `vault memory reflection`",
                f"- scheduled cycle workspace: `{str(bool(write_workspace and normalized_command == 'cycle')).lower()}`",
                "- cycle workspace path: `reports/automation/cycle-latest.json` when enabled",
                "- cycle workspace Markdown: `reports/automation/cycle-latest.md` when enabled",
                "- next agent startup command: `vault automation handoff`",
                f"- uncaptured transcript hints in scheduled handoff: `{str(bool(include_transcripts)).lower()}`",
                "- transcript discovery is metadata-only and does not read transcript contents",
                f"- auto-capture transcript candidates: `{str(bool(capture_transcripts)).lower()}`",
                "- transcript capture reads selected transcript contents and writes candidates only; it never promotes active memory",
                f"- low-risk auto-promote policy: `{str(bool(auto_promote_low_risk)).lower()}`",
                "- low-risk auto-promote requires `automation_policy.yaml` plus `--apply`; private, sensitive, duplicate, weak, or sourceless candidates stay in review",
                "",
                "Review `automation_policy.yaml` before enabling a scheduled job.",
                "Keep the Python virtualenv and project directory in stable paths, not `/tmp`.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    written["readme"] = str(readme)
    return written


def _normalize_remote_reader_targets(raw: str | list[str] | None) -> set[str]:
    if raw is None:
        return set()
    if isinstance(raw, str):
        parts = [part.strip().lower() for part in raw.split(",") if part.strip()]
    else:
        parts = [str(part).strip().lower() for part in raw if str(part).strip()]
    if not parts or "none" in parts:
        return set()
    unknown = [part for part in parts if part not in VALID_REMOTE_READER_TARGETS]
    if unknown:
        allowed = ", ".join(sorted(VALID_REMOTE_READER_TARGETS))
        raise ValueError(f"unknown remote reader template target '{unknown[0]}' (expected one of: {allowed})")
    if "all" in parts:
        return {"shell", "n8n", "coze"}
    return set(parts)


def write_remote_reader_templates(
    *,
    output_dir: str | Path,
    agent: str,
    targets: str | list[str] = "all",
    query: str = "deployment SOP",
    vault_executable: str = "vault",
) -> dict[str, str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    selected = _normalize_remote_reader_targets(targets)
    if not selected:
        return {}

    safe_agent = str(agent or "generic")
    safe_query = str(query or "deployment SOP")
    written: dict[str, str] = {}

    if "shell" in selected:
        path = out / "remote-reader-smoke.sh"
        path.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env sh",
                    "set -eu",
                    ": \"${SUPABASE_URL:?Set SUPABASE_URL first}\"",
                    ": \"${SUPABASE_ANON_KEY:?Set SUPABASE_ANON_KEY first}\"",
                    shell_join(
                        [
                            vault_executable,
                            "remote",
                            "smoke",
                            "--agent-id",
                            safe_agent,
                            "--query",
                            safe_query,
                            "--json",
                        ]
                    ),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        written["shell"] = str(path)

    if "n8n" in selected:
        path = out / "n8n-remote-reader.workflow.json"
        path.write_text(
            render_n8n_remote_reader_workflow(
                agent_id=safe_agent,
                query=safe_query,
                vault_executable=vault_executable,
            ),
            encoding="utf-8",
        )
        written["n8n"] = str(path)

    if "coze" in selected:
        path = out / "coze-supabase-vault-openapi.json"
        path.write_text(render_coze_supabase_openapi_template(agent_id=safe_agent), encoding="utf-8")
        written["coze"] = str(path)

    env_path = out / "remote-reader.env.example"
    env_path.write_text(
        "\n".join(
            [
                "# Vault-for-LLM remote reader credentials",
                "# Use an anon/authenticated key. Do not put SUPABASE_SERVICE_ROLE_KEY in hosted agents.",
                "SUPABASE_URL=https://YOUR_PROJECT.supabase.co",
                "SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY",
                f"VAULT_AGENT_ID={safe_agent}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    written["env_example"] = str(env_path)

    readme = out / "README-remote-reader.md"
    readme.write_text(
        "\n".join(
            [
                "# Vault-for-LLM Remote Reader Templates",
                "",
                "Use these templates after Supabase sync and `docs/supabase_read_policy.sql` are applied.",
                "",
                "Remote readers are for safe summaries and metadata. They should not receive the service role key.",
                "",
                "## Required credentials",
                "",
                "- `SUPABASE_URL`: Supabase Project URL",
                "- `SUPABASE_ANON_KEY`: anon/authenticated key for read-only RPC access",
                f"- Agent ID: `{safe_agent}`",
                "",
                "## Smoke test",
                "",
                f"```bash\nvault remote smoke --agent-id {shlex.quote(safe_agent)} --query {shlex.quote(safe_query)} --json\n```",
                "",
                "Expected result: `ok=true` and a `vault_search_readable` payload. If `ok=false`, follow the `next_action` message.",
                "",
                "## Reader flow",
                "",
                "```text",
                "vault remote search -> vault remote map -> vault remote read",
                "```",
                "",
                "Coze should call the Supabase RPC directly through the OpenAPI template. n8n can either run the CLI template or call the same RPC through HTTP nodes.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    written["readme"] = str(readme)
    return written


def write_sync_templates(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    obsidian_vault: str | Path,
    targets: str | list[str] = "all",
    interval_minutes: int = 15,
    vault_executable: str = "vault",
) -> dict[str, str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    selected = _normalize_sync_targets(targets)
    command = obsidian_sync_command(
        project_dir=project_dir,
        obsidian_vault=obsidian_vault,
        vault_executable=vault_executable,
    )

    written: dict[str, str] = {}
    if "cron" in selected:
        path = out / "obsidian-sync.cron"
        path.write_text(render_cron_template(command=command, interval_minutes=interval_minutes), encoding="utf-8")
        written["cron"] = str(path)
    if "launchagent" in selected:
        path = out / "com.zycaskevin.vault-for-llm.obsidian-sync.plist"
        path.write_text(
            render_launchagent_plist(command=command, interval_minutes=interval_minutes),
            encoding="utf-8",
        )
        written["launchagent"] = str(path)
    if "n8n" in selected:
        path = out / "n8n-obsidian-sync.workflow.json"
        path.write_text(render_n8n_workflow(command=command, interval_minutes=interval_minutes), encoding="utf-8")
        written["n8n"] = str(path)

    readme = out / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Vault-for-LLM Obsidian Sync Templates",
                "",
                "Generated command:",
                "",
                f"```bash\n{shell_join(command)}\n```",
                "",
                "Review paths before enabling any scheduled job.",
                "The import is incremental: Vault tracks Obsidian source hashes in `.vault/obsidian-import-manifest.json`, updates changed notes, and reports missing source notes without pruning raw copies unless `--prune-missing` is used.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    written["readme"] = str(readme)
    return written
