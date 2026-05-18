#!/usr/bin/env python3
"""Check release tag, package version, and changelog version parity.

This script is intentionally local-only: it reads repository files and optional
GitHub Actions environment variables, and never performs network access.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from pathlib import Path
from typing import Mapping, Sequence

try:  # Python 3.11+
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - exercised only on Python 3.10
    tomllib = None  # type: ignore[assignment]


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)$")
PROJECT_HEADER_RE = re.compile(r"^\s*\[([^]]+)]\s*$")
PROJECT_VERSION_RE = re.compile(r'^\s*version\s*=\s*["\'](?P<version>[^"\']+)["\']\s*(?:#.*)?$')
CHANGELOG_VERSION_RE = re.compile(r"^##\s+\[?(?P<version>\d+\.\d+\.\d+)\]?(?:\s|$)")
CHANGELOG_SECTION_RE = re.compile(r"^##(?!#)(?:\s+.*)?$")


class ReleaseParityError(Exception):
    """Raised when release parity cannot be verified."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify release tag, pyproject version, vault.__version__, and changelog parity."
    )
    parser.add_argument(
        "--tag",
        help="Release tag to verify, for example v0.4.3. Defaults to GITHUB_REF_NAME when set.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=PROJECT_ROOT,
        help="Repository root to check. Defaults to the parent of this script.",
    )
    return parser.parse_args(argv)


def normalize_tag(raw_tag: str | None) -> str | None:
    if not raw_tag:
        return None
    tag = raw_tag.strip()
    if tag.startswith("refs/tags/"):
        tag = tag.removeprefix("refs/tags/")
    return tag


def version_from_tag(tag: str) -> str:
    match = TAG_RE.fullmatch(tag)
    if not match:
        raise ReleaseParityError(
            f"Release tag must match vX.Y.Z (for example v0.4.3); found {tag!r}."
        )
    return match.group("version")


def read_pyproject_version(root: Path) -> str:
    pyproject_path = root / "pyproject.toml"
    try:
        raw = pyproject_path.read_bytes()
    except OSError as exc:
        raise ReleaseParityError(f"Unable to read {pyproject_path}: {exc}") from exc

    if tomllib is not None:
        try:
            data = tomllib.loads(raw.decode("utf-8"))
            version = data.get("project", {}).get("version")
        except Exception as exc:  # tomllib.TOMLDecodeError subclasses ValueError
            raise ReleaseParityError(f"Unable to parse {pyproject_path}: {exc}") from exc
        if isinstance(version, str) and version:
            return version
        raise ReleaseParityError(f"Missing [project].version in {pyproject_path}.")

    # Python 3.10 fallback without adding a runtime/dev dependency solely for this script.
    in_project = False
    for line in raw.decode("utf-8").splitlines():
        header = PROJECT_HEADER_RE.match(line)
        if header:
            in_project = header.group(1) == "project"
            continue
        if in_project:
            match = PROJECT_VERSION_RE.match(line)
            if match:
                return match.group("version")
    raise ReleaseParityError(f"Missing [project].version in {pyproject_path}.")


def read_vault_version(root: Path) -> str:
    init_path = root / "vault" / "__init__.py"
    try:
        tree = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
    except OSError as exc:
        raise ReleaseParityError(f"Unable to read {init_path}: {exc}") from exc
    except SyntaxError as exc:
        raise ReleaseParityError(f"Unable to parse {init_path}: {exc}") from exc

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
        raise ReleaseParityError(f"vault.__version__ in {init_path} must be a string literal.")
    raise ReleaseParityError(f"Missing vault.__version__ in {init_path}.")


def read_changelog_top_version(root: Path) -> str:
    changelog_path = root / "CHANGELOG.md"
    try:
        lines = changelog_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ReleaseParityError(f"Unable to read {changelog_path}: {exc}") from exc

    for line in lines:
        if not CHANGELOG_SECTION_RE.match(line):
            continue
        match = CHANGELOG_VERSION_RE.match(line)
        if match:
            return match.group("version")
        raise ReleaseParityError(
            "Top CHANGELOG.md section must be a semver release heading like "
            f"'## [0.4.3]' or '## 0.4.3'; found {line!r}."
        )
    raise ReleaseParityError(f"Missing top version entry in {changelog_path}.")


def collect_versions(root: Path, tag: str | None) -> dict[str, str]:
    tag_version = version_from_tag(tag) if tag is not None else None
    versions = {
        "pyproject.toml [project].version": read_pyproject_version(root),
        "vault.__version__": read_vault_version(root),
        "CHANGELOG.md top entry": read_changelog_top_version(root),
    }
    if tag_version is not None:
        versions = {"release tag": tag_version, **versions}
    return versions


def parity_errors(versions: Mapping[str, str], expected_source: str) -> list[str]:
    expected = versions[expected_source]
    errors: list[str] = []
    for source, version in versions.items():
        if version != expected:
            errors.append(
                f"{source} mismatch: expected {expected} from {expected_source}, found {version}."
            )
    return errors


def check_release_parity(root: Path, tag: str | None = None) -> dict[str, str]:
    root = root.resolve()
    normalized_tag = normalize_tag(tag)
    versions = collect_versions(root, normalized_tag)
    expected_source = "release tag" if normalized_tag is not None else "pyproject.toml [project].version"
    errors = parity_errors(versions, expected_source)
    if errors:
        raise ReleaseParityError("\n".join(errors))
    return versions


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    tag = args.tag if args.tag is not None else os.environ.get("GITHUB_REF_NAME")
    try:
        versions = check_release_parity(args.root, tag)
    except ReleaseParityError as exc:
        print("Release parity check failed:", file=sys.stderr)
        for line in str(exc).splitlines():
            print(f"  - {line}", file=sys.stderr)
        return 1

    print("Release parity check passed:")
    if normalize_tag(tag) is None:
        print("  release tag: not provided; checked local version file parity")
    for source, version in versions.items():
        print(f"  {source}: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
