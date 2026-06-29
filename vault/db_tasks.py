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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_ledger_status ON task_ledger(status)")
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
