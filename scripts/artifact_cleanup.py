#!/usr/bin/env python3
"""Clean safe generated artifacts after repository development work."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

if __package__ in {None, ""}:  # Support `python scripts/artifact_cleanup.py`.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import artifact_audit


def _resolve_under_root(root: Path, relative_path: str) -> Path:
    root = root.resolve()
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"refusing to operate outside root: {relative_path}") from exc
    if target == root:
        raise ValueError("refusing to delete repository root")
    return target


def _delete_path(path: Path) -> tuple[int, int]:
    bytes_before, files_before = artifact_audit._count_path(path)  # internal helper, deterministic
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()
    return bytes_before, files_before


def cleanup_repo(
    root: Path | str = ".",
    *,
    execute: bool = False,
    include_large: bool = False,
) -> dict[str, object]:
    """Plan or execute cleanup.

    By default this is a dry-run. `execute=True` deletes only safe generated
    artifacts. `include_large` is intentionally accepted for future extension,
    but current behavior still keeps review-only artifacts untouched.
    """
    root_path = Path(root).resolve()
    report = artifact_audit.audit_repo(root_path)
    safe_items = list(report["safe_delete"])
    review_items = list(report["needs_review"])
    archive_items = list(report["archive_candidates"])

    deleted: list[dict[str, object]] = []
    skipped_missing: list[str] = []

    if execute:
        for item in safe_items:
            rel = str(item["path"])
            target = _resolve_under_root(root_path, rel)
            if not target.exists() and not target.is_symlink():
                skipped_missing.append(rel)
                continue
            deleted_bytes, deleted_files = _delete_path(target)
            deleted.append(
                {
                    "path": rel,
                    "bytes": deleted_bytes,
                    "files": deleted_files,
                    "action": "deleted",
                }
            )

    summary = {
        "mode": "execute" if execute else "dry_run",
        "include_large": include_large,
        "would_delete_files": sum(int(item["files"]) for item in safe_items),
        "would_delete_bytes": sum(int(item["bytes"]) for item in safe_items),
        "deleted_files": sum(int(item["files"]) for item in deleted),
        "deleted_bytes": sum(int(item["bytes"]) for item in deleted),
        "needs_review_files": sum(int(item["files"]) for item in review_items),
        "archive_candidate_files": sum(int(item["files"]) for item in archive_items),
    }

    return {
        "schema": "vault.repo_artifact_cleanup.v1",
        "root": str(root_path),
        "summary": summary,
        "would_delete": safe_items,
        "deleted": deleted,
        "needs_review": review_items,
        "archive_candidates": archive_items,
        "skipped_missing": skipped_missing,
    }


def render_text(report: dict[str, object]) -> str:
    summary = report["summary"]
    assert isinstance(summary, dict)
    lines = [
        "Repo Artifact Cleanup",
        f"root: {report['root']}",
        f"mode: {summary['mode']}",
        f"would_delete_files: {summary['would_delete_files']}",
        f"deleted_files: {summary['deleted_files']}",
        f"needs_review_files: {summary['needs_review_files']}",
    ]
    if summary["mode"] == "dry_run":
        lines.append("No files were deleted. Re-run with --execute --safe-only to delete safe artifacts.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean safe generated repository artifacts.")
    parser.add_argument("--root", default=".", help="Repository root to clean.")
    parser.add_argument("--execute", action="store_true", help="Actually delete safe artifacts.")
    parser.add_argument("--safe-only", action="store_true", help="Required marker for safe-only deletion.")
    parser.add_argument("--include-large", action="store_true", help="Reserved; large artifacts still require review.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = parser.parse_args(argv)

    if args.execute and not args.safe_only:
        parser.error("--execute requires --safe-only")

    report = cleanup_repo(args.root, execute=args.execute, include_large=args.include_large)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report), end="")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
