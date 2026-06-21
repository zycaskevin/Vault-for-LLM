"""Agent-friendly setup wizard and sync template helpers."""

from __future__ import annotations

import contextlib
import io
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vault import __version__
from vault.db import VaultDB
from vault.import_obsidian import sync_obsidian_vault


DEFAULT_FEATURES = ["core", "mcp"]
VALID_FEATURES = {"core", "mcp", "obsidian_import", "semantic", "supabase", "headroom", "dev"}
VALID_SYNC_TARGETS = {"none", "cron", "launchagent", "n8n", "all"}
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


def render_launchagent_plist(
    *,
    command: list[str],
    label: str = "com.zycaskevin.vault-for-llm.obsidian-sync",
    interval_minutes: int = 15,
) -> str:
    interval_seconds = max(60, int(interval_minutes) * 60)
    program = command[0]
    args = command[1:]
    arg_lines = "\n".join(f"    <string>{_xml_escape(arg)}</string>" for arg in args)
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
  <string>{_xml_escape(str(Path.home() / ".vault-for-llm" / "obsidian-sync.log"))}</string>
  <key>StandardErrorPath</key>
  <string>{_xml_escape(str(Path.home() / ".vault-for-llm" / "obsidian-sync.err.log"))}</string>
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
                "",
            ]
        ),
        encoding="utf-8",
    )
    written["readme"] = str(readme)
    return written


def _normalize_sync_targets(targets: str | list[str]) -> set[str]:
    if isinstance(targets, str):
        selected = {part.strip() for part in targets.split(",") if part.strip()}
    else:
        selected = {str(part).strip() for part in targets if str(part).strip()}
    if not selected or "none" in selected:
        return set()
    if "all" in selected:
        return {"cron", "launchagent", "n8n"}
    unknown = selected - VALID_SYNC_TARGETS
    if unknown:
        raise ValueError(f"unknown sync target(s): {', '.join(sorted(unknown))}")
    return selected


@dataclass
class AgentSetupConfig:
    project_dir: Path
    scope: str = "private"
    agent: str = "generic"
    features: list[str] = field(default_factory=lambda: list(DEFAULT_FEATURES))
    tool_profile: str = "core"
    install_optional_deps: bool = False
    install_embedding_model: str | None = None
    obsidian_vault: Path | None = None
    import_obsidian: bool = False
    obsidian_dry_run_first: bool = True
    sync_targets: str | list[str] = "none"
    sync_interval_minutes: int = 15
    template_dir: Path | None = None
    allow_private: bool = False


def run_agent_setup(config: AgentSetupConfig) -> dict[str, Any]:
    project_path = ensure_project(config.project_dir)
    features = normalize_features(config.features)
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
    result: dict[str, Any] = {
        "project_dir": str(project_path),
        "scope": config.scope,
        "agent": config.agent,
        "features": features,
        "tool_profile": config.tool_profile,
        "optional_dependency_install": optional_dependency_install,
        "embedding_model_install": embedding_model_install,
        "db_path": str(project_path / "vault.db"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "obsidian": None,
        "sync_templates": {},
        "next_steps": [
            f"vault search \"test query\" --project-dir {shlex.quote(str(project_path))} --limit 5",
            f"vault-mcp --project-dir {shlex.quote(str(project_path))} --tool-profile {shlex.quote(config.tool_profile)}",
        ]
        + feature_next_steps,
    }

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
            template_dir = config.template_dir or (project_path / "agent-install")
            result["sync_templates"] = write_sync_templates(
                output_dir=template_dir,
                project_dir=project_path,
                obsidian_vault=config.obsidian_vault,
                targets=sorted(targets),
                interval_minutes=config.sync_interval_minutes,
            )

    return result


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
        steps.append("configure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY before running sync scripts")
    if "headroom" in features:
        if not installed_deps:
            steps.append("python -m pip install headroom-ai")
        steps.extend(
            [
                "Use Headroom after Vault retrieval when logs, tool output, or retrieved context are too large.",
                "Keep Vault citations tied to original vault_read_range output, not compressed summaries.",
            ]
        )
    if "dev" in features:
        if not installed_deps:
            steps.append('python -m pip install "vault-for-llm[dev]"')
    return steps


def interactive_setup(argv_config: dict[str, Any]) -> AgentSetupConfig:
    agent = str(argv_config.get("agent") or _ask("Agent/runtime", "generic"))
    scope = str(argv_config.get("scope") or _ask("Vault scope (shared/private/domain/temporary)", "private"))
    project_dir = argv_config.get("project_dir")
    if not project_dir:
        project_dir = _ask("Vault project directory", str(default_project_dir(scope, agent=agent)))

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

    return AgentSetupConfig(
        project_dir=Path(project_dir),
        scope=scope,
        agent=agent,
        features=features,
        tool_profile=str(argv_config.get("tool_profile") or "core"),
        install_optional_deps=install_optional_deps,
        install_embedding_model=install_embedding_choice,
        obsidian_vault=Path(obsidian_vault).expanduser() if obsidian_vault else None,
        import_obsidian=import_obsidian,
        sync_targets=sync_targets,
        sync_interval_minutes=int(argv_config.get("sync_interval_minutes") or 15),
        template_dir=Path(argv_config["template_dir"]) if argv_config.get("template_dir") else None,
        allow_private=bool(argv_config.get("allow_private", False)),
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
    if _ask_yes_no("Install developer/benchmark dependencies?", False):
        features.append("dev")
    return features


def _features_need_dependency_install(features: list[str]) -> bool:
    selected = set(normalize_features(features))
    return bool((selected & PYPI_EXTRA_FEATURES) or "headroom" in selected)


def _ask_yes_no(prompt: str, default: bool) -> bool:
    default_text = "Y/n" if default else "y/N"
    try:
        answer = input(f"{prompt} [{default_text}]: ").strip().lower()
    except EOFError:
        answer = ""
    if not answer:
        return default
    return answer in {"y", "yes", "true", "1"}
