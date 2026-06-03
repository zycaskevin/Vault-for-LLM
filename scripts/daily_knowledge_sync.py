#!/usr/bin/env python3
"""
Vault-for-LLM 每日知識同步 — 整合所有同步步驟的入口腳本。

流程：
1. 從 GitHub 拉取最新 raw/ 知識
2. vault compile（raw/ → DB + compiled/）
3. 本地 DB 去重掃描
4. Trust 動態調整
5. 知識缺口偵測
6. 審核佇列摘要

環境變數設定：
  VAULT_DIR    — 專案根目錄（含 vault.db）。不設定則自動從 cwd 往上搜尋。

用法：
  python3 scripts/daily_knowledge_sync.py
  VAULT_DIR=/path/to/project python3 scripts/daily_knowledge_sync.py
"""

import argparse
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts._utils import find_project_dir

# 專案目錄：優先用 VAULT_DIR 環境變數，否則自動搜尋
PROJECT_DIR = Path(os.environ.get("VAULT_DIR", "")) if os.environ.get("VAULT_DIR") else find_project_dir()
SCRIPTS_DIR = Path(__file__).resolve().parent


def run(cmd, desc, cwd=None, timeout=60):
    """執行指令並回報"""
    print(f"\n{'='*50}")
    print(f"📋 {desc}")
    print(f"{'='*50}")
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=str(cwd or PROJECT_DIR)
        )
        output = result.stdout.strip()
        if output:
            print(output[-500:])
        if result.returncode != 0:
            print(f"⚠️ Exit code: {result.returncode}")
            if result.stderr:
                print(f"   {result.stderr[:200]}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"❌ Timeout ({timeout}s)")
        return False


def main():
    print(f"🔄 Vault 每日同步 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   專案目錄: {PROJECT_DIR}\n")

    results = {}

    # 1. Git pull（取最新知識）
    results['git_pull'] = run(
        'git pull --ff-only 2>&1',
        "Git pull（同步最新知識）"
    )

    # 2. vault compile
    results['compile'] = run(
        'vault compile 2>&1',
        "vault compile（raw/ → DB + compiled/）",
        timeout=120
    )

    # 3. 語意去重（只掃描，不自動合併）
    results['dedup'] = run(
        'vault dedup 2>&1',
        "語意重複偵測"
    )

    # 4. Trust 動態調整
    results['trust'] = run(
        f'python3 {SCRIPTS_DIR}/trust_adjustment.py --apply 2>&1',
        "Trust 動態調整"
    )

    # 5. 知識缺口建議
    results['suggest'] = run(
        f'python3 {SCRIPTS_DIR}/suggest_new_knowledge.py 2>&1',
        "知識缺口偵測"
    )

    # 6. 審核佇列摘要
    results['review'] = run(
        f'python3 {SCRIPTS_DIR}/manual_review.py --queue 2>&1',
        "待審核佇列"
    )

    # 7. 統計提示（vault_wakeup.py 已移除）
    results['stats_note'] = run(
        'echo "改用 MCP vault_stats 或 vault stats 取得統計" 2>&1',
        "知識庫統計提示"
    )

    # 結果摘要
    print(f"\n{'='*50}")
    print(f"📊 同步結果摘要")
    print(f"{'='*50}")
    for step, success in results.items():
        icon = "✅" if success else "❌"
        print(f"  {icon} {step}")

    all_ok = all(results.values())
    print(f"\n{'🎉 全部完成！' if all_ok else '⚠️ 部分步驟失敗'}")
    return all_ok


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the local Vault daily maintenance wrapper.")
    parser.add_argument(
        "--project-dir",
        default=None,
        help="Project root to operate on. Defaults to VAULT_DIR or auto-discovery.",
    )
    args = parser.parse_args()
    if args.project_dir:
        PROJECT_DIR = Path(args.project_dir).expanduser().resolve()
    ok = main()
    sys.exit(0 if ok else 1)
