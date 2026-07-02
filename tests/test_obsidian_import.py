from argparse import Namespace
import json
from pathlib import Path


def test_sync_obsidian_vault_imports_notes_idempotently(tmp_path):
    from vault.import_obsidian import sync_obsidian_vault

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    obsidian = tmp_path / "ObsidianVault"
    obsidian.mkdir()
    (obsidian / ".obsidian").mkdir()
    (obsidian / "00-Vault-Knowledge").mkdir()
    (obsidian / "Projects").mkdir()

    (obsidian / "Projects" / "Decision.md").write_text(
        "---\n"
        "tags: [architecture, api]\n"
        "aliases: [ADR one]\n"
        "scope: shared\n"
        "sensitivity: medium\n"
        "owner_agent: profile-agent\n"
        "allowed_agents: [work-agent, product-agent]\n"
        "memory_type: decision\n"
        "---\n"
        "# API Decision\n\n"
        "Use bounded reads before final citations.\n",
        encoding="utf-8",
    )
    (obsidian / ".obsidian" / "workspace.md").write_text("Ignore me", encoding="utf-8")
    (obsidian / "00-Vault-Knowledge" / "exported.md").write_text("Ignore generated export", encoding="utf-8")

    dry = sync_obsidian_vault(project_dir=project_dir, vault_dir=obsidian, dry_run=True)
    assert dry["added"] == 1
    assert dry["ignored"] == 2
    assert not (project_dir / "raw").exists()

    first = sync_obsidian_vault(project_dir=project_dir, vault_dir=obsidian)
    assert first["added"] == 1
    assert first["updated"] == 0
    assert first["skipped"] == 0
    assert first["missing"] == 0
    assert first["deleted"] == 0
    manifest_path = project_dir / ".vault" / "obsidian-import-manifest.json"
    assert first["manifest_path"] == str(manifest_path)
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["notes"]["Projects/Decision.md"]["status"] == "active"

    imported = project_dir / "raw" / "obsidian" / "Projects" / "Decision.md"
    assert imported.exists()
    content = imported.read_text(encoding="utf-8")
    assert "imported_from: obsidian" in content
    assert "obsidian_source_path: Projects/Decision.md" in content
    assert "scope: shared" in content
    assert "sensitivity: medium" in content
    assert "owner_agent: profile-agent" in content
    assert "allowed_agents:" in content
    assert "- work-agent" in content
    assert "- product-agent" in content
    assert "memory_type: decision" in content
    assert "API Decision" in content
    assert "architecture" in content
    assert "00-Vault-Knowledge" not in "\n".join(first["paths"])

    second = sync_obsidian_vault(project_dir=project_dir, vault_dir=obsidian)
    assert second["added"] == 0
    assert second["updated"] == 0
    assert second["skipped"] == 1

    (obsidian / "Projects" / "Decision.md").write_text(
        "# API Decision\n\nUse bounded reads and cite exact source lines.\n",
        encoding="utf-8",
    )
    third = sync_obsidian_vault(project_dir=project_dir, vault_dir=obsidian)
    assert third["added"] == 0
    assert third["updated"] == 1


def test_sync_obsidian_vault_marks_and_prunes_missing_notes(tmp_path):
    from vault.import_obsidian import sync_obsidian_vault

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    obsidian = tmp_path / "ObsidianVault"
    obsidian.mkdir()
    note = obsidian / "DeletedLater.md"
    note.write_text("# Deleted Later\n\nThis note will move away.\n", encoding="utf-8")

    first = sync_obsidian_vault(project_dir=project_dir, vault_dir=obsidian)
    assert first["added"] == 1
    raw_note = project_dir / "raw" / "obsidian" / "DeletedLater.md"
    assert raw_note.exists()

    note.unlink()
    second = sync_obsidian_vault(project_dir=project_dir, vault_dir=obsidian)
    assert second["missing"] == 1
    assert second["deleted"] == 0
    assert raw_note.exists()
    manifest = json.loads((project_dir / ".vault" / "obsidian-import-manifest.json").read_text(encoding="utf-8"))
    assert manifest["notes"]["DeletedLater.md"]["status"] == "missing"

    third = sync_obsidian_vault(project_dir=project_dir, vault_dir=obsidian, prune_missing=True)
    assert third["missing"] == 1
    assert third["deleted"] == 1
    assert not raw_note.exists()
    manifest = json.loads((project_dir / ".vault" / "obsidian-import-manifest.json").read_text(encoding="utf-8"))
    assert "DeletedLater.md" not in manifest["notes"]


