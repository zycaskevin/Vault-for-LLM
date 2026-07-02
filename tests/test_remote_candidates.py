import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vault.db import VaultDB
from vault.remote_candidates import (
    REMOTE_CANDIDATE_RPC,
    REMOTE_CANDIDATE_TABLE,
    build_remote_candidate_request,
    pull_remote_candidate_requests,
    submit_remote_candidate_request,
)
from vault.sync_integrity import sign_sync_payload


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeRpcQuery:
    def __init__(self, client, name, params):
        self.client = client
        self.name = name
        self.params = params

    def execute(self):
        self.client.rpc_calls.append((self.name, dict(self.params)))
        return _FakeResponse([{"id": "req-1", "status": "submitted", "created_at": "2026-07-01T00:00:00Z"}])


class _FakeTableQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.filters = []
        self.update_payload = None
        self.limit_value = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def update(self, payload):
        self.update_payload = dict(payload)
        return self

    def execute(self):
        rows = self.client.tables.setdefault(self.table_name, [])
        if self.update_payload is not None:
            for row in rows:
                if all(row.get(field) == value for field, value in self.filters):
                    row.update(self.update_payload)
                    self.client.updates.append(dict(row))
            return _FakeResponse([])
        matches = [
            dict(row)
            for row in rows
            if all(row.get(field) == value for field, value in self.filters)
        ]
        if self.limit_value is not None:
            matches = matches[: self.limit_value]
        return _FakeResponse(matches)


class _FakeSupabaseClient:
    def __init__(self, rows=None):
        self.tables = {REMOTE_CANDIDATE_TABLE: rows or []}
        self.rpc_calls = []
        self.updates = []

    def rpc(self, name, params):
        return _FakeRpcQuery(self, name, params)

    def table(self, name):
        return _FakeTableQuery(self, name)


def test_build_remote_candidate_request_clamps_to_safe_public_boundary():
    payload = build_remote_candidate_request(
        title=" Remote lesson ",
        content="Use guarded candidate sync before active remote writes.",
        from_agent="remote-agent",
        tags="sync, memory",
        scope="private",
        sensitivity="restricted",
        allowed_agents='["work-agent"]',
    )

    assert payload["scope"] == "project"
    assert payload["sensitivity"] == "low"
    assert payload["tags"] == ["sync", "memory"]
    assert payload["allowed_agents"] == ["work-agent"]
    assert payload["idempotency_key"]


def test_submit_remote_candidate_request_calls_guarded_rpc():
    client = _FakeSupabaseClient()

    payload = submit_remote_candidate_request(
        sb_client=client,
        title="Remote sync lesson",
        content="Remote hosts should submit candidate requests, not active knowledge.",
        reason="keeps active vault reviewed",
        from_agent="remote-agent",
        trust=0.88,
        scope="shared",
        sensitivity="medium",
    )

    assert payload["ok"] is True
    assert payload["id"] == "req-1"
    assert client.rpc_calls[0][0] == REMOTE_CANDIDATE_RPC
    params = client.rpc_calls[0][1]
    assert params["p_title"] == "Remote sync lesson"
    assert params["p_trust"] == 0.88
    assert params["p_scope"] == "shared"
    assert params["p_sensitivity"] == "medium"
    assert "p_content" in params
    assert "content" not in payload["request"]


def test_submit_remote_candidate_request_can_sign_payload():
    client = _FakeSupabaseClient()

    payload = submit_remote_candidate_request(
        sb_client=client,
        hmac_secret="sync-secret",
        title="Signed remote sync lesson",
        content="Remote candidate sync payloads should carry HMAC metadata when a shared secret is configured.",
        from_agent="remote-agent",
        trust=0.8,
    )

    assert payload["ok"] is True
    params = client.rpc_calls[0][1]
    assert params["p_hmac_algorithm"] == "hmac-sha256-v1"
    assert len(params["p_payload_hash"]) == 64
    assert len(params["p_hmac_signature"]) == 64


