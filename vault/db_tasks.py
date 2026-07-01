"""Task Ledger schema helpers."""

from __future__ import annotations

import sqlite3


def init_task_tables(conn: sqlite3.Connection) -> None:
    """Create Task Ledger tables without expanding the core DB module."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_ledger (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            priority TEXT NOT NULL DEFAULT 'P2',
            due_at TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            goal TEXT NOT NULL,
            current_plan_json TEXT NOT NULL DEFAULT '[]',
            completed_json TEXT NOT NULL DEFAULT '[]',
            hard_decisions_json TEXT NOT NULL DEFAULT '[]',
            blockers_json TEXT NOT NULL DEFAULT '[]',
            open_questions_json TEXT NOT NULL DEFAULT '[]',
            next_actions_json TEXT NOT NULL DEFAULT '[]',
            continuation_note TEXT NOT NULL DEFAULT '',
            scope TEXT NOT NULL DEFAULT 'project',
            sensitivity TEXT NOT NULL DEFAULT 'low',
            owner_agent TEXT NOT NULL DEFAULT '',
            allowed_agents TEXT NOT NULL DEFAULT '[]',
            source TEXT NOT NULL DEFAULT 'cli'
        )
    """)
    _ensure_task_column(conn, "priority", "TEXT NOT NULL DEFAULT 'P2'")
    _ensure_task_column(conn, "due_at", "TEXT NOT NULL DEFAULT ''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_ledger_status ON task_ledger(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_ledger_priority ON task_ledger(priority)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_ledger_due_at ON task_ledger(due_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_ledger_updated_at ON task_ledger(updated_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_ledger_scope ON task_ledger(scope)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_ledger_sensitivity ON task_ledger(sensitivity)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_ledger_owner_agent ON task_ledger(owner_agent)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            agent_id TEXT NOT NULL DEFAULT '',
            source_ref TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (task_id) REFERENCES task_ledger(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_events_created_at ON task_events(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_events_type ON task_events(event_type)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_evidence_refs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            ref_type TEXT NOT NULL DEFAULT 'text',
            ref TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (task_id) REFERENCES task_ledger(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_evidence_task_id ON task_evidence_refs(task_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_evidence_ref_type ON task_evidence_refs(ref_type)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_handoffs (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            claimed_at TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            from_agent TEXT NOT NULL DEFAULT '',
            to_agent TEXT NOT NULL DEFAULT '',
            claimed_by TEXT NOT NULL DEFAULT '',
            message TEXT NOT NULL DEFAULT '',
            markdown TEXT NOT NULL DEFAULT '',
            source_ref TEXT NOT NULL DEFAULT '',
            scope TEXT NOT NULL DEFAULT 'project',
            sensitivity TEXT NOT NULL DEFAULT 'low',
            owner_agent TEXT NOT NULL DEFAULT '',
            allowed_agents TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (task_id) REFERENCES task_ledger(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_handoffs_task_id ON task_handoffs(task_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_handoffs_status ON task_handoffs(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_handoffs_to_agent ON task_handoffs(to_agent)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_handoffs_from_agent ON task_handoffs(from_agent)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_handoffs_updated_at ON task_handoffs(updated_at)")


def _ensure_task_column(conn: sqlite3.Connection, name: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(task_ledger)").fetchall()}
    if name not in columns:
        conn.execute(f"ALTER TABLE task_ledger ADD COLUMN {name} {definition}")
