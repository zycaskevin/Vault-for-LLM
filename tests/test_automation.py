from __future__ import annotations

from argparse import Namespace
from datetime import datetime, timedelta, timezone
import json

from vault.automation import (
    automation_doctor,
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
    assert any(item["id"] == "ttl_archive_apply" for item in payload["planned_actions"])


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
    assert payload["action_ledger"][0]["status"] == "skipped_usage"
    assert payload["human_review"]["required"] is True
    assert {"kind": "expired_but_used", "count": 1} in payload["human_review"]["items"]
    with VaultDB(project / "vault.db") as db:
        assert db.get_knowledge(expired_id)["status"] == "active"


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
    assert payload["dry_run_diff"]["skipped_policy_count"] == 2
    assert payload["dry_run_diff"]["permission_changes"] is False
    assert {item["status"] for item in payload["action_ledger"]} == {"skipped_policy"}
    assert {"kind": "protected_expired", "count": 2} in payload["human_review"]["items"]
    with VaultDB(project / "vault.db") as db:
        assert db.get_knowledge(private_id)["status"] == "active"
        assert db.get_knowledge(high_id)["status"] == "active"


def test_automation_report_lists_recent_runs(tmp_path):
    project = _init_project(tmp_path)
    automation_run(project, mode="balanced", write_reports=True)

    payload = automation_report(project)

    assert payload["action"] == "report"
    assert payload["report_count"] == 1
    assert payload["reports"][0]["path"].startswith("reports/automation/")


def test_automation_doctor_json_safe(tmp_path):
    project = _init_project(tmp_path)

    payload = automation_doctor(project)

    assert payload["action"] == "doctor"
    json.dumps(payload)
    check_names = {item["name"] for item in payload["checks"]}
    assert "vault_db_exists" in check_names
    assert "python_version_supported" in check_names
