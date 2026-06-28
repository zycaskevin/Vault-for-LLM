"""
Vault-for-LLM — CLI 入口。

用法：
  vault init              # 初始化專案
  vault add "標題"         # 加入知識
  vault import novel.md   # 匯入長文件（自動分塊）
  vault import obsidian   # 從既有 Obsidian vault 同步 Markdown notes
  vault compile           # 編譯 raw/ → db + compiled/
  vault search "查詢"     # 搜尋知識
  vault export obsidian   # 匯出成 Obsidian vault Markdown notes
  vault okf validate DIR  # 驗證 OKF-style Markdown bundle
  vault list              # 列出知識
  vault candidates        # 列出候選記憶
  vault remove <id>       # 刪除知識（需要 --confirm）
  vault lint              # 健康檢查
  vault doctor            # 環境診斷
  vault stats             # 統計
  vault install-embedding # 安裝嵌入模型
  vault config set/get    # 配置管理
"""

import argparse
import os
import sys
from pathlib import Path

from .cli_semantic import (
    _close_provider,
    _create_semantic_provider,
    _load_unique_qa_queries,
    _persistent_cache_payload,
    _semantic_stats_payload,
    _semantic_vectors_exist,
    cmd_semantic,
)
from .cli_search import add_temporal_search_arguments, temporal_search_kwargs
from .cli_context import (
    _extract_project_dir_arg,
    _json_print,
    find_project_dir,
    get_project_dir_override,
    set_project_dir_override,
)
from .cli_core import (
    cmd_add,
    cmd_compile,
    cmd_doctor,
    cmd_init,
    cmd_install_embedding,
    cmd_lint,
    cmd_list,
    cmd_remove,
    cmd_search,
    cmd_stats,
)
from .cli_content import (
    cmd_graph,
    cmd_import,
    cmd_skill as _cmd_skill_impl,
    cmd_skill_list,
    cmd_skill_pull,
    cmd_skill_push,
    cmd_skill_search,
    cmd_skill_stats,
)
from .cli_flow import (
    cmd_agent,
    cmd_automation,
    cmd_candidate_review,
    cmd_candidates,
    cmd_capture,
    cmd_db,
    cmd_dream,
    cmd_export,
    cmd_promote,
    cmd_remember,
    cmd_setup_agent,
    cmd_update_status,
    cmd_usage,
)
from .cli_map_remote import cmd_map, cmd_remote, _parse_map_line_range, _positive_int
from .cli_okf import add_okf_parser, cmd_okf
from .cli_quality import (
    cmd_config,
    cmd_converge,
    cmd_cross_validate,
    cmd_dedup,
    cmd_freshness,
    cmd_search_qa,
)
from .gui import DEFAULT_HOST, DEFAULT_PORT, cmd_gui


# ── 專案偵測 ─────────────────────────────────────────────


# ── 子命令 ──────────────────────────────────────────────


# ── CLI 入口 ─────────────────────────────────────────────

def cmd_skill(args):
    """Dispatch skill subcommands through vault.cli symbols for compatibility."""
    if args.skill_action == "push":
        return cmd_skill_push(args)
    if args.skill_action == "search":
        return cmd_skill_search(args)
    if args.skill_action == "pull":
        return cmd_skill_pull(args)
    if args.skill_action == "list":
        return cmd_skill_list(args)
    if args.skill_action == "stats":
        return cmd_skill_stats(args)
    return _cmd_skill_impl(args)


