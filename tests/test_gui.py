from __future__ import annotations

from argparse import Namespace
import http.client
from http.server import ThreadingHTTPServer
import threading

from vault.db import VaultDB
from vault.docmap import build_document_map_for_entry
from vault.gui_app import APP_HTML
from vault.memory import create_candidate
from vault.agent_registry import register_agent
from vault.gui import (
    cmd_gui,
    gui_agent_dashboard,
    gui_candidate,
    gui_candidates,
    gui_claim_task_handoff,
    gui_daily_report,
    gui_documents,
    gui_entry,
    gui_overview,
    gui_read_range,
    gui_review_candidate,
    gui_resolve_sync_conflict,
    gui_search,
    gui_sync_conflict,
    gui_sync_status,
    gui_task,
    gui_tasks,
    make_gui_handler,
)
from vault.task_ledger import create_task_handoff, start_task, update_task
from vault.multi_host import detect_candidate_conflicts, record_memory_revision


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
        create_task_handoff(
            db,
            "task-gui",
            handoff_id="handoff-gui",
            from_agent="codex",
            to_agent="hermes",
            message="Please review the GUI Task Ledger panel.",
            source_ref="tests/test_gui.py",
        )
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

    overview = gui_overview(project, language="zh-CN")
    assert overview["status"] == "ok"
    assert overview["recent"][0]["title"] == "GUI Console Runbook"
    assert overview["candidates"][0]["id"] == candidate_id
    assert "content" not in overview["candidates"][0]
    assert "content_preview" not in overview["candidates"][0]
    assert overview["tasks"][0]["id"] == "task-gui"
    assert overview["daily_report"]["action"] == "daily-report"
    assert overview["daily_report"]["language"] == "zh-CN"
    assert overview["daily_report"]["review_cards"]
    assert overview["agent_dashboard"]["status"] == "ok"
    inbox = overview["review_inbox"]
    assert inbox["safety"]["content_hidden_by_default"] is True
    assert {"candidate", "task_handoff"} <= {item["kind"] for item in inbox["items"]}
    assert "Task Snapshot" not in str(inbox)

    daily = gui_daily_report(project)
    assert daily["status"] == "completed"
    assert daily["summary"]["needs_confirmation"] >= 1

    tasks = gui_tasks(project)
    assert tasks["status"] == "ok"
    assert tasks["tasks"][0]["title"] == "GUI Task Panel"

    task = gui_task(project, "task-gui")
    assert task["status"] == "ok"
    assert "Task Handoff: GUI Task Panel" in task["markdown"]
    assert task["task"]["hard_decisions"] == ["read-only GUI first"]
    assert task["pending_handoffs"][0]["id"] == "handoff-gui"
    assert "Task Snapshot" not in str(task["pending_handoffs"])

    blocked_claim = gui_claim_task_handoff(project, "handoff-gui", confirm="")
    assert blocked_claim["error"] == "confirmation_required"

    claimed = gui_claim_task_handoff(project, "handoff-gui", confirm="handoff-gui:claim")
    assert claimed["status"] == "ok"
    assert claimed["handoff"]["status"] == "claimed"

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
    assert "Vault Memory Control Center" in APP_HTML
    assert "Memory Control Center" in APP_HTML
    assert "read-only report" in APP_HTML
    assert "No silent promote/archive/delete" in APP_HTML
    assert "__VAULT_DEFAULT_LANGUAGE__" in APP_HTML
    assert "Sections" in APP_HTML
    assert "Claims" in APP_HTML
    assert "data-read-node" in APP_HTML
    assert "Active Tasks" in APP_HTML
    assert "taskList" in APP_HTML
    assert "Daily Report" in APP_HTML
    assert "dailyReport" in APP_HTML
    assert "agentDashboard" in APP_HTML
    assert "syncHealth" in APP_HTML
    assert "openConflicts" in APP_HTML
    assert "sync-conflict" in APP_HTML
    assert "dashboard-subhead" in APP_HTML
    assert "review_inbox" in APP_HTML
    assert "task_handoff" in APP_HTML
    assert "data-claim-handoff" in APP_HTML
    assert "Claim handoff" in APP_HTML
    assert "Multi-Agent Dashboard" in APP_HTML
    assert "多 Agent Dashboard" in APP_HTML
    assert "languageSelect" in APP_HTML
    assert "zh-Hant" in APP_HTML
    assert "zh-CN" in APP_HTML
    assert "English" in APP_HTML
    assert "reviewPrompt" in APP_HTML
    assert "viewBeforeDecision" in APP_HTML
    assert "candidateDecisionQuestion" in APP_HTML
    assert "keepMemory" in APP_HTML
    assert "rejectMemory" in APP_HTML
    assert "conflictReview" in APP_HTML
    assert "keepLocalConflict" in APP_HTML
    assert "acceptRemoteConflict" in APP_HTML
    assert "manualConflict" in APP_HTML
    assert "是否收進正式記憶" in APP_HTML
    assert "選項會在詳情頁分開操作" not in APP_HTML


