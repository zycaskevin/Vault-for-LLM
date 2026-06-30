import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_agent_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("VAULT_AGENT_REGISTRY_DIR", str(tmp_path / "agent-registry"))
    monkeypatch.setenv("VAULT_AGENT_PRIVATE_ROOT", str(tmp_path / "agent-private-root"))


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


def test_run_agent_setup_consumer_audience_writes_daily_report_guide_and_safe_schedule(tmp_path):
    from vault.agent_setup import AgentSetupConfig, current_vault_executable, run_agent_setup

    project = tmp_path / "consumer-project"
    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=project,
            scope="shared",
            agent="consumer-agent",
            audience="consumer",
            features=["core", "mcp"],
            language="zh-Hant",
            template_dir=tmp_path / "templates",
        )
    )

    assert result["audience"] == "consumer"
    assert result["consumer_daily_report"]["guide"].endswith("README-consumer-daily-report.md")
    guide = (tmp_path / "templates" / "README-consumer-daily-report.md").read_text(encoding="utf-8")
    assert "你不需要學 CLI" in guide
    assert "vault daily-report" in guide
    assert {"cron", "readme"}.issubset(result["automation_schedule_templates"])
    cron = (tmp_path / "templates" / "memory-automation.cron").read_text(encoding="utf-8")
    readme = (tmp_path / "templates" / "README-memory-automation.md").read_text(encoding="utf-8")
    assert "vault automation cycle" in cron
    assert "--write-workspace" in cron
    assert "vault daily-report" in cron
    assert current_vault_executable() in cron
    assert "--language zh-Hant" in cron
    assert "0 9 * * * sh -lc" in cron
    assert "daily-report-latest" in readme
    assert "--apply" not in cron
    assert result["security_hardening"]["readme"].endswith("README-local-safety.md")
    security_env = (tmp_path / "templates" / "local-safety.env.example").read_text(encoding="utf-8")
    assert "VAULT_MCP_REQUIRE_AGENT_SIGNATURE=1" in security_env
    assert "VAULT_GUI_TOKEN=" in security_env
    assert result["human_next_steps"]
    assert any("daily report" in step for step in result["human_next_steps"])
    assert any("daily-report" in step for step in result["next_steps"])
    assert result["agent_next_steps"] == result["next_steps"]


def test_run_agent_setup_consumer_audience_supports_simplified_chinese(tmp_path):
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    project = tmp_path / "consumer-project"
    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=project,
            scope="shared",
            agent="consumer-agent",
            audience="consumer",
            features=["core", "mcp"],
            language="zh-CN",
            template_dir=tmp_path / "templates",
        )
    )

    assert result["language"] == "zh-CN"
    guide = (tmp_path / "templates" / "README-consumer-daily-report.md").read_text(encoding="utf-8")
    safety = (tmp_path / "templates" / "README-local-safety.md").read_text(encoding="utf-8")
    assert "一般用户模式" in guide
    assert "你不需要学习 CLI" in guide
    cron = (tmp_path / "templates" / "memory-automation.cron").read_text(encoding="utf-8")
    assert "--language zh-CN" in cron
    assert "本机安全默认值" in safety


