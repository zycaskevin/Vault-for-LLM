import json
import os
import subprocess
import sys
from pathlib import Path


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
            agent="profile-agent",
            features=["core", "mcp", "supabase"],
            language="zh-Hant",
            supabase_setup_mode="advanced",
            supabase_sync_targets="all",
            template_dir=tmp_path / "templates",
        )
    )

    assert result["language"] == "zh-Hant"
    assert result["supabase_setup"]["mode"] == "advanced"
    assert "read_policy_sql" in result["supabase_setup"]
    assert {"cron", "launchagent", "n8n", "readme"}.issubset(result["supabase_sync_templates"])

    guide = (tmp_path / "templates" / "README-supabase-setup.md").read_text(encoding="utf-8")
    policy = (tmp_path / "templates" / "supabase-read-policy.sql").read_text(encoding="utf-8")
    cron = (tmp_path / "templates" / "supabase-sync.cron").read_text(encoding="utf-8")
    plist = (tmp_path / "templates" / "com.zycaskevin.vault-for-llm.supabase-sync.plist").read_text(
        encoding="utf-8"
    )
    workflow = json.loads((tmp_path / "templates" / "n8n-supabase-sync.workflow.json").read_text(encoding="utf-8"))

    assert "Supabase 是可選功能" in guide
    assert "進階 Multi-Agent / RLS" in guide
    assert "supabase-read-policy.sql" in guide
    assert "service role key" in guide
    assert "vault_search_readable" in policy
    assert "security definer" in policy
    assert "allowed_agents" in policy
    assert "? p_agent_id" in policy
    search_policy = policy.split(
        "create or replace function public.vault_search_readable", 1
    )[1].split("create or replace function public.vault_get_readable", 1)[0]
    assert "content_raw" not in search_policy
    assert "scripts.sync_to_supabase" in cron
    assert "--db" in cron
    assert str(project / "vault.db") in cron
    assert "--document-map" in cron
    assert "--health" in cron
    assert "supabase-sync" in plist
    assert "supabase-sync.log" in plist
    assert "supabase-sync.err.log" in plist
    assert "obsidian-sync.log" not in plist
    assert "scripts.sync_to_supabase" in workflow["nodes"][1]["parameters"]["command"]


def test_run_agent_setup_writes_remote_reader_templates(tmp_path):
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    project = tmp_path / "agent-project"
    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=project,
            scope="shared",
            agent="remote-agent",
            features=["core", "mcp", "supabase"],
            supabase_setup_mode="advanced",
            remote_reader_targets="all",
            remote_reader_query="pricing SOP",
            template_dir=tmp_path / "templates",
        )
    )

    templates = result["remote_reader_templates"]
    assert {"shell", "n8n", "coze", "env_example", "readme"}.issubset(templates)

    shell = (tmp_path / "templates" / "remote-reader-smoke.sh").read_text(encoding="utf-8")
    workflow = json.loads((tmp_path / "templates" / "n8n-remote-reader.workflow.json").read_text(encoding="utf-8"))
    coze = json.loads((tmp_path / "templates" / "coze-supabase-vault-openapi.json").read_text(encoding="utf-8"))
    env_example = (tmp_path / "templates" / "remote-reader.env.example").read_text(encoding="utf-8")
    readme = (tmp_path / "templates" / "README-remote-reader.md").read_text(encoding="utf-8")

    assert "vault remote smoke" in shell
    assert "--agent-id remote-agent" in shell
    assert "--json" in shell
    assert "pricing SOP" in shell
    assert workflow["nodes"][1]["name"] == "Vault Remote Search"
    assert "vault remote search" in workflow["nodes"][1]["parameters"]["command"]
    assert coze["paths"]["/rpc/vault_search_readable"]["post"]["operationId"] == "vaultRemoteSearch"
    assert coze["components"]["securitySchemes"]["SupabaseApiKey"]["name"] == "apikey"
    assert "SUPABASE_ANON_KEY" in env_example
    assert "SUPABASE_SERVICE_ROLE_KEY=" not in env_example
    assert "vault remote search -> vault remote map -> vault remote read" in readme
    assert any("remote reader smoke" in step for step in result["next_steps"])


