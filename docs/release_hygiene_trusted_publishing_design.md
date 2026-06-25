# Release Hygiene + PyPI Trusted Publishing Design

> **For maintainers:** keep release changes bite-sized and commit after each verified segment.

**Status:** design complete, implementation pending

**Last updated:** 2026-05-17 22:52 CST

**Applies to:** Vault-for-LLM `0.4.3+` releases

**Current released baseline:** `0.4.2` at `76be7a1a93272ba1c512410f6713cd53d4b1ed06`

## Goal

Future Vault-for-LLM releases should be reproducible from a clean GitHub Actions checkout and published to PyPI with Trusted Publishing, not by pasting a PyPI token into a local terminal session.

In plain terms: GitHub should build the package, PyPI should trust exactly that GitHub workflow, and no long-lived PyPI token should sit in chat, shell history, repository files, or GitHub secrets.

## Evidence Used

Repo evidence:

- `pyproject.toml` currently declares `vault-for-llm` version `0.4.2`.
- `CHANGELOG.md` top entry is `0.4.2`.
- `.github/workflows/auto-review.yml` is currently the only GitHub Actions workflow.
- Existing CI only runs `tests/test_lite.py` on Python 3.11 and does not yet build/twine-check/wheel-smoke release artifacts.
- Local progress and audit notes are intentionally excluded from the public repository; record release status in GitHub Releases, CHANGELOG entries, and current PR bodies instead.

Official docs checked:

- PyPI Trusted Publishing docs: <https://docs.pypi.org/trusted-publishers/using-a-publisher/>
- Python Packaging User Guide for GitHub Actions publishing: <https://packaging.python.org/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/>
- GitHub OIDC for PyPI docs: <https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-pypi>

Key official requirements from those docs:

- Use `pypa/gh-action-pypi-publish@release/v1` for stable public Trusted Publishing.
- Do **not** pass `username` / `password` when using Trusted Publishing.
- Grant `id-token: write` at the publishing job level.
- Prefer a GitHub Environment such as `pypi`; manual approval/protection is recommended for PyPI production publishing.
- Configure PyPI to trust the exact GitHub owner/repo, workflow filename, and environment.

## Non-goals

- Do not re-upload `0.4.1` or `0.4.2`; PyPI versions are immutable.
- Do not store a PyPI API token in `.pypirc`, repository files, GitHub Secrets, local shell history, memory, or docs.
- Do not make Supabase or any hosted service required for core usage.
- Do not make `ruff` a blocking CI gate until the existing lint debt is either fixed or explicitly configured.
- Do not publish from local `dist/`; all future publish workflows must build artifacts from a clean checkout.

## Recommended End-state

### Files to create or modify

1. Create `.github/workflows/ci.yml`
   - Full project CI gate.
   - Runs on PRs and pushes that touch source, tests, docs, workflows, or package metadata.

2. Create `.github/workflows/publish.yml`
   - Release build + publish pipeline.
   - Publishes only from tag/release events after version parity checks pass.
   - Uses Trusted Publishing with `id-token: write` and no PyPI token.

3. Update `.gitignore`
   - Ignore local agent/session artifacts such as `.agent-runtime/` and `.ruff_cache/`.

4. Add or refresh release docs
   - Prefer a reusable `docs/release_checklist.md` over version-specific local notes.
   - Do not keep version-specific approval or release-readiness reports in the public repository unless they are rewritten as public release notes.

5. Later OSS hygiene docs
   - `SECURITY.md`
   - `CONTRIBUTING.md`
   - `.github/dependabot.yml`
   - Optional: `CODE_OF_CONDUCT.md`, `.github/pull_request_template.md`

## CI Design

Create `.github/workflows/ci.yml` with these jobs:

### `test`

Purpose: prove the package works across supported Python versions.

Recommended matrix:

- Python `3.10`
- Python `3.11`
- Python `3.12`
- Python `3.13` if the project intends to support it publicly

