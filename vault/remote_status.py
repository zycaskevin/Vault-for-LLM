"""Local-first remote sharing status for Supabase-backed Vault setups."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vault.agent_registry import list_agents


REMOTE_READER_FILES = {
    "shell": "remote-reader-smoke.sh",
    "n8n": "n8n-remote-reader.workflow.json",
    "coze": "coze-supabase-vault-openapi.json",
    "readme": "README-remote-reader.md",
}
SYNC_TEMPLATE_FILES = {
    "cron": "supabase-sync.cron",
    "launchagent": "com.zycaskevin.vault-for-llm.supabase-sync.plist",
    "n8n": "n8n-supabase-sync.workflow.json",
    "realtime": "supabase-realtime-sync.sh",
    "readme": "README-supabase-sync.md",
}
SETUP_FILES = {
    "guide": "README-supabase-setup.md",
    "read_policy": "supabase-read-policy.sql",
}
ACCESS_FILES = {
    "preset": "agent-access-preset.json",
    "presets": "AGENT_ACCESS_PRESETS.md",
    "roster": "agent-roster.json",
    "matrix": "AGENT_ACCESS_MATRIX.md",
    "layout": "hybrid-vault-layout.json",
}
SYNC_REPORT_CANDIDATES = (
    "reports/supabase-sync-latest.json",
    "reports/remote-sync-latest.json",
    "agent-install/supabase-sync-latest.json",
)


def build_remote_status(
    project_dir: str | Path,
    *,
    agent_id: str = "",
    max_sync_age_minutes: int = 24 * 60,
) -> dict[str, Any]:
    """Build an offline status view of local-to-remote memory sharing."""
    project = Path(project_dir).expanduser().resolve()
    install_dir = project / "agent-install"
    local = _local_db_status(project / "vault.db")
    setup = _file_set_status(install_dir, SETUP_FILES)
    remote_reader = _file_set_status(install_dir, REMOTE_READER_FILES)
    sync_templates = _file_set_status(install_dir, SYNC_TEMPLATE_FILES)
    access = _access_status(install_dir)
    registry = _registry_status(project, agent_id=agent_id)
    env = _supabase_env_status()
    report = _sync_report_status(project, max_age_minutes=max_sync_age_minutes)

    configured = bool(
        env["url_configured"]
        or env["anon_key_configured"]
        or any(remote_reader["targets"].values())
        or any(sync_templates["targets"].values())
        or any(setup["targets"].values())
    )
    near_realtime = bool(sync_templates["targets"].get("realtime"))
    warnings = _warnings(
        local=local,
        env=env,
        configured=configured,
        report=report,
        remote_reader=remote_reader,
        sync_templates=sync_templates,
        access=access,
    )
    next_actions = _next_actions(
        configured=configured,
        env=env,
        report=report,
        remote_reader=remote_reader,
        sync_templates=sync_templates,
        access=access,
    )
    ok = bool(local["db_exists"]) and not any(item["severity"] == "high" for item in warnings)
    return {
        "ok": ok,
        "project_dir": str(project),
        "source_of_truth": "local_sqlite",
        "remote_model": {
            "mode": "supabase_reviewed_read_copy_with_candidate_inbox",
            "direction": "local_to_supabase_active_memory_plus_remote_to_local_candidates",
            "bidirectional": False,
            "candidate_requests": True,
            "realtime": near_realtime,
            "realtime_kind": "near_realtime_push" if near_realtime else "scheduled_or_manual",
            "message": "Local vault.db remains the source of truth; Supabase is a shared reviewed read copy plus a remote candidate request inbox. Active knowledge is still not multi-master sync.",
        },
        "local": local,
        "supabase": env,
        "setup": setup,
        "remote_reader": remote_reader,
        "sync": {
            "templates": sync_templates,
            "last_report": report,
        },
        "agent_access": access,
        "registry": registry,
        "warnings": warnings,
        "next_actions": next_actions,
    }


def _local_db_status(db_path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "db_path": str(db_path),
        "db_exists": db_path.exists(),
        "knowledge_count": 0,
        "document_map_nodes": 0,
        "document_map_claims": 0,
        "content_hash_count": 0,
        "latest_updated_at": "",
        "error": "",
    }
    if not db_path.exists():
        return payload
    try:
        conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            payload["knowledge_count"] = _count(conn, "knowledge")
            payload["document_map_nodes"] = _count(conn, "knowledge_nodes")
            payload["document_map_claims"] = _count(conn, "knowledge_claims")
            if _has_column(conn, "knowledge", "content_hash"):
                payload["content_hash_count"] = conn.execute(
                    "SELECT COUNT(*) FROM knowledge WHERE COALESCE(content_hash, '') <> ''"
                ).fetchone()[0]
            if _has_column(conn, "knowledge", "updated_at"):
                payload["latest_updated_at"] = str(
                    conn.execute("SELECT MAX(updated_at) FROM knowledge").fetchone()[0] or ""
                )
        finally:
            conn.close()
    except sqlite3.Error as exc:
        payload["error"] = "unable_to_read_local_vault"
        payload["message"] = str(exc)
    return payload


def _count(conn: sqlite3.Connection, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    )


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    if not _table_exists(conn, table):
        return False
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return column in {str(row[1]) for row in rows}


def _file_set_status(base_dir: Path, files: dict[str, str]) -> dict[str, Any]:
    targets: dict[str, bool] = {}
    paths: dict[str, str] = {}
    for key, filename in files.items():
        path = base_dir / filename
        exists = path.exists()
        targets[key] = exists
        if exists:
            paths[key] = str(path)
    return {
        "directory": str(base_dir),
        "exists": base_dir.exists(),
        "targets": targets,
        "paths": paths,
    }


def _access_status(install_dir: Path) -> dict[str, Any]:
    files = _file_set_status(install_dir, ACCESS_FILES)
    roster = _read_json_file(install_dir / "agent-roster.json")
    preset = _read_json_file(install_dir / "agent-access-preset.json")
    agents = roster.get("agents", []) if isinstance(roster.get("agents"), list) else []
    remote_readers = [
        str(item.get("agent_id") or "")
        for item in agents
        if isinstance(item, dict) and item.get("remote_reader")
    ]
    shared_writers = [
        str(item.get("agent_id") or "")
        for item in agents
        if isinstance(item, dict) and item.get("can_write_shared")
    ]
    promoters = [
        str(item.get("agent_id") or "")
        for item in agents
        if isinstance(item, dict) and item.get("can_promote")
    ]
    return {
        **files,
        "agent_count": len(agents),
        "remote_readers": sorted(item for item in remote_readers if item),
        "shared_writers": sorted(item for item in shared_writers if item),
        "promoters": sorted(item for item in promoters if item),
        "current_agent_preset": preset if preset else {},
    }


def _registry_status(project: Path, *, agent_id: str = "") -> dict[str, Any]:
    try:
        registry = list_agents()
    except Exception as exc:  # pragma: no cover - defensive for corrupted home registry
        return {"available": False, "error": str(exc), "agents": []}
    project_text = str(project)
    agents = [
        item
        for item in registry.get("agents", [])
        if str(item.get("project_dir") or "") == project_text
        or str(item.get("private_project_dir") or "") == project_text
    ]
    if agent_id:
        agents = [item for item in agents if str(item.get("agent_id") or "") == agent_id]
    return {
        "available": True,
        "registry_path": registry.get("registry_path", ""),
        "agent_count": len(agents),
        "agents": agents,
    }


def _supabase_env_status() -> dict[str, Any]:
    anon = bool(os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_PUBLISHABLE_KEY"))
    service = bool(os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY"))
    return {
        "url_configured": bool(os.environ.get("SUPABASE_URL")),
        "anon_key_configured": anon,
        "service_role_key_present": service,
        "key_guidance": "Use anon/publishable keys for remote readers; keep service-role keys only on trusted sync hosts.",
    }


def _sync_report_status(project: Path, *, max_age_minutes: int) -> dict[str, Any]:
    candidates = [project / relative for relative in SYNC_REPORT_CANDIDATES]
    existing = next((path for path in candidates if path.exists()), None)
    payload: dict[str, Any] = {
        "path": str(existing) if existing else "",
        "exists": bool(existing),
        "status": "unknown",
        "last_synced_at": "",
        "age_minutes": None,
        "stale": None,
        "checked_candidates": [str(path) for path in candidates],
    }
    if not existing:
        return payload
    data = _read_json_file(existing)
    last_synced_at = str(
        data.get("last_synced_at")
        or data.get("synced_at")
        or data.get("completed_at")
        or data.get("checked_at")
        or ""
    )
    age = _age_minutes(last_synced_at)
    payload.update(
        {
            "status": str(data.get("status") or data.get("ok") or "reported"),
            "last_synced_at": last_synced_at,
            "age_minutes": age,
            "stale": None if age is None else age > max_age_minutes,
            "summary": {key: data.get(key) for key in ("new", "updated", "deleted", "processed", "errors") if key in data},
        }
    )
    return payload


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _age_minutes(value: str) -> float | None:
    if not value:
        return None
    try:
        text = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    return round(delta.total_seconds() / 60.0, 3)


def _warnings(
    *,
    local: dict[str, Any],
    env: dict[str, Any],
    configured: bool,
    report: dict[str, Any],
    remote_reader: dict[str, Any],
    sync_templates: dict[str, Any],
    access: dict[str, Any],
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    if not local.get("db_exists"):
        warnings.append({"severity": "high", "code": "local_db_missing", "message": "Local vault.db is missing; run `vault init` or point --project-dir at the shared project vault."})
    if configured and not env.get("url_configured"):
        warnings.append({"severity": "medium", "code": "supabase_url_missing", "message": "Supabase sharing templates exist, but SUPABASE_URL is not set in this environment."})
    if env.get("service_role_key_present"):
        warnings.append({"severity": "medium", "code": "service_role_key_present", "message": "A service-role key is present. Use it only on a trusted sync host, never inside remote-reader agents."})
    if any(sync_templates["targets"].values()) and not report.get("exists"):
        warnings.append({"severity": "medium", "code": "sync_report_missing", "message": "Sync templates exist, but no local sync report was found; remote freshness is unknown."})
    if report.get("stale") is True:
        warnings.append({"severity": "medium", "code": "sync_report_stale", "message": "The latest sync report is older than the allowed freshness window."})
    if any(remote_reader["targets"].values()) and not env.get("anon_key_configured"):
        warnings.append({"severity": "medium", "code": "remote_reader_key_missing", "message": "Remote-reader templates exist, but no anon/publishable key is set for read-only agents."})
    if access.get("agent_count", 0) and not access.get("remote_readers"):
        warnings.append({"severity": "low", "code": "no_remote_reader_agent", "message": "Agent roster exists but no agent is marked as a remote reader."})
    return warnings


def _next_actions(
    *,
    configured: bool,
    env: dict[str, Any],
    report: dict[str, Any],
    remote_reader: dict[str, Any],
    sync_templates: dict[str, Any],
    access: dict[str, Any],
) -> list[str]:
    actions: list[str] = []
    if not configured:
        actions.append("Run `vault setup-agent --features core,mcp,supabase --supabase-setup simple --remote-reader shell` to generate a guided remote-reader setup.")
    if any(sync_templates["targets"].values()) and not report.get("exists"):
        actions.append("After the first trusted sync, write a small JSON report to reports/supabase-sync-latest.json so agents can see remote freshness.")
    if any(remote_reader["targets"].values()) and not env.get("anon_key_configured"):
        actions.append("Set SUPABASE_URL and SUPABASE_ANON_KEY/SUPABASE_PUBLISHABLE_KEY before running `vault remote smoke`.")
    if access.get("agent_count", 0) and not access.get("remote_readers"):
        actions.append("Review agent-roster.json and mark hosted readers with remote_reader=true or use the remote-readonly-agent preset.")
    actions.append("Use `vault remote doctor --agent-id <agent>` only after credentials and Supabase SQL policy are configured.")
    return actions
