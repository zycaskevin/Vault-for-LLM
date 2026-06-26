"""Automation policy defaults and parsing helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

AUTOMATION_MODES = {"conservative", "balanced", "autonomous"}
DEFAULT_MODE = "balanced"
POLICY_FILE = "automation_policy.yaml"


DEFAULT_POLICIES: dict[str, dict[str, Any]] = {
    "conservative": {
        "mode": "conservative",
        "auto_archive_expired": False,
        "cold_store_used_expired": False,
        "protect_used_expired": True,
        "protected_scopes": ["private"],
        "protected_sensitivities": ["high", "restricted"],
        "auto_apply_safe_metadata": False,
        "dream_write_candidates": False,
        "forgetting_write_candidates": False,
        "session_capture_write_candidates": False,
        "auto_promote_low_risk_candidates": False,
        "auto_promote_allowed_sources": ["session_capture"],
        "auto_promote_allowed_memory_types": ["session_lesson"],
        "auto_promote_allowed_scopes": ["project", "shared", "public"],
        "auto_promote_allowed_sensitivities": ["low"],
        "auto_promote_min_trust": 0.65,
        "auto_promote_max_per_run": 3,
        "auto_promote_requires_source_ref": True,
        "write_reports": True,
        "dream_checks": ["freshness", "dedup", "convergence", "metadata", "orphans"],
        "review_thresholds": {
            "expired_active": 1,
            "used_expired": 1,
            "pending_candidates": 1,
            "duplicate_groups": 1,
            "weak_metadata": 1,
        },
    },
    "balanced": {
        "mode": "balanced",
        "auto_archive_expired": True,
        "cold_store_used_expired": True,
        "protect_used_expired": True,
        "protected_scopes": ["private"],
        "protected_sensitivities": ["high", "restricted"],
        "auto_apply_safe_metadata": False,
        "dream_write_candidates": True,
        "forgetting_write_candidates": True,
        "session_capture_write_candidates": False,
        "auto_promote_low_risk_candidates": False,
        "auto_promote_allowed_sources": ["session_capture"],
        "auto_promote_allowed_memory_types": ["session_lesson"],
        "auto_promote_allowed_scopes": ["project", "shared", "public"],
        "auto_promote_allowed_sensitivities": ["low"],
        "auto_promote_min_trust": 0.65,
        "auto_promote_max_per_run": 3,
        "auto_promote_requires_source_ref": True,
        "write_reports": True,
        "dream_checks": ["freshness", "dedup", "convergence", "metadata", "orphans"],
        "review_thresholds": {
            "expired_active": 5,
            "used_expired": 1,
            "pending_candidates": 10,
            "duplicate_groups": 1,
            "weak_metadata": 10,
        },
    },
    "autonomous": {
        "mode": "autonomous",
        "auto_archive_expired": True,
        "cold_store_used_expired": True,
        "protect_used_expired": True,
        "protected_scopes": ["private"],
        "protected_sensitivities": ["high", "restricted"],
        "auto_apply_safe_metadata": False,
        "dream_write_candidates": True,
        "forgetting_write_candidates": True,
        "session_capture_write_candidates": False,
        "auto_promote_low_risk_candidates": False,
        "auto_promote_allowed_sources": ["session_capture"],
        "auto_promote_allowed_memory_types": ["session_lesson"],
        "auto_promote_allowed_scopes": ["project", "shared", "public"],
        "auto_promote_allowed_sensitivities": ["low"],
        "auto_promote_min_trust": 0.65,
        "auto_promote_max_per_run": 3,
        "auto_promote_requires_source_ref": True,
        "write_reports": True,
        "dream_checks": ["freshness", "dedup", "convergence", "metadata", "orphans"],
        "review_thresholds": {
            "expired_active": 20,
            "used_expired": 5,
            "pending_candidates": 50,
            "duplicate_groups": 5,
            "weak_metadata": 25,
        },
    },
}


def default_policy(mode: str = DEFAULT_MODE) -> dict[str, Any]:
    mode = normalize_mode(mode)
    return json.loads(json.dumps(DEFAULT_POLICIES[mode]))


def load_policy(project_dir: str | Path, *, mode: str | None = None) -> dict[str, Any]:
    project = Path(project_dir)
    base = default_policy(mode or DEFAULT_MODE)
    path = project / POLICY_FILE
    if not path.exists():
        return base
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{POLICY_FILE} must contain a YAML object")
    loaded_mode = loaded.get("mode") or mode or DEFAULT_MODE
    base = default_policy(str(loaded_mode))
    return deep_merge(base, loaded)


def write_policy(project_dir: str | Path, *, mode: str = DEFAULT_MODE, overwrite: bool = False) -> str:
    project = Path(project_dir)
    path = project / POLICY_FILE
    if path.exists() and not overwrite:
        return str(path.relative_to(project))
    payload = default_policy(mode)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return str(path.relative_to(project))


def normalize_mode(mode: str) -> str:
    value = str(mode or DEFAULT_MODE).strip().lower()
    if value not in AUTOMATION_MODES:
        raise ValueError(f"automation mode must be one of: {', '.join(sorted(AUTOMATION_MODES))}")
    return value


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    out["mode"] = normalize_mode(str(out.get("mode") or DEFAULT_MODE))
    return out


def policy_list(policy: dict[str, Any], key: str) -> list[str]:
    value = policy.get(key, [])
    if isinstance(value, str):
        values = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        values = [str(part).strip() for part in value]
    else:
        values = []
    return [part.lower() for part in values if part]


def policy_float(policy: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(policy.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def policy_int(policy: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(policy.get(key, default))
    except (TypeError, ValueError):
        return int(default)
