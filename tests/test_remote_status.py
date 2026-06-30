import json
from datetime import datetime, timezone


def test_remote_status_reports_local_source_of_truth(tmp_path, capsys, monkeypatch):
    from vault.cli import main

    registry_dir = tmp_path / "registry"
    monkeypatch.setenv("VAULT_AGENT_REGISTRY_DIR", str(registry_dir))
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    project = tmp_path / "vault-project"
    main(["init", "--project-dir", str(project)])
    capsys.readouterr()

    main(["remote", "status", "--project-dir", str(project), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is True
    assert payload["source_of_truth"] == "local_sqlite"
    assert payload["remote_model"]["bidirectional"] is False
    assert payload["remote_model"]["realtime"] is False
    assert payload["local"]["db_exists"] is True
    assert payload["remote_reader"]["targets"]["shell"] is False
    assert any("setup-agent" in item for item in payload["next_actions"])


def test_remote_status_detects_templates_roster_and_sync_report(tmp_path, monkeypatch):
    from vault.cli import main
    from vault.remote_status import build_remote_status

    registry_dir = tmp_path / "registry"
    monkeypatch.setenv("VAULT_AGENT_REGISTRY_DIR", str(registry_dir))
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-test-key")

    project = tmp_path / "vault-project"
    main(["init", "--project-dir", str(project)])

    install = project / "agent-install"
    install.mkdir()
    (install / "remote-reader-smoke.sh").write_text("#!/usr/bin/env sh\n", encoding="utf-8")
    (install / "supabase-sync.cron").write_text("* * * * * vault sync\n", encoding="utf-8")
    (install / "agent-roster.json").write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "agent_id": "coze",
                        "remote_reader": True,
                        "can_write_shared": False,
                        "can_promote": False,
                    },
                    {
                        "agent_id": "codex",
                        "remote_reader": False,
                        "can_write_shared": True,
                        "can_promote": True,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    reports = project / "reports"
    reports.mkdir()
    (reports / "supabase-sync-latest.json").write_text(
        json.dumps({"status": "ok", "last_synced_at": datetime.now(timezone.utc).isoformat(), "processed": 7}),
        encoding="utf-8",
    )

    payload = build_remote_status(project)

    assert payload["ok"] is True
    assert payload["supabase"]["url_configured"] is True
    assert payload["supabase"]["anon_key_configured"] is True
    assert payload["remote_reader"]["targets"]["shell"] is True
    assert payload["sync"]["templates"]["targets"]["cron"] is True
    assert payload["sync"]["last_report"]["exists"] is True
    assert payload["sync"]["last_report"]["stale"] is False
    assert payload["agent_access"]["remote_readers"] == ["coze"]
    assert payload["agent_access"]["shared_writers"] == ["codex"]
    assert not any(item["code"] == "sync_report_missing" for item in payload["warnings"])


def test_remote_status_human_output(tmp_path, capsys, monkeypatch):
    from vault.cli import main

    monkeypatch.setenv("VAULT_AGENT_REGISTRY_DIR", str(tmp_path / "registry"))
    project = tmp_path / "vault-project"
    main(["init", "--project-dir", str(project)])
    capsys.readouterr()

    main(["remote", "status", "--project-dir", str(project)])
    output = capsys.readouterr().out

    assert "Vault remote status" in output
    assert "Source of truth: local vault.db" in output
    assert "Supabase read-only copy" in output
