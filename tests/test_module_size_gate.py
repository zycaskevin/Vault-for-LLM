from __future__ import annotations

import json
from pathlib import Path

from scripts import module_size_gate


def write_lines(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join("x = 1" for _ in range(count)) + "\n", encoding="utf-8")


def write_baseline(path: Path, *, default: int, files: dict[str, int] | None = None) -> None:
    path.write_text(
        json.dumps({"default_max_lines": default, "files": files or {}}, indent=2),
        encoding="utf-8",
    )


def test_module_size_gate_passes_modules_under_default(tmp_path: Path):
    baseline = tmp_path / "baseline.json"
    write_baseline(baseline, default=5)
    write_lines(tmp_path / "vault" / "small.py", 5)

    report = module_size_gate.check_modules(tmp_path, baseline, ("vault/*.py",))

    assert report["ok"] is True
    assert report["findings"] == []


def test_module_size_gate_blocks_new_module_over_default(tmp_path: Path):
    baseline = tmp_path / "baseline.json"
    write_baseline(baseline, default=5)
    write_lines(tmp_path / "vault" / "large.py", 6)

    report = module_size_gate.check_modules(tmp_path, baseline, ("vault/*.py",))

    assert report["ok"] is False
    assert report["findings"][0]["path"] == "vault/large.py"
    assert report["findings"][0]["allowed"] == 5


def test_module_size_gate_allows_baselined_large_module_but_blocks_growth(tmp_path: Path):
    baseline = tmp_path / "baseline.json"
    write_baseline(baseline, default=5, files={"vault/legacy.py": 10})
    write_lines(tmp_path / "vault" / "legacy.py", 10)

    report = module_size_gate.check_modules(tmp_path, baseline, ("vault/*.py",))
    assert report["ok"] is True

    write_lines(tmp_path / "vault" / "legacy.py", 11)
    grown = module_size_gate.check_modules(tmp_path, baseline, ("vault/*.py",))

    assert grown["ok"] is False
    assert grown["findings"][0]["source"] == "baseline"


def test_module_size_gate_flags_unused_baseline_entries(tmp_path: Path):
    baseline = tmp_path / "baseline.json"
    write_baseline(baseline, default=5, files={"vault/missing.py": 10})
    write_lines(tmp_path / "vault" / "small.py", 4)

    report = module_size_gate.check_modules(tmp_path, baseline, ("vault/*.py",))

    assert report["ok"] is False
    assert report["unused_baselines"] == ["vault/missing.py"]
