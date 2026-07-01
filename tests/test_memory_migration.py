import json

from vault.db import VaultDB
from vault.memory_migration import migrate_memory_source


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_memory_migration_markdown_preview_does_not_write_candidates(tmp_path):
    source = tmp_path / "notes"
    _write(
        source / "decision.md",
        """---
title: Use a shared project vault
tags: [agent, memory]
---

We decided to use a shared project vault because several agents need the same project facts.
""",
    )

    with VaultDB(tmp_path / "vault.db") as db:
        payload = migrate_memory_source(db, source, dry_run=True)
        candidates = db.list_memory_candidates(status=None)
        active_count = db.conn.execute("SELECT count(*) AS count FROM knowledge").fetchone()["count"]

    assert payload["status"] == "preview"
    assert payload["item_count"] == 1
    assert payload["candidate_count"] == 1
    assert payload["safety"]["candidate_first"] is True
    assert payload["safety"]["writes_active_knowledge"] is False
    assert candidates == []
    assert active_count == 0


def test_memory_migration_json_write_creates_candidates_only(tmp_path):
    source = tmp_path / "chatbox-export.json"
    source.write_text(
        json.dumps(
            [
                {
                    "title": "Keep Task Ledger separate",
                    "content": "Decision: keep Task Ledger separate from long-term memory because it is task runtime state.",
                    "source_system": "chatbox",
                    "tags": ["task-ledger", "decision"],
                    "confidence": 0.8,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with VaultDB(tmp_path / "vault.db") as db:
        payload = migrate_memory_source(db, source, dry_run=False, scope="shared")
        candidates = db.list_memory_candidates(status=None)
        active_count = db.conn.execute("SELECT count(*) AS count FROM knowledge").fetchone()["count"]

    assert payload["status"] == "ok"
    assert payload["created_count"] == 1
    assert len(candidates) == 1
    assert candidates[0]["source"] == "migration:chatbox"
    assert candidates[0]["status"] == "candidate"
    assert candidates[0]["scope"] == "shared"
    assert active_count == 0


def test_memory_migration_privacy_gate_rejects_secret_candidate(tmp_path):
    source = tmp_path / "secret.md"
    source.write_text("Never store this api_key=" + ("A" * 24), encoding="utf-8")

    with VaultDB(tmp_path / "vault.db") as db:
        payload = migrate_memory_source(db, source, dry_run=False)
        candidates = db.list_memory_candidates(status=None)
        active_count = db.conn.execute("SELECT count(*) AS count FROM knowledge").fetchone()["count"]

    assert payload["status"] == "ok"
    assert payload["created_count"] == 0
    assert payload["rejected_count"] == 1
    assert payload["privacy_fail"] == 1
    assert len(candidates) == 1
    assert candidates[0]["status"] == "rejected"
    assert candidates[0]["privacy_status"] == "fail"
    assert active_count == 0


def test_memory_migration_cli_json_preview_is_candidate_first(tmp_path, capsys):
    from vault.cli import main

    project = tmp_path / "project"
    source = tmp_path / "memory.json"
    source.write_text(
        json.dumps(
            {
                "memories": [
                    {
                        "title": "Prefer bounded reads",
                        "content": "Preference: agents should use bounded reads because citations stay traceable.",
                        "source_system": "chatgpt",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    main(["init", "--project-dir", str(project)])
    capsys.readouterr()
    main(["import", "memory", "--source", str(source), "--project-dir", str(project), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "preview"
    assert payload["dry_run"] is True
    assert payload["created_count"] == 0
    with VaultDB(project / "vault.db") as db:
        assert db.list_memory_candidates(status=None) == []
        active_count = db.conn.execute("SELECT count(*) AS count FROM knowledge").fetchone()["count"]
    assert active_count == 0
