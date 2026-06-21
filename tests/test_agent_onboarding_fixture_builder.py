"""Tests for repository-doc agent onboarding benchmark fixtures."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.agent_onboarding_benchmark import run_benchmark
from scripts.build_agent_onboarding_vault import REPO_DOCS, build_repo_docs_vault


REPO_ROOT = Path(__file__).resolve().parents[1]
QA_FILE = REPO_ROOT / "benchmarks/agent_onboarding/project_onboarding.repo.json"
CANDIDATE_FILE = REPO_ROOT / "benchmarks/agent_onboarding/session_candidates.example.json"
REPO_ONBOARDING_CASE_COUNT = 28


def test_repo_doc_onboarding_fixture_matches_generated_vault(tmp_path):
    manifest = build_repo_docs_vault(tmp_path, force=True)

    assert manifest["doc_count"] == len(REPO_DOCS)
    assert manifest["map_nodes"] >= len(REPO_DOCS)
    assert Path(manifest["db_path"]).exists()

    session_file = tmp_path / "codex-session.md"
    session_file.write_text(
        "\n".join(
            [
                "A prior Codex session discussed vault_read_range and bounded citations.",
                "It also mentioned Search QA benchmark checks.",
                "It noted sqlite-vec fallback behavior.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = run_benchmark(
        session_files=[session_file],
        qa_file=QA_FILE,
        db_path=Path(manifest["db_path"]),
        candidate_file=CANDIDATE_FILE,
        work_dir=tmp_path / "work",
        provider="codex-test",
    )

    assert report["mode"] == "external_session"
    assert report["summary"]["task_count"] == REPO_ONBOARDING_CASE_COUNT
    assert report["summary"]["vault_topk_hit_rate"] == 1.0
    assert report["summary"]["vault_source_hit_rate"] == 1.0
    assert report["summary"]["vault_read_range_guidance_rate"] == 1.0
    assert report["summary"]["candidate_active_delta_before_promotion"] == 0
    assert report["candidate_first"]["passed"] is True


def test_build_agent_onboarding_vault_cli_writes_manifest(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_agent_onboarding_vault.py",
            "--output-dir",
            str(tmp_path),
            "--compact",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    manifest_path = Path(payload["manifest_path"])
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["doc_count"] == len(REPO_DOCS)
    assert manifest["map_nodes"] >= len(REPO_DOCS)
