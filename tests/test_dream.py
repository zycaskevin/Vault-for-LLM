import json
import subprocess
import sys
from pathlib import Path

from vault.db import VaultDB
from vault.dream import run_dream

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_dream_report_missing_db_does_not_create_database(tmp_path):
    payload = run_dream(tmp_path, mode="report", write_report=False)

    assert payload["mode"] == "report"
    assert payload["summary"] == {
        "stale": 0,
        "duplicates": 0,
        "weak": 0,
        "metadata": 0,
        "orphans": 0,
        "actions_applied": 0,
    }
    assert "warning" in payload
    assert not (tmp_path / "vault.db").exists()


def test_dream_report_only_does_not_mutate_active_db_or_raw(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    raw_before = sorted(p.name for p in raw_dir.glob("*.md"))

    with VaultDB(tmp_path / "vault.db") as db:
        db.add_knowledge(
            title="Weak metadata item",
            content_raw="Dream report-only mode should only inspect this row.",
            source="test",
            category="general",
            tags="",
            trust=0.2,
        )
        db.add_knowledge(title="Duplicate Title", content_raw="A", source="test-a")
        db.add_knowledge(title="Duplicate Title", content_raw="B", source="test-b")
        before_rows = db.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"]

    payload = run_dream(
        tmp_path,
        mode="report",
        checks=["metadata", "dedup", "convergence"],
        limit=50,
        write_report=True,
    )

    assert payload["mode"] == "report"
    assert payload["summary"]["metadata"] >= 1
    assert payload["summary"]["duplicates"] >= 1
    assert payload["summary"]["actions_applied"] == 0
    assert payload["proposed_actions"]
    assert payload["plan_path"].startswith("reports/dream/plans/")
    report = tmp_path / payload["report_path"]
    assert report.exists()
    assert (tmp_path / payload["plan_path"]).exists()
    report_text = report.read_text(encoding="utf-8")
    assert "# Vault Dream Report" in report_text
    assert "Recommended actions" in report_text

    with VaultDB(tmp_path / "vault.db") as db:
        after_rows = db.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"]
    assert after_rows == before_rows
    assert sorted(p.name for p in raw_dir.glob("*.md")) == raw_before


def test_dream_apply_safe_updates_low_risk_metadata_and_backs_up(tmp_path):
    with VaultDB(tmp_path / "vault.db") as db:
        kid = db.add_knowledge(
            title="Apply safe item",
            content_raw="Apply safe currently reports and backs up without deleting.",
            source="test",
            category="general",
            tags="",
            trust=0.3,
        )

    payload = run_dream(
        tmp_path,
        mode="apply_safe",
        checks=["metadata"],
        limit=5,
        write_report=False,
        backup=True,
    )
    assert payload["summary"]["actions_applied"] == 2
    assert payload["backup_path"]
    assert payload["applied_actions"]
    with VaultDB(tmp_path / "vault.db") as db:
        assert db.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"] == 1
        row = db.get_knowledge(kid)
        assert row["tags"] == "needs-review"
        assert row["category"] == "review"


def test_dream_cli_smoke_writes_report(tmp_path):
    with VaultDB(tmp_path / "vault.db") as db:
        db.add_knowledge(
            title="CLI dream",
            content_raw="CLI smoke for dream report.",
            source="test",
            tags="",
            trust=0.5,
        )
    result = subprocess.run(
        [sys.executable, "-m", "vault.cli", "dream", "--mode", "report", "--limit", "5", "--write-report"],
        cwd=tmp_path,
        env={"PYTHONPATH": str(REPO_ROOT)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["summary"]["actions_applied"] == 0
    assert payload["proposed_actions"]
    assert (tmp_path / payload["report_path"]).exists()
