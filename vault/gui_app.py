"""Static browser app for the local Vault GUI."""

from __future__ import annotations

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
    button.danger { background: var(--danger); border-color: var(--danger); }
    button.warn { background: var(--warn); border-color: var(--warn); }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
    textarea {
      width: 100%;
      min-height: 70px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 11px;
      resize: vertical;
      font: inherit;
    }
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
    const postApi = async (path, payload) => (await fetch(path, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload || {}),
      cache: "no-store"
    })).json();

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
      node.innerHTML = items.map(item => {
        const itemId = item.id || item.candidate_id || "";
        const isCandidate = String(itemId).startsWith("mem_") || item.kind === "candidate";
        return `
        <div class="item" data-id="${esc(itemId)}" data-kind="${isCandidate ? "candidate" : "memory"}">
          <h3>${esc(item.title || item.kind || "Untitled")}</h3>
          <div class="subtle">${esc(item.reason || item.summary || item.safe_action || "")}</div>
          <div class="meta">
            ${pill(item.layer || item.status || "review")}
            ${pill(item.sensitivity || item.category || "")}
            ${isCandidate ? pill("candidate", "warn") : ""}
          </div>
        </div>
      `}).join("");
      node.querySelectorAll("[data-id]").forEach(el => {
        if (el.dataset.kind === "candidate") {
          el.addEventListener("click", () => loadCandidate(el.dataset.id));
        } else {
          const idValue = Number(el.dataset.id || 0);
          if (idValue) el.addEventListener("click", () => loadEntry(idValue));
        }
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

    async function loadCandidate(id) {
      const payload = await api(`/api/candidate/${encodeURIComponent(id)}`);
      if (payload.status !== "ok") {
        $("results").innerHTML = `<div class="empty">${esc(payload.error || payload.reason || "Unable to load candidate")}</div>`;
        return;
      }
      const row = payload.candidate || {};
      currentEntry = null;
      $("evidence").hidden = true;
      $("results").innerHTML = `
        <article class="result">
          <h3>${esc(row.title)}</h3>
          <div class="subtle">${esc(row.reason || row.source_ref || "")}</div>
          <div class="meta">
            ${pill(row.id)}
            ${pill(row.layer)}
            ${pill(row.scope)}
            ${pill(row.sensitivity, row.sensitivity === "low" ? "good" : "warn")}
            ${pill("privacy:" + (row.privacy_status || "unknown"))}
            ${pill("duplicate:" + (row.duplicate_status || "unknown"))}
            ${pill("quality:" + (row.quality_status || "unknown"))}
          </div>
        </article>
        <div class="panel">
          <h3>Candidate Content</h3>
          <pre>${esc(row.content || "")}</pre>
        </div>
        <div class="panel">
          <h3>Review Reason</h3>
          <textarea id="reviewReason" placeholder="Optional reason for reject/block. Promotion records the existing gate result."></textarea>
          <div class="actions">
            <button id="promoteCandidate" type="button">Promote</button>
            <button id="rejectCandidate" class="warn" type="button">Reject</button>
            <button id="blockCandidate" class="danger" type="button">Block</button>
          </div>
          <div class="subtle">Every action requires explicit confirmation and records feedback for automation learning.</div>
        </div>
      `;
      $("sidePanel").innerHTML = renderCandidateSide(row);
      $("promoteCandidate").addEventListener("click", () => reviewCandidate(row.id, "promote"));
      $("rejectCandidate").addEventListener("click", () => reviewCandidate(row.id, "reject"));
      $("blockCandidate").addEventListener("click", () => reviewCandidate(row.id, "block"));
    }

    function renderCandidateSide(row) {
      const keys = ["status", "source", "source_ref", "memory_type", "trust", "created_at", "updated_at", "valid_from", "valid_until", "expires_at"];
      const fields = keys.map(key => `<div class="kv"><span>${esc(key)}</span><strong>${esc(row[key] || "—")}</strong></div>`).join("");
      const gates = row.gates ? `<pre>${esc(JSON.stringify(row.gates, null, 2))}</pre>` : "";
      return `<div class="panel"><h3>${esc(row.title)}</h3><div class="subtle">Candidate review</div></div>${fields}${gates}`;
    }

    async function reviewCandidate(id, action) {
      const token = `${id}:${action}`;
      const label = action === "promote" ? "promote into active knowledge" : `${action} this candidate`;
      if (!window.confirm(`Confirm ${label}?\\n\\nRequired token: ${token}`)) return;
      const reason = $("reviewReason")?.value || "";
      const payload = await postApi(`/api/candidate/${encodeURIComponent(id)}/review`, {
        action,
        reason,
        confirm: token
      });
      if (payload.status !== "ok") {
        window.alert(payload.error || payload.reason || "Review action failed");
        return;
      }
      window.alert(`Review action completed: ${payload.result?.status || action}`);
      await boot();
      if (payload.result?.knowledge_id) {
        await loadEntry(payload.result.knowledge_id);
      }
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
      renderList("reviewQueue", overview.candidates || overview.inbox?.review_queue || overview.inbox?.review_digest?.items || [], "No review items");
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
