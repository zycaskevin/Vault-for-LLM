"""Self-hosted Vault Remote Server deployment template helpers."""

from __future__ import annotations

import json
from pathlib import Path

from vault.agent_setup_templates import shell_join
from vault.gateway import gateway_openapi


def write_remote_server_deploy_templates(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    vault_executable: str = "vault",
) -> dict[str, str]:
    """Write inert self-hosted Vault Remote Server deployment templates."""
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    project_path = Path(project_dir).expanduser().resolve()
    command = [
        vault_executable,
        "remote-server",
        "serve",
        "--project-dir",
        str(project_path),
        "--host",
        "0.0.0.0",
    ]
    health_command = [
        vault_executable,
        "remote-server",
        "health",
        "--project-dir",
        str(project_path),
        "--json",
    ]
    openapi_command = [
        vault_executable,
        "remote-server",
        "openapi",
        "--project-dir",
        str(project_path),
        "--json",
    ]

    launchagent_path = out / "vault-remote-server.launchagent.plist"
    launchagent_path.write_text(_render_remote_server_launchagent(command), encoding="utf-8")

    systemd_path = out / "vault-remote-server.service"
    systemd_path.write_text(
        "\n".join(
            [
                "[Unit]",
                "Description=Vault-for-LLM Remote Server",
                "After=network-online.target",
                "Wants=network-online.target",
                "",
                "[Service]",
                "Type=simple",
                "Environment=VAULT_GATEWAY_TOKEN=replace-with-stable-secret",
                f"ExecStart={shell_join(command)}",
                "Restart=on-failure",
                "RestartSec=5",
                "",
                "[Install]",
                "WantedBy=multi-user.target",
                "",
            ]
        ),
        encoding="utf-8",
    )

    compose_path = out / "vault-remote-server.compose.yaml"
    compose_path.write_text(
        "\n".join(
            [
                "services:",
                "  vault-remote-server:",
                "    image: python:3.12-slim",
                "    working_dir: /vault-project",
                "    command:",
                "      - sh",
                "      - -lc",
                "      - >",
                "        python -m pip install --no-cache-dir 'vault-for-llm[mcp]' &&",
                f"        {shell_join(command)}",
                "    ports:",
                "      - \"8789:8789\"",
                "    environment:",
                "      VAULT_GATEWAY_TOKEN: ${VAULT_GATEWAY_TOKEN:?set a stable token}",
                "    volumes:",
                f"      - {str(project_path)}:/vault-project",
                "",
            ]
        ),
        encoding="utf-8",
    )

    readme_path = out / "README-remote-server.md"
    readme_path.write_text(
        "\n".join(
            [
                "# Vault Remote Server Deployment",
                "",
                "Use this when the user wants one self-hosted central memory host instead of Supabase.",
                "",
                "Remote Server reuses the Gateway contract:",
                "",
                "- search active memory with read policy;",
                "- read bounded source ranges;",
                "- submit candidate memories;",
                "- never write active memory directly;",
                "- no offline active multi-master sync yet.",
                "",
                "Before serving, set a stable token:",
                "",
                "```bash",
                "export VAULT_GATEWAY_TOKEN=\"replace-with-stable-secret\"",
                "```",
                "",
                "Readiness checks:",
                "",
                "```bash",
                shell_join(health_command),
                shell_join(openapi_command),
                "```",
                "",
                "Run directly:",
                "",
                "```bash",
                shell_join(command),
                "```",
                "",
                "Generated deployment templates:",
                "",
                f"- macOS LaunchAgent example: `{launchagent_path.name}`",
                f"- systemd service example: `{systemd_path.name}`",
                f"- Docker Compose example: `{compose_path.name}`",
                "- remote client examples: `README-remote-clients.md`",
                "",
                "Network guidance:",
                "",
                "- Prefer a private network such as Tailscale, WireGuard, or LAN-only routing.",
                "- Do not expose this server publicly without TLS, firewalling, and a rotated token.",
                "- Keep remote writes candidate-first; promote from the trusted Vault review flow.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    remote_client_templates = _write_remote_client_templates(out)
    return {
        "readme": str(readme_path),
        "health_command": shell_join(health_command),
        "openapi_command": shell_join(openapi_command),
        "serve_command": shell_join(command),
        "launchagent": str(launchagent_path),
        "systemd": str(systemd_path),
        "docker_compose": str(compose_path),
        "remote_clients": remote_client_templates,
    }


def _write_remote_client_templates(out: Path) -> dict[str, str]:
    gateway_url = "https://vault.example.internal:8789"
    openapi = gateway_openapi(title="Vault Remote Server")
    openapi["servers"] = [{"url": gateway_url}]
    openapi.setdefault("x-vault-client-template", {})
    openapi["x-vault-client-template"] = {
        "gateway_url_env": "VAULT_REMOTE_URL",
        "token_env": "VAULT_GATEWAY_TOKEN",
        "agent_id_header": False,
        "remote_writes": "candidate_first",
        "active_multi_master_sync": False,
    }

    coze_openapi_path = out / "coze-vault-remote-openapi.json"
    coze_openapi_path.write_text(
        json.dumps(openapi, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    client_config = {
        "version": 1,
        "mode": "remote_gateway_client",
        "gateway_url_env": "VAULT_REMOTE_URL",
        "token_env": "VAULT_GATEWAY_TOKEN",
        "default_gateway_url": gateway_url,
        "auth_headers": {
            "Authorization": "Bearer ${VAULT_GATEWAY_TOKEN}",
            "X-Vault-Gateway-Token": "${VAULT_GATEWAY_TOKEN}",
        },
        "required_request_fields": ["agent_id"],
        "safe_first_requests": [
            {"method": "GET", "path": "/health"},
            {"method": "GET", "path": "/openapi.json"},
            {
                "method": "POST",
                "path": "/search",
                "body": {"agent_id": "<agent-id>", "query": "<task keyword>", "limit": 5},
            },
            {
                "method": "POST",
                "path": "/read-range",
                "body": {"agent_id": "<agent-id>", "knowledge_id": "<id>", "line_start": 1, "line_end": 40},
            },
            {
                "method": "POST",
                "path": "/submit-candidate",
                "body": {
                    "agent_id": "<agent-id>",
                    "title": "<memory proposal>",
                    "content": "<reviewable memory>",
                    "reason": "<why remember>",
                },
            },
        ],
        "clients": {
            "codex": {
                "target": "Project AGENTS.md or MCP/Gateway adapter note",
                "env": {"VAULT_REMOTE_URL": gateway_url, "VAULT_GATEWAY_TOKEN": "replace-with-stable-secret"},
                "startup_note": "Use the remote Gateway only when the local project vault is not available.",
            },
            "claude_code": {
                "target": "Project CLAUDE.md adapter note",
                "env": {"VAULT_REMOTE_URL": gateway_url, "VAULT_GATEWAY_TOKEN": "replace-with-stable-secret"},
                "startup_note": "Search remote memory first, then bounded read before citing.",
            },
            "hermes": {
                "target": "Hermes profile AGENTS.md or runtime bootstrap",
                "env": {"VAULT_REMOTE_URL": gateway_url, "VAULT_GATEWAY_TOKEN": "replace-with-stable-secret"},
                "startup_note": "Keep profile identity private; use remote shared memory for project knowledge.",
            },
            "openclaw": {
                "target": "OpenClaw workspace bootstrap or gateway plugin config",
                "env": {"VAULT_REMOTE_URL": gateway_url, "VAULT_GATEWAY_TOKEN": "replace-with-stable-secret"},
                "startup_note": "Read local latest-context first when present; use remote Gateway for shared Vault memory.",
            },
            "coze": {
                "target": coze_openapi_path.name,
                "mode": "openapi_connector",
                "warning": "Use a scoped Gateway token; never use Supabase service-role keys here.",
            },
            "n8n": {
                "target": "n8n-vault-remote-client.workflow.json",
                "mode": "http_request_workflow",
                "warning": "Store token in n8n credentials or environment variables, not inside workflow JSON.",
            },
        },
        "safety": {
            "candidate_first_writes": True,
            "search_returns_raw_content": False,
            "bounded_read_before_citation": True,
            "active_multi_master_sync": False,
        },
    }
    client_config_path = out / "vault-remote-client-config.json"
    client_config_path.write_text(
        json.dumps(client_config, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    n8n_path = out / "n8n-vault-remote-client.workflow.json"
    n8n_path.write_text(
        json.dumps(_remote_n8n_workflow(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    validation_path = out / "validate-vault-remote-client.py"
    validation_path.write_text(_render_remote_client_validation_script(), encoding="utf-8")
    validation_path.chmod(0o755)

    snippets_path = out / "AGENT_REMOTE_GATEWAY_SNIPPETS.md"
    snippets_path.write_text(_render_remote_gateway_snippets(gateway_url), encoding="utf-8")

    readme_path = out / "README-remote-clients.md"
    readme_path.write_text(
        "\n".join(
            [
                "# Vault Remote Client Templates",
                "",
                "Use these templates when an Agent connects to a self-hosted Vault Remote Server.",
                "",
                "Set the same two variables in each client runtime:",
                "",
                "```bash",
                f"export VAULT_REMOTE_URL=\"{gateway_url}\"",
                "export VAULT_GATEWAY_TOKEN=\"replace-with-stable-secret\"",
                "```",
                "",
                "Client files:",
                "",
                f"- `{client_config_path.name}`: machine-readable Codex, Claude Code, Hermes, OpenClaw, Coze, and n8n hints",
                f"- `{snippets_path.name}`: short human/agent setup snippets",
                f"- `{coze_openapi_path.name}`: OpenAPI connector template for Coze or similar hosted tools",
                f"- `{n8n_path.name}`: n8n HTTP Request workflow template",
                f"- `{validation_path.name}`: smoke-test the remote endpoint from an Agent machine",
                "",
                "Validation:",
                "",
                "```bash",
                f"python {validation_path.name} --agent-id codex --query \"deployment SOP\"",
                f"python {validation_path.name} --agent-id codex --submit-candidate",
                "```",
                "",
                "Safety boundary:",
                "",
                "- every request must send `agent_id`;",
                "- remote search returns compact results, not raw full content;",
                "- remote reads should use `/read-range` after search;",
                "- remote writes go to `/submit-candidate`, not active knowledge;",
                "- this is not offline active multi-master sync.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "readme": str(readme_path),
        "client_config": str(client_config_path),
        "agent_snippets": str(snippets_path),
        "coze_openapi": str(coze_openapi_path),
        "n8n_workflow": str(n8n_path),
        "validation_script": str(validation_path),
    }


def _remote_n8n_workflow() -> dict[str, object]:
    return {
        "name": "Vault Remote Server Search",
        "nodes": [
            {
                "id": "vault-search",
                "name": "Vault Remote Search",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4,
                "position": [320, 240],
                "parameters": {
                    "method": "POST",
                    "url": "={{$env.VAULT_REMOTE_URL}}/search",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Authorization", "value": "=Bearer {{$env.VAULT_GATEWAY_TOKEN}}"},
                            {"name": "Content-Type", "value": "application/json"},
                        ]
                    },
                    "sendBody": True,
                    "jsonBody": {
                        "agent_id": "n8n",
                        "query": "={{$json.query || $json.text || ''}}",
                        "limit": 5,
                    },
                },
            }
        ],
        "connections": {},
        "settings": {"executionOrder": "v1"},
        "vault_notes": {
            "token_storage": "Store VAULT_GATEWAY_TOKEN in environment variables or n8n credentials.",
            "writes": "Use /submit-candidate for proposed memory; do not bypass candidate review.",
        },
    }


def _render_remote_gateway_snippets(gateway_url: str) -> str:
    return "\n".join(
        [
            "# Agent Remote Gateway Snippets",
            "",
            "Use these snippets when the local runtime should read shared memory from a self-hosted Vault Remote Server.",
            "",
            "## Shared Environment",
            "",
            "```bash",
            f"export VAULT_REMOTE_URL=\"{gateway_url}\"",
            "export VAULT_GATEWAY_TOKEN=\"replace-with-stable-secret\"",
            "```",
            "",
            "## Minimal Search",
            "",
            "```bash",
            "curl -s \"$VAULT_REMOTE_URL/search\" \\",
            "  -H \"Authorization: Bearer $VAULT_GATEWAY_TOKEN\" \\",
            "  -H \"Content-Type: application/json\" \\",
            "  -d '{\"agent_id\":\"codex\",\"query\":\"deployment SOP\",\"limit\":5}'",
            "```",
            "",
            "## Codex / Claude Code",
            "",
            "Add a short project instruction: use `VAULT_REMOTE_URL` only when local `vault-mcp` is unavailable; search first, then bounded read before citing.",
            "",
            "## Hermes / OpenClaw",
            "",
            "Keep identity/personality memory in the runtime profile. Use the remote Gateway for shared project knowledge and candidate-first lessons.",
            "",
            "## Coze / n8n",
            "",
            "Use the generated OpenAPI or workflow template. Store the token in platform credentials or environment variables, not in public prompts.",
            "",
        ]
    )


def _render_remote_client_validation_script() -> str:
    return r'''#!/usr/bin/env python3
"""Smoke-test a Vault Remote Server client connection.

Reads VAULT_REMOTE_URL and VAULT_GATEWAY_TOKEN from the environment. The default
check is read-only: /health, /openapi.json, and /search. Pass
--submit-candidate when you also want to verify candidate-first remote writes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def _request(base_url: str, token: str, method: str, path: str, body: dict | None = None) -> dict:
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Vault-Gateway-Token": token,
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read().decode("utf-8")
            return {"ok": True, "status_code": response.status, "payload": json.loads(payload or "{}")}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status_code": exc.code, "error": detail[:500]}
    except Exception as exc:
        return {"ok": False, "status_code": 0, "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Vault Remote Server client connection.")
    parser.add_argument("--agent-id", default=os.environ.get("VAULT_AGENT_ID", "remote-smoke"))
    parser.add_argument("--query", default="vault")
    parser.add_argument("--submit-candidate", action="store_true")
    args = parser.parse_args()

    base_url = os.environ.get("VAULT_REMOTE_URL", "").strip()
    token = os.environ.get("VAULT_GATEWAY_TOKEN", "").strip()
    if not base_url or not token:
        print(json.dumps({
            "ok": False,
            "error": "Set VAULT_REMOTE_URL and VAULT_GATEWAY_TOKEN before running validation.",
        }, ensure_ascii=False, indent=2))
        return 2

    checks: list[dict] = []
    checks.append({"name": "health", **_request(base_url, token, "GET", "/health")})
    checks.append({"name": "openapi", **_request(base_url, token, "GET", "/openapi.json")})
    checks.append({
        "name": "search",
        **_request(base_url, token, "POST", "/search", {
            "agent_id": args.agent_id,
            "query": args.query,
            "limit": 5,
        }),
    })
    if args.submit_candidate:
        checks.append({
            "name": "submit_candidate",
            **_request(base_url, token, "POST", "/submit-candidate", {
                "agent_id": args.agent_id,
                "title": f"Remote client smoke {int(time.time())}",
                "content": "Remote client validation candidate. Safe to reject after smoke testing.",
                "reason": "Validate candidate-first remote writes.",
                "scope": "project",
                "sensitivity": "low",
                "tags": "smoke,remote-client",
                "source_ref": f"remote-client-smoke:{args.agent_id}",
            }),
        })

    ok = all(item.get("ok") and int(item.get("status_code") or 0) < 400 for item in checks)
    print(json.dumps({
        "ok": ok,
        "agent_id": args.agent_id,
        "remote_url": base_url,
        "submitted_candidate": bool(args.submit_candidate),
        "checks": checks,
    }, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _render_remote_server_launchagent(command: list[str]) -> str:
    stdout_path = Path.home() / ".vault-for-llm" / "vault-remote-server.log"
    stderr_path = Path.home() / ".vault-for-llm" / "vault-remote-server.err.log"
    program = command[0]
    args = "\n".join(f"    <string>{_xml_escape(arg)}</string>" for arg in command[1:])
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.zycaskevin.vault-for-llm.remote-server</string>
  <key>ProgramArguments</key>
  <array>
    <string>{_xml_escape(program)}</string>
{args}
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>VAULT_GATEWAY_TOKEN</key>
    <string>replace-with-stable-secret</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{_xml_escape(str(stdout_path))}</string>
  <key>StandardErrorPath</key>
  <string>{_xml_escape(str(stderr_path))}</string>
</dict>
</plist>
"""


def _xml_escape(value: object) -> str:
    text = str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