def test_setup_agent_consumer_text_output_separates_human_and_agent_steps(tmp_path, capsys):
    from vault.cli import main

    project = tmp_path / "consumer-project"
    main(
        [
            "setup-agent",
            "--non-interactive",
            "--audience",
            "consumer",
            "--agent",
            "consumer-agent",
            "--scope",
            "shared",
            "--memory-layout",
            "shared",
            "--agent-project-dir",
            str(project),
            "--features",
            "core,mcp",
            "--language",
            "zh-Hant",
        ]
    )

    out = capsys.readouterr().out
    assert "Vault consumer setup complete" in out
    assert "For you:" in out
    assert "For your agent:" in out
    assert "Full maintenance details are available with --json." in out
    assert "Next steps:" not in out
    assert "Review MCP startup guide" not in out


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
    assert "vault memory pipeline" in cron
    assert "--write-report" in cron
    assert "vault memory reflection" in cron
    assert "vault automation cycle" in cron
    assert "vault automation inbox" in cron
    assert "vault automation review-summary" in cron
    assert "vault automation learning-health" in cron
    assert "--write-handoff" in cron
    assert "--write-health" in cron
    assert "--write-workspace" not in cron
    assert "--project-dir" in cron
    assert str(project) in cron
    assert "--apply" not in cron
    assert "memory-automation.log" in cron
    assert "memory-automation" in plist
    assert "memory-automation.err.log" in plist
    assert workflow["name"] == "Vault-for-LLM Memory Automation"
    assert workflow["nodes"][1]["name"] == "Vault Memory Automation"
    assert "vault automation cycle" in workflow["nodes"][1]["parameters"]["command"]
    assert "vault memory pipeline" in workflow["nodes"][1]["parameters"]["command"]
    assert "--write-report" in workflow["nodes"][1]["parameters"]["command"]
    assert "vault memory reflection" in workflow["nodes"][1]["parameters"]["command"]
    assert "vault automation inbox" in workflow["nodes"][1]["parameters"]["command"]
    assert "vault automation review-summary" in workflow["nodes"][1]["parameters"]["command"]
    assert "vault automation learning-health" in workflow["nodes"][1]["parameters"]["command"]
    assert "--write-handoff" in workflow["nodes"][1]["parameters"]["command"]
    assert "--write-health" in workflow["nodes"][1]["parameters"]["command"]
    assert "vault automation plan" in readme
    assert "Next agent startup handoff" in readme
    assert "vault automation handoff" in readme
    assert "vault memory pipeline" in readme
    assert "vault memory reflection" in readme
    assert "learning-health-latest.json" in readme
    assert "review-summary-latest.json" in readme
    assert "scheduled command: `vault automation cycle`" in readme
    assert "next agent startup command: `vault automation handoff`" in readme
    assert "reports/automation/inbox-latest.json" in readme
    assert "reports/automation/review-summary-latest.json" in readme
    assert "reports/automation/learning-health-latest.json" in readme
    assert "reports/automation/pipeline-latest.json" in readme
    assert "session lessons as candidate memories" in readme
    assert "reflection review cards" in readme
    assert "apply reversible archival: `false`" in readme
    mcp_startup = result["mcp_startup"]
    mcp_json = json.loads(Path(mcp_startup["json"]).read_text(encoding="utf-8"))
    mcp_readme = Path(mcp_startup["readme"]).read_text(encoding="utf-8")
    assert mcp_json["mcp_server"]["tool_profile"] == "core"
    assert [step["tool"] for step in mcp_json["startup_sequence"][:2]] == [
        "vault_update_status",
        "vault_automation_handoff",
    ]
    assert mcp_json["startup_sequence"][0]["arguments"]["read_status"] is True
    assert mcp_json["startup_sequence"][0]["arguments"]["agent_id"] == "automation-agent"
    assert mcp_json["startup_sequence"][0]["fallback_arguments"]["check_pypi"] is False
    assert mcp_json["startup_sequence"][0]["fallback_arguments"]["agent_id"] == "automation-agent"
    assert mcp_json["startup_sequence"][1]["result_contract"]["read_first"] == [
        "fleet_health_content",
        "pipeline_receipt_content",
        "review_summary_content",
        "learning_health_content",
        "content",
    ]
    assert mcp_json["safety"]["check_pypi_default"] is False
    assert mcp_json["safety"]["auto_promote_memory"] is False
    assert mcp_json["safety"]["read_existing_update_status_first"] is True
    assert "vault_update_status" in mcp_readme
    assert "vault_automation_handoff" in mcp_readme
    assert "fleet_health_content" in mcp_readme
    assert "pipeline_receipt_content" in mcp_readme
    update_status = result["update_status_templates"]
    update_contract = json.loads(Path(update_status["contract"]).read_text(encoding="utf-8"))
    update_readme = Path(update_status["readme"]).read_text(encoding="utf-8")
    update_cron = Path(update_status["cron"]).read_text(encoding="utf-8")
    update_plist = Path(update_status["launchagent"]).read_text(encoding="utf-8")
    refresh_script = Path(update_status["refresh_script"])
    rollout_readme = Path(update_status["rollout_readme"]).read_text(encoding="utf-8")
    assert update_contract["mcp_read"]["arguments"]["read_status"] is True
    assert update_contract["mcp_read"]["arguments"]["agent_id"] == "automation-agent"
    assert update_contract["mcp_fallback"]["arguments"]["check_pypi"] is False
    assert update_contract["mcp_fallback"]["arguments"]["agent_id"] == "automation-agent"
    assert update_contract["mcp_doctor"]["arguments"]["doctor"] is True
    assert update_contract["mcp_doctor"]["arguments"]["agent_id"] == "automation-agent"
    assert update_contract["safety"]["auto_upgrade"] is False
    assert "vault update-status --read-status --agent automation-agent --json" in update_readme
    assert "doctor=true" in update_readme
    assert "vault update-status --write-status --json" in update_cron
    assert "com.zycaskevin.vault-for-llm.update-status" in update_plist
    assert refresh_script.exists()
    assert os.access(refresh_script, os.X_OK)
    assert "update-status --doctor" in refresh_script.read_text(encoding="utf-8")
    assert "Agent Update Rollout" in rollout_readme
    assert "not an auto-upgrader" in rollout_readme
    adapters = result["agent_adapter_startup"]
    adapter_contract = json.loads(Path(adapters["contract"]).read_text(encoding="utf-8"))
    adapter_readme = Path(adapters["readme"]).read_text(encoding="utf-8")
    runtime_playbook = json.loads(Path(adapters["runtime_playbook"]).read_text(encoding="utf-8"))
    runtime_playbook_readme = Path(adapters["runtime_playbook_readme"]).read_text(encoding="utf-8")
    codex_template = Path(adapters["codex"]).read_text(encoding="utf-8")
    openclaw_template = Path(adapters["openclaw"]).read_text(encoding="utf-8")
    assert sorted(adapter_contract["adapters"]) == ["claude_code", "codex", "hermes", "openclaw"]
    assert adapter_contract["agent"] == "automation-agent"
    assert adapter_contract["startup_sequence"][0]["mcp"]["arguments"]["read_status"] is True
    assert adapter_contract["startup_sequence"][0]["mcp"]["arguments"]["agent_id"] == "automation-agent"
    assert adapter_contract["startup_sequence"][0]["fallback"]["mcp"]["arguments"]["check_pypi"] is False
    assert adapter_contract["handoff_contract"]["read_order"] == [
        "fleet_health_content",
        "pipeline_receipt_content",
        "review_summary_content",
        "learning_health_content",
        "content",
    ]
    assert adapter_contract["startup_sequence"][1]["result_contract"]["do_not_replace_content"] is True
    assert any(step["name"] == "check_update_distribution_when_needed" for step in adapter_contract["startup_sequence"])
    assert adapter_contract["safety"]["auto_upgrade"] is False
    assert adapter_contract["safety"]["candidate_first_memory"] is True
    assert adapter_readme.count("vault guide") >= 1
    assert runtime_playbook["agent_first_entrypoints"]["human"] == "vault guide"
    assert runtime_playbook["startup_rule"][0].startswith("Keep the human-facing surface small")
    assert "Humans choose intent; agents choose commands" in runtime_playbook_readme
    assert "update-status -> automation handoff -> search/read/propose" in adapter_readme
    assert "fleet_health_content" in adapter_readme
    assert "pipeline_receipt_content" in adapter_readme
    assert "review_summary_content" in adapter_readme
    assert "learning_health_content" in adapter_readme
    assert "MCP doctor" in adapter_readme
    assert "no auto-upgrade" in adapter_readme
    assert "doctor=true" in codex_template
    assert "vault guide --mode agent --json" in codex_template
    assert "fleet_health_content" in codex_template
    assert "pipeline_receipt_content" in codex_template
    assert "review_summary_content" in codex_template
    assert "learning_health_content" in codex_template
    assert "vault update-status --read-status --agent automation-agent --json" in codex_template
    assert "latest-context.md" in openclaw_template
    assert runtime_playbook["mcp"]["doctor"]["arguments"]["doctor"] is True
    assert runtime_playbook["mcp"]["doctor"]["arguments"]["agent_id"] == "automation-agent"
    assert runtime_playbook["mcp"]["handoff"]["read_order"] == [
        "fleet_health_content",
        "pipeline_receipt_content",
        "review_summary_content",
        "learning_health_content",
        "content",
    ]
    assert runtime_playbook["safety"]["fleet_health_preface_read_only"] is True
    assert runtime_playbook["safety"]["pipeline_receipt_preface_read_only"] is True
    assert runtime_playbook["safety"]["review_summary_preface_read_only"] is True
    assert runtime_playbook["safety"]["learning_health_preface_read_only"] is True
    assert runtime_playbook["safety"]["auto_upgrade"] is False
    assert sorted(runtime_playbook["runtime_targets"]) == ["claude_code", "codex", "hermes", "openclaw"]
    assert "Runtime Update Playbook" in runtime_playbook_readme
    assert "vault guide --mode maintenance --json" in runtime_playbook_readme
    assert "fleet_health_content" in runtime_playbook_readme
    assert "pipeline_receipt_content" in runtime_playbook_readme
    assert "review_summary_content" in runtime_playbook_readme
    assert "learning_health_content" in runtime_playbook_readme
    assert "one shared project vault" in runtime_playbook_readme
    assert "not an auto-upgrader" in runtime_playbook_readme
    assert "README-runtime-update-playbook.md" in adapter_readme
    assert any("memory automation schedule" in step for step in result["next_steps"])
    assert any("vault automation handoff --project-dir" in step for step in result["next_steps"])
    assert any("MCP startup guide" in step for step in result["next_steps"])
    assert any("Agent adapter startup guide" in step for step in result["next_steps"])
    assert any("runtime update playbook" in step for step in result["next_steps"])
    assert any("Agent update status guide" in step for step in result["next_steps"])
    assert any("update rollout health check" in step for step in result["next_steps"])


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
    assert "vault memory pipeline" in cron
    assert "--write-report" in cron
    assert "vault memory reflection" in cron
    assert "vault automation cycle" in cron
    assert "vault automation inbox" in cron
    assert "--apply" in cron
    assert "<string>sh</string>" in plist
    assert "vault automation cycle" in plist
    assert "vault memory pipeline" in plist
    assert "vault memory reflection" in plist
    assert "vault automation inbox" in plist
    assert "vault automation cycle" in workflow["nodes"][1]["parameters"]["command"]
    assert "vault memory pipeline" in workflow["nodes"][1]["parameters"]["command"]
    assert "--write-report" in workflow["nodes"][1]["parameters"]["command"]
    assert "vault memory reflection" in workflow["nodes"][1]["parameters"]["command"]
    assert "vault automation inbox" in workflow["nodes"][1]["parameters"]["command"]
    assert "scheduled command: `vault automation cycle`" in readme
    assert "`cycle` first writes a bounded learning policy" in readme
    assert "vault automation handoff" in readme
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


