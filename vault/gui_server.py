"""HTTP server wrapper for the local Vault GUI."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
import webbrowser

from .gui_api import (
    gui_candidate,
    gui_candidates,
    gui_entry,
    gui_overview,
    gui_read_range,
    gui_review_candidate,
    gui_search,
)
from .gui_app import APP_HTML
from .gui_format import _int_arg, _path_int, _path_str, _str_arg

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

def run_gui(
    project_dir: str | Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
) -> None:
    """Start the local GUI server and block until interrupted."""
    project = Path(project_dir).expanduser().resolve()
    handler = make_gui_handler(project)
    server = ThreadingHTTPServer((host, int(port)), handler)
    url = f"http://{host}:{int(port)}/"
    print(f"Vault GUI: {url}")
    print(f"Project: {project}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Vault GUI.")
    finally:
        server.server_close()


def make_gui_handler(project_dir: Path):
    project = Path(project_dir)

    class VaultGuiHandler(BaseHTTPRequestHandler):
        server_version = "VaultGui/0.1"

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            if path == "/":
                self._send_html(APP_HTML)
                return
            if path == "/api/overview":
                self._send_json(gui_overview(project, limit=_int_arg(query, "limit", 5)))
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
            if path.startswith("/api/entry/"):
                self._send_json(gui_entry(project, _path_int(path, "/api/entry/")))
                return
            if path.startswith("/api/candidate/"):
                self._send_json(gui_candidate(project, _path_str(path, "/api/candidate/")))
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

        def _send_html(self, html: str) -> None:
            data = html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

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
    )

