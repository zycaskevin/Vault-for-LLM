"""HTTP server wrapper for the local Vault GUI."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
import webbrowser

from .daily_report import normalize_report_language
from .gui_api import (
    gui_agent_dashboard,
    gui_candidate,
    gui_candidates,
    gui_claim_task_handoff,
    gui_daily_report,
    gui_documents,
    gui_entry,
    gui_memory_migration,
    gui_overview,
    gui_read_range,
    gui_review_candidate,
    gui_search,
    gui_resolve_sync_conflict,
    gui_sync_conflict,
    gui_sync_status,
    gui_task,
    gui_tasks,
)
from .gui_app import APP_HTML
from .gui_format import _int_arg, _path_int, _path_str, _str_arg
from .gui_obsidian import gui_obsidian_conflict, gui_resolve_obsidian_conflict

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

def run_gui(
    project_dir: str | Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    auth_token: str | None = None,
    no_auth: bool = False,
    language: str = "zh-Hant",
) -> None:
    """Start the local GUI server and block until interrupted."""
    project = Path(project_dir).expanduser().resolve()
    host_text = str(host or DEFAULT_HOST)
    if no_auth and host_text not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("--no-auth is only allowed for localhost binds")
    token = "" if no_auth else (auth_token or os.environ.get("VAULT_GUI_TOKEN", "").strip() or secrets.token_urlsafe(24))
    handler = make_gui_handler(project, auth_token=token, language=language)
    server = ThreadingHTTPServer((host, int(port)), handler)
    url = f"http://{host}:{int(port)}/"
    browser_url = f"{url}?token={token}" if token else url
    print(f"Vault GUI: {url}")
    print(f"Auth: {'enabled' if token else 'disabled'}")
    print(f"Project: {project}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(browser_url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Vault GUI.")
    finally:
        server.server_close()


def make_gui_handler(project_dir: Path, *, auth_token: str = "", language: str = "zh-Hant"):
    project = Path(project_dir)
    token = str(auth_token or "")
    default_language = normalize_report_language(language)
    app_html = APP_HTML.replace("__VAULT_DEFAULT_LANGUAGE__", default_language)

    class VaultGuiHandler(BaseHTTPRequestHandler):
        server_version = "VaultGui/0.1"

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            if not self._is_authorized(query):
                self._send_unauthorized()
                return
            if path == "/":
                self._send_html(app_html, set_cookie=bool(token and _query_token(query) == token))
                return
            if path == "/api/overview":
                self._send_json(
                    gui_overview(
                        project,
                        limit=_int_arg(query, "limit", 5),
                        language=_str_arg(query, "lang", "en"),
                    )
                )
                return
            if path == "/api/daily-report":
                self._send_json(
                    gui_daily_report(
                        project,
                        limit=_int_arg(query, "limit", 5),
                        language=_str_arg(query, "lang", "en"),
                    )
                )
                return
            if path == "/api/agent-dashboard":
                self._send_json(
                    gui_agent_dashboard(
                        project,
                        limit=_int_arg(query, "limit", 5),
                        language=_str_arg(query, "lang", "en"),
                    )
                )
                return
            if path == "/api/sync-status":
                self._send_json(
                    gui_sync_status(
                        project,
                        limit=_int_arg(query, "limit", 5),
                    )
                )
                return
            if path == "/api/candidates":
                self._send_json(
                    gui_candidates(
                        project,
                        status=_str_arg(query, "status", "candidate"),
                        limit=_int_arg(query, "limit", 20),
                    )
                )
                return
            if path == "/api/tasks":
                self._send_json(
                    gui_tasks(
                        project,
                        status=_str_arg(query, "status", "active"),
                        limit=_int_arg(query, "limit", 20),
                    )
                )
                return
            if path == "/api/documents":
                self._send_json(
                    gui_documents(
                        project,
                        query=_str_arg(query, "q", ""),
                        layer=_str_arg(query, "layer", ""),
                        category=_str_arg(query, "category", ""),
                        scope=_str_arg(query, "scope", ""),
                        sensitivity=_str_arg(query, "sensitivity", ""),
                        limit=_int_arg(query, "limit", 50),
                    )
                )
                return
            if path == "/api/search":
                self._send_json(
                    gui_search(
                        project,
                        _str_arg(query, "q", ""),
                        mode=_str_arg(query, "mode", "keyword"),
                        limit=_int_arg(query, "limit", 10),
                    )
                )
                return
            if path == "/api/migration":
                self._send_json(
                    gui_memory_migration(
                        project,
                        source=_str_arg(query, "source", ""),
                        source_format=_str_arg(query, "format", "auto"),
                        write_candidates=False,
                        scope=_str_arg(query, "scope", "project"),
                        sensitivity=_str_arg(query, "sensitivity", "low"),
                        owner_agent=_str_arg(query, "owner_agent", ""),
                        only=_str_arg(query, "only", ""),
                        limit=_int_arg(query, "limit", 20),
                    )
                )
                return
            if path.startswith("/api/entry/"):
                self._send_json(gui_entry(project, _path_int(path, "/api/entry/")))
                return
            if path.startswith("/api/candidate/"):
                self._send_json(gui_candidate(project, _path_str(path, "/api/candidate/")))
                return
            if path.startswith("/api/sync-conflict/"):
                self._send_json(gui_sync_conflict(project, _path_str(path, "/api/sync-conflict/")))
                return
            if path.startswith("/api/obsidian-conflict/"):
                source_path = unquote(_path_str(path, "/api/obsidian-conflict/"))
                self._send_json(gui_obsidian_conflict(project, source_path))
                return
            if path.startswith("/api/task/"):
                self._send_json(gui_task(project, _path_str(path, "/api/task/")))
                return
            if path == "/api/read":
                self._send_json(
                    gui_read_range(
                        project,
                        _int_arg(query, "knowledge_id", 0),
                        line_start=_int_arg(query, "line_start", 1),
                        line_end=_int_arg(query, "line_end", 40),
                    )
                )
                return
            self._send_json({"status": "error", "error": "not_found"}, status=HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if not self._is_authorized(query):
                self._send_unauthorized()
                return
            if path.startswith("/api/candidate/") and path.endswith("/review"):
                candidate_id = path[len("/api/candidate/") : -len("/review")].strip("/")
                body = self._read_json_body()
                self._send_json(
                    gui_review_candidate(
                        project,
                        candidate_id,
                        action=str(body.get("action", "")),
                        reason=str(body.get("reason", "")),
                        confirm=str(body.get("confirm", "")),
                    )
                )
                return
            if path.startswith("/api/sync-conflict/") and path.endswith("/resolve"):
                conflict_id = path[len("/api/sync-conflict/") : -len("/resolve")].strip("/")
                body = self._read_json_body()
                self._send_json(
                    gui_resolve_sync_conflict(
                        project,
                        conflict_id,
                        resolution=str(body.get("resolution", "")),
                        reason=str(body.get("reason", "")),
                        agent_id=str(body.get("agent_id", "gui-reviewer")),
                        confirm=str(body.get("confirm", "")),
                    )
                )
                return
            if path.startswith("/api/obsidian-conflict/") and path.endswith("/resolve"):
                source_path = unquote(path[len("/api/obsidian-conflict/") : -len("/resolve")].strip("/"))
                body = self._read_json_body()
                self._send_json(
                    gui_resolve_obsidian_conflict(
                        project,
                        source_path,
                        resolution=str(body.get("resolution", "")),
                        confirm=str(body.get("confirm", "")),
                    )
                )
                return
            if path.startswith("/api/task-handoff/") and path.endswith("/claim"):
                handoff_id = path[len("/api/task-handoff/") : -len("/claim")].strip("/")
                body = self._read_json_body()
                self._send_json(gui_claim_task_handoff(
                    project,
                    handoff_id,
                    agent_id=str(body.get("agent_id", "gui-reviewer")),
                    note=str(body.get("note", "")),
                    confirm=str(body.get("confirm", "")),
                ))
                return
            if path == "/api/migration/import":
                body = self._read_json_body()
                self._send_json(
                    gui_memory_migration(
                        project,
                        source=str(body.get("source", "")),
                        source_format=str(body.get("format", "auto")),
                        write_candidates=bool(body.get("write_candidates", True)),
                        scope=str(body.get("scope", "project")),
                        sensitivity=str(body.get("sensitivity", "low")),
                        owner_agent=str(body.get("owner_agent", "")),
                        only=str(body.get("only", "")),
                        limit=int(body.get("limit", 20) or 20),
                    )
                )
                return
            self._send_json({"status": "error", "error": "not_found"}, status=HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_html(self, html: str, *, set_cookie: bool = False) -> None:
            data = html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            if set_cookie and token:
                self.send_header("Set-Cookie", f"vault_gui_token={token}; Path=/; SameSite=Strict; HttpOnly")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_unauthorized(self) -> None:
            if self.path.startswith("/api/"):
                self._send_json({"status": "error", "error": "unauthorized"}, status=HTTPStatus.UNAUTHORIZED)
                return
            data = b"Vault GUI requires a valid token."
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _is_authorized(self, query: dict[str, list[str]]) -> bool:
            if not token:
                return True
            if _query_token(query) == token:
                return True
            if str(self.headers.get("X-Vault-Gui-Token", "")) == token:
                return True
            cookie = str(self.headers.get("Cookie", ""))
            return any(part.strip() == f"vault_gui_token={token}" for part in cookie.split(";"))

        def _read_json_body(self) -> dict[str, Any]:
            try:
                length = max(0, min(int(self.headers.get("Content-Length", "0")), 16_384))
            except (TypeError, ValueError):
                length = 0
            if length <= 0:
                return {}
            try:
                return json.loads(self.rfile.read(length).decode("utf-8")) or {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                return {}

    return VaultGuiHandler


def cmd_gui(args: Any) -> None:
    from .cli_context import find_project_dir

    run_gui(
        find_project_dir(),
        host=str(getattr(args, "host", DEFAULT_HOST) or DEFAULT_HOST),
        port=int(getattr(args, "port", DEFAULT_PORT) or DEFAULT_PORT),
        open_browser=not bool(getattr(args, "no_open", False)),
        auth_token=getattr(args, "auth_token", None),
        no_auth=bool(getattr(args, "no_auth", False)),
        language=getattr(args, "language", "zh-Hant"),
    )


def _query_token(query: dict[str, list[str]]) -> str:
    values = query.get("token") or []
    return str(values[0]) if values else ""
