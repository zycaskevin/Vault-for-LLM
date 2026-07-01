"""CLI parser helpers for Gateway and self-hosted Remote Server commands."""

from __future__ import annotations

from typing import Any

from .gateway import DEFAULT_GATEWAY_HOST, DEFAULT_GATEWAY_PORT


REMOTE_SERVER_HOST = "0.0.0.0"


def add_gateway_parsers(sub: Any) -> None:
    """Register HTTP adapter commands without growing the main CLI module."""
    _add_gateway_parser(sub)
    _add_remote_server_parser(sub)


def _add_gateway_parser(sub: Any) -> None:
    parser = sub.add_parser("gateway", help="啟動 Agent 統一記憶入口（HTTP Gateway）")
    gateway_sub = parser.add_subparsers(dest="gateway_action")
    serve = gateway_sub.add_parser("serve", help="啟動薄 Gateway：search/read-range/submit-candidate/health")
    _add_serve_args(serve, host_default=DEFAULT_GATEWAY_HOST)
    health = gateway_sub.add_parser("health", help="輸出 Gateway readiness JSON，不啟動 server")
    _add_json_args(health)
    openapi = gateway_sub.add_parser("openapi", help="輸出 Gateway HTTP contract JSON，不啟動 server")
    _add_json_args(openapi)
    parser.set_defaults(gateway_profile="gateway")
    serve.set_defaults(gateway_profile="gateway")
    health.set_defaults(gateway_profile="gateway")
    openapi.set_defaults(gateway_profile="gateway")


def _add_remote_server_parser(sub: Any) -> None:
    parser = sub.add_parser("remote-server", help="啟動自架 Vault Remote Server（重用 Gateway contract）")
    remote_sub = parser.add_subparsers(dest="gateway_action")
    serve = remote_sub.add_parser("serve", help="啟動自架遠端入口：需穩定 token，寫入仍是候選優先")
    _add_serve_args(serve, host_default=REMOTE_SERVER_HOST)
    health = remote_sub.add_parser("health", help="輸出 self-host readiness JSON，不啟動 server")
    _add_json_args(health)
    openapi = remote_sub.add_parser("openapi", help="輸出 self-host Remote Server HTTP contract JSON")
    _add_json_args(openapi)
    parser.set_defaults(gateway_profile="remote_server")
    serve.set_defaults(gateway_profile="remote_server")
    health.set_defaults(gateway_profile="remote_server")
    openapi.set_defaults(gateway_profile="remote_server")


def _add_serve_args(parser: Any, *, host_default: str) -> None:
    parser.add_argument("--host", default=host_default, help=f"綁定 host；預設 {host_default}")
    parser.add_argument("--port", type=int, default=DEFAULT_GATEWAY_PORT, help=f"綁定 port；預設 {DEFAULT_GATEWAY_PORT}")
    parser.add_argument("--auth-token", default=None, help="Gateway token；也可用 VAULT_GATEWAY_TOKEN")
    parser.add_argument("--no-auth", action="store_true", help="只允許 localhost 綁定時關閉 token")
    parser.add_argument("--allow-shared-candidates", action="store_true", help="允許 submit-candidate 寫入 shared/public 候選")
    parser.add_argument("--allow-private-candidates", action="store_true", help="允許 submit-candidate 寫入 private 候選")
    parser.add_argument("--allow-high-sensitivity-candidates", action="store_true", help="允許 submit-candidate 寫入 high 候選")
    parser.add_argument("--allow-restricted-candidates", action="store_true", help="允許 submit-candidate 寫入 restricted 候選")


def _add_json_args(parser: Any) -> None:
    parser.add_argument("--json", action="store_true", help="輸出 JSON")
    parser.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")
