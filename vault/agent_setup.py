"""Agent-friendly setup wizard and sync template helpers."""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from vault import __version__
from vault.agent_registry import register_agent
from vault.agent_setup_templates import (
    DEFAULT_AUTOMATION_INTERVAL_MINUTES,
    DEFAULT_SUPABASE_SYNC_INTERVAL_MINUTES,
    VALID_AUTOMATION_COMMANDS,
    VALID_AUTOMATION_MODES,
    VALID_REMOTE_READER_TARGETS,
    VALID_SYNC_TARGETS,
    _normalize_automation_command,
    _normalize_automation_mode,
    _normalize_remote_reader_targets,
    _normalize_sync_targets,
    automation_inbox_handoff_command,
    automation_learning_health_command,
    automation_schedule_command,
    automation_schedule_with_inbox_command,
    obsidian_sync_command,
    render_coze_supabase_openapi_template,
    render_cron_template,
    render_daily_cron_template,
    render_launchagent_plist,
    render_n8n_automation_workflow,
    render_n8n_remote_reader_workflow,
    render_n8n_workflow,
    shell_join,
    supabase_sync_command,
    write_automation_schedule_templates,
    write_remote_reader_templates,
    write_supabase_sync_templates,
    write_sync_templates,
)
from vault.agent_setup_startup import (
    EXPECTED_HANDOFF_READ_ORDER,
    STARTUP_DOCTOR_JSON_FILES,
    STARTUP_DOCTOR_README_FILES,
    STARTUP_DOCTOR_TEMPLATE_FILES,
    _has_handoff_read_order,
    _replace_marked_block,
    _runtime_template_filename,
    _runtime_template_markers,
    _startup_doctor_check,
    _startup_doctor_json,
    install_runtime_template,
    startup_contract_doctor,
    write_agent_adapter_startup_templates,
    write_mcp_startup_guide,
    write_update_status_templates,
)
from vault.agent_setup_supabase import (
    SUPABASE_READ_POLICY_SQL,
    SUPABASE_SETUP_DOC_URL,
    VALID_SETUP_LANGUAGES,
    VALID_SUPABASE_SETUP_MODES,
    _normalize_setup_language,
    _normalize_supabase_setup_mode,
    render_supabase_setup_guide,
    write_supabase_setup_guide,
)
from vault.db import VaultDB
from vault.import_obsidian import sync_obsidian_vault


DEFAULT_FEATURES = ["core", "mcp"]
VALID_FEATURES = {
    "core",
    "mcp",
    "obsidian_import",
    "semantic",
    "supabase",
    "headroom",
    "memory_agents",
    "dev",
}
VALID_VALIDATION_PACK_TARGETS = {"none", "remote", "n8n", "coze", "all"}
VALID_AGENT_ROLES = {"work", "profile", "care", "dream", "remote", "automation", "observer"}
VALID_MEMORY_LAYOUTS = {"shared", "private", "hybrid"}
VALID_RUNTIME_TEMPLATES = {"codex", "claude-code", "claude_code", "openclaw", "hermes"}
PYPI_EXTRA_FEATURES = {"mcp", "semantic", "supabase", "dev"}
VALID_EMBEDDING_MODELS = {"zh", "en", "mix"}


def default_project_dir(scope: str, *, agent: str = "generic") -> Path:
    home = Path.home()
    if scope == "shared":
        return home / "Vaults" / "project-memory"
    if scope == "domain":
        return home / "Vaults" / "domain-memory"
    if scope == "temporary":
        import tempfile

        return Path(tempfile.mkdtemp(prefix="vault-agent-setup-"))
    if agent == "openclaw":
        return home / ".openclaw" / "workspace" / "vault-project"
    return home / ".vault-for-llm" / "agent-private"


def default_agent_private_dir(agent: str = "generic") -> Path:
    root = os.environ.get("VAULT_AGENT_PRIVATE_ROOT", "").strip()
    base = Path(root).expanduser() if root else Path.home() / "Vaults" / "agents"
    return base / _safe_slug(agent, default="generic") / "private-memory"


def normalize_features(raw: str | list[str] | None) -> list[str]:
    if raw is None:
        features = list(DEFAULT_FEATURES)
    elif isinstance(raw, str):
        features = [part.strip() for part in raw.split(",") if part.strip()]
    else:
        features = [str(part).strip() for part in raw if str(part).strip()]

    if "core" not in features:
        features.insert(0, "core")

    normalized: list[str] = []
    for feature in features:
        if feature not in VALID_FEATURES:
            allowed = ", ".join(sorted(VALID_FEATURES))
            raise ValueError(f"unknown optional feature '{feature}' (expected one of: {allowed})")
        if feature not in normalized:
            normalized.append(feature)
    return normalized


def ensure_project(project_dir: str | Path) -> Path:
    project_path = Path(project_dir).expanduser().resolve()
    project_path.mkdir(parents=True, exist_ok=True)
    for dirname in ["raw", "compiled", "L0-identity", "L1-core-facts", "L2-context", "L3-knowledge"]:
        (project_path / dirname).mkdir(parents=True, exist_ok=True)

    with VaultDB(str(project_path / "vault.db")) as db:
        db.set_config("embedding_provider", db.get_config("embedding_provider", "auto"))
        db.set_config("embedding_model", db.get_config("embedding_model", "mix"))
        db.set_config("embedding_dim", db.get_config("embedding_dim", "384"))

    gitignore = project_path / ".gitignore"
    lines = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    for line in ["# Vault-for-LLM", "*.db", "__pycache__/", ".cache/"]:
        if line not in lines:
            lines.append(line)
    gitignore.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return project_path


def compile_project(project_dir: str | Path, *, allow_private: bool = False) -> dict[str, Any]:
    from vault.compiler import VaultCompiler

    project_path = Path(project_dir).expanduser().resolve()
    db = VaultDB(str(project_path / "vault.db"))
    db.connect()
    try:
        compiler = VaultCompiler(project_path, db=db, embed_provider=None, allow_private=allow_private)
        with contextlib.redirect_stdout(io.StringIO()):
            return compiler.compile(dry_run=False)
    finally:
        db.close()


