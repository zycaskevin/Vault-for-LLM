"""Review-card helpers for automation feedback loops."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def apply_review_card_learning(card: dict[str, Any], rules: list[dict[str, Any]]) -> None:
    """Apply bounded learning-policy ranking hints to a review card in place."""
    base_priority = int(card.get("priority") or 0)
    kind = str(card.get("kind") or "")
    action = str(card.get("recommended_action") or "")
    best: dict[str, Any] = {}
    best_score = -1.0
    for rule in rules:
        selector = rule.get("selector") or {}
        if str(selector.get("source") or "") != "review-summary":
            continue
        if selector.get("memory_type") and str(selector.get("memory_type")) != kind:
            continue
        if selector.get("category") and str(selector.get("category")) != action:
            continue
        confidence = float(rule.get("confidence") or 0.0)
        if confidence > best_score:
            best = rule
            best_score = confidence
    if not best:
        card["learning_multiplier"] = 1.0
        card["learning_action"] = ""
        return
    multiplier = max(0.85, min(float(best.get("priority_multiplier") or 1.0), 1.15))
    learned_priority = max(1, min(99, round(base_priority * multiplier)))
    card["base_priority"] = base_priority
    card["priority"] = learned_priority
    card["learning_multiplier"] = multiplier
    card["learning_action"] = best.get("action", "")
    card["learning_confidence"] = float(best.get("confidence") or 0.0)
    card["learning_reason"] = best.get("reason", "")


def review_card_title(value: Any) -> str:
    text = str(value or "").replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else "Review item"


def load_review_summary(project: Path, *, summary_path: str | Path = "") -> dict[str, Any]:
    if summary_path:
        raw = Path(summary_path)
        path = raw if raw.is_absolute() else project / raw
    else:
        path = project / "reports" / "automation" / "review-summary-latest.json"
    if not path.exists():
        return {}
    try:
        resolved = path.expanduser().resolve()
        allowed = (project / "reports" / "automation").expanduser().resolve()
    except Exception:
        return {}
    if allowed != resolved and allowed not in resolved.parents:
        return {}
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def find_review_summary_card(summary: dict[str, Any], *, card_kind: str, card_id: str = "") -> dict[str, Any]:
    kind = str(card_kind or "")
    wanted_id = str(card_id or "")
    for card in summary.get("cards") or []:
        if not isinstance(card, dict):
            continue
        if str(card.get("kind") or "") != kind:
            continue
        if wanted_id and str(card.get("id") or "") != wanted_id:
            continue
        return dict(card)
    return {}


def review_feedback_score(decision: str, score: float | None) -> float:
    if score is not None:
        return max(0.0, min(float(score), 1.0))
    return {"accept": 1.0, "reject": 0.0, "defer": 0.5}.get(decision, 0.5)


def review_feedback_source_ref(summary: dict[str, Any], card: dict[str, Any], kind: str, card_id: str) -> str:
    path = str(summary.get("review_summary_path") or "reports/automation/review-summary-latest.json")
    if card:
        return f"{path}#{kind}:{card.get('id', card_id)}"
    return f"{path}#{kind}:{card_id}"


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
