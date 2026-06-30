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
    assert "vault_skill_search" not in core_names
    assert "vault_skill_search" in review_names

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
