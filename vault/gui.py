"""Local read-only GUI console for Vault-for-LLM."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
import webbrowser

from .automation import automation_brief
from .automation_inbox import automation_inbox
from .db import VaultDB
from .search import VaultSearch
from .search_utils import normalize_search_limit


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def gui_overview(project_dir: str | Path, *, limit: int = 5) -> dict[str, Any]:
    """Return the startup payload shown by the local GUI."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    if not db_path.exists():
        return {
            "status": "blocked",
            "project_dir": str(project),
            "reason": "vault.db missing",
            "stats": {},
            "brief": {},
            "inbox": {},
            "recent": [],
        }

    with VaultDB(db_path) as db:
        stats = db.stats()
        recent = [
            _compact_knowledge(row)
            for row in db.list_knowledge(limit=max(1, min(int(limit or 5), 20)))
        ]
    brief = automation_brief(project, limit=limit, review_limit=limit)
    inbox = automation_inbox(project, limit=limit, include_content=False)
    return {
        "status": "ok",
        "project_dir": str(project),
        "stats": stats,
        "brief": _compact_brief(brief),
        "inbox": _compact_inbox(inbox),
        "recent": recent,
    }


def gui_search(
    project_dir: str | Path,
    query: str,
    *,
    mode: str = "keyword",
    limit: int = 10,
) -> dict[str, Any]:
    """Run a local read-only search for the GUI."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    limit_i = normalize_search_limit(limit, default=10, maximum=50)
    if not query.strip() or limit_i <= 0:
        return {"status": "ok", "query": query, "results": []}
    if mode not in {"auto", "keyword", "semantic", "hybrid", "vector"}:
        mode = "keyword"
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing", "query": query, "results": []}

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
                "recommended_next_tool",
                "_score",
                "_snippet",
            ],
        )
    return {"status": "ok", "query": query, "mode": mode, "results": [_compact_knowledge(r) for r in rows]}


def gui_entry(project_dir: str | Path, knowledge_id: int) -> dict[str, Any]:
    """Return metadata, map nodes, claims, and graph summary for one entry."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing"}
    try:
        kid = int(knowledge_id)
    except (TypeError, ValueError):
        return {"status": "error", "error": "invalid_knowledge_id"}
    if kid <= 0:
        return {"status": "error", "error": "invalid_knowledge_id"}

    with VaultDB(db_path) as db:
        row = db.get_knowledge(kid)
        if not row:
            return {"status": "error", "error": "not_found", "knowledge_id": kid}
        nodes = [
            dict(r)
            for r in db.conn.execute(
                """SELECT node_uid, heading, level, path, summary, line_start, line_end
                   FROM knowledge_nodes
                   WHERE knowledge_id=?
                   ORDER BY line_start, level, id""",
                (kid,),
            ).fetchall()
        ]
        claims = [
            dict(r)
            for r in db.conn.execute(
                """SELECT claim, node_uid, line_start, line_end, confidence, source
                   FROM knowledge_claims
                   WHERE knowledge_id=?
                   ORDER BY line_start, id
                   LIMIT 20""",
                (kid,),
            ).fetchall()
        ]
        edges = _graph_edges_for_entry(db, kid)
    return {
        "status": "ok",
        "entry": _compact_knowledge(row),
        "nodes": nodes,
        "claims": claims,
        "graph": edges,
        "timeline": _timeline_for(row),
        "governance": _governance_for(row),
        "usage": _usage_for(row),
    }


def gui_read_range(
    project_dir: str | Path,
    knowledge_id: int,
    *,
    line_start: int = 1,
    line_end: int = 40,
    max_lines: int = 80,
) -> dict[str, Any]:
    """Return a bounded source range for the GUI evidence reader."""
    project = Path(project_dir)
    db_path = project / "vault.db"
    if not db_path.exists():
        return {"status": "blocked", "reason": "vault.db missing"}
    try:
        kid = int(knowledge_id)
        start = int(line_start)
        end = int(line_end)
        max_lines_i = max(1, min(int(max_lines), 200))
    except (TypeError, ValueError):
        return {"status": "error", "error": "invalid_range"}
    if kid <= 0:
        return {"status": "error", "error": "invalid_knowledge_id"}

    with VaultDB(db_path) as db:
        row = db.get_knowledge(kid)
        if not row:
            return {"status": "error", "error": "not_found", "knowledge_id": kid}
        lines = (row.get("content_raw") or "").splitlines()
    if not lines:
        return {"status": "ok", "knowledge_id": kid, "title": row.get("title", ""), "lines": []}

    total = len(lines)
    start = min(max(1, start), total)
    end = min(max(start, end), total)
    if end - start + 1 > max_lines_i:
        end = start + max_lines_i - 1
    payload_lines = [
        {"line": number, "text": lines[number - 1]}
        for number in range(start, end + 1)
    ]
    return {
        "status": "ok",
        "knowledge_id": kid,
        "title": row.get("title", ""),
        "line_start": start,
        "line_end": end,
        "citation": f"#{kid} {row.get('title', '')} L{start}-L{end}",
        "lines": payload_lines,
    }


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

    return VaultGuiHandler


