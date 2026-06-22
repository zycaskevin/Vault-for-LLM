import json
import sys


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


def test_run_agent_setup_writes_supabase_sync_templates(tmp_path):
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    project = tmp_path / "agent-project"
    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=project,
            scope="shared",
            agent="nancy",
            features=["core", "mcp", "supabase"],
            language="zh-Hant",
            supabase_setup_mode="advanced",
            supabase_sync_targets="all",
            template_dir=tmp_path / "templates",
        )
    )

    assert result["language"] == "zh-Hant"
    assert result["supabase_setup"]["mode"] == "advanced"
    assert {"cron", "launchagent", "n8n", "readme"}.issubset(result["supabase_sync_templates"])

    guide = (tmp_path / "templates" / "README-supabase-setup.md").read_text(encoding="utf-8")
    cron = (tmp_path / "templates" / "supabase-sync.cron").read_text(encoding="utf-8")
    plist = (tmp_path / "templates" / "com.zycaskevin.vault-for-llm.supabase-sync.plist").read_text(
        encoding="utf-8"
    )
    workflow = json.loads((tmp_path / "templates" / "n8n-supabase-sync.workflow.json").read_text(encoding="utf-8"))

    assert "Supabase 是可選功能" in guide
    assert "進階 Multi-Agent / RLS" in guide
    assert "service role key" in guide
    assert "scripts.sync_to_supabase" in cron
    assert "--db" in cron
    assert str(project / "vault.db") in cron
    assert "--document-map" in cron
    assert "--health" in cron
    assert "supabase-sync" in plist
    assert "scripts.sync_to_supabase" in workflow["nodes"][1]["parameters"]["command"]


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
            "--language",
            "zh-Hant",
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
    assert payload["language"] == "zh-Hant"
    assert payload["obsidian"]["import"]["added"] == 1
    assert "cron" in payload["sync_templates"]
    assert (project / "raw" / "obsidian" / "Note.md").exists()


def test_setup_agent_accepts_global_project_dir_for_missing_directory(tmp_path, capsys):
    from vault.cli import main

    project = tmp_path / "missing-agent-project"
    main(
        [
            "setup-agent",
            "--non-interactive",
            "--agent",
            "nancy",
            "--scope",
            "private",
            "--features",
            "core,mcp",
            "--project-dir",
            str(project),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["project_dir"] == str(project.resolve())
    assert (project / "vault.db").exists()
    assert (project / "raw").is_dir()


def test_setup_agent_help_exposes_supabase_sync_options(capsys):
    from vault.cli import main

    try:
        main(["setup-agent", "--help"])
    except SystemExit as exc:
        assert exc.code == 0

    captured = capsys.readouterr()
    assert "--supabase-sync" in captured.out
    assert "--supabase-setup" in captured.out
    assert "--supabase-sync-interval-minutes" in captured.out
    assert "--language" in captured.out


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


def test_setup_agent_memory_agents_writes_report_only_guide(tmp_path):
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    project = tmp_path / "agent-project"
    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=project,
            scope="shared",
            agent="nancy",
            features=["core", "mcp", "memory_agents"],
            language="zh-Hant",
            template_dir=tmp_path / "templates",
        )
    )

    assert result["features"] == ["core", "mcp", "memory_agents"]
    assert result["memory_agents"]["mode"] == "report_only_candidate_only"
    guide = (tmp_path / "templates" / "README-memory-agents.md").read_text(encoding="utf-8")
    assert "Profile agent 預設只產生候選記憶" in guide
    assert "Dream agent 預設只產生 report" in guide
    assert "Forgetting agent 預設只建議" in guide
    assert "owner_agent: nancy" in guide
    assert any("Progressive Memory Disclosure" in step for step in result["next_steps"])