def write_automation_policy_template(
    *,
    project_dir: str | Path,
    mode: str = "balanced",
    auto_promote_low_risk: bool = False,
) -> dict[str, Any]:
    from vault.automation import POLICY_FILE, default_policy

    project = Path(project_dir).expanduser().resolve()
    path = project / POLICY_FILE
    existed = path.exists()
    if existed:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"{POLICY_FILE} must contain a YAML object")
        policy = default_policy(str(loaded.get("mode") or mode))
        policy = _deep_merge_dict(policy, loaded)
    else:
        policy = default_policy(mode)

    policy["mode"] = _normalize_automation_mode(str(policy.get("mode") or mode))
    if auto_promote_low_risk:
        policy["auto_promote_low_risk_candidates"] = True
        policy.setdefault("auto_promote_allowed_sources", ["session_capture"])
        policy.setdefault("auto_promote_allowed_memory_types", ["session_lesson"])
        policy.setdefault("auto_promote_allowed_scopes", ["project", "shared", "public"])
        policy.setdefault("auto_promote_allowed_sensitivities", ["low"])
        policy.setdefault("auto_promote_min_trust", 0.65)
        policy.setdefault("auto_promote_max_per_run", 3)
        policy.setdefault("auto_promote_requires_source_ref", True)

    backup_path = ""
    if existed:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        backup = path.with_name(f"{path.name}.{stamp}.bak")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        backup_path = str(backup)
    path.write_text(yaml.safe_dump(policy, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return {
        "path": str(path),
        "backup_path": backup_path,
        "status": "updated" if existed else "created",
        "mode": policy["mode"],
        "auto_promote_low_risk_candidates": bool(policy.get("auto_promote_low_risk_candidates", False)),
        "next_action": "Review automation_policy.yaml before enabling scheduled --apply runs.",
    }


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
    if normalized == "profile":
        return {"scope": "private", "max_sensitivity": "high", "tool_profile": "review", "can_write_candidates": True}
    if normalized == "care":
        return {"scope": "private", "max_sensitivity": "medium", "tool_profile": "core", "can_write_candidates": True}
    if normalized == "dream":
        return {"scope": "private", "max_sensitivity": "medium", "tool_profile": "maintenance", "can_write_candidates": True}
    if normalized == "remote":
        return {"scope": "shared", "max_sensitivity": "medium", "tool_profile": "remote", "can_write_candidates": False}
    if normalized == "automation":
        return {"scope": "shared", "max_sensitivity": "low", "tool_profile": "core", "can_write_candidates": False}
    if normalized == "observer":
        return {"scope": "shared", "max_sensitivity": "low", "tool_profile": "core", "can_write_candidates": False}
    return {"scope": "shared", "max_sensitivity": "medium", "tool_profile": "core", "can_write_candidates": True}


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
        defaults = _role_defaults(role)
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
                "scope": scope,
                "max_sensitivity": max_sensitivity,
                "tool_profile": str(item.get("tool_profile") or defaults["tool_profile"]),
                "can_write_candidates": bool(item.get("can_write_candidates", defaults["can_write_candidates"])),
                "private_memory": bool(item.get("private_memory", role in {"profile", "care", "dream"})),
                "remote_reader": bool(item.get("remote_reader", role in {"remote", "automation", "observer"})),
            }
        )
    return normalized


