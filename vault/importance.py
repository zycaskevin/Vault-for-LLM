"""Explainable memory importance scoring.

The score is a bounded ranking and review signal. It is not an access-control
decision, promotion rule, deletion rule, or source-of-truth override.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


MODEL_ID = "usage_citation_recency_trust_freshness_ttl_v2"


def parse_utc_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.fromisoformat(f"{text}T00:00:00+00:00")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_memory_importance(row: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Return an explainable importance score for a memory-like row."""
    now_dt = now or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    now_dt = now_dt.astimezone(timezone.utc)

    access = int(row.get("access_count") or 0)
    citations = int(row.get("citation_count") or 0)
    trust = _clamp01(row.get("trust"), default=0.0)
    freshness = _clamp01(row.get("freshness"), default=1.0)
    ttl_score, ttl_signal = _ttl_pressure_component(row.get("expires_at", ""), now_dt, access=access, citations=citations)
    components = {
        "access": min(20.0, access * 2.0),
        "citation": min(35.0, citations * 8.0),
        "recency": _recency_component(row.get("last_accessed_at", ""), now_dt),
        "trust": round(trust * 10.0, 3),
        "freshness": round(freshness * 8.0, 3),
        "ttl_pressure": ttl_score,
        "protection": _protection_component(row.get("scope", ""), row.get("sensitivity", "")),
    }
    score = round(sum(float(value or 0.0) for value in components.values()), 3)
    signals = []
    if access > 0:
        signals.append("accessed")
    if citations > 0:
        signals.append("cited")
    if ttl_signal:
        signals.append(ttl_signal)
    if components["protection"] > 0:
        signals.append("protected_governance")
    return {
        "model": MODEL_ID,
        "importance_score": score,
        "weight_tier": _weight_tier(score),
        "lifecycle_action": _lifecycle_action(score=score, ttl_signal=ttl_signal, citations=citations),
        "importance_components": components,
        "signals": signals,
        "recommendation": _importance_recommendation(
            access=access,
            citations=citations,
            ttl_signal=ttl_signal,
            score=score,
        ),
    }


def _clamp01(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, min(parsed, 1.0))


def _recency_component(last_accessed_at: Any, now: datetime) -> float:
    accessed = parse_utc_datetime(last_accessed_at)
    if accessed is None:
        return 0.0
    age_days = max(0.0, (now - accessed).total_seconds() / 86400.0)
    if age_days <= 7:
        return 10.0
    if age_days <= 30:
        return 6.0
    if age_days <= 90:
        return 3.0
    return 1.0


def _ttl_pressure_component(expires_at: Any, now: datetime, *, access: int, citations: int) -> tuple[float, str]:
    if access <= 0 and citations <= 0:
        return 0.0, ""
    expires = parse_utc_datetime(expires_at)
    if expires is None:
        return 0.0, ""
    days_until_expiry = (expires - now).total_seconds() / 86400.0
    if days_until_expiry <= 0:
        return 10.0, "expired_but_used"
    if days_until_expiry <= 14:
        return 5.0, "expiring_soon_but_used"
    return 0.0, ""


def _protection_component(scope: Any, sensitivity: Any) -> float:
    scope_text = str(scope or "").strip().lower()
    sensitivity_text = str(sensitivity or "").strip().lower()
    score = 0.0
    if scope_text == "private":
        score += 2.0
    if sensitivity_text == "medium":
        score += 1.0
    elif sensitivity_text == "high":
        score += 2.0
    elif sensitivity_text == "restricted":
        score += 3.0
    return min(score, 5.0)


def _importance_recommendation(*, access: int, citations: int, ttl_signal: str, score: float) -> str:
    if ttl_signal == "expired_but_used":
        return "refresh_or_cold_store_before_forgetting"
    if ttl_signal == "expiring_soon_but_used":
        return "review_ttl_before_expiry"
    if citations > 0:
        return "protect_or_summarize_before_forgetting"
    if score > 0 or access > 0:
        return "keep_available"
    return "observe"


def _weight_tier(score: float) -> str:
    if score >= 45:
        return "critical"
    if score >= 25:
        return "strong"
    if score >= 10:
        return "warm"
    if score > 0:
        return "weak"
    return "cold"


def _lifecycle_action(*, score: float, ttl_signal: str, citations: int) -> str:
    if ttl_signal == "expired_but_used":
        if citations > 0 or score >= 25:
            return "refresh_or_summarize_before_cold_store"
        return "summarize_then_cold_store"
    if ttl_signal == "expiring_soon_but_used":
        return "review_ttl_before_expiry"
    if score >= 45:
        return "protect_and_refresh"
    if score >= 25:
        return "keep_hot"
    if score > 0:
        return "keep_warm"
    return "observe"
