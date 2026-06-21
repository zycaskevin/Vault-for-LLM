"""Tests for exported agent-session onboarding benchmark."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.agent_onboarding_benchmark import (
    load_session_chunks,
    run_benchmark,
)
from scripts.project_memory_proofs import ONBOARDING_CASES, ONBOARDING_DOCS, _build_docs_db
from vault.search_qa import write_json


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_demo_agent_onboarding_benchmark_compares_session_and_vault(tmp_path):
    report = run_benchmark(work_dir=tmp_path)

    assert report["benchmark_version"] == 1
    assert report["mode"] == "demo_fixture"
    assert report["summary"]["task_count"] == 5
    assert report["summary"]["session_hit_rate"] == 0.4
    assert report["summary"]["vault_topk_hit_rate"] == 1.0
    assert report["summary"]["topk_hit_rate_delta"] == 0.6
    assert report["summary"]["candidate_active_delta_before_promotion"] == 0
    assert report["summary"]["wrong_source_guard_passed"] is True
    assert report["candidate_first"]["passed"] is True
    assert report["wrong_source_bounded_read"]["would_title_only_pick_stale_source"] is True


def test_external_session_mode_uses_supplied_files(tmp_path):
    db_path = tmp_path / "vault.db"
    qa_file = tmp_path / "qa.json"
    session_file = tmp_path / "codex-session.md"
    candidate_file = tmp_path / "candidates.json"

    _build_docs_db(db_path, ONBOARDING_DOCS, build_maps=True)
    write_json(
        qa_file,
        {
            "version": 1,
            "cases": [
                {
                    **ONBOARDING_CASES[1],
                    "expected_session_substrings": [
                        "tests/test_vault_mcp_map.py",
                        "tests/test_mcp_memory.py",
                    ],
                },
                {
                    **ONBOARDING_CASES[4],
                    "expected_session_substrings": [
                        "dirty worktree",
                        "preserve unrelated",
                    ],
                },
            ],
        },
    )
    session_file.write_text(
        "Codex session says MCP changes require tests/test_vault_mcp_map.py "
        "and tests/test_mcp_memory.py before merging.\n",
        encoding="utf-8",
    )
    write_json(
        candidate_file,
        {
            "candidates": [
                {
                    "title": "MCP schema safety note",
                    "content": "MCP schema changes require rerunning map and memory tests because tool payload regressions can break integrations.",
                    "reason": "Extracted from session.",
                    "tags": "mcp,tests",
                    "source_ref": "codex-session#1",
                }
            ]
        },
    )

    report = run_benchmark(
        session_files=[session_file],
        qa_file=qa_file,
        db_path=db_path,
        candidate_file=candidate_file,
        work_dir=tmp_path / "work",
        provider="codex",
    )

    assert report["mode"] == "external_session"
    assert report["provider"] == "codex"
    assert report["summary"]["task_count"] == 2
    assert report["session_baseline"]["hits"] == 1
    assert report["vault_onboarding"]["topk_hits"] == 2
    assert report["summary"]["topk_hit_rate_delta"] == 0.5
    assert report["candidate_first"]["active_knowledge_delta_before_promotion"] == 0


def test_session_loader_reads_json_and_jsonl_exports(tmp_path):
    json_file = tmp_path / "hermes-session.json"
    jsonl_file = tmp_path / "codex-session.jsonl"
    json_file.write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "Please remember the release gate."},
                    {"role": "assistant", "content": "Run full pytest and Search QA."},
                ]
            }
        ),
        encoding="utf-8",
    )
    jsonl_file.write_text(
        "\n".join(
            [
                json.dumps({"content": "MCP schema changes need map tests."}),
                json.dumps({"text": "Bounded read_range is citation evidence."}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    chunks = load_session_chunks([json_file, jsonl_file])
    joined = "\n".join(chunk["text"] for chunk in chunks)

    assert "Please remember the release gate." in joined
    assert "Run full pytest and Search QA." in joined
    assert "MCP schema changes need map tests." in joined
    assert "Bounded read_range is citation evidence." in joined


def test_agent_onboarding_benchmark_cli_outputs_json(tmp_path):
    output = tmp_path / "benchmark.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/agent_onboarding_benchmark.py",
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
    assert stdout_payload["benchmark_version"] == 1
    assert file_payload["summary"]["vault_topk_hit_rate"] == 1.0
