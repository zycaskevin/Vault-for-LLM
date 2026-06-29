"""MCP tool schemas and visibility profiles."""

from __future__ import annotations

from vault.mcp_memory import (
    MCP_MEMORY_CANDIDATE_MAX_LIMIT,
    MCP_MEMORY_LOOP_TOOL_NAMES,
    MCP_MEMORY_LOOP_TOOLS,
)
from vault.mcp_search import MCP_SEARCH_MAX_LIMIT, MCP_SEARCH_MAX_OFFSET
from vault.mcp_skill import MCP_SKILL_TOOL_NAMES, MCP_SKILL_TOOLS
from vault.mcp_task import MCP_TASK_TOOL_NAMES, MCP_TASK_TOOLS


TOOLS = [
    {
        "name": "vault_search",
        "description": "搜尋 Vault 百科知識庫。支援關鍵字、向量、混合搜尋。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜尋查詢（中英文皆可）"
                },
                "mode": {
                    "type": "string",
                    "enum": ["auto", "keyword", "vector", "semantic", "hybrid"],
                    "description": "搜尋模式（預設 auto）",
                    "default": "auto"
                },
                "limit": {
                    "type": "integer",
                    "description": "最多回傳幾筆（預設 10）",
                    "default": 10,
                    "minimum": 1,
                    "maximum": MCP_SEARCH_MAX_LIMIT
                },
                "offset": {
                    "type": "integer",
                    "description": "跳過前 N 筆（分頁用，預設 0）",
                    "default": 0,
                    "minimum": 0,
                    "maximum": MCP_SEARCH_MAX_OFFSET
                },
                "normalize_scores": {
                    "type": "boolean",
                    "description": "是否對分數進行標準化（預設 false）",
                    "default": False
                },
                "include_snippet": {
                    "type": "boolean",
                    "description": "是否在結果中包含內容片段（預設 false）",
                    "default": False
                },
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "指定回傳欄位（如 ['id', 'title', 'best_claim']），預設全欄位"
                },
                "compact": {
                    "type": "boolean",
                    "description": "回傳精簡 payload（MCP 預設 true；設為 false 可取得含 content_preview 的完整輸出）",
                    "default": True
                },
                "agent_id": {
                    "type": "string",
                    "description": "可選 Agent 身份；提供後套用 scope/sensitivity/allowed_agents 讀取過濾",
                    "default": ""
                },
                "include_private": {
                    "type": "boolean",
                    "description": "搭配 agent_id 使用；允許讀取 owner/allow-list 授權的 private 記憶",
                    "default": False
                },
                "max_sensitivity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "restricted"],
                    "description": "最高敏感度；MCP 預設 medium 以排除 high/restricted",
                    "default": "medium"
                },
                "include_expired_temporal": {
                    "type": "boolean",
                    "description": "是否保留 temporal_state=past 的過期事實；預設 true 並在結果中標記",
                    "default": True
                },
                "include_future_temporal": {
                    "type": "boolean",
                    "description": "是否保留 temporal_state=future 的尚未生效事實；預設 true 並在結果中標記",
                    "default": True
                },
                "temporal_as_of": {
                    "type": "string",
                    "description": "可選 ISO 時間，用於判斷 temporal_state",
                    "default": ""
                },
            },
            "required": ["query"]
        }
    },
    {
        "name": "vault_add",
        "description": "Direct low-level add to active Vault knowledge. Prefer vault_memory_propose for autonomous agents and unreviewed memories.",
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
                "scope": {"type": "string", "enum": ["private", "project", "shared", "public"], "default": "project"},
                "sensitivity": {"type": "string", "enum": ["low", "medium", "high", "restricted"], "default": "low"},
                "owner_agent": {"type": "string", "default": ""},
                "allowed_agents": {"type": "array", "items": {"type": "string"}, "default": []},
                "memory_type": {"type": "string", "default": "knowledge"},
                "expires_at": {"type": "string", "default": ""},
                "agent_id": {"type": "string", "description": "Calling agent identity for write-side governance.", "default": ""},
                "allow_shared": {"type": "boolean", "description": "Required for shared/public writes.", "default": False},
                "allow_private": {"type": "boolean", "description": "Required for private writes.", "default": False},
                "allow_high_sensitivity": {"type": "boolean", "description": "Required for high-sensitivity writes.", "default": False},
                "allow_restricted": {"type": "boolean", "description": "Required for restricted writes.", "default": False},
            },
            "required": ["title", "content"]
        }
    },
    {
        "name": "vault_memory_propose",
        "description": "Propose a possible memory through deterministic gates. Candidate-first; use this instead of vault_add for autonomous agents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "source": {"type": "string", "default": "mcp"},
                "source_ref": {"type": "string", "default": ""},
                "layer": {"type": "string", "enum": ["L0", "L1", "L2", "L3"], "default": "L3"},
                "category": {"type": "string", "default": "general"},
                "tags": {"type": "string", "default": ""},
                "trust": {"type": "number", "default": 0.5},
                "scope": {"type": "string", "enum": ["private", "project", "shared", "public"], "default": "project"},
                "sensitivity": {"type": "string", "enum": ["low", "medium", "high", "restricted"], "default": "low"},
                "owner_agent": {"type": "string", "default": ""},
                "allowed_agents": {"type": "array", "items": {"type": "string"}, "default": []},
                "memory_type": {"type": "string", "default": "knowledge"},
                "expires_at": {"type": "string", "default": ""},
                "agent_id": {"type": "string", "description": "Calling agent identity for write-side governance.", "default": ""},
                "allow_shared": {"type": "boolean", "description": "Required for shared/public candidates.", "default": False},
                "allow_private": {"type": "boolean", "description": "Required for private candidates.", "default": False},
                "allow_high_sensitivity": {"type": "boolean", "description": "Required for high-sensitivity candidates.", "default": False},
                "allow_restricted": {"type": "boolean", "description": "Required for restricted candidates.", "default": False},
                "reason": {"type": "string", "description": "Why this is worth remembering"},
                "mode": {"type": "string", "enum": ["candidate", "promote_if_safe"], "default": "candidate"},
            },
            "required": ["title", "content", "reason"]
        }
    },
    {
        "name": "vault_memory_promote",
        "description": "Promote a reviewed memory candidate into raw/ plus active SQLite knowledge. Requires confirm=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "string"},
                "confirm": {"type": "boolean", "default": True},
                "compile": {"type": "boolean", "default": True},
                "build_map": {"type": "boolean", "default": True},
                "agent_id": {"type": "string", "description": "Calling agent identity for write-side governance.", "default": ""},
                "allow_shared": {"type": "boolean", "description": "Required when the candidate writes shared/public memory.", "default": False},
                "allow_private": {"type": "boolean", "description": "Required when the candidate writes private memory.", "default": False},
                "allow_high_sensitivity": {"type": "boolean", "description": "Required when the candidate writes high-sensitivity memory.", "default": False},
                "allow_restricted": {"type": "boolean", "description": "Required when the candidate writes restricted memory.", "default": False},
            },
            "required": ["candidate_id", "confirm"]
        }
    },
    {
        "name": "vault_memory_review",
        "description": "Record a rejected or blocked candidate review outcome so automation can learn without promoting memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "string"},
                "outcome": {"type": "string", "enum": ["rejected", "blocked"]},
                "reason": {"type": "string", "description": "Why the candidate was rejected or blocked"},
                "score": {"type": "number", "description": "Optional 0..1 feedback score"},
            },
            "required": ["candidate_id", "outcome", "reason"]
        }
    },
    {
        "name": "vault_memory_candidates",
        "description": "List memory candidates for review. Defaults to pending candidates and omits full raw content unless requested.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Candidate status filter, for example candidate/promoted/rejected.",
                    "default": "candidate",
                },
                "all": {
                    "type": "boolean",
                    "description": "List all statuses instead of filtering by status.",
                    "default": False,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum candidates to return.",
                    "default": 50,
                    "minimum": 1,
                    "maximum": MCP_MEMORY_CANDIDATE_MAX_LIMIT,
                },
                "include_content": {
                    "type": "boolean",
                    "description": "Include full candidate content. Defaults false to keep MCP payloads small.",
                    "default": False,
                },
                "include_gates": {
                    "type": "boolean",
                    "description": "Include the full gate payload for review.",
                    "default": False,
                },
                "agent_id": {
                    "type": "string",
                    "description": "Optional agent id for read-policy filtering.",
                    "default": "",
                },
                "include_private": {
                    "type": "boolean",
                    "description": "Allow private candidates only when the agent is owner or allowed.",
                    "default": False,
                },
                "max_sensitivity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "restricted"],
                    "description": "Maximum candidate sensitivity to return.",
                    "default": "medium",
                },
            },
        }
    },
    {
        "name": "vault_capture_session",
        "description": "Preview or write reviewable memory candidates from an agent session transcript. Dry-run by default; never promotes active memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "transcript_path": {
                    "type": "string",
                    "description": "Transcript path. Relative paths resolve under the current Vault project; absolute paths require allow_absolute_path=true.",
                },
                "format": {
                    "type": "string",
                    "enum": ["auto", "jsonl", "markdown", "text"],
                    "default": "auto",
                },
                "source_system": {
                    "type": "string",
                    "description": "Source system, for example codex/hermes/openclaw/claude-code.",
                    "default": "auto",
                },
                "agent_id": {"type": "string", "default": ""},
                "write_candidates": {
                    "type": "boolean",
                    "description": "Write gated candidates into memory_candidates. Defaults false for preview-only capture.",
                    "default": False,
                },
                "max_candidates": {
                    "type": "integer",
                    "description": "Maximum extracted candidates.",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                },
                "min_score": {
                    "type": "number",
                    "description": "Minimum deterministic capture score.",
                    "default": 0.55,
                },
                "scope": {
                    "type": "string",
                    "enum": ["private", "project", "shared", "public"],
                    "default": "project",
                },
                "sensitivity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "restricted"],
                    "default": "low",
                },
                "owner_agent": {"type": "string", "default": ""},
                "allowed_agents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
                "include_content": {
                    "type": "boolean",
                    "description": "Include redacted full candidate content. Defaults false.",
                    "default": False,
                },
                "allow_absolute_path": {
                    "type": "boolean",
                    "description": "Allow reading a transcript outside the current project directory.",
                    "default": False,
                },
            },
            "required": ["transcript_path"],
        }
    },
    {
        "name": "vault_capture_discover",
        "description": "Discover likely session transcript files without reading transcript contents. Use before vault_capture_session when the transcript path is unknown.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "search_dirs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional search directories. Relative paths resolve under the current Vault project.",
                    "default": [],
                },
                "source_system": {
                    "type": "string",
                    "description": "Preferred source system, for example codex/hermes/openclaw/claude-code.",
                    "default": "auto",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum transcript candidates to return.",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum directory depth to scan.",
                    "default": 3,
                    "minimum": 0,
                    "maximum": 8,
                },
                "max_file_mb": {
                    "type": "number",
                    "description": "Skip transcript-like files larger than this size.",
                    "default": 5.0,
                },
                "allow_absolute_paths": {
                    "type": "boolean",
                    "description": "Allow search directories outside the current project.",
                    "default": False,
                },
            },
        }
    },
    {
        "name": "vault_automation_inbox",
        "description": "Read the compact automation review inbox. Read-only by default; returns the shortest candidate/report queue without raw content unless requested.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum inbox items to return.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 50,
                },
                "include_content": {
                    "type": "boolean",
                    "description": "Include redacted candidate content. Defaults false.",
                    "default": False,
                },
                "write_handoff": {
                    "type": "boolean",
                    "description": "Write reports/automation/inbox-latest.json for scheduled handoff.",
                    "default": False,
                },
                "include_transcripts": {
                    "type": "boolean",
                    "description": "Include metadata-only transcript discovery hints. Defaults false.",
                    "default": False,
                },
                "transcript_limit": {
                    "type": "integer",
                    "description": "Maximum transcript discovery hints to include.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
            },
        }
    },
    {
        "name": "vault_automation_activity",
        "description": "Read compact closed-loop automation activity from recent reports. Read-only; returns promoted/skipped reasons without raw candidate content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum recent reports to scan.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
                "event_limit": {
                    "type": "integer",
                    "description": "Maximum activity events to return.",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                },
            },
        }
    },
    {
        "name": "vault_automation_brief",
        "description": "Read a compact automation intelligence brief: learning hints, memory weights, forgetting pressure, shared agent health, and the 5% human-review queue. Read-only.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum learning rules, usage weights, and forgetting preview rows to include.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
                "review_limit": {
                    "type": "integer",
                    "description": "Maximum human-review items to include.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
                "min_events": {
                    "type": "integer",
                    "description": "Minimum feedback events before a group is considered learnable.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 100,
                },
            },
        }
    },
    {
        "name": "vault_automation_handoff",
        "description": "Read the latest compact startup handoff for this project. Read-only; does not inspect raw transcripts or mutate memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "enum": ["auto", "cycle", "inbox"],
                    "description": "Which handoff to read. auto prefers cycle-latest.md and attaches fleet-health when present.",
                    "default": "auto",
                },
                "handoff_path": {
                    "type": "string",
                    "description": "Optional custom reports/automation/*.md or *.json handoff path.",
                    "default": "",
                },
            },
        }
    },
    *MCP_MEMORY_LOOP_TOOLS,
    *MCP_TASK_TOOLS,
    *MCP_SKILL_TOOLS,
    {
        "name": "vault_cold_store_expired",
        "description": "Preview or apply summarize-then-cold-store for expired-but-used memories. Defaults to dry-run; skips private, high/restricted, and L0/L1 memories.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum expired memories to inspect.",
                    "default": 100,
                    "minimum": 1,
                    "maximum": 1000,
                },
                "min_usage": {
                    "type": "integer",
                    "description": "Minimum access_count + citation_count required before cold-store.",
                    "default": 1,
                    "minimum": 1,
                    "maximum": 1000,
                },
                "summary_max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to keep in the cold-store summary.",
                    "default": 360,
                    "minimum": 80,
                    "maximum": 2000,
                },
                "apply": {
                    "type": "boolean",
                    "description": "Actually write summary and archive eligible rows. Defaults false.",
                    "default": False,
                },
            },
        }
    },
    {
        "name": "vault_obsidian_import",
        "description": "Import an existing Obsidian vault into raw/obsidian/. Run dry_run first; compile only after user confirmation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault_dir": {"type": "string", "description": "Obsidian vault directory"},
                "dry_run": {"type": "boolean", "default": True},
                "compile": {"type": "boolean", "default": False},
                "category": {"type": "string", "default": "obsidian"},
                "tags": {"type": "string", "default": "obsidian"},
                "layer": {"type": "string", "enum": ["L0", "L1", "L2", "L3"], "default": "L3"},
                "trust": {"type": "number", "default": 0.5},
                "allow_private": {"type": "boolean", "default": False},
            },
            "required": ["vault_dir"]
        }
    },
    {
        "name": "vault_dream_run",
        "description": "Run deterministic dream curation. Defaults to report-only and never deletes knowledge.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["report", "apply_safe"], "default": "report"},
                "checks": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["freshness", "dedup", "convergence", "metadata", "orphans"]},
                    "default": ["freshness", "dedup", "convergence", "metadata", "orphans"],
                },
                "limit": {"type": "integer", "default": 50},
                "write_report": {"type": "boolean", "default": True},
                "write_candidates": {
                    "type": "boolean",
                    "default": False,
                    "description": "Write Dream suggestions into the memory candidate queue. Never promotes automatically.",
                },
                "backup": {"type": "boolean", "default": True},
            }
        }
    },
    {
        "name": "vault_stats",
        "description": "取得 Vault 百科統計資訊。",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "vault_update_status",
        "description": "Show local Vault version, update hint, Agent registry, shared/private vaults, and startup handoff commands.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "latest_version": {
                    "type": "string",
                    "description": "Optional known latest version. Avoids network checks when provided.",
                    "default": "",
                },
                "check_pypi": {
                    "type": "boolean",
                    "description": "Contact PyPI to resolve the latest version. Defaults false for bounded startup.",
                    "default": False,
                },
                "read_status": {
                    "type": "boolean",
                    "description": "Read existing ~/.vault-for-llm/update-status.json without recomputing. Defaults false.",
                    "default": False,
                },
                "doctor": {
                    "type": "boolean",
                    "description": "Check shared update-status health without adding a separate MCP tool. Defaults false.",
                    "default": False,
                },
                "max_status_age_minutes": {
                    "type": "integer",
                    "description": "Freshness threshold for doctor mode. Defaults 1440 minutes.",
                    "default": 1440,
                    "minimum": 0,
                },
                "agent_id": {
                    "type": "string",
                    "description": "Optional Agent/runtime id for a focused startup checklist.",
                    "default": "",
                },
                "write_status": {
                    "type": "boolean",
                    "description": "Write ~/.vault-for-llm/update-status.json. Defaults false.",
                    "default": False,
                },
            }
        }
    },
    {
        "name": "vault_converge",
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
        "name": "vault_freshness",
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
        "name": "vault_map_show",
        "description": "讀取指定知識的 Document Map 結構（章節、路徑、行號）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "knowledge_id": {
                    "type": "integer",
                    "description": "知識條目 ID"
                },
                "compact": {
                    "type": "boolean",
                    "description": "回傳精簡節點欄位（預設 false）",
                    "default": False
                },
                "agent_id": {"type": "string", "default": ""},
                "include_private": {"type": "boolean", "default": False},
                "max_sensitivity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "restricted"],
                    "default": "medium"
                },
            },
            "required": ["knowledge_id"]
        }
    },
    {
        "name": "vault_read_range",
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
                "agent_id": {"type": "string", "default": ""},
                "include_private": {"type": "boolean", "default": False},
                "max_sensitivity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "restricted"],
                    "default": "medium"
                },
            },
            "required": ["knowledge_id"]
        }
    },
    {
        "name": "vault_remote_search",
        "description": "透過 Supabase read-only RPC 搜尋可讀遠端記憶；預設只回傳安全 metadata 與摘要。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜尋字串；空字串會回傳最新可讀記憶",
                    "default": ""
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent 身份，用於 owner_agent / allowed_agents 過濾",
                    "default": ""
                },
                "include_private": {
                    "type": "boolean",
                    "description": "是否允許讀取此 agent 被授權的 private 記憶",
                    "default": False
                },
                "max_sensitivity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "restricted"],
                    "description": "最高可讀 sensitivity；預設 medium",
                    "default": "medium"
                },
                "limit": {
                    "type": "integer",
                    "description": "最多回傳幾筆，最高 50",
                    "default": 10
                },
                "compact": {
                    "type": "boolean",
                    "description": "回傳精簡欄位（預設 true）",
                    "default": True
                },
            },
        }
    },
    {
        "name": "vault_remote_map_show",
        "description": "從 Supabase 同步目標讀取 Document Map 結構（唯讀；SQLite 仍是 source of truth）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "knowledge_id": {
                    "oneOf": [{"type": "integer"}, {"type": "string"}],
                    "description": "Remote knowledge ID；可為本地同步的正整數 ID，或 Supabase UUID"
                },
                "compact": {
                    "type": "boolean",
                    "description": "回傳精簡節點欄位（預設 false）",
                    "default": False
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent 身份，用於 owner_agent / allowed_agents 過濾",
                    "default": ""
                },
                "include_private": {
                    "type": "boolean",
                    "description": "是否允許讀取此 agent 被授權的 private 記憶",
                    "default": False
                },
                "max_sensitivity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "restricted"],
                    "description": "最高可讀 sensitivity；預設 medium",
                    "default": "medium"
                },
            },
            "required": ["knowledge_id"]
        }
    },
    {
        "name": "vault_remote_read_range",
        "description": "從 Supabase 同步目標讀取受限行號範圍；成功回傳固定 citation，預設最多 80 行。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "knowledge_id": {
                    "oneOf": [{"type": "integer"}, {"type": "string"}],
                    "description": "Remote knowledge ID；可為本地同步的正整數 ID，或 Supabase UUID"
                },
                "node_uid": {
                    "type": "string",
                    "description": "Remote Document Map node_uid；若省略行號，使用此 node 的行號範圍",
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
                "agent_id": {
                    "type": "string",
                    "description": "Agent 身份，用於 owner_agent / allowed_agents 過濾",
                    "default": ""
                },
                "include_private": {
                    "type": "boolean",
                    "description": "是否允許讀取此 agent 被授權的 private 記憶",
                    "default": False
                },
                "max_sensitivity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "restricted"],
                    "description": "最高可讀 sensitivity；預設 medium",
                    "default": "medium"
                },
            },
            "required": ["knowledge_id"]
        }
    },
]

