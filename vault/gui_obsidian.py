"""Obsidian conflict helpers for the local Vault GUI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .gui_format import confirmation_token
from .import_obsidian import resolve_obsidian_conflict


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_manifest(project: Path) -> dict[str, Any]:
    return _load_json_file(project / ".vault" / "obsidian-import-manifest.json")


def friendly_obsidian_conflict_title(source_path: str) -> str:
    return f"筆記兩邊都改過：{source_path}"


def friendly_obsidian_conflict_reason() -> str:
    return "Obsidian 和 Vault 都有新版本，請打開詳情後選擇要保留哪一邊。"


def list_obsidian_conflicts(project: Path, *, limit: int = 20) -> list[dict[str, Any]]:
    """Return compact open Obsidian conflicts without loading note bodies."""
    manifest = _load_manifest(project)
    notes = manifest.get("notes") if isinstance(manifest.get("notes"), dict) else {}
    conflicts: list[dict[str, Any]] = []
    for source_path, entry in notes.items():
        if not isinstance(entry, dict) or entry.get("status") != "conflict":
            continue
        source_text = str(source_path or "")
        conflicts.append(
            {
                "id": source_text,
                "source_path": source_text,
                "raw_path": str(entry.get("raw_path") or ""),
                "reason": friendly_obsidian_conflict_reason(),
                "technical_reason": str(entry.get("reason") or "obsidian_source_and_vault_raw_both_changed"),
                "title": friendly_obsidian_conflict_title(source_text),
                "status": "conflict",
                "folder_rule": str(entry.get("folder_rule") or ""),
                "current_source_hash": str(entry.get("current_source_hash") or ""),
                "current_raw_hash": str(entry.get("current_raw_hash") or ""),
                "pending_source_hash": str(entry.get("pending_source_hash") or ""),
                "next_action": "打開詳情，選擇接受 Obsidian、接受 Vault，或保留兩份。",
            }
        )
    return sorted(conflicts, key=lambda item: item["source_path"])[: max(0, int(limit or 20))]


def _obsidian_vault_dir(project: Path, manifest: dict[str, Any]) -> Path | None:
    raw = str(manifest.get("vault_dir") or "").strip()
    if not raw:
        return None
    try:
        path = Path(raw).expanduser().resolve()
    except OSError:
        return None
    return path if path.is_dir() else None


def _safe_project_file(project: Path, relative_path: str) -> Path | None:
    relative = str(relative_path or "").strip()
    if not relative:
        return None
    path = (project / relative).resolve()
    try:
        path.relative_to(project.resolve())
    except ValueError:
        return None
    return path


def _safe_obsidian_file(vault_dir: Path, source_path: str) -> Path | None:
    relative = Path(str(source_path or "")).as_posix().lstrip("/")
    if not relative or relative.startswith("../") or "/../" in relative:
        return None
    path = (vault_dir / relative).resolve()
    try:
        path.relative_to(vault_dir.resolve())
    except ValueError:
        return None
    return path


def gui_obsidian_conflict(project_dir: str | Path, source_path: str) -> dict[str, Any]:
    """Return one Obsidian import conflict for explicit GUI resolution."""
    project = Path(project_dir)
    source = Path(str(source_path or "")).as_posix().strip("/")
    if not source:
        return {"status": "error", "error": "invalid_source_path"}
    manifest = _load_manifest(project)
    notes = manifest.get("notes") if isinstance(manifest.get("notes"), dict) else {}
    entry = notes.get(source)
    if not isinstance(entry, dict) or entry.get("status") != "conflict":
        return {"status": "error", "error": "not_found", "source_path": source}
    obsidian_root = _obsidian_vault_dir(project, manifest)
    if obsidian_root is None:
        return {"status": "blocked", "reason": "Obsidian vault path is missing or unavailable."}
    source_file = _safe_obsidian_file(obsidian_root, source)
    raw_file = _safe_project_file(project, str(entry.get("raw_path") or ""))
    if source_file is None or raw_file is None:
        return {"status": "error", "error": "unsafe_conflict_path", "source_path": source}
    if not source_file.exists() or not raw_file.exists():
        return {"status": "error", "error": "conflict_file_missing", "source_path": source}
    source_text = source_file.read_text(encoding="utf-8")
    raw_text = raw_file.read_text(encoding="utf-8")
    return {
        "status": "ok",
        "conflict": {
            "id": source,
            "source_path": source,
            "raw_path": str(entry.get("raw_path") or ""),
            "title": friendly_obsidian_conflict_title(source),
            "reason": friendly_obsidian_conflict_reason(),
            "technical_reason": str(entry.get("reason") or "obsidian_source_and_vault_raw_both_changed"),
            "status": "conflict",
            "obsidian": {
                "path": str(source_file),
                "content": source_text,
                "content_length": len(source_text),
            },
            "vault": {
                "path": str(raw_file),
                "content": raw_text,
                "content_length": len(raw_text),
            },
            "confirmation": {
                "accept-obsidian": confirmation_token(source, "accept-obsidian"),
                "accept-vault": confirmation_token(source, "accept-vault"),
                "keep-both": confirmation_token(source, "keep-both"),
            },
            "safety": {
                "requires_confirmation": True,
                "no_silent_overwrite": True,
                "keep_both_available": True,
            },
        },
    }


def gui_resolve_obsidian_conflict(
    project_dir: str | Path,
    source_path: str,
    *,
    resolution: str,
    confirm: str = "",
) -> dict[str, Any]:
    """Resolve an Obsidian conflict from the local GUI with explicit confirmation."""
    project = Path(project_dir)
    source = Path(str(source_path or "")).as_posix().strip("/")
    resolution_i = str(resolution or "").strip().lower()
    if resolution_i not in {"accept-obsidian", "accept-vault", "keep-both"}:
        return {"status": "error", "error": "invalid_resolution"}
    if not source or str(confirm or "") != confirmation_token(source, resolution_i):
        return {"status": "error", "error": "confirmation_required"}
    manifest = _load_manifest(project)
    obsidian_root = _obsidian_vault_dir(project, manifest)
    if obsidian_root is None:
        return {"status": "blocked", "reason": "Obsidian vault path is missing or unavailable."}
    try:
        resolution_payload = resolve_obsidian_conflict(
            project_dir=project,
            vault_dir=obsidian_root,
            source_path=source,
            resolution=resolution_i,
            conflict_inbox=True,
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        return {"status": "error", "error": "resolution_failed", "reason": str(exc)}
    return {
        "status": "ok",
        "resolution": resolution_i,
        "conflict": {
            "source_path": source,
            "raw_path": resolution_payload.get("raw_path", ""),
            "written": resolution_payload.get("written", []),
            "conflict_inbox_path": resolution_payload.get("conflict_inbox_path", ""),
        },
    }
