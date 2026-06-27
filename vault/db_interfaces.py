"""Small adapters for public helpers that can accept VaultDB or raw SQLite."""

from __future__ import annotations

import sqlite3
from typing import Any


def connection_from(db_or_conn: Any, *, label: str = "database") -> sqlite3.Connection:
    """Return a sqlite3 connection from a VaultDB-like object or raw connection."""
    if isinstance(db_or_conn, sqlite3.Connection):
        return db_or_conn

    conn = getattr(db_or_conn, "conn", None)
    if isinstance(conn, sqlite3.Connection):
        return conn

    raise TypeError(f"{label} must be a connected VaultDB or sqlite3.Connection")
