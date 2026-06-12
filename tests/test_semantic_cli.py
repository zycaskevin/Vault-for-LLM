"""Semantic workflow CLI tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from vault.db import VaultDB


RAW = "\n".join(
    [
        "# Semantic Workflow Guide",
        "Intro",
        "## Cache Warm",
        "Semantic workflow warm deduplicates repeated QA queries.",
    ]
)
AAAK = "\n".join(
    [
        "TITLE: Semantic Workflow Guide",
        "CLAIMS:",
        "- [C1] Semantic workflow warm deduplicates repeated QA queries. (L4)",
    ]
)

REPO_ROOT = Path(__file__).parent.parent


def _run_cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "vault.cli", *args],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _build_db(tmp_path: Path, *, hash_config: bool = False) -> Path:
    db_path = tmp_path / "vault.db"
    db = VaultDB(db_path).connect()
    try:
        db.add_knowledge(
            "Semantic Workflow Guide",
            RAW,
            content_aaak=AAAK,
            category="search",
            tags="semantic,workflow",
            trust=0.9,
        )
        if hash_config:
            db.set_config("embedding_provider", "hash-deterministic-v1")
            db.set_config("embedding_model", "test")
    finally:
        db.close()
    return db_path


def _write_qa(tmp_path: Path) -> Path:
    qa_file = tmp_path / "qa.json"
    qa_file.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {
                        "id": "warm_first",
                        "query": "semantic workflow warm",
                        "expected_titles": ["Semantic Workflow Guide"],
                    },
                    {
                        "id": "warm_duplicate",
                        "query": "semantic workflow warm",
                        "expected_titles": ["Semantic Workflow Guide"],
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return qa_file


def _vector_count(db_path: Path) -> int:
    db = VaultDB(db_path).connect()
    try:
        row = db.conn.execute("SELECT count(*) AS count FROM semantic_vectors").fetchone()
        return int(row["count"])
    finally:
        db.close()


def test_semantic_cli_default_rejects_hash_provider_config(tmp_path: Path):
    db_path = _build_db(tmp_path, hash_config=True)

    result = _run_cli(tmp_path, "semantic", "rebuild", "--db-path", str(db_path))

    assert result.returncode == 2
    assert "error:" in result.stderr
    assert _vector_count(db_path) == 0


def test_semantic_cli_allow_hash_rebuild_populates_vectors(tmp_path: Path):
    db_path = _build_db(tmp_path)

    result = _run_cli(
        tmp_path,
        "semantic",
        "rebuild",
        "--db-path",
        str(db_path),
        "--allow-hash",
        "--hash-dim",
        "8",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["action"] == "rebuild"
    assert payload["provider_id"] == "hash-deterministic-v1"
    assert payload["is_semantic"] is False
    assert payload["dimension"] == 8
    assert payload["knowledge_rows"] == 1
    assert payload["node_vectors"] == 2
    assert payload["claim_vectors"] == 1
    assert _vector_count(db_path) == 3


def test_semantic_cli_warm_dedupes_and_does_not_write_vectors(tmp_path: Path):
    db_path = _build_db(tmp_path)
    qa_file = _write_qa(tmp_path)

    result = _run_cli(
        tmp_path,
        "semantic",
        "warm",
        "--db-path",
        str(db_path),
        "--qa-file",
        str(qa_file),
        "--allow-hash",
        "--hash-dim",
        "8",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["action"] == "warm"
    assert payload["warmed_queries"] == 1
    assert payload["cache_size"] == 1
    assert _vector_count(db_path) == 0


def test_semantic_cli_smoke_writes_combined_json_with_qa_aggregate(tmp_path: Path):
    db_path = _build_db(tmp_path)
    qa_file = _write_qa(tmp_path)
    output = tmp_path / "semantic_smoke.json"

    result = _run_cli(
        tmp_path,
        "semantic",
        "smoke",
        "--db-path",
        str(db_path),
        "--qa-file",
        str(qa_file),
        "--output",
        str(output),
        "--allow-hash",
        "--hash-dim",
        "8",
        "--limit",
        "3",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written == payload
    assert payload["action"] == "smoke"
    assert payload["output_written"] is True
    assert payload["rebuild"] == {
        "knowledge_rows": 1,
        "node_vectors": 2,
        "claim_vectors": 1,
    }
    assert payload["warmed_queries"] == 1
    assert payload["cache_size"] >= 1
    assert payload["qa"]["aggregate"]["total_cases"] == 2
    assert "cases_with_results" in payload["qa"]["aggregate"]