def test_run_agent_setup_can_include_transcript_hints_in_scheduled_handoff(tmp_path):
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
            automation_include_transcripts=True,
            automation_transcript_limit=7,
            template_dir=tmp_path / "templates",
        )
    )

    cron = Path(result["automation_schedule_templates"]["cron"]).read_text(encoding="utf-8")
    plist = Path(result["automation_schedule_templates"]["launchagent"]).read_text(encoding="utf-8")
    workflow = json.loads(Path(result["automation_schedule_templates"]["n8n"]).read_text(encoding="utf-8"))
    readme = Path(result["automation_schedule_templates"]["readme"]).read_text(encoding="utf-8")

    assert "--include-transcripts --transcript-limit 7" in cron
    assert "--include-transcripts --transcript-limit 7" in plist
    assert "--include-transcripts --transcript-limit 7" in workflow["nodes"][1]["parameters"]["command"]
    assert "--include-transcripts --transcript-limit 7" in readme
    assert "uncaptured transcript hints in scheduled handoff: `true`" in readme
    assert "metadata-only and does not read transcript contents" in readme


def test_run_agent_setup_can_write_scheduled_cycle_workspace(tmp_path):
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
            automation_write_workspace=True,
            automation_workspace_inbox_limit=9,
            automation_include_transcripts=True,
            automation_transcript_limit=7,
            template_dir=tmp_path / "templates",
        )
    )

    cron = Path(result["automation_schedule_templates"]["cron"]).read_text(encoding="utf-8")
    plist = Path(result["automation_schedule_templates"]["launchagent"]).read_text(encoding="utf-8")
    workflow = json.loads(Path(result["automation_schedule_templates"]["n8n"]).read_text(encoding="utf-8"))
    readme = Path(result["automation_schedule_templates"]["readme"]).read_text(encoding="utf-8")

    expected = "--write-workspace --inbox-limit 9 --include-transcripts --transcript-limit 7"
    assert expected in cron
    assert expected in plist
    assert expected in workflow["nodes"][1]["parameters"]["command"]
    assert expected in readme
    assert "scheduled cycle workspace: `true`" in readme
    assert "cycle workspace path: `reports/automation/cycle-latest.json`" in readme
    assert "cycle workspace Markdown: `reports/automation/cycle-latest.md`" in readme
    assert "next agent startup command: `vault automation handoff`" in readme


