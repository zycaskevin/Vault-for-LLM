#!/usr/bin/env python3
"""
Guardrails MCP Server — 讓任何 AI agent 透過 MCP 協議直接讀寫 Guardrails 百科。

暴露的 Tools：
  - guardrails_search(query, mode, limit) — 搜尋知識
  - guardrails_add(title, content, category, tags) — 新增知識
  - guardrails_stats() — 百科統計
  - guardrails_converge(limit) — 收斂檢查
  - guardrails_freshness(apply) — 新鮮度檢查

使用方式：
  1. 作為 stdio MCP server（給 Hermes config.yaml 用）：
     python3 guardrails_lite/guardrails_mcp.py

  2. 在 Hermes config.yaml 加入：
     mcp_servers:
       guardrails:
         command: "conda"
         args: ["run", "-n", "guardrails-lite", "python3", "<project_dir>/guardrails_lite/guardrails_mcp.py"]
"""

import hashlib
import json
import sqlite3
import sys
import os
from pathlib import Path

# 確保模組路徑
GUARDRAILS_DIR = str(Path(__file__).parent.parent)
if GUARDRAILS_DIR not in sys.path:
    sys.path.insert(0, GUARDRAILS_DIR)

DB_PATH = os.path.join(GUARDRAILS_DIR, "guardrails.db")


def _get_db():
    """取得資料庫連線。"""
    from guardrails_lite.guardrails_db import GuardrailsDB
    db = GuardrailsDB(DB_PATH)
    db.connect()
    return db


def _get_search():
    """取得搜尋引擎。"""
    from guardrails_lite.guardrails_db import GuardrailsDB
    from guardrails_lite.guardrails_search import GuardrailsSearch
    from guardrails_lite.guardrails_embed import create_embedding_provider

    db = GuardrailsDB(DB_PATH)
    db.connect()

    embed = None
    try:
        provider_name = db.get_config("embedding_provider", "auto")
        model_key = db.get_config("embedding_model", "mix")
        if provider_name != "none":
            embed = create_embedding_provider(provider=provider_name, model_key=model_key)
    except Exception:
        pass

    return db, GuardrailsSearch(db, embed_provider=embed)


# ── Document Map helpers ───────────────────────────────

def _open_readonly_db(db_path: str | None = None) -> sqlite3.Connection | None:
    """Open the local Guardrails DB read-only without creating missing files."""
    path = Path(db_path or DB_PATH)
    if not path.exists():
        return None
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _line_hash(lines: list[str], line_start: int, line_end: int) -> str:
    text = "\n".join(lines[line_start - 1 : line_end])
    return hashlib.sha256(text.encode()).hexdigest()


def _format_citation(knowledge_id: int, title: str, line_start: int, line_end: int) -> str:
    return f"#{knowledge_id} {title} L{line_start}-L{line_end}"


def _error(code: str, message: str, **extra) -> dict:
    payload = {"error": code, "message": message}
    payload.update(extra)
    return payload


def guardrails_map_show(knowledge_id: int) -> dict:
    """Return a knowledge entry's Document Map structure."""
    return _guardrails_map_show_payload(knowledge_id)


def _guardrails_map_show_payload(knowledge_id: int, db_path: str | None = None) -> dict:
    try:
        knowledge_id = int(knowledge_id)
    except (TypeError, ValueError):
        return _error("invalid_knowledge_id", "knowledge_id must be a positive integer")
    if knowledge_id <= 0:
        return _error("invalid_knowledge_id", "knowledge_id must be a positive integer")

    try:
        conn = _open_readonly_db(db_path)
    except sqlite3.Error as exc:
        return _error("db_open_failed", f"Unable to open guardrails.db read-only: {exc}")
    if conn is None:
        return _error("db_not_found", f"guardrails.db not found at {db_path or DB_PATH}")

    try:
        entry = conn.execute(
            "SELECT id, title FROM knowledge WHERE id=?",
            (knowledge_id,),
        ).fetchone()
        if entry is None:
            return _error("not_found", f"Knowledge id not found: {knowledge_id}")

        rows = conn.execute(
            """SELECT node_uid, path, heading, level, line_start, line_end,
                      summary, token_estimate
               FROM knowledge_nodes
               WHERE knowledge_id=?
               ORDER BY line_start, level, id""",
            (knowledge_id,),
        ).fetchall()
        nodes = [dict(row) for row in rows]
        payload = {
            "entry_id": knowledge_id,
            "title": entry["title"],
            "nodes": nodes,
        }
        if not nodes:
            payload.update(
                _error(
                    "no_document_map_nodes",
                    "No document map nodes found. Run: "
                    f"guardrails map build {knowledge_id}",
                )
            )
        return payload
    finally:
        conn.close()