def test_pull_remote_candidate_requests_imports_into_local_candidate_queue(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    db = VaultDB(project / "vault.db").connect()
    db.close()
    client = _FakeSupabaseClient(
        [
            {
                "id": "req-1",
                "status": "submitted",
                "created_at": "2026-07-01T00:00:00Z",
                "from_agent": "remote-agent",
                "title": "Remote candidate sync rule",
                "content": "Remote hosts should submit memory as candidates because active knowledge must stay reviewed.",
                "reason": "multi-host safety boundary",
                "category": "workflow",
                "tags": ["remote", "candidate"],
                "trust": 0.7,
                "scope": "shared",
                "sensitivity": "low",
                "owner_agent": "remote-agent",
                "allowed_agents": ["work-agent"],
                "memory_type": "remote_candidate",
                "source_ref": "",
            }
        ]
    )

    preview = pull_remote_candidate_requests(project, sb_client=client, apply=False)
    assert preview["ok"] is True
    assert preview["count"] == 1
    assert preview["imported_count"] == 0
    assert preview["requests"][0]["title"] == "Remote candidate sync rule"

    applied = pull_remote_candidate_requests(project, sb_client=client, apply=True, agent_id="sync-agent")
    assert applied["imported_count"] == 1
    assert applied["requests"][0]["local_candidate_id"].startswith("mem_")
    assert client.updates[-1]["status"] == "imported"

    db = VaultDB(project / "vault.db").connect()
    try:
        rows = db.list_memory_candidates()
        assert len(rows) == 1
        assert rows[0]["source"] == "remote_write_request"
        assert rows[0]["source_ref"] == "remote_write_request:req-1"
        assert rows[0]["status"] == "candidate"
        assert db.conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0] == 0
    finally:
        db.close()