TOOL_PROFILES = {
    "core": [
        "vault_search",
        "vault_read_range",
        "vault_memory_propose",
        "vault_stats",
        "vault_update_status",
        "vault_automation_activity",
        "vault_automation_brief",
        "vault_automation_handoff",
    ],
    "review": [
        "vault_search",
        "vault_read_range",
        "vault_memory_propose",
        "vault_stats",
        "vault_update_status",
        "vault_automation_activity",
        "vault_automation_brief",
        "vault_automation_handoff",
        "vault_memory_promote",
        "vault_memory_review",
        "vault_memory_candidates",
        *MCP_TASK_TOOL_NAMES,
        *MCP_SKILL_TOOL_NAMES,
        "vault_capture_discover",
        "vault_capture_session",
        "vault_automation_inbox",
        *MCP_MEMORY_LOOP_TOOL_NAMES,
        "vault_dream_run",
    ],
    "remote": [
        "vault_search",
        "vault_read_range",
        "vault_memory_propose",
        "vault_stats",
        "vault_update_status",
        "vault_automation_activity",
        "vault_automation_brief",
        "vault_automation_handoff",
        "vault_remote_search",
        "vault_remote_map_show",
        "vault_remote_read_range",
    ],
    "maintenance": [
        "vault_search",
        "vault_read_range",
        "vault_memory_propose",
        "vault_stats",
        "vault_update_status",
        "vault_automation_activity",
        "vault_automation_brief",
        "vault_automation_handoff",
        "vault_memory_promote",
        "vault_memory_review",
        "vault_memory_candidates",
        *MCP_TASK_TOOL_NAMES,
        *MCP_SKILL_TOOL_NAMES,
        "vault_capture_discover",
        "vault_capture_session",
        "vault_automation_inbox",
        *MCP_MEMORY_LOOP_TOOL_NAMES,
        "vault_cold_store_expired",
        "vault_obsidian_import",
        "vault_dream_run",
        "vault_converge",
        "vault_freshness",
    ],
    "full": [tool["name"] for tool in TOOLS],
}

