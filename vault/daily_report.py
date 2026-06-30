"""Consumer-facing daily memory report.

This module intentionally reuses the existing automation brief and review
summary. It gives humans a tiny approval surface while agents keep using the
larger automation/MCP toolbox.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .automation import automation_brief, automation_review_summary


def build_daily_report(
    project_dir: str | Path,
    *,
    limit: int = 5,
    min_events: int = 5,
    write_report: bool = False,
    report_path: str | Path = "",
) -> dict[str, Any]:
    """Build a short, human-first daily memory report.

    The report is read-only. It may write a JSON/Markdown artifact when
    requested, but it never promotes, archives, deletes, or changes memory.
    """
    project = Path(project_dir)
    limit_i = max(1, min(int(limit or 5), 20))
    generated_at = datetime.now(timezone.utc).isoformat()
    brief = automation_brief(project, limit=limit_i, review_limit=limit_i, min_events=min_events)
    review = automation_review_summary(project, limit=limit_i, min_events=min_events)
    brief_summary = brief.get("summary") or {}
    cards = [_compact_card(card) for card in (review.get("cards") or [])[:limit_i]]
    quiet_actions = _quiet_actions(brief_summary)
    payload = {
        "action": "daily-report",
        "generated_at": generated_at,
        "project_dir": str(project),
        "status": "completed" if brief.get("status") == "completed" else brief.get("status", "blocked"),
        "headline": _headline(brief_summary, cards),
        "summary": {
            "auto_kept_or_observed": int(quiet_actions.get("total", 0)),
            "pending_candidates": int(brief_summary.get("pending_candidates") or 0),
            "needs_confirmation": len(cards),
            "learning_rules": int(brief_summary.get("learning_rules") or 0),
            "expired_active": int(brief_summary.get("expired_active") or 0),
            "cold_store_preview": int(brief_summary.get("cold_store_preview") or 0),
            "cold_store_applied": int(brief_summary.get("cold_store_applied") or 0),
            "registered_agents": int((brief.get("agent_health") or {}).get("agent_count") or 0),
        },
        "quiet_actions": quiet_actions,
        "review_cards": cards,
        "daily_choices": _daily_choices(cards),
        "paths": {
            "json": "",
            "markdown": "",
        },
        "safety": {
            "read_only": True,
            "writes_active_memory": False,
            "writes_candidates": False,
            "hard_delete": False,
            "includes_raw_candidate_content": False,
            "intended_for": "humans; agents should keep using automation/MCP profiles",
        },
        "next_action": (
            "Review the cards only. Use accept/reject/defer feedback; do not open raw memory unless a card asks for evidence."
            if cards
            else "No human action needed today. Keep the agent automation schedule running."
        ),
    }
    if write_report:
        payload["paths"] = _write_daily_report(project, payload, report_path=report_path)
    return payload


def render_daily_report_text(payload: dict[str, Any]) -> str:
    """Render a concise terminal-friendly daily report."""
    summary = payload.get("summary") or {}
    lines = [
        "Vault Daily Memory Report",
        "",
        str(payload.get("headline") or ""),
        "",
        "Today:",
        f"  auto-kept/observed: {summary.get('auto_kept_or_observed', 0)}",
        f"  pending candidates: {summary.get('pending_candidates', 0)}",
        f"  needs your confirmation: {summary.get('needs_confirmation', 0)}",
        f"  learning rules: {summary.get('learning_rules', 0)}",
        f"  expired active memory: {summary.get('expired_active', 0)}",
    ]
    cards = payload.get("review_cards") or []
    lines += ["", "Needs Your Decision:"]
    if not cards:
        lines.append("  none")
    for index, card in enumerate(cards, start=1):
        lines += [
            f"  {index}. {card.get('title') or card.get('id') or card.get('kind')}",
            f"     suggested: {card.get('suggested_decision')}",
            f"     why: {card.get('reason')}",
            f"     choices: {', '.join(card.get('choices') or [])}",
        ]
    lines += ["", f"Next: {payload.get('next_action', '')}"]
    paths = payload.get("paths") or {}
    if paths.get("markdown"):
        lines.append(f"Markdown: {paths['markdown']}")
    if paths.get("json"):
        lines.append(f"JSON: {paths['json']}")
    return "\n".join(lines).rstrip() + "\n"


def _compact_card(card: dict[str, Any]) -> dict[str, Any]:
    action = str(card.get("recommended_action") or "review").strip() or "review"
    return {
        "kind": card.get("kind", ""),
        "id": card.get("id", ""),
        "title": card.get("title", ""),
        "priority": int(card.get("priority") or 0),
        "suggested_decision": _suggested_decision(action),
        "recommended_action": action,
        "reason": card.get("reason", ""),
        "safe_action": card.get("safe_action") or "Review compact evidence first.",
        "choices": _choices_for_action(action),
        "requires_human_decision": bool(card.get("requires_human_decision", True)),
    }


def _suggested_decision(action: str) -> str:
    text = action.lower()
    if "private" in text:
        return "keep private"
    if "share" in text or "promote" in text:
        return "approve if the source is correct"
    if "archive" in text or "cold" in text:
        return "allow cleanup only after evidence review"
    if "reject" in text:
        return "reject"
    return "review"


def _choices_for_action(action: str) -> list[str]:
    text = action.lower()
    if "archive" in text or "cold" in text:
        return ["keep active", "summarize then cold-store", "defer"]
    if "promote" in text or "candidate" in text:
        return ["keep", "make private", "do not remember", "defer"]
    return ["accept", "reject", "defer"]


def _quiet_actions(summary: dict[str, Any]) -> dict[str, int]:
    items = {
        "auto_promoted": int(summary.get("auto_promote_promoted") or 0),
        "auto_promote_skipped": int(summary.get("auto_promote_skipped") or 0),
        "cold_store_applied": int(summary.get("cold_store_applied") or 0),
        "cold_store_preview": int(summary.get("cold_store_preview") or 0),
    }
    items["total"] = sum(items.values())
    return items


def _daily_choices(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "card_id": card.get("id", ""),
            "title": card.get("title", ""),
            "choices": card.get("choices", []),
        }
        for card in cards
    ]


def _headline(summary: dict[str, Any], cards: list[dict[str, Any]]) -> str:
    needs = len(cards)
    pending = int(summary.get("pending_candidates") or 0)
    if needs:
        return f"{needs} memory decision(s) need your confirmation; {pending} candidate(s) are waiting."
    if pending:
        return f"No urgent decision today; {pending} candidate(s) can wait for an agent review pass."
    return "No human memory decision is needed today."


def _write_daily_report(project: Path, payload: dict[str, Any], *, report_path: str | Path = "") -> dict[str, str]:
    report_dir = project / "reports" / "daily"
    report_dir.mkdir(parents=True, exist_ok=True)
    if report_path:
        raw = Path(report_path)
        json_path = raw if raw.is_absolute() else project / raw
        resolved = json_path.expanduser().resolve()
        allowed = report_dir.expanduser().resolve()
        if allowed != resolved and allowed not in resolved.parents:
            raise ValueError("daily report path must stay under reports/daily")
        json_path = resolved
    else:
        json_path = report_dir / "daily-report-latest.json"
    markdown_path = json_path.with_suffix(".md")
    data = dict(payload)
    data["paths"] = {
        "json": _relative_to_project(project, json_path),
        "markdown": _relative_to_project(project, markdown_path),
    }
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_daily_markdown(data), encoding="utf-8")
    return data["paths"]


def _render_daily_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# Vault Daily Memory Report",
        "",
        f"- generated_at: `{_md(payload.get('generated_at', ''))}`",
        f"- status: `{_md(payload.get('status', ''))}`",
        f"- headline: {_md(payload.get('headline', ''))}",
        "",
        "## Today",
        "",
        f"- auto-kept/observed: `{int(summary.get('auto_kept_or_observed') or 0)}`",
        f"- pending candidates: `{int(summary.get('pending_candidates') or 0)}`",
        f"- needs confirmation: `{int(summary.get('needs_confirmation') or 0)}`",
        f"- learning rules: `{int(summary.get('learning_rules') or 0)}`",
        f"- expired active memory: `{int(summary.get('expired_active') or 0)}`",
        "",
        "## Needs Your Decision",
        "",
    ]
    cards = payload.get("review_cards") or []
    if not cards:
        lines.append("No human decision is needed today.")
    for index, card in enumerate(cards, start=1):
        lines += [
            f"### {index}. {_md(card.get('title') or card.get('id') or card.get('kind') or 'Review item')}",
            "",
            f"- suggested: `{_md(card.get('suggested_decision', 'review'))}`",
            f"- why: {_md(card.get('reason', ''))}",
            f"- safe action: {_md(card.get('safe_action', ''))}",
            f"- choices: `{_md(', '.join(card.get('choices') or []))}`",
            "",
        ]
    lines += [
        "## Safety",
        "",
        "- This report is read-only.",
        "- It does not include raw candidate content.",
        "- It does not promote, archive, delete, or change memory.",
        "",
        f"Next: {_md(payload.get('next_action', ''))}",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _relative_to_project(project: Path, path: Path) -> str:
    try:
        return str(path.relative_to(project))
    except ValueError:
        return str(path)


def _md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()
