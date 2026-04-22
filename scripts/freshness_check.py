#!/usr/bin/env python3
"""
Guardrails 新鮮度追蹤 — 檢查知識條目的新鮮度並標記過期條目。

策略：
1. 計算每條知識的 freshness 分數基於：
   - last_verified 時間（越久未驗證越不新鮮）
   - 更新時間（updated_at）
   - 引用頻率（entity 關聯數）
2. 超過 90 天未驗證 → freshness = 0.5
3. 超過 180 天 → freshness = 0.3
4. 從未驗證 → 按 updated_at 算
5. 標記 stale 條目供後續處理

使用方式：
  python3 scripts/freshness_check.py              # 預覽模式（不修改 DB）
  python3 scripts/freshness_check.py --apply       # 實際更新 freshness
  python3 scripts/freshness_check.py --limit 20    # 只處理 20 條
  python3 scripts/freshness_check.py --stale-only   # 只顯示 stale 條目
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from guardrails_lite.guardrails_db import GuardrailsDB

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "guardrails.db")


def calc_freshness(updated_at: str, last_verified: str = "", entity_count: int = 0) -> float:
    """
    計算新鮮度分數（0.0 ~ 1.0）。

    因素：
    - last_verified 時間衰減：越久未驗證越不新鮮
    - updated_at 衰減：越久未更新越不新鮮
    - entity 關聯加成：有更多實體關聯的知識通常更重要

    公式：
    base = 1.0 - min(days_since_verified / 180, 0.7)  # 未驗證衰減
    update_bonus = max(0, 0.2 - days_since_update / 365 * 0.2)  # 更新加成
    entity_bonus = min(entity_count / 10, 0.1)  # 引用加成
    freshness = base + update_bonus + entity_bonus
    """
    now = datetime.now(timezone.utc)

    # 計算天數差
    def days_since(date_str: str) -> float:
        if not date_str:
            return 999  # 從未驗證/更新
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return max(0, (now - dt).days)
        except Exception:
            return 999

    days_verified = days_since(last_verified)
    days_updated = days_since(updated_at)

    # 基礎分數：基於 last_verified
    if days_verified < 30:
        base = 1.0
    elif days_verified < 90:
        base = 0.8
    elif days_verified < 180:
        base = 0.5
    elif days_verified < 365:
        base = 0.3
    else:
        base = 0.2

    # 更新加成：最近更新的知識更可信
    update_bonus = max(0, 0.2 - days_updated / 365 * 0.2) if days_updated < 365 else 0

    # 引用加成：有更多實體關聯的知識更重要
    entity_bonus = min(entity_count / 10, 0.1)

    freshness = min(1.0, max(0.0, base + update_bonus + entity_bonus))
    return round(freshness, 3)


def get_entity_count(db: GuardrailsDB, kid: int) -> int:
    """取得條目的實體關聯數。"""
    try:
        entities = db.get_entities_for_knowledge(kid)
        return len(entities) if entities else 0
    except Exception:
        return 0


def check_freshness(
    db_path: str = DB_PATH,
    apply: bool = False,
    limit: int = 0,
    stale_only: bool = False,
):
    """執行新鮮度檢查。"""

    db = GuardrailsDB(db_path)
    db.connect()

    # 查詢所有條目
    query = "SELECT id, title, updated_at, last_verified, freshness, trust FROM knowledge ORDER BY freshness ASC, updated_at ASC"
    rows = db.conn.execute(query).fetchall()

    if not rows:
        print("📭 百科是空的，沒有條目需要檢查")
        db.close()
        return

    results = []
    fresh_count = 0
    stale_count = 0
    critical_count = 0

    for row in rows:
        if limit > 0 and len(results) >= limit:
            break

        kid = row[0]
        title = row[1]
        updated_at = row[2] or ""
        last_verified = row[3] or ""
        current_freshness = row[4] if row[4] is not None else 1.0
        trust = row[5]

        # 計算新鮮度
        entity_count = get_entity_count(db, kid)
        new_freshness = calc_freshness(updated_at, last_verified, entity_count)

        # 分類
        if new_freshness >= 0.8:
            category = "🟢 fresh"
            fresh_count += 1
        elif new_freshness >= 0.5:
            category = "🟡 stale"
            stale_count += 1
        else:
            category = "🔴 critical"
            critical_count += 1

        # 只顯示 stale 的
        if stale_only and new_freshness >= 0.8:
            continue

        # 計算天數資訊
        now = datetime.now(timezone.utc)
        days_since_update = 999
        days_since_verified = 999
        if updated_at:
            try:
                dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                days_since_update = (now - dt).days
            except Exception:
                pass
        if last_verified:
            try:
                dt = datetime.fromisoformat(last_verified.replace("Z", "+00:00"))
                days_since_verified = (now - dt).days
            except Exception:
                pass

        results.append({
            "id": kid,
            "title": title,
            "old_freshness": current_freshness,
            "new_freshness": new_freshness,
            "category": category,
            "days_since_update": days_since_update,
            "days_since_verified": days_since_verified,
            "entity_count": entity_count,
            "trust": trust,
        })

        # 更新 DB
        if apply:
            db.update_freshness(kid, new_freshness, last_verified if last_verified else None)

    # 輸出報告
    print("=" * 70)
    print(f"📊 新鮮度檢查結果")
    print(f"   總條目：{len(results)}")
    print(f"   🟢 新鮮 (>0.8)：{fresh_count}")
    print(f"   🟡 過期 (0.5-0.8)：{stale_count}")
    print(f"   🔴 嚴重過期 (<0.5)：{critical_count}")
    print("=" * 70)

    for r in results:
        delta = f"{r['old_freshness']:.2f}→{r['new_freshness']:.2f}" if r['old_freshness'] != r['new_freshness'] else f"{r['new_freshness']:.2f}"

        update_info = f"{r['days_since_update']}d ago" if r['days_since_update'] < 999 else "never"
        verify_info = f"{r['days_since_verified']}d ago" if r['days_since_verified'] < 999 else "never"

        print(f"  {r['category']} [{r['id']}] {r['title'][:50]}")
        print(f"       freshness={delta}, updated={update_info}, verified={verify_info}, entities={r['entity_count']}")

    if not apply:
        print(f"\n💡 這是預覽模式。使用 --apply 實際更新資料庫。")

    # 儲存 JSON 報告
    report_path = os.path.join(os.path.dirname(db_path), "freshness_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total": len(results),
            "fresh": fresh_count,
            "stale": stale_count,
            "critical": critical_count,
            "results": [{
                "id": r["id"],
                "title": r["title"],
                "old_freshness": r["old_freshness"],
                "new_freshness": r["new_freshness"],
                "days_since_update": r["days_since_update"],
                "days_since_verified": r["days_since_verified"],
                "entity_count": r["entity_count"],
            } for r in results],
        }, f, ensure_ascii=False, indent=2)
    print(f"\n📄 報告已儲存：{report_path}")

    # 建議：需要重新驗證的條目
    critical_items = [r for r in results if r["new_freshness"] < 0.5]
    if critical_items:
        print(f"\n⚠️  {len(critical_items)} 條嚴重過期，建議重新驗證：")
        for r in critical_items[:5]:
            print(f"  - [{r['id']}] {r['title'][:50]} (freshness={r['new_freshness']:.2f})")
        if len(critical_items) > 5:
            print(f"  ... 還有 {len(critical_items) - 5} 條")

    db.close()
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Guardrails 新鮮度追蹤")
    parser.add_argument("--apply", action="store_true", help="實際更新 DB（預設為預覽模式）")
    parser.add_argument("--limit", type=int, default=0, help="最多處理幾條（0=全部）")
    parser.add_argument("--stale-only", action="store_true", help="只顯示過期條目")
    args = parser.parse_args()

    check_freshness(
        apply=args.apply,
        limit=args.limit,
        stale_only=args.stale_only,
    )