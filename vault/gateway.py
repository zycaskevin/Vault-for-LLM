"""Thin local/remote HTTP gateway for agent memory access."""

from __future__ import annotations

from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
from typing import Any
from urllib.parse import parse_qs, urlparse

from .access_policy import can_write_memory, normalize_write_policy
from .db import VaultDB
from .gui_format import compact_knowledge
from .mcp_read import _vault_read_range_payload
from .memory import create_candidate
from .search import VaultSearch
from .search_utils import normalize_search_limit


DEFAULT_GATEWAY_HOST = "127.0.0.1"
DEFAULT_GATEWAY_PORT = 8789
LOCALHOSTS = {"127.0.0.1", "localhost", "::1"}


def gateway_health(project_dir: str | Path) -> dict[str, Any]:
    """Return a compact readiness payload for agents."""
    project = Path(project_dir).expanduser().resolve()
    db_path = project / "vault.db"
    stats: dict[str, Any] = {}
    if db_path.exists():
        try:
            with VaultDB(db_path) as db:
                stats = db.stats()
        except Exception:
            stats = {}
    return {
        "status": "ok" if db_path.exists() else "blocked",
        "project_dir": str(project),
        "db_exists": db_path.exists(),
        "stats": stats,
        "gateway": {
            "role": "unified_agent_memory_entrypoint",
            "writes_active_knowledge": False,
            "candidate_first_writes": True,
            "default_read_max_sensitivity": "low",
            "default_include_private": False,
            "endpoints": ["/health", "/search", "/read-range", "/submit-candidate"],
        },
    }


def gateway_search(
    project_dir: str | Path,
    *,
    query: str,
    agent_id: str,
    mode: str = "keyword",
    limit: int = 10,
    include_private: bool = False,
    max_sensitivity: str = "low",
) -> dict[str, Any]:
    """Search active memory through an explicit agent read policy."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    agent = _agent_id(agent_id)
    limit_i = normalize_search_limit(limit, default=10, maximum=50)
    if not db_path.exists():
        return _error("db_not_found", "vault.db missing", status="blocked")
    if not agent:
        return _error("agent_id_required", "Gateway search requires agent_id")
    if not str(query or "").strip() or limit_i <= 0:
        return {"status": "ok", "query": query, "mode": mode, "results": []}
    if mode not in {"auto", "keyword", "semantic", "hybrid", "vector"}:
        mode = "keyword"
    with VaultDB(db_path) as db:
        search = VaultSearch(db, embed_provider=None, embed_provider_name="none")
        rows = search.search(
            query,
            mode=mode,
            limit=limit_i,
            use_rerank=False,
            compact=False,
            include_snippet=True,
            fields=[
                "id",
                "title",
                "category",
                "layer",
                "trust",
                "summary",
                "tags",
                "source",
                "scope",
                "sensitivity",
                "owner_agent",
                "memory_type",
                "valid_from",
                "valid_until",
                "expires_at",
                "line_start",
                "line_end",
                "best_span",
                "_score",
                "_snippet",
            ],
            agent_id=agent,
            include_private=include_private,
            max_sensitivity=max_sensitivity or "low",
        )
    return {
        "status": "ok",
        "query": query,
        "mode": mode,
        "agent_id": agent,
        "results": [compact_knowledge(row) for row in rows],
        "safety": {
            "read_policy_active": True,
            "include_private": bool(include_private),
            "max_sensitivity": max_sensitivity or "low",
            "content_hidden_by_default": True,
        },
    }


def gateway_read_range(
    project_dir: str | Path,
    *,
    knowledge_id: int,
    agent_id: str,
    line_start: int = 1,
    line_end: int = 40,
    node_uid: str = "",
    max_lines: int = 80,
    include_private: bool = False,
    max_sensitivity: str = "low",
) -> dict[str, Any]:
    """Read bounded evidence through the same policy as MCP read_range."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    agent = _agent_id(agent_id)
    if not db_path.exists():
        return _error("db_not_found", "vault.db missing", status="blocked")
    if not agent:
        return _error("agent_id_required", "Gateway read-range requires agent_id")
    payload = _vault_read_range_payload(
        knowledge_id,
        node_uid=node_uid,
        line_start=line_start,
        line_end=line_end,
        max_lines=max_lines,
        agent_id=agent,
        include_private=include_private,
        max_sensitivity=max_sensitivity or "low",
        db_path=str(db_path),
    )
    if "error" in payload and "status" not in payload:
        payload["status"] = "error"
    else:
        payload["status"] = "ok"
    payload["agent_id"] = agent
    payload["safety"] = {
        "bounded_read": True,
        "include_private": bool(include_private),
        "max_sensitivity": max_sensitivity or "low",
    }
    return payload


