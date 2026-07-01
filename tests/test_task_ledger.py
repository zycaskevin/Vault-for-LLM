import json
import subprocess
import sys
from pathlib import Path

from vault.db import VaultDB
from vault.task_ledger import (
    claim_task_handoff,
    complete_task,
    create_task_handoff,
    list_task_handoffs,
    list_tasks,
    start_task,
    task_handoff,
    update_task,
)


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
            priority="P1",
            due_at="2026-06-30",
            scope="shared",
            owner_agent="codex",
            allowed_agents="codex,work-agent",
        )
        task = started["task"]
        assert task["id"] == "task-test"
        assert task["current_plan"] == ["define schema"]
        assert task["next_actions"] == ["write tests"]
        assert task["priority"] == "P1"
        assert task["due_at"] == "2026-06-30"
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
            priority="P0",
            due_at="2026-06-29",
        )
        task = updated["task"]
        assert task["completed"] == ["schema added"]
        assert task["hard_decisions"] == ["do not create L4"]
        assert task["priority"] == "P0"
        assert task["due_at"] == "2026-06-29"
        assert len(task["evidence_refs"]) == 2

        handoff = task_handoff(db, "task-test")
        assert "Task Handoff: Task Ledger Test" in handoff["markdown"]
        assert "- priority: P0" in handoff["markdown"]
        assert "- due_at: 2026-06-29" in handoff["markdown"]
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


def test_task_ledger_lists_by_priority_then_due_date(tmp_path):
    db_path = tmp_path / "vault.db"
    with VaultDB(db_path) as db:
        start_task(db, "Normal task", task_id="task-normal", priority="P2", due_at="2026-07-01")
        start_task(db, "Critical later", task_id="task-critical", priority="P0", due_at="2026-07-10")
        start_task(db, "Important soon", task_id="task-important", priority="P1", due_at="2026-06-30")

        rows = list_tasks(db, status="active", limit=10)

    assert [row["id"] for row in rows] == ["task-critical", "task-important", "task-normal"]


def test_task_handoff_inbox_lifecycle(tmp_path):
    db_path = tmp_path / "vault.db"
    with VaultDB(db_path) as db:
        start_task(
            db,
            "Continue multi-agent handoff work",
            task_id="task-handoff",
            title="Agent handoff",
            next_actions=["receiver claims handoff"],
            scope="shared",
            owner_agent="codex",
            allowed_agents="codex,hermes",
        )
        sent = create_task_handoff(
            db,
            "task-handoff",
            handoff_id="handoff-test",
            from_agent="codex",
            to_agent="hermes",
            message="Please continue from the Task Ledger snapshot.",
            source_ref="session:test",
        )
        handoff = sent["handoff"]
        assert handoff["id"] == "handoff-test"
        assert handoff["status"] == "pending"
        assert handoff["to_agent"] == "hermes"
        assert "Task Snapshot" in handoff["markdown"]

        inbox = list_task_handoffs(db, agent_id="hermes")
        assert [item["id"] for item in inbox] == ["handoff-test"]

        claimed = claim_task_handoff(db, "handoff-test", agent_id="hermes", note="Taking over.")
        assert claimed["handoff"]["status"] == "claimed"
        assert claimed["handoff"]["claimed_by"] == "hermes"

        claimed_inbox = list_task_handoffs(db, agent_id="hermes", status="claimed")
        assert [item["id"] for item in claimed_inbox] == ["handoff-test"]


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
            "--priority",
            "P1",
            "--due-at",
            "2026-06-30",
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
    assert payload["task"]["priority"] == "P1"
    assert payload["task"]["due_at"] == "2026-06-30"

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
            "--priority",
            "P0",
            "--due-at",
            "2026-06-29",
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
    assert "- priority: P0" in handoff.stdout
    assert "Use handoff before switching agents." in handoff.stdout

    sent = subprocess.run(
        [
            sys.executable,
            "-m",
            "vault.cli",
            "--project-dir",
            str(project),
            "task",
            "send-handoff",
            "task-cli",
            "--handoff-id",
            "handoff-cli",
            "--from-agent",
            "codex",
            "--to-agent",
            "hermes",
            "--message",
            "Please continue the CLI slice.",
            "--json",
        ],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(sent.stdout)["handoff"]["id"] == "handoff-cli"

    inbox = subprocess.run(
        [
            sys.executable,
            "-m",
            "vault.cli",
            "--project-dir",
            str(project),
            "task",
            "inbox",
            "--agent-id",
            "hermes",
            "--json",
        ],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(inbox.stdout)["handoffs"][0]["id"] == "handoff-cli"

    claimed = subprocess.run(
        [
            sys.executable,
            "-m",
            "vault.cli",
            "--project-dir",
            str(project),
            "task",
            "claim-handoff",
            "handoff-cli",
            "--agent-id",
            "hermes",
            "--json",
        ],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(claimed.stdout)["handoff"]["status"] == "claimed"

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
