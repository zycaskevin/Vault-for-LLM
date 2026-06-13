"""Deterministic, report-first dream curation engine.

The dream workflow is intentionally conservative: report mode never mutates
raw/ or active DB state. apply_safe creates a backup by default and applies only
low-risk metadata fixes that can be reviewed in the generated action payload.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable

from .db import VaultDB

DEFAULT_CHECKS = ["freshness", "dedup", "convergence", "metadata", "orphans"]
_VALID_CHECKS = set(DEFAULT_CHECKS)


def _normalize_checks(checks: Iterable[str] | str | None) -> list[str]:
    if checks is None or checks == "":
        return list(DEFAULT_CHECKS)
    if isinstance(checks, str):
        raw = [part.strip() for part in checks.split(",")]
    else:
        raw = [str(part).strip() for part in checks]
    out: list[str] = []
    for check in raw:
        if check and check in _VALID_CHECKS and check not in out:
            out.append(check)
    return out or list(DEFAULT_CHECKS)


def _limit_rows(rows: list[dict], limit: int) -> list[dict]:
    if limit <= 0:
        return rows
    return rows[:limit]


def _freshness_findings(db: VaultDB, limit: int) -> list[dict]:
    rows = db.conn.execute(
        """SELECT id, title, freshness, last_verified, updated_at
           FROM knowledge
           WHERE COALESCE(freshness, 1.0) < 0.5 OR COALESCE(last_verified, '') = ''
           ORDER BY freshness ASC, id ASC"""
    ).fetchall()
    return _limit_rows([dict(row) for row in rows], limit)


def _dedup_findings(db: VaultDB, limit: int) -> list[dict]:
    by_title = defaultdict(list)
    by_hash = defaultdict(list)
    for row in db.conn.execute(
        "SELECT id, title, content_hash FROM knowledge ORDER BY id ASC"
    ).fetchall():
        title_key = " ".join((row["title"] or "").casefold().split())
        if title_key:
            by_title[title_key].append({"id": row["id"], "title": row["title"]})
        if row["content_hash"]:
            by_hash[row["content_hash"]].append({"id": row["id"], "title": row["title"]})

    findings: list[dict] = []
    for key, items in sorted(by_title.items()):
        if len(items) > 1:
            findings.append({"type": "title", "key": key, "items": items})
    for key, items in sorted(by_hash.items()):
        if len(items) > 1:
            findings.append({"type": "content_hash", "key": key, "items": items})
    return _limit_rows(findings, limit)


def _convergence_findings(db: VaultDB, limit: int) -> list[dict]:
    rows = db.conn.execute(
        """SELECT id, title, convergence_status, convergence_score, trust
           FROM knowledge
           WHERE COALESCE(convergence_status, 'unknown') IN ('unknown', 'weak', 'insufficient')
              OR COALESCE(convergence_score, 1.0) < 0.5
           ORDER BY id ASC"""
    ).fetchall()
    return _limit_rows([dict(row) for row in rows], limit)


def _metadata_findings(db: VaultDB, limit: int) -> list[dict]:
    rows = db.conn.execute(
        """SELECT id, title, layer, category, tags, trust, source, content_raw
           FROM knowledge
           ORDER BY id ASC"""
    ).fetchall()
    findings: list[dict] = []
    for row in rows:
        issues = []
        if not (row["title"] or "").strip():
            issues.append("missing_title")
        if not (row["content_raw"] or "").strip():
            issues.append("empty_content")
        if not (row["layer"] or "").strip():
            issues.append("missing_layer")
        if not (row["category"] or "").strip() or row["category"] == "general":
            issues.append("weak_category")
        if not (row["tags"] or "").strip():
            issues.append("missing_tags")
        try:
            trust = float(row["trust"])
        except (TypeError, ValueError):
            trust = 0.0
        if trust < 0.4:
            issues.append("low_trust")
        if issues:
            findings.append({"id": row["id"], "title": row["title"], "issues": issues})
    return _limit_rows(findings, limit)


def _orphan_findings(db: VaultDB, limit: int) -> list[dict]:
    findings: list[dict] = []
    try:
        node_rows = db.conn.execute(
            """SELECT n.knowledge_id, COUNT(*) AS n
               FROM knowledge_nodes n
               LEFT JOIN knowledge k ON k.id = n.knowledge_id
               WHERE k.id IS NULL
               GROUP BY n.knowledge_id
               ORDER BY n.knowledge_id ASC"""
        ).fetchall()
        for row in node_rows:
            findings.append({"type": "knowledge_nodes", "knowledge_id": row["knowledge_id"], "rows": row["n"]})
    except Exception:
        pass
    try:
        claim_rows = db.conn.execute(
            """SELECT c.knowledge_id, COUNT(*) AS n
               FROM knowledge_claims c
               LEFT JOIN knowledge k ON k.id = c.knowledge_id
               WHERE k.id IS NULL
               GROUP BY c.knowledge_id
               ORDER BY c.knowledge_id ASC"""
        ).fetchall()
        for row in claim_rows:
            findings.append({"type": "knowledge_claims", "knowledge_id": row["knowledge_id"], "rows": row["n"]})
    except Exception:
        pass
    return _limit_rows(findings, limit)


def build_dream_report(payload: dict) -> str:
    summary = payload["summary"]
    checks = payload["checks"]
    lines = [
        "# Vault Dream Report",
        "",
        f"Generated: {payload['generated_at']}",
        f"Mode: {payload['mode']}",
        f"Checks: {', '.join(checks)}",
        "",
        "## Summary",
        "",
        f"- stale: {summary['stale']}",
        f"- duplicates: {summary['duplicates']}",
        f"- weak: {summary['weak']}",
        f"- metadata: {summary['metadata']}",
        f"- orphans: {summary['orphans']}",
        f"- actions_applied: {summary['actions_applied']}",
        "",
        "## Recommended actions",
        "",
        "- Review duplicate groups before merging; dream never deletes automatically.",
        "- Promote or reject old memory candidates through explicit memory tools.",
        "- Improve weak metadata (category, tags, trust, source) manually or via reviewed candidates.",
        f"- Proposed safe actions: {len(payload.get('proposed_actions', []))}",
        f"- Applied safe actions: {len(payload.get('applied_actions', []))}",
    ]
    for section, title in [
        ("freshness", "Freshness"),
        ("dedup", "Duplicate candidates"),
        ("convergence", "Convergence / weak knowledge"),
        ("metadata", "Weak metadata"),
        ("orphans", "Orphan map rows"),
    ]:
        items = payload["findings"].get(section, [])
        lines.extend(["", f"## {title}", "", f"Count: {len(items)}"])
        for item in items[:20]:
            lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def _build_safe_actions(findings: dict[str, list[dict]]) -> list[dict]:
    """Build deterministic low-risk actions from report findings.

    The first safe action set is deliberately narrow: it only improves weak
    metadata previews by adding a review tag or replacing the catch-all
    ``general`` category with ``review``. It never deletes, merges, rewrites
    content, or changes trust.
    """
    actions: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for item in findings.get("metadata", []):
        kid = int(item.get("id") or 0)
        if kid <= 0:
            continue
        issues = set(item.get("issues") or [])
        if "missing_tags" in issues and ("set_tags", kid) not in seen:
            actions.append({
                "type": "set_tags",
                "knowledge_id": kid,
                "value": "needs-review",
                "reason": "metadata check found missing_tags",
            })
            seen.add(("set_tags", kid))
        if "weak_category" in issues and ("set_category", kid) not in seen:
            actions.append({
                "type": "set_category",
                "knowledge_id": kid,
                "value": "review",
                "reason": "metadata check found weak_category",
            })
            seen.add(("set_category", kid))
    return actions


def _write_plan(project: Path, payload: dict) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    path = project / "reports" / "dream" / "plans" / f"{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path.relative_to(project))


def _apply_safe_actions(db: VaultDB, actions: list[dict]) -> list[dict]:
    applied: list[dict] = []
    for action in actions:
        action_type = action.get("type")
        kid = int(action.get("knowledge_id") or 0)
        row = db.get_knowledge(kid)
        if not row:
            applied.append({**action, "status": "skipped", "reason": "knowledge row not found"})
            continue
        if action_type == "set_tags":
            before = row.get("tags", "")
            if str(before).strip():
                applied.append({**action, "status": "skipped", "before": before, "reason": "tags no longer empty"})
                continue
            db.update_knowledge(kid, tags=str(action.get("value") or "needs-review"))
            applied.append({**action, "status": "applied", "before": before, "after": action.get("value")})
        elif action_type == "set_category":
            before = row.get("category", "")
            if before not in {"", "general"}:
                applied.append({**action, "status": "skipped", "before": before, "reason": "category no longer weak"})
                continue
            db.update_knowledge(kid, category=str(action.get("value") or "review"))
            applied.append({**action, "status": "applied", "before": before, "after": action.get("value")})
        else:
            applied.append({**action, "status": "skipped", "reason": "unsupported safe action"})
    return applied


def run_dream(
    project_dir: str | Path,
    *,
    mode: str = "report",
    checks: Iterable[str] | str | None = None,
    limit: int = 50,
    write_report: bool = False,
    backup: bool = True,
) -> dict:
    project = Path(project_dir)
    if mode not in {"report", "apply_safe"}:
        raise ValueError("mode must be report or apply_safe")
    try:
        limit_i = int(limit)
    except (TypeError, ValueError):
        limit_i = 50
    if limit_i < 0:
        limit_i = 50

    selected = _normalize_checks(checks)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    report_path = ""
    backup_path = ""
    plan_path = ""

    findings: dict[str, list[dict]] = {}
    actions_applied = 0
    db_path = project / "vault.db"

    if mode == "report" and not db_path.exists():
        payload = {
            "mode": mode,
            "checks": selected,
            "limit": limit_i,
            "generated_at": generated_at,
            "summary": {
                "stale": 0,
                "duplicates": 0,
                "weak": 0,
                "metadata": 0,
                "orphans": 0,
                "actions_applied": 0,
            },
            "findings": findings,
            "proposed_actions": [],
            "applied_actions": [],
            "plan_path": plan_path,
            "report_path": report_path,
            "backup_path": backup_path,
            "warning": "vault.db missing; report generated without creating or mutating the active database",
            "next_action": "Initialize or compile the vault database before running dream checks",
        }
        if write_report:
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
            path = project / "reports" / "dream" / f"{stamp}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(build_dream_report(payload), encoding="utf-8")
            payload["report_path"] = str(path.relative_to(project))
        return payload

    proposed_actions: list[dict] = []
    applied_actions: list[dict] = []

    with VaultDB(db_path) as db:
        if "freshness" in selected:
            findings["freshness"] = _freshness_findings(db, limit_i)
        if "dedup" in selected:
            findings["dedup"] = _dedup_findings(db, limit_i)
        if "convergence" in selected:
            findings["convergence"] = _convergence_findings(db, limit_i)
        if "metadata" in selected:
            findings["metadata"] = _metadata_findings(db, limit_i)
        if "orphans" in selected:
            findings["orphans"] = _orphan_findings(db, limit_i)

        proposed_actions = _build_safe_actions(findings)
        if mode == "apply_safe" and backup:
            from .db_backup import backup_database

            backup_result = backup_database(db_path, verify=True)
            backup_path = backup_result.get("backup_path", "")
        if mode == "apply_safe":
            applied_actions = _apply_safe_actions(db, proposed_actions)
            actions_applied = sum(1 for action in applied_actions if action.get("status") == "applied")

    summary = {
        "stale": len(findings.get("freshness", [])),
        "duplicates": len(findings.get("dedup", [])),
        "weak": len(findings.get("convergence", [])),
        "metadata": len(findings.get("metadata", [])),
        "orphans": len(findings.get("orphans", [])),
        "actions_applied": actions_applied,
    }
    payload = {
        "mode": mode,
        "checks": selected,
        "limit": limit_i,
        "generated_at": generated_at,
        "summary": summary,
        "findings": findings,
        "proposed_actions": proposed_actions,
        "applied_actions": applied_actions,
        "plan_path": plan_path,
        "report_path": report_path,
        "backup_path": backup_path,
        "next_action": "Review report and proposed_actions, then rerun with apply_safe if desired" if mode == "report" else "Review applied_actions; restore backup_path if the safe apply needs rollback",
    }
    if proposed_actions:
        plan_path = _write_plan(project, payload)
        payload["plan_path"] = plan_path
    if write_report:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
        path = project / "reports" / "dream" / f"{stamp}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(build_dream_report(payload), encoding="utf-8")
        payload["report_path"] = str(path.relative_to(project))
    return payload