def test_run_agent_setup_installs_selected_optional_dependencies(tmp_path, monkeypatch):
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    calls: list[list[str]] = []

    class FakeCompleted:
        returncode = 0
        stdout = "installed"
        stderr = ""

    def fake_run(command, capture_output, text, check):
        calls.append(command)
        assert capture_output is True
        assert text is True
        assert check is False
        return FakeCompleted()

    monkeypatch.setattr("vault.agent_setup.subprocess.run", fake_run)

    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=tmp_path / "agent-project",
            scope="private",
            agent="nancy",
            features=["core", "mcp", "semantic", "supabase", "headroom"],
            install_optional_deps=True,
        )
    )

    joined = [" ".join(command) for command in calls]
    assert any("vault-for-llm[mcp,semantic,supabase]" in command for command in joined)
    assert any("headroom-ai" in command for command in joined)
    assert result["optional_dependency_install"]["installed"] is True
    assert not any("pip install headroom-ai" == step for step in result["next_steps"])


def test_run_agent_setup_installs_embedding_model_when_requested(tmp_path, monkeypatch):
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    calls: list[list[str]] = []

    class FakeCompleted:
        returncode = 0
        stdout = "model installed"
        stderr = ""

    def fake_run(command, capture_output, text, check):
        calls.append(command)
        return FakeCompleted()

    monkeypatch.setattr("vault.agent_setup.subprocess.run", fake_run)

    project = tmp_path / "agent-project"
    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=project,
            scope="private",
            agent="nancy",
            features=["core", "semantic"],
            install_embedding_model="mix",
        )
    )

    assert result["embedding_model_install"]["model"] == "mix"
    assert calls == [
        [
            sys.executable,
            "-m",
            "vault.cli",
            "--project-dir",
            str(project.resolve()),
            "install-embedding",
            "--model",
            "mix",
        ]
    ]
    assert not any(step == "vault install-embedding --model mix" for step in result["next_steps"])


def test_run_agent_setup_warns_about_temporary_python_env(tmp_path, monkeypatch):
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    monkeypatch.setattr("vault.agent_setup.sys.prefix", "/tmp/vault-migrate-venv")
    monkeypatch.setattr("vault.agent_setup.sys.executable", "/tmp/vault-migrate-venv/bin/python")

    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=tmp_path / "agent-project",
            scope="shared",
            agent="nancy",
            features=["core", "mcp"],
        )
    )

    assert result["environment_warnings"]
    assert any("~/.hermes/venvs/vault-for-llm" in step for step in result["next_steps"])


def test_interactive_setup_asks_optional_feature_questions(tmp_path, monkeypatch):
    from vault.agent_setup import interactive_setup

    answers = iter(
        [
            "nancy",
            "private",
            str(tmp_path / "agent-project"),
            "zh-Hant",  # setup language
            "yes",  # MCP
            "yes",  # semantic
            "yes",  # Supabase
            "yes",  # Headroom
            "no",  # memory agents
            "no",  # dev
            "yes",  # install optional deps
            "no",  # install local embedding model
            "",  # Obsidian
            "simple",  # Supabase setup guide
            "none",  # Supabase sync templates
        ]
    )
    prompts: list[str] = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)
    config = interactive_setup({})

    assert config.language == "zh-Hant"
    assert config.features == ["core", "mcp", "semantic", "supabase", "headroom"]
    assert config.install_optional_deps is True
    assert config.install_embedding_model is None
    assert any("stdio MCP" in prompt for prompt in prompts)
    assert any("安裝語言" in prompt for prompt in prompts)
    assert any("semantic search" in prompt for prompt in prompts)
    assert any("Supabase sync" in prompt for prompt in prompts)
    assert any("Headroom context compression" in prompt for prompt in prompts)
    assert any("memory-agent guidance" in prompt for prompt in prompts)
    assert any("optional Python dependencies" in prompt for prompt in prompts)
    assert any("local ONNX embedding model" in prompt for prompt in prompts)
    assert any("Daily Supabase sync templates" in prompt for prompt in prompts)


def test_run_agent_setup_can_skip_supabase_setup_guide(tmp_path):
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=tmp_path / "agent-project",
            scope="shared",
            agent="coco",
            features=["core", "supabase"],
            supabase_setup_mode="none",
        )
    )

    assert result["supabase_setup"] == {}
    assert not (tmp_path / "agent-project" / "agent-install" / "README-supabase-setup.md").exists()
