"""Tests for local project-memory proof demos."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.project_memory_proofs import (
    run_agent_onboarding_proof,
    run_all_proofs,
    run_candidate_first_proof,
    run_wrong_source_bounded_read_proof,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_agent_onboarding_proof_reports_source_aware_recall(tmp_path):
    proof = run_agent_onboarding_proof(tmp_path)

    assert proof["passed"] is True
    assert proof["task_count"] == 5
    assert proof["naive_title_or_source_hits"] < proof["vault_topk_hits"]
    assert proof["vault_topk_hits"] == 5
    assert proof["vault_source_hit_rate"] == 1.0
    assert proof["vault_read_range_guidance_rate"] == 1.0


def test_candidate_first_proof_keeps_candidates_out_of_active_memory(tmp_path):
    proof = run_candidate_first_proof(tmp_path)

    assert proof["passed"] is True
    assert proof["candidate_count"] == 5
    assert proof["active_knowledge_delta_before_promotion"] == 0
    assert proof["active_knowledge_after_one_promotion"] == proof["active_knowledge_before"] + 1
    assert proof["review_buckets"]["rejected"] == 1
    assert proof["review_buckets"]["duplicate_review"] == 1
    assert proof["review_buckets"]["quality_review"] == 1
    assert proof["review_buckets"]["missing_source_reference"] == 1


def test_wrong_source_bounded_read_proof_detects_stale_title_match(tmp_path):
    proof = run_wrong_source_bounded_read_proof(tmp_path)

    assert proof["passed"] is True
    assert proof["would_title_only_pick_stale_source"] is True
    assert proof["source_aware_topk_hit"] is True
    assert proof["source_hit_rank"] == 1
    assert proof["bounded_read_contains_current_policy"] is True
    assert "Deployment Runbook" in proof["bounded_read_citation"]


def test_run_all_proofs_and_cli_emit_json(tmp_path):
    report = run_all_proofs(tmp_path / "api")

    assert report["proof_version"] == 1
    assert set(report["proofs"]) == {
        "agent_onboarding",
        "candidate_first",
        "wrong_source_bounded_read",
    }
    assert all(proof["passed"] for proof in report["proofs"].values())

    output = tmp_path / "proofs.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/project_memory_proofs.py",
            "--compact",
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    stdout_payload = json.loads(result.stdout)
    file_payload = json.loads(output.read_text(encoding="utf-8"))
    assert stdout_payload["proof_version"] == 1
    assert file_payload["proof_version"] == 1
    assert all(proof["passed"] for proof in stdout_payload["proofs"].values())
