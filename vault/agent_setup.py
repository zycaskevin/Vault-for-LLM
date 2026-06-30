"""Agent-friendly setup wizard and sync template helpers."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from vault import __version__
from vault.agent_access import (
    apply_agent_access_overrides,
    agent_access_preset,
    render_agent_access_presets_markdown,
)
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
    write_agent_adapter_startup_templates,
    write_mcp_startup_guide,
    write_update_status_templates,
)
from vault.agent_setup_runtime import (
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
)
from vault.agent_setup_consumer import (
    write_consumer_daily_report_guide,
    write_consumer_security_hardening_guide,
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
from vault.agent_setup_venv import default_stable_venv_path, write_stable_venv_template
from vault.agent_setup_roster import (
    VALID_AGENT_ROLES,
    VALID_VALIDATION_PACK_TARGETS,
    _deep_merge_dict,
    _normalize_validation_pack_targets,
    _safe_slug,
    normalize_agent_roster,
    render_agent_access_matrix,
    write_agent_roster_templates,
    write_live_validation_pack,
    write_memory_layout_manifest,
)
from vault.agent_setup_memory import (
    render_local_smoke_script,
    render_memory_agents_guide,
    write_local_smoke_template,
    write_memory_agents_guide,
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
VALID_MEMORY_LAYOUTS = {"shared", "private", "hybrid"}
VALID_RUNTIME_TEMPLATES = {"codex", "claude-code", "claude_code", "openclaw", "hermes"}
PYPI_EXTRA_FEATURES = {"mcp", "semantic", "supabase", "dev"}
VALID_EMBEDDING_MODELS = {"zh", "en", "mix"}


def current_vault_executable() -> str:
    """Return the best stable vault executable path for generated schedules."""
    return shutil.which("vault") or "vault"


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
    agent_preset: str = ""
    audience: str = "builder"
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
    daily_report_time: str = ""
    template_dir: Path | None = None
    allow_private: bool = False
    stable_venv_path: Path | None = None
    agent_access_overrides: dict[str, Any] = field(default_factory=dict)


def run_agent_setup(config: AgentSetupConfig) -> dict[str, Any]:
    access_preset = apply_agent_access_overrides(
        agent_access_preset(config.agent_preset),
        config.agent_access_overrides,
    )
    project_path = ensure_project(config.project_dir)
    features = normalize_features(config.features)
    language = _normalize_setup_language(config.language)
    audience = _normalize_audience(config.audience)
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
        "agent_preset": access_preset,
        "audience": audience,
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
        "consumer_daily_report": {},
        "agent_access": {},
        "security_hardening": {},
        "mcp_startup": {},
        "update_status_templates": {},
        "agent_adapter_startup": {},
        "agent_registry": {},
        "human_next_steps": [],
        "agent_next_steps": [],
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
    if access_preset:
        access_path = Path(template_dir).expanduser().resolve() / "agent-access-preset.json"
        access_path.parent.mkdir(parents=True, exist_ok=True)
        access_path.write_text(json.dumps(access_preset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        catalog_path = access_path.parent / "AGENT_ACCESS_PRESETS.md"
        catalog_path.write_text(render_agent_access_presets_markdown(), encoding="utf-8")
        result["agent_access"] = {
            "preset": access_preset["preset"],
            "path": str(access_path),
            "catalog": str(catalog_path),
        }
    result["memory_layout_files"] = write_memory_layout_manifest(
        output_dir=template_dir,
        agent=config.agent,
        memory_layout=memory_layout,
        shared_project_dir=project_path,
        private_project_dir=private_project_path,
    )
    result["next_steps"].append(f"Review memory layout manifest: {result['memory_layout_files']['manifest']}")
    if access_preset:
        result["next_steps"].append(
            f"Review agent access preset: {access_preset['preset']} ({access_preset['summary']})"
        )
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
    if audience == "consumer":
        result["consumer_daily_report"] = write_consumer_daily_report_guide(
            output_dir=template_dir,
            project_dir=project_path,
            agent=config.agent,
            language=language,
        )
        result["next_steps"].insert(
            0,
            "For everyday use, ask your agent to run the memory loop and show you `vault daily-report`.",
        )
        result["next_steps"].append(
            f"Review consumer daily-report guide: {result['consumer_daily_report']['guide']}"
        )
        result["human_next_steps"] = [
            "Ask your agent to maintain Vault memory for you.",
            "Read the daily report instead of learning commands.",
            "Only decide the few cards marked keep, private, reject, or defer.",
        ]
        result["security_hardening"] = write_consumer_security_hardening_guide(
            output_dir=template_dir,
            agent=config.agent,
            language=language,
        )
        result["next_steps"].append(
            f"Review local safety guide: {result['security_hardening']['readme']}"
        )
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
            agent_preset=config.agent_preset,
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

    automation_schedule_targets = config.automation_schedule_targets
    automation_write_workspace = config.automation_write_workspace
    if audience == "consumer" and _normalize_sync_targets(automation_schedule_targets) == set():
        automation_schedule_targets = "cron"
        automation_write_workspace = True
    daily_report_time = str(config.daily_report_time or ("09:00" if audience == "consumer" else ""))
    automation_targets = _normalize_sync_targets(automation_schedule_targets)
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
            vault_executable=current_vault_executable(),
            write_workspace=automation_write_workspace,
            workspace_inbox_limit=config.automation_workspace_inbox_limit,
            include_transcripts=config.automation_include_transcripts,
            transcript_limit=config.automation_transcript_limit,
            capture_transcripts=config.automation_capture_transcripts,
            capture_transcript_limit=config.automation_capture_transcript_limit,
            auto_promote_low_risk=config.automation_auto_promote_low_risk,
            write_daily_report=audience == "consumer",
            daily_report_time=daily_report_time,
            language=language,
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

    result["agent_next_steps"] = list(result["next_steps"])
    return result


def _normalize_audience(value: str | None) -> str:
    text = str(value or "builder").strip().lower()
    if text in {"consumer", "general", "human", "user"}:
        return "consumer"
    if text in {"builder", "developer", "agent-builder", "dev"}:
        return "builder"
    raise ValueError("audience must be consumer or builder")


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
    audience = _normalize_audience(str(argv_config.get("audience") or "builder"))
    if audience == "consumer":
        return _interactive_consumer_setup(argv_config, agent=agent, audience=audience)
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
        agent_preset=str(argv_config.get("agent_preset") or ""),
        audience=audience,
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
        agent_access_overrides=dict(argv_config.get("agent_access_overrides") or {}),
    )


def _interactive_consumer_setup(argv_config: dict[str, Any], *, agent: str, audience: str) -> AgentSetupConfig:
    """Small consumer wizard: vault layout, optional connectors, daily report time."""
    language = argv_config.get("language")
    if language is None:
        language = _ask("Language / 語言 / 语言 (zh-Hant/zh-CN/en)", "en")
    layout_choice = str(
        argv_config.get("consumer_memory_choice")
        or argv_config.get("scope")
        or _ask("Memory vault (independent/shared)", "independent")
    ).strip().lower()
    shared = layout_choice in {"shared", "share", "team", "merge", "merged"}
    scope = "shared" if shared else "private"
    memory_layout = "shared" if shared else "private"
    project_dir = argv_config.get("project_dir") or argv_config.get("agent_project_dir")
    if not project_dir:
        project_dir = str(default_project_dir(scope, agent=agent))

    connections = str(
        argv_config.get("consumer_connections")
        or _ask("Optional connections (none/obsidian/supabase/both)", "none")
    ).strip().lower()
    wants_obsidian = connections in {"obsidian", "both", "all"}
    wants_supabase = connections in {"supabase", "both", "all"}
    features = ["core", "mcp"]
    if wants_obsidian:
        features.append("obsidian_import")
    if wants_supabase:
        features.append("supabase")

    obsidian_vault = argv_config.get("obsidian_vault")
    if wants_obsidian and obsidian_vault is None:
        obsidian_vault = _ask("Obsidian vault path", "")
    daily_report_time = str(
        argv_config.get("daily_report_time") or _ask("Daily report time (HH:MM)", "09:00")
    ).strip() or "09:00"

    return AgentSetupConfig(
        project_dir=Path(project_dir),
        scope=scope,
        agent=agent,
        agent_preset=str(argv_config.get("agent_preset") or ""),
        audience=audience,
        memory_layout=memory_layout,
        features=features,
        language=_normalize_setup_language(str(language)),
        tool_profile=str(argv_config.get("tool_profile") or "core"),
        obsidian_vault=Path(obsidian_vault).expanduser() if obsidian_vault else None,
        import_obsidian=bool(argv_config.get("import_obsidian", False)),
        sync_targets="cron" if wants_obsidian else "none",
        supabase_setup_mode="simple" if wants_supabase else "none",
        supabase_sync_targets="cron" if wants_supabase else "none",
        remote_reader_targets="shell" if wants_supabase else "none",
        automation_schedule_targets="cron",
        automation_mode="balanced",
        automation_command="cycle",
        automation_apply=False,
        automation_write_workspace=True,
        daily_report_time=daily_report_time,
        template_dir=Path(argv_config["template_dir"]) if argv_config.get("template_dir") else None,
        stable_venv_path=(
            Path(argv_config["stable_venv_path"]).expanduser()
            if argv_config.get("stable_venv_path")
            else None
        ),
        agent_access_overrides=dict(argv_config.get("agent_access_overrides") or {}),
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