def main(argv: list[str] | None = None):
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    normalized_argv, explicit_project_dir = _extract_project_dir_arg(raw_argv)

    parser = argparse.ArgumentParser(
        prog="vault",
        description="Vault-for-LLM — local-first knowledge vault for LLM agents",
        epilog="Global agent option: --project-dir PATH may be passed before or after the subcommand.",
    )
    from vault import __version__

    parser.add_argument("--version", action="version", version=f"vault-for-llm {__version__}")
    sub = parser.add_subparsers(dest="command", help="子命令")

    # init
    p = sub.add_parser("init", help="初始化專案")
    p.add_argument("project_dir", nargs="?", default=".")

    # add
    from vault.cli_common import add_governance_args

    p = sub.add_parser("add", help="新增知識")
    p.add_argument("title", help="標題")
    p.add_argument("--content", "-c", default="", help="內容")
    p.add_argument("--file", "-f", help="從檔案讀取內容")
    p.add_argument("--layer", choices=["L0", "L1", "L2", "L3"], default="L3")
    p.add_argument("--category", default="general")
    p.add_argument("--tags", default="")
    p.add_argument("--trust", type=float, default=0.5)
    p.add_argument("--source", default="cli", help="來源標籤或檔案路徑")
    p.add_argument("--allow-private", action="store_true", help="允許含秘密模式的內容直接寫入本機 vault")
    add_governance_args(p)

    # remember/promote — safe memory curator workflow
    p = sub.add_parser("remember", help="提出記憶候選（預設不寫入 active knowledge）")
    p.add_argument("title", help="記憶標題")
    p.add_argument("--content", "-c", default="", help="記憶內容；省略時讀 stdin")
    p.add_argument("--file", "-f", help="從檔案讀取記憶內容")
    p.add_argument("--reason", required=True, help="為什麼值得記住")
    p.add_argument("--mode", choices=["candidate", "promote_if_safe"], default="candidate")
    p.add_argument("--layer", choices=["L0", "L1", "L2", "L3"], default="L3")
    p.add_argument("--category", default="general")
    p.add_argument("--tags", default="")
    p.add_argument("--trust", type=float, default=0.5)
    p.add_argument("--source", default="cli")
    p.add_argument("--source-ref", default="")
    add_governance_args(p)
    p.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    p = sub.add_parser("promote", help="將記憶候選提升為 active knowledge")
    p.add_argument("candidate_id", help="memory candidate id")
    p.add_argument("--confirm", action="store_true", help="必要：確認提升候選")
    p.add_argument("--no-compile", action="store_true", help="跳過 raw/ 編譯，直接寫 active DB")
    p.add_argument("--no-build-map", action="store_true", help="搭配 --no-compile 時跳過 Document Map 建置")
    p.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    p = sub.add_parser("candidate-review", help="記錄候選審核結果（rejected/blocked），供自動化學習")
    p.add_argument("candidate_id", help="memory candidate id")
    p.add_argument("--outcome", choices=["rejected", "blocked"], required=True)
    p.add_argument("--reason", required=True, help="為什麼拒絕或阻擋這個候選")
    p.add_argument("--score", type=float, default=None, help="0..1 feedback score；省略時依 outcome 使用安全預設")
    p.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    p = sub.add_parser("gui", help="啟動本機唯讀 Vault Console")
    p.add_argument("--host", default=DEFAULT_HOST, help="bind host；預設 127.0.0.1")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help="bind port；預設 8765")
    p.add_argument("--no-open", action="store_true", help="不要自動開啟瀏覽器")

    p = sub.add_parser("candidates", help="列出候選記憶（預設只列待審候選）")
    p.add_argument("--status", default="candidate", help="候選狀態，例如 candidate/promoted/rejected")
    p.add_argument("--all", action="store_true", help="列出所有狀態")
    p.add_argument("--limit", "-n", type=int, default=50)
    p.add_argument("--include-content", action="store_true", help="包含完整候選內容")
    p.add_argument("--include-gates", action="store_true", help="包含完整 gate payload")
    p.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    # capture — agent/session artifacts into candidate memory
    p = sub.add_parser("capture", help="從 agent/session artifact 擷取候選記憶")
    capture_sub = p.add_subparsers(dest="capture_action", help="Capture 子命令")
    sp = capture_sub.add_parser("discover", help="尋找可能的 session transcript 檔案")
    sp.add_argument("--search-dir", action="append", default=[], help="搜尋目錄；相對路徑以 project-dir 為基準，可重複")
    sp.add_argument("--source-system", default="auto", help="偏好的來源系統，例如 codex/hermes/openclaw/claude-code")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--max-depth", type=int, default=3)
    sp.add_argument("--max-file-mb", type=float, default=5.0)
    sp.add_argument("--allow-absolute-paths", action="store_true", help="允許搜尋 project-dir 以外的絕對路徑")
    sp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")
    sp = capture_sub.add_parser("session", help="從 session transcript 擷取候選記憶")
    sp.add_argument("transcript", help="JSONL、Markdown 或文字 transcript 檔案")
    sp.add_argument("--format", choices=["auto", "jsonl", "markdown", "text"], default="auto")
    sp.add_argument("--source-system", default="auto", help="來源系統，例如 codex/hermes/openclaw/claude-code")
    sp.add_argument("--agent-id", default="", help="產生候選的 agent id")
    sp.add_argument("--write-candidates", action="store_true", help="寫入 memory_candidates；預設只做 dry-run preview")
    sp.add_argument("--max-candidates", "-n", type=int, default=20)
    sp.add_argument("--min-score", type=float, default=0.55)
    sp.add_argument("--scope", choices=["private", "project", "shared", "public"], default="project")
    sp.add_argument("--sensitivity", choices=["low", "medium", "high", "restricted"], default="low")
    sp.add_argument("--owner-agent", default="")
    sp.add_argument("--allowed-agents", default="")
    sp.add_argument("--include-content", action="store_true", help="包含完整候選內容；預設只回 content_preview")
    sp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    # compile
    p = sub.add_parser("compile", help="編譯 raw/ → db + compiled/")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-embed", action="store_true", help="跳過嵌入生成")
    p.add_argument("--allow-private", action="store_true", help="允許含秘密模式的 raw/ 檔案進入編譯")

    # search — 加入 --graph-expand
    p = sub.add_parser("search", help="搜尋知識")
    p.add_argument("query", help="搜尋查詢")
    p.add_argument("--mode", choices=["auto", "keyword", "vector", "semantic", "hybrid"], default="auto")
    p.add_argument("--keyword-only", "-k", action="store_true")
    p.add_argument("--limit", "-n", type=int, default=10)
    p.add_argument("--min-trust", type=float, default=0.0)
    p.add_argument("--min-score", type=float, default=None,
                   help="minimum keyword match score before returning weak/no-result matches")
    p.add_argument("--layer", choices=["L0", "L1", "L2", "L3"])
    p.add_argument("--category")
    p.add_argument("--semantic-vector-kind", choices=["claim", "node"], default="claim",
                   help="stored semantic_vectors kind for --mode semantic/hybrid")
    p.add_argument("--allow-hash", action="store_true",
                   help="explicitly allow deterministic hash provider for tests/dev")
    p.add_argument("--hash-dim", type=int, default=32,
                   help="hash provider dimension when --allow-hash or hash config is used")
    p.add_argument("--graph-expand", type=int, default=0,
                   help="圖譜擴展跳數（0=不擴展，1=1跳，2=2跳）")
    p.add_argument("--no-rerank", action="store_true",
                   help="停用 reranker 重排序")
    p.add_argument("--agent-id", default="", help="可選 Agent 身份；提供後套用治理 metadata 讀取過濾")
    p.add_argument("--include-private", action="store_true", help="搭配 --agent-id 允許讀取 owner/allow-list 授權的 private 記憶")
    p.add_argument("--max-sensitivity", choices=["", "low", "medium", "high", "restricted"], default="", help="最高可讀敏感度")
    add_temporal_search_arguments(p)
    p.add_argument("--json", action="store_true", help="輸出 JSON")
    p.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    # list
    p = sub.add_parser("list", help="列出知識")
    p.add_argument("--layer", choices=["L0", "L1", "L2", "L3"])
    p.add_argument("--category")
    p.add_argument("--min-trust", type=float, default=0.0)
    p.add_argument("--limit", "-n", type=int, default=50)

    def add_remove_args(ap):
        ap.add_argument("knowledge_id", type=int, help="要刪除的 knowledge ID")
        ap.add_argument("--confirm", action="store_true", help="必要：確認刪除")
        ap.add_argument("--json", action="store_true", help="輸出 JSON")
        ap.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    p = sub.add_parser("remove", help="刪除知識條目（需要 --confirm）")
    add_remove_args(p)
    p = sub.add_parser("delete", help="remove 的別名")
    add_remove_args(p)

    # lint
    p = sub.add_parser("lint", help="健康檢查")

    # doctor
    p = sub.add_parser("doctor", help="環境診斷")

    # stats
    p = sub.add_parser("stats", help="統計")

    # usage — retrieval telemetry and TTL archival
    p = sub.add_parser("usage", help="記憶使用統計與 TTL 歸檔")
    usage_sub = p.add_subparsers(dest="usage_action")
    up = usage_sub.add_parser("stats", help="顯示記憶使用統計")
    up.add_argument("--limit", "-n", type=int, default=10)
    up.add_argument("--json", action="store_true", help="輸出 JSON")
    up.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")
    up = usage_sub.add_parser("archive-expired", help="歸檔 expires_at 已到期的 active 記憶")
    up.add_argument("--limit", "-n", type=int, default=100)
    up.add_argument("--apply", action="store_true", help="實際歸檔；預設只 dry-run")
    up.add_argument("--json", action="store_true", help="輸出 JSON")
    up.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")
    up = usage_sub.add_parser("cold-store-expired", help="摘要並冷存已到期但仍常被使用的記憶")
    up.add_argument("--limit", "-n", type=int, default=100)
    up.add_argument("--min-usage", type=int, default=1, help="最小 access+citation 次數")
    up.add_argument("--summary-max-chars", type=int, default=360, help="摘要最大字元數")
    up.add_argument("--apply", action="store_true", help="實際寫入 summary 並歸檔；預設只 dry-run")
    up.add_argument("--json", action="store_true", help="輸出 JSON")
    up.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    # install-embedding
    p = sub.add_parser("install-embedding", help="安裝嵌入模型")
    p.add_argument("--model", choices=["zh", "en", "mix"], default="mix")

    # update-status — local runtime update and registry status
    p = sub.add_parser("update-status", help="顯示本機 Vault 版本、更新與 Agent registry 狀態")
    p.add_argument("--latest-version", default="", help="手動提供最新版本，用於離線比較")
    p.add_argument("--check-pypi", action="store_true", help="連線 PyPI 查詢最新版本")
    p.add_argument("--read-status", action="store_true", help="讀取既有 ~/.vault-for-llm/update-status.json，不重新計算")
    p.add_argument("--write-status", action="store_true", help="寫入 ~/.vault-for-llm/update-status.json")
    p.add_argument("--doctor", action="store_true", help="檢查共享更新通知是否存在、過期，以及哪些 Agent 需要處理")
    p.add_argument("--max-status-age-minutes", type=int, default=24 * 60, help="doctor 判定 update-status 過期的分鐘數")
    p.add_argument("--agent", default="", help="聚焦特定 Agent/runtime 的啟動檢查")
    p.add_argument("--json", action="store_true", help="輸出 JSON")
    p.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    # agent — local multi-agent registry
    p = sub.add_parser("agent", help="本機多 Agent registry")
    agent_sub = p.add_subparsers(dest="agent_action", help="Agent registry 子命令")

    ap = agent_sub.add_parser("register", help="登記目前 Agent 使用的 Vault project")
    ap.add_argument("--agent", required=True, help="Agent/runtime 名稱，例如 codex/hermes/openclaw")
    ap.add_argument("--agent-project-dir", "--project", dest="agent_project_dir",
                    help="要登記的 Vault project directory；預設自動偵測")
    ap.add_argument("--scope", choices=["shared", "private", "project", "public", "domain", "temporary"],
                    default="shared", help="此 Agent 使用的記憶範圍")
    ap.add_argument("--features", default="core,mcp", help="已啟用功能 CSV")
    ap.add_argument("--tool-profile", choices=["core", "review", "remote", "maintenance", "full"],
                    default="core", help="建議 MCP tool profile")
    ap.add_argument("--memory-layout", choices=["hybrid", "shared", "private"], default="shared",
                    help="登記的記憶庫布局")
    ap.add_argument("--agent-private-dir", help="hybrid/private layout 的 Agent 私有 vault 目錄")
    ap.add_argument("--source", default="manual", help="登記來源，例如 manual/setup-agent")
    ap.add_argument("--json", action="store_true", help="輸出 JSON")
    ap.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    ap = agent_sub.add_parser("list", help="列出本機已登記 Agent")
    ap.add_argument("--json", action="store_true", help="輸出 JSON")
    ap.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    ap = agent_sub.add_parser("status", help="顯示 Agent registry 與更新狀態")
    ap.add_argument("--latest-version", default="", help="手動提供最新版本，用於離線比較")
    ap.add_argument("--check-pypi", action="store_true", help="連線 PyPI 查詢最新版本")
    ap.add_argument("--read-status", action="store_true", help="讀取既有 ~/.vault-for-llm/update-status.json，不重新計算")
    ap.add_argument("--write-status", action="store_true", help="寫入 ~/.vault-for-llm/update-status.json")
    ap.add_argument("--doctor", action="store_true", help="檢查共享更新通知是否存在、過期，以及哪些 Agent 需要處理")
    ap.add_argument("--max-status-age-minutes", type=int, default=24 * 60, help="doctor 判定 update-status 過期的分鐘數")
    ap.add_argument("--agent", default="", help="聚焦特定 Agent/runtime 的啟動檢查")
    ap.add_argument("--json", action="store_true", help="輸出 JSON")
    ap.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    ap = agent_sub.add_parser("doctor", help="檢查共享更新通知是否能讓所有 Agent 收到最新狀態")
    ap.add_argument("--max-status-age-minutes", type=int, default=24 * 60, help="判定 update-status 過期的分鐘數")
    ap.add_argument("--json", action="store_true", help="輸出 JSON")
    ap.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    ap = agent_sub.add_parser("install-runtime-template", help="安全套用 setup-agent 產生的 runtime 啟動模板")
    ap.add_argument("--runtime", required=True, choices=["codex", "claude-code", "openclaw", "hermes"],
                    help="要套用的 runtime 模板")
    ap.add_argument("--target", required=True, help="要寫入的啟動檔，例如 AGENTS.md 或 CLAUDE.md")
    ap.add_argument("--template-dir", help="setup-agent 產生的 agent-install 目錄；預設 project/agent-install")
    ap.add_argument("--apply", action="store_true", help="實際寫入；預設只做 dry-run preview")
    ap.add_argument("--no-backup", action="store_true", help="寫入既有檔案時不要產生 .bak 備份")
    ap.add_argument("--json", action="store_true", help="輸出 JSON")
    ap.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    ap = agent_sub.add_parser("startup-doctor", help="檢查 setup-agent 產生的啟動契約是否為最新版")
    ap.add_argument("--template-dir", help="setup-agent 產生的 agent-install 目錄；預設 project/agent-install")
    ap.add_argument("--json", action="store_true", help="輸出 JSON")
    ap.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    def add_agent_setup_args(ap):
        ap.add_argument("--agent", default="generic", help="Agent/runtime 名稱，例如 hermes/openclaw/codex/n8n")
        ap.add_argument("--scope", choices=["shared", "private", "domain", "temporary"], help="Vault 資料庫範圍")
        ap.add_argument("--agent-project-dir", "--project", dest="agent_project_dir",
                        help="要初始化/使用的 Vault project directory")
        ap.add_argument("--features", default=None,
                        help="可選功能 CSV，例如 core,mcp,obsidian_import,semantic,supabase,headroom,memory_agents")
        ap.add_argument("--language", choices=["en", "zh-Hant", "zh-CN"], default=None,
                        help="互動式安裝與產生文件的語言；非互動模式預設 en")
        ap.add_argument("--tool-profile", choices=["core", "review", "remote", "maintenance", "full"],
                        default="core", help="建議的 MCP tool profile")
        ap.add_argument("--memory-layout", choices=["hybrid", "shared", "private"], default="hybrid",
                        help="記憶庫布局：hybrid=shared project vault + private Agent vault")
        ap.add_argument("--agent-private-dir",
                        help="hybrid/private layout 使用的 Agent 私有 vault 目錄")
        ap.add_argument("--install-optional-deps", action="store_true",
                        help="立即安裝已選功能需要的 Python optional dependencies")
        ap.add_argument("--install-embedding-model", choices=["zh", "en", "mix"],
                        help="semantic feature 啟用時，下載並設定本地 ONNX embedding model")
        ap.add_argument("--obsidian-vault", help="既有 Obsidian vault 路徑；提供後會先 dry-run")
        ap.add_argument("--import-obsidian", action="store_true",
                        help="dry-run 後執行第一次 Obsidian 匯入並 compile")
        ap.add_argument("--obsidian-sync", choices=["none", "cron", "launchagent", "n8n", "all"],
                        default="none", help="產生後續自動同步模板")
        ap.add_argument("--sync-interval-minutes", type=int, default=15,
                        help="同步模板排程間隔分鐘數")
        ap.add_argument("--supabase-sync", choices=["none", "cron", "launchagent", "n8n", "all"],
                        default="none", help="產生每日 Supabase sync 模板")
        ap.add_argument("--supabase-setup", choices=["none", "simple", "advanced"],
                        default=None, help="產生 Supabase 連線導覽文件；非互動模式預設 simple")
        ap.add_argument("--supabase-sync-interval-minutes", type=int, default=1440,
                        help="Supabase sync LaunchAgent/n8n 排程間隔分鐘數（預設每日）")
        ap.add_argument("--remote-reader", choices=["none", "shell", "n8n", "coze", "all"],
                        default="none", help="產生 Supabase remote reader 範本給 shell/n8n/Coze")
        ap.add_argument("--remote-reader-query", default="deployment SOP",
                        help="remote reader smoke/template 使用的示範查詢")
        ap.add_argument("--agent-roster",
                        help="產生多 Agent roster/access matrix；role: work/profile/care/dream/remote/automation/observer")
        ap.add_argument("--validation-pack", choices=["none", "remote", "n8n", "coze", "all"],
                        default="none", help="產生 Supabase/n8n/Coze live validation pack")
        ap.add_argument("--automation-schedule", choices=["none", "cron", "launchagent", "n8n", "all"],
                        default="none", help="產生 memory automation cron/LaunchAgent/n8n 排程模板")
        ap.add_argument("--automation-interval-minutes", type=int, default=1440,
                        help="memory automation LaunchAgent/n8n 排程間隔分鐘數；cron 預設每日")
        ap.add_argument("--automation-mode", choices=["conservative", "balanced", "autonomous"],
                        default="balanced", help="memory automation policy mode")
        ap.add_argument("--automation-command", choices=["cycle", "run"],
                        default="cycle", help="排程使用 cycle 或 run；cycle 會先寫 learning policy 再整理")
        ap.add_argument("--automation-apply", action="store_true",
                        help="讓排程模板加入 --apply；只執行 policy 允許的可逆操作")
        ap.add_argument("--automation-write-workspace", action="store_true",
                        help="讓 cycle 排程寫出 reports/automation/cycle-latest.json 每日工作台")
        ap.add_argument("--automation-workspace-inbox-limit", type=int, default=5,
                        help="cycle workspace 內最多列出的候選審核項目數（預設 5，上限 50）")
        ap.add_argument("--automation-include-transcripts", action="store_true",
                        help="讓排程 handoff opt-in 加入未 capture transcript 的 metadata-only 候選清單")
        ap.add_argument("--automation-transcript-limit", type=int, default=5,
                        help="排程 handoff 最多列出的 transcript 候選數（預設 5，上限 20）")
        ap.add_argument("--automation-capture-transcripts", action="store_true",
                        help="讓 cycle 排程在 --automation-apply 時把 discovered transcripts 寫成候選記憶")
        ap.add_argument("--automation-capture-transcript-limit", type=int, default=3,
                        help="排程最多自動 capture 的 transcript 數（預設 3，上限 20）")
        ap.add_argument("--automation-auto-promote-low-risk", action="store_true",
                        help="寫入 policy，允許 --automation-apply 只提升低風險 session_capture/session_lesson 候選")
        ap.add_argument("--stable-venv",
                        help="產生穩定 Python virtualenv bootstrap 腳本，建議 ~/.hermes/venvs/vault-for-llm")
        ap.add_argument("--write-stable-venv-script", action="store_true",
                        help="用預設穩定 venv 路徑產生 setup-stable-venv.sh")
        ap.add_argument("--template-dir", help="同步模板輸出目錄；預設 project/agent-install")
        ap.add_argument("--allow-private", action="store_true",
                        help="允許 Obsidian 匯入含 secret-like pattern 的本機私人資料")
        ap.add_argument("--non-interactive", action="store_true", help="不要詢問，使用參數/defaults")
        ap.add_argument("--json", action="store_true", help="輸出 JSON")
        ap.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    # setup-agent / install-agent
    p = sub.add_parser("setup-agent", help="互動式 Agent 安裝精靈")
    add_agent_setup_args(p)
    p = sub.add_parser("install-agent", help="setup-agent 的別名")
    add_agent_setup_args(p)

    # import
    p = sub.add_parser("import", help="匯入長文件、OKF bundle，或從 Obsidian 同步 notes")
    p.add_argument("file", help="檔案路徑 (.md, .txt)，或使用 obsidian 搭配 --vault，或 okf 搭配 --bundle")
    p.add_argument("--title", "-t", help="文件標題（預設用檔名）")
    p.add_argument("--strategy", "-s", choices=["chapter", "semantic", "summary-guided", "sliding", "proposition"], default="chapter", help="分塊策略（預設: chapter，proposition 需要 Ollama）")
    p.add_argument("--layer", choices=["L0", "L1", "L2", "L3"], default="L3")
    p.add_argument("--category", default="general")
    p.add_argument("--tags", default="")
    p.add_argument("--trust", type=float, default=0.5)
    p.add_argument("--chunk-size", type=int, default=500, help="滑動視窗塊大小")
    p.add_argument("--overlap", type=int, default=100, help="滑動視窗重疊")
    p.add_argument("--no-embed", action="store_true", help="跳過嵌入生成")
    p.add_argument("--contextualize", action="store_true", help="Contextual Retrieval：用 Ollama 生成上下文摘要（Anthropic 2024）")
    p.add_argument("--ollama-model", default="qwen3:8b", help="Ollama 模型（用於 contextualize）")
    p.add_argument("--allow-private", action="store_true", help="允許含秘密模式的文件直接匯入本機 vault")
    p.add_argument("--bundle", help="OKF bundle 目錄；僅用於 `vault import okf`")
    p.add_argument("--reason", default="", help="OKF 匯入候選的審核理由；僅用於 `vault import okf`")
    p.add_argument("--limit", type=int, default=None, help="OKF 匯入候選數上限；僅用於 `vault import okf`")
    p.add_argument("--max-file-bytes", type=int, default=2_000_000, help="OKF 每個 Markdown 檔案大小上限")
    p.add_argument("--vault", help="Obsidian vault 目錄；僅用於 `vault import obsidian`")
    p.add_argument("--obsidian-raw-subdir", default="obsidian", help="Obsidian notes 寫入 raw/ 下的子目錄")
    p.add_argument("--exclude", action="append", default=[], help="Obsidian 匯入時額外忽略的目錄或檔名，可重複")
    p.add_argument("--dry-run", action="store_true", help="Obsidian 匯入時只列出新增/更新，不寫入")
    p.add_argument("--compile", action="store_true", help="Obsidian 匯入完成後立刻執行 vault compile")
    p.add_argument("--json", action="store_true", help="輸出 JSON；OKF 匯入支援")
    p.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出；OKF 匯入支援")
    add_governance_args(p)

    # export — read-only export targets
    p = sub.add_parser("export", help="匯出知識（單向、唯讀）")
    export_sub = p.add_subparsers(dest="export_target", help="匯出目標")

    ep = export_sub.add_parser("obsidian", help="匯出 Markdown notes 到 Obsidian vault")
    ep.add_argument("--vault", required=True, help="Obsidian vault 目錄")
    ep.add_argument("--category", help="只匯出指定 category")
    ep.add_argument("--tag", help="只匯出含指定 tag 的條目")
    ep.add_argument("--layer", choices=["L0", "L1", "L2", "L3"], help="只匯出指定 layer")
    ep.add_argument("--limit", type=int, help="最多匯出幾條")
    ep.add_argument("--min-trust", type=float, default=0.0, help="最低 trust 門檻")
    ep.add_argument("--source", choices=["db", "raw", "compiled"], default="db", help="來源（MVP 支援 db）")
    ep.add_argument("--dry-run", action="store_true", help="只列出將寫入的檔案，不建立檔案")

    ep = export_sub.add_parser("okf", help="匯出 OKF-style Markdown knowledge bundle")
    ep.add_argument("--bundle", required=True, help="OKF bundle 輸出目錄")
    ep.add_argument("--category", help="只匯出指定 category")
    ep.add_argument("--tag", help="只匯出含指定 tag 的條目")
    ep.add_argument("--layer", choices=["L0", "L1", "L2", "L3"], help="只匯出指定 layer")
    ep.add_argument("--limit", type=int, help="最多匯出幾條")
    ep.add_argument("--min-trust", type=float, default=0.0, help="最低 trust 門檻")
    ep.add_argument("--include-private", action="store_true", help="包含 scope=private；預設排除")
    ep.add_argument("--include-restricted", action="store_true", help="包含 sensitivity=restricted；預設排除")
    ep.add_argument("--dry-run", action="store_true", help="只列出將寫入的檔案，不建立檔案")
    ep.add_argument("--json", action="store_true", help="輸出 JSON")
    ep.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    # config
    p = sub.add_parser("config", help="配置管理")
    p.add_argument("config_action", choices=["set", "get", "list"])
    p.add_argument("config_args", nargs="*")

    # db — explicit SQLite schema status/migration/backup workflow
    p = sub.add_parser("db", help="SQLite schema status/migration/backup")
    db_sub = p.add_subparsers(dest="db_action", help="DB 子命令")

    dp = db_sub.add_parser("status", help="顯示 schema 狀態")
    dp.add_argument("--db-path", help="SQLite DB 路徑（預設 project_dir/vault.db）")
    dp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    dp = db_sub.add_parser("migrate", help="執行 idempotent schema migration")
    dp.add_argument("--db-path", help="SQLite DB 路徑（預設 project_dir/vault.db）")
    dp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    dp = db_sub.add_parser("backup", help="建立一致的 SQLite 備份")
    dp.add_argument("--db-path", help="SQLite DB 路徑（預設 project_dir/vault.db）")
    dp.add_argument("--output", help="備份輸出路徑（預設 db 旁 backups/vault-*.db）")
    dp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")
    dp.add_argument("--verify", action="store_true", help="備份後執行 integrity/schema/table-count 驗證")

    dp = db_sub.add_parser("verify-backup", help="驗證 SQLite 備份檔")
    dp.add_argument("backup_path", help="備份 DB 路徑")
    dp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    dp = db_sub.add_parser("restore", help="從已驗證的備份還原 SQLite DB")
    dp.add_argument("backup_path", help="備份 DB 路徑")
    dp.add_argument("--db-path", help="SQLite DB 路徑（預設 project_dir/vault.db）")
    dp.add_argument("--force", action="store_true", help="允許覆蓋既有 DB；覆蓋前會自動備份")
    dp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    # map — Document Map read-only navigation + backfill
    p = sub.add_parser("map", help="Document Map 操作")
    map_sub = p.add_subparsers(dest="map_action", help="Document Map 子命令")

    mp = map_sub.add_parser("build", help="建立/回填 Document Map")
    mp.add_argument("knowledge_id", nargs="?", type=int, help="知識 ID；省略時回填全部")

    mp = map_sub.add_parser("show", help="顯示知識條目的章節地圖")
    mp.add_argument("knowledge_id", type=int, help="知識 ID")

    mp = map_sub.add_parser("read", help="讀取知識條目的指定行號範圍")
    mp.add_argument("knowledge_id", type=int, help="知識 ID")
    mp.add_argument("--lines", required=True, help="行號範圍，例如 1-40")

    mp = map_sub.add_parser("query", help="搜尋 Document Map claims")
    mp.add_argument("query", help="查詢文字")
    mp.add_argument("--limit", "-n", type=_positive_int, default=10)

    # remote — optional Supabase read-only navigation
    p = sub.add_parser("remote", help="Supabase 遠端唯讀搜尋與 bounded read")
    remote_sub = p.add_subparsers(dest="remote_action", help="Remote 子命令")

    def add_remote_output_args(rp):
        rp.add_argument("--json", action="store_true", help="輸出 JSON")
        rp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    rp = remote_sub.add_parser("search", help="透過 Supabase vault_search_readable RPC 搜尋")
    rp.add_argument("query", nargs="?", default="", help="搜尋文字；省略時回傳最新可讀記憶")
    rp.add_argument("--agent-id", default="", help="Agent 身份，用於 owner/allowed_agents 過濾")
    rp.add_argument("--include-private", action="store_true", help="允許讀取此 agent 被授權的 private 記憶")
    rp.add_argument("--max-sensitivity", choices=["low", "medium", "high", "restricted"], default="medium")
    rp.add_argument("--limit", "-n", type=_positive_int, default=10)
    rp.add_argument("--compact", action=argparse.BooleanOptionalAction, default=True, help="回傳精簡欄位")
    add_remote_output_args(rp)

    rp = remote_sub.add_parser("map", help="讀取 Supabase 同步的 Document Map")
    rp.add_argument("knowledge_id", help="遠端知識 ID；可為正整數或 Supabase UUID")
    rp.add_argument("--compact", action=argparse.BooleanOptionalAction, default=False, help="回傳精簡節點欄位")
    rp.add_argument("--agent-id", default="", help="Agent 身份，用於 owner/allowed_agents 過濾")
    rp.add_argument("--include-private", action="store_true", help="允許讀取此 agent 被授權的 private 記憶")
    rp.add_argument("--max-sensitivity", choices=["low", "medium", "high", "restricted"], default="medium")
    add_remote_output_args(rp)

    rp = remote_sub.add_parser("read", help="讀取 Supabase 同步的 bounded range")
    rp.add_argument("knowledge_id", help="遠端知識 ID；可為正整數或 Supabase UUID")
    rp.add_argument("--node-uid", default="", help="Document Map node_uid；可單獨指定")
    rp.add_argument("--lines", help="行號範圍，例如 1-40")
    rp.add_argument("--max-lines", type=_positive_int, default=80, help="最大讀取行數")
    rp.add_argument("--agent-id", default="", help="Agent 身份，用於 owner/allowed_agents 過濾")
    rp.add_argument("--include-private", action="store_true", help="允許讀取此 agent 被授權的 private 記憶")
    rp.add_argument("--max-sensitivity", choices=["low", "medium", "high", "restricted"], default="medium")
    add_remote_output_args(rp)

    rp = remote_sub.add_parser("smoke", help="檢查 Supabase remote reader RPC 是否可用")
    rp.add_argument("--query", default="deployment SOP", help="測試查詢文字")
    rp.add_argument("--agent-id", default="", help="Agent 身份，用於 owner/allowed_agents 過濾")
    rp.add_argument("--include-private", action="store_true", help="允許讀取此 agent 被授權的 private 記憶")
    rp.add_argument("--max-sensitivity", choices=["low", "medium", "high", "restricted"], default="medium")
    rp.add_argument("--limit", "-n", type=_positive_int, default=3)
    add_remote_output_args(rp)

    rp = remote_sub.add_parser("doctor", help="診斷 Supabase remote reader search/map/read 閉環")
    rp.add_argument("--query", default="deployment SOP", help="測試查詢文字")
    rp.add_argument("--agent-id", default="", help="Agent 身份，用於 owner/allowed_agents 過濾")
    rp.add_argument("--include-private", action="store_true", help="允許讀取此 agent 被授權的 private 記憶")
    rp.add_argument("--max-sensitivity", choices=["low", "medium", "high", "restricted"], default="medium")
    rp.add_argument("--limit", "-n", type=_positive_int, default=3)
    add_remote_output_args(rp)

    # skill — 本機跨 Agent 技能登錄（實驗性）
    p = sub.add_parser("skill", help="本機技能登錄（實驗性）")
    skill_sub = p.add_subparsers(dest="skill_action", help="技能子命令")

    sp = skill_sub.add_parser("push", help="註冊技能到本機登錄")
    sp.add_argument("--file", "-f", help="SKILL.md 路徑（預設讀 stdin）")
    sp.add_argument("--name", help="技能名稱（預設從 frontmatter 讀取）")
    sp.add_argument("--version", default="1.0.0", help="版本號")
    sp.add_argument("--agent", default="vault-cli", help="來源 Agent")
    sp.add_argument("--category", default="general", help="分類")
    sp.add_argument("--capabilities", default="", help="能力標籤（逗號分隔）")
    sp.add_argument("--dependencies", default="", help="依賴（逗號分隔）")
    sp.add_argument("--trust", type=float, default=0.5, help="信任分數")
    sp.add_argument("--description", default="", help="簡短描述")
    sp.add_argument("--force", action="store_true", help="同名技能時強制覆蓋")

    sp = skill_sub.add_parser("search", help="搜尋本機登錄技能")
    sp.add_argument("query", nargs="?", default="", help="搜尋關鍵字")
    sp.add_argument("--capabilities", help="依能力過濾")
    sp.add_argument("--category", help="依分類過濾")
    sp.add_argument("--agent", help="依來源 Agent 過濾")
    sp.add_argument("--min-trust", type=float, default=0.0)
    sp.add_argument("--limit", "-n", type=int, default=20)

    sp = skill_sub.add_parser("pull", help="從本機登錄下載技能")
    sp.add_argument("name", help="技能名稱")

    sp = skill_sub.add_parser("list", help="列出本機登錄技能")
    sp.add_argument("--agent", help="依來源過濾")
    sp.add_argument("--category", help="依分類過濾")
    sp.add_argument("--min-trust", type=float, default=0.0)
    sp.add_argument("--limit", "-n", type=int, default=100)

    sp = skill_sub.add_parser("stats", help="本機技能登錄統計")

    # graph
    p = sub.add_parser("graph", help="圖譜操作")
    graph_sub = p.add_subparsers(dest="graph_action", help="圖譜子命令")

    g = graph_sub.add_parser("build", help="自動推斷圖譜")
    g.add_argument("--clear", action="store_true", help="先清除舊的自動推斷")

    g = graph_sub.add_parser("show", help="顯示圖譜摘要")

    g = graph_sub.add_parser("export", help="匯出圖譜")
    g.add_argument("--format", "-f", choices=["mermaid", "dot"], default="mermaid")
    g.add_argument("--node-id", "-n", type=int, help="指定起點節點（預設全部）")
    g.add_argument("--depth", "-d", type=int, default=2, help="擴展深度")
    g.add_argument("--output", "-o", help="輸出檔案路徑")

    g = graph_sub.add_parser("link", help="手動建立關聯")
    g.add_argument("source_id", type=int, help="來源知識 ID")
    g.add_argument("target_id", type=int, help="目標知識 ID")
    g.add_argument("--relation", "-r", default="related_to", help="關係類型")
    g.add_argument("--weight", "-w", type=float, default=1.0, help="權重")

    g = graph_sub.add_parser("unlink", help="刪除關聯")
    g.add_argument("edge_id", type=int, help="邊 ID")

    g = graph_sub.add_parser("clear", help="清除自動推斷的邊")

    g = graph_sub.add_parser("expand", help="從節點擴展")
    g.add_argument("node_id", type=int, help="起始節點 ID")
    g.add_argument("--depth", "-d", type=int, default=2, help="擴展深度")


    # converge — self-questioning convergence check
    p = sub.add_parser("converge", help="收斂檢查 — 自問知識是否充足")
    p.add_argument("--apply", action="store_true", help="實際更新資料庫（預設為預覽模式）")
    p.add_argument("--limit", type=int, default=0, help="最多檢查幾條（0=全部）")
    p.add_argument("--min-trust", type=float, default=1.0, help="只檢查 trust 低於此值的條目")
    p.add_argument("--ollama", type=str, default="", help="使用 ollama 模型評分（如 qwen3）")
    p.add_argument("--api", type=str, default="", help="使用 OpenAI 相容 API 評分")
    p.add_argument("--api-key", type=str, default="", help="API key（如需要）")

    # cross-validate — asymmetric LLM verification
    p = sub.add_parser("cross-validate", help="跨模型不對稱驗證")
    p.add_argument("--apply", action="store_true", help="實際更新 DB（預設為預覽模式）")
    p.add_argument("--limit", type=int, default=0, help="最多驗證幾條（0=全部）")
    p.add_argument("--min-trust", type=float, default=0.8, help="只驗證 trust 低於此值的條目")
    p.add_argument("--local-only", action="store_true", help="只用本地模型（不用雲端）")
    p.add_argument("--local-model", type=str, default="qwen3-8b", help="本地模型名稱")
    p.add_argument("--cloud-model", type=str, default="glm-5.1", help="雲端模型名稱")

    # freshness — staleness tracking and review scheduling
    p = sub.add_parser("freshness", help="知識新鮮度追蹤與審查排程")
    p.add_argument("--apply", action="store_true", help="實際更新 DB（預設為預覽模式）")
    p.add_argument("--limit", type=int, default=0, help="最多處理幾條（0=全部）")
    p.add_argument("--stale-only", action="store_true", help="只顯示過期條目")

    # dream — deterministic report-first curation
    p = sub.add_parser("dream", help="Dream 記憶整理報告（預設 report-only）")
    p.add_argument("--mode", choices=["report", "apply_safe"], default="report")
    p.add_argument("--checks", nargs="*", choices=["freshness", "dedup", "convergence", "metadata", "orphans"],
                   help="要執行的檢查；預設全部")
    p.add_argument("--limit", "-n", type=int, default=50)
    p.add_argument("--write-report", action="store_true", help="寫入 reports/dream/*.md")
    p.add_argument("--write-candidates", action="store_true", help="將 Dream 建議寫入候選記憶佇列；不會自動 promote")
    p.add_argument("--no-backup", action="store_true", help="apply_safe 時不建立 DB backup")
    p.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    # dedup — semantic duplicate detection and merge
    p = sub.add_parser("dedup", help="語意去重 — 檢測與合併重複知識")
    p.add_argument("--merge", action="store_true", help="實際合併（預設為預覽模式）")
    p.add_argument("--dry-run", action="store_true", help="預覽合併計劃（不修改資料庫）")
    p.add_argument("--threshold", type=float, default=0.85, help="相似度閾值（預設 0.85）")

    # search-qa — deterministic local search quality snapshots
    p = sub.add_parser("search-qa", help="搜尋品質 QA 評估與 before/after 比較")
    qa_sub = p.add_subparsers(dest="search_qa_action", help="Search QA 子命令")

    qp = qa_sub.add_parser("run", help="執行 Search QA Set 並輸出 snapshot JSON")
    qp.add_argument("--qa-file", required=True, help="Search QA Set JSON 路徑")
    qp.add_argument("--output", "-o", help="snapshot JSON 輸出路徑")
    qp.add_argument("--mode", choices=["auto", "keyword", "vector", "semantic", "hybrid"], default="keyword")
    qp.add_argument("--limit", "-n", type=int, default=10)
    qp.add_argument("--min-score", type=float, default=None,
                    help="minimum keyword match score before counting weak/no-result matches")
    qp.add_argument("--db-path", help="SQLite DB 路徑（預設 project_dir/vault.db）")
    qp.add_argument("--semantic-vector-kind", choices=["claim", "node"], default="claim",
                    help="stored semantic_vectors kind for semantic/hybrid QA")
    qp.add_argument("--allow-hash", action="store_true", help="明確允許測試用 deterministic hash provider")
    qp.add_argument("--hash-dim", type=int, default=32, help="hash provider 維度（僅 --allow-hash）")

    qp = qa_sub.add_parser("compare", help="比較兩個 Search QA snapshot JSON")
    qp.add_argument("--before", required=True, help="before snapshot JSON")
    qp.add_argument("--after", required=True, help="after snapshot JSON")
    qp.add_argument("--output", "-o", help="comparison JSON 輸出路徑")

    # semantic — operator semantic-index workflows
    p = sub.add_parser("semantic", help="語意索引工作流程（rebuild/warm/smoke）")
    semantic_sub = p.add_subparsers(dest="semantic_action", help="Semantic workflow 子命令")

    def add_semantic_common(sp):
        sp.add_argument("--db-path", help="SQLite DB 路徑（預設 project_dir/vault.db）")
        sp.add_argument("--allow-hash", action="store_true", help="明確允許測試用 deterministic hash provider")
        sp.add_argument("--hash-dim", type=int, default=32, help="hash provider 維度（僅 --allow-hash）")
        sp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    def add_cache_filters(sp):
        sp.add_argument("--provider-id", help="只處理指定 embedding provider")
        sp.add_argument("--dimension", type=int, help="只處理指定 embedding 維度")
        sp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")
        sp.add_argument("--db-path", help="SQLite DB 路徑（預設 project_dir/vault.db）")

    sp = semantic_sub.add_parser("rebuild", help="重建 semantic_vectors")
    add_semantic_common(sp)
    sp.add_argument("--knowledge-id", type=int, help="只重建指定 knowledge id")
    sp.add_argument("--changed-only", action="store_true", help="只重建缺失或已過期的 semantic vectors")
    sp.add_argument("--limit", "-n", type=int, help="最多重建幾筆 changed knowledge rows")
    sp.add_argument("--persist-cache", action="store_true", help="使用 durable embedding_cache 快取")

    sp = semantic_sub.add_parser("warm", help="預熱 QA 查詢 embedding cache（不寫入向量列）")
    add_semantic_common(sp)
    sp.add_argument("--qa-file", required=True, help="Search QA Set JSON 路徑")
    sp.add_argument("--persist-cache", action="store_true", help="使用 durable embedding_cache 快取")

    sp = semantic_sub.add_parser("smoke", help="重建、預熱並執行 Search QA smoke snapshot")
    add_semantic_common(sp)
    sp.add_argument("--qa-file", required=True, help="Search QA Set JSON 路徑")
    sp.add_argument("--knowledge-id", type=int, help="只重建指定 knowledge id")
    sp.add_argument("--changed-only", action="store_true", help="只重建缺失或已過期的 semantic vectors")
    sp.add_argument("--semantic-limit", type=int, help="最多重建幾筆 changed knowledge rows")
    sp.add_argument("--mode", choices=["auto", "keyword", "vector", "semantic", "hybrid"], default="keyword")
    sp.add_argument("--semantic-vector-kind", choices=["claim", "node"], default="claim",
                    help="stored semantic_vectors kind for semantic/hybrid smoke")
    sp.add_argument("--limit", "-n", type=int, default=10)
    sp.add_argument("--output", "-o", help="combined semantic workflow JSON 輸出路徑")
    sp.add_argument("--persist-cache", action="store_true", help="使用 durable embedding_cache 快取")

    sp = semantic_sub.add_parser("cache-stats", help="顯示 durable embedding cache 統計")
    add_cache_filters(sp)

    sp = semantic_sub.add_parser("cache-prune", help="清理 durable embedding cache")
    add_cache_filters(sp)
    sp.add_argument("--older-than-days", type=int, help="刪除 last_used_at 早於 N 天的列")
    sp.add_argument("--max-rows", type=int, help="保留最新 N 列，其餘刪除")

    def add_semantic_lifecycle(sp):
        sp.add_argument("--qa-file", help="Search QA Set JSON 路徑（用於 warm/smoke）")
        sp.add_argument("--allow-hash", action="store_true", help="明確允許測試用 deterministic hash provider")
        sp.add_argument("--hash-dim", type=int, default=32, help="hash provider 維度（僅 --allow-hash）")
        sp.add_argument("--db-path", help="SQLite DB 路徑（預設 project_dir/vault.db）")
        sp.add_argument("--no-persist-cache", action="store_true", help="停用預設 durable embedding cache")
        sp.add_argument("--rebuild", action="store_true", help="在啟動流程中重建 semantic_vectors")
        sp.add_argument("--changed-only", action="store_true", help="搭配 --rebuild，只重建缺失或已過期的 semantic vectors")
        sp.add_argument("--semantic-limit", type=int, help="搭配 --rebuild，最多重建幾筆 changed knowledge rows")
        sp.add_argument("--smoke", action="store_true", help="若提供 --qa-file，執行 Search QA smoke aggregate")
        sp.add_argument("--mode", choices=["auto", "keyword", "vector", "semantic", "hybrid"], default="keyword")
        sp.add_argument("--semantic-vector-kind", choices=["claim", "node"], default="claim",
                        help="stored semantic_vectors kind for semantic/hybrid smoke")
        sp.add_argument("--limit", "-n", type=int, default=10)
        sp.add_argument("--older-than-days", type=int, help="啟動流程結尾清理早於 N 天的 cache rows")
        sp.add_argument("--max-rows", type=int, help="啟動流程結尾最多保留 N 個 cache rows")
        sp.add_argument("--output", "-o", help="JSON 輸出檔案路徑")
        sp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    sp = semantic_sub.add_parser("startup", help="執行一次 importable semantic startup hook")
    add_semantic_lifecycle(sp)

    sp = semantic_sub.add_parser("daemon", help="執行 bounded semantic warm daemon（預設 repeat=1）")
    add_semantic_lifecycle(sp)
    sp.add_argument("--repeat", type=int, default=1, help="迭代次數；0=forever（只限 supervisor 管理）")
    sp.add_argument("--interval", type=float, default=60.0, help="迭代間隔秒數；測試可用 0")

    # automation — policy-based memory maintenance
    from vault.cli_automation import add_automation_parser
    from vault.cli_memory import add_memory_parser

    add_automation_parser(sub)
    add_memory_parser(sub)
    add_okf_parser(sub)
    args = parser.parse_args(normalized_argv)

    previous_project_dir_override = get_project_dir_override()
    if explicit_project_dir:
        if args.command == "init":
            args.project_dir = explicit_project_dir
        elif args.command in {"setup-agent", "install-agent"}:
            args.agent_project_dir = explicit_project_dir
        else:
            project_dir = Path(explicit_project_dir).expanduser().resolve()
            os.chdir(project_dir)
            set_project_dir_override(project_dir)

    commands = {
        "init": cmd_init,
        "add": cmd_add,
        "remember": cmd_remember,
        "promote": cmd_promote,
        "candidate-review": cmd_candidate_review,
        "candidates": cmd_candidates,
        "capture": cmd_capture,
        "compile": cmd_compile,
        "search": cmd_search,
        "list": cmd_list,
        "remove": cmd_remove,
        "delete": cmd_remove,
        "lint": cmd_lint,
        "doctor": cmd_doctor,
        "stats": cmd_stats,
        "usage": cmd_usage,
        "automation": cmd_automation,
        "memory": lambda parsed: __import__("vault.cli_memory", fromlist=["cmd_memory"]).cmd_memory(parsed, find_project_dir=find_project_dir, json_print=_json_print),
        "install-embedding": cmd_install_embedding,
        "update-status": cmd_update_status,
        "agent": cmd_agent,
        "setup-agent": cmd_setup_agent,
        "install-agent": cmd_setup_agent,
        "import": cmd_import,
        "export": cmd_export,
        "config": cmd_config,
        "db": cmd_db,
        "map": cmd_map,
        "remote": cmd_remote,
        "graph": cmd_graph,
        "skill": cmd_skill,
        "converge": cmd_converge,
        "cross-validate": cmd_cross_validate,
        "freshness": cmd_freshness,
        "dream": cmd_dream,
        "dedup": cmd_dedup,
        "search-qa": cmd_search_qa,
        "semantic": cmd_semantic,
        "okf": cmd_okf,
        "gui": cmd_gui,
    }

    try:
        if args.command in commands:
            commands[args.command](args)
        else:
            parser.print_help()
    finally:
        set_project_dir_override(previous_project_dir_override)


if __name__ == "__main__":
    main()
