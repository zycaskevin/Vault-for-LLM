import json
import subprocess
import sys
from pathlib import Path

from vault.db import VaultDB
from vault.memory import create_candidate, duplicate_gate, promote_candidate
from vault.privacy import scan_privacy

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_privacy_gate_blocks_tokens_with_redacted_span():
    # Build a token-shaped value at runtime so repository secret scans do not
    # flag this test fixture as a real credential.
    token = "ghp_" + "A" * 36
    result = scan_privacy(f"Do not store password=supersecret123 or {token}")
    assert result["status"] == "fail"

    types = {f["type"] for f in result["findings"]}
    assert {"password", "github_token"}.issubset(types)
    assert all("supersecret123" not in f["span"] for f in result["findings"])
    assert all(token not in f["span"] for f in result["findings"])


def test_duplicate_gate_warns_on_same_title(tmp_path):
    with VaultDB(tmp_path / "vault.db") as db:
        db.add_knowledge(title="Same Title", content_raw="Original body", source="test")
        result = duplicate_gate(db, " same   title ", "Different body")
        assert result["status"] == "warn"
        assert any(f["type"] == "active_title" for f in result["findings"])


def test_candidate_creation_does_not_alter_active_knowledge(tmp_path):
    with VaultDB(tmp_path / "vault.db") as db:
        before = db.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"]
        result = create_candidate(
            db,
            title="Candidate only",
            content="This should remain outside active knowledge.",
            reason="Useful future context",
            source="test",
        )
        after = db.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"]
        row = db.get_memory_candidate(result["candidate_id"])
        assert result["status"] == "candidate_created"
        assert before == after == 0
        assert row["title"] == "Candidate only"
        assert json.loads(row["gate_payload_json"])["privacy"]["status"] == "pass"


def test_privacy_fail_candidate_is_rejected_and_redacted(tmp_path):
    raw_key = "abcdefghijklmnop"
    with VaultDB(tmp_path / "vault.db") as db:
        result = create_candidate(
            db,
            title="Secret candidate",
            content=f"Do not store api_key={raw_key} in memory.",
            reason="Regression for rejected secret proposals",
            source="test",
        )
        row = db.get_memory_candidate(result["candidate_id"])

        assert row is not None
        assert result["status"] == "rejected"
        assert result["gates"]["privacy"] == "fail"
        assert "next_action" not in result
        assert row["status"] == "rejected"
        assert raw_key not in row["content"]
        assert "[REDACTED]" in row["content"]
        promoted = promote_candidate(db, result["candidate_id"], confirm=True, project_dir=tmp_path)
        assert promoted["status"] == "blocked"
        assert promoted["knowledge_id"] is None


def test_promotion_writes_raw_and_active_db(tmp_path):
    with VaultDB(tmp_path / "vault.db") as db:
        result = create_candidate(
            db,
            title="Promote Me",
            content="Promotion writes a raw Markdown note and active knowledge row.",
            layer="L2",
            category="test",
            tags=["memory", "promotion"],
            trust=0.8,
            reason="Exercise promotion scaffolding",
            source="test",
        )
        promoted = promote_candidate(db, result["candidate_id"], confirm=True, project_dir=tmp_path)
        raw_path = tmp_path / "raw" / "promote-me.md"
        candidate = db.get_memory_candidate(result["candidate_id"])
        knowledge = db.get_knowledge(promoted["knowledge_id"])

        assert promoted["status"] == "promoted"
        assert raw_path.exists()
        raw_text = raw_path.read_text(encoding="utf-8")
        assert "memory_candidate_id" in raw_text
        assert "Promotion writes" in raw_text
        assert candidate["status"] == "promoted"
        assert candidate["promoted_knowledge_id"] == promoted["knowledge_id"]
        assert knowledge["title"] == "Promote Me"
        assert knowledge["content_raw"] == "Promotion writes a raw Markdown note and active knowledge row."
        assert knowledge["layer"] == "L2"


def test_cli_remember_and_promote_smoke(tmp_path):
    with VaultDB(tmp_path / "vault.db"):
        pass
    env = {"PYTHONPATH": str(REPO_ROOT)}
    remember = subprocess.run(
        [
            sys.executable,
            "-m",
            "vault.cli",
            "remember",
            "CLI memory",
            "--content",
            "CLI remember creates a candidate first.",
            "--reason",
            "CLI smoke",
            "--mode",
            "candidate",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert remember.returncode == 0, remember.stderr
    proposed = json.loads(remember.stdout)
    assert proposed["status"] == "candidate_created"

    promote = subprocess.run(
        [
            sys.executable,
            "-m",
            "vault.cli",
            "promote",
            proposed["candidate_id"],
            "--confirm",
            "--no-compile",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert promote.returncode == 0, promote.stderr
    promoted = json.loads(promote.stdout)
    assert promoted["status"] == "promoted"
    assert promoted["knowledge_id"]
    assert (tmp_path / "raw" / "cli-memory.md").exists()
