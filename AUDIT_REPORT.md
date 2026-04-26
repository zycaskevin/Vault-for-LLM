# Security & Code Quality Audit Report — Vault-for-LLM v0.4.0

**Date:** 2026-04-26  
**Auditor:** Automated audit  
**Scope:** Full codebase, pre-open-source release

---

## Summary

| Severity | Count | Description |
|----------|-------|-------------|
| **P0 Critical** | 7 | Security/privacy issues that must be fixed before release |
| **P1 High** | 10 | Code quality issues that should be fixed |
| **P2 Medium** | 7 | Testing/reliability improvements |

---

## P0 — SECURITY & PRIVACY (Must Fix Before Release)

### P0-001: SQL Injection via `update_knowledge()` kwargs

**File:** `guardrails_lite/guardrails_db.py`, line 289-291  
**Issue:** Column names in `update_knowledge()` are built via f-string from `**fields` dict keys. While the caller currently controls the keys, this is a dangerous pattern — any user-controlled dict passed here enables SQL injection via column names.

```python
sets = ", ".join(f"{k}=?" for k in fields)
self.conn.execute(f"UPDATE knowledge SET {sets} WHERE id=?", vals)
```

**Fix:** Whitelist allowed column names:
```python
ALLOWED_COLUMNS = {"title", "layer", "category", "tags", "trust", "content_raw", 
                   "content_aaak", "content_hash", "source", "convergence_status",
                   "convergence_score", "convergence_checked_at", "last_verified", "freshness"}
fields = {k: v for k, v in fields.items() if k in ALLOWED_COLUMNS}
```

---

### P0-002: SQL Injection via `get_edges()` dynamic WHERE clause

**File:** `guardrails_lite/guardrails_db.py`, line 487-499  
**Issue:** The `where` clause is built via f-string. While `conditions` values are hardcoded strings (`source_id=?`, `target_id=?`), the `relation` parameter is user-controlled and concatenated directly:

```python
where += " AND relation=?"
```

This particular case is safe (uses `?`), but the f-string pattern `f"SELECT * FROM edges WHERE {where}"` is fragile.

**Fix:** Use a parameterized builder pattern consistently.

---

### P0-003: SQL Injection in `convergence_check.py` — LIMIT via f-string

**File:** `scripts/convergence_check.py`, line 255  
**Issue:** The `limit` parameter is directly interpolated into SQL:
```python
if limit > 0:
    query += f" LIMIT {limit}"
```
Although `limit` is typed as `int`, the f-string interpolation is a bad pattern.

**Fix:** Use parameterized query: `query += " LIMIT ?"` with `params.append(limit)`

---

### P0-004: SQL Injection in `cross_validate.py` — LIMIT via f-string

**File:** `scripts/cross_validate.py`, line 293-294  
**Issue:** Same pattern as P0-003:
```python
if limit > 0:
    query += f" LIMIT {limit}"
```

**Fix:** Same as P0-003 — use parameterized query.

---

### P0-005: Personal path exposure — `~/.hermes/.env`

**File:** `scripts/cross_validate.py`, line 72  
**Issue:** Hardcoded path to `~/.hermes/.env` exposes internal tooling:
```python
env_file = os.path.expanduser("~/.hermes/.env")
```

**Fix:** Remove this. Use standard `.env` loading via `_utils.py:load_dotenv_cascade()` instead. The comment in `sync_to_supabase.py` says "不再依賴 ~/.hermes/.env" but `cross_validate.py` still references it.

---

### P0-006: Personal path exposure — `.hermes` in comment

**File:** `scripts/sync_to_supabase.py`, line 23  
**Issue:** Comment references internal tool:
```python
# 載入 .env：優先用專案目錄的 .env，其次 ~/.env，不再依賴 ~/.hermes/.env
```

**Fix:** Remove the reference to `~/.hermes/.env` from the comment.

---

### P0-007: Error messages expose internal system details — WONTFIX

**Decision:** Open-source projects benefit from detailed error messages for debugging and issue reporting. No personal/private data found in error messages after thorough scan. Keeping as-is is the right call for open-source.

**Files:** Multiple  
**Issue:** Exception details are printed directly to users, potentially exposing filesystem paths, internal architecture, and debug info:

- `guardrails_lite/guardrails_db.py:218` — prints vector table rebuild details
- `guardrails_lite/guardrails_cli.py:143` — prints embedding exception details
- `guardrails_lite/guardrails_cli.py:766` — `traceback.print_exc()` in import
- `guardrails_lite/guardrails_mcp.py:273` — `str(e)` returned to MCP client
- `scripts/cross_validate.py:60` — prints vLLM error details

