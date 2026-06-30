"""CLI entrypoint for the consumer-facing daily memory report."""

from __future__ import annotations

from typing import Any, Callable

from .daily_report import build_daily_report, render_daily_report_text


def cmd_daily_report(
    args: Any,
    *,
    find_project_dir: Callable[[], Any],
    json_print: Callable[..., None],
) -> None:
    """Print or write the short daily memory report."""
    payload = build_daily_report(
        find_project_dir(),
        limit=getattr(args, "limit", 5),
        min_events=getattr(args, "min_events", 5),
        write_report=bool(getattr(args, "write_report", False)),
        report_path=getattr(args, "report_path", ""),
    )
    if getattr(args, "json", False) or getattr(args, "pretty", False):
        json_print(payload, pretty=bool(getattr(args, "pretty", False)))
        return
    print(render_daily_report_text(payload), end="")
