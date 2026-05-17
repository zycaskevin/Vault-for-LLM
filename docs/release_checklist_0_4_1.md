# Vault-for-LLM 0.4.1 Public Release Checklist

Status: prepared checklist only. Do not publish, tag, push, upload, or call external release services while completing this document.

This checklist is for a future `0.4.1` PyPI release that refreshes public package metadata and long description after the P0 public-boundary cleanup and P1/A1 license metadata cleanup. It intentionally separates local verification from release side effects.

## Current package parity snapshot

Verified locally on 2026-05-17:

| Item | Expected | Observed | Status |
|---|---:|---:|---|
| `pyproject.toml` version | `0.4.1` | `0.4.1` | aligned |
| `vault/__init__.py` `__version__` | `0.4.1` | `0.4.1` | aligned |
| top `CHANGELOG.md` entry | `0.4.1` | `0.4.1` | aligned |
| package README source | `README.md` | `README.md` | aligned |
| license metadata | SPDX `MIT` + `LICENSE` included | SPDX `MIT` + `LICENSE` included | aligned |

## README public-claim parity snapshot

`docs/readme_claim_matrix.md` remains the source of truth for English README public feature claims, proof, and maturity tier. The localized READMEs were checked against the same P0/P1 public-claim shape:

| File | H2 sections | H3 install subsections | capability table rows | quality-roadmap table rows | CLI table rows | command tokens |
|---|---:|---:|---:|---:|---:|---|
| `README.md` | 15 | 4 | 10 | 6 | 22 | aligned |
| `README.zh-CN.md` | 15 | 4 | 10 | 6 | 22 | aligned |
| `README.zh-Hant.md` | 15 | 4 | 10 | 6 | 22 | aligned |

Parity conclusion: the Simplified Chinese and Traditional Chinese READMEs still mirror the English README's public P0/P1 claims: local-first SQLite core, no cloud requirement for core usage, optional embeddings, optional Supabase sync/read target, alpha/CLI-first maturity, `vault skill` as experimental local-only registry rather than hosted marketplace, and the same CLI/MCP command surface. No localized README wording edit is required for 0.4.1.

## Release gates before any side effects

Complete every item below in a clean checkout or release worktree before requesting approval.

1. Scope freeze
   - Confirm `pyproject.toml`, `vault/__init__.py`, and `CHANGELOG.md` all name `0.4.1`.
   - Confirm the intended release is metadata/long-description cleanup only, not a feature release.
   - Confirm `README.md`, `README.zh-CN.md`, and `README.zh-Hant.md` still match `docs/readme_claim_matrix.md` on P0/P1 public claims.

2. Clean local test/build environment
   - Start from a clean git status except intentional release-commit changes.
   - Remove stale local build outputs: `dist/`, `build/`, and `*.egg-info/`.
   - Use a fresh virtual environment with current build tooling.

3. Clean build gate
   - Run `python -m build` from the repository root.
   - Treat packaging warnings as release blockers unless explicitly documented and accepted.
   - Confirm the generated wheel and sdist are for `vault-for-llm==0.4.1`.

4. Twine metadata gate
   - Run `twine check dist/*`.
   - Release blocker: any failed long-description render, missing metadata, or license warning regression.

5. Clean wheel import gate from `/tmp/site-packages`
   - Install only the built wheel into an empty target directory such as `/tmp/site-packages`.
   - Run Python with that target on `PYTHONPATH`, from `/tmp`, and verify:
     - `import vault` imports from `/tmp/site-packages`, not the repository checkout.
     - `vault.__version__ == "0.4.1"`.
     - `from vault import VaultDB, VaultSearch, VaultCompiler` succeeds.
     - `python -m vault.cli --help` succeeds when pointed at the installed wheel.

6. README claim matrix gate
   - Re-read `docs/readme_claim_matrix.md`.
   - Confirm every public README feature/capability claim remains classified as stable, usable-alpha, experimental, or positioning.
   - If any README wording changes, update the claim matrix before release.

7. Public string scan gate
   - Run the P0 public-boundary string scan from `docs/p0_public_string_audit.md` against README files, public docs, default code paths, tests, scripts, templates, and schema/progress files.
   - Exclude only historical audit/checklist documents that intentionally quote scan terms.
   - Release blocker: an unclassified private/internal product name, private path, hard-coded private table prefix, secret-looking credential, dashboard/admin-only wording, or hosted-marketplace wording in public-facing docs/default paths.
   - Document any remaining findings as accepted historical/audit references or fix them before release.

8. Tag exact commit gate
   - After all local gates pass, record the exact release commit SHA.
   - Tag exactly that commit, not a branch name or moving ref.
   - Verify the tag points at the reviewed commit before upload.

9. Arthur approval gate
   - Do not upload to PyPI, push a tag, create a GitHub release, or publish external artifacts until Arthur explicitly approves the exact commit and artifacts.
   - Approval must happen after the clean build, twine check, `/tmp/site-packages` import gate, README claim matrix gate, and public string scan gate.

10. Upload gate after approval only
    - Upload only the verified artifacts from the clean build directory.
    - Do not rebuild between approval and upload unless the full checklist is rerun and Arthur re-approves.
    - Keep credentials scoped and avoid printing tokens in logs.

11. Post-PyPI install verification
    - In a fresh virtual environment with no repository checkout on `PYTHONPATH`, run `pip install vault-for-llm==0.4.1`.
    - Verify `python -c "import vault; print(vault.__version__, vault.__file__)"` shows `0.4.1` from site-packages.
    - Verify `vault doctor`, `vault --help`, and a minimal `vault init` / `vault add` / `vault compile` / `vault search` smoke test.
    - Open the PyPI project page and confirm the rendered long description matches the cleaned local-first README positioning and no stale pre-cleanup wording remains.

12. Release record
    - Record the final commit SHA, tag, artifact filenames, `twine check` result, post-PyPI install result, and approval reference in the project release notes.
    - Do not store tokens, credentials, or raw private approval-channel contents in repository docs.