def test_run_agent_setup_can_enable_scheduled_transcript_capture(tmp_path):
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
            automation_apply=True,
            automation_write_workspace=True,
            automation_include_transcripts=True,
            automation_capture_transcripts=True,
            automation_capture_transcript_limit=2,
            template_dir=tmp_path / "templates",
        )
    )

    cron = Path(result["automation_schedule_templates"]["cron"]).read_text(encoding="utf-8")
    plist = Path(result["automation_schedule_templates"]["launchagent"]).read_text(encoding="utf-8")
    workflow = json.loads(Path(result["automation_schedule_templates"]["n8n"]).read_text(encoding="utf-8"))
    readme = Path(result["automation_schedule_templates"]["readme"]).read_text(encoding="utf-8")

    expected = "vault memory pipeline"
    assert expected in cron
    assert expected in plist
    assert expected in workflow["nodes"][1]["parameters"]["command"]
    assert expected in readme
    assert "--transcript-limit 2" in cron
    assert "--capture-transcripts" not in cron
    assert "--apply" in cron
    assert "auto-capture transcript candidates: `true`" in readme
    assert "writes candidates only" in readme


def test_run_agent_setup_can_write_low_risk_auto_promote_policy(tmp_path):
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    project = tmp_path / "agent-project"
    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=project,
            scope="shared",
            agent="automation-agent",
            features=["core", "mcp", "memory_agents"],
            automation_schedule_targets="cron",
            automation_interval_minutes=1440,
            automation_apply=True,
            automation_auto_promote_low_risk=True,
            template_dir=tmp_path / "templates",
        )
    )

    policy = Path(result["automation_policy"]["path"]).read_text(encoding="utf-8")
    readme = Path(result["automation_schedule_templates"]["readme"]).read_text(encoding="utf-8")
    cron = Path(result["automation_schedule_templates"]["cron"]).read_text(encoding="utf-8")

    assert result["automation_policy"]["status"] == "created"
    assert result["automation_policy"]["auto_promote_low_risk_candidates"] is True
    assert "auto_promote_low_risk_candidates: true" in policy
    assert "- session_capture" in policy
    assert "- session_lesson" in policy
    assert "- low" in policy
    assert "low-risk auto-promote policy: `true`" in readme
    assert "requires `automation_policy.yaml` plus `--apply`" in readme
    assert "--apply" in cron
    assert any("Review low-risk auto-promote policy" in step for step in result["next_steps"])