def render_agent_access_matrix(roster: list[dict[str, Any]]) -> str:
    lines = [
        "# Vault-for-LLM Agent Access Matrix",
        "",
        "Use this file as the reviewed roster for multi-agent memory sharing.",
        "",
        "| Agent | Role | Scope | Max sensitivity | Tool profile | Candidate write | Private memory | Remote reader |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in roster:
        lines.append(
            "| {agent_id} | {role} | {scope} | {max_sensitivity} | {tool_profile} | {can_write_candidates} | {private_memory} | {remote_reader} |".format(
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


def render_memory_agents_guide(
    *,
    project_dir: str | Path,
    agent: str,
    language: str = "en",
) -> str:
    project_path = Path(project_dir).expanduser()
    safe_language = _normalize_setup_language(language)
    if safe_language == "zh-Hant":
        lines = [
            "# Vault-for-LLM 記憶 Agent 設定",
            "",
            "這份文件給 Profile / Dream / Forgetting agent 使用。",
            "",
            "預設政策：",
            "",
            "- Profile agent 預設只產生候選記憶，不直接寫入 active memory。",
            "- Dream agent 預設只產生 report，不直接刪除或 promote。",
            "- Forgetting agent 預設只建議 archive、expire、merge 或降權，不自動刪除。",
            "- 原始私密對話不同步到 shared vault 或 Supabase，除非使用者明確同意。",
            "- 共享人格側寫只允許 reviewed summary，不共享 raw private interaction。",
            "",
            "建議生命週期：",
            "",
            "```text",
            "capture -> candidate -> review -> active -> dream -> consolidate -> archive/expire",
            "```",
            "",
            "建議 metadata：",
            "",
            "```yaml",
            "scope: private | project | shared | public",
            "sensitivity: low | medium | high | restricted",
            f"owner_agent: {agent}",
            "allowed_agents: []",
            "status: candidate | reviewed | active | archived",
            "memory_type: user_profile | care_summary | dream_report | forgetting_suggestion",
            "expires_at: null",
            "```",
            "",
            "建議執行方式：",
            "",
            f"- Project vault: `{project_path}`",
            "- Profile agent：整理 L0/L1/L2 側寫候選，等待使用者或 trusted agent review。",
            "- Dream agent：定期執行 `vault dream`，輸出整理報告。",
            "- Forgetting agent：根據 dream report 產生 archive/expire 建議，不直接刪除。",
        ]
    elif safe_language == "zh-CN":
        lines = [
            "# Vault-for-LLM 记忆 Agent 设置",
            "",
            "这份文件给 Profile / Dream / Forgetting agent 使用。",
            "",
            "默认政策：",
            "",
            "- Profile agent 默认只产生候选记忆，不直接写入 active memory。",
            "- Dream agent 默认只产生 report，不直接删除或 promote。",
            "- Forgetting agent 默认只建议 archive、expire、merge 或降权，不自动删除。",
            "- 原始私密对话不同步到 shared vault 或 Supabase，除非用户明确同意。",
            "- 共享人格侧写只允许 reviewed summary，不共享 raw private interaction。",
            "",
            "建议生命周期：",
            "",
            "```text",
            "capture -> candidate -> review -> active -> dream -> consolidate -> archive/expire",
            "```",
            "",
            "建议 metadata：",
            "",
            "```yaml",
            "scope: private | project | shared | public",
            "sensitivity: low | medium | high | restricted",
            f"owner_agent: {agent}",
            "allowed_agents: []",
            "status: candidate | reviewed | active | archived",
            "memory_type: user_profile | care_summary | dream_report | forgetting_suggestion",
            "expires_at: null",
            "```",
            "",
            "建议执行方式：",
            "",
            f"- Project vault: `{project_path}`",
            "- Profile agent：整理 L0/L1/L2 侧写候选，等待用户或 trusted agent review。",
            "- Dream agent：定期执行 `vault dream`，输出整理报告。",
            "- Forgetting agent：根据 dream report 产生 archive/expire 建议，不直接删除。",
        ]
    else:
        lines = [
            "# Vault-for-LLM Memory Agents",
            "",
            "Use this guide for Profile / Dream / Forgetting agents.",
            "",
            "Default policy:",
            "",
            "- Profile agents produce candidate memories; they do not write active memory directly.",
            "- Dream agents produce reports; they do not delete or promote memory directly.",
            "- Forgetting agents suggest archive, expiry, merge, or downgrade actions; they do not auto-delete.",
            "- Raw private conversations do not sync to shared vaults or Supabase unless the user explicitly approves.",
            "- Shared user profiles should be reviewed summaries, not raw private interactions.",
            "",
            "Recommended lifecycle:",
            "",
            "```text",
            "capture -> candidate -> review -> active -> dream -> consolidate -> archive/expire",
            "```",
            "",
            "Recommended metadata:",
            "",
            "```yaml",
            "scope: private | project | shared | public",
            "sensitivity: low | medium | high | restricted",
            f"owner_agent: {agent}",
            "allowed_agents: []",
            "status: candidate | reviewed | active | archived",
            "memory_type: user_profile | care_summary | dream_report | forgetting_suggestion",
            "expires_at: null",
            "```",
            "",
            "Recommended operation:",
            "",
            f"- Project vault: `{project_path}`",
            "- Profile agent: propose L0/L1/L2 profile candidates for user or trusted-agent review.",
            "- Dream agent: run `vault dream` on a schedule and write review reports.",
            "- Forgetting agent: convert dream findings into archive/expiry suggestions, not direct deletion.",
        ]
    return "\n".join(lines) + "\n"


def write_memory_agents_guide(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    agent: str,
    language: str = "en",
) -> dict[str, str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    path = out / "README-memory-agents.md"
    path.write_text(
        render_memory_agents_guide(
            project_dir=project_dir,
            agent=agent,
            language=language,
        ),
        encoding="utf-8",
    )
    return {"guide": str(path), "mode": "report_only_candidate_only"}


def render_local_smoke_script(*, project_dir: str | Path, vault_executable: str = "vault") -> str:
    project = shlex.quote(str(Path(project_dir).expanduser()))
    return "\n".join(
        [
            "#!/usr/bin/env sh",
            "set -eu",
            f"PROJECT_DIR={project}",
            f"VAULT=${{VAULT:-{shlex.quote(vault_executable)}}}",
            "if [ -z \"${PYTHON:-}\" ]; then",
            "  VAULT_BIN=\"$(command -v \"$VAULT\" 2>/dev/null || true)\"",
            "  VAULT_SHEBANG=\"$(test -n \"$VAULT_BIN\" && test -f \"$VAULT_BIN\" && sed -n '1s/^#!//p' \"$VAULT_BIN\" || true)\"",
            "  case \"$VAULT_SHEBANG\" in *python*) PYTHON=\"$VAULT_SHEBANG\" ;; *) PYTHON=python3 ;; esac",
            "fi",
            "SMOKE_ID=\"$(date +%Y%m%d%H%M%S)-$$\"",
            "TITLE=\"Vault local smoke ${SMOKE_ID}\"",
            "CANDIDATE_TITLE=\"Vault local smoke candidate ${SMOKE_ID}\"",
            "CONTENT=\"Vault-for-LLM local smoke ${SMOKE_ID}: add/search-json/remember/candidates works.\"",
            "",
            "$VAULT add \"$TITLE\" \\",
            "  --project-dir \"$PROJECT_DIR\" \\",
            "  --content \"$CONTENT\" \\",
            "  --category setup \\",
            "  --tags smoke,setup \\",
            "  --trust 0.9 \\",
            "  --source setup-agent >/dev/null",
            "",
            "SEARCH_JSON=\"$($VAULT search \"$TITLE\" --project-dir \"$PROJECT_DIR\" --keyword-only --limit 5 --json)\"",
            "export SEARCH_JSON TITLE",
            "SMOKE_KID=\"$($PYTHON -c 'import json, os; p=json.loads(os.environ[\"SEARCH_JSON\"]); t=os.environ[\"TITLE\"]; rows=p.get(\"results\", []); matches=[r for r in rows if r.get(\"title\") == t]; assert p.get(\"count\", 0) >= 1 and matches, p; print(matches[0].get(\"id\"))')\"",
            "$VAULT --project-dir \"$PROJECT_DIR\" map build >/dev/null",
            "MAP_READ=\"$($VAULT --project-dir \"$PROJECT_DIR\" map read \"$SMOKE_KID\" --lines 1-20)\"",
            "case \"$MAP_READ\" in *\"local smoke\"*) ;; *) echo \"map read did not return smoke content\" >&2; exit 1 ;; esac",
            "",
            "$VAULT remember \"$CANDIDATE_TITLE\" \\",
            "  --project-dir \"$PROJECT_DIR\" \\",
            "  --content \"Candidate-only smoke memory created during agent setup validation.\" \\",
            "  --reason \"Verify candidate memory workflow after agent installation.\" \\",
            "  --mode candidate \\",
            "  --category setup \\",
            "  --tags smoke,setup \\",
            "  --source setup-agent \\",
            "  --source-ref \"local-smoke:${SMOKE_ID}\" >/dev/null",
            "",
            "CANDIDATES_JSON=\"$($VAULT candidates --project-dir \"$PROJECT_DIR\" --pretty)\"",
            "export CANDIDATES_JSON CANDIDATE_TITLE",
            "$PYTHON - <<'PY'",
            "import json, os",
            "payload = json.loads(os.environ['CANDIDATES_JSON'])",
            "title = os.environ['CANDIDATE_TITLE']",
            "if payload.get('count', 0) < 1:",
            "    raise SystemExit(f'candidate list is empty: {payload!r}')",
            "if not any(item.get('title') == title for item in payload.get('candidates', [])):",
            "    raise SystemExit(f'candidate list did not include smoke candidate: {payload!r}')",
            "PY",
            "",
            "export PROJECT_DIR",
            "$PYTHON - <<'PY'",
            "import json, os",
            "from vault.mcp import _set_project_dir, handle_tool_call, select_tools",
            "_set_project_dir(os.environ['PROJECT_DIR'])",
            "core = [tool['name'] for tool in select_tools('core')]",
            "required = {'vault_update_status', 'vault_automation_handoff'}",
            "missing = sorted(required - set(core))",
            "if missing:",
            "    raise SystemExit(f'MCP core profile missing startup tools: {missing}')",
            "status = json.loads(handle_tool_call('vault_update_status', {})['result'])",
            "if 'installed_version' not in status or 'startup_commands' not in status:",
            "    raise SystemExit(f'invalid update status payload: {status!r}')",
            "handoff = json.loads(handle_tool_call('vault_automation_handoff', {})['result'])",
            "if handoff.get('action') != 'handoff' or not handoff.get('safety', {}).get('read_only'):",
            "    raise SystemExit(f'invalid handoff payload: {handoff!r}')",
            "PY",
            "",
            "echo \"local_smoke=ok\"",
            "",
        ]
    )


def write_local_smoke_template(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    vault_executable: str = "vault",
) -> dict[str, str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    script_path = out / "local-smoke.sh"
    script_path.write_text(
        render_local_smoke_script(project_dir=project_dir, vault_executable=vault_executable),
        encoding="utf-8",
    )
    script_path.chmod(0o755)
    return {"script": str(script_path)}


def _normalize_memory_layout(layout: str | None) -> str:
    value = str(layout or "hybrid").strip().lower()
    if value not in VALID_MEMORY_LAYOUTS:
        allowed = ", ".join(sorted(VALID_MEMORY_LAYOUTS))
        raise ValueError(f"unknown memory layout '{layout}' (expected one of: {allowed})")
    return value


@dataclass
class AgentSetupConfig:
    project_dir: Path
    scope: str = "private"
    agent: str = "generic"
    memory_layout: str = "hybrid"
    agent_private_dir: Path | None = None
    features: list[str] = field(default_factory=lambda: list(DEFAULT_FEATURES))
    language: str = "en"
    tool_profile: str = "core"
    install_optional_deps: bool = False
    install_embedding_model: str | None = None
    obsidian_vault: Path | None = None
    import_obsidian: bool = False
    obsidian_dry_run_first: bool = True
    sync_targets: str | list[str] = "none"
    sync_interval_minutes: int = 15
    supabase_sync_targets: str | list[str] = "none"
    supabase_sync_interval_minutes: int = DEFAULT_SUPABASE_SYNC_INTERVAL_MINUTES
    supabase_setup_mode: str = "simple"
    remote_reader_targets: str | list[str] = "none"
    remote_reader_query: str = "deployment SOP"
    agent_roster: str | list[dict[str, Any]] | None = None
    validation_pack_targets: str | list[str] = "none"
    automation_schedule_targets: str | list[str] = "none"
    automation_interval_minutes: int = DEFAULT_AUTOMATION_INTERVAL_MINUTES
    automation_mode: str = "balanced"
    automation_command: str = "cycle"
    automation_apply: bool = False
    automation_write_workspace: bool = False
    automation_workspace_inbox_limit: int = 5
    automation_include_transcripts: bool = False
    automation_transcript_limit: int = 5
    automation_capture_transcripts: bool = False
    automation_capture_transcript_limit: int = 3
    automation_auto_promote_low_risk: bool = False
    template_dir: Path | None = None
    allow_private: bool = False
    stable_venv_path: Path | None = None


def run_agent_setup(config: AgentSetupConfig) -> dict[str, Any]:
    project_path = ensure_project(config.project_dir)
    features = normalize_features(config.features)
    language = _normalize_setup_language(config.language)
    memory_layout = _normalize_memory_layout(config.memory_layout)
    private_project_path: Path | None = None
    if memory_layout in {"hybrid", "private"}:
        private_project_path = ensure_project(config.agent_private_dir or default_agent_private_dir(config.agent))
    optional_dependency_install = None
    if config.install_optional_deps:
        optional_dependency_install = install_optional_dependencies(features)
    embedding_model_install = None
    if config.install_embedding_model:
        if "semantic" not in features:
            raise ValueError("install_embedding_model requires the semantic feature")
        embedding_model_install = install_embedding_model(
            config.install_embedding_model,
            project_dir=project_path,
        )
    feature_next_steps = optional_feature_next_steps(
        features,
        project_dir=project_path,
        installed_deps=bool(config.install_optional_deps),
        installed_embedding_model=config.install_embedding_model,
    )
    environment_warnings = python_environment_warnings()
    result: dict[str, Any] = {
        "version": __version__,
        "project_dir": str(project_path),
        "scope": config.scope,
        "agent": config.agent,
        "memory_layout": memory_layout,
        "agent_private_dir": str(private_project_path) if private_project_path else "",
        "features": features,
        "language": language,
        "tool_profile": config.tool_profile,
        "optional_dependency_install": optional_dependency_install,
        "embedding_model_install": embedding_model_install,
        "environment_warnings": environment_warnings,
        "db_path": str(project_path / "vault.db"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "obsidian": None,
        "sync_templates": {},
        "supabase_setup": {},
        "supabase_sync_templates": {},
        "remote_reader_templates": {},
        "agent_roster": {},
        "live_validation_pack": {},
        "memory_agents": {},
        "automation_policy": {},
        "automation_schedule_templates": {},
        "local_smoke": {},
        "stable_venv": {},
        "memory_layout_files": {},
        "mcp_startup": {},
        "update_status_templates": {},
        "agent_adapter_startup": {},
        "agent_registry": {},
        "next_steps": [
            f"vault search \"test query\" --project-dir {shlex.quote(str(project_path))} --limit 5 --json",
            f"vault-mcp --project-dir {shlex.quote(str(project_path))} --tool-profile {shlex.quote(config.tool_profile)}",
        ]
        + feature_next_steps,
    }
    result["agent_registry"] = register_agent(
        agent=config.agent,
        project_dir=project_path,
        scope=config.scope,
        features=features,
        tool_profile=config.tool_profile,
        source="setup-agent",
        memory_layout=memory_layout,
        private_project_dir=private_project_path,
    )
    result["next_steps"].insert(0, "Check local agent registry and update status: vault update-status")
    template_dir = config.template_dir or (project_path / "agent-install")
    result["memory_layout_files"] = write_memory_layout_manifest(
        output_dir=template_dir,
        agent=config.agent,
        memory_layout=memory_layout,
        shared_project_dir=project_path,
        private_project_dir=private_project_path,
    )
    result["next_steps"].append(f"Review memory layout manifest: {result['memory_layout_files']['manifest']}")
    result["mcp_startup"] = write_mcp_startup_guide(
        output_dir=template_dir,
        project_dir=project_path,
        tool_profile=config.tool_profile,
        agent=config.agent,
    )
    result["next_steps"].append(f"Review MCP startup guide: {result['mcp_startup']['readme']}")
    result["update_status_templates"] = write_update_status_templates(
        output_dir=template_dir,
        agent=config.agent,
    )
    result["next_steps"].append(f"Review Agent update status guide: {result['update_status_templates']['readme']}")
    result["next_steps"].append(f"Run update rollout health check: {result['update_status_templates']['refresh_script']}")
    result["agent_adapter_startup"] = write_agent_adapter_startup_templates(
        output_dir=template_dir,
        project_dir=project_path,
        tool_profile=config.tool_profile,
        agent=config.agent,
    )
    result["next_steps"].append(f"Review Agent adapter startup guide: {result['agent_adapter_startup']['readme']}")
    result["next_steps"].append(
        f"Review runtime update playbook: {result['agent_adapter_startup']['runtime_playbook_readme']}"
    )
    result["local_smoke"] = write_local_smoke_template(
        output_dir=template_dir,
        project_dir=project_path,
    )
    result["next_steps"].insert(0, f"Run local smoke test: {result['local_smoke']['script']}")
    if environment_warnings:
        result["next_steps"].append(
            "Move temporary Python virtualenvs to a stable path such as ~/.hermes/venvs/vault-for-llm/ before relying on scheduled jobs."
        )

    if "memory_agents" in features:
        result["memory_agents"] = write_memory_agents_guide(
            output_dir=template_dir,
            project_dir=project_path,
            agent=config.agent,
            language=language,
        )
        result["next_steps"].append(
            f"Review memory agents guide: {result['memory_agents']['guide']}"
        )

    if config.stable_venv_path:
        result["stable_venv"] = write_stable_venv_template(
            output_dir=template_dir,
            project_dir=project_path,
            venv_path=config.stable_venv_path,
            agent=config.agent,
            scope=config.scope,
            features=features,
            tool_profile=config.tool_profile,
            install_embedding_model=config.install_embedding_model,
        )
        result["next_steps"].append(
            f"Run stable venv bootstrap: sh {shlex.quote(result['stable_venv']['script'])}"
        )

    if config.obsidian_vault:
        obsidian_payload: dict[str, Any] = {"vault": str(config.obsidian_vault)}
        if config.obsidian_dry_run_first:
            obsidian_payload["dry_run"] = sync_obsidian_vault(
                project_dir=project_path,
                vault_dir=config.obsidian_vault,
                dry_run=True,
                allow_private=config.allow_private,
            )
        if config.import_obsidian:
            obsidian_payload["import"] = sync_obsidian_vault(
                project_dir=project_path,
                vault_dir=config.obsidian_vault,
                dry_run=False,
                allow_private=config.allow_private,
            )
            obsidian_payload["compile"] = compile_project(project_path, allow_private=config.allow_private)
        result["obsidian"] = obsidian_payload

        targets = _normalize_sync_targets(config.sync_targets)
        if targets:
            result["sync_templates"] = write_sync_templates(
                output_dir=template_dir,
                project_dir=project_path,
                obsidian_vault=config.obsidian_vault,
                targets=sorted(targets),
                interval_minutes=config.sync_interval_minutes,
            )

    if "supabase" in features:
        result["supabase_setup"] = write_supabase_setup_guide(
            output_dir=template_dir,
            project_dir=project_path,
            agent=config.agent,
            mode=config.supabase_setup_mode,
            language=language,
        )
        if result["supabase_setup"]:
            result["next_steps"].append(
                f"Review Supabase setup guide: {result['supabase_setup']['guide']}"
            )

    supabase_targets = _normalize_sync_targets(config.supabase_sync_targets)
    if "supabase" in features and supabase_targets:
        result["supabase_sync_templates"] = write_supabase_sync_templates(
            output_dir=template_dir,
            project_dir=project_path,
            targets=sorted(supabase_targets),
            interval_minutes=config.supabase_sync_interval_minutes,
        )

    remote_reader_targets = _normalize_remote_reader_targets(config.remote_reader_targets)
    if "supabase" in features and remote_reader_targets:
        result["remote_reader_templates"] = write_remote_reader_templates(
            output_dir=template_dir,
            agent=config.agent,
            targets=sorted(remote_reader_targets),
            query=config.remote_reader_query,
        )
        if result["remote_reader_templates"]:
            result["next_steps"].append(
                f"Run remote reader smoke test: {result['remote_reader_templates'].get('shell') or 'vault remote smoke'}"
            )

    if config.agent_roster:
        result["agent_roster"] = write_agent_roster_templates(
            output_dir=template_dir,
            project_dir=project_path,
            roster=config.agent_roster,
        )
        if result["agent_roster"]:
            result["next_steps"].append(f"Review agent access matrix: {result['agent_roster']['matrix']}")

    validation_targets = _normalize_validation_pack_targets(config.validation_pack_targets)
    if validation_targets:
        result["live_validation_pack"] = write_live_validation_pack(
            output_dir=template_dir,
            agent=config.agent,
            targets=sorted(validation_targets),
            query=config.remote_reader_query,
        )
        if result["live_validation_pack"]:
            result["next_steps"].append(f"Run live validation checklist: {result['live_validation_pack']['readme']}")

    automation_targets = _normalize_sync_targets(config.automation_schedule_targets)
    if config.automation_auto_promote_low_risk:
        result["automation_policy"] = write_automation_policy_template(
            project_dir=project_path,
            mode=config.automation_mode,
            auto_promote_low_risk=True,
        )
        result["next_steps"].append(
            f"Review low-risk auto-promote policy: {result['automation_policy']['path']}"
        )
    if automation_targets:
        result["automation_schedule_templates"] = write_automation_schedule_templates(
            output_dir=template_dir,
            project_dir=project_path,
            targets=sorted(automation_targets),
            interval_minutes=config.automation_interval_minutes,
            mode=config.automation_mode,
            command=config.automation_command,
            apply=config.automation_apply,
            write_workspace=config.automation_write_workspace,
            workspace_inbox_limit=config.automation_workspace_inbox_limit,
            include_transcripts=config.automation_include_transcripts,
            transcript_limit=config.automation_transcript_limit,
            capture_transcripts=config.automation_capture_transcripts,
            capture_transcript_limit=config.automation_capture_transcript_limit,
            auto_promote_low_risk=config.automation_auto_promote_low_risk,
        )
        result["next_steps"].append(
            f"Review memory automation schedule: {result['automation_schedule_templates']['readme']}"
        )
        result["next_steps"].append(
            f"Next agent startup handoff: vault automation handoff --project-dir {project_path}"
        )
        if config.automation_auto_promote_low_risk and not config.automation_apply:
            result["next_steps"].append(
                "Low-risk auto-promote policy is enabled, but generated schedules omit --apply; scheduled runs will preview only until --automation-apply is enabled."
            )

    return result


def default_stable_venv_path() -> Path:
    return Path("~/.hermes/venvs/vault-for-llm").expanduser()


def _pypi_install_target_for_features(features: list[str]) -> str:
    selected = normalize_features(features)
    extras = [feature for feature in ["mcp", "semantic", "supabase", "dev"] if feature in selected]
    if extras:
        return f"vault-for-llm[{','.join(extras)}]=={__version__}"
    return f"vault-for-llm=={__version__}"


def render_stable_venv_script(
    *,
    venv_path: str | Path,
    project_dir: str | Path,
    agent: str,
    scope: str,
    features: list[str],
    tool_profile: str,
    install_embedding_model: str | None = None,
) -> str:
    selected = normalize_features(features)
    install_target = _pypi_install_target_for_features(selected)
    project_path = Path(project_dir).expanduser()
    venv = Path(venv_path).expanduser()
    setup_command = [
        '"$VENV/bin/vault"',
        "setup-agent",
        "--non-interactive",
        "--agent",
        agent,
        "--scope",
        scope,
        "--agent-project-dir",
        str(project_path),
        "--features",
        ",".join(selected),
        "--tool-profile",
        tool_profile,
        "--json",
    ]
    if install_embedding_model:
        setup_command.extend(["--install-embedding-model", install_embedding_model])

    lines = [
        "#!/usr/bin/env sh",
        "set -eu",
        "",
        f"VENV={shlex.quote(str(venv))}",
        f"PROJECT_DIR={shlex.quote(str(project_path))}",
        "",
        "mkdir -p \"$(dirname \"$VENV\")\"",
        "python3 -m venv \"$VENV\"",
        "\"$VENV/bin/python\" -m pip install --upgrade pip",
        f"\"$VENV/bin/python\" -m pip install {shlex.quote(install_target)}",
    ]
    if "headroom" in selected:
        lines.append("\"$VENV/bin/python\" -m pip install headroom-ai")
    lines.extend(
        [
            "\"$VENV/bin/vault\" --version",
            "mkdir -p \"$PROJECT_DIR\"",
            " ".join(shlex.quote(part) if "$" not in part else part for part in setup_command),
            "",
        ]
    )
    return "\n".join(lines)


def render_stable_venv_readme(*, venv_path: str | Path, script_path: str | Path) -> str:
    return "\n".join(
        [
            "# Stable Python Virtualenv",
            "",
            "This template creates a long-lived Python virtualenv for Vault-for-LLM.",
            "Use it for scheduled jobs, MCP commands, Supabase sync, and agent runtimes.",
            "",
            f"Recommended venv path: `{Path(venv_path).expanduser()}`",
            "",
            "Run:",
            "",
            "```bash",
            f"sh {shlex.quote(str(script_path))}",
            "```",
            "",
            "After it succeeds, point scheduled jobs and agent MCP commands at the",
            "`vault` and `vault-mcp` executables inside that venv instead of a",
            "temporary `/tmp/...` virtualenv.",
            "",
        ]
    )


def write_stable_venv_template(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    venv_path: str | Path,
    agent: str,
    scope: str,
    features: list[str],
    tool_profile: str,
    install_embedding_model: str | None = None,
) -> dict[str, Any]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    script_path = out / "setup-stable-venv.sh"
    script_path.write_text(
        render_stable_venv_script(
            venv_path=venv_path,
            project_dir=project_dir,
            agent=agent,
            scope=scope,
            features=features,
            tool_profile=tool_profile,
            install_embedding_model=install_embedding_model,
        ),
        encoding="utf-8",
    )
    script_path.chmod(0o755)

    readme_path = out / "README-stable-venv.md"
    readme_path.write_text(
        render_stable_venv_readme(venv_path=venv_path, script_path=script_path),
        encoding="utf-8",
    )
    return {
        "venv_path": str(Path(venv_path).expanduser()),
        "script": str(script_path),
        "readme": str(readme_path),
    }


def install_optional_dependencies(features: list[str]) -> dict[str, Any]:
    selected = normalize_features(features)
    commands: list[list[str]] = []
    extras = [feature for feature in ["mcp", "semantic", "supabase", "dev"] if feature in selected]
    if extras:
        commands.append(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                f"vault-for-llm[{','.join(extras)}]=={__version__}",
            ]
        )
    if "headroom" in selected:
        commands.append([sys.executable, "-m", "pip", "install", "headroom-ai"])

    results: list[dict[str, Any]] = []
    for command in commands:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        item = {
            "command": shell_join(command),
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-2000:],
            "stderr_tail": completed.stderr[-2000:],
        }
        results.append(item)
        if completed.returncode != 0:
            raise RuntimeError(
                "optional dependency install failed: "
                f"{shell_join(command)}\n{completed.stderr[-2000:]}"
            )

    return {
        "installed": bool(commands),
        "features": selected,
        "commands": [shell_join(command) for command in commands],
        "results": results,
    }


def python_environment_warnings() -> list[str]:
    """Warn agents when Vault was installed into a disposable temp environment."""
    prefixes = {
        str(Path(tempfile.gettempdir()).resolve()),
        "/tmp",
        "/private/tmp",
        "/var/tmp",
        "/private/var/tmp",
    }
    candidates = {
        "sys_prefix": str(Path(sys.prefix).expanduser()),
        "sys_executable": str(Path(sys.executable).expanduser()),
    }
    warnings: list[str] = []
    for label, raw_path in candidates.items():
        path = str(Path(raw_path).resolve())
        if any(path == prefix or path.startswith(prefix + "/") for prefix in prefixes):
            warnings.append(
                f"{label} is under a temporary directory ({raw_path}); use a stable venv such as ~/.hermes/venvs/vault-for-llm/ for long-lived agent installs."
            )
    return warnings


def install_embedding_model(model_key: str, *, project_dir: str | Path) -> dict[str, Any]:
    model = str(model_key).strip().lower()
    if model not in VALID_EMBEDDING_MODELS:
        allowed = ", ".join(sorted(VALID_EMBEDDING_MODELS))
        raise ValueError(f"unknown embedding model '{model_key}' (expected one of: {allowed})")

    command = [
        sys.executable,
        "-m",
        "vault.cli",
        "--project-dir",
        str(Path(project_dir).expanduser()),
        "install-embedding",
        "--model",
        model,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    result = {
        "model": model,
        "command": shell_join(command),
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
    }
    if completed.returncode != 0:
        raise RuntimeError(
            "embedding model install failed: "
            f"{shell_join(command)}\n{completed.stderr[-2000:]}"
        )
    return result


def optional_feature_next_steps(
    features: list[str],
    *,
    project_dir: str | Path,
    installed_deps: bool = False,
    installed_embedding_model: str | None = None,
) -> list[str]:
    project_path = Path(project_dir).expanduser()
    steps: list[str] = []
    if "semantic" in features:
        if not installed_deps:
            steps.append('python -m pip install "vault-for-llm[semantic]"')
        if not installed_embedding_model:
            steps.append("vault install-embedding --model mix")
        steps.append(
            f"vault semantic rebuild --project-dir {shlex.quote(str(project_path))} --persist-cache --pretty"
        )
    if "supabase" in features:
        if not installed_deps:
            steps.append('python -m pip install "vault-for-llm[supabase]"')
        steps.append(
            "Use Supabase only for cross-host/team/shared-memory sync; skip it when local vault.db is enough."
        )
        steps.append("configure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY before running sync scripts")
        steps.append("use SUPABASE_ANON_KEY, not the service role key, for remote reader agents")
    if "headroom" in features:
        if not installed_deps:
            steps.append("python -m pip install headroom-ai")
        steps.extend(
            [
                "Use Headroom after Vault retrieval when logs, tool output, or retrieved context are too large.",
                "Keep Vault citations tied to original vault_read_range output, not compressed summaries.",
            ]
        )
    if "memory_agents" in features:
        steps.extend(
            [
                "Keep Profile/Dream/Forgetting agents report-only or candidate-only by default.",
                "Use reviewed summaries for shared profile memory; keep raw private interactions local.",
                "Use Progressive Memory Disclosure: boot summary -> active context -> topic map -> bounded read -> raw/archive only when justified.",
            ]
        )
    if "dev" in features:
        if not installed_deps:
            steps.append('python -m pip install "vault-for-llm[dev]"')
    return steps


def interactive_setup(argv_config: dict[str, Any]) -> AgentSetupConfig:
    agent = str(argv_config.get("agent") or _ask("Agent/runtime", "generic"))
    scope = str(argv_config.get("scope") or _ask("Vault scope (shared/private/domain/temporary)", "private"))
    memory_layout = str(
        argv_config.get("memory_layout")
        or _ask("Memory layout (hybrid/shared/private)", "hybrid")
    )
    project_dir = argv_config.get("project_dir")
    if not project_dir:
        project_dir = _ask("Vault project directory", str(default_project_dir(scope, agent=agent)))
    agent_private_dir = argv_config.get("agent_private_dir")
    if not agent_private_dir and _normalize_memory_layout(memory_layout) in {"hybrid", "private"}:
        agent_private_dir = _ask("Agent private vault directory", str(default_agent_private_dir(agent)))
    language = argv_config.get("language")
    if language is None:
        language = _ask("Setup language / 安裝語言 (en/zh-Hant/zh-CN)", "en")

    features_raw = argv_config.get("features")
    if features_raw:
        features = normalize_features(features_raw)
    else:
        features = _ask_interactive_features()

    install_optional_deps = bool(argv_config.get("install_optional_deps", False))
    if not install_optional_deps and _features_need_dependency_install(features):
        install_optional_deps = _ask_yes_no("Install selected optional Python dependencies now?", True)

    install_embedding_choice = argv_config.get("install_embedding_model")
    if install_embedding_choice is None and install_optional_deps and "semantic" in features:
        if _ask_yes_no("Download and configure a local ONNX embedding model now?", True):
            install_embedding_choice = _ask("Embedding model (zh/en/mix)", "mix")

    obsidian_vault = argv_config.get("obsidian_vault")
    if obsidian_vault is None:
        obsidian_vault = _ask("Existing Obsidian vault path (blank to skip)", "")

    import_obsidian = bool(argv_config.get("import_obsidian", False))
    sync_targets = argv_config.get("sync_targets", "none")
    if obsidian_vault:
        if "import_obsidian" not in argv_config:
            import_obsidian = _ask_yes_no("Run first Obsidian import after dry-run?", False)
        if not argv_config.get("sync_targets"):
            sync_targets = _ask("Automatic sync templates (none/cron/launchagent/n8n/all)", "none")

    supabase_sync_targets = argv_config.get("supabase_sync_targets", "none")
    supabase_setup_mode = argv_config.get("supabase_setup_mode")
    if "supabase" in features and supabase_setup_mode is None:
        supabase_setup_mode = _ask("Supabase setup guide (simple/advanced/none)", "simple")
    if "supabase" in features and not argv_config.get("supabase_sync_targets"):
        supabase_sync_targets = _ask("Daily Supabase sync templates (none/cron/launchagent/n8n/all)", "none")
    remote_reader_targets = argv_config.get("remote_reader_targets", "none")
    if "supabase" in features and not argv_config.get("remote_reader_targets"):
        remote_reader_targets = _ask("Remote reader templates for n8n/Coze/shell (none/shell/n8n/coze/all)", "none")
    remote_reader_query = str(argv_config.get("remote_reader_query") or "deployment SOP")
    agent_roster = argv_config.get("agent_roster")
    if agent_roster is None and _ask_yes_no("Generate multi-agent roster/access-matrix templates?", False):
        agent_roster = _ask("Agent roster (example: profile-agent:profile,work-agent:work,product-agent:work,remote-agent:remote,n8n:automation)", "")
    validation_pack_targets = argv_config.get("validation_pack_targets", "none")
    if "supabase" in features and not argv_config.get("validation_pack_targets"):
        validation_pack_targets = _ask("Live validation pack for remote/n8n/coze (none/remote/n8n/coze/all)", "none")

    automation_schedule_targets = argv_config.get("automation_schedule_targets", "none")
    if not argv_config.get("automation_schedule_targets"):
        automation_schedule_targets = _ask("Memory automation schedule templates (none/cron/launchagent/n8n/all)", "none")
    automation_mode = argv_config.get("automation_mode") or "balanced"
    if automation_schedule_targets and automation_schedule_targets != "none" and not argv_config.get("automation_mode"):
        automation_mode = _ask("Memory automation mode (conservative/balanced/autonomous)", "balanced")
    automation_command = argv_config.get("automation_command") or "cycle"
    if automation_schedule_targets and automation_schedule_targets != "none" and not argv_config.get("automation_command"):
        automation_command = _ask("Memory automation command (cycle/run)", "cycle")
    automation_apply = bool(argv_config.get("automation_apply", False))
    if automation_schedule_targets and automation_schedule_targets != "none" and "automation_apply" not in argv_config:
        automation_apply = _ask_yes_no("Allow scheduled automation to apply reversible archival?", False)
    automation_write_workspace = bool(argv_config.get("automation_write_workspace", False))
    if (
        automation_schedule_targets
        and automation_schedule_targets != "none"
        and str(automation_command or "cycle") == "cycle"
        and "automation_write_workspace" not in argv_config
    ):
        automation_write_workspace = _ask_yes_no(
            "Write scheduled cycle workspace handoff (cycle-latest.json)?",
            False,
        )
    automation_workspace_inbox_limit = int(argv_config.get("automation_workspace_inbox_limit") or 5)
    automation_include_transcripts = bool(argv_config.get("automation_include_transcripts", False))
    if (
        automation_schedule_targets
        and automation_schedule_targets != "none"
        and "automation_include_transcripts" not in argv_config
    ):
        automation_include_transcripts = _ask_yes_no(
            "Include metadata-only uncaptured transcript hints in scheduled inbox handoff?",
            False,
        )
    automation_transcript_limit = int(argv_config.get("automation_transcript_limit") or 5)
    automation_capture_transcripts = bool(argv_config.get("automation_capture_transcripts", False))
    if (
        automation_schedule_targets
        and automation_schedule_targets != "none"
        and "automation_capture_transcripts" not in argv_config
    ):
        automation_capture_transcripts = _ask_yes_no(
            "Capture discovered transcripts into review candidates during scheduled apply runs?",
            False,
        )
    automation_capture_transcript_limit = int(argv_config.get("automation_capture_transcript_limit") or 3)
    automation_auto_promote_low_risk = bool(argv_config.get("automation_auto_promote_low_risk", False))
    if (
        automation_schedule_targets
        and automation_schedule_targets != "none"
        and "automation_auto_promote_low_risk" not in argv_config
    ):
        automation_auto_promote_low_risk = _ask_yes_no(
            "Enable low-risk auto-promote policy for session_capture/session_lesson candidates?",
            False,
        )

    stable_venv_path = argv_config.get("stable_venv_path")
    if not stable_venv_path and argv_config.get("write_stable_venv_script"):
        stable_venv_path = str(default_stable_venv_path())
    if stable_venv_path is None and python_environment_warnings():
        if _ask_yes_no("Current Python environment looks temporary. Generate a stable venv bootstrap script?", True):
            stable_venv_path = _ask("Stable venv path", str(default_stable_venv_path()))

    return AgentSetupConfig(
        project_dir=Path(project_dir),
        scope=scope,
        agent=agent,
        memory_layout=memory_layout,
        agent_private_dir=Path(agent_private_dir).expanduser() if agent_private_dir else None,
        features=features,
        language=_normalize_setup_language(str(language)),
        tool_profile=str(argv_config.get("tool_profile") or "core"),
        install_optional_deps=install_optional_deps,
        install_embedding_model=install_embedding_choice,
        obsidian_vault=Path(obsidian_vault).expanduser() if obsidian_vault else None,
        import_obsidian=import_obsidian,
        sync_targets=sync_targets,
        sync_interval_minutes=int(argv_config.get("sync_interval_minutes") or 15),
        supabase_sync_targets=supabase_sync_targets,
        supabase_sync_interval_minutes=int(
            argv_config.get("supabase_sync_interval_minutes")
            or DEFAULT_SUPABASE_SYNC_INTERVAL_MINUTES
        ),
        supabase_setup_mode=str(supabase_setup_mode or "simple"),
        remote_reader_targets=remote_reader_targets,
        remote_reader_query=remote_reader_query,
        agent_roster=agent_roster or None,
        validation_pack_targets=validation_pack_targets,
        automation_schedule_targets=automation_schedule_targets,
        automation_interval_minutes=int(
            argv_config.get("automation_interval_minutes")
            or DEFAULT_AUTOMATION_INTERVAL_MINUTES
        ),
        automation_mode=_normalize_automation_mode(str(automation_mode)),
        automation_command=_normalize_automation_command(str(automation_command)),
        automation_apply=automation_apply,
        automation_write_workspace=automation_write_workspace,
        automation_workspace_inbox_limit=automation_workspace_inbox_limit,
        automation_include_transcripts=automation_include_transcripts,
        automation_transcript_limit=automation_transcript_limit,
        automation_capture_transcripts=automation_capture_transcripts,
        automation_capture_transcript_limit=automation_capture_transcript_limit,
        automation_auto_promote_low_risk=automation_auto_promote_low_risk,
        template_dir=Path(argv_config["template_dir"]) if argv_config.get("template_dir") else None,
        allow_private=bool(argv_config.get("allow_private", False)),
        stable_venv_path=Path(stable_venv_path).expanduser() if stable_venv_path else None,
    )


def _ask(prompt: str, default: str) -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        answer = ""
    return answer or default


def _ask_interactive_features() -> list[str]:
    features = ["core"]
    if _ask_yes_no("Configure local stdio MCP tools for this agent?", True):
        features.append("mcp")
    if _ask_yes_no("Enable optional semantic search and embedding workflow?", False):
        features.append("semantic")
    if _ask_yes_no("Enable optional Supabase sync/read dependencies?", False):
        features.append("supabase")
    if _ask_yes_no(
        "Enable optional Headroom context compression for long logs/tool output?",
        False,
    ):
        features.append("headroom")
    if _ask_yes_no("Enable Profile/Dream/Forgetting memory-agent guidance?", False):
        features.append("memory_agents")
    if _ask_yes_no("Install developer/benchmark dependencies?", False):
        features.append("dev")
    return features


def _features_need_dependency_install(features: list[str]) -> bool:
    selected = set(normalize_features(features))
    # The recommended first install already uses vault-for-llm[mcp]. Do not ask
    # users to install "optional" dependencies again when MCP is the only extra.
    extras_that_need_confirmation = PYPI_EXTRA_FEATURES - {"mcp"}
    return bool((selected & extras_that_need_confirmation) or "headroom" in selected)


def _ask_yes_no(prompt: str, default: bool) -> bool:
    default_text = "Y/n" if default else "y/N"
    try:
        answer = input(f"{prompt} [{default_text}]: ").strip().lower()
    except EOFError:
        answer = ""
    if not answer:
        return default
    return answer in {"y", "yes", "true", "1"}