def cmd_gui(args: Any) -> None:
    from .cli_context import find_project_dir

    run_gui(
        find_project_dir(),
        host=str(getattr(args, "host", DEFAULT_HOST) or DEFAULT_HOST),
        port=int(getattr(args, "port", DEFAULT_PORT) or DEFAULT_PORT),
        open_browser=not bool(getattr(args, "no_open", False)),
    )


def _compact_knowledge(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "title": row.get("title", ""),
        "category": row.get("category", ""),
        "layer": row.get("layer", ""),
        "trust": row.get("trust", 0),
        "summary": row.get("summary", ""),
        "tags": row.get("tags", ""),
        "source": row.get("source", ""),
        "scope": row.get("scope", "project"),
        "sensitivity": row.get("sensitivity", "low"),
        "owner_agent": row.get("owner_agent", ""),
        "memory_type": row.get("memory_type", ""),
        "valid_from": row.get("valid_from", ""),
        "valid_until": row.get("valid_until", ""),
        "expires_at": row.get("expires_at", ""),
        "best_span": row.get("best_span", ""),
        "line_start": row.get("line_start"),
        "line_end": row.get("line_end"),
        "_score": row.get("_score"),
        "_snippet": row.get("_snippet", ""),
        "usage_count": row.get("usage_count", 0),
        "last_accessed_at": row.get("last_accessed_at", ""),
    }


def _compact_brief(brief: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": brief.get("status", ""),
        "summary": brief.get("summary", {}),
        "human_review": brief.get("human_review_5_percent", {}),
        "learning": brief.get("learning", {}),
        "forgetting_strategy": brief.get("forgetting_strategy", {}),
        "agent_health": brief.get("agent_health", {}),
        "next_action": brief.get("next_action", ""),
    }


def _compact_inbox(inbox: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": inbox.get("status", ""),
        "summary": inbox.get("summary", {}),
        "review_digest": inbox.get("review_digest", {}),
        "review_queue": inbox.get("review_queue", []),
        "next_action": inbox.get("next_action", ""),
    }


def _graph_edges_for_entry(db: VaultDB, knowledge_id: int) -> dict[str, Any]:
    edges = db.get_edges(node_id=knowledge_id)
    shaped = []
    for edge in edges[:20]:
        other_id = edge.get("target_id") if edge.get("source_id") == knowledge_id else edge.get("source_id")
        other = db.get_knowledge(int(other_id)) if other_id else None
        shaped.append(
            {
                "relation": edge.get("relation", ""),
                "weight": edge.get("weight", 0),
                "auto_inferred": bool(edge.get("auto_inferred")),
                "other_id": other_id,
                "other_title": (other or {}).get("title", ""),
            }
        )
    return {"edge_count": len(edges), "edges": shaped}


def _timeline_for(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "valid_from": row.get("valid_from", ""),
        "valid_until": row.get("valid_until", ""),
        "expires_at": row.get("expires_at", ""),
        "supersedes_id": row.get("supersedes_id"),
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
    }


def _governance_for(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": row.get("scope", "project"),
        "sensitivity": row.get("sensitivity", "low"),
        "owner_agent": row.get("owner_agent", ""),
        "allowed_agents": row.get("allowed_agents", ""),
        "memory_type": row.get("memory_type", ""),
        "trust": row.get("trust", 0),
    }


def _usage_for(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "usage_count": row.get("usage_count", 0),
        "last_accessed_at": row.get("last_accessed_at", ""),
        "source": row.get("source", ""),
        "status": row.get("status", "active"),
    }


def _str_arg(query: dict[str, list[str]], name: str, default: str) -> str:
    values = query.get(name)
    return values[0] if values else default


def _int_arg(query: dict[str, list[str]], name: str, default: int) -> int:
    try:
        return int(_str_arg(query, name, str(default)))
    except (TypeError, ValueError):
        return default


def _path_int(path: str, prefix: str) -> int:
    try:
        return int(path[len(prefix) :].strip("/"))
    except (TypeError, ValueError):
        return 0


