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


def normalize_report_language(value: Any = "en") -> str:
    text = str(value or "en").strip()
    lowered = text.lower()
    if lowered in {"zh-hant", "zh_tw", "zh-tw", "tw", "繁中", "繁體", "繁体", "traditional"}:
        return "zh-Hant"
    if lowered in {"zh-cn", "zh_cn", "zh-hans", "cn", "簡中", "简中", "簡體", "简体", "simplified"}:
        return "zh-CN"
    return "en"


def _labels(language: str) -> dict[str, str]:
    lang = normalize_report_language(language)
    if lang == "zh-Hant":
        return {
            "title": "Vault 每日記憶報告",
            "today": "今天",
            "auto_kept": "自動保留/觀察",
            "pending_candidates": "待整理候選記憶",
            "needs_confirmation": "需要你確認",
            "learning_rules": "學習規則",
            "expired_active": "過期活躍記憶",
            "needs_decision": "需要你決定",
            "none": "無",
            "suggested": "建議",
            "why": "原因",
            "choices": "選項",
            "next": "下一步",
            "review": "審核",
            "accept": "接受",
            "reject": "拒絕",
            "defer": "延後",
            "keep": "保留",
            "make_private": "改成私人",
            "do_not_remember": "不要記住",
            "keep_active": "保持活躍",
            "summarize_cold_store": "摘要後冷存",
            "keep_private": "保留為私人記憶",
            "approve_if_source": "來源正確才批准",
            "cleanup_after_review": "看過證據後再允許清理",
            "review_evidence_first": "先看短證據再決定。",
            "next_review_cards": "只看這幾張卡片。用接受/拒絕/延後回饋；除非卡片要求，不需要打開原始記憶。",
            "next_no_action": "今天不需要你處理。讓 Agent 的自動化排程繼續跑。",
            "intended_for": "給人看的短報告；Agent 應繼續使用 automation/MCP 工具",
            "headline_needs": "{needs} 筆記憶決策需要你確認；{pending} 筆候選記憶等待整理。",
            "headline_pending": "今天沒有緊急決策；{pending} 筆候選記憶可以等 Agent 審核。",
            "headline_clear": "今天沒有需要人決定的記憶事項。",
            "generated_at": "產生時間",
            "status": "狀態",
            "headline": "摘要",
            "safety": "安全邊界",
            "read_only": "這份報告是唯讀報告。",
            "no_raw": "不包含原始候選內容。",
            "no_mutation": "不會收進正式記憶、封存、刪除或修改記憶。",
        }
    if lang == "zh-CN":
        return {
            "title": "Vault 每日记忆报告",
            "today": "今天",
            "auto_kept": "自动保留/观察",
            "pending_candidates": "待整理候选记忆",
            "needs_confirmation": "需要你确认",
            "learning_rules": "学习规则",
            "expired_active": "过期活跃记忆",
            "needs_decision": "需要你决定",
            "none": "无",
            "suggested": "建议",
            "why": "原因",
            "choices": "选项",
            "next": "下一步",
            "review": "审核",
            "accept": "接受",
            "reject": "拒绝",
            "defer": "延后",
            "keep": "保留",
            "make_private": "改成私人",
            "do_not_remember": "不要记住",
            "keep_active": "保持活跃",
            "summarize_cold_store": "摘要后冷存",
            "keep_private": "保留为私人记忆",
            "approve_if_source": "来源正确才批准",
            "cleanup_after_review": "看过证据后再允许清理",
            "review_evidence_first": "先看短证据再决定。",
            "next_review_cards": "只看这几张卡片。用接受/拒绝/延后反馈；除非卡片要求，不需要打开原始记忆。",
            "next_no_action": "今天不需要你处理。让 Agent 的自动化排程继续跑。",
            "intended_for": "给人看的短报告；Agent 应继续使用 automation/MCP 工具",
            "headline_needs": "{needs} 条记忆决策需要你确认；{pending} 条候选记忆等待整理。",
            "headline_pending": "今天没有紧急决策；{pending} 条候选记忆可以等 Agent 审核。",
            "headline_clear": "今天没有需要人决定的记忆事项。",
            "generated_at": "生成时间",
            "status": "状态",
            "headline": "摘要",
            "safety": "安全边界",
            "read_only": "这份报告是只读报告。",
            "no_raw": "不包含原始候选内容。",
            "no_mutation": "不会收进正式记忆、归档、删除或修改记忆。",
        }
    return {
        "title": "Vault Daily Memory Report",
        "today": "Today",
        "auto_kept": "auto-kept/observed",
        "pending_candidates": "pending candidates",
        "needs_confirmation": "needs your confirmation",
        "learning_rules": "learning rules",
        "expired_active": "expired active memory",
        "needs_decision": "Needs Your Decision",
        "none": "none",
        "suggested": "suggested",
        "why": "why",
        "choices": "choices",
        "next": "Next",
        "review": "review",
        "accept": "accept",
        "reject": "reject",
        "defer": "defer",
        "keep": "keep",
        "make_private": "make private",
        "do_not_remember": "do not remember",
        "keep_active": "keep active",
        "summarize_cold_store": "summarize then cold-store",
        "keep_private": "keep private",
        "approve_if_source": "approve if the source is correct",
        "cleanup_after_review": "allow cleanup only after evidence review",
        "review_evidence_first": "Review compact evidence first.",
        "next_review_cards": "Review the cards only. Use accept/reject/defer feedback; do not open raw memory unless a card asks for evidence.",
        "next_no_action": "No human action needed today. Keep the agent automation schedule running.",
        "intended_for": "humans; agents should keep using automation/MCP profiles",
        "headline_needs": "{needs} memory decision(s) need your confirmation; {pending} candidate(s) are waiting.",
        "headline_pending": "No urgent decision today; {pending} candidate(s) can wait for an agent review pass.",
        "headline_clear": "No human memory decision is needed today.",
        "generated_at": "generated_at",
        "status": "status",
        "headline": "headline",
        "safety": "Safety",
        "read_only": "This report is read-only.",
        "no_raw": "It does not include raw candidate content.",
        "no_mutation": "It does not promote, archive, delete, or change memory.",
    }