def test_run_agent_setup_low_risk_auto_promote_without_apply_is_preview_only(tmp_path):
    from vault.agent_setup import AgentSetupConfig, run_agent_setup

    project = tmp_path / "agent-project"
    result = run_agent_setup(
        AgentSetupConfig(
            project_dir=project,
            scope="shared",
            agent="automation-agent",
            features=["core", "mcp"],
            automation_schedule_targets="cron",
            automation_auto_promote_low_risk=True,
            template_dir=tmp_path / "templates",
        )
    )

    cron = Path(result["automation_schedule_templates"]["cron"]).read_text(encoding="utf-8")
    assert "auto_promote_low_risk_candidates: true" in Path(result["automation_policy"]["path"]).read_text(
        encoding="utf-8"
    )
    assert "--apply" not in cron
    assert any("will preview only until --automation-apply is enabled" in step for step in result["next_steps"])


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


def test_agent_install_runtime_template_is_dry_run_then_apply(tmp_path, capsys):
    from vault.cli import main

    project = tmp_path / "agent-project"
    target = tmp_path / "AGENTS.md"
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
            "--json",
        ]
    )
    capsys.readouterr()

    main(
        [
            "agent",
            "install-runtime-template",
            "--runtime",
            "codex",
            "--target",
            str(target),
            "--template-dir",
            str(project / "agent-install"),
            "--json",
        ]
    )
    preview = json.loads(capsys.readouterr().out)
    assert preview["apply"] is False
    assert preview["changed"] is True
    assert preview["action"] == "create"
    assert not target.exists()

    main(
        [
            "agent",
            "install-runtime-template",
            "--runtime",
            "codex",
            "--target",
            str(target),
            "--template-dir",
            str(project / "agent-install"),
            "--apply",
            "--json",
        ]
    )
    applied = json.loads(capsys.readouterr().out)
    assert applied["apply"] is True
    assert applied["changed"] is True
    assert applied["action"] == "create"
    body = target.read_text(encoding="utf-8")
    assert "BEGIN Vault-for-LLM runtime startup: codex" in body
    assert "Codex Startup Template" in body

    target.write_text(body.replace("Codex Startup Template", "Old Vault Template"), encoding="utf-8")
    main(
        [
            "agent",
            "install-runtime-template",
            "--runtime",
            "codex",
            "--target",
            str(target),
            "--template-dir",
            str(project / "agent-install"),
            "--apply",
            "--json",
        ]
    )
    replaced = json.loads(capsys.readouterr().out)
    assert replaced["action"] == "replace"
    assert replaced["backup"]
    assert Path(replaced["backup"]).exists()
    assert "Codex Startup Template" in target.read_text(encoding="utf-8")
    assert "Old Vault Template" in Path(replaced["backup"]).read_text(encoding="utf-8")


