# SQLite backup, verify, and restore

Vault-for-LLM stores local knowledge in `vault.db`. The `vault db` backup commands create and restore **local SQLite files only**; they do not upload data or contact external services.

## Create a backup

```bash
vault db backup --verify --pretty
```

By default, backups are written next to the database under `backups/` with a timestamped filename such as:

```text
backups/vault-YYYYmmdd-HHMMSS-microseconds.db
```

Use explicit paths when operating outside the detected project directory:

```bash
vault db backup \
  --db-path /path/to/project/vault.db \
  --output /safe/location/vault-before-change.db \
  --verify \
  --pretty
```

Backups use SQLite's online backup API, so they remain consistent even when the source database uses WAL mode. Output is JSON and includes the source path, backup path, file size, SHA-256 digest, schema status, and optional verification details.

## Verify a backup

```bash
vault db verify-backup backups/vault-20260612-120000.db --pretty
```

Verification opens the backup read-only and reports:

- `PRAGMA integrity_check`
- Vault schema validation, including required tables, core columns, schema version, and migration metadata
- basic row counts for core Vault tables
- file size and SHA-256 digest

A valid backup has `ok: true`, `integrity_check: "ok"`, and `vault_schema_ok: true`. A structurally valid SQLite file that is not a Vault database will report `integrity_check: "ok"` but `ok: false`, and restore will refuse it.

## Restore a backup

Restores verify the source backup before replacing the target database. They refuse to overwrite an existing target unless `--force` is passed:

```bash
vault db restore backups/vault-20260612-120000.db --db-path ./vault.db
```

If `./vault.db` already exists, the command exits with an error. To overwrite intentionally:

```bash
vault db restore backups/vault-20260612-120000.db --db-path ./vault.db --force --pretty
```

When `--force` overwrites an existing target, Vault first creates an automatic pre-restore backup under `backups/pre-restore-*.db` and includes that path in the JSON result. The replacement is staged through a temporary file and then installed with `os.replace`.

## Operational notes

- Close long-running processes using `vault.db` before restoring.
- Keep backup files private; they contain the same local knowledge as `vault.db`.
- Store important backups outside disposable working directories.
- Use `vault db status --pretty` after restore if you want an additional schema-focused check.
