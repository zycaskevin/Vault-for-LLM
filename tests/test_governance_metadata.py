import json

from vault.compiler import VaultCompiler
from vault.db import VaultDB, normalize_allowed_agents, normalize_governance_metadata
from vault.memory import promote_candidate, propose_memory


def test_normalize_governance_metadata_accepts_csv_json_and_lists():
    assert normalize_allowed_agents(["profile-agent", "work-agent"]) == '["profile-agent", "work-agent"]'
    assert normalize_allowed_agents('["product-agent", "codex"]') == '["product-agent", "codex"]'
    assert normalize_allowed_agents("profile-agent,work-agent") == '["profile-agent", "work-agent"]'

    meta = normalize_governance_metadata(
        scope="SHARED",
        sensitivity="medium",
        owner_agent=" profile-agent ",
        allowed_agents="work-agent,product-agent",
        memory_type="care_summary",
        expires_at="2026-07-01T00:00:00Z",
    )

    assert meta == {
        "scope": "shared",
        "sensitivity": "medium",
        "owner_agent": "profile-agent",
        "allowed_agents": '["work-agent", "product-agent"]',
        "memory_type": "care_summary",
        "expires_at": "2026-07-01T00:00:00Z",
    }


def test_add_knowledge_persists_governance_metadata(tmp_path):
    with VaultDB(tmp_path / "vault.db") as db:
        kid = db.add_knowledge(
            title="Shared project decision",
            content_raw="Use shared memory for reviewed project decisions.",
            source="test",
            scope="shared",
            sensitivity="medium",
            owner_agent="profile-agent",
            allowed_agents=["work-agent", "product-agent"],
            memory_type="decision",
            expires_at="2026-07-01T00:00:00Z",
        )
        row = db.get_knowledge(kid)

    assert row["scope"] == "shared"
    assert row["sensitivity"] == "medium"
    assert row["owner_agent"] == "profile-agent"
    assert json.loads(row["allowed_agents"]) == ["work-agent", "product-agent"]
    assert row["memory_type"] == "decision"
    assert row["expires_at"] == "2026-07-01T00:00:00Z"


def test_candidate_promotion_preserves_governance_metadata(tmp_path):
    with VaultDB(tmp_path / "vault.db") as db:
        proposal = propose_memory(
            db,
            title="Care summary routing",
            content="Care summary routing is caused by multi-agent privacy needs; the fix is to share summaries, not raw private chats.",
            reason="Keep cross-agent care summaries reviewable.",
            tags="care,privacy",
            category="care",
            source="test",
            scope="shared",
            sensitivity="medium",
            owner_agent="profile-agent",
            allowed_agents=["care-agent", "work-agent"],
            memory_type="care_summary",
        )
        promoted = promote_candidate(
            db,
            proposal["candidate_id"],
            confirm=True,
            project_dir=tmp_path,
            compile=False,
        )
        knowledge = promoted["knowledge"]
        candidate = promoted["candidate"]

    assert candidate["scope"] == "shared"
    assert candidate["sensitivity"] == "medium"
    assert candidate["owner_agent"] == "profile-agent"
    assert json.loads(candidate["allowed_agents"]) == ["care-agent", "work-agent"]
    assert candidate["memory_type"] == "care_summary"
    assert knowledge["scope"] == "shared"
    assert knowledge["sensitivity"] == "medium"
    assert knowledge["owner_agent"] == "profile-agent"
    assert json.loads(knowledge["allowed_agents"]) == ["care-agent", "work-agent"]
    assert knowledge["memory_type"] == "care_summary"


def test_compiler_preserves_governance_frontmatter(tmp_path):
    project = tmp_path / "project"
    raw = project / "raw"
    raw.mkdir(parents=True)
    (raw / "profile-summary.md").write_text(
        "---\n"
        "title: Profile Summary\n"
        "layer: L1\n"
        "category: profile\n"
        "tags: [profile, user]\n"
        "trust: 0.8\n"
        "scope: shared\n"
        "sensitivity: medium\n"
        "owner_agent: profile-agent\n"
        "allowed_agents: [work-agent, product-agent]\n"
        "memory_type: profile_summary\n"
        "expires_at: 2026-07-01T00:00:00Z\n"
        "---\n\n"
        "the user prefers reviewed shared summaries instead of exposing raw private chats.\n",
        encoding="utf-8",
    )

    with VaultDB(project / "vault.db") as db:
        compiler = VaultCompiler(project, db=db, embed_provider=None)
        stats = compiler.compile(dry_run=False)
        row = db.conn.execute("SELECT * FROM knowledge WHERE title = ?", ("Profile Summary",)).fetchone()

    assert stats["new"] == 1
    assert row["scope"] == "shared"
    assert row["sensitivity"] == "medium"
    assert row["owner_agent"] == "profile-agent"
    assert json.loads(row["allowed_agents"]) == ["work-agent", "product-agent"]
    assert row["memory_type"] == "profile_summary"
    assert row["expires_at"] == "2026-07-01T00:00:00+00:00"