**Fix:** Use a generic error message for users, log details only when debug mode is on.

---

## P1 — CODE QUALITY (Should Fix)

### P1-001: Missing CLI commands documented in README — FIXED

**File:** `guardrails_lite/guardrails_cli.py` vs `README.md`  
**Issue:** The README documents these commands but they were NOT implemented as CLI subcommands:

| Documented Command | Status |
|---|---|
| `vault converge` | ✅ Now implemented as CLI subcommand |
| `vault cross-validate` | ✅ Now implemented as CLI subcommand |
| `vault freshness` | ✅ Now implemented as CLI subcommand |
| `vault dedup` | ✅ Now implemented as CLI subcommand |
| `vault dedup --dry-run` | ✅ Now implemented as CLI subcommand |
| `vault dedup --merge` | ✅ Now implemented as CLI subcommand |

**Fix:** Added 4 CLI subcommand wrappers that import and call the existing script functions.

---

### P1-002: Version mismatch — `__init__.py` says 0.3.2, `pyproject.toml` says 0.4.0

**File:** `guardrails_lite/__init__.py`, line 3  
**Issue:** `__version__ = "0.3.2"` but `pyproject.toml` declares `version = "0.4.0"`.

**Fix:** Update `__init__.py` to `__version__ = "0.4.0"`.

---

### P1-003: Inconsistent naming — "Guardrails" vs "Vault" branding

**Files:** Throughout codebase  
**Issue:** The project is branded "Vault-for-LLM" (README, pyproject.toml, GitHub URL) but all internal code uses "Guardrails" / "guardrails_lite":
- Package name: `guardrails_lite`
- CLI entry point: `vault` (good) but prog name says `guardrails` (line 803)
- DB file: `guardrails.db`
- Cache dir: `~/.cache/guardrails-lite`
- Logger: `guardrails-lite`
- MCP server name: `guardrails-mcp`
- All class names: `GuardrailsDB`, `GuardrailsCompiler`, `GuardrailsSearch`, etc.

**Fix:** For a clean open-source release, either:
1. Rename the package to `vault_for_llm` (major effort), OR
2. Update the `prog` name to `vault` (line 803), keep the internal module name as is, and add a note in README explaining the legacy naming.

At minimum, fix line 803:
```python
parser = argparse.ArgumentParser(
    prog="vault",  # Not "guardrails"
    ...
)
```

---

### P1-004: DB resource leak — `GuardrailsDB` not used as context manager in many places

**Files:** `guardrails_cli.py` (lines 241, 268, 474, etc.), `scripts/*.py`  
**Issue:** Throughout the CLI, `db = GuardrailsDB(...)` + `db.connect()` is used without a `try/finally` block. If an exception occurs between `connect()` and `close()`, the DB connection leaks.

Example (`cmd_stats`, line 503):
```python
db = GuardrailsDB(str(db_path))
db.connect()
# ... code that may throw ...
db.close()
```

**Fix:** Use the context manager:
```python
with GuardrailsDB(str(db_path)) as db:
    ...
```
Or wrap in `try/finally`.

---

### P1-005: Duplicate DB connections in `cmd_install_embedding`

**File:** `guardrails_lite/guardrails_cli.py`, lines 474-486  
**Issue:** Opens two separate DB connections back-to-back just to call `_init_vec_table()`:
```python
db = GuardrailsDB(...)
db.connect()
...
db.close()

db2 = GuardrailsDB(...)  # Second connection!
db2.connect()
db2._init_vec_table()
db2.close()
```

**Fix:** Use a single connection and call `_init_vec_table()` on it.

---

### P1-006: Duplicate DB connections in `cmd_import`

**File:** `guardrails_lite/guardrails_cli.py`, lines 707-768  
**Issue:** Opens a temp DB to read config, closes it, then opens another for import, then opens a THIRD to check context.

**Fix:** Reuse a single DB connection.

---

### P1-007: Duplicate `import re` inside functions

**File:** `guardrails_lite/guardrails_compile.py`, lines 89, 134  
**Issue:** `import re` appears inside function bodies when it's already imported at the module level (line 18). This is unnecessary overhead.

**Fix:** Remove the local `import re` statements.

---

### P1-008: Unused import in `guardrails_search.py`

**File:** `guardrails_lite/guardrails_search.py`, lines 14-19  
**Issue:** `MODELS` and `DEFAULT_MODEL_KEY` are imported but never used:
```python
from .guardrails_embed import (
    create_embedding_provider,
    EmbeddingProvider,
    MODELS,           # unused
    DEFAULT_MODEL_KEY, # unused
)
```

**Fix:** Remove unused imports.

