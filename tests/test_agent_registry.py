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
            "--memory-layout",
            "hybrid",
            "--agent-private-dir",
            str(tmp_path / "codex-private"),
            "--json",
        ]
    )
    registered = json.loads(capsys.readouterr().out)
    assert registered["ok"] is True
    assert registered["agent"]["agent_id"] == "codex"
    assert registered["agent"]["project_dir"] == str(project.resolve())
    assert registered["agent"]["memory_layout"] == "hybrid"
    assert registered["agent"]["private_project_dir"] == str((tmp_path / "codex-private").resolve())
    assert registered["agent"]["vault_version"] == __version__

    main(["update-status", "--latest-version", "9.9.9", "--write-status", "--json"])
    status = json.loads(capsys.readouterr().out)
    assert status["installed_version"] == __version__
    assert status["latest_version"] == "9.9.9"
    assert status["update_available"] is True
    assert status["agent_count"] == 1
    assert status["agents"][0]["agent_id"] == "codex"
    assert status["private_projects"] == [str((tmp_path / "codex-private").resolve())]
    assert f"vault automation handoff --project-dir {project.resolve()}" in status["startup_commands"]
    assert status["agent_update_notice_count"] == 1
    notice = status["agent_update_notices"][0]
    assert notice["agent_id"] == "codex"
    assert notice["registered_version"] == __version__
    assert notice["latest_known_version"] == "9.9.9"
    assert notice["behind_latest_known"] is True
    assert notice["needs_attention"] is True
    assert "9.9.9" in notice["recommended_action"]
    assert (tmp_path / "registry" / "update-status.json").exists()


def test_build_update_status_reports_agent_versions_behind_current_runtime(tmp_path, monkeypatch):
    from vault import __version__
    from vault.agent_registry import build_update_status, load_registry, register_agent, save_registry

    monkeypatch.setenv("VAULT_AGENT_REGISTRY_DIR", str(tmp_path / "registry"))
    project = tmp_path / "project"
    project.mkdir()

    register_agent(agent="old-runtime", project_dir=project, scope="shared", features=["core"])
    registry = load_registry()
    registry["agents"]["old-runtime"]["vault_version"] = "0.0.1"
    save_registry(registry)

    status = build_update_status()
    assert status["installed_version"] == __version__
    assert status["latest_version"] == __version__
    assert status["agent_update_notice_count"] == 1
    notice = status["agent_update_notices"][0]
    assert notice["agent_id"] == "old-runtime"
    assert notice["registered_version"] == "0.0.1"
    assert notice["behind_current_runtime"] is True
    assert notice["behind_latest_known"] is True
    assert notice["status"] == "behind_latest"


def test_setup_agent_registers_agent(tmp_path, monkeypatch):
    from vault.agent_registry import list_agents
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    monkeypatch.setenv("VAULT_AGENT_REGISTRY_DIR", str(tmp_path / "registry"))
    project = tmp_path / "agent-project"
    private_project = tmp_path / "agent-private"

    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=project,
            scope="shared",
            agent="openclaw",
            memory_layout="hybrid",
            agent_private_dir=private_project,
            features=["core", "mcp", "memory_agents"],
            template_dir=tmp_path / "templates",
        )
    )

    assert result["agent_registry"]["agent"]["agent_id"] == "openclaw"
    assert result["agent_registry"]["agent"]["project_dir"] == str(project.resolve())
    assert result["agent_registry"]["agent"]["private_project_dir"] == str(private_project.resolve())
    assert result["memory_layout"] == "hybrid"
    assert result["agent_private_dir"] == str(private_project.resolve())
    assert (private_project / "vault.db").exists()
    assert (tmp_path / "templates" / "hybrid-vault-layout.json").exists()
    assert (tmp_path / "templates" / "README-hybrid-vault-layout.md").exists()
    assert any("vault update-status" in step for step in result["next_steps"])

    registry = list_agents()
    assert registry["agent_count"] == 1
    assert registry["agents"][0]["agent_id"] == "openclaw"
    assert registry["agents"][0]["features"] == ["core", "mcp", "memory_agents"]
    assert registry["agents"][0]["memory_layout"] == "hybrid"