def test_run_agent_setup_writes_memory_automation_schedule_templates(tmp_path):
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    project = tmp_path / "agent-project"
    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=project,
            scope="shared",
            agent="automation-agent",
            features=["core", "mcp", "memory_agents"],
            automation_schedule_targets="all",
            automation_interval_minutes=1440,
            automation_mode="balanced",
            template_dir=tmp_path / "templates",
        )
    )

    templates = result["automation_schedule_templates"]
    assert {"cron", "launchagent", "n8n", "readme"}.issubset(templates)

    cron = (tmp_path / "templates" / "memory-automation.cron").read_text(encoding="utf-8")
    plist = (tmp_path / "templates" / "com.zycaskevin.vault-for-llm.memory-automation.plist").read_text(
        encoding="utf-8"
    )
    workflow = json.loads((tmp_path / "templates" / "n8n-memory-automation.workflow.json").read_text(encoding="utf-8"))
    readme = (tmp_path / "templates" / "README-memory-automation.md").read_text(encoding="utf-8")

    assert "0 3 * * * sh -lc" in cron
    assert "vault automation cycle" in cron
    assert "vault automation inbox" in cron
    assert "--write-handoff" in cron
    assert "--project-dir" in cron
    assert str(project) in cron
    assert "--apply" not in cron
    assert "memory-automation.log" in cron
    assert "memory-automation" in plist
    assert "memory-automation.err.log" in plist
    assert workflow["name"] == "Vault-for-LLM Memory Automation"
    assert workflow["nodes"][1]["name"] == "Vault Memory Automation"
    assert "vault automation cycle" in workflow["nodes"][1]["parameters"]["command"]
    assert "vault automation inbox" in workflow["nodes"][1]["parameters"]["command"]
    assert "--write-handoff" in workflow["nodes"][1]["parameters"]["command"]
    assert "vault automation plan" in readme
    assert "scheduled command: `vault automation cycle`" in readme
    assert "reports/automation/inbox-latest.json" in readme
    assert "apply reversible archival: `false`" in readme
    assert any("memory automation schedule" in step for step in result["next_steps"])


def test_run_agent_setup_can_schedule_automation_cycle(tmp_path):
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    project = tmp_path / "agent-project"
    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=project,
            scope="shared",
            agent="automation-agent",
            features=["core", "mcp", "memory_agents"],
            automation_schedule_targets="all",
            automation_interval_minutes=1440,
            automation_mode="balanced",
            automation_command="cycle",
            automation_apply=True,
            template_dir=tmp_path / "templates",
        )
    )

    cron = (tmp_path / "templates" / "memory-automation.cron").read_text(encoding="utf-8")
    plist = (tmp_path / "templates" / "com.zycaskevin.vault-for-llm.memory-automation.plist").read_text(
        encoding="utf-8"
    )
    workflow = json.loads((tmp_path / "templates" / "n8n-memory-automation.workflow.json").read_text(encoding="utf-8"))
    readme = (tmp_path / "templates" / "README-memory-automation.md").read_text(encoding="utf-8")

    assert "0 3 * * * sh -lc" in cron
    assert "vault automation cycle" in cron
    assert "vault automation inbox" in cron
    assert "--apply" in cron
    assert "<string>sh</string>" in plist
    assert "vault automation cycle" in plist
    assert "vault automation inbox" in plist
    assert "vault automation cycle" in workflow["nodes"][1]["parameters"]["command"]
    assert "vault automation inbox" in workflow["nodes"][1]["parameters"]["command"]
    assert "scheduled command: `vault automation cycle`" in readme
    assert "`cycle` first writes a bounded learning policy" in readme
    assert result["automation_schedule_templates"]["readme"].endswith("README-memory-automation.md")


def test_run_agent_setup_memory_automation_apply_is_explicit(tmp_path):
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    project = tmp_path / "agent-project"
    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=project,
            scope="private",
            agent="codex",
            features=["core", "mcp"],
            automation_schedule_targets="cron",
            automation_interval_minutes=30,
            automation_mode="conservative",
            automation_command="run",
            automation_apply=True,
            template_dir=tmp_path / "templates",
        )
    )

    cron = Path(result["automation_schedule_templates"]["cron"]).read_text(encoding="utf-8")
    assert "*/30 * * * * sh -lc" in cron
    assert "vault automation run" in cron
    assert "vault automation inbox" in cron
    assert "--mode conservative" in cron
    assert "--apply" in cron


