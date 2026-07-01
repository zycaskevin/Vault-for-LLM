import json

from vault.cli import main


def _read_json(capsys):
    return json.loads(capsys.readouterr().out)


def _make_project(tmp_path, capsys):
    project = tmp_path / "project"
    main(["init", str(project)])
    capsys.readouterr()
    main(
        [
            "add",
            "JSON contract lesson",
            "--content",
            "Vault CLI JSON contract smoke should stay parseable for agents.",
            "--project-dir",
            str(project),
            "--category",
            "workflow",
        ]
    )
    capsys.readouterr()
    main(["compile", "--project-dir", str(project), "--no-embed"])
    capsys.readouterr()
    return project


def test_core_agent_commands_accept_json_and_emit_parseable_payloads(tmp_path, capsys):
    project = _make_project(tmp_path, capsys)

    main(["doctor", "--project-dir", str(project), "--json"])
    doctor = _read_json(capsys)
    assert {"ok", "status", "checks", "next_action"} <= set(doctor)

    main(
        [
            "remember",
            "JSON candidate",
            "--content",
            "Remember output should be parseable JSON.",
            "--reason",
            "Regression test for agent JSON contract",
            "--project-dir",
            str(project),
            "--json",
        ]
    )
    remembered = _read_json(capsys)
    assert remembered["ok"] is True
    assert remembered["status"] == "candidate_created"
    assert remembered["candidate_id"]

    main(["candidates", "--project-dir", str(project), "--json"])
    candidates = _read_json(capsys)
    assert candidates["ok"] is True
    assert candidates["count"] >= 1
    assert candidates["candidates"][0]["id"]


def test_map_and_graph_json_contracts_are_parseable(tmp_path, capsys):
    project = _make_project(tmp_path, capsys)

    main(["map", "build", "--project-dir", str(project), "--json"])
    built = _read_json(capsys)
    assert built["ok"] is True
    assert built["action"] == "build"
    assert built["entry_count"] == 1

    main(["map", "show", "1", "--project-dir", str(project), "--json"])
    shown = _read_json(capsys)
    assert shown["ok"] is True
    assert shown["knowledge_id"] == 1
    assert isinstance(shown["nodes"], list)

    main(["map", "read", "1", "--lines", "1-5", "--project-dir", str(project), "--json"])
    read = _read_json(capsys)
    assert read["ok"] is True
    assert read["line_start"] >= 1
    assert read["lines"]

    main(["map", "query", "contract", "--project-dir", str(project), "--json"])
    queried = _read_json(capsys)
    assert queried["ok"] is True
    assert queried["action"] == "query"
    assert "results" in queried

    main(["graph", "build", "--project-dir", str(project), "--json"])
    graph_built = _read_json(capsys)
    assert graph_built["ok"] is True
    assert graph_built["action"] == "build"

    main(["graph", "show", "--project-dir", str(project), "--json"])
    graph = _read_json(capsys)
    assert graph["ok"] is True
    assert graph["stats"]["edges_total"] >= 0
    assert isinstance(graph["edges"], list)


def test_gateway_and_obsidian_export_json_contracts_are_parseable(tmp_path, capsys):
    project = _make_project(tmp_path, capsys)

    main(["gateway", "health", "--project-dir", str(project), "--json"])
    gateway = _read_json(capsys)
    assert gateway["ok"] is True
    assert gateway["status"] == "ok"
    assert gateway["gateway"]["candidate_first_writes"] is True

    obsidian = tmp_path / "ObsidianVault"
    main(
        [
            "export",
            "obsidian",
            "--vault",
            str(obsidian),
            "--project-dir",
            str(project),
            "--dry-run",
            "--json",
        ]
    )
    exported = _read_json(capsys)
    assert exported["ok"] is True
    assert exported["status"] == "ok"
    assert exported["dry_run"] is True
    assert exported["matched"] == 1
    assert "paths" in exported


def test_setup_agent_json_has_stable_top_level_status(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("VAULT_AGENT_REGISTRY_DIR", str(tmp_path / "registry"))
    monkeypatch.setenv("VAULT_AGENT_PRIVATE_ROOT", str(tmp_path / "private-root"))

    main(
        [
            "setup-agent",
            "--non-interactive",
            "--agent",
            "codex",
            "--scope",
            "shared",
            "--agent-project-dir",
            str(tmp_path / "agent-project"),
            "--features",
            "core,mcp",
            "--json",
        ]
    )
    payload = _read_json(capsys)
    assert payload["ok"] is True
    assert payload["status"] == "ok"
    assert payload["version"]
    assert payload["agent_registry"]["ok"] is True
