"""Shared CLI runtime context helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path


_PROJECT_DIR_OVERRIDE: Path | None = None


def set_project_dir_override(path: Path | None) -> None:
    global _PROJECT_DIR_OVERRIDE
    _PROJECT_DIR_OVERRIDE = path


def get_project_dir_override() -> Path | None:
    return _PROJECT_DIR_OVERRIDE


def _json_print(payload, *, pretty: bool = False):
    print(json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None, default=str))


def find_project_dir() -> Path:
    """往上找含有 vault.db 或 raw/ 的目錄。"""
    if _PROJECT_DIR_OVERRIDE is not None:
        return _PROJECT_DIR_OVERRIDE
    cwd = Path.cwd()
    for d in [cwd] + list(cwd.parents):
        if (d / "vault.db").exists() or (d / "raw").is_dir():
            return d
    return cwd


def _arg_value(args, name: str, default=None):
    """Read argparse/Namespace values without letting MagicMock invent attrs."""
    return vars(args).get(name, default)


def _json_flags(args) -> tuple[bool, bool]:
    """Return explicit JSON/pretty flags for argparse-like namespaces."""
    pretty = _arg_value(args, "pretty", False) is True
    return (_arg_value(args, "json", False) is True or pretty, pretty)


def _extract_project_dir_arg(argv: list[str]) -> tuple[list[str], str | None]:
    """Extract --project-dir from anywhere in the CLI command.

    Most agents pass runtime-specific options after the subcommand, for example
    ``vault search "query" --project-dir /path``. argparse global options only
    work before the subcommand, so we normalize this option before parsing.
    """
    cleaned: list[str] = []
    project_dir: str | None = None
    i = 0
    while i < len(argv):
        item = argv[i]
        if item == "--project-dir":
            if i + 1 >= len(argv):
                print("error: --project-dir requires a value", file=sys.stderr)
                raise SystemExit(2)
            project_dir = argv[i + 1]
            i += 2
            continue
        if item.startswith("--project-dir="):
            project_dir = item.split("=", 1)[1]
            i += 1
            continue
        cleaned.append(item)
        i += 1
    return cleaned, project_dir


def _privacy_block_message(label: str, privacy: dict) -> str:
    findings = privacy.get("findings", [])
    kinds = ", ".join(
        sorted(
            {
                str(item.get("type", "secret"))
                for item in findings
                if item.get("severity") == "fail"
            }
        )
    )
    return f"privacy gate blocked {label}: {kinds or 'secret-like content'}"


def _enforce_cli_privacy(content: str, *, allow_private: bool, label: str) -> None:
    if allow_private:
        return
    from vault.privacy import scan_privacy

    privacy = scan_privacy(content)
    if privacy.get("status") != "fail":
        return
    print(f"❌ {_privacy_block_message(label, privacy)}", file=sys.stderr)
    print("   Use --allow-private only for explicit local/private vault ingestion.", file=sys.stderr)
    raise SystemExit(2)