def guardrails_read_range(
    knowledge_id: int,
    node_uid: str = "",
    line_start: int = 0,
    line_end: int = 0,
) -> dict:
    """Return a bounded, line-numbered source range with a fixed citation."""
    return _guardrails_read_range_payload(
        knowledge_id,
        node_uid=node_uid,
        line_start=line_start,
        line_end=line_end,
    )


def _guardrails_read_range_payload(
    knowledge_id: int,
    node_uid: str = "",
    line_start: int = 0,
    line_end: int = 0,
    *,
    max_lines: int = 80,
    db_path: str | None = None,
) -> dict:
    try:
        knowledge_id = int(knowledge_id)
    except (TypeError, ValueError):
        return _error("invalid_knowledge_id", "knowledge_id must be a positive integer")
    if knowledge_id <= 0:
        return _error("invalid_knowledge_id", "knowledge_id must be a positive integer")

    try:
        max_lines = int(max_lines)
    except (TypeError, ValueError):
        max_lines = 80
    if max_lines <= 0:
        max_lines = 80

    try:
        conn = _open_readonly_db(db_path)
    except sqlite3.Error as exc:
        return _error("db_open_failed", f"Unable to open guardrails.db read-only: {exc}")
    if conn is None:
        return _error("db_not_found", f"guardrails.db not found at {db_path or DB_PATH}")

    try:
        entry = conn.execute(
            "SELECT id, title, content_raw FROM knowledge WHERE id=?",
            (knowledge_id,),
        ).fetchone()
        if entry is None:
            return _error("not_found", f"Knowledge id not found: {knowledge_id}")

        node = None
        node_uid = (node_uid or "").strip()
        if node_uid:
            node = conn.execute(
                """SELECT node_uid, path, heading, line_start, line_end, content_hash
                   FROM knowledge_nodes
                   WHERE knowledge_id=? AND node_uid=?""",
                (knowledge_id, node_uid),
            ).fetchone()
            if node is None:
                return _error("node_not_found", f"Node not found: {node_uid}")

        try:
            line_start = int(line_start or 0)
            line_end = int(line_end or 0)
        except (TypeError, ValueError):
            return _error("invalid_range", "line_start and line_end must be integers")

        if node is not None and line_start == 0 and line_end == 0:
            line_start = int(node["line_start"])
            line_end = int(node["line_end"])
        elif line_start <= 0 or line_end <= 0:
            return _error(
                "invalid_range",
                "Provide a positive line_start and line_end, or provide node_uid alone.",
            )

        if line_start <= 0 or line_end <= 0 or line_end < line_start:
            return _error("invalid_range", "Range must be a positive START-END span")

        if node is not None and not (
            int(node["line_start"]) <= line_start <= line_end <= int(node["line_end"])
        ):
            return _error(
                "range_outside_node",
                f"Requested L{line_start}-L{line_end} is outside node "
                f"{node_uid} L{node['line_start']}-L{node['line_end']}.",
                node_uid=node_uid,
                node_range=f"L{node['line_start']}-L{node['line_end']}",
            )

        line_count = line_end - line_start + 1
        if line_count > max_lines:
            return _error(
                "range_too_large",
                f"Requested {line_count} lines exceeds max {max_lines}. "
                "Please split into smaller ranges.",
                max_lines=max_lines,
                requested_lines=line_count,
            )

        lines = (entry["content_raw"] or "").splitlines()
        total_lines = len(lines)
        if total_lines == 0:
            return _error("empty_content", "Knowledge entry has no content_raw lines")
        if line_start > total_lines or line_end > total_lines:
            return _error(
                "range_outside_content",
                f"Requested L{line_start}-L{line_end} exceeds content length L1-L{total_lines}",
                total_lines=total_lines,
            )

        if node is None:
            node = conn.execute(
                """SELECT node_uid, path, heading, line_start, line_end, content_hash
                   FROM knowledge_nodes
                   WHERE knowledge_id=? AND line_start <= ? AND line_end >= ?
                   ORDER BY level DESC, (line_end - line_start) ASC, id
                   LIMIT 1""",
                (knowledge_id, line_start, line_end),
            ).fetchone()

        content = "\n".join(
            f"{line_number}|{lines[line_number - 1]}"
            for line_number in range(line_start, line_end + 1)
        )
        exact_node_range = (
            node is not None
            and line_start == int(node["line_start"])
            and line_end == int(node["line_end"])
        )
        content_hash = (
            node["content_hash"]
            if exact_node_range and node["content_hash"]
            else _line_hash(lines, line_start, line_end)
        )

        return {
            "entry_id": knowledge_id,
            "title": entry["title"],
            "range": f"L{line_start}-L{line_end}",
            "line_start": line_start,
            "line_end": line_end,
            "citation": _format_citation(knowledge_id, entry["title"], line_start, line_end),
            "content": content,
            "content_hash": content_hash,
            "node_uid": node["node_uid"] if node is not None else "",
            "path": node["path"] if node is not None else "",
        }
    finally:
        conn.close()