def test_sync_obsidian_vault_detects_two_sided_conflict_without_overwrite(tmp_path):
    from vault.import_obsidian import sync_obsidian_vault

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    obsidian = tmp_path / "ObsidianVault"
    obsidian.mkdir()
    note = obsidian / "Shared.md"
    note.write_text("# Shared\n\nOriginal note.\n", encoding="utf-8")

    first = sync_obsidian_vault(project_dir=project_dir, vault_dir=obsidian)
    assert first["added"] == 1
    raw_note = project_dir / "raw" / "obsidian" / "Shared.md"
    original_raw = raw_note.read_text(encoding="utf-8")

    raw_note.write_text(original_raw + "\nVault-side edit.\n", encoding="utf-8")
    note.write_text("# Shared\n\nObsidian-side edit.\n", encoding="utf-8")

    second = sync_obsidian_vault(project_dir=project_dir, vault_dir=obsidian)
    assert second["conflicts"] == 1
    assert second["updated"] == 0
    assert second["conflict_items"][0]["source_path"] == "Shared.md"
    assert "Vault-side edit." in raw_note.read_text(encoding="utf-8")
    assert "Obsidian-side edit." not in raw_note.read_text(encoding="utf-8")

    manifest = json.loads((project_dir / ".vault" / "obsidian-import-manifest.json").read_text(encoding="utf-8"))
    entry = manifest["notes"]["Shared.md"]
    assert entry["status"] == "conflict"
    assert entry["pending_source_hash"] == second["conflict_items"][0]["current_source_hash"]


def test_sync_obsidian_vault_writes_conflict_inbox_note(tmp_path):
    from vault.import_obsidian import sync_obsidian_vault

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    obsidian = tmp_path / "ObsidianVault"
    obsidian.mkdir()
    note = obsidian / "Shared.md"
    note.write_text("# Shared\n\nOriginal note.\n", encoding="utf-8")

    sync_obsidian_vault(project_dir=project_dir, vault_dir=obsidian)
    raw_note = project_dir / "raw" / "obsidian" / "Shared.md"
    raw_note.write_text(raw_note.read_text(encoding="utf-8") + "\nVault-side edit.\n", encoding="utf-8")
    note.write_text("# Shared\n\nObsidian-side edit.\n", encoding="utf-8")

    result = sync_obsidian_vault(project_dir=project_dir, vault_dir=obsidian, conflict_inbox=True)

    assert result["conflicts"] == 1
    inbox_path = obsidian / "00-Vault-Knowledge" / "_Inbox" / "Obsidian Import Conflicts.md"
    assert result["conflict_inbox_path"] == str(inbox_path)
    text = inbox_path.read_text(encoding="utf-8")
    assert "Vault 每日筆記審核" in text
    assert "**Shared.md**" in text
    assert "接受 Obsidian" in text
    assert "接受 Vault" in text
    assert "保留兩份" in text
    assert "Vault 沒有偷偷覆蓋任何一邊" in text
    assert "Obsidian-side edit." not in text
    assert "Vault-side edit." not in text


