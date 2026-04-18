#!/usr/bin/env python3
"""
Guardrails 每日知識同步 — 整合所有同步步驟的入口腳本。

流程：
1. 從 GitHub 拉取最新 raw/ 知識
2. Compiler 編譯 raw/ → Supabase
3. 本地 DB 去重
4. Trust 動態調整
5. Supabase 清理重複
6. 統計報告
"""

import os
import sys
import subprocess
import json
from pathlib import Path
from datetime import datetime

GUARDRAILS_DIR = Path.home() / '.agent-runtime' / 'Guardrails'
KNOWLEDGE_DIR = Path.home() / 'Guardrails-knowledge'
SCRIPTS = KNOWLEDGE_DIR / 'scripts'


def run(cmd, desc, timeout=60):
    """執行指令並回報"""
    print(f"\n{'='*50}")
    print(f"📋 {desc}")
    print(f"{'='*50}")
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout.strip()
        if output:
            print(output[-500:])  # 只顯示最後 500 字元
        if result.returncode != 0:
            print(f"⚠️ Exit code: {result.returncode}")
            if result.stderr:
                print(f"   {result.stderr[:200]}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"❌ Timeout ({timeout}s)")
        return False


def main():
    print(f"🔄 Guardrails 每日同步 — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    results = {}

    # 1. Git pull
    results['git_pull'] = run(
        f'cd {GUARDRAILS_DIR} && git pull --ff-only 2>&1',
        "Git pull (.agent-runtime/Guardrails)"
    )
    results['git_pull_kb'] = run(
        f'cd {KNOWLEDGE_DIR} && git pull --ff-only 2>&1',
        "Git pull (Guardrails-knowledge)"
    )

    # 2. Compiler (raw/ → Supabase)
    results['compiler'] = run(
        f'python3 {Path.home()}/.agent-runtime/scripts/guardrails_compiler_update.py 2>&1',
        "Compiler: raw/ → Supabase",
        timeout=120
    )

    # 3. Trust adjustment
    results['trust'] = run(
        f'cd {GUARDRAILS_DIR} && python3 scripts/trust_adjustment.py --apply 2>&1',
        "Trust 動態調整"
    )

    # 4. 統計
    results['stats'] = run(
        f'python3 {GUARDRAILS_DIR}/scripts/guardrails_wakeup.py --stats 2>&1',
        "知識庫統計"
    )

    # 5. 建議
    results['suggest'] = run(
        f'cd {GUARDRAILS_DIR} && python3 scripts/suggest_new_knowledge.py 2>&1',
        "知識缺口偵測"
    )

    # 6. 審核佇列摘要
    results['review'] = run(
        f'cd {GUARDRAILS_DIR} && python3 scripts/manual_review.py --queue 2>&1',
        "審核佇列"
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
    ok = main()
    sys.exit(0 if ok else 1)
