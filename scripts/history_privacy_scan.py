#!/usr/bin/env python3
"""Scan reachable git history for public-boundary privacy regressions.

This intentionally focuses on repository-specific high-confidence signals. It
is not a general secret scanner; CI also runs a separate token-pattern check.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


SCRIPT_PATH = "scripts/history_privacy_scan.py"

PRIVATE_TERMS = [
    "user " + "Liao",
    "Art" + "hur " + "Liao",
    "zycaskevin" + "@gmail.com",
    "zmttlqmallluooqxswqy" + ".supabase.co",
    "玻" + "尿酸",
    "肉" + "毒",
    "電" + "波拉皮",
    "电" + "波拉皮",
    "inst" + "reet",
    "xiaogu",
    "eve-" + "guard" + "rails",
    "fei" + "shu",
]

FORBIDDEN_PATH_PATTERNS = [
    r"\.env(\.|$)",
    r"duplicate_report\.json",
    r".*_report\.json",
    r".*\.(db|sqlite|sqlite3)",
    r"SETUP\.md",
    r"INSTALL\.md",
    "guard" + "rails" + r"_wakeup\.py",
    "guard" + "rails" + r"_semantic_search\.py",
    "guard" + "rails" + r"_vector_search\.py",
    "graphify" + "-out",
    "_knowledge" + "_base",
    r"\." + "agent-runtime",
    r"\." + "hermes",
    r"\." + "opencode",
]
FORBIDDEN_PATH_RE = re.compile(r"(^|/)(" + "|".join(FORBIDDEN_PATH_PATTERNS) + r")")


@dataclass(frozen=True)
class Finding:
    kind: str
    location: str
    detail: str


def _git(repo: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=check,
    )


def scan_paths(repo: Path) -> list[Finding]:
    result = _git(repo, ["log", "--all", "--name-only", "--pretty=format:"], check=True)
    findings: list[Finding] = []
    for raw_path in sorted({line.strip() for line in result.stdout.splitlines() if line.strip()}):
        if FORBIDDEN_PATH_RE.search(raw_path):
            findings.append(Finding("forbidden_path", raw_path, "path appeared in reachable history"))
    return findings


def scan_terms(repo: Path) -> list[Finding]:
    commits = _git(repo, ["rev-list", "--all"], check=True).stdout.splitlines()
    if not commits:
        return []

    findings: list[Finding] = []
    for term in PRIVATE_TERMS:
        result = _git(
            repo,
            ["grep", "-I", "-n", "-i", "-F", term, *commits, "--", ".", ":(exclude).git"],
            check=False,
        )
        if result.returncode not in (0, 1):
            raise RuntimeError(result.stderr.strip() or f"git grep failed for {term!r}")
        for line in result.stdout.splitlines():
            parts = line.split(":", 3)
            if len(parts) < 4:
                continue
            commit, path, line_no, _text = parts
            if path == SCRIPT_PATH:
                continue
            findings.append(
                Finding(
                    "private_term",
                    f"{commit[:12]}:{path}:{line_no}",
                    f"matched repository-private term {term!r}",
                )
            )
    return findings


def render(findings: list[Finding]) -> str:
    if not findings:
        return "History privacy scan: PASS\n"
    lines = ["History privacy scan: FAIL", "Findings:"]
    for finding in findings:
        lines.append(f"  - [{finding.kind}] {finding.location}: {finding.detail}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan reachable git history for private repo context.")
    parser.add_argument("--repo-root", default=".", help="Repository root to scan.")
    args = parser.parse_args(argv)

    repo = Path(args.repo_root).resolve()
    findings = [*scan_paths(repo), *scan_terms(repo)]
    print(render(findings), end="")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