def _make_obsidian_conflict(tmp_path):
    from vault.import_obsidian import sync_obsidian_vault

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    obsidian = tmp_path / "ObsidianVault"
    obsidian.mkdir()
    note = obsidian / "Shared.md"
    note.write_text("# Shared\n\nOriginal note.\n", encoding="utf-8")
    sync_obsidian_vault(project_dir=project_dir, vault_dir=obsidian)
    raw_note = project_dir / "raw" / "obsidian" / "Shared.md"
    raw_note.write_text(raw_note.read_text(encoding="utf-8") + "\nVault-side edit.\n", encoding="utf-8")
    note.write_text("# Shared\n\nObsidian-side edit.\n", encoding="utf-8")
    sync_obsidian_vault(project_dir=project_dir, vault_dir=obsidian, conflict_inbox=True)
    return project_dir, obsidian, note, raw_note


def test_resolve_obsidian_conflict_accepts_obsidian_into_vault_raw(tmp_path):
    from vault.import_obsidian import resolve_obsidian_conflict

    project_dir, obsidian, _note, raw_note = _make_obsidian_conflict(tmp_path)

    result = resolve_obsidian_conflict(
        project_dir=project_dir,
        vault_dir=obsidian,
        source_path="Shared.md",
        resolution="accept-obsidian",
    )

    assert result["status"] == "resolved"
    text = raw_note.read_text(encoding="utf-8")
    assert "Obsidian-side edit." in text
    assert "Vault-side edit." not in text
    manifest = json.loads((project_dir / ".vault" / "obsidian-import-manifest.json").read_text(encoding="utf-8"))
    assert manifest["notes"]["Shared.md"]["status"] == "active"


def test_resolve_obsidian_conflict_accepts_vault_into_obsidian_note(tmp_path):
    from vault.import_obsidian import resolve_obsidian_conflict

    project_dir, obsidian, note, raw_note = _make_obsidian_conflict(tmp_path)

    result = resolve_obsidian_conflict(
        project_dir=project_dir,
        vault_dir=obsidian,
        source_path="Shared.md",
        resolution="accept-vault",
    )

    assert result["status"] == "resolved"
    assert "Vault-side edit." in note.read_text(encoding="utf-8")
    assert "Obsidian-side edit." not in note.read_text(encoding="utf-8")
    assert "Vault-side edit." in raw_note.read_text(encoding="utf-8")
    manifest = json.loads((project_dir / ".vault" / "obsidian-import-manifest.json").read_text(encoding="utf-8"))
    assert manifest["notes"]["Shared.md"]["status"] == "active"


def test_resolve_obsidian_conflict_keep_both_copies_vault_side(tmp_path):
    from vault.import_obsidian import resolve_obsidian_conflict

    project_dir, obsidian, _note, raw_note = _make_obsidian_conflict(tmp_path)

    result = resolve_obsidian_conflict(
        project_dir=project_dir,
        vault_dir=obsidian,
        source_path="Shared.md",
        resolution="keep-both",
    )

    text = raw_note.read_text(encoding="utf-8")
    assert "Obsidian-side edit." in text
    assert "Vault-side edit." not in text
    copy_path = Path(result["vault_copy_path"])
    assert copy_path.exists()
    assert "Vault-side edit." in copy_path.read_text(encoding="utf-8")
    manifest = json.loads((project_dir / ".vault" / "obsidian-import-manifest.json").read_text(encoding="utf-8"))
    assert manifest["notes"]["Shared.md"]["status"] == "active"


def test_cmd_import_obsidian_resolve_conflict_json(tmp_path, monkeypatch, capsys):
    from vault.cli import cmd_import

    project_dir, obsidian, _note, _raw_note = _make_obsidian_conflict(tmp_path)
    monkeypatch.chdir(project_dir)
    args = Namespace(
        file="obsidian",
        vault=str(obsidian),
        resolve_conflict="Shared.md",
        resolution="accept-obsidian",
        category="general",
        tags="agent",
        layer="L3",
        trust=0.5,
        obsidian_raw_subdir="obsidian",
        obsidian_rules=None,
        exclude=[],
        prune_missing=False,
        watch=False,
        watch_interval=5.0,
        watch_iterations=0,
        conflict_inbox=True,
        dry_run=False,
        compile=False,
        no_embed=True,
        allow_private=False,
        json=True,
        pretty=False,
    )

    cmd_import(args)
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["status"] == "resolved"
    assert payload["resolution"]["source_path"] == "Shared.md"
    assert payload["resolution"]["resolution"] == "accept-obsidian"
    assert payload["resolution"]["conflict_inbox_path"].endswith("Obsidian Import Conflicts.md")


