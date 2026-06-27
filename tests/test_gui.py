from __future__ import annotations

from argparse import Namespace

from vault.db import VaultDB
from vault.docmap import build_document_map_for_entry
from vault.gui import cmd_gui, gui_entry, gui_overview, gui_read_range, gui_search


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


def test_gui_overview_search_entry_and_read(tmp_path):
    project, kid = _make_project(tmp_path)

    overview = gui_overview(project)
    assert overview["status"] == "ok"
    assert overview["recent"][0]["title"] == "GUI Console Runbook"

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
