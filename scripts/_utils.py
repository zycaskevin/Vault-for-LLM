"""
scripts/_utils.py — Vault-for-LLM 共用工具

所有 scripts 應使用此模組的 find_db_path() 來定位 guardrails.db，
避免各自用 os.path.dirname(__file__) 造成找錯目錄的問題。
"""

from __future__ import annotations
import os
from pathlib import Path


def find_db_path(explicit_path: str | None = None) -> Path:
    """
    搜尋 guardrails.db，依優先度：

    1. 明確指定的路徑（explicit_path 參數 / CLI --db 引數）
    2. 環境變數 VAULT_PATH 或 GUARDRAILS_PATH
    3. 從 cwd 往上找含有 guardrails.db 的目錄
    4. fallback：cwd/guardrails.db（讓呼叫端自行處理不存在的情況）

    範例：
        db_path = find_db_path(args.db)
        db = GuardrailsDB(str(db_path))
    """
    # 1. 明確指定
    if explicit_path:
        return Path(explicit_path)

    # 2. 環境變數（支援兩個名稱，向後相容）
    for env_key in ("VAULT_PATH", "GUARDRAILS_PATH"):
        env = os.environ.get(env_key)
        if env:
            p = Path(env)
            return p if p.suffix == ".db" else p / "guardrails.db"

    # 3. 從 cwd 往上搜尋
    cwd = Path.cwd()
    for d in [cwd] + list(cwd.parents):
        candidate = d / "guardrails.db"
        if candidate.exists():
            return candidate

    # 4. fallback：cwd 下
    return cwd / "guardrails.db"


def find_project_dir(explicit_path: str | None = None) -> Path:
    """回傳含有 guardrails.db 的專案根目錄（find_db_path 的目錄版）。"""
    return find_db_path(explicit_path).parent


def load_dotenv_cascade(*paths: str) -> None:
    """
    按優先度載入 .env，第一個存在的為準。
    預設搜尋：專案根目錄 → 使用者家目錄
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return  # python-dotenv 非必要，跳過

    search_paths = list(paths) if paths else []
    # 自動加入專案根目錄 .env
    project_env = find_project_dir() / ".env"
    search_paths.append(str(project_env))
    # 家目錄 .env 作為 fallback（跨平台相容）
    home_dir = os.environ.get("HOME") or os.environ.get("USERPROFILE") or os.path.expanduser("~")
    search_paths.append(os.path.join(home_dir, ".env"))

    for p in search_paths:
        if Path(p).exists():
            load_dotenv(p, override=False)
            break
