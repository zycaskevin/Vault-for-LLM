from __future__ import annotations

from argparse import Namespace

from vault.db import VaultDB
from vault.docmap import build_document_map_for_entry
from vault.memory import create_candidate
from vault.gui import (
    cmd_gui,
    gui_candidate,
    gui_candidates,
    gui_entry,
    gui_overview,
    gui_read_range,
    gui_review_candidate,
    gui_search,
)


def _make_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    with VaultDB(project / "vault.db") as db:
        kid = db.add_knowledge(
            "GUI Console Runbook",
            "# GUI Console Runbook\n\nSearch should find this memory.\n\n## Evidence\n\nBounded reads should show line ranges.",
            category="runbook",
            tags="gui,console",
            trust=0.9,
            content_aaak="TITLE:GUI Console Runbook\nCLAIMS:\n- [C1] Search should find this memory. (L3)",
        )
        build_document_map_for_entry(db, kid)
    return project, kid


def _make_candidate(project):
    with VaultDB(project / "vault.db") as db:
        result = create_candidate(
            db,
            title="GUI Review Candidate",
            content=(
                "Decision: GUI review actions should require explicit confirmation because "
                "candidate memory changes must stay auditable and reversible."
            ),
            reason="Test candidate review flow.",
            layer="L3",
            category="workflow",
            tags="gui,review",
            trust=0.8,
            source="test",
            source_ref="tests/test_gui.py",
        )
    return result["candidate_id"]


def test_gui_overview_search_entry_and_read(tmp_path):
    project, kid = _make_project(tmp_path)
    candidate_id = _make_candidate(project)

    overview = gui_overview(project)
    assert overview["status"] == "ok"
    assert overview["recent"][0]["title"] == "GUI Console Runbook"
    assert overview["candidates"][0]["id"] == candidate_id

    search = gui_search(project, "console", limit=5)
    assert search["status"] == "ok"
    assert search["results"]
    assert search["results"][0]["id"] == kid

    entry = gui_entry(project, kid)
    assert entry["status"] == "ok"
    assert entry["entry"]["title"] == "GUI Console Runbook"
    assert entry["nodes"]
    assert entry["claims"]
    assert entry["governance"]["scope"] == "project"

    evidence = gui_read_range(project, kid, line_start=1, line_end=3)
    assert evidence["status"] == "ok"
    assert evidence["citation"].endswith("L1-L3")
    assert evidence["lines"][0]["line"] == 1


def test_gui_candidate_review_requires_confirmation(tmp_path):
    project, _kid = _make_project(tmp_path)
    candidate_id = _make_candidate(project)

    payload = gui_review_candidate(project, candidate_id, action="reject", confirm="")

    assert payload["status"] == "error"
    assert payload["error"] == "confirmation_required"
    with VaultDB(project / "vault.db") as db:
        assert db.get_memory_candidate(candidate_id)["status"] == "candidate"


def test_gui_candidate_reject_records_review(tmp_path):
    project, _kid = _make_project(tmp_path)
    candidate_id = _make_candidate(project)

    listed = gui_candidates(project)
    assert listed["status"] == "ok"
    assert listed["candidates"][0]["id"] == candidate_id

    detail = gui_candidate(project, candidate_id)
    assert detail["status"] == "ok"
    assert detail["candidate"]["content"]
    assert detail["confirmation"]["reject"] == f"{candidate_id}:reject"

    payload = gui_review_candidate(
        project,
        candidate_id,
        action="reject",
        reason="Not needed in active memory.",
        confirm=f"{candidate_id}:reject",
    )

    assert payload["status"] == "ok"
    assert payload["result"]["status"] == "rejected"
    with VaultDB(project / "vault.db") as db:
        assert db.get_memory_candidate(candidate_id)["status"] == "rejected"
        events = db.list_memory_feedback(limit=5, outcome="rejected")
    assert events
    assert events[0]["candidate_id"] == candidate_id


def test_gui_candidate_promote_uses_safe_memory_flow(tmp_path):
    project, _kid = _make_project(tmp_path)
    candidate_id = _make_candidate(project)

    payload = gui_review_candidate(
        project,
        candidate_id,
        action="promote",
        confirm=f"{candidate_id}:promote",
    )

    assert payload["status"] == "ok"
    assert payload["result"]["status"] == "promoted"
    assert payload["result"]["knowledge_id"]
    with VaultDB(project / "vault.db") as db:
        candidate = db.get_memory_candidate(candidate_id)
        knowledge = db.get_knowledge(payload["result"]["knowledge_id"])
    assert candidate["status"] == "promoted"
    assert knowledge["title"] == "GUI Review Candidate"


def test_gui_search_rejects_non_positive_limit(tmp_path):
    project, _kid = _make_project(tmp_path)

    assert gui_search(project, "console", limit=0)["results"] == []
    assert gui_search(project, "console", limit=-10)["results"] == []


def test_gui_missing_or_invalid_project(tmp_path):
    missing = tmp_path / "missing"
    missing.mkdir()

    assert gui_overview(missing)["status"] == "blocked"
    assert gui_search(missing, "anything")["status"] == "blocked"
    assert gui_entry(missing, 1)["status"] == "blocked"
    assert gui_read_range(missing, 1)["status"] == "blocked"


def test_cmd_gui_passes_cli_options(monkeypatch, tmp_path):
    calls = {}

    def fake_run_gui(project_dir, *, host, port, open_browser):
        calls.update(
            {
                "project_dir": project_dir,
                "host": host,
                "port": port,
                "open_browser": open_browser,
            }
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("vault.gui.run_gui", fake_run_gui)

    cmd_gui(Namespace(host="127.0.0.1", port=9999, no_open=True))

    assert calls["project_dir"] == tmp_path
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 9999
    assert calls["open_browser"] is False
