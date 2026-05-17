# P1 Release Readiness Report — Vault-for-LLM 0.4.1

**Generated:** 2026-05-17 11:05 CST  
**Scope:** local release readiness only  
**External side effects:** none — no PyPI upload, no git tag, no push, no GitHub release

---

## Verdict

**PASS for local release-readiness preparation.**

The repository is locally ready for a future manually approved `0.4.1` package release, subject to Arthur explicitly approving external release actions.

Do not publish from this report alone. A real release still requires:

1. clean git status on the exact release commit,
2. Arthur approval,
3. tag exact commit,
4. upload artifacts,
5. verify fresh PyPI install after upload.

---

## What changed in P1

### A1 — License metadata hygiene

Modernized Python package metadata:

- `pyproject.toml` now uses PEP 639 SPDX license string:
  - `license = "MIT"`
  - `license-files = ["LICENSE"]`
- Removed deprecated license classifier:
  - `License :: OSI Approved :: MIT License`
- Raised build backend requirement:
  - `setuptools>=77.0.3`
- Updated `CHANGELOG.md` with the metadata cleanup.

### A2 — Release checklist and README parity

Added:

- `docs/release_checklist_0_4_1.md`

Checklist includes:

- clean build gate,
- `twine check`,
- clean wheel import from `/tmp/site-packages`,
- README claim matrix gate,
- public string scan gate,
- exact-commit tag gate,
- Arthur approval before upload,
- post-PyPI install verification,
- explicit no-publish/no-side-effect language.

### A3 — Clean dev test-path fix

Fixed `tests/test_e2e.py` so a clean `.[dev]` environment without optional `onnxruntime` does not fail during test collection.

Root cause:

- `from vault.embed import ONNXEmbeddingProvider` can succeed even when `onnxruntime` is not installed because `onnxruntime` is imported lazily at encode/load time.
- The test treated the provider import as proof that ONNX runtime was available.

Fix:

- Explicitly test `import onnxruntime` before enabling semantic embedding checks.
- If unavailable, skip semantic embedding checks and continue with local keyword/fallback paths.

---

## Verification commands and results

### Local current environment

```bash
python -m pytest -q
```

Result:

```text
79 passed
```

```bash
git diff --check
python -m compileall -q vault scripts tests
python -m vault.cli --help
python -m vault.mcp --help
```

Result: passed.

### Clean `.[dev]` environment gate

Commands:

```bash
rm -rf dist build vault_for_llm.egg-info /tmp/vfl-p1-dev-venv /tmp/vfl-p1-site /tmp/vfl-p1-smoke
python3 -m venv /tmp/vfl-p1-dev-venv
/tmp/vfl-p1-dev-venv/bin/python -m pip install --upgrade pip setuptools wheel build twine pytest
/tmp/vfl-p1-dev-venv/bin/python -m pip install -e '.[dev]'
/tmp/vfl-p1-dev-venv/bin/python -m pytest -q
```

Result:

```text
79 passed
```

### Build + twine gate

Commands:

```bash
/tmp/vfl-p1-dev-venv/bin/python -m build 2>&1 | tee /tmp/vfl_p1_build_output.log
/tmp/vfl-p1-dev-venv/bin/python -m twine check dist/*
```

Result:

```text
Successfully built vault_for_llm-0.4.1.tar.gz and vault_for_llm-0.4.1-py3-none-any.whl
Checking dist/vault_for_llm-0.4.1-py3-none-any.whl: PASSED
Checking dist/vault_for_llm-0.4.1.tar.gz: PASSED
```

Deprecation warning check:

```bash
grep -E 'project\.license.*TOML table|License classifiers are deprecated|License :: OSI Approved' /tmp/vfl_p1_build_output.log
```

Result: no matches.

### Clean wheel import gate from `/tmp`

Commands:

```bash
mkdir -p /tmp/vfl-p1-site
/tmp/vfl-p1-dev-venv/bin/python -m pip install --no-deps --target /tmp/vfl-p1-site dist/vault_for_llm-0.4.1-py3-none-any.whl
cd /tmp
PYTHONPATH=/tmp/vfl-p1-site /tmp/vfl-p1-dev-venv/bin/python - <<'PY'
import vault, subprocess, sys
print(vault.__version__)
print(vault.__file__)
assert vault.__version__ == '0.4.1'
assert vault.__file__.startswith('/tmp/vfl-p1-site/'), vault.__file__
from vault import VaultDB, VaultSearch, VaultCompiler
r = subprocess.run([sys.executable, '-m', 'vault.cli', '--help'], env={'PYTHONPATH':'/tmp/vfl-p1-site'}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
assert r.returncode == 0, r.stdout
PY
```

Result:

```text
0.4.1
/tmp/vfl-p1-site/vault/__init__.py
VaultDB VaultSearch VaultCompiler
help_rc 0
```

### Public stale-string scan

Command:

```bash
git grep -n -I -E 'hermes_vault|hermes-main|\.hermes|skill marketplace|技能市場|Dashboard|dashboard' -- README.md README.zh-CN.md README.zh-Hant.md docs/optimization_plan_v2.md docs/agent_memory_qa_roadmap.md vault scripts tests raw templates SCHEMA.md PROGRESS.md AUDIT_REPORT.md || true
```

Result:

- Only a historical verification note in `PROGRESS.md` matched the word `dashboard`.
- No stale public default-path wording was found in README files or default code paths.

### Graphify

Command:

```bash
python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"
```

Result:

```text
[graphify watch] Rebuilt: 117 nodes, 5 edges, 114 communities
```

---

## Warnings / follow-ups

### W1 — Do not publish without explicit approval

All checks here are local. PyPI upload, git tag, push, and GitHub release remain blocked until Arthur explicitly approves.

### W2 — Build artifacts are disposable

`dist/`, `build/`, and `vault_for_llm.egg-info/` are generated artifacts. They should be removed before committing unless a release workflow explicitly requires retaining them.

### W3 — Clean dev test-path issue fixed in this branch

The clean `.[dev]` failure was real and has been fixed by explicit `onnxruntime` availability detection in `tests/test_e2e.py`.

---

## Release-readiness conclusion

The repo is locally ready for a future `0.4.1` release preparation commit.

Recommended next human decision:

- If Arthur wants to publish: run the exact checklist in `docs/release_checklist_0_4_1.md`, tag the reviewed commit, upload to PyPI, verify fresh PyPI install, then rotate/restrict credentials.
- If not publishing yet: stop here; keep the branch as a verified release candidate.