Commands:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest -q
python -m compileall -q vault scripts tests
```

### `build-smoke`

Purpose: prove a clean wheel can be built and imported outside the source tree.

Commands:

```bash
python -m pip install --upgrade pip build twine
rm -rf dist build *.egg-info
python -m build
python -m twine check dist/*
python -m venv /tmp/vfl-wheel-smoke
/tmp/vfl-wheel-smoke/bin/python -m pip install dist/*.whl
cd /tmp
/tmp/vfl-wheel-smoke/bin/vault --help
/tmp/vfl-wheel-smoke/bin/python - <<'PY'
import importlib.metadata as m
print(m.version('vault-for-llm'))
PY
```

### `release-parity`

Purpose: catch version drift before a release.

Checks:

- Tag `vX.Y.Z` matches `pyproject.toml` version `X.Y.Z`; release-candidate tags use PyPI-compatible `vX.Y.ZrcN`.
- `vault.__version__` matches `pyproject.toml` version.
- `CHANGELOG.md` top entry is `## [X.Y.Z]` or `## [X.Y.ZrcN]`.
- Release tags must point at the same commit that CI tested.

### `secret-scan-light`

Keep the current lightweight scan, but avoid broad false positives. Scan source/docs for common high-risk token patterns and always exclude `.git/`, `dist/`, `.venv/`, and generated caches.

## Publish Workflow Design

Create `.github/workflows/publish.yml`.

Preferred trigger:

```yaml
on:
  release:
    types: [published]
  workflow_dispatch:
```

Why release-triggered:

- A GitHub Release is an intentional human action.
- The release page becomes the public changelog anchor.
- The publish job can use the release tag as the single source of version truth.

Minimum jobs:

```yaml
name: Publish Python distribution to PyPI

on:
  release:
    types: [published]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  build:
    name: Build distribution
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - uses: actions/setup-python@v5
        with:
          python-version: "3.x"
      - name: Install build tools
        run: python -m pip install --upgrade pip build twine
      - name: Verify version parity
        run: python scripts/check_release_parity.py
      - name: Build distributions
        run: python -m build
      - name: Check distributions
        run: python -m twine check dist/*
      - name: Upload distributions
        uses: actions/upload-artifact@v4
        with:
          name: python-package-distributions
          path: dist/

  publish:
    name: Publish to PyPI
    needs: [build]
    runs-on: ubuntu-latest
    environment:
      name: pypi
      url: https://pypi.org/project/vault-for-llm/
    permissions:
      id-token: write
      contents: read
    steps:
      - name: Download distributions
        uses: actions/download-artifact@v4
        with:
          name: python-package-distributions
          path: dist/
      - name: Publish distributions to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

Implementation notes:

- `publish.permissions.id-token: write` is mandatory for Trusted Publishing.
- Do not configure `username`, `password`, or `PYPI_API_TOKEN`.
- Use the `pypi` GitHub Environment and protect it with manual approval / deployment rules.
- If using `workflow_dispatch`, the job must still require version parity and environment approval.
- Consider pinning third-party actions to commit SHAs in a follow-up hardening pass.

## PyPI Trusted Publisher Configuration

In PyPI project settings for `vault-for-llm`, configure a Trusted Publisher with:

| Field | Value |
|---|---|
| PyPI project | `vault-for-llm` |
| GitHub owner | `zycaskevin` |
| GitHub repository | `Vault-for-LLM` |
| Workflow filename | `publish.yml` |
| GitHub Environment | `pypi` |

Important: PyPI docs and GitHub docs both warn that this trust relationship is equivalent to giving publish rights. Enter owner, repo, workflow filename, and environment carefully.

## Release Procedure After Implementation

1. Update version in `pyproject.toml` and `vault/__init__.py`.
2. Update `CHANGELOG.md` with the new top entry.
3. Run local gates:
   ```bash
   git diff --check
   python -m pytest -q
   python -m compileall -q vault scripts tests
   rm -rf dist build *.egg-info
   python -m build
   python -m twine check dist/*
   ```
4. Commit release candidate.
5. Tag the exact commit:
   ```bash
   git tag vX.Y.Z
   git push origin main --tags
   ```
   For release candidates, use the PEP 440 shape, for example `v0.7.0rc1`.
6. Create a GitHub Release for `vX.Y.Z` or the matching RC tag.
7. GitHub Actions builds from clean checkout and publishes via Trusted Publishing.
8. Verify PyPI from a fresh environment:
   ```bash
   python -m venv /tmp/vfl-pypi-smoke
   /tmp/vfl-pypi-smoke/bin/python -m pip install --upgrade pip
   /tmp/vfl-pypi-smoke/bin/python -m pip install --no-cache-dir vault-for-llm==X.Y.Z
   /tmp/vfl-pypi-smoke/bin/vault --help
   ```
9. Verify PyPI JSON contains both wheel and sdist.
10. Never retry the same PyPI version after a partial failure; bump patch version if artifacts were already accepted.

## Risk Matrix

| Risk | Impact | Mitigation |
|---|---:|---|
| Wrong PyPI Trusted Publisher owner/repo/workflow | High | Configure exactly `zycaskevin/Vault-for-LLM`, `publish.yml`, environment `pypi`; verify before first run. |
| Re-upload immutable version | High | Version parity check + PyPI existence preflight + release checklist. |
| Workflow publishes from stale/local artifact | High | Build in clean GitHub checkout; artifact passed from build job only. |
| Manual token leaks again | High | Trusted Publishing only; no `PYPI_API_TOKEN` secret; no `.pypirc`. |
| CI becomes noisy because of existing ruff debt | Medium | Do not make ruff blocking until cleanup/config PR. |
| `workflow_dispatch` accidentally publishes | Medium | Require `pypi` environment approval and version/tag parity check. |
| Docs claim support for Python 3.13 before CI proves it | Medium | Add 3.13 to matrix before adding classifier, or keep classifier list as-is. |

## Implementation Tasks

### Task 1: Add release parity checker

**Objective:** make version/tag/changelog drift fail before publishing.

**Files:**

- Create: `scripts/check_release_parity.py`
- Test: `tests/test_release_parity.py`

**Acceptance criteria:**

- Accepts tag `v0.4.3` when `pyproject.toml`, `vault.__version__`, and `CHANGELOG.md` top entry are all `0.4.3`.
- Accepts release-candidate tag `v0.7.0rc1` when `pyproject.toml`, `vault.__version__`, and `CHANGELOG.md` top entry are all `0.7.0rc1`.
- Fails with clear messages for version mismatch.
- Can run locally without network.

### Task 2: Add full CI workflow

**Objective:** replace lightweight-only CI with package-level release readiness checks.

**Files:**

- Create: `.github/workflows/ci.yml`
- Optionally retire or rename: `.github/workflows/auto-review.yml`

**Acceptance criteria:**

- Runs tests, compileall, build, twine check, and wheel smoke.
- Uses Python matrix aligned with public classifiers.
- Path filters include README/docs/workflows/CHANGELOG/package metadata.

### Task 3: Add publish workflow

**Objective:** publish to PyPI by Trusted Publishing.

**Files:**

- Create: `.github/workflows/publish.yml`

**Acceptance criteria:**

- Publishing job has job-level `permissions.id-token: write`.
- Uses environment `pypi`.
- Uses `pypa/gh-action-pypi-publish@release/v1` without `username` or `password`.
- Does not run on ordinary PRs.

### Task 4: Configure PyPI + GitHub Environment

**Objective:** create the external trust boundary.

**Manual steps:**

- In GitHub, create/protect environment `pypi` with required reviewer approval.
- In PyPI, add Trusted Publisher for `vault-for-llm` using owner `zycaskevin`, repo `Vault-for-LLM`, workflow `publish.yml`, environment `pypi`.

**Acceptance criteria:**

- First dry release attempt reaches PyPI without a local token.
- No PyPI token exists in GitHub Secrets for this project.

### Task 5: Add OSS hygiene docs

**Objective:** make contributor/security expectations explicit.

**Files:**

- Create: `SECURITY.md`
- Create: `CONTRIBUTING.md`
- Create: `.github/dependabot.yml`

**Acceptance criteria:**

- Security doc tells users not to publicly paste vault contents or secrets.
- Contributing doc documents local test gates and says releases are maintainer-only through GitHub Actions.
- Dependabot covers GitHub Actions and Python dependencies.

## Current Decision

Do **not** implement automatic publishing immediately in the same step as the 0.4.2 manual release. Treat this document as the design/contract for the next release-hygiene PR. The next implementation should be a small, reviewable change set: parity checker + CI first, publish workflow second, PyPI/GitHub environment configuration last.