def test_run_agent_setup_writes_agent_roster_and_validation_pack(tmp_path):
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    project = tmp_path / "agent-project"
    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=project,
            scope="shared",
            agent="profile-agent",
            features=["core", "mcp", "supabase", "memory_agents"],
            supabase_setup_mode="advanced",
            remote_reader_targets="all",
            remote_reader_query="pricing SOP",
            agent_roster="profile-agent:profile,work-agent:work,product-agent:work,remote-agent:remote,n8n:automation",
            validation_pack_targets="all",
            template_dir=tmp_path / "templates",
        )
    )

    roster = result["agent_roster"]
    validation = result["live_validation_pack"]
    assert roster["count"] == 5
    assert {"roster", "matrix", "commands", "readme", "env"}.issubset(roster)
    assert {"remote", "n8n", "coze", "readme"}.issubset(validation)

    roster_json = json.loads((tmp_path / "templates" / "agent-roster.json").read_text(encoding="utf-8"))
    matrix = (tmp_path / "templates" / "AGENT_ACCESS_MATRIX.md").read_text(encoding="utf-8")
    profile_agent_env = (tmp_path / "templates" / "agent-env" / "profile-agent.env.example").read_text(encoding="utf-8")
    validate_remote = (tmp_path / "templates" / "validate-remote-reader.sh").read_text(encoding="utf-8")
    validate_coze = (tmp_path / "templates" / "VALIDATE-coze.md").read_text(encoding="utf-8")

    assert roster_json["agents"][0]["agent_id"] == "profile-agent"
    assert roster_json["agents"][0]["role"] == "profile"
    assert roster_json["agents"][0]["private_memory"] is True
    assert any(item["agent_id"] == "remote-agent" and item["remote_reader"] for item in roster_json["agents"])
    assert "| profile-agent | profile | private | high | review | True | True | False |" in matrix
    assert "VAULT_AGENT_ROLE=profile" in profile_agent_env
    assert "vault remote smoke" in validate_remote
    assert "--json" in validate_remote
    assert "pricing SOP" in validate_remote
    assert "content_raw" in validate_coze
    assert any("agent access matrix" in step for step in result["next_steps"])
    assert any("live validation checklist" in step for step in result["next_steps"])


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
            "profile-agent",
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
    assert any("vault search" in step and "--json" in step for step in payload["next_steps"])


def test_run_agent_setup_writes_executable_local_smoke(tmp_path):
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    project = tmp_path / "agent-project"
    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=project,
            scope="shared",
            agent="codex",
            features=["core", "mcp"],
            template_dir=tmp_path / "templates",
        )
    )

    script = Path(result["local_smoke"]["script"])
    body = script.read_text(encoding="utf-8")
    assert script.exists()
    assert os.access(script, os.X_OK)
    assert "$VAULT search" in body
    assert "--json" in body
    assert "$VAULT remember" in body
    assert "$VAULT candidates" in body
    assert any("local-smoke.sh" in step for step in result["next_steps"])

    env = {
        **os.environ,
        "VAULT": f"{sys.executable} -m vault.cli",
        "PYTHON": sys.executable,
    }
    completed = subprocess.run([str(script)], capture_output=True, text=True, check=False, env=env)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "local_smoke=ok" in completed.stdout


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
    assert "--remote-reader" in captured.out
    assert "--agent-roster" in captured.out
    assert "--validation-pack" in captured.out
    assert "--language" in captured.out
    assert "--automation-schedule" in captured.out
    assert "--automation-mode" in captured.out
    assert "--automation-command" in captured.out
    assert "--automation-apply" in captured.out


def test_cli_version_flag(capsys):
    from vault.cli import main

    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0

    captured = capsys.readouterr()
    assert "vault-for-llm 0.6.69" in captured.out


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
            agent="profile-agent",
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
    assert "owner_agent: profile-agent" in guide
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
            agent="profile-agent",
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
            agent="profile-agent",
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
            agent="profile-agent",
            features=["core", "mcp"],
        )
    )

    assert result["environment_warnings"]
    assert any("~/.hermes/venvs/vault-for-llm" in step for step in result["next_steps"])


def test_run_agent_setup_writes_stable_venv_template(tmp_path):
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    project = tmp_path / "agent-project"
    stable_venv = tmp_path / "stable-venv"

    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=project,
            scope="shared",
            agent="codex",
            features=["core", "mcp", "supabase", "headroom"],
            stable_venv_path=stable_venv,
        )
    )

    payload = result["stable_venv"]
    script = Path(payload["script"])
    readme = Path(payload["readme"])
    assert payload["venv_path"] == str(stable_venv)
    assert script.exists()
    assert readme.exists()
    body = script.read_text(encoding="utf-8")
    assert "python3 -m venv \"$VENV\"" in body
    assert "vault-for-llm[mcp,supabase]==0.6.69" in body
    assert "headroom-ai" in body
    assert "--agent-project-dir" in body
    assert str(project) in body
    assert any("setup-stable-venv.sh" in step for step in result["next_steps"])


