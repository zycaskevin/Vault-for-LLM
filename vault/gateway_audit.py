"""Read-only Gateway audit log summaries."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any


GATEWAY_AUDIT_RELATIVE_PATH = Path("reports") / "gateway" / "audit.jsonl"


def gateway_audit_report(
    project_dir: str | Path,
    *,
    limit: int = 20,
    event: str = "",
) -> dict[str, Any]:
    """Return a compact, token-safe Gateway audit summary."""
    project = Path(project_dir).expanduser().resolve()
    path = project / GATEWAY_AUDIT_RELATIVE_PATH
    limit_i = max(1, min(int(limit or 20), 100))
    events = _read_audit_events(path, event=event)
    rotated_logs = _rotated_audit_logs(path.parent)
    recent = events[-limit_i:]
    event_counts = Counter(str(row.get("event") or "") for row in events)
    status_counts = Counter(str(row.get("status") or "") for row in events)
    reason_counts = Counter(str(row.get("reason") or "") for row in events if row.get("reason"))
    client_ips = sorted({str(row.get("client_ip") or "") for row in events if row.get("client_ip")})
    blocked_events = [
        row
        for row in events
        if row.get("event") in {"auth_failed", "request_blocked"}
        or str(row.get("status") or "") in {"error", "rate_limited", "auth_locked"}
    ]
    return {
        "ok": True,
        "status": "needs_review" if blocked_events else ("ok" if events else "idle"),
        "audit_path": str(path),
        "exists": path.exists(),
        "rotation": {
            "rotated_log_count": len(rotated_logs),
            "rotated_logs": [str(item) for item in rotated_logs[:10]],
        },
        "filter": {"event": event or "", "limit": limit_i},
        "summary": {
            "total_events": len(events),
            "blocked_or_failed_events": len(blocked_events),
            "unique_client_ips": len(client_ips),
            "event_counts": dict(sorted(event_counts.items())),
            "status_counts": dict(sorted(status_counts.items())),
            "top_reasons": dict(reason_counts.most_common(10)),
        },
        "recent_events": [_safe_event(row) for row in recent],
        "next_action": _next_action(events, blocked_events),
    }


def _read_audit_events(path: Path, *, event: str = "") -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if event and str(row.get("event") or "") != event:
            continue
        rows.append(row)
    return rows


def _rotated_audit_logs(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    rows: list[Path] = []
    for item in directory.glob("audit-*.jsonl"):
        if item.is_file():
            rows.append(item)
    return sorted(rows, key=lambda item: item.stat().st_mtime, reverse=True)


def _safe_event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "created_at": row.get("created_at", ""),
        "event": row.get("event", ""),
        "status": row.get("status", ""),
        "agent_id": row.get("agent_id", ""),
        "client_ip": row.get("client_ip", ""),
        "user_agent": str(row.get("user_agent") or "")[:120],
        "endpoint": row.get("endpoint", ""),
        "method": row.get("method", ""),
        "reason": row.get("reason", ""),
        "knowledge_id": row.get("knowledge_id", ""),
        "candidate_id": row.get("candidate_id", ""),
    }


def _next_action(events: list[dict[str, Any]], blocked_events: list[dict[str, Any]]) -> str:
    if not events:
        return "No Gateway audit events yet. Start the Gateway and run a health or search smoke test."
    if blocked_events:
        return "Review auth_failed/request_blocked events, client IPs, and rate-limit/IP policy before wider rollout."
    return "No blocked Gateway events in the selected audit window."
