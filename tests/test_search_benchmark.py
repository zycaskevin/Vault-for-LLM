"""Smoke tests for the public benchmark helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent


def test_search_benchmark_can_run_search_qa_fixture(tmp_path):
    output = tmp_path / "benchmark.json"
    db_path = tmp_path / "benchmark.db"

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "benchmarks" / "search_benchmark.py"),
            "--db-path",
            str(db_path),
            "--embed-provider",
            "None",
            "--qa-file",
            str(REPO_ROOT / "benchmarks" / "search_qa" / "basic.en.json"),
            "--qa-modes",
            "keyword",
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["metrics"]
    assert payload["search_qa"][0]["aggregate"]["total_cases"] == 3
    assert payload["search_qa"][0]["aggregate"]["topk_hits"] >= 2
