"""Local GUI console public API for Vault-for-LLM."""

from __future__ import annotations

from .gui_api import (
    gui_agent_dashboard,
    gui_candidate,
    gui_candidates,
    gui_daily_report,
    gui_documents,
    gui_entry,
    gui_overview,
    gui_read_range,
    gui_review_candidate,
    gui_search,
    gui_task,
    gui_tasks,
)
from .gui_server import DEFAULT_HOST, DEFAULT_PORT, make_gui_handler, run_gui


def cmd_gui(args) -> None:
    from .cli_context import find_project_dir

    run_gui(
        find_project_dir(),
        host=str(getattr(args, "host", DEFAULT_HOST) or DEFAULT_HOST),
        port=int(getattr(args, "port", DEFAULT_PORT) or DEFAULT_PORT),
        open_browser=not bool(getattr(args, "no_open", False)),
        auth_token=getattr(args, "auth_token", None),
        no_auth=bool(getattr(args, "no_auth", False)),
        language=getattr(args, "language", "zh-Hant"),
    )

__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "cmd_gui",
    "make_gui_handler",
    "run_gui",
    "gui_agent_dashboard",
    "gui_candidate",
    "gui_candidates",
    "gui_daily_report",
    "gui_documents",
    "gui_entry",
    "gui_overview",
    "gui_read_range",
    "gui_review_candidate",
    "gui_search",
    "gui_task",
    "gui_tasks",
]
