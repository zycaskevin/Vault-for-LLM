import json


def test_agent_register_and_update_status_cli(tmp_path, monkeypatch, capsys):
    from vault import __version__
    from vault.cli import main

    monkeypatch.setenv("VAULT_AGENT_REGISTRY_DIR", str(tmp_path / "registry"))
    project = tmp_path / "project"
    project.mkdir()

    main(
        [
            "agent",
            "register",
            "--agent",
            "codex",
            "--project",
            str(project),
            "--scope",
            "shared",
            "--features",
            "core,mcp",
            "--json",
        ]
    )
    registered = json.loads(capsys.readouterr().out)
    assert registered["ok"] is True
    assert registered["agent"]["agent_id"] == "codex"
    assert registered["agent"]["project_dir"] == str(project.resolve())
    assert registered["agent"]["vault_version"] == __version__

    main(["update-status", "--latest-version", "9.9.9", "--write-status", "--json"])
    status = json.loads(capsys.readouterr().out)
    assert status["installed_version"] == __version__
    assert status["latest_version"] == "9.9.9"
    assert status["update_available"] is True
    assert status["agent_count"] == 1
    assert status["agents"][0]["agent_id"] == "codex"
    assert f"vault automation handoff --project-dir {project.resolve()}" in status["startup_commands"]
    assert (tmp_path / "registry" / "update-status.json").exists()


def test_setup_agent_registers_agent(tmp_path, monkeypatch):
    from vault.agent_registry import list_agents
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    monkeypatch.setenv("VAULT_AGENT_REGISTRY_DIR", str(tmp_path / "registry"))
    project = tmp_path / "agent-project"

    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=project,
            scope="shared",
            agent="openclaw",
            features=["core", "mcp", "memory_agents"],
            template_dir=tmp_path / "templates",
        )
    )

    assert result["agent_registry"]["agent"]["agent_id"] == "openclaw"
    assert result["agent_registry"]["agent"]["project_dir"] == str(project.resolve())
    assert any("vault update-status" in step for step in result["next_steps"])

    registry = list_agents()
    assert registry["agent_count"] == 1
    assert registry["agents"][0]["agent_id"] == "openclaw"
    assert registry["agents"][0]["features"] == ["core", "mcp", "memory_agents"]
