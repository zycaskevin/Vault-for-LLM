from argparse import Namespace


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
