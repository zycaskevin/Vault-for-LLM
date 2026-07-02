import json
from pathlib import Path

from vault.cli import main
from vault.demo_agent_governance import run_agent_governance_demo


def _read_json(capsys):
    return json.loads(capsys.readouterr().out)


def test_agent_governance_demo_runs_full_lifecycle(tmp_path):
    project = tmp_path / "demo-project"

    payload = run_agent_governance_demo(project_dir=project)

    assert payload["ok"] is True
    assert payload["scenario"] == "agent_memory_governance"
    assert payload["lifecycle"] == [
        "propose",
        "review",
        "promote",
        "search",
        "bounded_read",
        "rollback_available",
        "audit",
    ]
    assert payload["candidate_id"].startswith("mem_")
    assert payload["promoted_knowledge_id"] > 0
    assert payload["search_hit"]["id"] == payload["promoted_knowledge_id"]
    assert f"#{payload['promoted_knowledge_id']}" in payload["read_range_citation"]
    assert payload["rollback_available"] is True
    assert payload["rollback"]["verified"] is True
    assert any(event["outcome"] == "promoted" for event in payload["audit_events"])

    report = Path(payload["artifacts"]["report_md"])
    assert report.exists()
    assert "memory governance" in report.read_text(encoding="utf-8").lower()
    assert Path(payload["artifacts"]["codex_startup"]).exists()
    assert Path(payload["artifacts"]["claude_code_startup"]).exists()
    assert Path(payload["artifacts"]["hermes_startup"]).exists()


def test_agent_governance_demo_cli_json_with_explicit_project_dir(tmp_path, capsys):
    project = tmp_path / "explicit-demo"

    main(["demo", "agent-governance", "--project-dir", str(project), "--json"])
    payload = _read_json(capsys)

    assert payload["ok"] is True
    assert payload["project_dir"] == str(project.resolve())
    assert payload["temporary_project"] is False
    assert Path(payload["artifacts"]["report_json"]).exists()
    assert Path(payload["artifacts"]["snippet_dir"]).is_dir()


def test_agent_governance_demo_cli_without_project_dir_uses_temp_project(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    main(["demo", "agent-governance", "--json"])
    payload = _read_json(capsys)

    assert payload["ok"] is True
    assert payload["temporary_project"] is True
    assert payload["project_dir"] != str(tmp_path)
    assert not (tmp_path / "vault.db").exists()
    assert Path(payload["artifacts"]["report_md"]).exists()
