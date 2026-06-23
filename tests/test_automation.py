from __future__ import annotations

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
    assert payload["report_path"].startswith("reports/automation/")
    assert payload["dream"]["report_path"].startswith("reports/dream/")
    with VaultDB(project / "vault.db") as db:
        assert db.get_knowledge(expired_id)["status"] == "archived"
        assert db.get_knowledge(future_id)["status"] == "active"


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
