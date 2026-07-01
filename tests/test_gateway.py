from __future__ import annotations

import http.client
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

import pytest

from vault.cli import main
from vault.db import VaultDB
from vault.docmap import build_document_map_for_entry
from vault.gateway import (
    gateway_read_range,
    gateway_openapi,
    gateway_search,
    gateway_submit_candidate,
    make_gateway_handler,
    run_gateway,
)
from vault.agent_setup_remote_server import write_remote_server_deploy_templates


def _project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    with VaultDB(project / "vault.db") as db:
        public_id = db.add_knowledge(
            "Shared Gateway Runbook",
            "# Shared Gateway Runbook\n\nGateway search should find this shared runbook.\n\n## Evidence\n\nAgents should read bounded ranges.",
            category="runbook",
            tags="gateway,shared",
            scope="shared",
            sensitivity="low",
            trust=0.9,
        )
        build_document_map_for_entry(db, public_id)
        private_id = db.add_knowledge(
            "Private Gateway Note",
            "# Private Gateway Note\n\nOnly the owner should see this private note.",
            category="private",
            tags="gateway,private",
            scope="private",
            sensitivity="high",
            owner_agent="profile-agent",
            trust=0.9,
        )
        build_document_map_for_entry(db, private_id)
    return project, public_id, private_id


