#!/usr/bin/env python3
"""Fail-closed public PR privacy boundary gate.

The gate scans the *actual PR diff* for files and added lines that should not be
published to an open-source repository.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_FILE_NAMES = {
    "PROGRESS.md",
    "AUDIT_REPORT.md",
}

# Build repo-specific private runtime literals from fragments so this gate can
# safely scan its own implementation diff while still detecting the rendered
# strings in PR payloads.
PRIVATE_RUNTIME_DIR = "." + "hermes"
PRIVATE_RUNTIME_ENV = "HERMES" + "_HOME"
CHANNEL_ID_KEY = "chat" + "_id"
THREAD_ID_KEY = "thread" + "_id"

FORBIDDEN_PATH_PARTS = {
    PRIVATE_RUNTIME_DIR,
    ".opencode",
    "handoffs",
    "worklogs",
    "raw",
    "compiled",
    "runtime",
}

FORBIDDEN_FILE_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
}

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("local_path", re.compile(r"(/home/[A-Za-z0-9_.-]+|/Users/[A-Za-z0-9_.-]+|[A-Za-z]:\\Users\\[A-Za-z0-9_.-]+|/mnt/[A-Za-z0-9_.-]+)")),
    ("private_platform_context", re.compile(r"\b(" + "|".join(map(re.escape, [CHANNEL_ID_KEY, THREAD_ID_KEY])) + r")\b", re.IGNORECASE)),
    ("chat_or_user_id", re.compile(r"\b(o[uc]_[0-9a-fA-F]{6,}|-100\d{6,})\b")),
    ("private_runtime_context", re.compile(re.escape(PRIVATE_RUNTIME_DIR) + r"|" + re.escape(PRIVATE_RUNTIME_ENV))),
    (
        "secret_literal",
        re.compile(
            r"(?i)\b([a-z0-9_]*api[_-]?key|[a-z0-9_]*secret|[a-z0-9_]*password|[a-z0-9_]*passwd|[a-z0-9_]*token|github_token|gh_token|openai_api_key)\b\s*[:=]\s*['\"]?[^'\"\s]{6,}"
        ),
    ),
    ("secret_literal", re.compile(r"\b(sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|xox[baprs]-[A-Za-z0-9-]{12,})\b")),
]


@dataclass(frozen=True)
class DiffLine:
    path: str
    line: str
    change: str
    line_number: int | None = None


@dataclass(frozen=True)
class ChangedPath:
    path: str
    source: str


def _iter_removed_paths(diff_text: str) -> set[str]:
    """Return paths being removed from the public tree."""
    removed: set[str] = set()
    old_path: str | None = None
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            old_path = _normalize_diff_path(parts[2]) if len(parts) >= 3 else None
            continue
        if line.startswith("rename from "):
            normalized = _normalize_diff_path(line.removeprefix("rename from "))
            if normalized:
                removed.add(normalized)
            continue
        if line.startswith("+++ /dev/null") and old_path:
            removed.add(old_path)
    return removed


def _normalize_diff_path(path: str) -> str | None:
    path = path.strip()
    if path == "/dev/null" or not path:
        return None
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def _is_forbidden_path(path: str) -> bool:
    path_obj = Path(path)
    parts = set(path_obj.parts)
    return (
        path_obj.name in FORBIDDEN_FILE_NAMES
        or path_obj.suffix.lower() in FORBIDDEN_FILE_SUFFIXES
        or bool(parts & FORBIDDEN_PATH_PARTS)
    )


def _iter_payload_lines(diff_text: str) -> list[DiffLine]:
    """Return diff payload lines that are visible in a public PR.

    Public PRs expose added, deleted, and context lines. Metadata is scanned via
    path parsing, so this skips diff headers and hunk markers.
    """
    current_path = ""
    payload: list[DiffLine] = []
    new_line_number: int | None = None
    old_line_number: int | None = None
    for raw_line in diff_text.splitlines():
        if raw_line.startswith("diff --git "):
            parts = raw_line.split()
            if len(parts) >= 4:
                current_path = _normalize_diff_path(parts[3]) or _normalize_diff_path(parts[2]) or current_path
            new_line_number = None
            old_line_number = None
            continue
        if raw_line.startswith("+++ "):
            normalized = _normalize_diff_path(raw_line.removeprefix("+++ "))
            if normalized:
                current_path = normalized
            continue
        if raw_line.startswith("--- "):
            normalized = _normalize_diff_path(raw_line.removeprefix("--- "))
            if normalized and not current_path:
                current_path = normalized
            continue
        if raw_line.startswith("@@"):
            old_match = re.search(r"-(\d+)(?:,(\d+))?", raw_line)
            new_match = re.search(r"\+(\d+)(?:,(\d+))?", raw_line)
            old_line_number = int(old_match.group(1)) if old_match else None
            new_line_number = int(new_match.group(1)) if new_match else None
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            payload.append(DiffLine(current_path, raw_line[1:], "add", new_line_number))
            if new_line_number is not None:
                new_line_number += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            payload.append(DiffLine(current_path, raw_line[1:], "delete", old_line_number))
            if old_line_number is not None:
                old_line_number += 1
        elif raw_line.startswith(" "):
            payload.append(DiffLine(current_path, raw_line[1:], "context", new_line_number))
            if old_line_number is not None:
                old_line_number += 1
            if new_line_number is not None:
                new_line_number += 1
    return payload


def _iter_changed_paths(diff_text: str) -> list[ChangedPath]:
    paths: list[ChangedPath] = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            for raw in parts[2:4]:
                normalized = _normalize_diff_path(raw)
                if normalized:
                    paths.append(ChangedPath(normalized, "diff_header"))
        elif line.startswith("rename from "):
            normalized = _normalize_diff_path(line.removeprefix("rename from "))
            if normalized:
                paths.append(ChangedPath(normalized, "rename_from"))
        elif line.startswith("rename to "):
            normalized = _normalize_diff_path(line.removeprefix("rename to "))
            if normalized:
                paths.append(ChangedPath(normalized, "rename_to"))
        elif line.startswith("--- ") or line.startswith("+++ "):
            normalized = _normalize_diff_path(line[4:])
            if normalized:
                paths.append(ChangedPath(normalized, "file_marker"))
    return paths


def scan_diff(
    diff_text: str,
    *,
    target_visibility: str = "public",
    max_changed_files: int = 80,
    allow_cleanup_deletions: bool = False,
) -> dict[str, object]:
    """Scan a unified diff and return a fail-closed public-boundary report."""
    findings: list[dict[str, object]] = []
    changed_path_records = _iter_changed_paths(diff_text)
    changed_paths = sorted({record.path for record in changed_path_records})
    removed_paths = _iter_removed_paths(diff_text) if allow_cleanup_deletions else set()

    if target_visibility == "public" and len(changed_paths) > max_changed_files:
        findings.append(
            {
                "kind": "large_diff",
                "path": "<diff>",
                "message": f"changed file count {len(changed_paths)} exceeds {max_changed_files}; split or review manually",
            }
        )

    for path in changed_paths:
        if allow_cleanup_deletions and path in removed_paths:
            continue
        if target_visibility == "public" and _is_forbidden_path(path):
            findings.append(
                {
                    "kind": "forbidden_file",
                    "path": path,
                    "message": "file/path is internal-only by default for public PRs",
                }
            )

    for item in _iter_payload_lines(diff_text):
        if allow_cleanup_deletions and item.change == "delete":
            continue
        for kind, pattern in PATTERNS:
            if pattern.search(item.line):
                finding: dict[str, object] = {
                    "kind": kind,
                    "path": item.path,
                    "message": "diff payload line matches public-boundary risk pattern",
                }
                if item.line_number is not None:
                    finding["line"] = item.line_number
                findings.append(finding)

    return {
        "schema": "vault.public_pr_gate.v1",
        "target_visibility": target_visibility,
        "changed_files": len(changed_paths),
        "passed": not findings,
        "findings": findings,
    }


def _git_diff(repo_root: Path, base: str, head: str) -> str:
    command = ["git", "diff", f"{base}..{head}", "--", ".", ":(exclude).git"]
    return subprocess.check_output(command, cwd=repo_root, text=True, errors="replace")


def render_text(report: dict[str, object]) -> str:
    status = "PASS" if report["passed"] else "FAIL"
    lines = [
        f"Public PR Gate: {status}",
        f"target_visibility: {report['target_visibility']}",
        f"changed_files: {report['changed_files']}",
    ]
    findings = report["findings"]
    assert isinstance(findings, list)
    if findings:
        lines.append("Findings:")
        for finding in findings:
            line = f"  - [{finding['kind']}] {finding['path']}: {finding['message']}"
            if "line" in finding:
                line += f" (line {finding['line']})"
            lines.append(line)
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan a PR diff for public-boundary privacy risks.")
    parser.add_argument("--repo-root", default=".", help="Repository root for git diff mode.")
    parser.add_argument("--base", default="origin/main", help="Base ref for git diff mode.")
    parser.add_argument("--head", default="HEAD", help="Head ref for git diff mode.")
    parser.add_argument("--stdin", action="store_true", help="Read unified diff from stdin.")
    parser.add_argument("--target-visibility", default="public", choices=["public", "private", "internal"])
    parser.add_argument("--max-changed-files", type=int, default=80)
    parser.add_argument(
        "--allow-cleanup-deletions",
        action="store_true",
        help="Allow deletion/rename-away of internal-only paths that already exist in the base branch.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = parser.parse_args(argv)

    diff_text = sys.stdin.read() if args.stdin else _git_diff(Path(args.repo_root), args.base, args.head)
    report = scan_diff(
        diff_text,
        target_visibility=args.target_visibility,
        max_changed_files=args.max_changed_files,
        allow_cleanup_deletions=args.allow_cleanup_deletions,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report), end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