def gateway_submit_candidate(
    project_dir: str | Path,
    *,
    title: str,
    content: str,
    agent_id: str,
    reason: str = "",
    layer: str = "L3",
    category: str = "general",
    tags: str = "",
    trust: float = 0.5,
    scope: str = "project",
    sensitivity: str = "low",
    owner_agent: str = "",
    allowed_agents: str = "",
    memory_type: str = "knowledge",
    source_ref: str = "",
    allow_shared_candidates: bool = False,
    allow_private_candidates: bool = False,
    allow_high_sensitivity_candidates: bool = False,
    allow_restricted_candidates: bool = False,
) -> dict[str, Any]:
    """Write an agent proposal into memory_candidates, never active knowledge."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    agent = _agent_id(agent_id)
    if not db_path.exists():
        return _error("db_not_found", "vault.db missing", status="blocked")
    if not agent:
        return _error("agent_id_required", "Gateway candidate submit requires agent_id")
    meta = {
        "title": str(title or "").strip(),
        "content": str(content or "").strip(),
        "layer": layer or "L3",
        "category": category or "general",
        "tags": tags or "",
        "trust": trust,
        "source": f"gateway:{agent}",
        "source_ref": source_ref or f"gateway:{agent}",
        "reason": reason or "Submitted through Vault Gateway; review before promotion.",
        "scope": scope or "project",
        "sensitivity": sensitivity or "low",
        "owner_agent": owner_agent or agent,
        "allowed_agents": allowed_agents or "",
        "memory_type": memory_type or "knowledge",
    }
    allowed, why = can_write_memory(
        meta,
        normalize_write_policy(
            agent_id=agent,
            allow_shared=allow_shared_candidates,
            allow_private=allow_private_candidates,
            allow_high_sensitivity=allow_high_sensitivity_candidates,
            allow_restricted=allow_restricted_candidates,
        ),
    )
    if not allowed:
        return _error("access_denied", why)
    with VaultDB(db_path) as db:
        result = create_candidate(db, **meta)
    return {
        "status": "ok" if result.get("status") != "rejected" else "rejected",
        "candidate": result,
        "safety": {
            "candidate_first": True,
            "writes_active_knowledge": False,
            "requires_review_before_promotion": True,
        },
    }


def make_gateway_handler(
    project_dir: str | Path,
    *,
    auth_token: str = "",
    allow_shared_candidates: bool = False,
    allow_private_candidates: bool = False,
    allow_high_sensitivity_candidates: bool = False,
    allow_restricted_candidates: bool = False,
):
    """Create a small JSON HTTP handler for the Gateway."""
    project = Path(project_dir).expanduser().resolve()
    token = str(auth_token or "")

    class VaultGatewayHandler(BaseHTTPRequestHandler):
        server_version = "VaultGateway/0.1"

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            if not self._is_authorized(parsed):
                self._send_unauthorized()
                return
            if parsed.path == "/health":
                payload = gateway_health(project)
                _append_audit(project, "health", _request_agent({}, parsed), payload.get("status", "ok"))
                self._send_json(payload)
                return
            self._send_json(_error("not_found", "unknown endpoint"), status=HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            if not self._is_authorized(parsed):
                self._send_unauthorized()
                return
            body = self._read_json_body()
            agent = _request_agent(body, parsed)
            if parsed.path == "/search":
                payload = gateway_search(
                    project,
                    query=str(body.get("query", "")),
                    agent_id=agent,
                    mode=str(body.get("mode", "keyword")),
                    limit=_int_value(body.get("limit"), 10),
                    include_private=_bool_value(body.get("include_private"), False),
                    max_sensitivity=str(body.get("max_sensitivity", "low") or "low"),
                )
                _append_audit(project, "search", agent, payload.get("status", "ok"), query=str(body.get("query", "")))
                self._send_json(payload)
                return
            if parsed.path == "/read-range":
                payload = gateway_read_range(
                    project,
                    knowledge_id=_int_value(body.get("knowledge_id"), 0),
                    node_uid=str(body.get("node_uid", "")),
                    line_start=_int_value(body.get("line_start"), 1),
                    line_end=_int_value(body.get("line_end"), 40),
                    max_lines=_int_value(body.get("max_lines"), 80),
                    agent_id=agent,
                    include_private=_bool_value(body.get("include_private"), False),
                    max_sensitivity=str(body.get("max_sensitivity", "low") or "low"),
                )
                _append_audit(project, "read_range", agent, payload.get("status", "ok"), knowledge_id=body.get("knowledge_id", 0))
                self._send_json(payload)
                return
            if parsed.path == "/submit-candidate":
                payload = gateway_submit_candidate(
                    project,
                    title=str(body.get("title", "")),
                    content=str(body.get("content", "")),
                    agent_id=agent,
                    reason=str(body.get("reason", "")),
                    layer=str(body.get("layer", "L3") or "L3"),
                    category=str(body.get("category", "general") or "general"),
                    tags=str(body.get("tags", "") or ""),
                    trust=_float_value(body.get("trust"), 0.5),
                    scope=str(body.get("scope", "project") or "project"),
                    sensitivity=str(body.get("sensitivity", "low") or "low"),
                    owner_agent=str(body.get("owner_agent", "") or ""),
                    allowed_agents=str(body.get("allowed_agents", "") or ""),
                    memory_type=str(body.get("memory_type", "knowledge") or "knowledge"),
                    source_ref=str(body.get("source_ref", "") or ""),
                    allow_shared_candidates=allow_shared_candidates,
                    allow_private_candidates=allow_private_candidates,
                    allow_high_sensitivity_candidates=allow_high_sensitivity_candidates,
                    allow_restricted_candidates=allow_restricted_candidates,
                )
                candidate = payload.get("candidate") if isinstance(payload.get("candidate"), dict) else {}
                _append_audit(
                    project,
                    "submit_candidate",
                    agent,
                    payload.get("status", "ok"),
                    candidate_id=candidate.get("candidate_id", ""),
                    title=str(body.get("title", "")),
                )
                self._send_json(payload)
                return
            self._send_json(_error("not_found", "unknown endpoint"), status=HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _is_authorized(self, parsed) -> bool:
            if not token:
                return True
            if str(self.headers.get("X-Vault-Gateway-Token", "")) == token:
                return True
            auth = str(self.headers.get("Authorization", ""))
            if auth == f"Bearer {token}":
                return True
            query = parse_qs(parsed.query)
            return bool(query.get("token") and str(query["token"][0]) == token)

        def _send_unauthorized(self) -> None:
            self._send_json(_error("unauthorized", "valid gateway token required"), status=HTTPStatus.UNAUTHORIZED)

        def _send_json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json_body(self) -> dict[str, Any]:
            try:
                length = max(0, min(int(self.headers.get("Content-Length", "0")), 65_536))
            except (TypeError, ValueError):
                length = 0
            if length <= 0:
                return {}
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8")) or {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                return {}
            return payload if isinstance(payload, dict) else {}

    return VaultGatewayHandler


def run_gateway(
    project_dir: str | Path,
    *,
    host: str = DEFAULT_GATEWAY_HOST,
    port: int = DEFAULT_GATEWAY_PORT,
    auth_token: str | None = None,
    no_auth: bool = False,
    allow_shared_candidates: bool = False,
    allow_private_candidates: bool = False,
    allow_high_sensitivity_candidates: bool = False,
    allow_restricted_candidates: bool = False,
) -> None:
    """Start the thin Gateway server and block."""
    host_text = str(host or DEFAULT_GATEWAY_HOST)
    if no_auth and host_text not in LOCALHOSTS:
        raise ValueError("--no-auth is only allowed for localhost binds")
    token = "" if no_auth else (auth_token or os.environ.get("VAULT_GATEWAY_TOKEN", "").strip() or secrets.token_urlsafe(24))
    handler = make_gateway_handler(
        project_dir,
        auth_token=token,
        allow_shared_candidates=allow_shared_candidates,
        allow_private_candidates=allow_private_candidates,
        allow_high_sensitivity_candidates=allow_high_sensitivity_candidates,
        allow_restricted_candidates=allow_restricted_candidates,
    )
    server = ThreadingHTTPServer((host_text, int(port)), handler)
    print(f"Vault Gateway: http://{host_text}:{int(port)}")
    print(f"Auth: {'enabled' if token else 'disabled'}")
    if token:
        print(f"Token: {token}")
    print(f"Project: {Path(project_dir).expanduser().resolve()}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Vault Gateway.")
    finally:
        server.server_close()


def cmd_gateway(args: Any) -> None:
    from .cli_context import _arg_value, _json_print, find_project_dir

    action = str(getattr(args, "gateway_action", "") or "")
    if action == "health":
        payload = gateway_health(find_project_dir())
        payload.setdefault("ok", payload.get("status") == "ok")
        _json_print(payload, pretty=_arg_value(args, "pretty", False) is True)
        return
    if action != "serve":
        print("用法: vault gateway {serve|health}")
        raise SystemExit(2)
    run_gateway(
        find_project_dir(),
        host=str(getattr(args, "host", DEFAULT_GATEWAY_HOST) or DEFAULT_GATEWAY_HOST),
        port=int(getattr(args, "port", DEFAULT_GATEWAY_PORT) or DEFAULT_GATEWAY_PORT),
        auth_token=getattr(args, "auth_token", None),
        no_auth=bool(getattr(args, "no_auth", False)),
        allow_shared_candidates=bool(getattr(args, "allow_shared_candidates", False)),
        allow_private_candidates=bool(getattr(args, "allow_private_candidates", False)),
        allow_high_sensitivity_candidates=bool(getattr(args, "allow_high_sensitivity_candidates", False)),
        allow_restricted_candidates=bool(getattr(args, "allow_restricted_candidates", False)),
    )


def _agent_id(value: Any) -> str:
    return str(value or "").strip().lower()


def _request_agent(body: dict[str, Any], parsed) -> str:
    query = parse_qs(parsed.query)
    return _agent_id(body.get("agent_id") or (query.get("agent_id") or [""])[0])


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _bool_value(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _error(code: str, message: str, *, status: str = "error") -> dict[str, Any]:
    return {"status": status, "error": code, "message": message}


def _append_audit(project_dir: Path, event: str, agent_id: str, status: str, **extra: Any) -> None:
    path = project_dir / "reports" / "gateway" / "audit.jsonl"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "agent_id": agent_id,
            "status": status,
            **extra,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        return
