import json


def test_mcp_obsidian_import_is_maintenance_not_core():
    from vault.mcp import select_tools

    core_names = {tool["name"] for tool in select_tools("core")}
    maintenance = select_tools("maintenance")
    maintenance_names = {tool["name"] for tool in maintenance}

    assert "vault_obsidian_import" not in core_names
    assert "vault_obsidian_import" in maintenance_names
    import_tool = next(tool for tool in maintenance if tool["name"] == "vault_obsidian_import")
    assert import_tool["inputSchema"]["properties"]["prune_missing"]["default"] is False


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