# ── MCP Server Implementation ──────────────────────────

TOOLS = [
    {
        "name": "guardrails_search",
        "description": "搜尋 Guardrails 百科知識庫。支援關鍵字、向量、混合搜尋。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜尋查詢（中英文皆可）"
                },
                "mode": {
                    "type": "string",
                    "enum": ["auto", "keyword", "vector", "hybrid"],
                    "description": "搜尋模式（預設 auto）",
                    "default": "auto"
                },
                "limit": {
                    "type": "integer",
                    "description": "最多回傳幾筆（預設 10）",
                    "default": 10
                },
            },
            "required": ["query"]
        }
    },
    {
        "name": "guardrails_add",
        "description": "新增一筆知識到 Guardrails 百科。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "知識標題"
                },
                "content": {
                    "type": "string",
                    "description": "知識內容（Markdown 格式）"
                },
                "category": {
                    "type": "string",
                    "description": "分類（error/technique/architecture/concept/decision/general）",
                    "default": "general"
                },
                "tags": {
                    "type": "string",
                    "description": "標籤（逗號分隔，如 'sqlite,踩坑,擴展'）",
                    "default": ""
                },
                "trust": {
                    "type": "number",
                    "description": "信任分數（0.0-1.0，session 提取建議 0.4，手動驗證 0.8+）",
                    "default": 0.5
                },
                "layer": {
                    "type": "string",
                    "description": "知識層級（L0-L3）",
                    "default": "L3"
                },
            },
            "required": ["title", "content"]
        }
    },
    {
        "name": "guardrails_stats",
        "description": "取得 Guardrails 百科統計資訊。",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "guardrails_converge",
        "description": "執行收斂檢查 — 判斷哪些知識條目內容不夠完整。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "最多檢查幾條（0=全部）",
                    "default": 5
                },
                "min_trust": {
                    "type": "number",
                    "description": "只檢查 trust 低於此值（預設 1.0 = 檢查所有未收斂的）",
                    "default": 1.0
                },
            }
        }
    },
    {
        "name": "guardrails_freshness",
        "description": "檢查知識條目的新鮮度 — 哪些條目過期了。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "stale_only": {
                    "type": "boolean",
                    "description": "只顯示過期條目",
                    "default": True
                },
            }
        }
    },
    {
        "name": "guardrails_map_show",
        "description": "讀取指定知識的 Document Map 結構（章節、路徑、行號）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "knowledge_id": {
                    "type": "integer",
                    "description": "知識條目 ID"
                },
            },
            "required": ["knowledge_id"]
        }
    },
    {
        "name": "guardrails_read_range",
        "description": "讀取指定知識的受限行號範圍；成功回傳固定 citation，預設最多 80 行。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "knowledge_id": {
                    "type": "integer",
                    "description": "知識條目 ID"
                },
                "node_uid": {
                    "type": "string",
                    "description": "Document Map node_uid；若省略行號，使用此 node 的行號範圍",
                    "default": ""
                },
                "line_start": {
                    "type": "integer",
                    "description": "起始行號（含）",
                    "default": 0
                },
                "line_end": {
                    "type": "integer",
                    "description": "結束行號（含）",
                    "default": 0
                },
            },
            "required": ["knowledge_id"]
        }
    },
]


