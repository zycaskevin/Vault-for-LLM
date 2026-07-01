"""Multi-host revision, conflict, and audit tables."""

from __future__ import annotations

import sqlite3


def init_multi_host_tables(conn: sqlite3.Connection) -> None:
    """Create tables used by future multi-host co-writing workflows."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_revisions (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            knowledge_id INTEGER,
            candidate_id TEXT NOT NULL DEFAULT '',
            remote_request_id TEXT NOT NULL DEFAULT '',
            parent_revision_id TEXT NOT NULL DEFAULT '',
            revision_hash TEXT NOT NULL,
            content_hash TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            source_agent TEXT NOT NULL DEFAULT '',
            operation TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}'
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_revisions_knowledge ON memory_revisions(knowledge_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_revisions_candidate ON memory_revisions(candidate_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_revisions_remote_request ON memory_revisions(remote_request_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_revisions_created_at ON memory_revisions(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_revisions_status ON memory_revisions(status)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_conflicts (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            knowledge_id INTEGER,
            left_revision_id TEXT NOT NULL DEFAULT '',
            right_revision_id TEXT NOT NULL DEFAULT '',
            candidate_id TEXT NOT NULL DEFAULT '',
            conflict_type TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            resolution_json TEXT NOT NULL DEFAULT '{}'
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_conflicts_status ON memory_conflicts(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_conflicts_knowledge ON memory_conflicts(knowledge_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_conflicts_candidate ON memory_conflicts(candidate_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_conflicts_updated_at ON memory_conflicts(updated_at)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            actor_agent TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL DEFAULT '',
            target_type TEXT NOT NULL DEFAULT '',
            target_id TEXT NOT NULL DEFAULT '',
            revision_id TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}'
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_audit_created_at ON memory_audit_log(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_audit_action ON memory_audit_log(action)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_audit_target ON memory_audit_log(target_type, target_id)")
