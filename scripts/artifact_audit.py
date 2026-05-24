#!/usr/bin/env python3
"""Audit generated/runtime artifacts in a repository.

This script is intentionally read-only. It classifies common generated files so
agents can clean caches without touching source-of-truth files.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

SAFE_DELETE_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".tox",
    "htmlcov",
}

SAFE_DELETE_FILE_NAMES = {
    ".coverage",
    "coverage.xml",
}

SAFE_DELETE_SUFFIXES = {
    ".pyc",
    ".pyo",
}

SAFE_DELETE_DIR_SUFFIXES = {
    ".egg-info",
}

REVIEW_DIR_NAMES = {
    ".opencode",
    "node_modules",
    "graphify-out",
    "build",
    "dist",
}

ARCHIVE_DIR_NAMES = {
    "handoffs",
}

SKIP_DIR_NAMES = {
    ".git",
}


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _relative(path: Path, root: Path) -> str:
    rel = path.relative_to(root).as_posix()
    return rel or "."


def _count_path(path: Path) -> tuple[int, int]:
    """Return (bytes, file_count) without following directory symlinks."""
    if path.is_symlink() or path.is_file():
        try:
            return path.stat().st_size, 1
        except OSError:
            return 0, 0
    total_bytes = 0
    total_files = 0
    for current_root, dirs, files in os.walk(path):
        dirs[:] = [name for name in dirs if name not in SKIP_DIR_NAMES]
        for filename in files:
            file_path = Path(current_root) / filename
            try:
                total_bytes += file_path.stat().st_size
                total_files += 1
            except OSError:
                continue
    return total_bytes, total_files


def _artifact_record(path: Path, root: Path, category: str, action: str) -> dict[str, object]:
    size, files = _count_path(path)
    return {
        "path": _relative(path, root),
        "category": category,
        "action": action,
        "bytes": size,
        "files": files,
    }


def _is_safe_delete_dir(path: Path, root: Path) -> bool:
    name = path.name
    if name in SAFE_DELETE_DIR_NAMES:
        return True
    if any(name.endswith(suffix) for suffix in SAFE_DELETE_DIR_SUFFIXES):
        return True
    # Graph caches are large, generated, and reproducible; the full graph output
    # may be valuable, so only cache subdirectories are safe by default.
    parts = path.relative_to(root).parts
    return len(parts) >= 2 and parts[-1] == "cache" and parts[-2] == "graphify-out"


def _is_safe_delete_file(path: Path) -> bool:
    return path.name in SAFE_DELETE_FILE_NAMES or path.suffix in SAFE_DELETE_SUFFIXES


def _top_level(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return "."
    return rel.parts[0] if rel.parts else "."


def audit_repo(root: Path | str = ".") -> dict[str, object]:
    """Return a read-only artifact audit report for *root*."""
    root_path = Path(root).resolve()
    if not root_path.exists():
        raise FileNotFoundError(root_path)
    if not root_path.is_dir():
        raise NotADirectoryError(root_path)

    safe_delete: list[dict[str, object]] = []
    needs_review: list[dict[str, object]] = []
    archive_candidates: list[dict[str, object]] = []
    file_count_by_top: dict[str, int] = {}
    bytes_by_top: dict[str, int] = {}

    consumed: set[Path] = set()

    for current_root, dirs, files in os.walk(root_path):
        current = Path(current_root)
        dirs[:] = [name for name in dirs if name not in SKIP_DIR_NAMES]

        pruned_dirs: set[str] = set()
        for dirname in list(dirs):
            path = current / dirname
            resolved = path.resolve()
            if any(_is_relative_to(resolved, item) for item in consumed):
                pruned_dirs.add(dirname)
                continue
            if _is_safe_delete_dir(resolved, root_path):
                safe_delete.append(_artifact_record(resolved, root_path, "generated_cache", "delete_safe"))
                consumed.add(resolved)
                pruned_dirs.add(dirname)
            elif dirname in REVIEW_DIR_NAMES:
                needs_review.append(_artifact_record(resolved, root_path, "large_or_tool_runtime", "review"))
                if dirname != "graphify-out":
                    consumed.add(resolved)
                    pruned_dirs.add(dirname)
            elif dirname in ARCHIVE_DIR_NAMES:
                archive_candidates.append(_artifact_record(resolved, root_path, "handoff_or_report", "archive"))
                consumed.add(resolved)
                pruned_dirs.add(dirname)
        if pruned_dirs:
            dirs[:] = [dirname for dirname in dirs if dirname not in pruned_dirs]

        for filename in files:
            path = current / filename
            resolved = path.resolve()
            if any(_is_relative_to(resolved, item) for item in consumed):
                continue
            if _is_safe_delete_file(resolved):
                safe_delete.append(_artifact_record(resolved, root_path, "generated_cache", "delete_safe"))

            try:
                size = resolved.stat().st_size
            except OSError:
                size = 0
            top = _top_level(resolved, root_path)
            file_count_by_top[top] = file_count_by_top.get(top, 0) + 1
            bytes_by_top[top] = bytes_by_top.get(top, 0) + size

    def sort_key(item: dict[str, object]) -> tuple[int, str]:
        return int(item["bytes"]), str(item["path"])

    safe_delete.sort(key=sort_key, reverse=True)
    needs_review.sort(key=sort_key, reverse=True)
    archive_candidates.sort(key=sort_key, reverse=True)

    summary = {
        "safe_delete_files": sum(int(item["files"]) for item in safe_delete),
        "safe_delete_bytes": sum(int(item["bytes"]) for item in safe_delete),
        "needs_review_files": sum(int(item["files"]) for item in needs_review),
        "needs_review_bytes": sum(int(item["bytes"]) for item in needs_review),
        "archive_candidate_files": sum(int(item["files"]) for item in archive_candidates),
        "archive_candidate_bytes": sum(int(item["bytes"]) for item in archive_candidates),
    }

    hotspots = [
        {"path": path, "files": file_count_by_top[path], "bytes": bytes_by_top.get(path, 0)}
        for path in sorted(file_count_by_top, key=lambda key: file_count_by_top[key], reverse=True)
    ]

    return {
        "schema": "vault.repo_artifact_audit.v1",
        "root": str(root_path),
        "summary": summary,
        "safe_delete": safe_delete,
        "needs_review": needs_review,
        "archive_candidates": archive_candidates,
        "file_count_hotspots": hotspots[:30],
    }


def _human_bytes(value: int) -> str:
    units = ["B", "KiB", "MiB", "GiB"]
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} GiB"


def render_text(report: dict[str, object]) -> str:
    summary = report["summary"]
    assert isinstance(summary, dict)
    lines = [
        "Repo Artifact Audit",
        f"root: {report['root']}",
        "",
        "Safe-to-delete generated artifacts:",
        f"  files: {summary['safe_delete_files']}",
        f"  size : {_human_bytes(int(summary['safe_delete_bytes']))}",
        "",
        "Needs review before deletion:",
        f"  files: {summary['needs_review_files']}",
        f"  size : {_human_bytes(int(summary['needs_review_bytes']))}",
    ]
    safe_delete = report["safe_delete"]
    assert isinstance(safe_delete, list)
    if safe_delete:
        lines.append("\nTop safe-delete candidates:")
        for item in safe_delete[:20]:
            lines.append(f"  - {item['path']} ({item['files']} files, {_human_bytes(int(item['bytes']))})")
    needs_review = report["needs_review"]
    assert isinstance(needs_review, list)
    if needs_review:
        lines.append("\nReview candidates:")
        for item in needs_review[:20]:
            lines.append(f"  - {item['path']} ({item['files']} files, {_human_bytes(int(item['bytes']))})")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit generated/runtime repository artifacts.")
    parser.add_argument("--root", default=".", help="Repository root to audit.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = parser.parse_args(argv)

    report = audit_repo(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report), end="")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
