"""Static browser app for the local Vault GUI."""

from __future__ import annotations

APP_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Vault Memory Control Center</title>
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
    .topbar-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
    .language-select { max-width: 118px; padding: 7px 8px; font-size: 13px; }
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
    .hero {
      margin: 16px 18px;
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }
    .hero h2 {
      margin: 0 0 6px;
      color: var(--ink);
      font-size: 20px;
      text-transform: none;
      letter-spacing: 0;
    }
    .hero .next { margin-top: 12px; color: var(--muted); line-height: 1.5; }
    .choice-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 0 18px 16px; }
    .choice-row .panel { min-height: 96px; }
    .safety-strip {
      margin: 0 18px 16px;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
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
    .filter-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-bottom: 10px; }
    .filter-grid input, .filter-grid select { width: 100%; padding: 8px 9px; font-size: 13px; }
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
    .tabs { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; padding: 12px 12px 0; }
    .tabs button { padding: 8px 6px; background: #fff; color: var(--muted); border-color: var(--line); }
    .tabs button.active { color: #fff; background: var(--accent-2); border-color: var(--accent-2); }
    .right-content { padding: 14px; }
    .kv { display: grid; grid-template-columns: 110px 1fr; gap: 8px; font-size: 13px; padding: 7px 0; border-bottom: 1px solid var(--line); }
    .kv span:first-child { color: var(--muted); }
    .map-list { display: grid; gap: 8px; margin-top: 10px; }
    .map-node, .claim {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 9px;
      background: #fff;
      width: 100%;
      color: var(--ink);
      text-align: left;
    }
    .map-node { cursor: pointer; }
    .map-node:hover { border-color: var(--accent); }
    .map-node strong, .claim strong { display: block; font-size: 13px; }
    .map-node.level-2 { margin-left: 10px; width: calc(100% - 10px); }
    .map-node.level-3, .map-node.level-4, .map-node.level-5, .map-node.level-6 { margin-left: 20px; width: calc(100% - 20px); }
    .graph-canvas {
      position: relative;
      min-height: 270px;
      margin-top: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background:
        linear-gradient(90deg, rgba(216,221,213,.45) 1px, transparent 1px),
        linear-gradient(rgba(216,221,213,.45) 1px, transparent 1px),
        #fbfbf8;
      background-size: 32px 32px;
      overflow: hidden;
    }
    .graph-link {
      position: absolute;
      height: 2px;
      background: #a8b0b8;
      transform-origin: 0 50%;
      opacity: .75;
    }
    .graph-node {
      position: absolute;
      width: 112px;
      min-height: 58px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--ink);
      padding: 7px;
      box-shadow: 0 2px 8px rgba(15, 23, 42, .08);
      font-size: 12px;
      text-align: left;
      overflow-wrap: anywhere;
    }
    .graph-node.center {
      border-color: var(--accent-2);
      background: #eef2ff;
      cursor: default;
    }
    .graph-node.linked { cursor: pointer; }
    .graph-node.linked:hover { border-color: var(--accent); }
    .graph-node small { display: block; color: var(--muted); margin-top: 4px; }
    .empty { padding: 30px 18px; color: var(--muted); text-align: center; }
    @media (max-width: 1040px) {
      .app { grid-template-columns: 280px 1fr; }
      .right { grid-column: 1 / -1; border-left: 0; border-top: 1px solid var(--line); }
    }
    @media (max-width: 760px) {
      .app { display: block; }
      .left, .right { border: 0; border-bottom: 1px solid var(--line); }
      .choice-row { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="left">
      <div class="topbar">
        <div class="topbar-row">
          <h1 id="appTitle">Vault Memory</h1>
          <select id="languageSelect" class="language-select" aria-label="Language">
            <option value="zh-Hant">繁中</option>
            <option value="zh-CN">简中</option>
            <option value="en">English</option>
          </select>
        </div>
        <div class="subtle" id="projectPath"></div>
      </div>
      <div class="section">
        <h2 id="dailyHeading">Daily Report</h2>
        <div id="dailyReport"></div>
        <h2 id="statusHeading">Status</h2>
        <div class="metric-grid" id="metrics"></div>
        <h2 id="tasksHeading">Active Tasks</h2>
        <div id="taskList"></div>
        <h2 id="reviewHeading">Review Inbox</h2>
        <div id="reviewQueue"></div>
        <h2 id="documentsHeading">Documents</h2>
        <div class="filter-grid">
          <input id="docQuery" placeholder="Filter documents">
          <select id="docLayer"><option value="">Any layer</option></select>
          <select id="docCategory"><option value="">Any category</option></select>
          <select id="docSensitivity"><option value="">Any sensitivity</option></select>
        </div>
        <div class="actions">
          <button id="applyDocFilters" class="secondary" type="button">Apply</button>
          <button id="clearDocFilters" class="secondary" type="button">Clear</button>
        </div>
        <div id="documentList"></div>
      </div>
    </aside>
    <main class="content">
      <form class="searchbar" id="searchForm">
        <input id="query" name="query" placeholder="Search project memory" autocomplete="off">
        <button id="searchButton" type="submit">Search</button>
      </form>
      <div class="results" id="results"></div>
      <div class="evidence" id="evidence" hidden>
        <div class="evidence-head" id="evidenceHead"></div>
        <pre id="evidenceBody"></pre>
      </div>
    </main>
    <aside class="right">
      <div class="tabs">
        <button data-tab="map" class="active">Map</button>
        <button data-tab="graph">Graph</button>
        <button data-tab="timeline">Timeline</button>
        <button data-tab="governance">Governance</button>
        <button data-tab="usage">Usage</button>
      </div>
      <div class="right-content" id="sidePanel"></div>
    </aside>
  </div>
  <script>
    let currentEntry = null;
    let currentTask = null;
    let activeTab = "map";
    let documentFacets = {};
    let currentLanguage = localStorage.getItem("vaultGuiLanguage") || "zh-Hant";

    const $ = (id) => document.getElementById(id);
    const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const UI_TEXT = {
      "zh-Hant": {
        title: "Vault 記憶",
        pageTitle: "Vault 記憶控制台",
        daily: "每日報告",
        status: "狀態",
        tasks: "進行中任務",
        review: "審核佇列",
        documents: "文件",
        knowledge: "知識",
        candidates: "候選",
        vectors: "向量",
        dbMb: "DB MB",
        anyLayer: "任何層級",
        anyCategory: "任何分類",
        anySensitivity: "任何敏感度",
        searchPlaceholder: "搜尋專案記憶",
        search: "搜尋",
        apply: "套用",
        clear: "清除",
        noDaily: "還沒有每日報告",
        noDecision: "今天不需要你決定",
        noTasks: "沒有進行中任務",
        noReview: "沒有待審項目",
        noDocs: "沒有文件",
        noMemory: "沒有符合的記憶",
        selectMemory: "選擇一筆記憶",
        controlCenter: "記憶控制台",
        noDecisionBody: "你的 Agent 可以繼續維護記憶。明天再看下一份短報告。",
        agents: "Agent",
        toConfirm: "待確認",
        expired: "過期",
        reviewItem: "審核項目",
        reviewAction: "審核",
        decide: "決定",
        readOnly: "read-only 報告",
        tokenProtected: "GUI token 保護",
        noSilentMutation: "不會偷偷 promote/archive/delete",
        boundedReads: "先讀有邊界證據",
        agentDefaultHeadline: "你的 Agent 可以操作 Vault；你只看每日短報告。",
        noHumanAction: "今天不需要人處理。",
        next: "下一步",
        blockers: "阻礙",
      },
      "zh-CN": {
        title: "Vault 记忆",
        pageTitle: "Vault 记忆控制台",
        daily: "每日报告",
        status: "状态",
        tasks: "进行中任务",
        review: "审核队列",
        documents: "文件",
        knowledge: "知识",
        candidates: "候选",
        vectors: "向量",
        dbMb: "DB MB",
        anyLayer: "任何层级",
        anyCategory: "任何分类",
        anySensitivity: "任何敏感度",
        searchPlaceholder: "搜索项目记忆",
        search: "搜索",
        apply: "应用",
        clear: "清除",
        noDaily: "还没有每日报告",
        noDecision: "今天不需要你决定",
        noTasks: "没有进行中任务",
        noReview: "没有待审项目",
        noDocs: "没有文件",
        noMemory: "没有匹配的记忆",
        selectMemory: "选择一条记忆",
        controlCenter: "记忆控制台",
        noDecisionBody: "你的 Agent 可以继续维护记忆。明天再看下一份短报告。",
        agents: "Agent",
        toConfirm: "待确认",
        expired: "过期",
        reviewItem: "审核项目",
        reviewAction: "审核",
        decide: "决定",
        readOnly: "read-only 报告",
        tokenProtected: "GUI token 保护",
        noSilentMutation: "不会偷偷 promote/archive/delete",
        boundedReads: "先读有边界证据",
        agentDefaultHeadline: "你的 Agent 可以操作 Vault；你只看每日短报告。",
        noHumanAction: "今天不需要人处理。",
        next: "下一步",
        blockers: "阻碍",
      },
      en: {
        title: "Vault Memory",
        pageTitle: "Vault Memory Control Center",
        daily: "Daily Report",
        status: "Status",
        tasks: "Active Tasks",
        review: "Review Inbox",
        documents: "Documents",
        knowledge: "Knowledge",
        candidates: "Candidates",
        vectors: "Vectors",
        dbMb: "DB MB",
        anyLayer: "Any layer",
        anyCategory: "Any category",
        anySensitivity: "Any sensitivity",
        searchPlaceholder: "Search project memory",
        search: "Search",
        apply: "Apply",
        clear: "Clear",
        noDaily: "No daily report yet",
        noDecision: "No decision needed",
        noTasks: "No active tasks",
        noReview: "No review items",
        noDocs: "No documents",
        noMemory: "No matching memory",
        selectMemory: "Select a memory",
        controlCenter: "Memory Control Center",
        noDecisionBody: "Your agent can keep maintaining memory. Come back tomorrow for the next short report.",
        agents: "agents",
        toConfirm: "to confirm",
        expired: "expired",
        reviewItem: "Review item",
        reviewAction: "review",
        decide: "decide",
        readOnly: "read-only report",
        tokenProtected: "GUI token protected",
        noSilentMutation: "No silent promote/archive/delete",
        boundedReads: "Bounded reads first",
        agentDefaultHeadline: "Your agent can operate Vault; you only review the daily report.",
        noHumanAction: "No human action needed today.",
        next: "next",
        blockers: "blockers",
      }
    };
    const ui = () => UI_TEXT[currentLanguage] || UI_TEXT.en;
    const api = async (path) => {
      const separator = path.includes("?") ? "&" : "?";
      return (await fetch(`${path}${separator}lang=${encodeURIComponent(currentLanguage)}`, {cache: "no-store"})).json();
    };
    const postApi = async (path, payload) => (await fetch(path, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload || {}),
      cache: "no-store"
    })).json();

    function pill(text, kind="") {
      return `<span class="pill ${kind}">${esc(text)}</span>`;
    }

    function applyLanguage() {
      const text = ui();
      document.title = text.pageTitle;
      $("languageSelect").value = currentLanguage;
      $("appTitle").textContent = text.title;
      $("dailyHeading").textContent = text.daily;
      $("statusHeading").textContent = text.status;
      $("tasksHeading").textContent = text.tasks;
      $("reviewHeading").textContent = text.review;
      $("documentsHeading").textContent = text.documents;
      $("query").placeholder = text.searchPlaceholder;
      $("docQuery").placeholder = text.documents;
      $("searchButton").textContent = text.search;
      $("applyDocFilters").textContent = text.apply;
      $("clearDocFilters").textContent = text.clear;
    }

    function renderMetrics(stats, inbox) {
      const pending = inbox?.summary?.pending_candidates ?? 0;
      const text = ui();
      $("metrics").innerHTML = [
        [text.knowledge, stats?.knowledge_count ?? stats?.total_knowledge ?? 0],
        [text.candidates, pending],
        [text.vectors, stats?.embedding_count ?? 0],
        [text.dbMb, stats?.db_size_mb ?? stats?.size_mb ?? 0],
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

    function renderTaskList(items) {
      const node = $("taskList");
      if (!items || !items.length) {
        node.innerHTML = `<div class="empty">${esc(ui().noTasks)}</div>`;
        return;
      }
      node.innerHTML = items.map(task => `
        <div class="item" data-task-id="${esc(task.id || "")}">
          <h3>${esc(task.title || task.id || "Untitled task")}</h3>
          <div class="subtle">${esc(task.goal || task.continuation_note || "")}</div>
          <div class="meta">
            ${pill(task.status || "active", task.status === "blocked" ? "warn" : "good")}
            ${pill((task.next_actions || []).length + " " + ui().next)}
            ${task.blockers && task.blockers.length ? pill(task.blockers.length + " " + ui().blockers, "warn") : ""}
          </div>
        </div>
      `).join("");
      node.querySelectorAll("[data-task-id]").forEach(el => {
        el.addEventListener("click", () => loadTask(el.dataset.taskId));
      });
    }

    function renderDailyReport(report) {
      const node = $("dailyReport");
      const text = ui();
      if (!report || !report.summary) {
        node.innerHTML = `<div class="empty">${esc(text.noDaily)}</div>`;
        return;
      }
      const summary = report.summary || {};
      const cards = report.review_cards || [];
      const cardHtml = cards.length ? cards.slice(0, 3).map(card => `
        <div class="item" data-daily-card="${esc(card.id || "")}">
          <h3>${esc(card.title || card.id || card.kind || text.reviewItem)}</h3>
          <div class="subtle">${esc(card.reason || card.safe_action || "")}</div>
          <div class="meta">
            ${pill(card.suggested_decision || text.reviewAction, "warn")}
            ${pill((card.choices || []).slice(0, 2).join(" / ") || text.decide)}
          </div>
        </div>
      `).join("") : `<div class="empty">${esc(text.noDecision)}</div>`;
      node.innerHTML = `
        <div class="panel">
          <h3>${esc(report.headline || text.daily)}</h3>
          <div class="subtle">${esc(report.next_action || "")}</div>
          <div class="meta">
            ${pill(`${summary.needs_confirmation || 0} ${text.toConfirm}`, summary.needs_confirmation ? "warn" : "good")}
            ${pill(`${summary.pending_candidates || 0} ${text.candidates}`)}
            ${pill(`${summary.expired_active || 0} ${text.expired}`)}
            ${pill(report.safety?.read_only ? text.readOnly : text.reviewAction)}
          </div>
        </div>
        ${cardHtml}
      `;
      node.querySelectorAll("[data-daily-card]").forEach(el => {
        const id = el.dataset.dailyCard || "";
        if (id.startsWith("mem_")) el.addEventListener("click", () => loadCandidate(id));
      });
    }

    function renderMemoryControlCenter(overview) {
      const report = overview.daily_report || {};
      const summary = report.summary || {};
      const cards = report.review_cards || [];
      const text = ui();
      const choices = cards.length ? cards.slice(0, 3).map(card => `
        <div class="panel">
          <h3>${esc(card.title || card.id || text.reviewItem)}</h3>
          <div class="subtle">${esc(card.reason || card.safe_action || "")}</div>
          <div class="meta">
            ${pill(card.suggested_decision || text.reviewAction, "warn")}
            ${pill((card.choices || []).slice(0, 3).join(" / ") || text.decide)}
          </div>
        </div>
      `).join("") : `
        <div class="panel">
          <h3>${esc(text.noDecision)}</h3>
          <div class="subtle">${esc(text.noDecisionBody)}</div>
        </div>
      `;
      $("results").innerHTML = `
        <section class="hero">
          <h2>${esc(text.controlCenter)}</h2>
          <div class="subtle">${esc(report.headline || text.agentDefaultHeadline)}</div>
          <div class="meta">
            ${pill(`${summary.needs_confirmation || 0} ${text.toConfirm}`, summary.needs_confirmation ? "warn" : "good")}
            ${pill(`${summary.pending_candidates || 0} ${text.candidates}`)}
            ${pill(`${summary.registered_agents || 0} ${text.agents}`)}
            ${pill(text.readOnly, "good")}
          </div>
          <div class="next">${esc(report.next_action || text.noHumanAction)}</div>
        </section>
        <div class="safety-strip">
          ${pill(text.tokenProtected, "good")}
          ${pill(text.noSilentMutation, "good")}
          ${pill(text.boundedReads, "good")}
        </div>
        <div class="choice-row">${choices}</div>
      `;
    }

    function renderFacetSelect(id, label, items, selected) {
      const options = [`<option value="">${esc(label)}</option>`].concat(
        (items || []).map(item => {
          const value = item.value || "";
          const title = `${value} (${item.count})`;
          return `<option value="${esc(value)}" ${value === selected ? "selected" : ""}>${esc(title)}</option>`;
        })
      );
      $(id).innerHTML = options.join("");
    }

    function renderDocumentFilters(filters, facets) {
      documentFacets = facets || documentFacets || {};
      $("docQuery").value = filters?.query || $("docQuery").value || "";
      renderFacetSelect("docLayer", ui().anyLayer, documentFacets.layers || [], filters?.layer || "");
      renderFacetSelect("docCategory", ui().anyCategory, documentFacets.categories || [], filters?.category || "");
      renderFacetSelect("docSensitivity", ui().anySensitivity, documentFacets.sensitivities || [], filters?.sensitivity || "");
    }

    async function loadDocuments() {
      const params = new URLSearchParams({
        q: $("docQuery")?.value || "",
        layer: $("docLayer")?.value || "",
        category: $("docCategory")?.value || "",
        sensitivity: $("docSensitivity")?.value || "",
        limit: "50"
      });
      const payload = await api(`/api/documents?${params.toString()}`);
      renderDocumentFilters(payload.filters || {}, payload.facets || {});
      renderList("documentList", payload.documents || [], ui().noDocs);
    }

    function renderResults(items) {
      if (!items.length) {
        $("results").innerHTML = `<div class="empty">${esc(ui().noMemory)}</div>`;
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

    async function readRange(id, start, end) {
      const range = await api(`/api/read?knowledge_id=${id}&line_start=${start}&line_end=${end}`);
      $("evidence").hidden = false;
      $("evidenceHead").textContent = range.citation || currentEntry.entry?.title || "";
      $("evidenceBody").textContent = (range.lines || []).map(line => `${line.line}| ${line.text}`).join("\n");
    }

    async function loadEntry(id) {
      currentTask = null;
      currentEntry = await api(`/api/entry/${id}`);
      renderSidePanel();
      const nodes = currentEntry.nodes || [];
      const first = nodes[0] || {};
      const start = first.line_start || 1;
      const end = Math.min(first.line_end || start + 39, start + 39);
      await readRange(id, start, end);
    }

    async function loadCandidate(id) {
      const payload = await api(`/api/candidate/${encodeURIComponent(id)}`);
      if (payload.status !== "ok") {
        $("results").innerHTML = `<div class="empty">${esc(payload.error || payload.reason || "Unable to load candidate")}</div>`;
        return;
      }
      const row = payload.candidate || {};
      currentTask = null;
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

    async function loadTask(id) {
      const payload = await api(`/api/task/${encodeURIComponent(id)}`);
      if (payload.status !== "ok") {
        $("results").innerHTML = `<div class="empty">${esc(payload.error || payload.reason || "Unable to load task")}</div>`;
        return;
      }
      currentEntry = null;
      currentTask = payload;
      $("evidence").hidden = true;
      const task = payload.task || {};
      $("results").innerHTML = renderTaskMain(task, payload.markdown || "");
      renderSidePanel();
    }

    function renderTaskMain(task, markdown) {
      const section = (title, items) => {
        if (!items || !items.length) return "";
        return `<div class="panel"><h3>${esc(title)}</h3>${items.map(item => `<div class="subtle">• ${esc(item)}</div>`).join("")}</div>`;
      };
      return `
        <article class="result">
          <h3>${esc(task.title || task.id)}</h3>
          <div class="subtle">${esc(task.goal || "")}</div>
          <div class="meta">
            ${pill(task.id || "")}
            ${pill(task.status || "")}
            ${pill(task.scope || "project")}
            ${pill(task.sensitivity || "low", task.sensitivity === "low" ? "good" : "warn")}
          </div>
        </article>
        ${section("Current Plan", task.current_plan)}
        ${section("Completed", task.completed)}
        ${section("Hard Decisions", task.hard_decisions)}
        ${section("Blockers", task.blockers)}
        ${section("Next Actions", task.next_actions)}
        <div class="panel">
          <h3>Handoff Markdown</h3>
          <pre>${esc(markdown || "")}</pre>
        </div>
      `;
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
      if (currentTask && currentTask.status === "ok") {
        $("sidePanel").innerHTML = renderTaskSide(currentTask.task || {});
        return;
      }
      if (!currentEntry || currentEntry.status !== "ok") {
        $("sidePanel").innerHTML = `<div class="empty">${esc(ui().selectMemory)}</div>`;
        return;
      }
      const data = currentEntry[activeTab] || {};
      if (activeTab === "map") {
        $("sidePanel").innerHTML = renderMapPanel(currentEntry);
        $("sidePanel").querySelectorAll("[data-read-node]").forEach(button => {
          button.addEventListener("click", () => {
            const start = Number(button.dataset.lineStart || 1);
            const end = Number(button.dataset.lineEnd || start);
            readRange(currentEntry.entry.id, start, end);
          });
        });
        return;
      }
      if (activeTab === "graph") {
        $("sidePanel").innerHTML = renderGraphPanel(currentEntry);
        $("sidePanel").querySelectorAll("[data-open-node]").forEach(button => {
          button.addEventListener("click", () => {
            const id = Number(button.dataset.openNode || 0);
            if (id) loadEntry(id);
          });
        });
        return;
      }
      $("sidePanel").innerHTML = Object.entries(data).map(([key, value]) => `
        <div class="kv"><span>${esc(key)}</span><strong>${esc(value || "—")}</strong></div>
      `).join("");
    }

    function renderMapPanel(entry) {
      const nodes = entry.nodes || [];
      const claims = entry.claims || [];
      const nodeHtml = nodes.length ? nodes.map(node => {
        const start = node.line_start || 1;
        const end = node.line_end || start;
        const level = Math.max(1, Math.min(6, Number(node.level || 1)));
        return `
          <button class="map-node level-${level}" type="button" data-read-node="1" data-line-start="${esc(start)}" data-line-end="${esc(end)}">
            <strong>${esc(node.heading || node.path || "Untitled section")}</strong>
            <span class="subtle">${esc(node.path || "")} L${esc(start)}-L${esc(end)}</span>
          </button>
        `;
      }).join("") : `<div class="empty">No Document Map nodes</div>`;
      const claimHtml = claims.length ? claims.slice(0, 8).map(claim => `
        <div class="claim">
          <strong>${esc(claim.claim || "")}</strong>
          <span class="subtle">${esc(claim.node_uid || "")} L${esc(claim.line_start || "—")}-L${esc(claim.line_end || "—")}</span>
        </div>
      `).join("") : `<div class="empty">No claims yet</div>`;
      return `
        <div class="panel">
          <h3>${esc(entry.entry.title)}</h3>
          <div class="subtle">${esc(nodes.length)} sections · ${esc(claims.length)} visible claims</div>
        </div>
        <h2>Sections</h2>
        <div class="map-list">${nodeHtml}</div>
        <h2>Claims</h2>
        <div class="map-list">${claimHtml}</div>
      `;
    }

    function renderTaskSide(task) {
      const refs = task.evidence_refs || [];
      const events = task.events || [];
      const refsHtml = refs.length ? refs.map(ref => `
        <div class="kv"><span>${esc(ref.ref_type || "ref")}</span><strong>${esc(ref.ref || "")}</strong></div>
      `).join("") : `<div class="empty">No evidence refs</div>`;
      const eventsHtml = events.length ? events.slice(-8).map(event => `
        <div class="kv"><span>${esc(event.event_type || "event")}</span><strong>${esc(event.content || event.created_at || "")}</strong></div>
      `).join("") : `<div class="empty">No task events</div>`;
      return `
        <div class="panel">
          <h3>${esc(task.title || task.id)}</h3>
          <div class="subtle">Task Ledger working set, separate from L0-L3 memory</div>
        </div>
        <div class="kv"><span>task_id</span><strong>${esc(task.id || "")}</strong></div>
        <div class="kv"><span>status</span><strong>${esc(task.status || "")}</strong></div>
        <div class="kv"><span>owner</span><strong>${esc(task.owner_agent || "—")}</strong></div>
        <div class="kv"><span>updated</span><strong>${esc(task.updated_at || "—")}</strong></div>
        <h2>Continuation</h2>
        <div class="panel"><div class="subtle">${esc(task.continuation_note || "No continuation note")}</div></div>
        <h2>Evidence Refs</h2>
        ${refsHtml}
        <h2>Recent Events</h2>
        ${eventsHtml}
      `;
    }

    function renderGraphPanel(entry) {
      const graph = entry.graph || {};
      const edges = (graph.edges || []).slice(0, 8).filter(edge => Number(edge.other_id || 0));
      if (!edges.length) {
        return `
          <div class="panel">
            <h3>${esc(entry.entry.title)}</h3>
            <div class="subtle">No linked memories yet</div>
          </div>
          <div class="empty">Build or link the knowledge graph to see relationships here.</div>
        `;
      }
      const center = { x: 132, y: 106 };
      const radiusX = 102;
      const radiusY = 82;
      const nodeHtml = edges.map((edge, index) => {
        const angle = (-Math.PI / 2) + (index * 2 * Math.PI / edges.length);
        const x = Math.round(center.x + Math.cos(angle) * radiusX);
        const y = Math.round(center.y + Math.sin(angle) * radiusY);
        const dx = x - center.x;
        const dy = y - center.y;
        const length = Math.max(1, Math.round(Math.sqrt(dx * dx + dy * dy)));
        const degrees = Math.round(Math.atan2(dy, dx) * 180 / Math.PI);
        return `
          <div class="graph-link" style="left:${center.x + 56}px;top:${center.y + 29}px;width:${length}px;transform:rotate(${degrees}deg)"></div>
          <button class="graph-node linked" type="button" style="left:${x}px;top:${y}px" data-open-node="${esc(edge.other_id)}">
            <strong>#${esc(edge.other_id)} ${esc(edge.other_title || "Linked memory")}</strong>
            <small>${esc(edge.relation || "related")} · ${esc(edge.weight || 0)}</small>
          </button>
        `;
      }).join("");
      const listHtml = edges.map(edge => `
        <div class="kv"><span>${esc(edge.relation || "related")}</span><strong>#${esc(edge.other_id)} ${esc(edge.other_title || "Linked memory")}</strong></div>
      `).join("");
      return `
        <div class="panel">
          <h3>${esc(entry.entry.title)}</h3>
          <div class="subtle">${esc(graph.edge_count || edges.length)} linked edges</div>
        </div>
        <div class="graph-canvas">
          ${nodeHtml}
          <div class="graph-node center" style="left:${center.x}px;top:${center.y}px">
            <strong>#${esc(entry.entry.id)} ${esc(entry.entry.title)}</strong>
            <small>current memory</small>
          </div>
        </div>
        <h2>Linked Memories</h2>
        ${listHtml}
      `;
    }

    async function boot() {
      applyLanguage();
      const overview = await api("/api/overview");
      $("projectPath").textContent = overview.project_dir || "";
      renderMetrics(overview.stats || {}, overview.inbox || {});
      renderTaskList(overview.tasks || []);
      renderDailyReport(overview.daily_report || {});
      renderList("reviewQueue", overview.candidates || overview.inbox?.review_queue || overview.inbox?.review_digest?.items || [], "No review items");
      await loadDocuments();
      renderMemoryControlCenter(overview);
      renderSidePanel();
    }

    $("languageSelect").addEventListener("change", async () => {
      currentLanguage = $("languageSelect").value || "en";
      localStorage.setItem("vaultGuiLanguage", currentLanguage);
      applyLanguage();
      await boot();
    });

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

    $("applyDocFilters").addEventListener("click", () => loadDocuments());
    $("clearDocFilters").addEventListener("click", () => {
      $("docQuery").value = "";
      $("docLayer").value = "";
      $("docCategory").value = "";
      $("docSensitivity").value = "";
      loadDocuments();
    });
    $("docQuery").addEventListener("keydown", event => {
      if (event.key === "Enter") {
        event.preventDefault();
        loadDocuments();
      }
    });

    boot().catch(err => {
      $("results").innerHTML = `<div class="empty">${esc(err.message || err)}</div>`;
    });
  </script>
</body>
</html>
"""