def _post_json(host, port, path, payload, *, token="secret"):
    conn = http.client.HTTPConnection(host, port, timeout=5)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    conn.request("POST", path, json.dumps(payload).encode("utf-8"), headers)
    response = conn.getresponse()
    body = response.read()
    conn.close()
    return response.status, json.loads(body.decode("utf-8"))


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_remote_server(url: str, token: str, *, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            conn = http.client.HTTPConnection(url.replace("http://", ""), timeout=1)
            conn.request("GET", "/health", headers={"Authorization": f"Bearer {token}"})
            response = conn.getresponse()
            response.read()
            conn.close()
            if response.status == 200:
                return
        except Exception as exc:
            last_error = exc
        time.sleep(0.1)
    raise AssertionError(f"remote server did not become ready: {last_error}")


def test_gateway_http_requires_token_and_serves_health(tmp_path):
    project, _public_id, _private_id = _project(tmp_path)
    handler = make_gateway_handler(project, auth_token="secret")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/health")
        denied = conn.getresponse()
        assert denied.status == 401
        denied.read()
        conn.close()

        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/health", headers={"X-Vault-Gateway-Token": "secret"})
        allowed = conn.getresponse()
        assert allowed.status == 200
        payload = json.loads(allowed.read().decode("utf-8"))
        assert payload["status"] == "ok"
        assert payload["gateway"]["candidate_first_writes"] is True
        assert "/openapi.json" in payload["gateway"]["endpoints"]
        assert payload["gateway"]["remote_ready"]["active_multi_master_sync"] is False
        conn.close()

        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/openapi.json", headers={"X-Vault-Gateway-Token": "secret"})
        contract_response = conn.getresponse()
        assert contract_response.status == 200
        contract = json.loads(contract_response.read().decode("utf-8"))
        assert contract["info"]["title"] == "Vault Gateway"
        assert contract["x-vault-safety"]["candidate_first_writes"] is True
        assert contract["x-vault-safety"]["writes_active_knowledge"] is False
        conn.close()
    finally:
        server.shutdown()
        server.server_close()


def test_gateway_search_and_read_range_apply_agent_policy(tmp_path):
    project, public_id, private_id = _project(tmp_path)

    missing_agent = gateway_search(project, query="Gateway", agent_id="")
    assert missing_agent["error"] == "agent_id_required"

    search = gateway_search(project, query="Gateway", agent_id="work-agent", max_sensitivity="low")
    assert search["status"] == "ok"
    titles = {row["title"] for row in search["results"]}
    assert "Shared Gateway Runbook" in titles
    assert "Private Gateway Note" not in titles

    denied = gateway_read_range(
        project,
        knowledge_id=private_id,
        agent_id="work-agent",
        include_private=False,
        max_sensitivity="low",
        line_start=1,
        line_end=2,
    )
    assert denied["error"] == "access_denied"

    allowed = gateway_read_range(
        project,
        knowledge_id=public_id,
        agent_id="work-agent",
        include_private=False,
        max_sensitivity="low",
        line_start=1,
        line_end=2,
    )
    assert allowed["status"] == "ok"
    assert allowed["entry_id"] == public_id
    assert "Shared Gateway Runbook" in allowed["title"]


def test_gateway_submit_candidate_is_candidate_first_and_policy_bound(tmp_path):
    project, _public_id, _private_id = _project(tmp_path)

    blocked = gateway_submit_candidate(
        project,
        title="Shared candidate",
        content="Decision: shared candidates need an explicit gateway launch flag because shared memory affects other agents.",
        agent_id="work-agent",
        scope="shared",
    )
    assert blocked["error"] == "access_denied"

    accepted = gateway_submit_candidate(
        project,
        title="Project candidate",
        content="Decision: project gateway candidates stay in review because Gateway v0 must not write active memory.",
        agent_id="work-agent",
        scope="project",
    )
    assert accepted["status"] == "ok"
    assert accepted["safety"]["writes_active_knowledge"] is False
    with VaultDB(project / "vault.db") as db:
        candidates = db.list_memory_candidates(status=None)
        active_count = db.conn.execute("SELECT count(*) AS count FROM knowledge").fetchone()["count"]
    assert len(candidates) == 1
    assert candidates[0]["source"] == "gateway:work-agent"
    assert candidates[0]["status"] == "candidate"
    assert active_count == 2


def test_gateway_openapi_contract_documents_safe_adapter_boundary():
    contract = gateway_openapi()
    assert contract["openapi"].startswith("3.")
    assert {"/health", "/openapi.json", "/search", "/read-range", "/submit-candidate"} <= set(contract["paths"])
    assert contract["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
    safety = contract["x-vault-safety"]
    assert safety["agent_id_required_for_reads"] is True
    assert safety["private_hidden_by_default"] is True
    assert safety["search_returns_raw_content"] is False
    assert safety["writes_active_knowledge"] is False
    assert safety["candidate_first_writes"] is True


def test_gateway_http_search_submit_and_audit(tmp_path):
    project, _public_id, _private_id = _project(tmp_path)
    handler = make_gateway_handler(project, auth_token="secret")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        status, search = _post_json(
            host,
            port,
            "/search",
            {"agent_id": "work-agent", "query": "runbook", "max_sensitivity": "low"},
        )
        assert status == 200
        assert search["status"] == "ok"
        assert search["results"]

        status, submitted = _post_json(
            host,
            port,
            "/submit-candidate",
            {
                "agent_id": "work-agent",
                "title": "Gateway candidate",
                "content": "Decision: Gateway HTTP writes should create review candidates because agents need one safe door.",
            },
        )
        assert status == 200
        assert submitted["status"] == "ok"
    finally:
        server.shutdown()
        server.server_close()

    audit = project / "reports" / "gateway" / "audit.jsonl"
    assert audit.exists()
    lines = audit.read_text(encoding="utf-8").splitlines()
    assert any('"event": "search"' in line for line in lines)
    assert any('"event": "submit_candidate"' in line for line in lines)


def test_gateway_http_tolerates_bad_numeric_fields(tmp_path):
    project, _public_id, _private_id = _project(tmp_path)
    handler = make_gateway_handler(project, auth_token="secret")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        status, search = _post_json(
            host,
            port,
            "/search",
            {"agent_id": "work-agent", "query": "runbook", "limit": "not-a-number"},
        )
        assert status == 200
        assert search["status"] == "ok"

        status, read = _post_json(
            host,
            port,
            "/read-range",
            {
                "agent_id": "work-agent",
                "knowledge_id": "not-a-number",
                "line_start": "also-bad",
            },
        )
        assert status == 200
        assert read["status"] == "error"
    finally:
        server.shutdown()
        server.server_close()


def test_gateway_no_auth_requires_localhost(tmp_path):
    with pytest.raises(ValueError):
        run_gateway(tmp_path, host="0.0.0.0", no_auth=True)


def test_remote_server_cli_and_generated_validation_script_end_to_end(tmp_path):
    project, _public_id, _private_id = _project(tmp_path)
    templates = write_remote_server_deploy_templates(output_dir=tmp_path / "templates", project_dir=project)
    validation_script = Path(templates["remote_clients"]["validation_script"])
    port = _free_local_port()
    url = f"http://127.0.0.1:{port}"
    token = "stable-test-token"
    env = os.environ.copy()
    env["VAULT_GATEWAY_TOKEN"] = token
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "vault.cli",
            "remote-server",
            "serve",
            "--project-dir",
            str(project),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        _wait_for_remote_server(url, token)
        read_only = subprocess.run(
            [
                sys.executable,
                str(validation_script),
                "--agent-id",
                "codex",
                "--query",
                "runbook",
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**env, "VAULT_REMOTE_URL": url},
        )
        read_payload = json.loads(read_only.stdout)
        assert read_payload["ok"] is True
        assert read_payload["submitted_candidate"] is False
        assert [item["name"] for item in read_payload["checks"]] == ["health", "openapi", "search"]

        write_smoke = subprocess.run(
            [
                sys.executable,
                str(validation_script),
                "--agent-id",
                "codex",
                "--query",
                "runbook",
                "--submit-candidate",
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**env, "VAULT_REMOTE_URL": url},
        )
        write_payload = json.loads(write_smoke.stdout)
        assert write_payload["ok"] is True
        assert write_payload["submitted_candidate"] is True
        assert [item["name"] for item in write_payload["checks"]] == [
            "health",
            "openapi",
            "search",
            "submit_candidate",
        ]
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    with VaultDB(project / "vault.db") as db:
        candidates = db.list_memory_candidates(status=None)
        active_count = db.conn.execute("SELECT count(*) AS count FROM knowledge").fetchone()["count"]
    assert len(candidates) == 1
    assert candidates[0]["source"] == "gateway:codex"
    assert active_count == 2


def test_remote_server_serve_requires_stable_token(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("VAULT_GATEWAY_TOKEN", raising=False)
    project, _public_id, _private_id = _project(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["remote-server", "serve", "--project-dir", str(project)])
    assert exc.value.code == 2
    output = capsys.readouterr().out
    assert "requires a stable token" in output
