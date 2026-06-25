#!/usr/bin/env python3
"""Keep oversized Python modules from quietly growing.

The gate is intentionally baseline-based: existing large modules can stay at
their recorded size while the project pays down the split work, but they cannot
grow without an explicit baseline update.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = PROJECT_ROOT / "scripts" / "module_size_baseline.json"
DEFAULT_GLOBS = ("vault/*.py",)


@dataclass(frozen=True)
class ModuleSize:
    path: str
    lines: int
    allowed: int
    source: str


class ModuleSizeGateError(Exception):
    """Raised when the module-size gate cannot run."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fail when Python modules exceed size limits.")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT, help="Repository root.")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="JSON file with default_max_lines and per-file baseline limits.",
    )
    parser.add_argument(
        "--glob",
        action="append",
        dest="globs",
        help="File glob to scan relative to root. Can be repeated. Defaults to vault/*.py.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON report instead of human-readable output.",
    )
    return parser.parse_args(argv)


def _repo_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def load_baseline(path: Path) -> tuple[int, dict[str, int]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ModuleSizeGateError(f"Unable to read baseline {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ModuleSizeGateError(f"Unable to parse baseline {path}: {exc}") from exc

    default_max = raw.get("default_max_lines", 1200)
    files = raw.get("files", {})
    if not isinstance(default_max, int) or default_max <= 0:
        raise ModuleSizeGateError("baseline default_max_lines must be a positive integer")
    if not isinstance(files, dict):
        raise ModuleSizeGateError("baseline files must be an object")

    normalized: dict[str, int] = {}
    for key, value in files.items():
        if not isinstance(key, str) or not isinstance(value, int) or value <= 0:
            raise ModuleSizeGateError("baseline file entries must map path strings to positive integers")
        normalized[key] = value
    return default_max, normalized


def count_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def collect_modules(root: Path, globs: Sequence[str]) -> list[Path]:
    paths: set[Path] = set()
    for pattern in globs:
        paths.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(paths)


def check_modules(root: Path, baseline_path: Path, globs: Sequence[str]) -> dict[str, object]:
    root = root.resolve()
    baseline_path = baseline_path if baseline_path.is_absolute() else root / baseline_path
    default_max, baselines = load_baseline(baseline_path)
    modules: list[ModuleSize] = []
    findings: list[dict[str, object]] = []

    for path in collect_modules(root, globs):
        rel = _repo_path(root, path)
        lines = count_lines(path)
        allowed = baselines.get(rel, default_max)
        source = "baseline" if rel in baselines else "default"
        modules.append(ModuleSize(rel, lines, allowed, source))
        if lines > allowed:
            findings.append(
                {
                    "path": rel,
                    "lines": lines,
                    "allowed": allowed,
                    "source": source,
                    "message": f"{rel} has {lines} lines; allowed {allowed} from {source}",
                }
            )

    unused_baselines = sorted(path for path in baselines if not (root / path).exists())
    return {
        "ok": not findings and not unused_baselines,
        "default_max_lines": default_max,
        "module_count": len(modules),
        "modules": [module.__dict__ for module in sorted(modules, key=lambda item: item.lines, reverse=True)],
        "findings": findings,
        "unused_baselines": unused_baselines,
    }


def render(report: dict[str, object]) -> str:
    findings = report["findings"]
    unused = report["unused_baselines"]
    if not findings and not unused:
        top = report["modules"][:8]  # type: ignore[index]
        lines = [
            "Module size gate: PASS",
            f"  scanned modules: {report['module_count']}",
            f"  default max lines: {report['default_max_lines']}",
            "  largest modules:",
        ]
        for module in top:
            lines.append(
                f"    - {module['path']}: {module['lines']} lines "
                f"(allowed {module['allowed']} via {module['source']})"
            )
        return "\n".join(lines) + "\n"

    lines = ["Module size gate: FAIL"]
    for finding in findings:  # type: ignore[union-attr]
        lines.append(f"  - {finding['message']}")
    for path in unused:  # type: ignore[union-attr]
        lines.append(f"  - unused baseline entry: {path}")
    lines.append("Split the module or update the baseline with an explicit review note.")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    globs = tuple(args.globs or DEFAULT_GLOBS)
    try:
        report = check_modules(args.root, args.baseline, globs)
    except ModuleSizeGateError as exc:
        print(f"Module size gate failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render(report), end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