def handle_tool_call(name: str, arguments: dict) -> dict:
    """處理 MCP tool call，回傳結果。"""
    try:
        if name == "guardrails_search":
            db, search = _get_search()
            results = search.search(
                query=arguments.get("query", ""),
                mode=arguments.get("mode", "auto"),
                limit=arguments.get("limit", 10),
                min_trust=0.0,
            )
            # 簡化輸出
            output = []
            for r in results:
                item = {
                    "id": r.get("id"),
                    "title": r.get("title"),
                    "category": r.get("category"),
                    "layer": r.get("layer"),
                    "trust": r.get("trust"),
                    "tags": r.get("tags"),
                    "best_claim": r.get("best_claim", ""),
                    "best_span": r.get("best_span"),
                    "best_node": r.get("best_node"),
                    "node_uid": r.get("node_uid"),
                    "path": r.get("path"),
                    "heading": r.get("heading"),
                    "line_start": r.get("line_start"),
                    "line_end": r.get("line_end"),
                    "citation": r.get("citation"),
                    "recommended_next_tool": r.get("recommended_next_tool"),
                    "rerank_score": r.get("_rerank_score"),
                }
                # 截斷 content_raw
                raw = r.get("content_raw", "")
                if raw and len(raw) > 200:
                    item["content_preview"] = raw[:200] + "..."
                else:
                    item["content_preview"] = raw
                output.append(item)
            db.close()
            return {"result": json.dumps(output, ensure_ascii=False, indent=2)}

        elif name == "guardrails_add":
            db = _get_db()
            kid = db.add_knowledge(
                title=arguments.get("title", ""),
                content_raw=arguments.get("content", ""),
                category=arguments.get("category", "general"),
                tags=arguments.get("tags", ""),
                trust=arguments.get("trust", 0.5),
                layer=arguments.get("layer", "L3"),
                source="mcp",
            )
            db.close()
            return {"result": json.dumps({
                "success": True,
                "id": kid,
                "message": f"已新增知識 #{kid}: {arguments.get('title', '')}",
            }, ensure_ascii=False)}

        elif name == "guardrails_stats":
            db = _get_db()
            stats = db.stats()
            db.close()
            return {"result": json.dumps(stats, ensure_ascii=False, indent=2)}

        elif name == "guardrails_converge":
            # 使用關鍵詞 fallback，不依賴 LLM
            from scripts.convergence_check import check_convergence
            results = check_convergence(
                db_path=DB_PATH,
                apply=False,  # MCP 只讀取，不自動更新
                limit=arguments.get("limit", 5),
                min_trust=arguments.get("min_trust", 1.0),
            )
            if results is None:
                return {"result": json.dumps({"message": "沒有待檢查的條目"}, ensure_ascii=False)}
            output = [{
                "id": r["id"],
                "title": r["title"],
                "avg_score": r["avg_score"],
                "status": r["status"],
            } for r in results]
            return {"result": json.dumps(output, ensure_ascii=False, indent=2)}

        elif name == "guardrails_freshness":
            from scripts.freshness_check import check_freshness
            results = check_freshness(
                db_path=DB_PATH,
                apply=False,  # MCP 只讀取
                stale_only=arguments.get("stale_only", True),
            )
            if results is None:
                return {"result": json.dumps({"message": "百科是空的"}, ensure_ascii=False)}
            output = [{
                "id": r["id"],
                "title": r["title"],
                "freshness": r["new_freshness"],
                "category": r["category"],
            } for r in results[:20]]  # 最多回傳 20 條
            return {"result": json.dumps(output, ensure_ascii=False, indent=2)}

        elif name == "guardrails_map_show":
            payload = _guardrails_map_show_payload(arguments.get("knowledge_id", 0))
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        elif name == "guardrails_read_range":
            payload = _guardrails_read_range_payload(
                knowledge_id=arguments.get("knowledge_id", 0),
                node_uid=arguments.get("node_uid", ""),
                line_start=arguments.get("line_start", 0),
                line_end=arguments.get("line_end", 0),
            )
            return {"result": json.dumps(payload, ensure_ascii=False, indent=2)}

        else:
            return {"error": f"Unknown tool: {name}"}

    except Exception as e:
        return {"error": f"Error: {str(e)}"}


# ── stdio MCP Server ──────────────────────────────────

def run_stdio():
    """作為 stdio MCP server 運行。"""
    # 讀取 MCP 協議訊息
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = message.get("method", "")
        msg_id = message.get("id")
        params = message.get("params", {})

        # Initialize
        if method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False},
                    },
                    "serverInfo": {
                        "name": "guardrails-mcp",
                        "version": "0.1.0",
                    },
                },
            }
            print(json.dumps(response), flush=True)

        # List tools
        elif method == "tools/list":
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS},
            }
            print(json.dumps(response), flush=True)

        # Call tool
        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = handle_tool_call(tool_name, arguments)

            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {"type": "text", "text": result.get("result", result.get("error", ""))}
                    ]
                },
            }
            print(json.dumps(response), flush=True)

        # Notifications (no response needed)
        elif method == "notifications/initialized":
            pass

        else:
            if msg_id is not None:
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
                print(json.dumps(response), flush=True)


# ── Direct CLI (for testing) ──────────────────────────

if __name__ == "__main__":
    # 如果有 --cli 參數，直接執行工具（不啟動 MCP server）
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        tool_name = sys.argv[2] if len(sys.argv) > 2 else "stats"
        args = {}

        if tool_name == "search" and len(sys.argv) > 3:
            args = {"query": sys.argv[3], "mode": "auto", "limit": 5}
        elif tool_name == "add" and len(sys.argv) > 4:
            args = {"title": sys.argv[3], "content": sys.argv[4]}
        elif tool_name == "stats":
            args = {}
        elif tool_name == "converge":
            args = {"limit": 5}
        elif tool_name == "freshness":
            args = {"stale_only": True}

        result = handle_tool_call(f"guardrails_{tool_name}", args)
        print(result.get("result", result.get("error", "")))
    else:
        # 啟動 MCP stdio server
        run_stdio()