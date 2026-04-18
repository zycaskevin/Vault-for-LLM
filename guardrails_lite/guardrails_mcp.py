"""
Vault for LLM — MCP Server

讓 Claude Code、Cursor、OpenClaw 等 AI agent 可以透過 MCP 協議
直接操作知識庫，不需要手動跑 CLI。

安裝方式：
  pip install "vault-for-llm[mcp]"

啟動方式（在有 guardrails.db 的專案目錄）：
  vault-mcp

或指定路徑：
  vault-mcp --project-dir /path/to/project

Claude Code 設定（~/.claude/claude_desktop_config.json）：
  {
    "mcpServers": {
      "vault": {
        "command": "vault-mcp",
        "args": ["--project-dir", "/path/to/your/project"]
      }
    }
  }

可用工具：
  vault_search         — 搜尋知識庫（關鍵字 / 語意 / 混合）
  vault_add            — 新增一筆知識
  vault_get            — 取得單筆知識詳情
  vault_list           — 列出知識（可按層級/分類篩選）
  vault_stats          — 統計資訊
  vault_record_access  — 記錄存取（更新 access_count）
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# ── 檢查 mcp 是否安裝 ────────────────────────────────────
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp import types
except ImportError:
    print(
        "❌ 缺少 mcp 套件。請執行：pip install 'vault-for-llm[mcp]'",
        file=sys.stderr,
    )
    sys.exit(1)

from .guardrails_db import GuardrailsDB
from .guardrails_search import GuardrailsSearch


# ── 全域 DB 實例（Server 啟動後初始化）────────────────────
_db: GuardrailsDB | None = None
_project_dir: Path = Path(".")


def _get_db() -> GuardrailsDB:
    global _db
    if _db is None:
        db_path = _project_dir / "guardrails.db"
        _db = GuardrailsDB(str(db_path))
        _db.connect()
    return _db


def _get_embed():
    """延遲載入嵌入 provider（可選）。"""
    try:
        db = _get_db()
        provider_name = db.get_config("embedding_provider", "auto")
        model_key = db.get_config("embedding_model", "mix")
        if provider_name == "none":
            return None
        from .guardrails_embed import create_embedding_provider
        return create_embedding_provider(provider=provider_name, model_key=model_key)
    except Exception:
        return None


# ── MCP Server 建立 ─────────────────────────────────────
server = Server("vault-for-llm")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="vault_search",
            description=(
                "搜尋 Guardrails 知識庫。支援關鍵字、語意向量、混合模式。"
                "回傳相關知識條目列表（含 trust 分數）。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜尋查詢字串"},
                    "mode": {
                        "type": "string",
                        "enum": ["auto", "keyword", "vector", "hybrid"],
                        "default": "auto",
                        "description": "搜尋模式：auto 自動選擇，keyword 純關鍵字，vector 語意，hybrid 混合",
                    },
                    "limit": {"type": "integer", "default": 10, "description": "回傳筆數上限"},
                    "min_trust": {"type": "number", "default": 0.0, "description": "最低信任分數篩選"},
                    "layer": {
                        "type": "string",
                        "enum": ["L0", "L1", "L2", "L3"],
                        "description": "只搜尋特定層級（可選）",
                    },
                    "record_access": {
                        "type": "boolean",
                        "default": True,
                        "description": "是否記錄存取（影響 trust decay 計算）",
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="vault_add",
            description="新增一筆知識到 Guardrails 知識庫。",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "知識標題"},
                    "content": {"type": "string", "description": "知識內容（Markdown 格式）"},
                    "layer": {
                        "type": "string",
                        "enum": ["L0", "L1", "L2", "L3"],
                        "default": "L3",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["concept", "technique", "workflow", "lesson", "error", "comparison", "general"],
                        "default": "general",
                    },
                    "tags": {"type": "string", "description": "逗號分隔的標籤"},
                    "trust": {"type": "number", "default": 0.5, "description": "信任分數 0.0~1.0"},
                    "source": {"type": "string", "default": "mcp", "description": "知識來源"},
                },
                "required": ["title", "content"],
            },
        ),
        types.Tool(
            name="vault_get",
            description="取得單筆知識的完整內容（by ID）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "知識 ID"},
                    "record_access": {"type": "boolean", "default": True},
                },
                "required": ["id"],
            },
        ),
        types.Tool(
            name="vault_list",
            description="列出知識條目，支援層級/分類/信任度篩選。",
            inputSchema={
                "type": "object",
                "properties": {
                    "layer": {"type": "string", "enum": ["L0", "L1", "L2", "L3"]},
                    "category": {"type": "string"},
                    "min_trust": {"type": "number", "default": 0.0},
                    "limit": {"type": "integer", "default": 50},
                },
            },
        ),
        types.Tool(
            name="vault_stats",
            description="取得知識庫統計資訊（知識數、向量數、圖譜節點/邊數等）。",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="vault_record_access",
            description="記錄一次存取（更新 access_count + last_accessed_at）。用於 trust decay 計算。",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "知識 ID"},
                },
                "required": ["id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """處理所有工具呼叫。"""
    try:
        result = await _dispatch(name, arguments)
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as e:
        error = {"error": str(e), "tool": name}
        return [types.TextContent(type="text", text=json.dumps(error, ensure_ascii=False))]


async def _dispatch(name: str, args: dict) -> Any:
    db = _get_db()

    if name == "vault_search":
        embed = _get_embed() if args.get("mode", "auto") != "keyword" else None
        search = GuardrailsSearch(db, embed_provider=embed)
        results = search.search(
            query=args["query"],
            mode=args.get("mode", "auto"),
            limit=args.get("limit", 10),
            min_trust=args.get("min_trust", 0.0),
            layer=args.get("layer"),
        )
        # 記錄存取
        if args.get("record_access", True):
            for r in results:
                db.record_access(r["id"])
        # 精簡輸出（不回傳完整 content_raw 避免 token 爆炸）
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "layer": r["layer"],
                "category": r["category"],
                "tags": r["tags"],
                "trust": r["trust"],
                "preview": (r.get("content_aaak") or r.get("content_raw", ""))[:200],
                "_score": r.get("_score"),
                "_mode": r.get("_mode"),
            }
            for r in results
        ]

    elif name == "vault_add":
        kid = db.add_knowledge(
            title=args["title"],
            content_raw=args["content"],
            layer=args.get("layer", "L3"),
            category=args.get("category", "general"),
            tags=args.get("tags", ""),
            trust=args.get("trust", 0.5),
            source=args.get("source", "mcp"),
        )
        return {"success": True, "id": kid, "title": args["title"]}

    elif name == "vault_get":
        k = db.get_knowledge(args["id"])
        if not k:
            return {"error": f"找不到 ID={args['id']}"}
        if args.get("record_access", True):
            db.record_access(args["id"])
        return k

    elif name == "vault_list":
        rows = db.list_knowledge(
            layer=args.get("layer"),
            category=args.get("category"),
            min_trust=args.get("min_trust", 0.0),
            limit=args.get("limit", 50),
        )
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "layer": r["layer"],
                "category": r["category"],
                "tags": r["tags"],
                "trust": r["trust"],
                "access_count": r.get("access_count", 0),
            }
            for r in rows
        ]

    elif name == "vault_stats":
        return db.stats()

    elif name == "vault_record_access":
        db.record_access(args["id"])
        return {"success": True, "id": args["id"]}

    else:
        return {"error": f"未知工具: {name}"}


# ── 啟動入口 ─────────────────────────────────────────────

async def _run_server():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main():
    global _project_dir

    parser = argparse.ArgumentParser(
        description="Vault-for-LLM MCP Server — 讓 AI agent 直接操作知識庫"
    )
    parser.add_argument(
        "--project-dir",
        type=str,
        default=None,
        help="專案目錄（含 guardrails.db）。預設自動搜尋",
    )
    args = parser.parse_args()

    if args.project_dir:
        _project_dir = Path(args.project_dir)
    else:
        # 自動向上搜尋
        cwd = Path.cwd()
        for d in [cwd] + list(cwd.parents):
            if (d / "guardrails.db").exists():
                _project_dir = d
                break

    db_file = _project_dir / "guardrails.db"
    print(f"[vault-mcp] 使用資料庫：{db_file}", file=sys.stderr)
    if not db_file.exists():
        print(f"[vault-mcp] ⚠️  資料庫不存在，將在首次工具呼叫時自動建立", file=sys.stderr)

    import asyncio
    asyncio.run(_run_server())


if __name__ == "__main__":
    main()