def test_pull_remote_candidate_requests_requires_valid_hmac_before_import(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    db = VaultDB(project / "vault.db").connect()
    db.close()
    good = build_remote_candidate_request(
        title="Signed candidate sync rule",
        content="Decision: signed remote candidates can be imported because HMAC verifies payload integrity.",
        from_agent="remote-agent",
        reason="multi-host safety",
        category="decision",
        tags=["remote", "hmac"],
        trust=0.88,
        scope="shared",
        sensitivity="low",
    )
    good.update(sign_sync_payload(good, "sync-secret"))
    bad = dict(good)
    bad.update(
        {
            "idempotency_key": "tampered-request",
            "title": "Tampered candidate sync rule",
            "content": "Decision: this content was changed after signing.",
        }
    )
    client = _FakeSupabaseClient(
        [
            {"id": "req-signed", "status": "submitted", "created_at": "2026-07-01T00:00:00Z", **good},
            {"id": "req-tampered", "status": "submitted", "created_at": "2026-07-01T00:00:01Z", **bad},
        ]
    )

    payload = pull_remote_candidate_requests(
        project,
        sb_client=client,
        apply=True,
        hmac_secret="sync-secret",
        require_hmac=True,
    )

    assert payload["integrity"]["hmac_required"] is True
    assert payload["integrity"]["verified_count"] == 1
    assert payload["integrity"]["invalid_count"] == 1
    assert payload["imported_count"] == 1
    assert payload["skipped_count"] == 1
    signed = next(item for item in payload["requests"] if item["id"] == "req-signed")
    tampered = next(item for item in payload["requests"] if item["id"] == "req-tampered")
    assert signed["integrity"]["status"] == "verified"
    assert tampered["status"] == "signature_invalid"
    assert tampered["integrity"]["error"] in {"payload_hash_mismatch", "hmac_signature_mismatch"}
    assert any(row["status"] == "signature_invalid" for row in client.updates)
    with VaultDB(project / "vault.db") as db:
        rows = db.list_memory_candidates()
    assert len(rows) == 1
    assert rows[0]["title"] == "Signed candidate sync rule"


def test_pull_remote_candidate_requests_can_auto_promote_only_imported_low_risk_items(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "automation_policy.yaml").write_text(
        "\n".join(
            [
                "mode: balanced",
                "auto_promote_low_risk_candidates: true",
                "auto_promote_allowed_sources:",
                "  - remote_write_request",
                "auto_promote_allowed_memory_types:",
                "  - remote_candidate",
                "auto_promote_allowed_scopes:",
                "  - shared",
                "auto_promote_allowed_sensitivities:",
                "  - low",
                "auto_promote_min_trust: 0.8",
                "auto_promote_max_per_run: 2",
                "auto_promote_requires_source_ref: true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    db = VaultDB(project / "vault.db").connect()
    db.close()
    client = _FakeSupabaseClient(
        [
            {
                "id": "req-safe",
                "status": "submitted",
                "created_at": "2026-07-01T00:00:00Z",
                "from_agent": "remote-agent",
                "title": "Remote candidate auto merge rule",
                "content": (
                    "Decision: remote candidates can be auto-promoted because low risk requests "
                    "must pass privacy, duplicate, metadata, and quality gates first."
                ),
                "reason": "Safe multi-host candidate merge because policy allows it.",
                "category": "decision",
                "tags": ["remote", "candidate", "automation"],
                "trust": 0.92,
                "scope": "shared",
                "sensitivity": "low",
                "owner_agent": "remote-agent",
                "allowed_agents": [],
                "memory_type": "remote_candidate",
                "source_ref": "",
            },
            {
                "id": "req-low-trust",
                "status": "submitted",
                "created_at": "2026-07-01T00:00:01Z",
                "from_agent": "remote-agent",
                "title": "Remote low trust candidate stays reviewable",
                "content": (
                    "Decision: low trust remote requests should stay candidates because automatic "
                    "promotion requires a higher trust threshold."
                ),
                "reason": "Low trust should require a human review.",
                "category": "decision",
                "tags": ["remote", "candidate", "review"],
                "trust": 0.55,
                "scope": "shared",
                "sensitivity": "low",
                "owner_agent": "remote-agent",
                "allowed_agents": [],
                "memory_type": "remote_candidate",
                "source_ref": "",
            },
        ]
    )

    payload = pull_remote_candidate_requests(
        project,
        sb_client=client,
        apply=True,
        auto_promote_low_risk=True,
    )

    assert payload["imported_count"] == 2
    assert payload["auto_promote"]["promoted_count"] == 1
    safe = next(item for item in payload["requests"] if item["id"] == "req-safe")
    low_trust = next(item for item in payload["requests"] if item["id"] == "req-low-trust")
    assert safe["status"] == "promoted_locally"
    assert safe["knowledge_id"]
    assert low_trust["status"] == "imported"
    assert client.updates[-1]["status"] == "promoted_locally"

    db = VaultDB(project / "vault.db").connect()
    try:
        assert db.conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0] == 1
        candidates = db.list_memory_candidates(limit=10)
        assert {row["status"] for row in candidates} == {"promoted", "candidate"}
    finally:
        db.close()


def test_remote_candidate_cli_submit_uses_json_output(tmp_path, monkeypatch, capsys):
    from vault.cli import main
    import vault.remote_candidates as remote_candidates

    project = tmp_path / "project"
    main(["init", "--project-dir", str(project)])
    capsys.readouterr()

    monkeypatch.setattr(
        remote_candidates,
        "submit_remote_candidate_request",
        lambda **_kwargs: {"ok": True, "id": "req-cli", "status": "submitted"},
    )

    main(
        [
            "remote",
            "submit-candidate",
            "--project-dir",
            str(project),
            "--title",
            "CLI remote lesson",
            "--content",
            "Remote CLI submissions remain candidate-first.",
            "--json",
        ]
    )

    out = capsys.readouterr().out
    assert '"id": "req-cli"' in out
    assert '"status": "submitted"' in out


def test_remote_candidate_cli_pull_preview_is_available(tmp_path, monkeypatch, capsys):
    from vault.cli import main
    import vault.remote_candidates as remote_candidates

    project = tmp_path / "project"
    main(["init", "--project-dir", str(project)])
    capsys.readouterr()

    monkeypatch.setattr(
        remote_candidates,
        "pull_remote_candidate_requests",
        lambda *_args, **_kwargs: {
            "ok": True,
            "apply": False,
            "count": 1,
            "imported_count": 0,
            "skipped_count": 0,
            "requests": [{"id": "req-cli", "title": "Preview me", "status": "submitted"}],
        },
    )

    main(["remote", "pull-candidates", "--project-dir", str(project)])

    out = capsys.readouterr().out
    assert "remote candidate pull: preview" in out
    assert "Preview me" in out