def test_sync_obsidian_vault_applies_folder_rules_and_wikilinks(tmp_path):
    from vault.import_obsidian import sync_obsidian_vault

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".vault").mkdir()
    (project_dir / ".vault" / "obsidian-folder-rules.yaml").write_text(
        "rules:\n"
        "  - pattern: 'Personal/**'\n"
        "    scope: private\n"
        "    sensitivity: high\n"
        "    category: profile\n"
        "    tags: [personal, profile]\n"
        "  - pattern: 'Public/**'\n"
        "    scope: public\n"
        "    sensitivity: low\n",
        encoding="utf-8",
    )

    obsidian = tmp_path / "ObsidianVault"
    (obsidian / "Personal").mkdir(parents=True)
    (obsidian / "Personal" / "Arthur.md").write_text(
        "---\n"
        "scope: public\n"
        "sensitivity: low\n"
        "---\n"
        "# Arthur\n\n"
        "Connect this profile to [[Daily Report]] and [[Projects/Vault|Vault]].\n"
        "![[Ignored Embed]]\n",
        encoding="utf-8",
    )

    result = sync_obsidian_vault(project_dir=project_dir, vault_dir=obsidian)
    assert result["added"] == 1

    imported = project_dir / "raw" / "obsidian" / "Personal" / "Arthur.md"
    content = imported.read_text(encoding="utf-8")
    assert "scope: private" in content
    assert "sensitivity: high" in content
    assert "category: profile" in content
    assert "- personal" in content
    assert "- profile" in content
    assert "obsidian_folder_rule: Personal/**" in content
    assert "obsidian_links:" in content
    assert "- Daily Report" in content
    assert "- Projects/Vault" in content
    assert "Ignored Embed" not in content.split("obsidian_links:", 1)[1].split("---", 1)[0]

    manifest = json.loads((project_dir / ".vault" / "obsidian-import-manifest.json").read_text(encoding="utf-8"))
    assert manifest["folder_rules_count"] == 2
    assert manifest["notes"]["Personal/Arthur.md"]["folder_rule"] == "Personal/**"