def test_setup_agent_cli_writes_default_stable_venv_script(tmp_path, capsys):
    from vault.cli import main

    project = tmp_path / "agent-project"
    main(
        [
            "setup-agent",
            "--non-interactive",
            "--agent",
            "codex",
            "--scope",
            "shared",
            "--agent-project-dir",
            str(project),
            "--features",
            "core,mcp",
            "--write-stable-venv-script",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["stable_venv"]["venv_path"].endswith(".hermes/venvs/vault-for-llm")
    assert Path(payload["stable_venv"]["script"]).exists()


def test_interactive_setup_asks_optional_feature_questions(tmp_path, monkeypatch):
    from vault.agent_setup import interactive_setup

    answers = iter(
        [
            "profile-agent",
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
            "n8n",  # remote reader templates
            "yes",  # agent roster
            "profile-agent:profile,remote-agent:remote",  # roster entries
            "all",  # live validation pack
            "cron",  # memory automation schedule
            "balanced",  # memory automation mode
            "",  # default memory automation command: cycle
            "no",  # no scheduled apply
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
    assert any("Remote reader templates" in prompt for prompt in prompts)
    assert any("multi-agent roster" in prompt for prompt in prompts)
    assert any("Live validation pack" in prompt for prompt in prompts)
    assert any("Memory automation schedule" in prompt for prompt in prompts)
    assert any("Memory automation mode" in prompt for prompt in prompts)
    assert any("Memory automation command" in prompt for prompt in prompts)
    assert any("reversible archival" in prompt for prompt in prompts)
    assert config.remote_reader_targets == "n8n"
    assert config.agent_roster == "profile-agent:profile,remote-agent:remote"
    assert config.validation_pack_targets == "all"
    assert config.automation_schedule_targets == "cron"
    assert config.automation_mode == "balanced"
    assert config.automation_command == "cycle"
    assert config.automation_apply is False


def test_interactive_setup_does_not_ask_optional_deps_for_core_mcp_only(tmp_path, monkeypatch):
    import vault.agent_setup as agent_setup

    answers = iter(
        [
            "codex",
            "private",
            str(tmp_path / "agent-project"),
            "en",
            "yes",  # MCP
            "no",  # semantic
            "no",  # Supabase
            "no",  # Headroom
            "no",  # memory agents
            "no",  # dev
            "",  # Obsidian
            "no",  # agent roster
            "none",  # memory automation schedule
        ]
    )
    prompts: list[str] = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(agent_setup, "python_environment_warnings", lambda: [])

    config = agent_setup.interactive_setup({})

    assert config.features == ["core", "mcp"]
    assert config.install_optional_deps is False
    assert not any("optional Python dependencies" in prompt for prompt in prompts)


def test_run_agent_setup_can_skip_supabase_setup_guide(tmp_path):
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=tmp_path / "agent-project",
            scope="shared",
            agent="remote-agent",
            features=["core", "supabase"],
            supabase_setup_mode="none",
        )
    )

    assert result["supabase_setup"] == {}
    assert not (tmp_path / "agent-project" / "agent-install" / "README-supabase-setup.md").exists()


def test_checked_in_supabase_read_policy_matches_generated_template():
    from pathlib import Path

    from vault.agent_setup import SUPABASE_READ_POLICY_SQL

    root = Path(__file__).resolve().parents[1]
    checked_in = (root / "docs" / "supabase_read_policy.sql").read_text(encoding="utf-8")

    assert checked_in == SUPABASE_READ_POLICY_SQL
    assert "vault_search_readable" in checked_in
    assert "vault_get_readable" in checked_in
    assert "vault_nodes_readable" in checked_in
    assert "vault_claims_readable" in checked_in
    assert "vault_content_readable" in checked_in
    assert "revoke all on table public.vault_knowledge from anon, authenticated" in checked_in
    assert "revoke all on table public.vault_knowledge_nodes from anon, authenticated" in checked_in
    assert "revoke all on table public.vault_knowledge_claims from anon, authenticated" in checked_in
    assert "grant execute on function public.vault_search_readable" in checked_in
    assert "content_raw" not in checked_in.split("create or replace function public.vault_search_readable", 1)[1].split("create or replace function public.vault_get_readable", 1)[0]
