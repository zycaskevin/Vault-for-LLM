"""Runtime startup template install and startup-contract doctor helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _safe_slug(value: object, default: str = "agent") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.-]+", "-", text)
    text = text.strip("-._")
    return text or default


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
    "pipeline_receipt_content",
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


def _has_remote_status_command(value: object) -> bool:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value or "")
    return "remote" in text and "status" in text and "--json" in text


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
    _startup_doctor_check(
        checks,
        name="mcp_remote_status_preflight",
        status="pass" if _has_remote_status_command(mcp.get("cli_preflight")) else "warn",
        path=mcp_path,
        detail=(
            "MCP startup includes CLI remote-status preflight"
            if _has_remote_status_command(mcp.get("cli_preflight"))
            else "MCP startup is missing CLI `vault remote status --json` preflight"
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
    remote_status_step = next(
        (step for step in adapter_sequence if isinstance(step, dict) and step.get("name") == "check_remote_sharing_status"),
        {},
    )
    _startup_doctor_check(
        checks,
        name="adapter_remote_status_step",
        status="pass" if _has_remote_status_command(remote_status_step) else "fail",
        path=adapter_path,
        detail=(
            "adapter startup checks remote sharing status before live remote calls"
            if _has_remote_status_command(remote_status_step)
            else "adapter startup is missing `check_remote_sharing_status`"
        ),
    )
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
    playbook_cli = playbook.get("cli") if isinstance(playbook.get("cli"), dict) else {}
    playbook_safety = playbook.get("safety") or {}
    playbook_prefaces_read_only = all(
        bool(playbook_safety.get(name))
        for name in (
            "fleet_health_preface_read_only",
            "pipeline_receipt_preface_read_only",
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
    _startup_doctor_check(
        checks,
        name="runtime_playbook_remote_status",
        status="pass" if _has_remote_status_command(playbook_cli.get("remote_status")) else "warn",
        path=playbook_path,
        detail=(
            "runtime playbook includes CLI remote-status preflight"
            if _has_remote_status_command(playbook_cli.get("remote_status"))
            else "runtime playbook is missing remote-status startup guidance"
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
            and "vault remote status" in text
        )
        _startup_doctor_check(
            checks,
            name=f"{name}_startup_template",
            status="pass" if ok else "fail",
            path=path,
            detail=(
                "runtime template names the startup-preface handoff contract"
                if ok
                else "runtime template is missing startup-preface handoff or remote-status guidance"
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
            and "remote status" in text
        )
        _startup_doctor_check(
            checks,
            name=name,
            status="pass" if ok else "warn",
            path=path,
            detail=(
                "README documents startup-preface handoff"
                if ok
                else "README is missing startup-preface or remote-status guidance; regenerate setup files for clearer guidance"
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
