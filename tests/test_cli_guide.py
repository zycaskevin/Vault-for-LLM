import json

from vault.cli import main


def test_cli_guide_defaults_to_human_surface(capsys):
    main(["guide"])

    out = capsys.readouterr().out
    assert "Vault-for-LLM guide" in out
    assert "Intent shortcuts" in out
    assert "For humans, keep the surface small" in out
    assert "vault setup-agent" in out
    assert "vault daily-report" in out


def test_cli_guide_agent_json_lists_mcp_profiles(capsys):
    main(["guide", "--mode", "agent", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["mode"] == "agent"
    assert payload["intent"] == "all"
    assert "everyday_entrypoints" not in payload
    assert [row["profile"] for row in payload["agent_mcp_profiles"]] == [
        "core",
        "review",
        "maintenance",
        "full",
    ]


def test_cli_guide_all_pretty_includes_all_surfaces(capsys):
    main(["guide", "--mode", "all", "--pretty"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "all"
    assert payload["everyday_entrypoints"]
    assert any(row["command"] == "vault daily-report" for row in payload["everyday_entrypoints"])
    assert payload["agent_mcp_profiles"]
    assert payload["maintenance_entrypoints"]


def test_cli_guide_human_intent_skills_is_small(capsys):
    main(["guide", "--intent", "skills", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "human"
    assert payload["intent"] == "skills"
    assert payload["everyday_entrypoints"] == []
    assert [row["command"] for row in payload["maintenance_entrypoints"]] == [
        "vault skill upgrade-plan --installed-file installed-skills.json"
    ]