def test_cmd_import_obsidian_compile_writes_vault_db(tmp_path, monkeypatch, capsys):
    from vault.cli import cmd_import
    from vault.db import VaultDB

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    with VaultDB(str(project_dir / "vault.db")):
        pass

    obsidian = tmp_path / "ObsidianVault"
    obsidian.mkdir()
    (obsidian / "Runbook.md").write_text(
        "# Deploy Runbook\n\nRun smoke tests before release.\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(project_dir)
    args = Namespace(
        file="obsidian",
        vault=str(obsidian),
        category="runbook",
        tags="ops",
        layer="L3",
        trust=0.8,
        obsidian_raw_subdir="obsidian",
        exclude=[],
        prune_missing=False,
        dry_run=False,
        compile=True,
        no_embed=True,
        allow_private=False,
    )
    cmd_import(args)
    captured = capsys.readouterr()

    assert "Obsidian 匯入結果" in captured.out
    assert "編譯結果" in captured.out

    with VaultDB(str(project_dir / "vault.db")) as db:
        row = db.conn.execute(
            "SELECT title, category, tags, source FROM knowledge WHERE title = ?",
            ("Deploy Runbook",),
        ).fetchone()

    assert row is not None
    assert row["category"] == "runbook"
    assert row["tags"] == "ops,obsidian"
    assert row["source"] == "obsidian/Runbook.md"


def test_cmd_import_obsidian_watch_updates_changed_notes(tmp_path, monkeypatch, capsys):
    from vault import cli_content
    from vault.cli import cmd_import

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    obsidian = tmp_path / "ObsidianVault"
    obsidian.mkdir()
    note = obsidian / "Watch.md"
    note.write_text("# Watch\n\nFirst version.\n", encoding="utf-8")

    sleep_calls = 0

    def fake_sleep(_seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        note.write_text("# Watch\n\nSecond version.\n", encoding="utf-8")

    monkeypatch.setattr(cli_content.time, "sleep", fake_sleep)
    monkeypatch.chdir(project_dir)
    args = Namespace(
        file="obsidian",
        vault=str(obsidian),
        category="notes",
        tags="watch",
        layer="L3",
        trust=0.7,
        obsidian_raw_subdir="obsidian",
        exclude=[],
        prune_missing=False,
        watch=True,
        watch_interval=0.2,
        watch_iterations=2,
        dry_run=False,
        compile=False,
        no_embed=True,
        allow_private=False,
        json=True,
        pretty=False,
        obsidian_rules=None,
    )

    cmd_import(args)
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is True
    assert payload["watch"]["iterations"] == 2
    assert payload["cycles"][0]["import"]["added"] == 1
    assert payload["cycles"][1]["import"]["updated"] == 1
    assert sleep_calls == 1
    raw_note = project_dir / "raw" / "obsidian" / "Watch.md"
    assert "Second version." in raw_note.read_text(encoding="utf-8")


def test_obsidian_wikilinks_build_graph_edges(tmp_path):
    from vault.compiler import VaultCompiler
    from vault.db import VaultDB
    from vault.graph import VaultGraph
    from vault.import_obsidian import sync_obsidian_vault

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    obsidian = tmp_path / "ObsidianVault"
    obsidian.mkdir()
    (obsidian / "Daily Report.md").write_text(
        "# Daily Report\n\nReview candidate memories.\n",
        encoding="utf-8",
    )
    (obsidian / "Project Plan.md").write_text(
        "# Project Plan\n\nSee [[Daily Report]] before promoting candidates.\n",
        encoding="utf-8",
    )

    sync_obsidian_vault(project_dir=project_dir, vault_dir=obsidian)
    with VaultDB(str(project_dir / "vault.db")) as db:
        compiler = VaultCompiler(project_dir, db=db, embed_provider=None)
        compiler.compile()
        result = VaultGraph(db).infer_all()

        assert result["obsidian_edges_created"] == 1
        edge = db.conn.execute(
            "SELECT e.relation, s.title AS source_title, t.title AS target_title "
            "FROM edges e "
            "JOIN knowledge s ON s.id = e.source_id "
            "JOIN knowledge t ON t.id = e.target_id "
            "WHERE e.relation = ?",
            ("obsidian_link",),
        ).fetchone()

    assert edge is not None
    assert edge["source_title"] == "Project Plan"
    assert edge["target_title"] == "Daily Report"


def test_cmd_import_obsidian_json_output_is_machine_readable(tmp_path, monkeypatch, capsys):
    from vault.cli import cmd_import

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    obsidian = tmp_path / "ObsidianVault"
    obsidian.mkdir()
    (obsidian / "Agent.md").write_text("# Agent\n\nShared setup note.\n", encoding="utf-8")

    monkeypatch.chdir(project_dir)
    args = Namespace(
        file="obsidian",
        vault=str(obsidian),
        category="general",
        tags="agent",
        layer="L2",
        trust=0.8,
        obsidian_raw_subdir="obsidian",
        exclude=[],
        prune_missing=False,
        dry_run=False,
        compile=False,
        no_embed=True,
        allow_private=False,
        json=True,
        pretty=False,
    )

    cmd_import(args)
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["status"] == "ok"
    assert payload["import"]["added"] == 1
    assert payload["import"]["manifest_path"]
