# API Interface Conventions

Vault has two database-facing layers:

- `VaultDB`: the high-level public object used by CLI, MCP, tests, and most
  integrations.
- `sqlite3.Connection`: low-level SQL helpers used inside `VaultDB` modules.

New public helpers should prefer `VaultDB` or accept both `VaultDB` and a raw
connection through `vault.db_interfaces.connection_from()`.

## Recommended Pattern

```python
from vault.db_interfaces import connection_from


def public_helper(db_or_conn, item_id: int) -> dict:
    conn = connection_from(db_or_conn, label="public_helper")
    row = conn.execute("SELECT * FROM knowledge WHERE id=?", (item_id,)).fetchone()
    ...
```

This keeps older integrations working while giving new users the simpler
`VaultDB` surface:

```python
from vault.db import VaultDB
from vault.docmap import build_document_map_for_entry

with VaultDB("vault.db") as db:
    build_document_map_for_entry(db, 1)
```

## Boundary Rule

- CLI/MCP handlers should open a `VaultDB`.
- Feature modules can use `VaultDB` when they need other high-level methods.
- Pure SQL modules can accept a raw `sqlite3.Connection`.
- Public utility functions should document which one they expect, or support
  both with `connection_from()`.

Avoid silently opening a second database connection inside helpers that already
received a connected object. That makes transactions and tests harder to reason
about.
