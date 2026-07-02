import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from vault.db import VaultDB
from vault.multi_host import (
    detect_candidate_conflicts,
    list_audit_log,
    list_conflicts,
    list_revisions,
    preview_conflict,
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


def test_accept_remote_conflict_requires_explicit_memory_apply(tmp_path):
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
            source_ref="remote_write_request:req-apply",
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
            remote_request_id="req-apply",
            source_agent="remote-agent",
        )
        conflict = detect_candidate_conflicts(
            db,
            candidate_id=candidate["candidate_id"],
            revision_id=revision["revision_id"],
        )[0]

        with pytest.raises(ValueError, match="apply_memory_change"):
            resolve_conflict(db, conflict["id"], resolution="accept_remote")

        assert db.get_knowledge(knowledge_id)["status"] == "active"
        assert db.get_memory_candidate(candidate["candidate_id"])["status"] == "candidate"


def test_preview_conflict_summarizes_local_remote_diff_without_mutating(tmp_path):
    db_path = tmp_path / "vault.db"
    with VaultDB(db_path) as db:
        knowledge_id = db.add_knowledge(
            "Shared deployment rule",
            "Current rule says smoke tests run after deploy.\nKeep rollback checklist nearby.",
            source="local",
            trust=0.8,
        )
        candidate = create_candidate(
            db,
            title="Shared deployment rule",
            content="Decision: smoke tests should run before deploy because rollback risk is lower.\nKeep rollback checklist nearby.",
            reason="Remote agent observed a safer workflow.",
            source="remote_write_request",
            source_ref="remote_write_request:req-preview",
            memory_type="remote_candidate",
            category="decision",
            tags="deploy,smoke,remote",
            trust=0.91,
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
            remote_request_id="req-preview",
            source_agent="remote-agent",
        )
        conflict = detect_candidate_conflicts(
            db,
            candidate_id=candidate["candidate_id"],
            revision_id=revision["revision_id"],
        )[0]

        payload = preview_conflict(db, conflict["id"])

        assert payload["ok"] is True
        assert payload["status"] == "needs_review"
        assert payload["local"]["id"] == knowledge_id
        assert payload["remote"]["id"] == candidate["candidate_id"]
        assert payload["remote"]["trust"] == 0.91
        assert payload["recommendation"]["safe_action"] == "review_accept_remote"
        assert any(line.startswith("-Current rule") for line in payload["diff"])
        assert any(line.startswith("+Decision: smoke") for line in payload["diff"])
        assert db.get_knowledge(knowledge_id)["status"] == "active"
        assert db.get_memory_candidate(candidate["candidate_id"])["status"] == "candidate"


def test_accept_remote_conflict_promotes_candidate_and_archives_local(tmp_path):
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
            source_ref="remote_write_request:req-accept",
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
            remote_request_id="req-accept",
            source_agent="remote-agent",
        )
        conflict = detect_candidate_conflicts(
            db,
            candidate_id=candidate["candidate_id"],
            revision_id=revision["revision_id"],
        )[0]

        resolved = resolve_conflict(
            db,
            conflict["id"],
            resolution="accept_remote",
            reason="Remote candidate is newer and safer.",
            actor_agent="review-agent",
            apply_memory_change=True,
            project_dir=tmp_path,
            compile=False,
            build_map=False,
        )

        resolution = json.loads(resolved["resolution_json"])
        promoted_id = db.get_memory_candidate(candidate["candidate_id"])["promoted_knowledge_id"]
        assert resolved["status"] == "resolved"
        assert resolution["memory_change_applied"] is True
        assert db.get_knowledge(knowledge_id)["status"] == "archived"
        assert db.get_knowledge(promoted_id)["status"] == "active"
        assert db.get_knowledge(promoted_id)["content_raw"].startswith("Decision: smoke tests")
        actions = [row["action"] for row in list_audit_log(db, limit=20)]
        assert "knowledge:archived_for_remote_accept" in actions
        assert "conflict:resolved" in actions
        operations = [row["operation"] for row in list_revisions(db, limit=20)]
        assert "remote_candidate_promoted_accept_remote" in operations
        assert "local_knowledge_archived_for_remote_accept" in operations


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

    main(["sync", "preview-conflict", "conf_cli", "--project-dir", str(project), "--json"])
    preview = json.loads(capsys.readouterr().out)
    assert preview["conflict"]["id"] == "conf_cli"
    assert preview["remote"]["id"] == candidate["candidate_id"]
    assert preview["recommendation"]["safe_action"] in {"manual_review", "review_accept_remote", "keep_local"}

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
