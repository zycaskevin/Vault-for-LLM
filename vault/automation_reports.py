"""Automation report, handoff, and Markdown artifact helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def _relative_to_project(project: Path, path: Path) -> str:
    try:
        return str(path.relative_to(project))
    except ValueError:
        return str(path.expanduser().resolve().relative_to(project.expanduser().resolve()))


def _write_brief(project: Path, payload: dict[str, Any], *, brief_path: str | Path = "") -> str:
    report_dir = project / "reports" / "automation"
    report_dir.mkdir(parents=True, exist_ok=True)
    if brief_path:
        raw = Path(brief_path)
        candidate = raw if raw.is_absolute() else project / raw
        try:
            resolved = candidate.expanduser().resolve()
            allowed = report_dir.expanduser().resolve()
        except Exception as exc:
            raise ValueError(f"unable to resolve automation brief path: {exc}") from exc
        if allowed != resolved and allowed not in resolved.parents:
            raise ValueError("automation brief path must stay under reports/automation")
        path = resolved
    else:
        path = report_dir / "brief-latest.json"
    data = dict(payload)
    data["brief_path"] = _relative_to_project(project, path)
    data["brief_markdown_path"] = str(data.get("brief_markdown_path") or "")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return _relative_to_project(project, path)


def _write_brief_markdown(project: Path, payload: dict[str, Any], *, brief_path: str | Path) -> str:
    json_path = project / brief_path if not Path(brief_path).is_absolute() else Path(brief_path)
    path = json_path.with_suffix(".md")
    summary = payload.get("summary") or {}
    review = payload.get("human_review_5_percent") or {}
    learning = payload.get("learning") or {}
    weights = payload.get("memory_weights") or {}
    forgetting = payload.get("forgetting_strategy") or {}
    agent_health = payload.get("agent_health") or {}
    lines = [
        "# Vault Automation Intelligence Brief",
        "",
        f"- generated_at: `{_md_text(payload.get('generated_at', ''))}`",
        f"- status: `{_md_text(payload.get('status', ''))}`",
        f"- pending candidates: `{int(summary.get('pending_candidates') or 0)}`",
        f"- needs review: `{int(summary.get('needs_review') or 0)}`",
        f"- auto-promoted: `{int(summary.get('auto_promote_promoted') or 0)}`",
        f"- auto-promote skipped: `{int(summary.get('auto_promote_skipped') or 0)}`",
        f"- learning readiness: `{_md_text(summary.get('learning_readiness', ''))}`",
        f"- expired active: `{int(summary.get('expired_active') or 0)}`",
        f"- cold-store preview: `{int(summary.get('cold_store_preview') or 0)}`",
        f"- cold-store applied: `{int(summary.get('cold_store_applied') or 0)}`",
        "",
        "## Human Review 5%",
        "",
    ]
    items = review.get("items") or []
    if items:
        lines += [_md_row(["kind", "id", "title", "action", "reason"]), _md_row(["---", "---", "---", "---", "---"])]
        for item in items:
            lines.append(
                _md_row(
                    [
                        item.get("kind", ""),
                        item.get("id", ""),
                        item.get("title", ""),
                        item.get("recommended_action", ""),
                        item.get("reason", ""),
                    ]
                )
            )
    else:
        lines.append("No urgent human-review items.")
    lines += [
        "",
        "## Learning",
        "",
        f"- readiness: `{_md_text(learning.get('readiness', ''))}`",
        f"- feedback events: `{int(learning.get('event_count') or 0)}`",
        f"- top rules: `{len(learning.get('top_rules') or [])}`",
        "",
        "## Memory Weights",
        "",
    ]
    top_used = weights.get("top_used") or []
    if top_used:
        lines += [
            _md_row(["id", "title", "importance", "access", "citations", "recommendation"]),
            _md_row(["---", "---", "---", "---", "---", "---"]),
        ]
        for item in top_used[:10]:
            lines.append(
                _md_row(
                    [
                        item.get("knowledge_id", ""),
                        item.get("title", ""),
                        item.get("importance_score", item.get("weight_score", 0)),
                        item.get("access_count", 0),
                        item.get("citation_count", 0),
                        item.get("recommendation", ""),
                    ]
                )
            )
    else:
        lines.append("No usage-weight signal yet.")
    lines += [
        "",
        "## Forgetting Strategy",
        "",
        f"- archiveable expired: `{int(forgetting.get('archiveable_count') or 0)}`",
        f"- used expired: `{int(forgetting.get('used_expired_count') or 0)}`",
        f"- protected expired: `{int(forgetting.get('protected_expired_count') or 0)}`",
        "",
        "## Agent Health",
        "",
        f"- registered agents: `{int(agent_health.get('agent_count') or 0)}`",
        "",
        "## Safety",
        "",
        "- read-only brief",
        "- no raw candidate content",
        "- no auto-promote policy widening",
        "- forgetting strategy only; no compression or cold-store mutation",
    ]
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return _relative_to_project(project, path)


def _write_review_summary(project: Path, payload: dict[str, Any], *, summary_path: str | Path = "") -> str:
    report_dir = project / "reports" / "automation"
    report_dir.mkdir(parents=True, exist_ok=True)
    if summary_path:
        raw = Path(summary_path)
        path = raw if raw.is_absolute() else project / raw
        try:
            resolved = path.expanduser().resolve()
            allowed = report_dir.expanduser().resolve()
        except Exception as exc:
            raise ValueError(f"unable to resolve automation review summary path: {exc}") from exc
        if allowed != resolved and allowed not in resolved.parents:
            raise ValueError("automation review summary path must stay under reports/automation")
        path = resolved
    else:
        path = report_dir / "review-summary-latest.json"
    data = dict(payload)
    data["review_summary_path"] = _relative_to_project(project, path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return _relative_to_project(project, path)


def _write_review_summary_markdown(project: Path, payload: dict[str, Any], *, summary_path: str | Path) -> str:
    json_path = project / summary_path if not Path(summary_path).is_absolute() else Path(summary_path)
    path = json_path.with_suffix(".md")
    cards = payload.get("cards") or []
    summary = payload.get("summary") or {}
    lines = [
        "# Vault Automation Review Summary",
        "",
        f"- generated: `{_md_text(payload.get('generated_at', ''))}`",
        f"- status: `{_md_text(payload.get('status', ''))}`",
        f"- cards: `{int(summary.get('cards') or 0)}`",
        f"- requires human decision: `{bool(summary.get('requires_human_decision', False))}`",
        f"- top importance score: `{float(summary.get('top_importance_score') or 0.0)}`",
        "",
        "## What To Review First",
        "",
        "Read only these cards first. Each card is a decision prompt, not an action already taken.",
        "",
    ]
    if cards:
        for index, card in enumerate(cards, start=1):
            lines += [
                f"### {index}. {_md_text(card.get('title') or card.get('id') or card.get('kind') or 'Review item')}",
                "",
                f"- priority: `{int(card.get('priority') or 0)}`",
                f"- kind: `{_md_text(card.get('kind', ''))}`",
                f"- id: `{_md_text(card.get('id', ''))}`",
                f"- suggested decision: `{_review_card_decision(card)}`",
                f"- why: {_md_text(card.get('reason', ''))}",
                f"- safe next step: {_md_text(card.get('safe_action') or card.get('recommended_action') or 'Review compact evidence first.')}",
                "",
            ]
    else:
        lines.append("No review cards.")
    lines += [
        "",
        "## Safety",
        "",
        "- read-only summary",
        "- no raw candidate content",
        "- no promotion, archive, or deletion",
        "- importance is a ranking hint only",
        "",
        f"Next action: {_md_text(payload.get('next_action', ''))}",
    ]
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return _relative_to_project(project, path)


def _write_learning_health(project: Path, payload: dict[str, Any], *, health_path: str | Path = "") -> str:
    report_dir = project / "reports" / "automation"
    report_dir.mkdir(parents=True, exist_ok=True)
    if health_path:
        raw = Path(health_path)
        path = raw if raw.is_absolute() else project / raw
        try:
            resolved = path.expanduser().resolve()
            allowed = report_dir.expanduser().resolve()
        except Exception as exc:
            raise ValueError(f"unable to resolve automation learning health path: {exc}") from exc
        if allowed != resolved and allowed not in resolved.parents:
            raise ValueError("automation learning health path must stay under reports/automation")
        path = resolved
    else:
        path = report_dir / "learning-health-latest.json"
    data = dict(payload)
    data["health_path"] = _relative_to_project(project, path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return _relative_to_project(project, path)


def _write_learning_health_markdown(project: Path, payload: dict[str, Any], *, health_path: str | Path) -> str:
    json_path = project / health_path if not Path(health_path).is_absolute() else Path(health_path)
    path = json_path.with_suffix(".md")
    summary = payload.get("summary") or {}
    cards = payload.get("cards") or []
    rules = payload.get("top_rules") or []
    lines = [
        "# Vault Automation Learning Health",
        "",
        f"- generated: `{_md_text(payload.get('generated_at', ''))}`",
        f"- status: `{_md_text(payload.get('status', ''))}`",
        f"- readiness: `{_md_text(summary.get('readiness', ''))}`",
        f"- events: `{int(summary.get('event_count') or 0)}`",
        f"- positive rate: `{float(summary.get('positive_rate') or 0.0)}`",
        f"- prefer / downgrade / observe: `{int(summary.get('prefer_rules') or 0)}` / `{int(summary.get('downgrade_rules') or 0)}` / `{int(summary.get('observe_rules') or 0)}`",
        "",
        "## Cards",
        "",
    ]
    if cards:
        lines += [
            _md_row(["priority", "kind", "title", "why", "safe action"]),
            _md_row(["---", "---", "---", "---", "---"]),
        ]
        for card in cards:
            lines.append(
                _md_row(
                    [
                        card.get("priority", ""),
                        card.get("kind", ""),
                        card.get("title", ""),
                        card.get("reason", ""),
                        card.get("safe_action", ""),
                    ]
                )
            )
    else:
        lines.append("No learning-health cards.")
    lines += [
        "",
        "## Top Rules",
        "",
    ]
    if rules:
        lines += [
            _md_row(["source", "type", "category", "action", "confidence", "multiplier"]),
            _md_row(["---", "---", "---", "---", "---", "---"]),
        ]
        for rule in rules:
            lines.append(
                _md_row(
                    [
                        rule.get("source", ""),
                        rule.get("memory_type", ""),
                        rule.get("category", ""),
                        rule.get("action", ""),
                        rule.get("confidence", ""),
                        rule.get("priority_multiplier", ""),
                    ]
                )
            )
    else:
        lines.append("No learned rules yet.")
    lines += [
        "",
        "## Safety",
        "",
        "- read-only health panel",
        "- no raw feedback reasons",
        "- no promotion, archive, or deletion",
        "- learning is a ranking hint only",
        "",
        f"Next action: {_md_text(payload.get('next_action', ''))}",
    ]
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return _relative_to_project(project, path)


def _write_fleet_health(project: Path, payload: dict[str, Any], *, health_path: str | Path = "") -> str:
    report_dir = project / "reports" / "automation"
    report_dir.mkdir(parents=True, exist_ok=True)
    if health_path:
        raw = Path(health_path)
        path = raw if raw.is_absolute() else project / raw
        try:
            resolved = path.expanduser().resolve()
            allowed = report_dir.expanduser().resolve()
        except Exception as exc:
            raise ValueError(f"unable to resolve automation fleet health path: {exc}") from exc
        if allowed != resolved and allowed not in resolved.parents:
            raise ValueError("automation fleet health path must stay under reports/automation")
        path = resolved
    else:
        path = report_dir / "fleet-health-latest.json"
    data = dict(payload)
    data["fleet_health_path"] = _relative_to_project(project, path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return _relative_to_project(project, path)


def _write_fleet_health_markdown(project: Path, payload: dict[str, Any], *, health_path: str | Path) -> str:
    json_path = project / health_path if not Path(health_path).is_absolute() else Path(health_path)
    path = json_path.with_suffix(".md")
    summary = payload.get("summary") or {}
    cards = payload.get("cards") or []
    agents = payload.get("agents") or []
    lines = [
        "# Vault Automation Fleet Health",
        "",
        f"- generated: `{_md_text(payload.get('generated_at', ''))}`",
        f"- status: `{_md_text(payload.get('status', ''))}`",
        f"- registered agents: `{int(summary.get('registered_agents') or 0)}`",
        f"- agents for this project: `{int(summary.get('agents_for_project') or 0)}`",
        f"- learning: `{_md_text(summary.get('learning_status', ''))}` / `{_md_text(summary.get('learning_readiness', ''))}`",
        f"- learning events / rules: `{int(summary.get('learning_events') or 0)}` / `{int(summary.get('learning_rules') or 0)}`",
        f"- update distribution ok: `{str(bool(summary.get('update_distribution_ok'))).lower()}`",
        "",
        "## Cards",
        "",
    ]
    if cards:
        lines += [
            _md_row(["priority", "kind", "title", "why", "safe action"]),
            _md_row(["---", "---", "---", "---", "---"]),
        ]
        for card in cards:
            lines.append(
                _md_row(
                    [
                        card.get("priority", ""),
                        card.get("kind", ""),
                        card.get("title", ""),
                        card.get("reason", ""),
                        card.get("safe_action", ""),
                    ]
                )
            )
    else:
        lines.append("No fleet-health cards.")
    lines += [
        "",
        "## Project Agents",
        "",
    ]
    if agents:
        lines += [
            _md_row(["agent", "scope", "layout", "profile", "version"]),
            _md_row(["---", "---", "---", "---", "---"]),
        ]
        for agent in agents:
            lines.append(
                _md_row(
                    [
                        agent.get("agent_id", ""),
                        agent.get("scope", ""),
                        agent.get("memory_layout", ""),
                        agent.get("tool_profile", ""),
                        agent.get("vault_version", ""),
                    ]
                )
            )
    else:
        lines.append("No registered project agents.")
    lines += [
        "",
        "## Safety",
        "",
        "- read-only fleet panel",
        "- registry metadata only",
        "- no raw candidate content",
        "- no raw feedback reasons",
        "- no promotion, archive, or deletion",
        "",
        f"Next action: {_md_text(payload.get('next_action', ''))}",
    ]
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return _relative_to_project(project, path)


def _write_cycle_workspace_markdown(
    project: Path,
    workspace: dict[str, Any],
    *,
    workspace_path: str | Path = "",
) -> str:
    report_dir = project / "reports" / "automation"
    report_dir.mkdir(parents=True, exist_ok=True)
    if workspace_path:
        raw = Path(workspace_path)
        raw = raw.with_suffix(".md")
        candidate = raw if raw.is_absolute() else project / raw
        try:
            resolved = candidate.expanduser().resolve()
            allowed = report_dir.expanduser().resolve()
        except Exception as exc:
            raise ValueError(f"unable to resolve automation cycle workspace Markdown path: {exc}") from exc
        if allowed != resolved and allowed not in resolved.parents:
            raise ValueError("automation cycle workspace Markdown path must stay under reports/automation")
        path = resolved
    else:
        path = report_dir / "cycle-latest.md"
    path.write_text(_render_cycle_workspace_markdown(workspace), encoding="utf-8")
    return _relative_to_project(project, path)


def _md_text(value: Any) -> str:
    text = str(value if value is not None else "").replace("\r", " ").replace("\n", " ").strip()
    return text.replace("|", "\\|")


def _md_row(values: list[Any]) -> str:
    return "| " + " | ".join(_md_text(value) for value in values) + " |"


def _review_card_decision(card: dict[str, Any]) -> str:
    action = str(card.get("recommended_action") or "").strip()
    if bool(card.get("requires_human_decision", False)):
        return action or "human_review_required"
    if action in {"keep_observing", "observe", "review"}:
        return "defer_or_observe"
    return action or "agent_can_handle"


def _render_cycle_workspace_markdown(workspace: dict[str, Any]) -> str:
    summary = workspace.get("summary") or {}
    candidate_review = workspace.get("candidate_review") or {}
    queue = candidate_review.get("queue") or []
    transcripts = workspace.get("transcripts_to_capture") or {}
    transcript_summary = transcripts.get("summary") or {}
    transcript_items = transcripts.get("items") or []
    transcript_capture = workspace.get("transcript_capture") or {}
    capture_summary = transcript_capture.get("summary") or {}
    capture_items = transcript_capture.get("items") or []
    curation = workspace.get("curation_policy") or {}
    rules = curation.get("rules") or []
    safety = workspace.get("safety") or {}
    priority_brief = workspace.get("priority_brief") or []
    suggested_tasks = workspace.get("suggested_next_tasks") or []
    lines: list[str] = [
        "# Vault Automation Cycle Workspace",
        "",
        f"- generated_at: `{_md_text(workspace.get('generated_at', ''))}`",
        f"- status: `{_md_text(workspace.get('status', ''))}`",
        f"- project_dir: `{_md_text(workspace.get('project_dir', ''))}`",
        f"- json: `{_md_text(workspace.get('workspace_path', 'reports/automation/cycle-latest.json'))}`",
        "",
        "## Summary",
        "",
        f"- candidate queue items: `{int(summary.get('candidate_queue_items') or 0)}`",
        f"- pending candidates: `{int(summary.get('pending_candidates') or 0)}`",
        f"- needs review: `{int(summary.get('needs_review') or 0)}`",
        f"- uncaptured transcripts: `{int(summary.get('uncaptured_transcripts') or 0)}`",
        f"- transcript capture status: `{_md_text(summary.get('transcript_capture_status', ''))}`",
        f"- transcript candidates written: `{int(summary.get('transcript_capture_candidates_written') or 0)}`",
        f"- auto-promote enabled: `{str(bool(summary.get('auto_promote_enabled', False))).lower()}`",
        f"- auto-promote would promote: `{int(summary.get('auto_promote_would_promote_count') or 0)}`",
        f"- auto-promote promoted: `{int(summary.get('auto_promote_promoted_count') or 0)}`",
        f"- learning rules: `{int(summary.get('learning_rules') or 0)}`",
        f"- learning readiness: `{_md_text(summary.get('learning_readiness', ''))}`",
        f"- automation report: `{_md_text(summary.get('automation_report_path', ''))}`",
        f"- learning policy: `{_md_text(summary.get('learning_policy_path', ''))}`",
        "",
        "## Priority Brief",
        "",
    ]
    if priority_brief:
        lines += [
            _md_row(["priority", "title", "count", "safe action"]),
            _md_row(["---", "---", "---", "---"]),
        ]
        for item in priority_brief[:8]:
            if not isinstance(item, dict):
                continue
            lines.append(
                _md_row(
                    [
                        item.get("priority", ""),
                        item.get("title", ""),
                        item.get("count", ""),
                        item.get("safe_action", ""),
                    ]
                )
            )
    else:
        lines.append("No urgent automation handoff items.")

    lines += [
        "",
        "## Candidate Review",
        "",
        f"- content hidden: `{str(bool(candidate_review.get('content_hidden', True))).lower()}`",
    ]
    if queue:
        lines += [
            "",
            _md_row(["id", "title", "source", "type", "priority", "action"]),
            _md_row(["---", "---", "---", "---", "---", "---"]),
        ]
        for item in queue[:10]:
            if not isinstance(item, dict):
                continue
            lines.append(
                _md_row(
                    [
                        item.get("candidate_id", item.get("id", "")),
                        item.get("title", ""),
                        item.get("source", ""),
                        item.get("memory_type", item.get("type", "")),
                        item.get("priority", ""),
                        item.get("recommended_action", item.get("action", "")),
                    ]
                )
            )
    else:
        lines += ["", "No pending candidate review items."]

    lines += [
        "",
        "## Transcripts To Capture",
        "",
        f"- count: `{int(transcript_summary.get('count') or 0)}`",
        f"- include transcripts: `{str(bool(transcript_summary.get('include_transcripts'))).lower()}`",
        f"- read contents: `{str(bool(transcript_summary.get('read_contents'))).lower()}`",
    ]
    if transcript_items:
        lines += [
            "",
            _md_row(["capture_path", "source_system", "format", "size_bytes"]),
            _md_row(["---", "---", "---", "---"]),
        ]
        for item in transcript_items[:10]:
            if not isinstance(item, dict):
                continue
            lines.append(
                _md_row(
                    [
                        item.get("capture_path", item.get("path", "")),
                        item.get("source_system", ""),
                        item.get("format", ""),
                        item.get("size_bytes", ""),
                    ]
                )
            )

    lines += [
        "",
        "## Transcript Capture",
        "",
        f"- status: `{_md_text(transcript_capture.get('status', ''))}`",
        f"- enabled: `{str(bool(transcript_capture.get('enabled'))).lower()}`",
        f"- reads contents: `{str(bool(transcript_capture.get('reads_contents'))).lower()}`",
        f"- content hidden: `{str(bool(transcript_capture.get('content_hidden', True))).lower()}`",
        f"- transcripts captured: `{int(capture_summary.get('transcripts_captured') or 0)}`",
        f"- candidates written: `{int(capture_summary.get('candidates_written') or 0)}`",
        f"- candidates rejected: `{int(capture_summary.get('candidates_rejected') or 0)}`",
    ]
    if capture_items:
        lines += [
            "",
            _md_row(["capture_path", "written", "rejected", "candidate ids"]),
            _md_row(["---", "---", "---", "---"]),
        ]
        for item in capture_items[:10]:
            if not isinstance(item, dict):
                continue
            ids = ", ".join(
                str(candidate.get("candidate_id", ""))
                for candidate in item.get("candidates", [])[:5]
                if isinstance(candidate, dict) and candidate.get("candidate_id")
            )
            lines.append(
                _md_row(
                    [
                        item.get("capture_path", ""),
                        item.get("written", 0),
                        item.get("rejected", 0),
                        ids,
                    ]
                )
            )

    lines += [
        "",
        "## Curation Policy",
        "",
        f"- path: `{_md_text(curation.get('path', ''))}`",
        f"- readiness: `{_md_text(curation.get('readiness', ''))}`",
        f"- feedback events: `{int(curation.get('event_count') or 0)}`",
        f"- rule count: `{len(rules)}`",
    ]
    if rules:
        lines += [
            "",
            _md_row(["source", "type", "action", "priority_multiplier"]),
            _md_row(["---", "---", "---", "---"]),
        ]
        for rule in rules[:10]:
            if not isinstance(rule, dict):
                continue
            lines.append(
                _md_row(
                    [
                        rule.get("source", ""),
                        rule.get("memory_type", ""),
                        rule.get("action", ""),
                        rule.get("priority_multiplier", ""),
                    ]
                )
            )

    lines += [
        "",
        "## Safety",
        "",
        f"- read only: `{str(bool(safety.get('read_only', True))).lower()}`",
        f"- auto promote: `{str(bool(safety.get('auto_promote', False))).lower()}`",
        f"- hard delete: `{str(bool(safety.get('hard_delete', False))).lower()}`",
        f"- candidate content hidden: `{str(bool(safety.get('candidate_content_hidden', True))).lower()}`",
        f"- transcript discovery reads contents: `{str(bool(safety.get('transcript_discovery_reads_contents', False))).lower()}`",
        f"- transcript capture reads contents: `{str(bool(safety.get('transcript_capture_reads_contents', False))).lower()}`",
        f"- writes active memory: `{str(bool(safety.get('writes_active_memory', False))).lower()}`",
        "",
        "## Suggested Next Tasks",
        "",
    ]
    if suggested_tasks:
        lines += [
            _md_row(["step", "task", "command", "approval"]),
            _md_row(["---", "---", "---", "---"]),
        ]
        for item in suggested_tasks[:8]:
            if not isinstance(item, dict):
                continue
            lines.append(
                _md_row(
                    [
                        item.get("step", ""),
                        item.get("task", ""),
                        item.get("command", ""),
                        "yes" if item.get("requires_human_approval") else "no",
                    ]
                )
            )

    lines += [
        "",
        "## Agent Start Prompt",
        "",
        "```text",
        str(workspace.get("agent_start_prompt", "")).strip()
        or "Read this workspace handoff first, then review candidates without promoting memory automatically.",
        "```",
        "",
        "## Next Action",
        "",
        _md_text(workspace.get("next_action", "")) or "Review candidate queue before changing active memory.",
        "",
    ]
    return "\n".join(lines)

def _write_report(project: Path, payload: dict[str, Any]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    path = project / "reports" / "automation" / f"{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path.relative_to(project))


def _read_report(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _report_summary(project: Path, path: Path, data: dict[str, Any]) -> dict[str, Any]:
    diff = data.get("dry_run_diff") or {}
    ledger = data.get("action_ledger") or []
    archive = data.get("archive_expired") or {}
    cold_store = data.get("cold_store_expired") or {}
    forgetting = data.get("forgetting") or {}
    auto_promote = data.get("auto_promote") or {}
    dream = data.get("dream") or {}
    dream_learning = dream.get("learning_policy") or {}
    return {
        "path": str(path.relative_to(project)),
        "generated_at": data.get("generated_at", ""),
        "mode": data.get("mode", ""),
        "status": data.get("status", ""),
        "apply": bool(data.get("apply", False)),
        "human_review": data.get("human_review", {}),
        "report_path": data.get("report_path", ""),
        "dream_report_path": dream.get("report_path", ""),
        "dream_candidate_suggestions": int((dream.get("summary") or {}).get("candidate_suggestions") or 0),
        "dream_candidates_written": int((dream.get("summary") or {}).get("candidates_written") or 0),
        "dream_candidates_skipped_existing": int((dream.get("summary") or {}).get("candidates_skipped_existing") or 0),
        "dream_learning_policy_status": dream_learning.get("status", ""),
        "dream_learning_policy_applied_rules": int(dream_learning.get("applied_rules") or 0),
        "forgetting_candidate_suggestions": int(forgetting.get("candidate_suggestions") or 0),
        "forgetting_candidates_written": int(forgetting.get("candidates_written") or 0),
        "forgetting_candidates_skipped_existing": int(forgetting.get("candidates_skipped_existing") or 0),
        "cold_store_eligible_count": int(cold_store.get("eligible_count") or 0),
        "cold_store_applied_count": int(cold_store.get("applied_count") or 0),
        "cold_store_skipped_protected_count": int(cold_store.get("skipped_protected_count") or 0),
        "auto_promote_enabled": bool(auto_promote.get("enabled", False)),
        "auto_promote_would_promote_count": int(auto_promote.get("would_promote_count") or 0),
        "auto_promote_promoted_count": int(auto_promote.get("promoted_count") or 0),
        "archived_count": int(archive.get("archived_count") or 0),
        "eligible_count": int(archive.get("eligible_count") or 0),
        "skipped_used_count": int(archive.get("skipped_used_count") or 0),
        "skipped_policy_count": int(archive.get("skipped_protected_count") or 0),
        "dry_run_diff": {
            "would_archive_count": int(diff.get("would_archive_count") or 0),
            "applied_count": int(diff.get("applied_count") or 0),
            "skipped_usage_count": int(diff.get("skipped_usage_count") or 0),
            "skipped_policy_count": int(diff.get("skipped_policy_count") or 0),
            "would_cold_store_count": int(diff.get("would_cold_store_count") or 0),
            "cold_store_applied_count": int(diff.get("cold_store_applied_count") or 0),
            "cold_store_skipped_usage_count": int(diff.get("cold_store_skipped_usage_count") or 0),
            "cold_store_skipped_policy_count": int(diff.get("cold_store_skipped_policy_count") or 0),
            "hard_delete": bool(diff.get("hard_delete", False)),
            "promote_candidates": bool(diff.get("promote_candidates", False)),
            "permission_changes": bool(diff.get("permission_changes", False)),
        },
        "ledger_count": len(ledger) if isinstance(ledger, list) else 0,
    }


def _resolve_report_path(
    project: Path,
    report_dir: Path,
    *,
    report_path: str | Path = "",
    latest: bool = False,
) -> Path | None:
    if report_path:
        raw = Path(report_path)
        candidate = raw if raw.is_absolute() else project / raw
        try:
            resolved = candidate.expanduser().resolve()
            allowed = report_dir.expanduser().resolve()
        except Exception as exc:
            raise ValueError(f"unable to resolve automation report path: {exc}") from exc
        if allowed != resolved and allowed not in resolved.parents:
            raise ValueError("automation report path must stay under reports/automation")
        if not resolved.exists():
            raise FileNotFoundError(str(resolved))
        return resolved
    if latest:
        reports = _automation_report_files(report_dir)
        return reports[0] if reports else None
    return None


def _resolve_handoff_read_path(
    project: Path,
    report_dir: Path,
    *,
    source: str = "auto",
    handoff_path: str | Path = "",
) -> Path | None:
    if source not in {"auto", "cycle", "inbox"}:
        raise ValueError("handoff source must be one of: auto, cycle, inbox")
    if handoff_path:
        raw = Path(handoff_path)
        candidate = raw if raw.is_absolute() else project / raw
        try:
            resolved = candidate.expanduser().resolve()
            allowed = report_dir.expanduser().resolve()
        except Exception as exc:
            raise ValueError(f"unable to resolve automation handoff path: {exc}") from exc
        if allowed != resolved and allowed not in resolved.parents:
            raise ValueError("automation handoff path must stay under reports/automation")
        if resolved.suffix.lower() not in {".md", ".json"}:
            raise ValueError("automation handoff path must be a Markdown or JSON file")
        if not resolved.exists():
            raise FileNotFoundError(str(resolved))
        return resolved
    names_by_source = {
        "cycle": ["cycle-latest.md", "cycle-latest.json"],
        "inbox": ["inbox-latest.json"],
        "auto": [
            "cycle-latest.md",
            "cycle-latest.json",
            "inbox-latest.json",
            "fleet-health-latest.md",
            "fleet-health-latest.json",
        ],
    }
    for name in names_by_source[source]:
        candidate = report_dir / name
        if candidate.exists():
            return candidate
    return None


def _resolve_fleet_health_read_path(report_dir: Path) -> Path | None:
    for name in ("fleet-health-latest.md", "fleet-health-latest.json"):
        candidate = report_dir / name
        if candidate.exists():
            return candidate
    return None


def _resolve_review_summary_read_path(report_dir: Path) -> Path | None:
    for name in ("review-summary-latest.md", "review-summary-latest.json"):
        candidate = report_dir / name
        if candidate.exists():
            return candidate
    return None


def _resolve_learning_health_read_path(report_dir: Path) -> Path | None:
    for name in ("learning-health-latest.md", "learning-health-latest.json"):
        candidate = report_dir / name
        if candidate.exists():
            return candidate
    return None


def _automation_report_files(report_dir: Path) -> list[Path]:
    """Return timestamped automation run reports, excluding handoff artifacts."""
    return sorted(
        (path for path in report_dir.glob("*.json") if path.name != "learning_policy.json"),
        reverse=True,
    )
