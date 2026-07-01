import os
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from vault.db import VaultDB
from vault.export_obsidian import export_obsidian_review_inbox, export_obsidian_vault, slugify_filename


REPO_ROOT = Path(__file__).parent.parent


def _run_cli(project_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{REPO_ROOT}{os.pathsep}{env.get('PYTHONPATH', '')}"
    return subprocess.run(
        [sys.executable, "-m", "vault.cli", *args],
        cwd=project_dir,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _make_vault_db(path: Path) -> list[int]:
    with VaultDB(path) as db:
        first = db.add_knowledge(
            title="Vault Document Map Example",
            content_raw="# Vault Document Map Example\n\nTool-gated reading keeps long entries bounded.",
            layer="L3",
            category="technique",
            tags="vault, document-map",
            trust=0.8,
            source="unit-test",
            summary="Tool-gated reading keeps long entries bounded.",
        )
        second = db.add_knowledge(
            title='Bad / Name: "Quoted"?',
            content_raw="Unsafe filenames should still export safely.",
            layer="L3",
            category="error",
            tags='["vault", "filenames"]',
            trust=0.7,
            source="unit-test",
        )
        third = db.add_knowledge(
            title="Private Draft",
            content_raw="Draft body should be filterable.",
            layer="L2",
            category="general",
            tags="draft",
            trust=0.4,
            source="unit-test",
        )
        fourth = db.add_knowledge(
            title="Low Trust Entry",
            content_raw="Low trust body.",
            layer="L3",
            category="technique",
            tags="vault, low-trust",
            trust=0.2,
            source="unit-test",
        )
    return [first, second, third, fourth]


def _knowledge_snapshot(db_path: Path) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            """
            SELECT id, title, layer, category, tags, trust, content_raw,
                   content_aaak, source, summary, created_at, updated_at
            FROM knowledge
            ORDER BY id
            """
        ).fetchall()
    finally:
        conn.close()


def test_slugify_filename_is_stable_and_path_safe():
    assert slugify_filename('Bad / Name: "Quoted"?') == "Bad-Name-Quoted"
    assert slugify_filename("...///...") == "untitled"
    assert slugify_filename("中文 標題") == "中文-標題"


def test_export_obsidian_writes_idempotent_markdown_with_frontmatter(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _make_vault_db(project_dir / "vault.db")

    vault_dir = tmp_path / "ObsidianVault"
    result = export_obsidian_vault(
        project_dir=project_dir,
        vault_dir=vault_dir,
        category="technique",
        tag="document-map",
    )

    assert result["written"] == 1
    assert result["matched"] == 1
    assert result["dry_run"] is False
    note = vault_dir / "00-Vault-Knowledge" / "technique" / "0001-Vault-Document-Map-Example.md"
    assert note.exists()

    content = note.read_text(encoding="utf-8")
    assert "vault_id: 1" in content
    assert 'title: "Vault Document Map Example"' in content
    assert 'category: "technique"' in content
    assert 'tags: ["vault", "document-map"]' in content
    assert 'layer: "L3"' in content
    assert "trust: 0.8" in content
    assert "# Vault Document Map Example" in content
    assert "## Citation\n\nVault #1" in content

    # Running again overwrites the same path rather than creating duplicates.
    second = export_obsidian_vault(project_dir=project_dir, vault_dir=vault_dir, category="technique", tag="document-map")
    assert second["written"] == 1
    assert len(list((vault_dir / "00-Vault-Knowledge" / "technique").glob("*.md"))) == 1


def test_export_obsidian_filters_layer_min_trust_and_limit_in_id_order(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _make_vault_db(project_dir / "vault.db")

    result = export_obsidian_vault(
        project_dir=project_dir,
        vault_dir=tmp_path / "ObsidianVault",
        layer="L3",
        min_trust=0.3,
        limit=2,
    )

    assert result["matched"] == 2
    assert [Path(path).name for path in result["paths"]] == [
        "0001-Vault-Document-Map-Example.md",
        "0002-Bad-Name-Quoted.md",
    ]
    assert (tmp_path / "ObsidianVault" / "00-Vault-Knowledge" / "technique" / "0001-Vault-Document-Map-Example.md").exists()
    assert (tmp_path / "ObsidianVault" / "00-Vault-Knowledge" / "error" / "0002-Bad-Name-Quoted.md").exists()
    assert not (tmp_path / "ObsidianVault" / "00-Vault-Knowledge" / "general" / "0003-Private-Draft.md").exists()
    assert not (tmp_path / "ObsidianVault" / "00-Vault-Knowledge" / "technique" / "0004-Low-Trust-Entry.md").exists()


def test_export_obsidian_parses_json_tags_and_adds_heading_for_plain_body(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _make_vault_db(project_dir / "vault.db")

    result = export_obsidian_vault(
        project_dir=project_dir,
        vault_dir=tmp_path / "ObsidianVault",
        tag="filenames",
    )

    assert result["matched"] == 1
    note_path = Path(result["paths"][0])
    content = note_path.read_text(encoding="utf-8")
    assert note_path.name == "0002-Bad-Name-Quoted.md"
    assert 'tags: ["vault", "filenames"]' in content
    assert '# Bad / Name: "Quoted"?' in content
    assert "Unsafe filenames should still export safely." in content


def test_export_obsidian_dry_run_does_not_write_files_or_mutate_db(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    db_path = project_dir / "vault.db"
    _make_vault_db(db_path)
    before = _knowledge_snapshot(db_path)

    vault_dir = tmp_path / "ObsidianVault"
    result = export_obsidian_vault(project_dir=project_dir, vault_dir=vault_dir, dry_run=True, limit=1)

    assert result["matched"] == 1
    assert result["written"] == 0
    assert result["dry_run"] is True
    assert not vault_dir.exists()
    assert _knowledge_snapshot(db_path) == before


def test_export_obsidian_actual_write_does_not_mutate_db(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    db_path = project_dir / "vault.db"
    _make_vault_db(db_path)
    before = _knowledge_snapshot(db_path)

    result = export_obsidian_vault(project_dir=project_dir, vault_dir=tmp_path / "ObsidianVault")

    assert result["matched"] == 4
    assert result["written"] == 4
    assert _knowledge_snapshot(db_path) == before


def test_export_obsidian_review_inbox_writes_daily_candidates_and_sync_status(tmp_path):
    from vault.memory import create_candidate
    from vault.multi_host import detect_candidate_conflicts, record_memory_revision

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    db_path = project_dir / "vault.db"
    _make_vault_db(db_path)
    with VaultDB(db_path) as db:
        candidate = create_candidate(
            db,
            title="Review candidate memory",
            content="Agent should review candidate memories before promotion because it protects source quality.",
            tags="review,agent",
            reason="Show this in the Obsidian review inbox.",
            source="unit-test",
            source_ref="tests",
            scope="shared",
            sensitivity="low",
        )
        conflict_candidate = create_candidate(
            db,
            title="Vault Document Map Example",
            content="Remote content should not appear in the generated sync status list.",
            tags="remote,sync",
            reason="Remote sync conflict for Obsidian inbox.",
            source="remote_candidate_sync",
            source_ref="supabase:test",
            scope="shared",
            sensitivity="low",
        )
        revision = record_memory_revision(
            db,
            title="Vault Document Map Example",
            content="Remote content should not appear in the generated sync status list.",
            operation="remote_candidate_imported",
            status="candidate_created",
            candidate_id=conflict_candidate["candidate_id"],
            remote_request_id="obsidian-inbox-conflict",
            source_agent="remote-agent",
        )
        detect_candidate_conflicts(db, candidate_id=conflict_candidate["candidate_id"], revision_id=revision["revision_id"])

    manifest_dir = project_dir / ".vault"
    manifest_dir.mkdir()
    (manifest_dir / "obsidian-import-manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "vault_dir": str(tmp_path / "ObsidianVault"),
                "raw_subdir": "obsidian",
                "folder_rules_count": 1,
                "notes": {
                    "Projects/Active.md": {
                        "status": "active",
                        "raw_path": "raw/obsidian/Projects/Active.md",
                        "folder_rule": "Projects/**",
                    },
                    "Loose.md": {
                        "status": "active",
                        "raw_path": "raw/obsidian/Loose.md",
                    },
                    "Missing.md": {
                        "status": "missing",
                        "raw_path": "raw/obsidian/Missing.md",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    vault_dir = tmp_path / "ObsidianVault"
    result = export_obsidian_review_inbox(project_dir=project_dir, vault_dir=vault_dir)

    assert result["written"] == 4
    assert result["candidate_count"] == 2
    assert result["missing_count"] == 1
    assert result["sync_status"] == "needs_review"
    assert result["sync_conflict_count"] == 1

    daily = vault_dir / "00-Vault-Knowledge" / "_Inbox" / "Daily Memory Report.md"
    candidates = vault_dir / "00-Vault-Knowledge" / "_Inbox" / "Memory Candidates.md"
    sync = vault_dir / "00-Vault-Knowledge" / "_Inbox" / "Sync Status.md"
    rules = vault_dir / "00-Vault-Knowledge" / "_Inbox" / "Folder Rules Preview.md"
    assert daily.exists()
    assert candidates.exists()
    assert sync.exists()
    assert rules.exists()
    assert "Pending memory candidates: **2**" in daily.read_text(encoding="utf-8")
    assert "Open remote sync conflicts: **1**" in daily.read_text(encoding="utf-8")
    candidate_text = candidates.read_text(encoding="utf-8")
    assert "Review candidate memory" in candidate_text
    assert candidate["candidate_id"] in candidate_text
    sync_text = sync.read_text(encoding="utf-8")
    assert "`Missing.md`" in sync_text
    assert "Folder rules: **1**" in sync_text
    assert "Folder-rule unmatched active notes: **1**" in sync_text
    assert "Remote Candidate Sync" in sync_text
    assert "Open conflicts: **1**" in sync_text
    assert "same_title_content_mismatch" in sync_text
    assert "Remote content should not appear" not in sync_text
    rules_text = rules.read_text(encoding="utf-8")
    assert "**Projects/**" in rules_text
    assert "`Projects/Active.md`" in rules_text
    assert "No folder rule matched" in rules_text
    assert "`Loose.md`" in rules_text


def test_export_obsidian_can_include_review_inbox(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _make_vault_db(project_dir / "vault.db")
    vault_dir = tmp_path / "ObsidianVault"

    result = export_obsidian_vault(
        project_dir=project_dir,
        vault_dir=vault_dir,
        category="technique",
        tag="document-map",
        include_review_inbox=True,
    )

    assert result["matched"] == 1
    assert result["review_inbox"]["written"] == 4
    assert (vault_dir / "00-Vault-Knowledge" / "technique" / "0001-Vault-Document-Map-Example.md").exists()
    assert (vault_dir / "00-Vault-Knowledge" / "_Inbox" / "Daily Memory Report.md").exists()


def test_export_obsidian_rejects_unsupported_sources(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _make_vault_db(project_dir / "vault.db")

    with pytest.raises(ValueError, match="supports --source db only"):
        export_obsidian_vault(project_dir=project_dir, vault_dir=tmp_path / "ObsidianVault", source="raw")


def test_export_obsidian_reports_missing_db(tmp_path):
    with pytest.raises(FileNotFoundError, match="vault.db not found"):
        export_obsidian_vault(project_dir=tmp_path / "project", vault_dir=tmp_path / "ObsidianVault")


def test_export_obsidian_cli_supports_dry_run(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _make_vault_db(project_dir / "vault.db")
    vault_dir = tmp_path / "ObsidianVault"

    result = _run_cli(
        project_dir,
        "export",
        "obsidian",
        "--vault",
        str(vault_dir),
        "--category",
        "technique",
        "--tag",
        "document-map",
        "--dry-run",
    )

    assert result.returncode == 0, result.stderr
    assert "Obsidian export" in result.stdout
    assert "matched=1" in result.stdout
    assert "written=0" in result.stdout
    assert "dry_run=True" in result.stdout
    assert not vault_dir.exists()


def test_export_obsidian_cli_writes_notes(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _make_vault_db(project_dir / "vault.db")
    vault_dir = tmp_path / "ObsidianVault"

    result = _run_cli(
        project_dir,
        "export",
        "obsidian",
        "--vault",
        str(vault_dir),
        "--layer",
        "L3",
        "--min-trust",
        "0.3",
    )

    assert result.returncode == 0, result.stderr
    assert "matched=2" in result.stdout
    assert "written=2" in result.stdout
    assert (vault_dir / "00-Vault-Knowledge" / "technique" / "0001-Vault-Document-Map-Example.md").exists()
    assert (vault_dir / "00-Vault-Knowledge" / "error" / "0002-Bad-Name-Quoted.md").exists()


def test_export_obsidian_cli_rejects_unsupported_source_without_traceback(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _make_vault_db(project_dir / "vault.db")
    vault_dir = tmp_path / "ObsidianVault"

    result = _run_cli(
        project_dir,
        "export",
        "obsidian",
        "--vault",
        str(vault_dir),
        "--source",
        "raw",
    )

    assert result.returncode == 2
    assert "supports --source db only" in result.stderr
    assert "Traceback" not in result.stderr
    assert not vault_dir.exists()


def test_export_obsidian_cli_reports_missing_db_without_traceback(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    vault_dir = tmp_path / "ObsidianVault"

    result = _run_cli(project_dir, "export", "obsidian", "--vault", str(vault_dir))

    assert result.returncode == 2
    assert "vault.db not found" in result.stderr
    assert "Traceback" not in result.stderr
    assert not vault_dir.exists()