def build_daily_report(
    project_dir: str | Path,
    *,
    limit: int = 5,
    min_events: int = 5,
    write_report: bool = False,
    report_path: str | Path = "",
    language: str = "en",
    precomputed_brief: dict[str, Any] | None = None,
    precomputed_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a short, human-first daily memory report.

    The report is read-only. It may write a JSON/Markdown artifact when
    requested, but it never promotes, archives, deletes, or changes memory.
    """
    project = Path(project_dir)
    limit_i = max(1, min(int(limit or 5), 20))
    lang = normalize_report_language(language)
    labels = _labels(lang)
    generated_at = datetime.now(timezone.utc).isoformat()
    brief = precomputed_brief or automation_brief(project, limit=limit_i, review_limit=limit_i, min_events=min_events)
    review = precomputed_review or automation_review_summary(
        project,
        limit=limit_i,
        min_events=min_events,
        precomputed_brief=brief,
    )
    brief_summary = brief.get("summary") or {}
    cards_all = [_compact_card(card, language=lang) for card in (review.get("cards") or [])[:limit_i]]
    decision_cards = [card for card in cards_all if card.get("requires_human_decision", True)]
    quiet_actions = _quiet_actions(brief_summary)
    payload = {
        "action": "daily-report",
        "language": lang,
        "generated_at": generated_at,
        "project_dir": str(project),
        "status": "completed" if brief.get("status") == "completed" else brief.get("status", "blocked"),
        "headline": _headline(brief_summary, decision_cards, language=lang),
        "labels": labels,
        "summary": {
            "auto_kept_or_observed": int(quiet_actions.get("total", 0)),
            "pending_candidates": int(brief_summary.get("pending_candidates") or 0),
            "needs_confirmation": len(decision_cards),
            "learning_rules": int(brief_summary.get("learning_rules") or 0),
            "expired_active": int(brief_summary.get("expired_active") or 0),
            "cold_store_preview": int(brief_summary.get("cold_store_preview") or 0),
            "cold_store_applied": int(brief_summary.get("cold_store_applied") or 0),
            "registered_agents": int((brief.get("agent_health") or {}).get("agent_count") or 0),
        },
        "quiet_actions": quiet_actions,
        "review_cards": decision_cards,
        "daily_choices": _daily_choices(decision_cards),
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
            "intended_for": labels["intended_for"],
        },
        "next_action": (
            labels["next_review_cards"]
            if decision_cards
            else labels["next_no_action"]
        ),
    }
    if write_report:
        payload["paths"] = _write_daily_report(project, payload, report_path=report_path)
    return payload


def render_daily_report_text(payload: dict[str, Any]) -> str:
    """Render a concise terminal-friendly daily report."""
    summary = payload.get("summary") or {}
    labels = payload.get("labels") or _labels(normalize_report_language(payload.get("language")))
    lines = [
        labels["title"],
        "",
        str(payload.get("headline") or ""),
        "",
        f"{labels['today']}:",
        f"  {labels['auto_kept']}: {summary.get('auto_kept_or_observed', 0)}",
        f"  {labels['pending_candidates']}: {summary.get('pending_candidates', 0)}",
        f"  {labels['needs_confirmation']}: {summary.get('needs_confirmation', 0)}",
        f"  {labels['learning_rules']}: {summary.get('learning_rules', 0)}",
        f"  {labels['expired_active']}: {summary.get('expired_active', 0)}",
    ]
    cards = payload.get("review_cards") or []
    lines += ["", f"{labels['needs_decision']}:"]
    if not cards:
        lines.append(f"  {labels['none']}")
    for index, card in enumerate(cards, start=1):
        lines += [
            f"  {index}. {card.get('title') or card.get('id') or card.get('kind')}",
            f"     {labels['suggested']}: {card.get('suggested_decision')}",
            f"     {labels['why']}: {card.get('reason')}",
            f"     {labels['choices']}: {', '.join(card.get('choices') or [])}",
        ]
    lines += ["", f"{labels['next']}: {payload.get('next_action', '')}"]
    paths = payload.get("paths") or {}
    if paths.get("markdown"):
        lines.append(f"Markdown: {paths['markdown']}")
    if paths.get("json"):
        lines.append(f"JSON: {paths['json']}")
    return "\n".join(lines).rstrip() + "\n"


def _compact_card(card: dict[str, Any], *, language: str = "en") -> dict[str, Any]:
    action = str(card.get("recommended_action") or "review").strip() or "review"
    return {
        "kind": card.get("kind", ""),
        "id": card.get("id", ""),
        "title": card.get("title", ""),
        "priority": int(card.get("priority") or 0),
        "suggested_decision": _suggested_decision(action, language=language),
        "recommended_action": action,
        "reason": card.get("reason", ""),
        "safe_action": card.get("safe_action") or _labels(language)["review_evidence_first"],
        "choices": _choices_for_action(action, language=language),
        "requires_human_decision": bool(card.get("requires_human_decision", True)),
    }


def _suggested_decision(action: str, *, language: str = "en") -> str:
    labels = _labels(language)
    text = action.lower()
    if "private" in text:
        return labels["keep_private"]
    if "share" in text or "promote" in text:
        return labels["approve_if_source"]
    if "archive" in text or "cold" in text:
        return labels["cleanup_after_review"]
    if "reject" in text:
        return labels["reject"]
    return labels["review"]


def _choices_for_action(action: str, *, language: str = "en") -> list[str]:
    labels = _labels(language)
    text = action.lower()
    if "archive" in text or "cold" in text:
        return [labels["keep_active"], labels["summarize_cold_store"], labels["defer"]]
    if "promote" in text or "candidate" in text:
        return [labels["keep"], labels["make_private"], labels["do_not_remember"], labels["defer"]]
    return [labels["accept"], labels["reject"], labels["defer"]]


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


def _headline(summary: dict[str, Any], cards: list[dict[str, Any]], *, language: str = "en") -> str:
    labels = _labels(language)
    needs = len(cards)
    pending = int(summary.get("pending_candidates") or 0)
    if needs:
        return labels["headline_needs"].format(needs=needs, pending=pending)
    if pending:
        return labels["headline_pending"].format(pending=pending)
    return labels["headline_clear"]


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
    labels = payload.get("labels") or _labels(normalize_report_language(payload.get("language")))
    lines = [
        f"# {labels['title']}",
        "",
        f"- {labels['generated_at']}: `{_md(payload.get('generated_at', ''))}`",
        f"- {labels['status']}: `{_md(payload.get('status', ''))}`",
        f"- {labels['headline']}: {_md(payload.get('headline', ''))}",
        "",
        f"## {labels['today']}",
        "",
        f"- {labels['auto_kept']}: `{int(summary.get('auto_kept_or_observed') or 0)}`",
        f"- {labels['pending_candidates']}: `{int(summary.get('pending_candidates') or 0)}`",
        f"- {labels['needs_confirmation']}: `{int(summary.get('needs_confirmation') or 0)}`",
        f"- {labels['learning_rules']}: `{int(summary.get('learning_rules') or 0)}`",
        f"- {labels['expired_active']}: `{int(summary.get('expired_active') or 0)}`",
        "",
        f"## {labels['needs_decision']}",
        "",
    ]
    cards = payload.get("review_cards") or []
    if not cards:
        lines.append(labels["headline_clear"])
    for index, card in enumerate(cards, start=1):
        lines += [
            f"### {index}. {_md(card.get('title') or card.get('id') or card.get('kind') or 'Review item')}",
            "",
            f"- {labels['suggested']}: `{_md(card.get('suggested_decision', labels['review']))}`",
            f"- {labels['why']}: {_md(card.get('reason', ''))}",
            f"- safe action: {_md(card.get('safe_action', ''))}",
            f"- {labels['choices']}: `{_md(', '.join(card.get('choices') or []))}`",
            "",
        ]
    lines += [
        f"## {labels['safety']}",
        "",
        f"- {labels['read_only']}",
        f"- {labels['no_raw']}",
        f"- {labels['no_mutation']}",
        "",
        f"{labels['next']}: {_md(payload.get('next_action', ''))}",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _relative_to_project(project: Path, path: Path) -> str:
    try:
        return str(path.relative_to(project))
    except ValueError:
        return str(path)


def _md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()
