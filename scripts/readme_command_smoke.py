#!/usr/bin/env python3
"""Smoke-test the public README command path.

This script intentionally exercises only local, dependency-light commands that are
safe for CI and for a clean source checkout. It protects README examples from
claiming a command shape that no longer exists.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = result.stdout.strip()
    if result.returncode != 0:
        joined = " ".join(command)
        raise SystemExit(f"Command failed ({result.returncode}): {joined}\n{output}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test README documented commands")
    parser.add_argument("--keep-temp", action="store_true", help="keep the temporary project for debugging")
    args = parser.parse_args()

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(REPO_ROOT) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")

    python = sys.executable
    temp_ctx = tempfile.TemporaryDirectory(prefix="vault-readme-smoke-")
    temp_dir = Path(temp_ctx.name)
    if args.keep_temp:
        # Avoid automatic cleanup by intentionally leaking ownership to the caller.
        temp_ctx.cleanup = lambda: None  # type: ignore[method-assign]

    outputs: dict[str, str] = {}
    outputs["vault_help"] = run([python, "-m", "vault.cli", "--help"], cwd=temp_dir, env=env)
    outputs["semantic_help"] = run([python, "-m", "vault.cli", "semantic", "--help"], cwd=temp_dir, env=env)
    outputs["search_qa_help"] = run([python, "-m", "vault.cli", "search-qa", "--help"], cwd=temp_dir, env=env)

    run([python, "-m", "vault.cli", "init"], cwd=temp_dir, env=env)
    run(
        [
            python,
            "-m",
            "vault.cli",
            "add",
            "First lesson",
            "--content",
            "The bug was caused by a missing cache key. The fix was adding provider metadata.",
        ],
        cwd=temp_dir,
        env=env,
    )
    run([python, "-m", "vault.cli", "compile", "--no-embed"], cwd=temp_dir, env=env)
    search_output = run([python, "-m", "vault.cli", "search", "cache key", "--keyword-only"], cwd=temp_dir, env=env)
    if "First lesson" not in search_output:
        raise SystemExit(f"README quickstart search did not find the added note:\n{search_output}")

    qa_file = temp_dir / "qa.json"
    qa_file.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {
                        "id": "cache-key",
                        "query": "cache key",
                        "expected_titles": ["First lesson"],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    qa_output = temp_dir / "qa-output.json"
    run(
        [
            python,
            "-m",
            "vault.cli",
            "search-qa",
            "run",
            "--qa-file",
            str(qa_file),
            "--output",
            str(qa_output),
            "--mode",
            "keyword",
        ],
        cwd=temp_dir,
        env=env,
    )
    qa_payload = json.loads(qa_output.read_text(encoding="utf-8"))
    if qa_payload.get("aggregate", {}).get("total_cases") != 1:
        raise SystemExit(f"Unexpected Search QA output: {qa_payload}")

    semantic_output = run(
        [
            python,
            "-m",
            "vault.cli",
            "semantic",
            "smoke",
            "--allow-hash",
            "--qa-file",
            str(qa_file),
            "--mode",
            "keyword",
            "--limit",
            "5",
            "--pretty",
        ],
        cwd=temp_dir,
        env=env,
    )
    semantic_payload = json.loads(semantic_output)
    if semantic_payload.get("action") != "smoke" or not semantic_payload.get("qa"):
        raise SystemExit(f"Unexpected semantic smoke output: {semantic_payload}")

    cache_stats = run(
        [python, "-m", "vault.cli", "semantic", "cache-stats", "--pretty"],
        cwd=temp_dir,
        env=env,
    )
    json.loads(cache_stats)

    print("✅ README documented command smoke passed")
    print(f"  temp_project: {temp_dir}")
    print("  commands: help, init, add, compile --no-embed, search --keyword-only, search-qa run, semantic smoke, semantic cache-stats")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
