import json

from vault.db import VaultDB
from vault.mcp import _set_project_dir, handle_tool_call
from vault.mcp_tools import select_tools


def _payload(result):
    assert "result" in result, result
    return json.loads(result["result"])


def test_mcp_skill_registry_tools_are_profiled_and_bounded(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _set_project_dir(project)
    with VaultDB(project / "vault.db") as db:
        db.add_skill(
            name="review-helper",
            version="1.0.0",
            content_raw="Review workflow v1",
            capabilities="review,testing",
            category="engineering",
            trust=0.8,
        )
        db.add_skill(
            name="review-helper",
            version="1.1.0",
            content_raw="Review workflow v2 with improved evidence checks",
            capabilities="review,testing",
            category="engineering",
            trust=0.9,
        )

    core_names = {tool["name"] for tool in select_tools("core")}
    review_names = {tool["name"] for tool in select_tools("review")}
    maintenance_names = {tool["name"] for tool in select_tools("maintenance")}
    assert "vault_skill_search" not in core_names
    assert "vault_skill_search" in review_names
    assert "vault_skill_sync_manifest" in review_names
    assert "vault_skill_push" not in review_names
    assert "vault_skill_push" in maintenance_names

    search = _payload(handle_tool_call("vault_skill_search", {"query": "review"}))
    assert search["ok"] is True
    assert search["skills"][0]["name"] == "review-helper"
    assert "content_raw" not in search["skills"][0]

    versions = _payload(handle_tool_call("vault_skill_versions", {"name": "review-helper"}))
    assert [row["version"] for row in versions["versions"]] == ["1.1.0", "1.0.0"]

    pulled = _payload(handle_tool_call("vault_skill_pull", {"name": "review-helper", "max_chars": 1000}))
    assert pulled["skill"]["content"] == "Review workflow v2 with improved evidence checks"
    assert pulled["skill"]["truncated"] is False

    plan = _payload(handle_tool_call(
        "vault_skill_upgrade_plan",
        {"installed": {"review-helper": "1.0.0"}},
    ))
    assert plan["upgrade_count"] == 1
    assert plan["skills"][0]["latest_version"] == "1.1.0"


def test_mcp_skill_push_requires_explicit_permission_and_privacy_gate(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _set_project_dir(project)

    blocked = _payload(handle_tool_call(
        "vault_skill_push",
        {"name": "review-helper", "content": "safe content"},
    ))
    assert blocked["ok"] is False
    assert blocked["error"] == "skill_write_not_allowed"

    secret = _payload(handle_tool_call(
        "vault_skill_push",
        {
            "name": "secret-helper",
            "content": "Never store api_key = abcdefghijklmnop1234 in a Skill.",
            "allow_skill_write": True,
        },
    ))
    assert secret["ok"] is False
    assert secret["error"] == "privacy_gate_failed"

    invalid_name = _payload(handle_tool_call(
        "vault_skill_push",
        {"name": "../escape", "content": "safe content", "allow_skill_write": True},
    ))
    assert invalid_name["ok"] is False
    assert invalid_name["error"] == "invalid_skill_name"

    pushed = _payload(handle_tool_call(
        "vault_skill_push",
        {
            "name": "review-helper",
            "version": "1.0.0",
            "content": "# Review Helper\n\nUse bounded evidence before judging a PR.",
            "capabilities": "review,testing",
            "category": "engineering",
            "trust": 0.9,
            "description": "Review helper",
            "allow_skill_write": True,
        },
    ))
    assert pushed["ok"] is True
    assert pushed["status"] == "created"
    assert pushed["writes_runtime_files"] is False
    assert "content_raw" not in pushed["skill"]

    with VaultDB(project / "vault.db") as db:
        skill = db.get_skill("review-helper")
        assert skill["content_raw"].startswith("# Review Helper")


def test_mcp_skill_sync_manifest_and_mark_synced_are_gated(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _set_project_dir(project)
    with VaultDB(project / "vault.db") as db:
        db.add_skill(
            name="sync-helper",
            version="1.0.0",
            content_raw="# Sync Helper\n\nShip a compact manifest first.",
            capabilities="sync",
            category="operations",
            trust=0.7,
        )

    status = _payload(handle_tool_call("vault_skill_sync_status", {}))
    assert status["ok"] is True
    assert status["counts"]["never_synced"] == 1
    assert status["skills"][0]["sync_state"] == "never_synced"
    assert "content_raw" not in status["skills"][0]

    manifest = _payload(handle_tool_call("vault_skill_sync_manifest", {}))
    assert manifest["ok"] is True
    assert manifest["items"][0]["name"] == "sync-helper"
    assert "content" not in manifest["items"][0]

    denied_manifest = _payload(handle_tool_call(
        "vault_skill_sync_manifest",
        {"include_content": True},
    ))
    assert denied_manifest["ok"] is False
    assert denied_manifest["error"] == "skill_content_export_not_allowed"

    content_manifest = _payload(handle_tool_call(
        "vault_skill_sync_manifest",
        {"include_content": True, "allow_skill_content_export": True},
    ))
    assert content_manifest["ok"] is True
    assert content_manifest["items"][0]["content"].startswith("# Sync Helper")

    denied_mark = _payload(handle_tool_call(
        "vault_skill_mark_synced",
        {"name": "sync-helper"},
    ))
    assert denied_mark["ok"] is False
    assert denied_mark["error"] == "skill_sync_mark_not_allowed"

    marked = _payload(handle_tool_call(
        "vault_skill_mark_synced",
        {"name": "sync-helper", "allow_skill_sync_mark": True},
    ))
    assert marked["ok"] is True
    assert marked["sync_state"] == "synced"

    final_status = _payload(handle_tool_call("vault_skill_sync_status", {"include_synced": True}))
    assert final_status["counts"]["synced"] == 1
    assert final_status["skills"][0]["sync_state"] == "synced"
