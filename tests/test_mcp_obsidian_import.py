import json


def test_mcp_obsidian_import_is_maintenance_not_core():
    from vault.mcp import select_tools

    core_names = {tool["name"] for tool in select_tools("core")}
    maintenance = select_tools("maintenance")
    maintenance_names = {tool["name"] for tool in maintenance}

    assert "vault_obsidian_import" not in core_names
    assert "vault_obsidian_resolve_conflict" not in core_names
    assert "vault_obsidian_import" in maintenance_names
    assert "vault_obsidian_resolve_conflict" in maintenance_names
    import_tool = next(tool for tool in maintenance if tool["name"] == "vault_obsidian_import")
    assert import_tool["inputSchema"]["properties"]["prune_missing"]["default"] is False
    resolver_tool = next(tool for tool in maintenance if tool["name"] == "vault_obsidian_resolve_conflict")
    assert set(resolver_tool["inputSchema"]["properties"]["resolution"]["enum"]) == {
        "accept-obsidian",
        "accept-vault",
        "keep-both",
    }


def test_mcp_obsidian_import_dry_run_and_compile(tmp_path):
    from vault.db import VaultDB
    from vault.mcp import _set_project_dir, handle_tool_call

    project = tmp_path / "project"
    project.mkdir()
    (project / "raw").mkdir()
    with VaultDB(str(project / "vault.db")):
        pass

    obsidian = tmp_path / "ObsidianVault"
    obsidian.mkdir()
    (obsidian / "MCP.md").write_text("# MCP Import\n\nMCP can import Obsidian notes.\n", encoding="utf-8")

    _set_project_dir(project)
    dry = json.loads(
        handle_tool_call(
            "vault_obsidian_import",
            {"vault_dir": str(obsidian), "dry_run": True},
        )["result"]
    )
    assert dry["import"]["added"] == 1
    assert not (project / "raw" / "obsidian" / "MCP.md").exists()

    applied = json.loads(
        handle_tool_call(
            "vault_obsidian_import",
            {"vault_dir": str(obsidian), "dry_run": False, "compile": True},
        )["result"]
    )
    assert applied["import"]["added"] == 1
    assert applied["compile"]["new"] == 1
    assert (project / "raw" / "obsidian" / "MCP.md").exists()

    (obsidian / "MCP.md").unlink()
    missing = json.loads(
        handle_tool_call(
            "vault_obsidian_import",
            {"vault_dir": str(obsidian), "dry_run": False},
        )["result"]
    )
    assert missing["import"]["missing"] == 1
    assert missing["import"]["deleted"] == 0
    assert (project / "raw" / "obsidian" / "MCP.md").exists()


def test_mcp_obsidian_resolve_conflict_accepts_obsidian(tmp_path):
    from vault.db import VaultDB
    from vault.mcp import _set_project_dir, handle_tool_call

    project = tmp_path / "project"
    project.mkdir()
    (project / "raw").mkdir()
    with VaultDB(str(project / "vault.db")):
        pass

    obsidian = tmp_path / "ObsidianVault"
    obsidian.mkdir()
    note = obsidian / "Shared.md"
    note.write_text("# Shared\n\nOriginal note.\n", encoding="utf-8")

    _set_project_dir(project)
    handle_tool_call(
        "vault_obsidian_import",
        {"vault_dir": str(obsidian), "dry_run": False},
    )
    raw_note = project / "raw" / "obsidian" / "Shared.md"
    raw_note.write_text(raw_note.read_text(encoding="utf-8") + "\nVault-side edit.\n", encoding="utf-8")
    note.write_text("# Shared\n\nObsidian-side edit.\n", encoding="utf-8")
    conflict = json.loads(
        handle_tool_call(
            "vault_obsidian_import",
            {"vault_dir": str(obsidian), "dry_run": False, "conflict_inbox": True},
        )["result"]
    )
    assert conflict["import"]["conflicts"] == 1

    resolved = json.loads(
        handle_tool_call(
            "vault_obsidian_resolve_conflict",
            {
                "vault_dir": str(obsidian),
                "source_path": "Shared.md",
                "resolution": "accept-obsidian",
                "conflict_inbox": True,
            },
        )["result"]
    )

    assert resolved["resolution"]["status"] == "resolved"
    assert resolved["resolution"]["resolution"] == "accept-obsidian"
    assert "Obsidian-side edit." in raw_note.read_text(encoding="utf-8")
    assert "Vault-side edit." not in raw_note.read_text(encoding="utf-8")
    assert resolved["next_action"]["tool"] == "vault_obsidian_import"
    assert resolved["resolution"]["conflict_inbox_path"].endswith("Obsidian Import Conflicts.md")
