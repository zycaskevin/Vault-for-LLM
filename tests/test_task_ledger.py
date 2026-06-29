import json
import subprocess
import sys
from pathlib import Path

from vault.db import VaultDB
from vault.task_ledger import complete_task, start_task, task_handoff, update_task


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_task_ledger_lifecycle_does_not_write_active_knowledge(tmp_path):
    db_path = tmp_path / "vault.db"
    with VaultDB(db_path) as db:
        started = start_task(
            db,
            "Implement task ledger",
            task_id="task-test",
            title="Task Ledger Test",
            current_plan=["define schema"],
            next_actions=["write tests"],
            evidence_refs=["file:docs/memory_governance.md"],
            continuation_note="Resume from the schema boundary.",
            scope="shared",
            owner_agent="codex",
            allowed_agents="codex,work-agent",
        )
        task = started["task"]
        assert task["id"] == "task-test"
        assert task["current_plan"] == ["define schema"]
        assert task["next_actions"] == ["write tests"]
        assert task["scope"] == "shared"
        assert json.loads(task["allowed_agents"]) == ["codex", "work-agent"]

        updated = update_task(
            db,
            "task-test",
            completed=["schema added"],
            hard_decisions=["do not create L4"],
            blockers=["MCP comes later"],
            open_questions=["file-backed or db-backed?"],
            next_actions=["add CLI"],
            evidence_refs=["pr:229"],
            continuation_note="Continue with CLI wiring.",
        )
        task = updated["task"]
        assert task["completed"] == ["schema added"]
        assert task["hard_decisions"] == ["do not create L4"]
        assert len(task["evidence_refs"]) == 2

        handoff = task_handoff(db, "task-test")
        assert "Task Handoff: Task Ledger Test" in handoff["markdown"]
        assert "do not create L4" in handoff["markdown"]
        assert "Continue with CLI wiring." in handoff["markdown"]

        completed = complete_task(db, "task-test", summary="CLI ready")
        assert completed["task"]["status"] == "completed"
        assert completed["task"]["completed_at"]

        knowledge_count = db.conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
        assert knowledge_count == 0


def test_task_ledger_title_defaults_to_task_id(tmp_path):
    db_path = tmp_path / "vault.db"
    with VaultDB(db_path) as db:
        started = start_task(db, "Resume release work", task_id="task-release")
        assert started["task"]["title"] == "task-release"


def test_task_cli_start_update_handoff_complete(tmp_path):
    project = tmp_path / "project"
    project.mkdir()

    start = subprocess.run(
        [
            sys.executable,
            "-m",
            "vault.cli",
            "--project-dir",
            str(project),
            "task",
            "start",
            "Ship task ledger",
            "--task-id",
            "task-cli",
            "--plan",
            "write code",
            "--next-action",
            "run tests",
            "--json",
        ],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(start.stdout)
    assert payload["task"]["id"] == "task-cli"
    assert payload["task"]["goal"] == "Ship task ledger"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "vault.cli",
            "--project-dir",
            str(project),
            "task",
            "update",
            "task-cli",
            "--decision",
            "Task Ledger is not L2",
            "--done",
            "CLI wired",
            "--continuation-note",
            "Use handoff before switching agents.",
            "--json",
        ],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=True,
    )

    handoff = subprocess.run(
        [
            sys.executable,
            "-m",
            "vault.cli",
            "--project-dir",
            str(project),
            "task",
            "handoff",
            "task-cli",
        ],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=True,
    )
    assert "Task Ledger is not L2" in handoff.stdout
    assert "Use handoff before switching agents." in handoff.stdout

    complete = subprocess.run(
        [
            sys.executable,
            "-m",
            "vault.cli",
            "--project-dir",
            str(project),
            "task",
            "complete",
            "task-cli",
            "--summary",
            "Task ledger slice complete",
            "--json",
        ],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(complete.stdout)["task"]["status"] == "completed"
