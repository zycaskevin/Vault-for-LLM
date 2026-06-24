"""Local agent registry and update status helpers."""

from __future__ import annotations

import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vault import __version__


REGISTRY_VERSION = 1
PYPI_JSON_URL = "https://pypi.org/pypi/vault-for-llm/json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def registry_dir() -> Path:
    override = os.environ.get("VAULT_AGENT_REGISTRY_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path("~/.vault-for-llm").expanduser()


def registry_path() -> Path:
    return registry_dir() / "agent-registry.json"


def update_status_path() -> Path:
    return registry_dir() / "update-status.json"


def safe_agent_id(value: object, default: str = "generic") -> str:
    text = str(value or default).strip().lower()
    cleaned = []
    for char in text:
        if char.isalnum() or char in {"-", "_"}:
            cleaned.append(char)
        elif char in {" ", ".", "/", ":"}:
            cleaned.append("-")
    agent_id = "".join(cleaned).strip("-_")
    return agent_id or default


def _empty_registry() -> dict[str, Any]:
    now = utc_now_iso()
    return {
        "version": REGISTRY_VERSION,
        "created_at": now,
        "updated_at": now,
        "agents": {},
    }


def load_registry(path: str | Path | None = None) -> dict[str, Any]:
    registry_file = Path(path).expanduser() if path else registry_path()
    if not registry_file.exists():
        return _empty_registry()
    try:
        payload = json.loads(registry_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid agent registry JSON: {registry_file}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"invalid agent registry payload: {registry_file}")
    payload.setdefault("version", REGISTRY_VERSION)
    payload.setdefault("created_at", utc_now_iso())
    payload.setdefault("updated_at", utc_now_iso())
    payload.setdefault("agents", {})
    if not isinstance(payload["agents"], dict):
        raise ValueError(f"invalid agent registry agents map: {registry_file}")
    return payload


def save_registry(payload: dict[str, Any], path: str | Path | None = None) -> Path:
    registry_file = Path(path).expanduser() if path else registry_path()
    registry_file.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = utc_now_iso()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(registry_file.parent),
        prefix=f".{registry_file.name}.",
        delete=False,
    ) as handle:
        handle.write(text)
        temp_name = handle.name
    Path(temp_name).replace(registry_file)
    return registry_file


def register_agent(
    *,
    agent: str,
    project_dir: str | Path,
    scope: str = "shared",
    features: list[str] | tuple[str, ...] | None = None,
    tool_profile: str = "core",
    source: str = "manual",
    path: str | Path | None = None,
) -> dict[str, Any]:
    agent_id = safe_agent_id(agent)
    project_path = Path(project_dir).expanduser().resolve()
    now = utc_now_iso()
    registry = load_registry(path)
    previous = registry["agents"].get(agent_id, {})
    registered_at = previous.get("registered_at") or now
    entry = {
        "agent_id": agent_id,
        "scope": scope,
        "project_dir": str(project_path),
        "db_path": str(project_path / "vault.db"),
        "features": sorted(str(item) for item in (features or []) if str(item).strip()),
        "tool_profile": tool_profile,
        "source": source,
        "vault_version": __version__,
        "registered_at": registered_at,
        "last_seen_at": now,
    }
    registry["agents"][agent_id] = entry
    written = save_registry(registry, path)
    return {
        "ok": True,
        "registry_path": str(written),
        "agent": entry,
    }


def list_agents(path: str | Path | None = None) -> dict[str, Any]:
    registry = load_registry(path)
    agents = sorted(registry["agents"].values(), key=lambda item: item.get("agent_id", ""))
    return {
        "registry_path": str(Path(path).expanduser() if path else registry_path()),
        "version": registry.get("version", REGISTRY_VERSION),
        "updated_at": registry.get("updated_at", ""),
        "agent_count": len(agents),
        "agents": agents,
    }


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", str(value or ""))
    return tuple(int(part) for part in parts[:4]) or (0,)


def is_newer_version(latest: str, current: str = __version__) -> bool:
    return _version_tuple(latest) > _version_tuple(current)


def fetch_latest_pypi_version(timeout: float = 5.0) -> str:
    request = urllib.request.Request(
        PYPI_JSON_URL,
        headers={"Accept": "application/json", "User-Agent": f"vault-for-llm/{__version__}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("unable to fetch latest version from PyPI") from exc
    latest = str((payload.get("info") or {}).get("version") or "").strip()
    if not latest:
        raise RuntimeError("PyPI response did not include a latest version")
    return latest


def build_update_status(
    *,
    latest_version: str | None = None,
    check_pypi: bool = False,
    path: str | Path | None = None,
) -> dict[str, Any]:
    registry = list_agents(path)
    latest_error = ""
    resolved_latest = latest_version or ""
    if check_pypi:
        try:
            resolved_latest = fetch_latest_pypi_version()
        except RuntimeError as exc:
            latest_error = str(exc)
    update_available = bool(resolved_latest and is_newer_version(resolved_latest, __version__))
    projects = sorted({agent.get("project_dir", "") for agent in registry["agents"] if agent.get("project_dir")})
    startup_commands = ["vault update-status"]
    for project in projects:
        startup_commands.append(f"vault automation handoff --project-dir {project}")
    payload = {
        "checked_at": utc_now_iso(),
        "installed_version": __version__,
        "latest_version": resolved_latest or __version__,
        "update_available": update_available,
        "latest_version_source": "pypi" if check_pypi and resolved_latest else ("argument" if latest_version else "installed"),
        "latest_version_error": latest_error,
        "registry_path": registry["registry_path"],
        "agent_count": registry["agent_count"],
        "agents": registry["agents"],
        "projects": projects,
        "startup_commands": startup_commands,
        "next_steps": _update_next_steps(update_available=update_available, latest_version=resolved_latest, projects=projects),
    }
    return payload


def _update_next_steps(*, update_available: bool, latest_version: str, projects: list[str]) -> list[str]:
    steps: list[str] = []
    if update_available:
        steps.append(f"Review release notes and upgrade Vault-for-LLM to {latest_version}.")
    else:
        steps.append("Vault-for-LLM is up to date for the known version source.")
    if projects:
        steps.append("Run the latest automation handoff before starting agent work.")
    else:
        steps.append("Register at least one agent with `vault agent register` or `vault setup-agent`.")
    return steps


def write_update_status(payload: dict[str, Any], path: str | Path | None = None) -> Path:
    status_file = Path(path).expanduser() if path else update_status_path()
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return status_file
