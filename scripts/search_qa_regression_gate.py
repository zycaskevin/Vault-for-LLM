#!/usr/bin/env python3
"""Run a small local Search QA regression gate for CI.

The gate intentionally uses the public benchmark demo DB and keyword mode so it
does not need network access, model downloads, or optional embedding providers.
It catches obvious retrieval regressions in the source-checkout fixtures.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QA_FILE = PROJECT_ROOT / "benchmarks" / "search_qa" / "basic.en.json"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Search QA regression thresholds.")
    parser.add_argument("--qa-file", type=Path, default=DEFAULT_QA_FILE)
    parser.add_argument("--mode", default="keyword")
    parser.add_argument("--min-top1-hits", type=int, default=2)
    parser.add_argument("--min-topk-hits", type=int, default=2)
    parser.add_argument("--min-mrr", type=float, default=0.66)
    parser.add_argument("--min-no-result-precision", type=float, default=1.0)
    parser.add_argument("--max-citation-policy-violations", type=int, default=0)
    parser.add_argument("--max-result-mode-violations", type=int, default=0)
    return parser.parse_args(argv)


def run_benchmark(args: argparse.Namespace, work_dir: Path) -> dict[str, Any]:
    output_path = work_dir / "search-qa-gate.json"
    db_path = work_dir / "search-qa-gate.db"
    command = [
        sys.executable,
        str(PROJECT_ROOT / "benchmarks" / "search_benchmark.py"),
        "--db-path",
        str(db_path),
        "--embed-provider",
        "None",
        "--qa-file",
        str(args.qa_file),
        "--qa-modes",
        args.mode,
        "--output",
        str(output_path),
    ]
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    return json.loads(output_path.read_text(encoding="utf-8"))


def fail(message: str) -> int:
    print(f"Search QA regression gate failed: {message}", file=sys.stderr)
    return 1


def check_thresholds(snapshot: dict[str, Any], args: argparse.Namespace) -> int:
    aggregate = snapshot.get("aggregate") or {}
    checks = [
        ("top1_hits", aggregate.get("top1_hits", 0), args.min_top1_hits, ">="),
        ("topk_hits", aggregate.get("topk_hits", 0), args.min_topk_hits, ">="),
        (
            "mean_reciprocal_rank",
            aggregate.get("mean_reciprocal_rank", 0.0),
            args.min_mrr,
            ">=",
        ),
        (
            "no_result_precision",
            aggregate.get("no_result_precision", 0.0),
            args.min_no_result_precision,
            ">=",
        ),
        (
            "citation_policy_violations",
            aggregate.get("citation_policy_violations", 0),
            args.max_citation_policy_violations,
            "<=",
        ),
        (
            "result_mode_violations",
            aggregate.get("result_mode_violations", 0),
            args.max_result_mode_violations,
            "<=",
        ),
    ]
    for name, actual, expected, operator in checks:
        if operator == ">=" and float(actual) < float(expected):
            return fail(f"{name}={actual} is below {expected}")
        if operator == "<=" and float(actual) > float(expected):
            return fail(f"{name}={actual} is above {expected}")

    print("Search QA regression gate passed:")
    print(f"  qa_file: {snapshot.get('qa_file')}")
    print(f"  mode: {snapshot.get('mode')}")
    for key in (
        "total_cases",
        "top1_hits",
        "topk_hits",
        "mean_reciprocal_rank",
        "no_result_precision",
        "citation_policy_violations",
        "result_mode_violations",
        "mean_latency_ms",
        "p95_latency_ms",
    ):
        print(f"  {key}: {aggregate.get(key)}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="vault-search-qa-gate-") as tmp:
        payload = run_benchmark(args, Path(tmp))
    snapshots = payload.get("search_qa") or []
    if len(snapshots) != 1:
        return fail(f"expected one Search QA snapshot, found {len(snapshots)}")
    return check_thresholds(snapshots[0], args)


if __name__ == "__main__":
    raise SystemExit(main())