def test_agent_startup_doctor_passes_current_setup_pack(tmp_path, capsys):
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
            "--json",
        ]
    )
    capsys.readouterr()

    main(
        [
            "agent",
            "startup-doctor",
            "--template-dir",
            str(project / "agent-install"),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["status"] == "pass"
    assert payload["summary"]["fail"] == 0
    assert payload["safety"]["read_only"] is True
    assert any(check["name"] == "mcp_handoff_result_contract" for check in payload["checks"])
    assert any(check["name"] == "adapter_handoff_contract" for check in payload["checks"])


def test_agent_startup_doctor_fails_old_handoff_contract(tmp_path, capsys):
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
            "--json",
        ]
    )
    capsys.readouterr()
    install_dir = project / "agent-install"
    mcp_path = install_dir / "mcp-startup.json"
    mcp_json = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert mcp_json["agent_first_entrypoints"]["agent"] == "vault guide --mode agent --json"
    mcp_readme = (install_dir / "README-mcp-startup.md").read_text(encoding="utf-8")
    assert "Humans choose intent; agents choose commands" in mcp_readme
    assert "vault guide" in mcp_readme
    mcp_json["startup_sequence"][1].pop("result_contract", None)
    mcp_path.write_text(json.dumps(mcp_json), encoding="utf-8")
    codex_path = install_dir / "codex-startup.md"
    codex_path.write_text(
        codex_path.read_text(encoding="utf-8").replace("review_summary_content", "old_handoff_field"),
        encoding="utf-8",
    )

    main(
        [
            "agent",
            "startup-doctor",
            "--template-dir",
            str(install_dir),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["status"] == "fail"
    assert payload["summary"]["fail"] >= 2
    assert any(check["name"] == "mcp_handoff_result_contract" and check["status"] == "fail" for check in payload["checks"])
    assert any(check["name"] == "codex_startup_template" and check["status"] == "fail" for check in payload["checks"])
    assert any("setup-agent" in action for action in payload["recommended_actions"])


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
    assert "VAULT_SHEBANG" in body
    assert "vault_update_status" in body
    assert "vault_automation_handoff" in body
    assert any("local-smoke.sh" in step for step in result["next_steps"])

    fake_vault = tmp_path / "fake-vault"
    fake_vault.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "from vault.cli import main\n"
        "main(sys.argv[1:])\n",
        encoding="utf-8",
    )
    fake_vault.chmod(0o755)
    env = {**os.environ, "VAULT": str(fake_vault)}
    env.pop("PYTHON", None)
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
    assert "work/profile/care/dream/remote/automation/observer" in captured.out
    assert "--validation-pack" in captured.out
    assert "--language" in captured.out
    assert "--automation-schedule" in captured.out
    assert "--automation-mode" in captured.out
    assert "--automation-command" in captured.out
    assert "--automation-apply" in captured.out
    assert "--automation-write-workspace" in captured.out
    assert "--automation-workspace-inbox-limit" in captured.out
    assert "--automation-include-transcripts" in captured.out
    assert "--automation-transcript-limit" in captured.out
    assert "--automation-auto-promote-low-risk" in captured.out


def test_cli_version_flag(capsys):
    from vault.cli import main

    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0

    captured = capsys.readouterr()
    assert "vault-for-llm 0.7.18" in captured.out


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
    assert "vault-for-llm[mcp,supabase]==0.7.18" in body
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
                "hybrid",
                str(tmp_path / "agent-project"),
                str(tmp_path / "profile-private"),
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
                "yes",  # write cycle workspace handoff
                "yes",  # include metadata-only transcript hints in scheduled handoff
                "no",  # do not auto-capture transcripts into candidates
                "yes",  # enable low-risk auto-promote policy
            ]
        )
    prompts: list[str] = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)
    config = interactive_setup({})

    assert config.language == "zh-Hant"
    assert config.memory_layout == "hybrid"
    assert config.agent_private_dir == tmp_path / "profile-private"
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
    assert any("cycle workspace handoff" in prompt for prompt in prompts)
    assert any("uncaptured transcript hints" in prompt for prompt in prompts)
    assert any("low-risk auto-promote policy" in prompt for prompt in prompts)
    assert config.remote_reader_targets == "n8n"
    assert config.agent_roster == "profile-agent:profile,remote-agent:remote"
    assert config.validation_pack_targets == "all"
    assert config.automation_schedule_targets == "cron"
    assert config.automation_mode == "balanced"
    assert config.automation_command == "cycle"
    assert config.automation_apply is False
    assert config.automation_write_workspace is True
    assert config.automation_workspace_inbox_limit == 5
    assert config.automation_include_transcripts is True
    assert config.automation_transcript_limit == 5
    assert config.automation_auto_promote_low_risk is True