def test_gui_agent_dashboard_lists_agents_sync_and_review(tmp_path, monkeypatch):
    project, _kid = _make_project(tmp_path)
    candidate_id = _make_candidate(project)
    monkeypatch.setenv("VAULT_AGENT_REGISTRY_DIR", str(tmp_path / "registry"))
    register_agent(
        agent="codex",
        project_dir=project,
        features=["mcp", "obsidian"],
        tool_profile="core",
        source="test",
    )
    manifest_dir = project / ".vault"
    manifest_dir.mkdir()
    (manifest_dir / "obsidian-import-manifest.json").write_text(
        '{"version":1,"updated_at":"2026-07-01T00:00:00+00:00","raw_subdir":"obsidian","notes":{"A.md":{"status":"active"},"B.md":{"status":"missing"}}}',
        encoding="utf-8",
    )

    dashboard = gui_agent_dashboard(project, limit=5)

    assert dashboard["status"] == "ok"
    assert dashboard["agents"]["connected_count"] == 1
    assert dashboard["agents"]["items"][0]["agent_id"] == "codex"
    assert dashboard["recent_candidates"][0]["id"] == candidate_id
    obsidian = next(item for item in dashboard["recent_sync"] if item["kind"] == "obsidian")
    assert obsidian["summary"]["active_notes"] == 1
    assert obsidian["summary"]["missing_notes"] == 1
    assert dashboard["sync_health"]["status"] == "idle"
    assert dashboard["sync_health"]["safety"]["read_only"] is True
    assert dashboard["human_review"]["items"]


def test_gui_sync_status_shows_open_conflicts_without_content(tmp_path):
    project, _kid = _make_project(tmp_path)
    with VaultDB(project / "vault.db") as db:
        result = create_candidate(
            db,
            title="GUI Console Runbook",
            content="Remote content differs from the reviewed local runbook.",
            reason="remote sync conflict",
            source="remote_write_request",
            source_ref="remote_write_request:req-gui",
            trust=0.8,
            scope="shared",
            sensitivity="low",
            memory_type="remote_candidate",
        )
        revision = record_memory_revision(
            db,
            title="GUI Console Runbook",
            content="Remote content differs from the reviewed local runbook.",
            operation="remote_candidate_imported",
            status="candidate",
            candidate_id=result["candidate_id"],
            remote_request_id="req-gui",
            source_agent="remote-agent",
        )
        detect_candidate_conflicts(
            db,
            candidate_id=result["candidate_id"],
            revision_id=revision["revision_id"],
        )

    payload = gui_sync_status(project)
    dashboard = gui_agent_dashboard(project, limit=5)

    assert payload["status"] == "needs_review"
    assert payload["counts"]["open_conflicts"] == 1
    assert payload["open_conflicts"][0]["conflict_type"] == "same_title_content_mismatch"
    assert "Remote content differs" not in str(payload)
    assert dashboard["sync_health"]["counts"]["open_conflicts"] == 1
    review_inbox = dashboard["human_review"]["unified_inbox"]
    assert any(item["kind"] == "sync_conflict" for item in review_inbox["items"])
    assert "Remote content differs" not in str(review_inbox)