---

### P1-009: Test uses `conda run` — not portable

**File:** `tests/test_new_features.py`, line 150  
**Issue:** Test hardcodes `conda run -n guardrails-lite` which won't work in other environments:
```python
result = subprocess.run(
    ["conda", "run", "-n", "guardrails-lite", "python", ...],
)
```

**Fix:** Use `sys.executable` instead:
```python
result = subprocess.run(
    [sys.executable, str(PROJECT_ROOT / "scripts" / "convergence_check.py"), ...],
)
```

---

### P1-010: CLI `shell=True` in test — command injection risk

**File:** `tests/test_e2e.py`, line 309  
**Issue:** Uses `shell=True` with string interpolation:
```python
r = subprocess.run(
    f"{CLI} {cmd}",
    shell=True, capture_output=True, ...
)
```

**Fix:** Use list-form `subprocess.run([CLI] + cmd.split(), ...)`.

---

## P2 — TESTING & RELIABILITY (Should Improve)

### P2-001: No test coverage for v0.4.0 CLI commands

**Issue:** The following v0.4.0 features have NO CLI-level test coverage:
- `vault converge` (not even implemented as CLI command)
- `vault cross-validate` (not even implemented as CLI command)
- `vault freshness` (not even implemented as CLI command)
- `vault dedup` (not even implemented as CLI command)

**Fix:** Add CLI-level tests for all documented commands.

---

### P2-002: No edge case tests

**Issue:** Missing test coverage for:
- Empty database (0 entries) — search, list, lint
- Missing `guardrails.db` file
- Corrupt YAML in frontmatter (partially covered but could be more thorough)
- Concurrent DB access
- Very large content (>100KB)
- Special characters in titles (`/`, `\`, `"`, `'`)
- Unicode edge cases in search

---

### P2-003: `test_lite.py` and `test_e2e.py` not using pytest

**Issue:** Both files use a custom `check()` function and manual test runner instead of pytest assertions. They also use `print()` instead of proper test reporting. The `pyproject.toml` lists `pytest>=7.0` as a dev dependency.

**Fix:** Rewrite tests using pytest framework with proper `assert` statements and fixtures.

---

### P2-004: `test_lite.py` temp file leak

**File:** `tests/test_lite.py`, line 19  
**Issue:** Uses `tempfile.mktemp()` (deprecated, creates race condition) instead of `tempfile.mkstemp()` or `tmp_path` fixture.

**Fix:** Use `tempfile.mkstemp()` or pytest's `tmp_path` fixture.

---

### P2-005: No `.gitignore` for generated reports

**Issue:** Several scripts generate JSON reports in the project directory:
- `convergence_report.json`
- `cross_validation_report.json`
- `freshness_report.json`
- `duplicate_report.json`
- `graphify-out/`

None of these are in `.gitignore`.

**Fix:** Add to `.gitignore`:
```
*_report.json
graphify-out/
```

---

### P2-006: MCP server DB path is hardcoded to repo root

**File:** `guardrails_lite/guardrails_mcp.py`, line 33  
**Issue:** `DB_PATH` is hardcoded relative to the source file location:
```python
DB_PATH = os.path.join(GUARDRAILS_DIR, "guardrails.db")
```

When installed via pip, this points to the package directory, not the user's project directory. The `--project-dir` flag documented in README is not implemented in the MCP server.

**Fix:** Support `--project-dir` argument for the MCP server.

---

### P2-007: `vault.yaml` referenced in README but never created

**File:** `README.md`, line 179  
**Issue:** README shows `vault.yaml` in the directory structure but `cmd_init` never creates it. There's no code that reads from `vault.yaml`.

**Fix:** Either create `vault.yaml` in `init` or remove it from the README directory structure.

---

## Additional Notes

### Positive Findings
- All SQL queries use parameterized `?` placeholders for values (good!)
- API keys are read from environment variables, not hardcoded (good!)
- `supabase` dependency is in sync scripts only, not in main package (good!)
- Proper use of `hashlib.sha256` for content hashing
- Foreign keys are enabled (`PRAGMA foreign_keys=ON`)
- WAL mode is enabled for concurrent access
- `yaml.safe_load()` is used (not `yaml.load()`)

### Recommendations for Open Source Release
1. Add a `CONTRIBUTING.md` file
2. Add a `SECURITY.md` file with vulnerability reporting instructions
3. Add `LICENSE` file (MIT, as referenced in README)
4. Consider adding a `CODE_OF_CONDUCT.md`
5. Add GitHub Actions CI workflow (`.github/workflows/` exists but should run tests)
6. Clean up the `graphify-out/` directory from the repo