def test_interactive_consumer_setup_keeps_questions_short(tmp_path, monkeypatch):
    from vault.agent_setup import interactive_setup

    answers = iter(
        [
            "daily-agent",
            "zh-Hant",
            "shared",
            "both",
            str(tmp_path / "obsidian"),
            "08:30",
        ]
    )
    prompts: list[str] = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)
    config = interactive_setup(
        {
            "audience": "consumer",
            "template_dir": str(tmp_path / "templates"),
        }
    )

    assert config.audience == "consumer"
    assert config.language == "zh-Hant"
    assert config.scope == "shared"
    assert config.memory_layout == "shared"
    assert config.features == ["core", "mcp", "obsidian_import", "supabase"]
    assert config.obsidian_vault == tmp_path / "obsidian"
    assert config.supabase_setup_mode == "simple"
    assert config.supabase_sync_targets == "cron"
    assert config.remote_reader_targets == "shell"
    assert config.automation_schedule_targets == "cron"
    assert config.automation_write_workspace is True
    assert config.automation_apply is False
    assert config.daily_report_time == "08:30"
    assert len(prompts) == 6
    assert any("語言" in prompt for prompt in prompts)
    assert not any("semantic search" in prompt for prompt in prompts)
    assert not any("auto-promote" in prompt for prompt in prompts)


def test_interactive_setup_does_not_ask_optional_deps_for_core_mcp_only(tmp_path, monkeypatch):
    import vault.agent_setup as agent_setup

    answers = iter(
            [
                "codex",
                "private",
                "hybrid",
                str(tmp_path / "agent-project"),
                str(tmp_path / "codex-private"),
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
    assert config.memory_layout == "hybrid"
    assert config.agent_private_dir == tmp_path / "codex-private"
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
