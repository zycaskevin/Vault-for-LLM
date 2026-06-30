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
            "--skills",
            "review-helper@1.0.0,task-helper",
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
    assert registered["agent"]["skills"] == ["review-helper@1.0.0", "task-helper"]
    assert registered["agent"]["private_project_dir"] == str((tmp_path / "codex-private").resolve())
    assert registered["agent"]["vault_version"] == __version__

    main(["update-status", "--latest-version", "9.9.9", "--write-status", "--json"])
    status = json.loads(capsys.readouterr().out)
    assert status["installed_version"] == __version__
    assert status["latest_version"] == "9.9.9"
    assert status["update_available"] is True
    assert status["agent_count"] == 1
    assert status["agents"][0]["agent_id"] == "codex"
    assert status["agents"][0]["skills"] == ["review-helper@1.0.0", "task-helper"]
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

    main(["update-status", "--latest-version", "9.9.9", "--write-status", "--agent", "codex", "--json"])
    focused_write = json.loads(capsys.readouterr().out)
    stored_status = json.loads((tmp_path / "registry" / "update-status.json").read_text(encoding="utf-8"))
    assert focused_write["startup_agent_id"] == "codex"
    assert "startup_agent_id" not in stored_status

    main(["update-status", "--read-status", "--agent", "codex", "--json"])
    read_status = json.loads(capsys.readouterr().out)
    assert read_status["ok"] is True
    assert read_status["action"] == "read_status"
    assert read_status["status_path"] == str(tmp_path / "registry" / "update-status.json")
    assert read_status["agent_update_notice_count"] == 1
    assert read_status["agent_update_notices"][0]["latest_known_version"] == "9.9.9"
    assert read_status["startup_agent_id"] == "codex"
    assert read_status["startup_agent_registered"] is True
    assert read_status["current_agent_needs_attention"] is True
    assert "9.9.9" in read_status["current_agent_recommended_action"]
    assert any("vault automation handoff" in step for step in read_status["startup_checklist"])


def test_update_status_read_missing_file_is_non_fatal(tmp_path, monkeypatch, capsys):
    from vault.cli import main

    monkeypatch.setenv("VAULT_AGENT_REGISTRY_DIR", str(tmp_path / "registry"))

    main(["update-status", "--read-status", "--agent", "codex", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["missing"] is True
    assert payload["startup_agent_id"] == "codex"
    assert payload["status_path"] == str(tmp_path / "registry" / "update-status.json")
    assert "write-status" in payload["message"]
    assert any("write-status" in step for step in payload["startup_checklist"])


def test_agent_update_distribution_doctor_reports_stale_and_attention(tmp_path, monkeypatch, capsys):
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
            "--json",
        ]
    )
    capsys.readouterr()

    main(["agent", "doctor", "--json"])
    missing = json.loads(capsys.readouterr().out)
    assert missing["ok"] is False
    assert missing["status_exists"] is False
    assert any("write-status" in action for action in missing["recommended_actions"])

    main(["update-status", "--latest-version", "9.9.9", "--write-status", "--json"])
    capsys.readouterr()
    status_path = tmp_path / "registry" / "update-status.json"
    stale_payload = json.loads(status_path.read_text(encoding="utf-8"))
    stale_payload["checked_at"] = "2000-01-01T00:00:00+00:00"
    status_path.write_text(json.dumps(stale_payload), encoding="utf-8")
    main(["update-status", "--doctor", "--max-status-age-minutes", "1", "--json"])
    doctor = json.loads(capsys.readouterr().out)
    assert doctor["ok"] is False
    assert doctor["status_exists"] is True
    assert doctor["status_stale"] is True
    assert doctor["agents_needing_attention"] == ["codex"]
    assert any("Upgrade" in action for action in doctor["recommended_actions"])

    main(["update-status", "--write-status", "--json"])
    capsys.readouterr()
    mismatch_payload = json.loads(status_path.read_text(encoding="utf-8"))
    mismatch_payload["installed_version"] = "0.0.1"
    status_path.write_text(json.dumps(mismatch_payload), encoding="utf-8")
    main(["agent", "doctor", "--json"])
    mismatch = json.loads(capsys.readouterr().out)
    assert mismatch["ok"] is False
    assert mismatch["status_current_runtime_mismatch"] is True
    assert mismatch["status_installed_version"] == "0.0.1"
    assert any("0.0.1" in action for action in mismatch["recommended_actions"])

    main(["update-status", "--write-status", "--json"])
    capsys.readouterr()
    main(["agent", "doctor", "--json"])
    healthy = json.loads(capsys.readouterr().out)
    assert healthy["ok"] is True
    assert healthy["status_stale"] is False
    assert healthy["agents_needing_attention"] == []


def test_cross_runtime_update_notice_smoke_for_shared_project(tmp_path, monkeypatch, capsys):
    from vault import __version__
    from vault.agent_registry import load_registry, save_registry
    from vault.cli import main

    monkeypatch.setenv("VAULT_AGENT_REGISTRY_DIR", str(tmp_path / "registry"))
    project = tmp_path / "shared-project"
    project.mkdir()

    for runtime in ["codex", "claude-code", "openclaw", "hermes"]:
        main(
            [
                "agent",
                "register",
                "--agent",
                runtime,
                "--project",
                str(project),
                "--scope",
                "shared",
                "--features",
                "core,mcp",
                "--json",
            ]
        )
        capsys.readouterr()

    registry = load_registry()
    registry["agents"]["openclaw"]["vault_version"] = "0.0.1"
    save_registry(registry)

    main(["update-status", "--write-status", "--json"])
    status = json.loads(capsys.readouterr().out)
    assert status["agent_count"] == 4
    assert status["projects"] == [str(project.resolve())]
    notices = {item["agent_id"]: item for item in status["agent_update_notices"]}
    assert sorted(notices) == ["claude-code", "codex", "hermes", "openclaw"]
    assert notices["openclaw"]["registered_version"] == "0.0.1"
    assert notices["openclaw"]["behind_current_runtime"] is True
    assert notices["openclaw"]["needs_attention"] is True
    assert notices["codex"]["registered_version"] == __version__
    assert notices["codex"]["needs_attention"] is False

    main(["update-status", "--read-status", "--agent", "openclaw", "--json"])
    focused = json.loads(capsys.readouterr().out)
    assert focused["startup_agent_id"] == "openclaw"
    assert focused["current_agent_needs_attention"] is True
    assert __version__ in focused["current_agent_recommended_action"]

    main(["agent", "doctor", "--json"])
    doctor = json.loads(capsys.readouterr().out)
    assert doctor["ok"] is False
    assert doctor["agents_missing_from_status"] == []
    assert doctor["agents_needing_attention"] == ["openclaw"]
    assert any("Upgrade" in action or "restart" in action for action in doctor["recommended_actions"])


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
