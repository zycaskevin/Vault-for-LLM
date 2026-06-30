import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from vault.db import VaultDB
from vault.memory_pipeline import run_memory_pipeline
from vault.reflection import run_reflection
from vault.search import VaultSearch
from vault.temporal import list_temporal_memories, temporal_summary


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_temporal_metadata_separates_current_and_past_facts(tmp_path):
    now = datetime.now(timezone.utc)
    past = (now - timedelta(days=5)).isoformat()
    future = (now + timedelta(days=5)).isoformat()
    with VaultDB(tmp_path / "vault.db") as db:
        old_id = db.add_knowledge(
            "Old office",
            "The office was previously in City A.",
            valid_until=past,
        )
        db.add_knowledge(
            "Current office",
            "The office is now in City B.",
            valid_from=past,
            supersedes_id=old_id,
        )
        db.add_knowledge("Future plan", "The office may move later.", valid_from=future)
        summary = temporal_summary(db, as_of=now.isoformat())
        current = list_temporal_memories(db, state="current", as_of=now.isoformat())
        past_items = list_temporal_memories(db, state="past", as_of=now.isoformat())

    assert summary["counts"]["current"] == 1
    assert summary["counts"]["past"] == 1
    assert summary["counts"]["future"] == 1
    assert current["items"][0]["title"] == "Current office"
    assert past_items["items"][0]["title"] == "Old office"


def test_memory_pipeline_previews_then_writes_candidates(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "codex-session.md").write_text(
        "Decision: Use candidate memory first because automation should not write active knowledge directly.\n"
        "Bug fix: Pipeline capture should summarize reusable session lessons.",
        encoding="utf-8",
    )
    with VaultDB(tmp_path / "vault.db"):
        pass

    preview = run_memory_pipeline(
        tmp_path,
        search_dirs=["sessions"],
        source_system="codex",
        transcript_limit=1,
        write_candidates=False,
    )
    written = run_memory_pipeline(
        tmp_path,
        search_dirs=["sessions"],
        source_system="codex",
        transcript_limit=1,
        write_candidates=True,
    )
    with VaultDB(tmp_path / "vault.db") as db:
        rows = db.list_memory_candidates(limit=10)

    assert preview["preview_count"] >= 1
    assert preview["candidate_count"] == 0
    assert written["candidate_count"] >= 1
    assert rows
    assert all(row["source"] == "session_capture" for row in rows)


def test_memory_pipeline_marks_merge_targets_for_existing_memory(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "codex-session.md").write_text(
        "Decision: Use candidate memory first because automation should not write active knowledge directly.",
        encoding="utf-8",
    )
    with VaultDB(tmp_path / "vault.db") as db:
        db.add_knowledge(
            "Candidate-first automation",
            "Decision: Use candidate memory first because automation should not write active knowledge directly.",
            category="decision",
        )

    preview = run_memory_pipeline(
        tmp_path,
        search_dirs=["sessions"],
        source_system="codex",
        transcript_limit=1,
        write_candidates=False,
    )

    candidates = preview["captures"][0]["candidates"]
    assert candidates
    assert candidates[0]["recommended_action"] == "merge_into_existing"
    assert candidates[0]["novelty_score"] < 0.4
    assert candidates[0]["merge_target"]["kind"] == "knowledge"


def test_memory_pipeline_writes_safe_latest_report(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "codex-session.md").write_text(
        "Decision: Pipeline reports should show ingestion counts without raw candidate content.",
        encoding="utf-8",
    )
    with VaultDB(tmp_path / "vault.db"):
        pass

    payload = run_memory_pipeline(
        tmp_path,
        search_dirs=["sessions"],
        source_system="codex",
        transcript_limit=1,
        write_candidates=True,
        include_content=True,
        write_report=True,
    )
    report = tmp_path / payload["report_path"]
    markdown = tmp_path / payload["report_markdown_path"]
    report_payload = json.loads(report.read_text(encoding="utf-8"))

    assert payload["report_path"] == "reports/automation/pipeline-latest.json"
    assert payload["report_markdown_path"] == "reports/automation/pipeline-latest.md"
    assert report_payload["candidate_count"] >= 1
    for capture in report_payload["captures"]:
        for candidate in capture["candidates"]:
            assert "content" not in candidate
            assert "content_preview" not in candidate
            assert "gate_payload" not in candidate


