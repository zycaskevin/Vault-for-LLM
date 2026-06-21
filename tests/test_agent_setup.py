import json


def test_run_agent_setup_imports_obsidian_and_writes_templates(tmp_path):
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    project = tmp_path / "agent-project"
    obsidian = tmp_path / "ObsidianVault"
    (obsidian / "Projects").mkdir(parents=True)
    (obsidian / "00-Vault-Knowledge").mkdir()
    (obsidian / "Projects" / "Install.md").write_text(
        "# Agent Install\n\nUse Vault before answering project questions.\n",
        encoding="utf-8",
    )
    (obsidian / "00-Vault-Knowledge" / "Generated.md").write_text(
        "# Generated\n\nDo not import exported notes.\n",
        encoding="utf-8",
    )

    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=project,
            scope="private",
            agent="codex",
            features=["core", "mcp", "obsidian_import"],
            obsidian_vault=obsidian,
            import_obsidian=True,
            sync_targets="all",
            template_dir=tmp_path / "templates",
        )
    )

    assert (project / "vault.db").exists()
    assert (project / "raw" / "obsidian" / "Projects" / "Install.md").exists()
    assert not (project / "raw" / "obsidian" / "00-Vault-Knowledge" / "Generated.md").exists()
    assert result["obsidian"]["dry_run"]["added"] == 1
    assert result["obsidian"]["import"]["added"] == 1
    assert {"cron", "launchagent", "n8n", "readme"}.issubset(result["sync_templates"])

    cron = (tmp_path / "templates" / "obsidian-sync.cron").read_text(encoding="utf-8")
    plist = (tmp_path / "templates" / "com.zycaskevin.vault-for-llm.obsidian-sync.plist").read_text(
        encoding="utf-8"
    )
    workflow = json.loads((tmp_path / "templates" / "n8n-obsidian-sync.workflow.json").read_text(encoding="utf-8"))

    assert "vault import obsidian" in cron
    assert "--compile" in cron
    assert "<key>StartInterval</key>" in plist
    assert workflow["nodes"][1]["type"] == "n8n-nodes-base.executeCommand"


def test_setup_agent_cli_non_interactive(tmp_path, capsys):
    from vault.cli import main

    project = tmp_path / "agent-project"
    obsidian = tmp_path / "ObsidianVault"
    obsidian.mkdir()
    (obsidian / "Note.md").write_text("# Setup CLI\n\nCLI setup imports Obsidian.\n", encoding="utf-8")

    main(
        [
            "setup-agent",
            "--non-interactive",
            "--agent",
            "hermes",
            "--scope",
            "private",
            "--agent-project-dir",
            str(project),
            "--features",
            "core,mcp,obsidian_import",
            "--obsidian-vault",
            str(obsidian),
            "--import-obsidian",
            "--obsidian-sync",
            "cron",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["agent"] == "hermes"
    assert payload["obsidian"]["import"]["added"] == 1
    assert "cron" in payload["sync_templates"]
    assert (project / "raw" / "obsidian" / "Note.md").exists()


def test_setup_agent_headroom_is_optional_next_step(tmp_path):
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    project = tmp_path / "agent-project"
    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=project,
            scope="private",
            agent="codex",
            features=["core", "mcp", "headroom"],
        )
    )

    assert result["features"] == ["core", "mcp", "headroom"]
    assert any("headroom-ai" in step for step in result["next_steps"])
    assert any("original vault_read_range" in step for step in result["next_steps"])
