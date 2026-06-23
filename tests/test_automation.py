from __future__ import annotations

from argparse import Namespace
from datetime import datetime, timedelta, timezone
import json

from vault.automation import (
    automation_doctor,
    automation_eval,
    automation_plan,
    automation_report,
    automation_run,
    load_policy,
)
from vault.db import VaultDB


def _init_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "raw").mkdir()
    with VaultDB(project / "vault.db") as db:
        db.set_config("embedding_provider", "hash")
    return project


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
                "category": "memory-curation",
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
                "category": "memory-curation",
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


def test_automation_doctor_json_safe(tmp_path):
    project = _init_project(tmp_path)

    payload = automation_doctor(project)

    assert payload["action"] == "doctor"
    json.dumps(payload)
    check_names = {item["name"] for item in payload["checks"]}
    assert "vault_db_exists" in check_names
    assert "python_version_supported" in check_names
