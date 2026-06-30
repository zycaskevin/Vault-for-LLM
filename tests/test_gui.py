from __future__ import annotations

from argparse import Namespace
import http.client
from http.server import ThreadingHTTPServer
import threading

from vault.db import VaultDB
from vault.docmap import build_document_map_for_entry
from vault.gui_app import APP_HTML
from vault.memory import create_candidate
from vault.gui import (
    cmd_gui,
    gui_candidate,
    gui_candidates,
    gui_documents,
    gui_entry,
    gui_overview,
    gui_read_range,
    gui_review_candidate,
    gui_search,
    gui_task,
    gui_tasks,
    make_gui_handler,
)
from vault.task_ledger import start_task, update_task


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
        private_id = db.add_knowledge(
            "Private GUI Note",
            "# Private GUI Note\n\nThis should be filterable by sensitivity.",
            layer="L1",
            category="private-note",
            tags="gui,private",
            trust=0.7,
            scope="private",
            sensitivity="high",
            owner_agent="gui-agent",
        )
        build_document_map_for_entry(db, private_id)
        linked_id = db.add_knowledge(
            "GUI Linked Decision",
            "# GUI Linked Decision\n\nGraph panel should show linked memories.",
            category="decision",
            tags="gui,graph",
            trust=0.8,
        )
        db.add_edge(kid, linked_id, relation="supports", weight=0.8, auto_inferred=False)
        start_task(
            db,
            "Finish GUI Task Ledger panel",
            task_id="task-gui",
            title="GUI Task Panel",
            current_plan=["add active task list"],
            next_actions=["wire task detail panel"],
            evidence_refs=["file:docs/gui_console.md"],
            continuation_note="Show task state separately from L0-L3 memory.",
            owner_agent="gui-agent",
        )
        update_task(db, "task-gui", completed=["task API ready"], hard_decisions=["read-only GUI first"])
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
    assert overview["tasks"][0]["id"] == "task-gui"

    tasks = gui_tasks(project)
    assert tasks["status"] == "ok"
    assert tasks["tasks"][0]["title"] == "GUI Task Panel"

    task = gui_task(project, "task-gui")
    assert task["status"] == "ok"
    assert "Task Handoff: GUI Task Panel" in task["markdown"]
    assert task["task"]["hard_decisions"] == ["read-only GUI first"]

    search = gui_search(project, "console", limit=5)
    assert search["status"] == "ok"
    assert search["results"]
    assert search["results"][0]["id"] == kid

    entry = gui_entry(project, kid)
    assert entry["status"] == "ok"
    assert entry["entry"]["title"] == "GUI Console Runbook"
    assert entry["nodes"]
    assert entry["claims"]
    assert entry["graph"]["edge_count"] == 1
    assert entry["graph"]["edges"][0]["other_title"] == "GUI Linked Decision"
    assert entry["governance"]["scope"] == "project"

    evidence = gui_read_range(project, kid, line_start=1, line_end=3)
    assert evidence["status"] == "ok"
    assert evidence["citation"].endswith("L1-L3")
    assert evidence["lines"][0]["line"] == 1


def test_gui_app_exposes_document_map_panel():
    assert 'data-tab="map"' in APP_HTML
    assert "Sections" in APP_HTML
    assert "Claims" in APP_HTML
    assert "data-read-node" in APP_HTML
    assert "Active Tasks" in APP_HTML
    assert "taskList" in APP_HTML


def test_gui_app_exposes_graph_visual_panel():
    assert "graph-canvas" in APP_HTML
    assert "graph-node linked" in APP_HTML
    assert "data-open-node" in APP_HTML


def test_gui_documents_filters_and_facets(tmp_path):
    project, kid = _make_project(tmp_path)

    documents = gui_documents(project, limit=10)
    assert documents["status"] == "ok"
    document_titles = {row["title"] for row in documents["documents"]}
    assert {"GUI Console Runbook", "Private GUI Note", "GUI Linked Decision"} <= document_titles
    assert any(item["value"] == "L3" for item in documents["facets"]["layers"])
    assert any(item["value"] == "runbook" for item in documents["facets"]["categories"])

    by_layer = gui_documents(project, layer="L3", limit=10)
    assert "GUI Console Runbook" in {row["title"] for row in by_layer["documents"]}

    by_category = gui_documents(project, category="private-note", sensitivity="high", limit=10)
    assert [row["title"] for row in by_category["documents"]] == ["Private GUI Note"]

    by_query = gui_documents(project, query="private", limit=10)
    assert [row["title"] for row in by_query["documents"]] == ["Private GUI Note"]


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
    assert gui_documents(project, limit=0)["documents"] == []
    assert gui_documents(project, limit=-10)["documents"] == []


def test_gui_missing_or_invalid_project(tmp_path):
    missing = tmp_path / "missing"
    missing.mkdir()

    assert gui_overview(missing)["status"] == "blocked"
    assert gui_search(missing, "anything")["status"] == "blocked"
    assert gui_entry(missing, 1)["status"] == "blocked"
    assert gui_read_range(missing, 1)["status"] == "blocked"


def test_cmd_gui_passes_cli_options(monkeypatch, tmp_path):
    calls = {}

    def fake_run_gui(project_dir, *, host, port, open_browser, auth_token=None, no_auth=False):
        calls.update(
            {
                "project_dir": project_dir,
                "host": host,
                "port": port,
                "open_browser": open_browser,
                "auth_token": auth_token,
                "no_auth": no_auth,
            }
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("vault.gui.run_gui", fake_run_gui)

    cmd_gui(Namespace(host="127.0.0.1", port=9999, no_open=True, auth_token="test-token", no_auth=False))

    assert calls["project_dir"] == tmp_path
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 9999
    assert calls["open_browser"] is False
    assert calls["auth_token"] == "test-token"
    assert calls["no_auth"] is False


def test_gui_handler_requires_token_for_api(tmp_path):
    project, _kid = _make_project(tmp_path)
    handler = make_gui_handler(project, auth_token="secret-token")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/api/overview")
        denied = conn.getresponse()
        assert denied.status == 401
        denied.read()
        conn.close()

        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/api/overview?token=secret-token")
        allowed = conn.getresponse()
        assert allowed.status == 200
        assert b'"status": "ok"' in allowed.read()
        conn.close()
    finally:
        server.shutdown()
        server.server_close()