APP_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Vault Console</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f7f4;
      --panel: #ffffff;
      --ink: #202124;
      --muted: #686f77;
      --line: #d8ddd5;
      --accent: #0f766e;
      --accent-2: #4f46e5;
      --warn: #b45309;
      --danger: #b91c1c;
      --good: #15803d;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--ink); }
    button, input, select { font: inherit; }
    .app {
      display: grid;
      grid-template-columns: minmax(260px, 320px) minmax(420px, 1fr) minmax(300px, 380px);
      min-height: 100vh;
    }
    aside, main { min-width: 0; }
    .left, .right { background: var(--panel); border-right: 1px solid var(--line); overflow: auto; }
    .right { border-right: 0; border-left: 1px solid var(--line); }
    .topbar { padding: 18px 18px 14px; border-bottom: 1px solid var(--line); }
    h1 { margin: 0; font-size: 22px; letter-spacing: 0; }
    h2 { margin: 18px 0 8px; font-size: 13px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
    h3 { margin: 0 0 4px; font-size: 15px; }
    .subtle { color: var(--muted); font-size: 13px; line-height: 1.45; }
    .section { padding: 0 18px 18px; }
    .metric-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .metric, .item, .result, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
    }
    .metric strong { display: block; font-size: 22px; }
    .metric span { color: var(--muted); font-size: 12px; }
    .searchbar { display: grid; grid-template-columns: 1fr auto; gap: 8px; padding: 16px 18px; border-bottom: 1px solid var(--line); background: #fbfbf8; }
    input, select {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 11px;
      background: #fff;
      color: var(--ink);
      min-width: 0;
    }
    button {
      border: 1px solid var(--accent);
      background: var(--accent);
      color: #fff;
      border-radius: 8px;
      padding: 10px 12px;
      cursor: pointer;
    }
    button.secondary { background: #fff; color: var(--accent); }
    .content { overflow: auto; }
    .results { display: grid; gap: 10px; padding: 16px 18px; }
    .result { cursor: pointer; }
    .result:hover, .item:hover { border-color: var(--accent); }
    .meta { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
    .pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 2px 7px;
      font-size: 12px;
      color: var(--muted);
      background: #fafafa;
    }
    .pill.good { color: var(--good); border-color: #bbf7d0; }
    .pill.warn { color: var(--warn); border-color: #fed7aa; }
    .evidence {
      margin: 0 18px 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #101418;
      color: #e7ecef;
      overflow: hidden;
    }
    .evidence-head { padding: 10px 12px; border-bottom: 1px solid #2b333b; color: #b9c2cc; font-size: 13px; }
    pre { margin: 0; padding: 12px; overflow: auto; line-height: 1.5; white-space: pre-wrap; }
    .tabs { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; padding: 12px 12px 0; }
    .tabs button { padding: 8px 6px; background: #fff; color: var(--muted); border-color: var(--line); }
    .tabs button.active { color: #fff; background: var(--accent-2); border-color: var(--accent-2); }
    .right-content { padding: 14px; }
    .kv { display: grid; grid-template-columns: 110px 1fr; gap: 8px; font-size: 13px; padding: 7px 0; border-bottom: 1px solid var(--line); }
    .kv span:first-child { color: var(--muted); }
    .empty { padding: 30px 18px; color: var(--muted); text-align: center; }
    @media (max-width: 1040px) {
      .app { grid-template-columns: 280px 1fr; }
      .right { grid-column: 1 / -1; border-left: 0; border-top: 1px solid var(--line); }
    }
    @media (max-width: 760px) {
      .app { display: block; }
      .left, .right { border: 0; border-bottom: 1px solid var(--line); }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="left">
      <div class="topbar">
        <h1>Vault Console</h1>
        <div class="subtle" id="projectPath"></div>
      </div>
      <div class="section">
        <h2>Status</h2>
        <div class="metric-grid" id="metrics"></div>
        <h2>Review Inbox</h2>
        <div id="reviewQueue"></div>
        <h2>Recent Memory</h2>
        <div id="recentList"></div>
      </div>
    </aside>
    <main class="content">
      <form class="searchbar" id="searchForm">
        <input id="query" name="query" placeholder="Search project memory" autocomplete="off">
        <button type="submit">Search</button>
      </form>
      <div class="results" id="results"></div>
      <div class="evidence" id="evidence" hidden>
        <div class="evidence-head" id="evidenceHead"></div>
        <pre id="evidenceBody"></pre>
      </div>
    </main>
    <aside class="right">
      <div class="tabs">
        <button data-tab="graph" class="active">Graph</button>
        <button data-tab="timeline">Timeline</button>
        <button data-tab="governance">Governance</button>
        <button data-tab="usage">Usage</button>
      </div>
      <div class="right-content" id="sidePanel"></div>
    </aside>
  </div>
  <script>
    let currentEntry = null;
    let activeTab = "graph";

    const $ = (id) => document.getElementById(id);
    const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const api = async (path) => (await fetch(path, {cache: "no-store"})).json();

    function pill(text, kind="") {
      return `<span class="pill ${kind}">${esc(text)}</span>`;
    }

    function renderMetrics(stats, inbox) {
      const pending = inbox?.summary?.pending_candidates ?? 0;
      $("metrics").innerHTML = [
        ["Knowledge", stats?.knowledge_count ?? stats?.total_knowledge ?? 0],
        ["Candidates", pending],
        ["Vectors", stats?.embedding_count ?? 0],
        ["DB MB", stats?.db_size_mb ?? stats?.size_mb ?? 0],
      ].map(([label, value]) => `<div class="metric"><strong>${esc(value)}</strong><span>${esc(label)}</span></div>`).join("");
    }

    function renderList(id, items, emptyText) {
      const node = $(id);
      if (!items || !items.length) {
        node.innerHTML = `<div class="empty">${esc(emptyText)}</div>`;
        return;
      }
      node.innerHTML = items.map(item => `
        <div class="item" data-id="${esc(item.id || item.candidate_id || "")}">
          <h3>${esc(item.title || item.kind || "Untitled")}</h3>
          <div class="subtle">${esc(item.reason || item.summary || item.safe_action || "")}</div>
          <div class="meta">${pill(item.layer || item.status || "review")}${pill(item.sensitivity || item.category || "")}</div>
        </div>
      `).join("");
      node.querySelectorAll("[data-id]").forEach(el => {
        const idValue = Number(el.dataset.id || 0);
        if (idValue) el.addEventListener("click", () => loadEntry(idValue));
      });
    }

    function renderResults(items) {
      if (!items.length) {
        $("results").innerHTML = `<div class="empty">No matching memory</div>`;
        return;
      }
      $("results").innerHTML = items.map(row => `
        <article class="result" data-id="${esc(row.id)}">
          <h3>${esc(row.title)}</h3>
          <div class="subtle">${esc(row._snippet || row.summary || row.source || "")}</div>
          <div class="meta">
            ${pill("#" + row.id)}
            ${pill(row.layer || "")}
            ${pill(row.scope || "project")}
            ${pill(row.sensitivity || "low", row.sensitivity === "low" ? "good" : "warn")}
            ${row.best_span ? pill(row.best_span) : ""}
          </div>
        </article>
      `).join("");
      $("results").querySelectorAll("[data-id]").forEach(el => {
        el.addEventListener("click", () => loadEntry(Number(el.dataset.id)));
      });
    }

    async function loadEntry(id) {
      currentEntry = await api(`/api/entry/${id}`);
      renderSidePanel();
      const nodes = currentEntry.nodes || [];
      const first = nodes[0] || {};
      const start = first.line_start || 1;
      const end = Math.min(first.line_end || start + 39, start + 39);
      const range = await api(`/api/read?knowledge_id=${id}&line_start=${start}&line_end=${end}`);
      $("evidence").hidden = false;
      $("evidenceHead").textContent = range.citation || currentEntry.entry?.title || "";
      $("evidenceBody").textContent = (range.lines || []).map(line => `${line.line}| ${line.text}`).join("\n");
    }

    function renderSidePanel() {
      if (!currentEntry || currentEntry.status !== "ok") {
        $("sidePanel").innerHTML = `<div class="empty">Select a memory</div>`;
        return;
      }
      const data = currentEntry[activeTab] || {};
      if (activeTab === "graph") {
        $("sidePanel").innerHTML = `<div class="panel"><h3>${esc(currentEntry.entry.title)}</h3><div class="subtle">${esc(data.edge_count || 0)} linked edges</div></div>` +
          (data.edges || []).map(edge => `<div class="kv"><span>${esc(edge.relation)}</span><strong>#${esc(edge.other_id)} ${esc(edge.other_title)}</strong></div>`).join("");
        return;
      }
      $("sidePanel").innerHTML = Object.entries(data).map(([key, value]) => `
        <div class="kv"><span>${esc(key)}</span><strong>${esc(value || "—")}</strong></div>
      `).join("");
    }

    async function boot() {
      const overview = await api("/api/overview");
      $("projectPath").textContent = overview.project_dir || "";
      renderMetrics(overview.stats || {}, overview.inbox || {});
      renderList("reviewQueue", overview.inbox?.review_queue || overview.inbox?.review_digest?.items || [], "No review items");
      renderList("recentList", overview.recent || [], "No memory yet");
      $("results").innerHTML = `<div class="empty">Search or choose a memory</div>`;
      renderSidePanel();
    }

    $("searchForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const query = $("query").value.trim();
      const payload = await api(`/api/search?q=${encodeURIComponent(query)}&mode=keyword&limit=10`);
      renderResults(payload.results || []);
    });

    document.querySelectorAll(".tabs button").forEach(button => {
      button.addEventListener("click", () => {
        document.querySelectorAll(".tabs button").forEach(b => b.classList.remove("active"));
        button.classList.add("active");
        activeTab = button.dataset.tab;
        renderSidePanel();
      });
    });

    boot().catch(err => {
      $("results").innerHTML = `<div class="empty">${esc(err.message || err)}</div>`;
    });
  </script>
</body>
</html>
"""
