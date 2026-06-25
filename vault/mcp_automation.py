"""MCP handlers for automation, dream, and lifecycle maintenance tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _json_result(payload: dict[str, Any] | list[dict[str, Any]]) -> dict[str, str]:
    return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}


def _project_dir(db_path: str) -> Path:
    return Path(db_path).resolve().parent


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def handle_automation_tool_call(name: str, arguments: dict[str, Any], *, db_path: str) -> dict[str, str] | None:
    """Handle MCP automation and lifecycle calls, or return ``None`` if unknown."""
    arguments = arguments or {}
    project_dir = _project_dir(db_path)

    if name == "vault_automation_inbox":
        from vault.automation import automation_inbox

        payload = automation_inbox(
            project_dir,
            limit=_clamp_int(arguments.get("limit", 5), default=5, minimum=1, maximum=50),
            include_content=bool(arguments.get("include_content", False)),
            include_transcripts=bool(arguments.get("include_transcripts", False)),
            transcript_limit=_clamp_int(
                arguments.get("transcript_limit", 5),
                default=5,
                minimum=1,
                maximum=20,
            ),
            write_handoff=bool(arguments.get("write_handoff", False)),
        )
        return _json_result(payload)

    if name == "vault_automation_activity":
        from vault.automation import automation_activity

        payload = automation_activity(
            project_dir,
            limit=_clamp_int(arguments.get("limit", 5), default=5, minimum=1, maximum=20),
            event_limit=_clamp_int(
                arguments.get("event_limit", 20),
                default=20,
                minimum=1,
                maximum=100,
            ),
        )
        return _json_result(payload)

    if name == "vault_automation_brief":
        from vault.automation import automation_brief

        payload = automation_brief(
            project_dir,
            limit=_clamp_int(arguments.get("limit", 5), default=5, minimum=1, maximum=20),
            review_limit=_clamp_int(arguments.get("review_limit", 5), default=5, minimum=1, maximum=20),
            min_events=_clamp_int(arguments.get("min_events", 5), default=5, minimum=1, maximum=100),
            write_brief=False,
        )
        return _json_result(payload)

    if name == "vault_automation_handoff":
        from vault.automation import automation_handoff

        payload = automation_handoff(
            project_dir,
            source=str(arguments.get("source") or "auto"),
            handoff_path=str(arguments.get("handoff_path") or ""),
        )
        return _json_result(payload)

    if name == "vault_cold_store_expired":
        from vault.db import VaultDB

        with VaultDB(db_path) as db:
            payload = db.cold_store_expired_knowledge(
                limit=_clamp_int(arguments.get("limit", 100), default=100, minimum=1, maximum=1000),
                dry_run=not bool(arguments.get("apply", False)),
                min_usage=_clamp_int(arguments.get("min_usage", 1), default=1, minimum=1, maximum=1000),
                summary_max_chars=_clamp_int(
                    arguments.get("summary_max_chars", 360),
                    default=360,
                    minimum=80,
                    maximum=2000,
                ),
            )
        return _json_result(payload)

    if name == "vault_dream_run":
        from vault.dream import run_dream

        payload = run_dream(
            project_dir,
            mode=arguments.get("mode", "report"),
            checks=arguments.get("checks"),
            limit=arguments.get("limit", 50),
            write_report=bool(arguments.get("write_report", True)),
            write_candidates=bool(arguments.get("write_candidates", False)),
            backup=bool(arguments.get("backup", True)),
        )
        return _json_result(payload)

    return None
