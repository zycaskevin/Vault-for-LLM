from __future__ import annotations

from argparse import Namespace
from datetime import datetime, timedelta, timezone
import json

from vault.automation import (
    automation_activity,
    automation_brief,
    automation_cycle,
    automation_doctor,
    automation_eval,
    automation_handoff,
    automation_inbox,
    automation_plan,
    automation_report,
    automation_run,
    load_policy,
)
from vault.db import VaultDB
from vault.memory import create_candidate


def _init_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "raw").mkdir()
    with VaultDB(project / "vault.db") as db:
        db.set_config("embedding_provider", "hash")
    return project


def _write_auto_promote_policy(project):
    (project / "automation_policy.yaml").write_text(
        "\n".join(
            [
                "mode: balanced",
                "auto_promote_low_risk_candidates: true",
                "auto_promote_max_per_run: 5",
                "auto_promote_min_trust: 0.65",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _create_low_risk_session_candidate(db: VaultDB, *, title: str = "Reusable session lesson") -> str:
    result = create_candidate(
        db,
        title=title,
        content=(
            "Decision: automation may promote low-risk session lessons because the candidate "
            "passed privacy, duplicate, metadata, and quality gates with a source reference."
        ),
        reason="Reusable low-risk lesson captured from a reviewed session.",
        source="session_capture",
        source_ref="codex:session:test#L1-L4",
        memory_type="session_lesson",
        category="decision",
        tags="session-capture,decision,automation",
        trust=0.82,
        scope="project",
        sensitivity="low",
    )
    assert result["status"] == "candidate_created"
    assert result["gates"] == {
        "privacy": "pass",
        "duplicate": "pass",
        "metadata": "pass",
        "quality": "pass",
    }
    return result["candidate_id"]


def test_automation_plan_writes_default_policy(tmp_path):
    project = _init_project(tmp_path)

    payload = automation_plan(project, mode="balanced", write_policy_file=True)

    assert payload["action"] == "plan"
    assert payload["mode"] == "balanced"
    assert payload["policy_path"] == "automation_policy.yaml"
    assert (project / "automation_policy.yaml").exists()
    policy = load_policy(project)
    assert policy["auto_archive_expired"] is True
    assert policy["protect_used_expired"] is True
    assert policy["dream_write_candidates"] is True
    assert policy["forgetting_write_candidates"] is True
    assert policy["auto_promote_low_risk_candidates"] is False
    assert any(item["id"] == "ttl_archive_apply" for item in payload["planned_actions"])
    dream_candidate_action = next(
        item for item in payload["planned_actions"] if item["id"] == "dream_candidate_suggestions"
    )
    assert dream_candidate_action["enabled"] is True
    forgetting_candidate_action = next(
        item for item in payload["planned_actions"] if item["id"] == "forgetting_candidate_suggestions"
    )
    assert forgetting_candidate_action["enabled"] is True


def test_automation_run_balanced_apply_archives_expired_memory(tmp_path):
    project = _init_project(tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    with VaultDB(project / "vault.db") as db:
        expired_id = db.add_knowledge("Expired", "Short lived", expires_at=expired)
        future_id = db.add_knowledge("Future", "Still active", expires_at=future)

    payload = automation_run(project, mode="balanced", apply=True, limit=10, write_reports=True)

    assert payload["status"] == "completed"
    assert payload["archive_expired"]["dry_run"] is False
    assert payload["archive_expired"]["archived_count"] == 1
    assert payload["dry_run_diff"]["applied_count"] == 1
    assert payload["dry_run_diff"]["hard_delete"] is False
    assert payload["dry_run_diff"]["promote_candidates"] is False
    assert payload["action_ledger"][0]["status"] == "applied"
    assert payload["action_ledger"][0]["before"] == {"status": "active"}
    assert payload["action_ledger"][0]["after"] == {"status": "archived"}
    assert payload["report_path"].startswith("reports/automation/")
    assert payload["dream"]["report_path"].startswith("reports/dream/")
    with VaultDB(project / "vault.db") as db:
        assert db.get_knowledge(expired_id)["status"] == "archived"
        assert db.get_knowledge(future_id)["status"] == "active"


def test_automation_run_protects_expired_but_used_memory(tmp_path):
    project = _init_project(tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with VaultDB(project / "vault.db") as db:
        expired_id = db.add_knowledge("Still useful expired SOP", "Deployment rollback", expires_at=expired)
        db.record_knowledge_access([expired_id])

    payload = automation_run(project, mode="balanced", apply=True, limit=10, write_reports=False)

    assert payload["archive_expired"]["archived_count"] == 0
    assert payload["archive_expired"]["skipped_used_count"] == 1
    assert payload["dry_run_diff"]["skipped_usage_count"] == 1
    assert payload["usage_review"]["expired_used_review_count"] == 1
    assert payload["forgetting"]["candidates_written"] == 1
    assert payload["action_ledger"][0]["status"] == "skipped_usage"
    assert payload["human_review"]["required"] is True
    assert {"kind": "expired_but_used", "count": 1} in payload["human_review"]["items"]
    assert {"kind": "forgetting_candidate_suggestions", "count": 1} in payload["human_review"]["items"]
    with VaultDB(project / "vault.db") as db:
        assert db.get_knowledge(expired_id)["status"] == "active"
        forgetting_candidates = [
            item for item in db.list_memory_candidates(limit=20)
            if item["memory_type"] == "forgetting_suggestion"
        ]
    assert len(forgetting_candidates) == 1
    assert forgetting_candidates[0]["source"] == "automation"


def test_automation_cli_shows_usage_review(tmp_path, monkeypatch, capsys):
    from vault.cli import cmd_automation

    project = _init_project(tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with VaultDB(project / "vault.db") as db:
        expired_id = db.add_knowledge("Still useful expired SOP", "Deployment rollback", expires_at=expired)
        db.record_knowledge_access([expired_id])
    monkeypatch.chdir(project)

    cmd_automation(
        Namespace(
            automation_action="run",
            mode="balanced",
            limit=10,
            apply=True,
            no_report=True,
            write_policy=False,
            overwrite_policy=False,
            json=False,
            pretty=False,
        )
    )

    out = capsys.readouterr().out
    assert "Usage review:" in out
    assert "review_expired_but_used" in out
    assert "skipped_used=1" in out
    assert "action ledger:" in out


def test_automation_run_conservative_apply_stays_dry_run(tmp_path):
    project = _init_project(tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with VaultDB(project / "vault.db") as db:
        expired_id = db.add_knowledge("Expired", "Short lived", expires_at=expired)

    payload = automation_run(project, mode="conservative", apply=True, limit=10, write_reports=False)

    assert payload["archive_expired"]["dry_run"] is True
    assert payload["archive_expired"]["archived_count"] == 0
    assert payload["warning"] == "apply requested, but policy auto_archive_expired is false"
    with VaultDB(project / "vault.db") as db:
        assert db.get_knowledge(expired_id)["status"] == "active"


def test_automation_run_balanced_writes_dream_candidates_by_policy(tmp_path):
    project = _init_project(tmp_path)
    with VaultDB(project / "vault.db") as db:
        db.add_knowledge(
            "Weak metadata for automation",
            "Automation should pre-fill a Dream review candidate without promoting active memory.",
            category="general",
            tags="",
            trust=0.3,
        )
        before = db.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"]

    payload = automation_run(project, mode="balanced", apply=True, limit=10, write_reports=False)

    assert payload["policy"]["dream_write_candidates"] is True
    assert payload["dream"]["summary"]["candidate_suggestions"] >= 1
    assert payload["dream"]["summary"]["candidates_written"] >= 1
    assert payload["dry_run_diff"]["promote_candidates"] is False
    assert {
        "kind": "dream_candidate_suggestions",
        "count": payload["dream"]["summary"]["candidate_suggestions"],
    } in payload["human_review"]["items"]
    with VaultDB(project / "vault.db") as db:
        assert db.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"] == before
        candidates = db.list_memory_candidates()
    assert len(candidates) == payload["dream"]["summary"]["candidates_written"]
    assert {item["source"] for item in candidates} == {"dream"}
    assert {item["memory_type"] for item in candidates} == {"dream_suggestion"}


def test_automation_report_summarizes_dream_learning_policy(tmp_path):
    project = _init_project(tmp_path)
    policy_dir = project / "reports" / "automation"
    policy_dir.mkdir(parents=True)
    (policy_dir / "learning_policy.json").write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-06-23T00:00:00+00:00",
                "readiness": "learning",
                "event_count": 6,
                "rules": [
                    {
                        "selector": {
                            "source": "dream",
                            "memory_type": "dream_suggestion",
                            "category": "dream-review",
                        },
                        "action": "prefer_candidates",
                        "recommendation": "prefer",
                        "priority_multiplier": 1.15,
                        "confidence": 0.9,
                        "reason": "Dream suggestions are often promoted.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with VaultDB(project / "vault.db") as db:
        db.add_knowledge(
            "Learning policy automation item",
            "Automation should include Dream learning-policy status in report summaries.",
            category="general",
            tags="",
            trust=0.3,
        )

    run = automation_run(project, mode="balanced", apply=True, limit=10, write_reports=True)
    latest = automation_report(project, latest=True, detail=False)

    assert run["dream"]["learning_policy"]["applied_rules"] >= 1
    assert latest["report"]["dream_learning_policy_status"] == "loaded"
    assert latest["report"]["dream_learning_policy_applied_rules"] == run["dream"]["learning_policy"]["applied_rules"]


def test_automation_run_balanced_skips_existing_dream_candidates(tmp_path):
    project = _init_project(tmp_path)
    with VaultDB(project / "vault.db") as db:
        db.add_knowledge(
            "Recurring Dream suggestion",
            "Repeated automation runs should not create duplicate Dream review candidates.",
            category="general",
            tags="",
            trust=0.3,
        )

    first = automation_run(project, mode="balanced", apply=True, limit=10, write_reports=True)
    second = automation_run(project, mode="balanced", apply=True, limit=10, write_reports=True)
    latest = automation_report(project, latest=True, detail=False)

    assert first["dream"]["summary"]["candidates_written"] >= 1
    assert second["dream"]["summary"]["candidates_written"] == 0
    assert second["dream"]["summary"]["candidates_skipped_existing"] >= first["dream"]["summary"]["candidates_written"]
    assert latest["report"]["dream_candidates_written"] == 0
    assert latest["report"]["dream_candidates_skipped_existing"] == second["dream"]["summary"]["candidates_skipped_existing"]
    with VaultDB(project / "vault.db") as db:
        assert len(db.list_memory_candidates()) == first["dream"]["summary"]["candidates_written"]


def test_automation_run_conservative_does_not_write_dream_candidates(tmp_path):
    project = _init_project(tmp_path)
    with VaultDB(project / "vault.db") as db:
        db.add_knowledge(
            "Weak conservative automation",
            "Conservative automation should report Dream suggestions without writing candidates.",
            category="general",
            tags="",
            trust=0.3,
        )

    payload = automation_run(project, mode="conservative", apply=False, limit=10, write_reports=False)

    assert payload["policy"]["dream_write_candidates"] is False
    assert payload["dream"]["summary"]["candidate_suggestions"] >= 1
    assert payload["dream"]["summary"]["candidates_written"] == 0
    with VaultDB(project / "vault.db") as db:
        assert db.list_memory_candidates() == []


def test_automation_run_without_apply_does_not_write_dream_candidates(tmp_path):
    project = _init_project(tmp_path)
    with VaultDB(project / "vault.db") as db:
        db.add_knowledge(
            "Report-only balanced automation",
            "Balanced automation without apply should report Dream suggestions without writing candidates.",
            category="general",
            tags="",
            trust=0.3,
        )

    payload = automation_run(project, mode="balanced", apply=False, limit=10, write_reports=False)

    assert payload["policy"]["dream_write_candidates"] is True
    assert payload["policy"]["dream_write_candidates_requires_apply"] is True
    assert payload["dream"]["summary"]["candidate_suggestions"] >= 1
    assert payload["dream"]["summary"]["candidates_written"] == 0
    with VaultDB(project / "vault.db") as db:
        assert db.list_memory_candidates() == []


def test_automation_run_does_not_auto_promote_by_default(tmp_path):
    project = _init_project(tmp_path)
    with VaultDB(project / "vault.db") as db:
        candidate_id = _create_low_risk_session_candidate(db)
        before_active = db.conn.execute("SELECT COUNT(*) AS n FROM knowledge WHERE status = 'active'").fetchone()["n"]

    payload = automation_run(project, mode="balanced", apply=True, limit=10, write_reports=False)

    assert payload["policy"]["auto_promote_low_risk_candidates"] is False
    assert payload["auto_promote"]["enabled"] is False
    assert payload["auto_promote"]["promoted_count"] == 0
    assert payload["dry_run_diff"]["promote_candidates"] is False
    with VaultDB(project / "vault.db") as db:
        assert db.get_memory_candidate(candidate_id)["status"] == "candidate"
        assert db.conn.execute("SELECT COUNT(*) AS n FROM knowledge WHERE status = 'active'").fetchone()["n"] == before_active


def test_automation_run_previews_low_risk_auto_promote_without_apply(tmp_path):
    project = _init_project(tmp_path)
    _write_auto_promote_policy(project)
    with VaultDB(project / "vault.db") as db:
        candidate_id = _create_low_risk_session_candidate(db)
        before_active = db.conn.execute("SELECT COUNT(*) AS n FROM knowledge WHERE status = 'active'").fetchone()["n"]

    payload = automation_run(project, mode="balanced", apply=False, limit=10, write_reports=False)

    assert payload["auto_promote"]["enabled"] is True
    assert payload["auto_promote"]["status"] == "preview"
    assert payload["auto_promote"]["would_promote_count"] == 1
    assert payload["auto_promote"]["promoted_count"] == 0
    assert payload["dry_run_diff"]["promote_candidates"] is True
    assert {"kind": "auto_promote_low_risk_preview", "count": 1} in payload["human_review"]["items"]
    with VaultDB(project / "vault.db") as db:
        assert db.get_memory_candidate(candidate_id)["status"] == "candidate"
        assert db.conn.execute("SELECT COUNT(*) AS n FROM knowledge WHERE status = 'active'").fetchone()["n"] == before_active


def test_automation_run_auto_promotes_only_low_risk_policy_matches(tmp_path):
    project = _init_project(tmp_path)
    _write_auto_promote_policy(project)
    with VaultDB(project / "vault.db") as db:
        safe_id = _create_low_risk_session_candidate(db, title="Safe session lesson for promotion")
        high_result = create_candidate(
            db,
            title="High sensitivity session lesson stays candidate",
            content=(
                "Decision: high sensitivity memories require human review because automated promotion "
                "must preserve the private memory boundary and audit trail."
            ),
            reason="High sensitivity should not be promoted by the low-risk policy.",
            source="session_capture",
            source_ref="codex:session:test#L8-L12",
            memory_type="session_lesson",
            category="decision",
            tags="session-capture,decision,privacy",
            trust=0.9,
            scope="project",
            sensitivity="high",
        )
        assert high_result["status"] == "candidate_created"
        before_active = db.conn.execute("SELECT COUNT(*) AS n FROM knowledge WHERE status = 'active'").fetchone()["n"]

    payload = automation_run(project, mode="balanced", apply=True, limit=10, write_reports=False)

    assert payload["auto_promote"]["enabled"] is True
    assert payload["auto_promote"]["status"] == "completed"
    assert payload["auto_promote"]["would_promote_count"] == 1
    assert payload["auto_promote"]["promoted_count"] == 1
    assert payload["dry_run_diff"]["promote_candidates"] is True
    assert payload["dry_run_diff"]["applied_promotions_count"] == 1
    assert {"kind": "auto_promote_low_risk_preview", "count": 1} in payload["human_review"]["items"]
    assert {"kind": "auto_promoted_low_risk", "count": 1} in payload["human_review"]["items"]
    skipped_reasons = {
        item.get("reason", "")
        for item in payload["auto_promote"]["items"]
        if item.get("candidate_id") == high_result["candidate_id"]
    }
    assert any("sensitivity_not_allowed:high" in reason for reason in skipped_reasons)
    with VaultDB(project / "vault.db") as db:
        assert db.get_memory_candidate(safe_id)["status"] == "promoted"
        assert db.get_memory_candidate(high_result["candidate_id"])["status"] == "candidate"
        assert db.conn.execute("SELECT COUNT(*) AS n FROM knowledge WHERE status = 'active'").fetchone()["n"] == before_active + 1


def test_automation_activity_summarizes_auto_promote_decisions_without_content(tmp_path):
    project = _init_project(tmp_path)
    _write_auto_promote_policy(project)
    with VaultDB(project / "vault.db") as db:
        safe_id = _create_low_risk_session_candidate(db, title="Visible low-risk activity")
        high_result = create_candidate(
            db,
            title="Skipped high sensitivity activity",
            content=(
                "Decision: high sensitivity candidates stay in review because activity "
                "summaries should explain skip reasons without exposing content."
            ),
            reason="High sensitivity should stay review-only.",
            source="session_capture",
            source_ref="codex:session:activity#L8-L12",
            memory_type="session_lesson",
            category="decision",
            tags="session-capture,decision,privacy",
            trust=0.9,
            scope="project",
            sensitivity="high",
        )

    automation_run(project, mode="balanced", apply=True, limit=10, write_reports=True)
    payload = automation_activity(project, limit=3, event_limit=10)

    assert payload["action"] == "activity"
    assert payload["status"] == "completed"
    assert payload["totals"]["auto_promote_enabled_runs"] == 1
    assert payload["totals"]["promoted_count"] == 1
    assert payload["totals"]["skipped_count"] >= 1
    assert payload["safety"]["includes_raw_candidate_content"] is False
    promoted = [item for item in payload["events"] if item["kind"] == "auto_promoted_low_risk"]
    skipped = [item for item in payload["events"] if item["kind"] == "auto_promote_skipped"]
    assert promoted and promoted[0]["candidate_id"] == safe_id
    assert skipped and skipped[0]["candidate_id"] == high_result["candidate_id"]
    assert "sensitivity_not_allowed:high" in skipped[0]["reason"]
    assert skipped[0]["title_hidden"] is True
    assert skipped[0]["title"] == ""
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "summaries should explain skip reasons without exposing content" not in rendered
    assert "Skipped high sensitivity activity" not in rendered


def test_automation_activity_reports_preview_without_promoting(tmp_path):
    project = _init_project(tmp_path)
    _write_auto_promote_policy(project)
    with VaultDB(project / "vault.db") as db:
        candidate_id = _create_low_risk_session_candidate(db, title="Preview activity lesson")

    automation_run(project, mode="balanced", apply=False, limit=10, write_reports=True)
    payload = automation_activity(project, limit=1, event_limit=5)

    assert payload["totals"]["would_promote_count"] == 1
    assert payload["totals"]["promoted_count"] == 0
    assert payload["events"][0]["kind"] == "auto_promote_preview"
    assert payload["events"][0]["candidate_id"] == candidate_id


def test_automation_brief_combines_learning_weights_forgetting_and_review(tmp_path):
    project = _init_project(tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with VaultDB(project / "vault.db") as db:
        used_id = db.add_knowledge(
            "Expired but cited deployment SOP",
            "Deployment rollback remains important even after its TTL.",
            expires_at=expired,
            category="workflow",
            tags="deployment,rollback",
        )
        db.record_knowledge_access([used_id], cited=True)
        db.add_knowledge(
            "Unused expired temporary note",
            "Temporary note can move out of daily recall.",
            expires_at=expired,
        )
        _create_low_risk_session_candidate(db, title="Brief review lesson")
        db.record_memory_feedback(
            {
                "candidate_id": "brief_promoted",
                "source": "session_capture",
                "memory_type": "session_lesson",
                "category": "decision",
                "outcome": "promoted",
                "score": 1.0,
                "reason": "review accepted",
            }
        )

    payload = automation_brief(project, limit=5, review_limit=5, min_events=1, write_brief=True)

    assert payload["action"] == "brief"
    assert payload["status"] == "completed"
    assert payload["safety"]["read_only"] is True
    assert payload["safety"]["forgetting_is_strategy_only"] is True
    assert payload["learning"]["readiness"] == "learning"
    assert payload["learning"]["top_rules"]
    assert payload["memory_weights"]["top_used"][0]["knowledge_id"] == used_id
    assert payload["memory_weights"]["top_used"][0]["weight_score"] == 3
    assert payload["forgetting_strategy"]["used_expired_count"] == 1
    assert payload["forgetting_strategy"]["archiveable_count"] == 1
    assert payload["human_review_5_percent"]["items"]
    assert payload["brief_path"] == "reports/automation/brief-latest.json"
    assert payload["brief_markdown_path"] == "reports/automation/brief-latest.md"
    assert (project / payload["brief_path"]).exists()
    assert (project / payload["brief_markdown_path"]).exists()
    written = json.loads((project / payload["brief_path"]).read_text(encoding="utf-8"))
    assert written["brief_markdown_path"] == "reports/automation/brief-latest.md"


def test_automation_apply_does_not_touch_private_or_high_sensitivity_memory(tmp_path):
    project = _init_project(tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with VaultDB(project / "vault.db") as db:
        private_id = db.add_knowledge(
            "Private expired profile",
            "Private notes should stay human-reviewed.",
            expires_at=expired,
            scope="private",
            sensitivity="low",
        )
        high_id = db.add_knowledge(
            "High sensitivity expired summary",
            "High sensitivity notes need explicit review.",
            expires_at=expired,
            scope="project",
            sensitivity="high",
        )

    payload = automation_run(project, mode="balanced", apply=True, limit=10, write_reports=False)

    assert payload["archive_expired"]["archived_count"] == 0
    assert payload["archive_expired"]["skipped_protected_count"] == 2
    assert payload["usage_review"]["expired_protected_count"] == 2
    assert payload["forgetting"]["candidates_written"] == 2
    assert payload["dry_run_diff"]["skipped_policy_count"] == 2
    assert payload["dry_run_diff"]["permission_changes"] is False
    assert {item["status"] for item in payload["action_ledger"]} == {"skipped_policy"}
    assert {"kind": "protected_expired", "count": 2} in payload["human_review"]["items"]
    with VaultDB(project / "vault.db") as db:
        assert db.get_knowledge(private_id)["status"] == "active"
        assert db.get_knowledge(high_id)["status"] == "active"
        forgetting_candidates = [
            item for item in db.list_memory_candidates(limit=20)
            if item["memory_type"] == "forgetting_suggestion"
        ]
    assert len(forgetting_candidates) == 2


def test_automation_run_without_apply_does_not_write_forgetting_candidates(tmp_path):
    project = _init_project(tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with VaultDB(project / "vault.db") as db:
        expired_id = db.add_knowledge("Used expired no apply", "Keep report-only without apply.", expires_at=expired)
        db.record_knowledge_access([expired_id])

    payload = automation_run(project, mode="balanced", apply=False, limit=10, write_reports=False)

    assert payload["policy"]["forgetting_write_candidates"] is True
    assert payload["policy"]["forgetting_write_candidates_requires_apply"] is True
    assert payload["forgetting"]["candidates_written"] == 0
    with VaultDB(project / "vault.db") as db:
        assert [
            item for item in db.list_memory_candidates(limit=20)
            if item["memory_type"] == "forgetting_suggestion"
        ] == []


def test_automation_forgetting_candidates_skip_existing(tmp_path):
    project = _init_project(tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with VaultDB(project / "vault.db") as db:
        expired_id = db.add_knowledge("Recurring forgetting", "Repeated forgetting candidates should be skipped.", expires_at=expired)
        db.record_knowledge_access([expired_id])

    first = automation_run(project, mode="balanced", apply=True, limit=10, write_reports=True)
    second = automation_run(project, mode="balanced", apply=True, limit=10, write_reports=True)
    latest = automation_report(project, latest=True, detail=False)

    assert first["forgetting"]["candidates_written"] == 1
    assert second["forgetting"]["candidates_written"] == 0
    assert second["forgetting"]["candidates_skipped_existing"] == 1
    assert latest["report"]["forgetting_candidates_written"] == 0
    assert latest["report"]["forgetting_candidates_skipped_existing"] == 1


def test_automation_report_lists_recent_runs(tmp_path):
    project = _init_project(tmp_path)
    automation_run(project, mode="balanced", write_reports=True)

    payload = automation_report(project)

    assert payload["action"] == "report"
    assert payload["report_count"] == 1
    assert payload["reports"][0]["path"].startswith("reports/automation/")
    assert payload["reports"][0]["ledger_count"] >= 0


def test_automation_report_latest_detail_includes_ledger(tmp_path):
    project = _init_project(tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with VaultDB(project / "vault.db") as db:
        db.add_knowledge("Expired", "Short lived", expires_at=expired)

    run = automation_run(project, mode="balanced", apply=True, write_reports=True)
    payload = automation_report(project, latest=True, detail=True)

    assert payload["action"] == "report"
    assert payload["report_count"] == 1
    assert payload["report"]["path"] == run["report_path"]
    assert payload["report"]["archived_count"] == 1
    assert payload["report"]["dry_run_diff"]["applied_count"] == 1
    assert payload["report"]["ledger_count"] == 1
    assert payload["detail"]["action_ledger"][0]["status"] == "applied"


def test_automation_eval_reports_feedback_acceptance(tmp_path):
    project = _init_project(tmp_path)
    with VaultDB(project / "vault.db") as db:
        db.record_memory_feedback(
            {
                "candidate_id": "mem_good",
                "knowledge_id": 1,
                "source": "dream",
                "source_ref": "dream:metadata:1",
                "memory_type": "dream_suggestion",
                "category": "dream-review",
                "outcome": "promoted",
                "score": 1.0,
                "reason": "accepted by reviewer",
            }
        )
        db.record_memory_feedback(
            {
                "candidate_id": "mem_bad",
                "source": "dream",
                "source_ref": "dream:metadata:2",
                "memory_type": "dream_suggestion",
                "category": "dream-review",
                "outcome": "rejected",
                "score": 0.0,
                "reason": "too vague",
            }
        )

    payload = automation_eval(project, limit=10, min_events=2)

    assert payload["action"] == "eval"
    assert payload["status"] == "completed"
    assert payload["readiness"] == "learning"
    assert payload["event_count"] == 2
    assert payload["outcome_counts"] == {"promoted": 1, "rejected": 1}
    assert payload["source_memory_type_scores"][0]["source"] == "dream"
    assert payload["source_memory_type_scores"][0]["memory_type"] == "dream_suggestion"
    assert payload["source_memory_type_scores"][0]["acceptance_rate"] == 0.5
    assert payload["source_memory_type_scores"][0]["recommendation"] == "keep_observing"
    assert payload["learning_policy"]["bounds"]["no_auto_promote"] is True
    assert payload["learning_policy"]["rules"][0]["action"] == "keep_observing"


def test_automation_eval_builds_bounded_learning_policy(tmp_path):
    project = _init_project(tmp_path)
    with VaultDB(project / "vault.db") as db:
        for idx in range(3):
            db.record_memory_feedback(
                {
                    "candidate_id": f"good_{idx}",
                    "source": "dream",
                    "memory_type": "dream_suggestion",
                    "category": "dream-review",
                    "outcome": "promoted",
                    "score": 1.0,
                }
            )
        for idx in range(3):
            db.record_memory_feedback(
                {
                    "candidate_id": f"bad_{idx}",
                    "source": "import",
                    "memory_type": "raw_note",
                    "category": "scratch",
                    "outcome": "rejected",
                    "score": 0.0,
                }
            )

    payload = automation_eval(project, limit=10, min_events=3, write_learning_policy=True)

    rules = payload["learning_policy"]["rules"]
    by_source = {rule["selector"]["source"]: rule for rule in rules}
    assert by_source["dream"]["action"] == "prefer_candidates"
    assert by_source["dream"]["priority_multiplier"] == 1.15
    assert by_source["import"]["action"] == "downgrade_or_require_review"
    assert by_source["import"]["priority_multiplier"] == 0.85
    assert payload["learning_policy"]["bounds"]["priority_multiplier_min"] == 0.85
    assert payload["learning_policy"]["bounds"]["priority_multiplier_max"] == 1.15
    assert payload["learning_policy_path"] == "reports/automation/learning_policy.json"
    written = json.loads((project / payload["learning_policy_path"]).read_text(encoding="utf-8"))
    assert written["rules"] == rules


def test_automation_cycle_writes_learning_policy_and_runs_dream(tmp_path):
    project = _init_project(tmp_path)
    with VaultDB(project / "vault.db") as db:
        for idx in range(3):
            db.record_memory_feedback(
                {
                    "candidate_id": f"dream_good_{idx}",
                    "source": "dream",
                    "memory_type": "dream_suggestion",
                    "category": "dream-review",
                    "outcome": "promoted",
                    "score": 1.0,
                }
            )
        db.add_knowledge(
            "Cycle weak metadata",
            "Automation cycle should turn reviewed feedback into Dream review priority hints.",
            category="general",
            tags="",
            trust=0.3,
        )
        before_active = db.conn.execute("SELECT COUNT(*) AS n FROM knowledge WHERE status = 'active'").fetchone()["n"]

    payload = automation_cycle(project, mode="balanced", apply=True, limit=10, min_events=3, write_reports=True)

    assert payload["action"] == "cycle"
    assert payload["status"] == "completed"
    assert payload["eval"]["learning_policy_path"] == "reports/automation/learning_policy.json"
    assert payload["summary"]["learning_policy_path"] == "reports/automation/learning_policy.json"
    assert payload["summary"]["learning_rules"] >= 1
    assert payload["summary"]["dream_learning_policy_status"] == "loaded"
    assert payload["summary"]["dream_learning_policy_applied_rules"] >= 1
    assert payload["summary"]["candidates_written"] >= 1
    assert payload["summary"]["automation_report_path"].startswith("reports/automation/")
    assert (project / payload["summary"]["learning_policy_path"]).exists()
    assert (project / payload["summary"]["automation_report_path"]).exists()
    assert "does not auto-promote by default" in payload["principle"]
    with VaultDB(project / "vault.db") as db:
        assert db.conn.execute("SELECT COUNT(*) AS n FROM knowledge WHERE status = 'active'").fetchone()["n"] == before_active
        candidates = db.list_memory_candidates(limit=20)
    assert any(item["memory_type"] == "dream_suggestion" for item in candidates)


def test_automation_cycle_writes_compact_workspace_with_transcript_hints(tmp_path):
    project = _init_project(tmp_path)
    token = "sk-proj-1234567890abcdefghij1234567890"
    sessions = project / "sessions"
    sessions.mkdir()
    (sessions / "codex-session.md").write_text(
        f"Decision: cycle workspace must not expose {token} from transcript content.\n",
        encoding="utf-8",
    )
    with VaultDB(project / "vault.db") as db:
        for idx in range(3):
            db.record_memory_feedback(
                {
                    "candidate_id": f"dream_workspace_{idx}",
                    "source": "dream",
                    "memory_type": "dream_suggestion",
                    "category": "dream-review",
                    "outcome": "promoted",
                    "score": 1.0,
                }
            )
        db.add_knowledge(
            "Cycle workspace weak metadata",
            "Automation cycle workspace should give reviewers one compact next-step view.",
            category="general",
            tags="",
            trust=0.3,
        )

    payload = automation_cycle(
        project,
        mode="balanced",
        apply=True,
        limit=10,
        min_events=3,
        write_reports=True,
        write_workspace=True,
        include_transcripts=True,
        transcript_limit=3,
        inbox_limit=4,
    )

    assert payload["workspace_path"] == "reports/automation/cycle-latest.json"
    assert payload["workspace_markdown_path"] == "reports/automation/cycle-latest.md"
    path = project / payload["workspace_path"]
    assert path.exists()
    workspace = json.loads(path.read_text(encoding="utf-8"))
    assert workspace["action"] == "cycle_workspace"
    assert workspace["workspace_markdown_path"] == "reports/automation/cycle-latest.md"
    assert workspace["summary"]["learning_rules"] >= 1
    assert workspace["summary"]["auto_promote_enabled"] is False
    assert workspace["summary"]["auto_promote_promoted_count"] == 0
    assert workspace["candidate_review"]["content_hidden"] is True
    assert workspace["transcripts_to_capture"]["summary"]["count"] == 1
    assert workspace["transcripts_to_capture"]["summary"]["read_contents"] is False
    assert workspace["transcripts_to_capture"]["items"][0]["capture_path"] == "sessions/codex-session.md"
    assert workspace["curation_policy"]["rules"]
    assert workspace["priority_brief"]
    assert workspace["priority_brief"][0]["priority"] == "P1"
    assert "Review candidate memory queue" in workspace["priority_brief"][0]["title"]
    assert workspace["suggested_next_tasks"]
    assert workspace["suggested_next_tasks"][0]["requires_human_approval"] is True
    assert "Candidate queue items:" in workspace["agent_start_prompt"]
    assert "auto-promoted: 0" in workspace["agent_start_prompt"]
    assert workspace["safety"]["auto_promote"] is False
    assert workspace["safety"]["transcript_discovery_reads_contents"] is False
    assert token not in json.dumps(workspace)
    markdown = (project / payload["workspace_markdown_path"]).read_text(encoding="utf-8")
    assert "# Vault Automation Cycle Workspace" in markdown
    assert "## Priority Brief" in markdown
    assert "## Candidate Review" in markdown
    assert "## Transcripts To Capture" in markdown
    assert "## Curation Policy" in markdown
    assert "## Safety" in markdown
    assert "## Suggested Next Tasks" in markdown
    assert "## Agent Start Prompt" in markdown
    assert "Review candidate memory queue" in markdown
    assert "You are continuing a Vault-for-LLM memory automation cycle." in markdown
    assert "sessions/codex-session.md" in markdown
    assert token not in markdown


def test_automation_cycle_can_capture_transcripts_as_candidates_without_active_memory(tmp_path):
    project = _init_project(tmp_path)
    token = "sk-proj-1234567890abcdefghij1234567890"
    sessions = project / "sessions"
    sessions.mkdir()
    (sessions / "codex-session.md").write_text(
        "\n".join(
            [
                "Decision: automation cycle should capture reusable session lessons because agents forget context.",
                f"Fix: automation transcript capture must redact {token} because secrets stay out of handoffs.",
            ]
        ),
        encoding="utf-8",
    )
    with VaultDB(project / "vault.db") as db:
        before_active = db.conn.execute("SELECT COUNT(*) AS n FROM knowledge WHERE status = 'active'").fetchone()["n"]

    disabled = automation_cycle(
        project,
        mode="balanced",
        apply=True,
        limit=10,
        min_events=1,
        write_reports=False,
        write_workspace=True,
        include_transcripts=True,
        capture_transcripts=False,
    )
    assert disabled["transcript_capture"]["status"] == "disabled"
    assert disabled["transcript_capture"]["summary"]["candidates_written"] == 0

    payload = automation_cycle(
        project,
        mode="balanced",
        apply=True,
        limit=10,
        min_events=1,
        write_reports=False,
        write_workspace=True,
        include_transcripts=True,
        capture_transcripts=True,
        capture_transcript_limit=2,
        capture_max_candidates_per_transcript=5,
    )

    capture = payload["transcript_capture"]
    assert capture["status"] == "completed"
    assert capture["summary"]["transcripts_seen"] == 1
    assert capture["summary"]["transcripts_captured"] == 1
    assert capture["summary"]["candidates_written"] >= 1
    assert capture["safety"]["candidate_first"] is True
    assert capture["safety"]["auto_promote"] is False
    assert capture["safety"]["reads_transcript_contents"] is True
    assert payload["summary"]["transcript_capture_candidates_written"] >= 1
    assert payload["workspace"]["transcript_capture"]["content_hidden"] is True
    assert payload["workspace"]["safety"]["transcript_capture_reads_contents"] is True
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "content_preview" not in rendered
    assert token not in rendered
    markdown = (project / payload["workspace_markdown_path"]).read_text(encoding="utf-8")
    assert "## Transcript Capture" in markdown
    assert "candidates written" in markdown
    assert token not in markdown
    with VaultDB(project / "vault.db") as db:
        assert db.conn.execute("SELECT COUNT(*) AS n FROM knowledge WHERE status = 'active'").fetchone()["n"] == before_active
        rows = db.list_memory_candidates(status=None, limit=20)
    assert any(row["source"] == "session_capture" and row["memory_type"] == "session_lesson" for row in rows)


def test_automation_cycle_reports_low_risk_auto_promote_workspace_boundary(tmp_path):
    project = _init_project(tmp_path)
    _write_auto_promote_policy(project)
    with VaultDB(project / "vault.db") as db:
        candidate_id = _create_low_risk_session_candidate(db, title="Cycle low-risk session lesson")
        before_active = db.conn.execute("SELECT COUNT(*) AS n FROM knowledge WHERE status = 'active'").fetchone()["n"]

    payload = automation_cycle(
        project,
        mode="balanced",
        apply=True,
        limit=10,
        min_events=1,
        write_reports=True,
        write_workspace=True,
    )

    assert payload["summary"]["auto_promote_enabled"] is True
    assert payload["summary"]["auto_promote_promoted_count"] == 1
    assert payload["workspace"]["summary"]["auto_promote_promoted_count"] == 1
    assert payload["workspace"]["safety"]["auto_promote"] is True
    assert payload["workspace"]["safety"]["writes_active_memory"] is True
    assert "Review auto-promoted low-risk memories" in {
        item["title"] for item in payload["workspace"]["priority_brief"]
    }
    assert any(
        task["command"] == "vault automation report --latest --detail"
        for task in payload["workspace"]["suggested_next_tasks"]
    )
    assert "auto-promoted: 1" in payload["workspace"]["agent_start_prompt"]
    with VaultDB(project / "vault.db") as db:
        assert db.get_memory_candidate(candidate_id)["status"] == "promoted"
        assert db.conn.execute("SELECT COUNT(*) AS n FROM knowledge WHERE status = 'active'").fetchone()["n"] == before_active + 1


def test_automation_cycle_blocks_without_vault_db(tmp_path):
    payload = automation_cycle(tmp_path, min_events=1)

    assert payload["action"] == "cycle"
    assert payload["status"] == "blocked"
    assert payload["phase"] == "eval"
    assert payload["summary"]["feedback_events"] == 0
    assert "vault init" in payload["next_action"]


def test_automation_handoff_reads_latest_cycle_markdown(tmp_path):
    project = _init_project(tmp_path)
    report_dir = project / "reports" / "automation"
    report_dir.mkdir(parents=True)
    (report_dir / "cycle-latest.md").write_text(
        "# Vault Automation Cycle Workspace\n\n## Agent Start Prompt\n\nStart here.\n",
        encoding="utf-8",
    )

    payload = automation_handoff(project)

    assert payload["action"] == "handoff"
    assert payload["status"] == "completed"
    assert payload["handoff_path"] == "reports/automation/cycle-latest.md"
    assert payload["content_type"] == "markdown"
    assert "Agent Start Prompt" in payload["content"]
    assert payload["safety"]["writes_active_memory"] is False


def test_automation_handoff_path_must_stay_under_reports(tmp_path):
    project = _init_project(tmp_path)
    outside = project / "outside.md"
    outside.write_text("# outside\n", encoding="utf-8")

    try:
        automation_handoff(project, handoff_path=outside)
    except ValueError as exc:
        assert "reports/automation" in str(exc)
    else:
        raise AssertionError("expected automation_handoff to reject paths outside reports/automation")


def test_automation_report_specific_path_must_stay_under_report_dir(tmp_path):
    project = _init_project(tmp_path)
    outside = project / "not-automation-report.json"
    outside.write_text("{}", encoding="utf-8")

    try:
        automation_report(project, report_path=outside)
    except ValueError as exc:
        assert "reports/automation" in str(exc)
    else:
        raise AssertionError("expected automation_report to reject paths outside reports/automation")


def test_automation_cli_report_latest_detail_prints_ledger(tmp_path, monkeypatch, capsys):
    from vault.cli import cmd_automation

    project = _init_project(tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with VaultDB(project / "vault.db") as db:
        db.add_knowledge("Expired", "Short lived", expires_at=expired)
    automation_run(project, mode="balanced", apply=True, write_reports=True)
    monkeypatch.chdir(project)

    cmd_automation(
        Namespace(
            automation_action="report",
            mode=None,
            limit=10,
            latest=True,
            detail=True,
            report_path="",
            json=False,
            pretty=False,
        )
    )

    out = capsys.readouterr().out
    assert "Automation reports" in out
    assert "ledger entries: 1" in out
    assert "action ledger:" in out
    assert "archive_expired applied" in out


def test_automation_cli_activity_prints_closed_loop_counts(tmp_path, monkeypatch, capsys):
    from vault.cli import cmd_automation

    project = _init_project(tmp_path)
    _write_auto_promote_policy(project)
    with VaultDB(project / "vault.db") as db:
        _create_low_risk_session_candidate(db)
    automation_run(project, mode="balanced", apply=True, write_reports=True)
    monkeypatch.chdir(project)

    cmd_automation(
        Namespace(
            automation_action="activity",
            mode=None,
            limit=5,
            event_limit=5,
            json=False,
            pretty=False,
        )
    )

    out = capsys.readouterr().out
    assert "Automation activity" in out
    assert "promoted=1" in out
    assert "auto_promoted_low_risk" in out


def test_automation_cli_brief_prints_short_human_review(tmp_path, monkeypatch, capsys):
    from vault.cli import cmd_automation

    project = _init_project(tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with VaultDB(project / "vault.db") as db:
        used_id = db.add_knowledge("Brief CLI used expired", "Used expired memory.", expires_at=expired)
        db.record_knowledge_access([used_id], cited=True)
        _create_low_risk_session_candidate(db, title="Brief CLI review lesson")
    monkeypatch.chdir(project)

    cmd_automation(
        Namespace(
            automation_action="brief",
            mode=None,
            limit=5,
            review_limit=5,
            min_events=1,
            write_brief=True,
            brief_path="",
            json=False,
            pretty=False,
        )
    )

    out = capsys.readouterr().out
    assert "Automation intelligence brief" in out
    assert "Human review 5%" in out
    assert "used_expired=1" in out
    assert "brief: reports/automation/brief-latest.json" in out


def test_automation_cli_eval_prints_feedback_scores(tmp_path, monkeypatch, capsys):
    from vault.cli import cmd_automation

    project = _init_project(tmp_path)
    with VaultDB(project / "vault.db") as db:
        db.record_memory_feedback(
            {
                "candidate_id": "mem_feedback",
                "source": "automation",
                "memory_type": "forgetting_suggestion",
                "category": "forgetting-review",
                "outcome": "promoted",
                "score": 1.0,
                "reason": "review accepted",
            }
        )
    monkeypatch.chdir(project)

    cmd_automation(
        Namespace(
            automation_action="eval",
            mode=None,
            limit=10,
            min_events=1,
            json=False,
            pretty=False,
        )
    )

    out = capsys.readouterr().out
    assert "Automation eval" in out
    assert "feedback events: 1" in out
    assert "source=automation" in out
    assert "recommendation=prefer" in out


def test_automation_cli_cycle_prints_learning_summary(tmp_path, monkeypatch, capsys):
    from vault.cli import cmd_automation

    project = _init_project(tmp_path)
    with VaultDB(project / "vault.db") as db:
        for idx in range(2):
            db.record_memory_feedback(
                {
                    "candidate_id": f"dream_cli_{idx}",
                    "source": "dream",
                    "memory_type": "dream_suggestion",
                    "category": "dream-review",
                    "outcome": "promoted",
                    "score": 1.0,
                }
            )
        db.add_knowledge(
            "CLI cycle weak metadata",
            "CLI cycle should show learning-policy and Dream learning status.",
            category="general",
            tags="",
            trust=0.3,
        )
    monkeypatch.chdir(project)

    cmd_automation(
        Namespace(
            automation_action="cycle",
            mode="balanced",
            limit=10,
            min_events=2,
            apply=True,
            no_report=False,
            write_workspace=True,
            workspace_path="",
            inbox_limit=5,
            include_transcripts=False,
            transcript_limit=5,
            json=False,
            pretty=False,
        )
    )

    out = capsys.readouterr().out
    assert "Automation cycle" in out
    assert "learning policy: reports/automation/learning_policy.json" in out
    assert "dream learning: loaded" in out
    assert "workspace: reports/automation/cycle-latest.json" in out
    assert "workspace markdown: reports/automation/cycle-latest.md" in out
    assert "does not auto-promote by default" in out


def test_automation_cli_handoff_prints_markdown(tmp_path, monkeypatch, capsys):
    from vault.cli import cmd_automation

    project = _init_project(tmp_path)
    report_dir = project / "reports" / "automation"
    report_dir.mkdir(parents=True)
    (report_dir / "cycle-latest.md").write_text(
        "# Vault Automation Cycle Workspace\n\n## Priority Brief\n\nStart from the short handoff.\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(project)

    cmd_automation(
        Namespace(
            automation_action="handoff",
            mode=None,
            limit=50,
            source="auto",
            handoff_path="",
            json=False,
            pretty=False,
        )
    )

    out = capsys.readouterr().out
    assert "# Vault Automation Cycle Workspace" in out
    assert "## Priority Brief" in out
    assert "Start from the short handoff." in out


def test_automation_inbox_prioritizes_privacy_blocked_candidates(tmp_path):
    project = _init_project(tmp_path)
    token = "sk-proj-1234567890abcdefghij1234567890"
    with VaultDB(project / "vault.db") as db:
        safe = create_candidate(
            db,
            title="Decision: keep session capture candidate-first",
            content="Decision: session capture should stay candidate-first because active memory needs review.",
            reason="Reusable automation decision.",
            source="session_capture",
            source_ref="codex:session:1",
            memory_type="session_lesson",
            category="decision",
            tags="session-capture,decision",
        )
        blocked = create_candidate(
            db,
            title="Fix: redact standalone API keys",
            content=f"Fix: never show {token} in session capture reports because secrets must stay out.",
            reason="Privacy regression guard.",
            source="session_capture",
            source_ref="codex:session:2",
            memory_type="session_lesson",
            category="error",
            tags="session-capture,privacy",
        )

    payload = automation_inbox(project, limit=2)
    rendered = json.dumps(payload, ensure_ascii=False)

    assert payload["action"] == "inbox"
    assert payload["status"] == "completed"
    assert payload["summary"]["pending_candidates"] == 1
    assert payload["summary"]["rejected_candidates"] == 1
    assert payload["summary"]["privacy_blocked"] == 1
    assert payload["review_queue"][0]["id"] == blocked["candidate_id"]
    assert payload["review_queue"][0]["recommended_action"] == "block_or_redact"
    assert payload["review_queue"][1]["id"] == safe["candidate_id"]
    assert "content" not in payload["review_queue"][0]
    assert token not in rendered
    assert payload["safety"]["read_only"] is True
    assert payload["safety"]["auto_promote"] is False


def test_automation_inbox_can_include_redacted_content(tmp_path):
    project = _init_project(tmp_path)
    token = "sk-proj-1234567890abcdefghij1234567890"
    with VaultDB(project / "vault.db") as db:
        create_candidate(
            db,
            title="Fix: redact content",
            content=f"Fix: redact {token} before returning inbox content.",
            reason="Privacy regression guard.",
            source="session_capture",
            source_ref="codex:session:3",
            memory_type="session_lesson",
            category="error",
            tags="session-capture,privacy",
        )

    payload = automation_inbox(project, limit=1, include_content=True)
    item = payload["review_queue"][0]

    assert "content" in item
    assert "[REDACTED]" in item["content"]
    assert token not in json.dumps(payload)


def test_automation_inbox_writes_handoff_under_reports(tmp_path):
    project = _init_project(tmp_path)
    with VaultDB(project / "vault.db") as db:
        create_candidate(
            db,
            title="Decision: write inbox handoff",
            content="Decision: scheduled automation should write inbox handoff because the next agent needs a short review queue.",
            reason="Scheduled handoff workflow.",
            source="session_capture",
            source_ref="codex:session:handoff",
            memory_type="session_lesson",
            category="decision",
            tags="session-capture,handoff",
        )

    payload = automation_inbox(project, limit=3, write_handoff=True)
    path = project / payload["inbox_handoff_path"]
    written = json.loads(path.read_text(encoding="utf-8"))

    assert payload["inbox_handoff_path"] == "reports/automation/inbox-latest.json"
    assert written["action"] == "inbox"
    assert written["inbox_handoff_path"] == "reports/automation/inbox-latest.json"
    assert written["summary"]["pending_candidates"] == 1


def test_automation_inbox_can_include_transcript_discovery_hints(tmp_path):
    project = _init_project(tmp_path)
    sessions = project / "sessions"
    sessions.mkdir()
    token = "sk-proj-1234567890abcdefghij1234567890"
    (sessions / "codex-session.md").write_text(
        f"Decision: automation inbox discovery must not expose {token} from transcript content.",
        encoding="utf-8",
    )

    default_payload = automation_inbox(project)
    payload = automation_inbox(project, include_transcripts=True, transcript_limit=3)
    rendered = json.dumps(payload, ensure_ascii=False)

    assert default_payload["summary"]["uncaptured_transcripts"] == 0
    assert default_payload["transcript_discovery"] == {}
    assert payload["summary"]["uncaptured_transcripts"] == 1
    assert payload["summary"]["transcript_discovery_reads_contents"] is False
    assert payload["transcript_discovery"]["read_contents"] is False
    assert payload["transcript_discovery"]["transcripts"][0]["capture_path"] == "sessions/codex-session.md"
    assert token not in rendered


def test_automation_inbox_handoff_can_include_transcript_discovery(tmp_path):
    project = _init_project(tmp_path)
    sessions = project / "sessions"
    sessions.mkdir()
    (sessions / "hermes-session.jsonl").write_text(
        '{"role":"assistant","content":"Decision: scheduled inbox handoff should show uncaptured transcripts."}\n',
        encoding="utf-8",
    )

    payload = automation_inbox(project, include_transcripts=True, write_handoff=True)
    path = project / payload["inbox_handoff_path"]
    written = json.loads(path.read_text(encoding="utf-8"))

    assert written["summary"]["uncaptured_transcripts"] == 1
    assert written["transcript_discovery"]["transcripts"][0]["capture_path"] == "sessions/hermes-session.jsonl"


def test_automation_inbox_handoff_path_must_stay_under_reports(tmp_path):
    project = _init_project(tmp_path)

    try:
        automation_inbox(project, write_handoff=True, handoff_path="../outside.json")
    except ValueError as exc:
        assert "reports/automation" in str(exc)
    else:
        raise AssertionError("expected automation_inbox to reject handoff paths outside reports/automation")


def test_automation_cli_inbox_prints_short_review_queue(tmp_path, monkeypatch, capsys):
    from vault.cli import cmd_automation

    project = _init_project(tmp_path)
    with VaultDB(project / "vault.db") as db:
        create_candidate(
            db,
            title="Workflow: review inbox daily",
            content="Workflow: automation inbox should show a short queue because humans should review only the necessary memory decisions.",
            reason="Daily review workflow decision.",
            source="session_capture",
            source_ref="codex:session:4",
            memory_type="session_lesson",
            category="workflow",
            tags="session-capture,workflow",
        )
    monkeypatch.chdir(project)

    cmd_automation(
        Namespace(
            automation_action="inbox",
            mode=None,
            limit=5,
            include_content=False,
            include_transcripts=False,
            transcript_limit=5,
            json=False,
            pretty=False,
        )
    )

    out = capsys.readouterr().out
    assert "Automation inbox" in out
    assert "pending=1" in out
    assert "Review queue:" in out
    assert "review_for_promotion" in out


def test_automation_doctor_json_safe(tmp_path):
    project = _init_project(tmp_path)

    payload = automation_doctor(project)

    assert payload["action"] == "doctor"
    json.dumps(payload)
    check_names = {item["name"] for item in payload["checks"]}
    assert "vault_db_exists" in check_names
    assert "python_version_supported" in check_names
