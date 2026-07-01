import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vault.db import VaultDB
from vault.multi_host import (
    detect_candidate_conflicts,
    list_audit_log,
    list_conflicts,
    list_revisions,
    record_memory_revision,
    resolve_conflict,
)
from vault.memory import create_candidate


def test_revision_conflict_and_audit_helpers(tmp_path):
    db_path = tmp_path / "vault.db"
    with VaultDB(db_path) as db:
        knowledge_id = db.add_knowledge(
            "Shared deployment rule",
            "Current rule says smoke tests run after deploy.",
            source="local",
        )
        candidate = create_candidate(
            db,
            title="Shared deployment rule",
            content="Decision: smoke tests should run before deploy because rollback risk is lower.",
            reason="Remote agent observed a safer workflow.",
            source="remote_write_request",
            source_ref="remote_write_request:req-1",
            memory_type="remote_candidate",
            category="decision",
            tags="deploy,smoke,remote",
            trust=0.9,
            scope="shared",
            sensitivity="low",
        )
        revision = record_memory_revision(
            db,
            title="Shared deployment rule",
            content="Decision: smoke tests should run before deploy because rollback risk is lower.",
            operation="remote_candidate_imported",
            status="candidate_created",
            candidate_id=candidate["candidate_id"],
            remote_request_id="req-1",
            source_agent="remote-agent",
        )

        conflicts = detect_candidate_conflicts(
            db,
            candidate_id=candidate["candidate_id"],
            revision_id=revision["revision_id"],
        )

        assert len(conflicts) == 1
        assert conflicts[0]["knowledge_id"] == knowledge_id
        assert conflicts[0]["status"] == "open"
        assert list_revisions(db, limit=5)[0]["operation"] == "remote_candidate_imported"
        assert list_conflicts(db, status="open", limit=5)[0]["id"] == conflicts[0]["id"]
        assert any(row["action"] == "conflict:opened" for row in list_audit_log(db, limit=10))

        resolved = resolve_conflict(
            db,
            conflicts[0]["id"],
            resolution="manual",
            reason="Operator will write a merged candidate.",
            actor_agent="review-agent",
        )

        assert resolved["status"] == "resolved"
        assert list_conflicts(db, status="open", limit=5) == []
        assert any(row["action"] == "conflict:resolved" for row in list_audit_log(db, limit=10))


def test_sync_cli_revisions_conflicts_audit_and_resolve(tmp_path, capsys):
    from vault.cli import main

    project = tmp_path / "project"
    main(["init", "--project-dir", str(project)])
    capsys.readouterr()
    with VaultDB(project / "vault.db") as db:
        candidate = create_candidate(
            db,
            title="CLI sync candidate",
            content="Decision: CLI sync status should expose revisions and conflicts for audit.",
            reason="Testing multi-host sync surfaces.",
            source="remote_write_request",
            source_ref="remote_write_request:req-cli",
            memory_type="remote_candidate",
            category="decision",
            tags="sync,cli,audit",
            trust=0.9,
            scope="shared",
            sensitivity="low",
        )
        revision = record_memory_revision(
            db,
            title="CLI sync candidate",
            content="Decision: CLI sync status should expose revisions and conflicts for audit.",
            operation="remote_candidate_imported",
            status="candidate_created",
            candidate_id=candidate["candidate_id"],
            remote_request_id="req-cli",
            source_agent="remote-agent",
        )
        conflict = db.conn.execute(
            """INSERT INTO memory_conflicts
               (id, created_at, updated_at, status, knowledge_id, left_revision_id,
                right_revision_id, candidate_id, conflict_type, reason, resolution_json)
               VALUES('conf_cli', 'now', 'now', 'open', NULL, '', ?, ?, 'manual_test', 'test conflict', '{}')""",
            (revision["revision_id"], candidate["candidate_id"]),
        )
        db.conn.commit()

    main(["sync", "revisions", "--project-dir", str(project), "--json"])
    revisions = json.loads(capsys.readouterr().out)
    assert revisions["revisions"][0]["operation"] == "remote_candidate_imported"

    main(["sync", "conflicts", "--project-dir", str(project), "--json"])
    conflicts = json.loads(capsys.readouterr().out)
    assert conflicts["conflicts"][0]["id"] == "conf_cli"

    main(
        [
            "sync",
            "resolve-conflict",
            "conf_cli",
            "--resolution",
            "manual",
            "--reason",
            "reviewed",
            "--agent-id",
            "review-agent",
            "--project-dir",
            str(project),
            "--json",
        ]
    )
    resolved = json.loads(capsys.readouterr().out)
    assert resolved["conflict"]["status"] == "resolved"

    main(["sync", "audit", "--project-dir", str(project), "--json"])
    audit = json.loads(capsys.readouterr().out)
    assert any(row["action"] == "conflict:resolved" for row in audit["events"])