_ACTIVE_TOOLS = TOOLS


def _tool_names_from_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    names = [name.strip() for name in value.split(",") if name.strip()]
    return names or None


def _tools_for_names(names: list[str]) -> list[dict]:
    by_name = {tool["name"]: tool for tool in TOOLS}
    unknown = [name for name in names if name not in by_name]
    if unknown:
        raise ValueError(f"Unknown MCP tool(s): {', '.join(unknown)}")
    return [by_name[name] for name in names]


def select_tools(tool_profile: str = "full", tools: str | None = None) -> list[dict]:
    """Return the MCP tool schemas visible to the client."""
    custom_names = _tool_names_from_csv(tools)
    if custom_names:
        return _tools_for_names(custom_names)
    if tool_profile not in TOOL_PROFILES:
        allowed = ", ".join(sorted(TOOL_PROFILES))
        raise ValueError(f"Unknown MCP tool profile '{tool_profile}' (expected {allowed})")
    return _tools_for_names(TOOL_PROFILES[tool_profile])


def _set_active_tools(tool_profile: str = "full", tools: str | None = None) -> None:
    global _ACTIVE_TOOLS
    _ACTIVE_TOOLS = select_tools(tool_profile, tools)


def active_tools() -> list[dict]:
    """Return the currently visible MCP tool schemas."""
    return _ACTIVE_TOOLS