def test_gui_sync_conflict_detail_and_resolution(tmp_path):
    project, knowledge_id = _make_project(tmp_path)
    with VaultDB(project / "vault.db") as db:
        result = create_candidate(
            db,
            title="GUI Console Runbook",
            content="Remote content differs from the reviewed local runbook.",
            reason="remote sync conflict",
            source="remote_write_request",
            source_ref="remote_write_request:req-gui-resolve",
            trust=0.8,
            scope="shared",
            sensitivity="low",
            memory_type="remote_candidate",
        )
        revision = record_memory_revision(
            db,
            title="GUI Console Runbook",
            content="Remote content differs from the reviewed local runbook.",
            operation="remote_candidate_imported",
            status="candidate",
            candidate_id=result["candidate_id"],
            remote_request_id="req-gui-resolve",
            source_agent="remote-agent",
        )
        conflict = detect_candidate_conflicts(db, candidate_id=result["candidate_id"], revision_id=revision["revision_id"])[0]

    detail = gui_sync_conflict(project, conflict["id"])

    assert detail["status"] == "ok"
    assert detail["conflict"]["candidate"]["content"].startswith("Remote content differs")
    assert detail["conflict"]["knowledge"]["content"].startswith("# GUI Console Runbook")
    assert detail["conflict"]["confirmation"]["accept_remote"] == f"{conflict['id']}:accept_remote"

    blocked = gui_resolve_sync_conflict(project, conflict["id"], resolution="accept_remote", confirm="")
    assert blocked["error"] == "confirmation_required"

    resolved = gui_resolve_sync_conflict(
        project,
        conflict["id"],
        resolution="accept_remote",
        reason="GUI accepted remote candidate.",
        confirm=f"{conflict['id']}:accept_remote",
    )
    assert resolved["status"] == "ok"
    with VaultDB(project / "vault.db") as db:
        assert db.get_knowledge(knowledge_id)["status"] == "archived"
        promoted_id = db.get_memory_candidate(result["candidate_id"])["promoted_knowledge_id"]
        assert db.get_knowledge(promoted_id)["status"] == "active"


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
    assert "expected_confirmation" not in payload
    with VaultDB(project / "vault.db") as db:
        assert db.get_memory_candidate(candidate_id)["status"] == "candidate"


def test_gui_candidate_reject_records_review(tmp_path):
    project, _kid = _make_project(tmp_path)
    candidate_id = _make_candidate(project)

    listed = gui_candidates(project)
    assert listed["status"] == "ok"
    assert listed["candidates"][0]["id"] == candidate_id
    assert "content" not in listed["candidates"][0]
    assert "content_preview" not in listed["candidates"][0]

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

    def fake_run_gui(project_dir, *, host, port, open_browser, auth_token=None, no_auth=False, language="zh-Hant"):
        calls.update(
            {
                "project_dir": project_dir,
                "host": host,
                "port": port,
                "open_browser": open_browser,
                "auth_token": auth_token,
                "no_auth": no_auth,
                "language": language,
            }
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("vault.gui.run_gui", fake_run_gui)

    cmd_gui(Namespace(host="127.0.0.1", port=9999, no_open=True, auth_token="test-token", no_auth=False, language="zh-CN"))

    assert calls["project_dir"] == tmp_path
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 9999
    assert calls["open_browser"] is False
    assert calls["auth_token"] == "test-token"
    assert calls["no_auth"] is False
    assert calls["language"] == "zh-CN"


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

        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/?token=secret-token")
        page = conn.getresponse()
        assert page.status == 200
        assert "HttpOnly" in (page.getheader("Set-Cookie") or "")
        assert b"__VAULT_DEFAULT_LANGUAGE__" not in page.read()
        conn.close()
    finally:
        server.shutdown()
        server.server_close()
