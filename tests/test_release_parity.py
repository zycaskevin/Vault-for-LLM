from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_release_parity.py"


def load_checker_module():
    spec = importlib.util.spec_from_file_location("check_release_parity", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_release_files(root: Path, *, pyproject: str, vault: str, changelog: str) -> None:
    (root / "vault").mkdir()
    (root / "pyproject.toml").write_text(
        f"""
[build-system]
requires = ["setuptools"]

[project]
name = "vault-for-llm"
version = "{pyproject}"
""".lstrip(),
        encoding="utf-8",
    )
    (root / "vault" / "__init__.py").write_text(
        f'"""Test package."""\n\n__version__ = "{vault}"\n',
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(
        f"""
# Changelog

## [{changelog}] — 2026-05-18

### Changed
- Test entry.

## [0.1.0] — 2026-01-01
""".lstrip(),
        encoding="utf-8",
    )


def run_checker(root: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env.pop("GITHUB_REF_NAME", None)
    merged_env.pop("GITHUB_REF_TYPE", None)
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        check=False,
        text=True,
        capture_output=True,
        env=merged_env,
    )


def test_accepts_matching_release_tag(tmp_path: Path) -> None:
    write_release_files(tmp_path, pyproject="0.4.3", vault="0.4.3", changelog="0.4.3")

    result = run_checker(tmp_path, "--tag", "v0.4.3")

    assert result.returncode == 0, result.stderr
    assert "Release parity check passed" in result.stdout
    assert "release tag: 0.4.3" in result.stdout
    assert "pyproject.toml [project].version: 0.4.3" in result.stdout
    assert "vault.__version__: 0.4.3" in result.stdout
    assert "CHANGELOG.md top entry: 0.4.3" in result.stdout


def test_explicit_tag_wins_over_branch_environment(tmp_path: Path) -> None:
    write_release_files(tmp_path, pyproject="0.4.3", vault="0.4.3", changelog="0.4.3")

    result = run_checker(
        tmp_path,
        "--tag",
        "v0.4.3",
        env={"GITHUB_REF_TYPE": "branch", "GITHUB_REF_NAME": "main"},
    )

    assert result.returncode == 0, result.stderr
    assert "release tag: 0.4.3" in result.stdout


def test_reports_all_version_mismatches_against_tag(tmp_path: Path) -> None:
    write_release_files(tmp_path, pyproject="0.4.2", vault="0.4.1", changelog="0.4.0")

    result = run_checker(tmp_path, "--tag", "v0.4.3")

    assert result.returncode == 1
    assert "Release parity check failed" in result.stderr
    assert (
        "pyproject.toml [project].version mismatch: expected 0.4.3 from release tag, found 0.4.2"
        in result.stderr
    )
    assert "vault.__version__ mismatch: expected 0.4.3 from release tag, found 0.4.1" in result.stderr
    assert "CHANGELOG.md top entry mismatch: expected 0.4.3 from release tag, found 0.4.0" in result.stderr


def test_uses_github_ref_name_for_github_tag_runs(tmp_path: Path) -> None:
    write_release_files(tmp_path, pyproject="0.4.3", vault="0.4.3", changelog="0.4.3")

    result = run_checker(tmp_path, env={"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": "v0.4.3"})

    assert result.returncode == 0, result.stderr
    assert "release tag: 0.4.3" in result.stdout


def test_github_branch_ref_name_uses_local_no_tag_parity(tmp_path: Path) -> None:
    write_release_files(tmp_path, pyproject="0.4.3", vault="0.4.3", changelog="0.4.3")

    result = run_checker(tmp_path, env={"GITHUB_REF_TYPE": "branch", "GITHUB_REF_NAME": "main"})

    assert result.returncode == 0, result.stderr
    assert "release tag: not provided; checked local version file parity" in result.stdout
    assert "release tag: 0.4.3" not in result.stdout


def test_accepts_full_refs_tags_env_value(tmp_path: Path) -> None:
    write_release_files(tmp_path, pyproject="0.4.3", vault="0.4.3", changelog="0.4.3")

    result = run_checker(tmp_path, env={"GITHUB_REF_NAME": "refs/tags/v0.4.3"})

    assert result.returncode == 0, result.stderr
    assert "release tag: 0.4.3" in result.stdout


def test_local_mode_without_tag_checks_file_parity(tmp_path: Path) -> None:
    write_release_files(tmp_path, pyproject="0.4.3", vault="0.4.3", changelog="0.4.3")

    result = run_checker(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "release tag: not provided; checked local version file parity" in result.stdout


def test_local_mode_without_tag_reports_file_drift(tmp_path: Path) -> None:
    write_release_files(tmp_path, pyproject="0.4.3", vault="0.4.2", changelog="0.4.1")

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert (
        "vault.__version__ mismatch: expected 0.4.3 from pyproject.toml [project].version, found 0.4.2"
        in result.stderr
    )
    assert (
        "CHANGELOG.md top entry mismatch: expected 0.4.3 from pyproject.toml [project].version, found 0.4.1"
        in result.stderr
    )


def test_rejects_unreleased_section_before_release_entry(tmp_path: Path) -> None:
    write_release_files(tmp_path, pyproject="0.4.3", vault="0.4.3", changelog="0.4.3")
    (tmp_path / "CHANGELOG.md").write_text(
        """
# Changelog

## [Unreleased]

### Changed
- Pending change.

## [0.4.3] — 2026-05-18

### Changed
- Release entry.
""".lstrip(),
        encoding="utf-8",
    )

    result = run_checker(tmp_path, "--tag", "v0.4.3")

    assert result.returncode == 1
    assert "Top CHANGELOG.md section must be a semver release heading" in result.stderr
    assert "## [Unreleased]" in result.stderr


def test_python310_pyproject_fallback_reads_project_version(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.example]
version = "9.9.9"

[project]
name = "vault-for-llm"
version = "0.4.3"
""".lstrip(),
        encoding="utf-8",
    )
    checker = load_checker_module()
    monkeypatch.setattr(checker, "tomllib", None)

    assert checker.read_pyproject_version(tmp_path) == "0.4.3"


def test_rejects_invalid_tag_format_before_file_reads(tmp_path: Path) -> None:
    result = run_checker(tmp_path, "--tag", "0.4.3")

    assert result.returncode == 1
    assert "Release tag must match vX.Y.Z" in result.stderr
    assert "'0.4.3'" in result.stderr
    assert "Unable to read" not in result.stderr