def test_reflection_run_is_report_first_and_does_not_promote(tmp_path):
    with VaultDB(tmp_path / "vault.db") as db:
        db.add_knowledge("Duplicate", "A workflow decision because it explains a fix.")
        db.add_knowledge("Duplicate", "Another workflow decision because it explains a fix.")
    payload = run_reflection(tmp_path, limit=10, write_candidates=True, apply=False)
    with VaultDB(tmp_path / "vault.db") as db:
        active_count = db.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"]

    assert payload["action"] == "memory_reflection_run"
    assert payload["safety"]["report_first"] is True
    assert payload["safety"]["hard_delete"] is False
    assert active_count == 2


def test_reflection_writes_consolidation_candidates(tmp_path):
    with VaultDB(tmp_path / "vault.db") as db:
        db.add_knowledge(
            "Deploy pitfall",
            "Deploy failed because environment variables were missing; fix by checking the release checklist.",
            category="error",
        )
        db.add_knowledge(
            "Deploy pitfall duplicate",
            "Deployment failure happened because environment variables were missing; fix by checking the release checklist.",
            category="error",
        )

    payload = run_reflection(tmp_path, limit=10, write_candidates=True, apply=False)
    with VaultDB(tmp_path / "vault.db") as db:
        rows = db.list_memory_candidates(status="candidate", limit=10)

    assert payload["consolidation"]["suggestion_count"] >= 1
    assert payload["consolidation"]["written_count"] >= 1
    assert any(row["memory_type"] == "consolidation_suggestion" for row in rows)


def test_search_temporal_ranking_prefers_current_fact(tmp_path):
    now = datetime.now(timezone.utc)
    past = (now - timedelta(days=2)).isoformat()
    with VaultDB(tmp_path / "vault.db") as db:
        old_id = db.add_knowledge(
            "Office location",
            "The office location is City A.",
            valid_until=past,
        )
        current_id = db.add_knowledge(
            "Office location",
            "The office location is City B.",
            valid_from=past,
            supersedes_id=old_id,
        )
        results = VaultSearch(db, enable_query_expansion=False).search(
            "office location",
            mode="keyword",
            limit=5,
            use_rerank=False,
            temporal_as_of=now.isoformat(),
        )

    assert results[0]["id"] == current_id
    assert results[0]["temporal_state"] == "current"
    assert any(row["id"] == old_id and row["temporal_state"] == "past" for row in results)


def test_cli_memory_group_smoke(tmp_path):
    with VaultDB(tmp_path / "vault.db"):
        pass
    transcript = tmp_path / "session.md"
    transcript.write_text(
        "Workflow: Always run the memory pipeline after session exports because it extracts candidates.",
        encoding="utf-8",
    )
    env = {"PYTHONPATH": str(REPO_ROOT)}

    pipeline = subprocess.run(
        [
            sys.executable,
            "-m",
            "vault.cli",
            "memory",
            "pipeline",
            "--search-dir",
            ".",
            "--write-candidates",
            "--pretty",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert pipeline.returncode == 0, pipeline.stderr
    pipeline_payload = json.loads(pipeline.stdout)
    assert pipeline_payload["candidate_count"] >= 1

    temporal = subprocess.run(
        [sys.executable, "-m", "vault.cli", "memory", "temporal", "status", "--pretty"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert temporal.returncode == 0, temporal.stderr
    assert json.loads(temporal.stdout)["action"] == "temporal_status"

    reflection = subprocess.run(
        [sys.executable, "-m", "vault.cli", "memory", "reflection", "--limit", "5", "--pretty"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert reflection.returncode == 0, reflection.stderr
    assert json.loads(reflection.stdout)["action"] == "memory_reflection_run"
