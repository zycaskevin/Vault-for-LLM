"""Self-hosted Vault Remote Server deployment template helpers."""

from __future__ import annotations

from pathlib import Path

from vault.agent_setup_templates import shell_join


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
    return {
        "readme": str(readme_path),
        "health_command": shell_join(health_command),
        "openapi_command": shell_join(openapi_command),
        "serve_command": shell_join(command),
        "launchagent": str(launchagent_path),
        "systemd": str(systemd_path),
        "docker_compose": str(compose_path),
    }


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
