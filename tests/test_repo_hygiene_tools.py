from __future__ import annotations

import json
from pathlib import Path

from scripts import artifact_audit, artifact_cleanup, public_pr_gate


def test_artifact_audit_classifies_safe_generated_cache(tmp_path: Path):
    pycache = tmp_path / "pkg" / "__pycache__"
    pycache.mkdir(parents=True)
    (pycache / "module.cpython-311.pyc").write_bytes(b"cache")
    pytest_cache = tmp_path / ".pytest_cache"
    pytest_cache.mkdir()
    (pytest_cache / "README.md").write_text("cache", encoding="utf-8")

    report = artifact_audit.audit_repo(tmp_path)

    safe_paths = {item["path"] for item in report["safe_delete"]}
    assert "pkg/__pycache__" in safe_paths
    assert ".pytest_cache" in safe_paths
    assert report["summary"]["safe_delete_files"] == 2
    assert report["summary"]["safe_delete_bytes"] == len(b"cache") + len("cache")


def test_artifact_audit_classifies_graphify_cache_safe_but_full_graph_review(tmp_path: Path):
    cache = tmp_path / "graphify-out" / "cache"
    cache.mkdir(parents=True)
    (cache / "ast.json").write_text("{}", encoding="utf-8")
    (tmp_path / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")

    report = artifact_audit.audit_repo(tmp_path)

    assert any(item["path"] == "graphify-out/cache" for item in report["safe_delete"])
    assert any(item["path"] == "graphify-out" for item in report["needs_review"])


def test_artifact_cleanup_dry_run_does_not_delete_and_execute_deletes_safe_only(tmp_path: Path):
    pycache = tmp_path / "pkg" / "__pycache__"
    pycache.mkdir(parents=True)
    (pycache / "module.pyc").write_bytes(b"cache")
    opencode = tmp_path / ".opencode" / "node_modules"
    opencode.mkdir(parents=True)
    (opencode / "keep.js").write_text("keep", encoding="utf-8")

    dry_run = artifact_cleanup.cleanup_repo(tmp_path, execute=False, include_large=False)
    assert pycache.exists()
    assert dry_run["summary"]["deleted_files"] == 0
    assert any(item["path"] == "pkg/__pycache__" for item in dry_run["would_delete"])
    assert any(item["path"] == ".opencode" for item in dry_run["needs_review"])

    executed = artifact_cleanup.cleanup_repo(tmp_path, execute=True, include_large=False)
    assert not pycache.exists()
    assert opencode.exists()
    assert executed["summary"]["deleted_files"] == 1


def test_artifact_cleanup_keeps_generic_build_dir_for_review(tmp_path: Path):
    build = tmp_path / "pkg" / "build"
    build.mkdir(parents=True)
    (build / "source_of_truth.py").write_text("important", encoding="utf-8")

    dry_run = artifact_cleanup.cleanup_repo(tmp_path, execute=False)
    assert not any(item["path"] == "pkg/build" for item in dry_run["would_delete"])
    assert any(item["path"] == "pkg/build" for item in dry_run["needs_review"])

    artifact_cleanup.cleanup_repo(tmp_path, execute=True)
    assert build.exists()
    assert (build / "source_of_truth.py").exists()


def test_public_pr_gate_flags_forbidden_files_and_private_added_lines():
    home_path = "/".join(["", "home", "example_user", "private"])
    channel_key = "chat" + "_id"
    channel_value = "oc_" + "123abc"
    diff = f"""diff --git a/PROGRESS.md b/PROGRESS.md
+++ b/PROGRESS.md
@@ -0,0 +1,3 @@
+Internal path {home_path}
+review channel {channel_key} {channel_value}
+normal public text
"""

    report = public_pr_gate.scan_diff(diff, target_visibility="public")

    kinds = {finding["kind"] for finding in report["findings"]}
    assert "forbidden_file" in kinds
    assert "local_path" in kinds
    assert "private_platform_context" in kinds
    assert report["passed"] is False


def test_public_pr_gate_passes_clean_public_diff():
    diff = """diff --git a/docs/example.md b/docs/example.md
+++ b/docs/example.md
@@ -0,0 +1,2 @@
+This is a public-safe example for a local review channel.
+No generic runtime or user-specific path is included.
"""

    report = public_pr_gate.scan_diff(diff, target_visibility="public")

    assert report["passed"] is True
    assert report["findings"] == []


def test_public_pr_gate_flags_deleted_private_payload_and_rename_paths():
    private_dir = "." + "hermes"
    user_path = "/".join(["", "Users", "example_user", "private", "project"])
    secret_key = "ACCESS" + "_TOKEN"
    secret_value = "example" + "_secret_value_123"
    diff = f"""diff --git a/{private_dir}/secret.md b/docs/secret.md
similarity index 100%
rename from {private_dir}/secret.md
rename to docs/secret.md
diff --git a/docs/old.md b/docs/old.md
--- a/docs/old.md
+++ b/docs/old.md
@@ -1,2 +1,2 @@
-{user_path}
-{secret_key}={secret_value}
+public replacement
"""

    report = public_pr_gate.scan_diff(diff, target_visibility="public")

    kinds = {finding["kind"] for finding in report["findings"]}
    assert "forbidden_file" in kinds
    assert "local_path" in kinds
    assert "secret_literal" in kinds
    assert report["passed"] is False


def test_public_pr_gate_flags_internal_data_dirs_worklogs_and_runtime_dbs():
    diff = """diff --git a/raw/private.md b/raw/private.md
+++ b/raw/private.md
@@ -0,0 +1 @@
+synthetic clean text
diff --git a/compiled/private.md b/compiled/private.md
+++ b/compiled/private.md
@@ -0,0 +1 @@
+synthetic clean text
diff --git a/runtime/state.sqlite b/runtime/state.sqlite
+++ b/runtime/state.sqlite
@@ -0,0 +1 @@
+synthetic clean text
diff --git a/guardrails.db b/guardrails.db
+++ b/guardrails.db
@@ -0,0 +1 @@
+synthetic clean text
diff --git a/worklogs/private.md b/worklogs/private.md
+++ b/worklogs/private.md
@@ -0,0 +1 @@
+synthetic clean text
"""

    report = public_pr_gate.scan_diff(diff, target_visibility="public")

    forbidden_paths = {finding["path"] for finding in report["findings"] if finding["kind"] == "forbidden_file"}
    assert {
        "raw/private.md",
        "compiled/private.md",
        "runtime/state.sqlite",
        "guardrails.db",
        "worklogs/private.md",
    }.issubset(forbidden_paths)
    assert report["passed"] is False


def test_public_pr_gate_flags_windows_user_paths():
    drive_user_path = "C:" + "\\" + "Users" + "\\" + "example_user" + "\\" + "private" + "\\" + "project"
    diff = f"""diff --git a/docs/path.md b/docs/path.md
+++ b/docs/path.md
@@ -0,0 +1 @@
+{drive_user_path}
"""

    report = public_pr_gate.scan_diff(diff, target_visibility="public")

    kinds = {finding["kind"] for finding in report["findings"]}
    assert "local_path" in kinds
    assert report["passed"] is False


def test_public_pr_gate_cli_json_for_stdin(monkeypatch, capsys):
    secret_key = "tok" + "en"
    secret_value = "abc" + "123456"
    monkeypatch.setattr(
        "sys.stdin",
        type("FakeStdin", (), {"read": lambda self: f"+++ b/AUDIT_REPORT.md\n+{secret_key}='{secret_value}'\n"})(),
    )

    code = public_pr_gate.main(["--stdin", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 1
    assert payload["passed"] is False
    assert {item["kind"] for item in payload["findings"]} >= {"forbidden_file", "secret_literal"}
