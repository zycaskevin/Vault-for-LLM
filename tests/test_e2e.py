"""Pytest-style end-to-end smoke tests for the local Vault workflow."""

from __future__ import annotations

from pathlib import Path

from vault.db import VaultDB
from vault.memory import create_candidate, promote_candidate
from vault.search import VaultSearch


def test_e2e_memory_lifecycle_keyword_recall(tmp_path: Path):
    """Candidate-first memory can be promoted, searched, and mapped."""
    with VaultDB(tmp_path / "vault.db") as db:
        result = create_candidate(
            db,
            title="Ollama Timeout Runbook",
            content=(
                "Ollama timeout incidents are usually caused by cold models or low GPU memory. "
                "The fix is to pull the model first, warm it once, and set timeout=120."
            ),
            reason="Keep a concrete troubleshooting memory for future agent recall.",
            category="runbook",
            tags="ollama,timeout,gpu",
            source="test",
        )
        promoted = promote_candidate(db, result["candidate_id"], confirm=True, project_dir=tmp_path)

        assert promoted["status"] == "promoted"
        assert promoted["knowledge_id"]
        assert (tmp_path / "raw" / "ollama-timeout-runbook.md").exists()

        rows = VaultSearch(db).search("ollama timeout gpu fix", mode="keyword", limit=3, use_rerank=False)
        assert rows
        assert rows[0]["title"] == "Ollama Timeout Runbook"

        nodes = db.conn.execute(
            "SELECT count(*) AS count FROM knowledge_nodes WHERE knowledge_id=?",
            (promoted["knowledge_id"],),
        ).fetchone()
        assert int(nodes["count"]) >= 1
