"""Semantic workflow CLI tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from vault.db import VaultDB
from vault.semantic_lifecycle import close_provider, run_semantic_daemon, run_semantic_startup


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


def _cache_summary(db_path: Path) -> dict[str, int]:
    db = VaultDB(db_path).connect()
    try:
        row = db.conn.execute(
            "SELECT count(*) AS rows, coalesce(sum(hit_count), 0) AS hits FROM embedding_cache"
        ).fetchone()
        return {"rows": int(row["rows"]), "hits": int(row["hits"])}
    finally:
        db.close()


def _write_unique_qa(tmp_path: Path, count: int = 3) -> Path:
    qa_file = tmp_path / "qa_unique.json"
    qa_file.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {
                        "id": f"case_{index}",
                        "query": f"semantic workflow warm query {index}",
                        "expected_titles": ["Semantic Workflow Guide"],
                    }
                    for index in range(count)
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return qa_file


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


def test_semantic_cli_persistent_warm_inserts_and_reuses_rows(tmp_path: Path):
    db_path = _build_db(tmp_path)
    qa_file = _write_qa(tmp_path)

    first = _run_cli(
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
        "--persist-cache",
    )
    assert first.returncode == 0, first.stderr
    first_payload = json.loads(first.stdout)
    assert first_payload["persistent_cache"]["writes"] == 1
    assert _cache_summary(db_path) == {"rows": 1, "hits": 0}

    second = _run_cli(
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
        "--persist-cache",
    )
    assert second.returncode == 0, second.stderr
    second_payload = json.loads(second.stdout)
    assert second_payload["persistent_cache"]["persistent_hits"] == 1
    assert second_payload["persistent_cache"]["writes"] == 0
    assert _cache_summary(db_path) == {"rows": 1, "hits": 1}


def test_semantic_cli_persistent_cache_dimension_mismatch_does_not_reuse(tmp_path: Path):
    db_path = _build_db(tmp_path)
    qa_file = _write_qa(tmp_path)

    for dim in (8, 16):
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
            str(dim),
            "--persist-cache",
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["persistent_cache"]["writes"] == 1
        assert payload["persistent_cache"]["persistent_hits"] == 0

    assert _cache_summary(db_path) == {"rows": 2, "hits": 0}


def test_semantic_cli_cache_stats_returns_rows_and_hits(tmp_path: Path):
    db_path = _build_db(tmp_path)
    qa_file = _write_qa(tmp_path)
    for _ in range(2):
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
            "--persist-cache",
        )
        assert result.returncode == 0, result.stderr

    stats = _run_cli(
        tmp_path,
        "semantic",
        "cache-stats",
        "--db-path",
        str(db_path),
        "--provider-id",
        "hash-deterministic-v1",
        "--dimension",
        "8",
    )
    assert stats.returncode == 0, stats.stderr
    payload = json.loads(stats.stdout)
    assert payload["action"] == "cache-stats"
    assert payload["total_rows"] == 1
    assert payload["total_hits"] == 1
    assert payload["provider_id"] == "hash-deterministic-v1"
    assert payload["dimension"] == 8


def test_semantic_cli_cache_prune_max_rows_deletes_expected_rows(tmp_path: Path):
    db_path = _build_db(tmp_path)
    qa_file = _write_unique_qa(tmp_path, count=3)
    warm = _run_cli(
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
        "--persist-cache",
    )
    assert warm.returncode == 0, warm.stderr
    assert _cache_summary(db_path)["rows"] == 3

    prune = _run_cli(
        tmp_path,
        "semantic",
        "cache-prune",
        "--db-path",
        str(db_path),
        "--provider-id",
        "hash-deterministic-v1",
        "--dimension",
        "8",
        "--max-rows",
        "1",
    )
    assert prune.returncode == 0, prune.stderr
    payload = json.loads(prune.stdout)
    assert payload == {"action": "cache-prune", "deleted_rows": 2}
    assert _cache_summary(db_path)["rows"] == 1


def test_semantic_startup_hook_warms_rebuilds_and_smokes(tmp_path: Path):
    db_path = _build_db(tmp_path)
    qa_file = _write_qa(tmp_path)

    payload = run_semantic_startup(
        db_path=db_path,
        qa_file=qa_file,
        allow_hash=True,
        hash_dim=8,
        persist_cache=True,
        rebuild=True,
        smoke=True,
        limit=3,
    )

    assert payload["success"] is True
    assert payload["provider"]["provider_id"] == "hash-deterministic-v1"
    assert payload["provider"]["dimension"] == 8
    assert payload["rebuild"] == {
        "knowledge_rows": 1,
        "node_vectors": 2,
        "claim_vectors": 1,
        "provider_id": "hash-deterministic-v1",
        "dimension": 8,
    }
    assert payload["warmed_queries"] == 1
    assert payload["cache_before"]["total_rows"] == 0
    assert payload["cache_after"]["total_rows"] > 0
    assert payload["persistent_cache"]["writes"] > 0
    assert payload["smoke"]["aggregate"]["total_cases"] == 2


def test_semantic_daemon_repeat_two_reuses_persistent_cache(tmp_path: Path):
    db_path = _build_db(tmp_path)
    qa_file = _write_qa(tmp_path)

    payload = run_semantic_daemon(
        db_path=db_path,
        qa_file=qa_file,
        allow_hash=True,
        hash_dim=8,
        persist_cache=True,
        repeat=2,
        interval=0,
    )

    assert payload["success"] is True
    assert payload["repeat"] == 2
    assert len(payload["iterations"]) == 2
    assert payload["iterations"][0]["persistent_cache"]["writes"] == 1
    assert payload["iterations"][1]["persistent_cache"]["persistent_hits"] == 1
    assert _cache_summary(db_path)["rows"] > 0
    assert _cache_summary(db_path)["hits"] > 0


def test_close_provider_swallows_close_failure():
    class BrokenClose:
        def close(self):
            raise RuntimeError("boom")

    close_provider(BrokenClose())


def test_semantic_cli_startup_outputs_json_and_file(tmp_path: Path):
    db_path = _build_db(tmp_path)
    qa_file = _write_qa(tmp_path)
    output = tmp_path / "startup.json"

    result = _run_cli(
        tmp_path,
        "semantic",
        "startup",
        "--db-path",
        str(db_path),
        "--qa-file",
        str(qa_file),
        "--allow-hash",
        "--hash-dim",
        "8",
        "--rebuild",
        "--smoke",
        "--output",
        str(output),
        "--limit",
        "3",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert payload["action"] == "startup"
    assert payload["success"] is True
    assert payload["warmed_queries"] == 1
    assert payload["smoke"]["aggregate"]["total_cases"] == 2
    assert _cache_summary(db_path)["rows"] > 0


def test_semantic_cli_daemon_repeat_two_interval_zero(tmp_path: Path):
    db_path = _build_db(tmp_path)
    qa_file = _write_qa(tmp_path)

    result = _run_cli(
        tmp_path,
        "semantic",
        "daemon",
        "--db-path",
        str(db_path),
        "--qa-file",
        str(qa_file),
        "--allow-hash",
        "--hash-dim",
        "8",
        "--repeat",
        "2",
        "--interval",
        "0",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["action"] == "daemon"
    assert payload["success"] is True
    assert len(payload["iterations"]) == 2
    assert payload["iterations"][1]["persistent_cache"]["persistent_hits"] == 1
