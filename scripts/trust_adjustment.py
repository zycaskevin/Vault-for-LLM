#!/usr/bin/env python3
"""
Guardrails 動態信任調整腳本
根據使用頻率、時間衰減、品質指標自動調整 trust 分數。

策略：
1. 時間衰減：越久沒更新的知識，trust 微幅下降
2. 品質加分：有完整 tags、category、content_raw 的加分
3. 孤立懲罰：沒有任何 entity 關聯的微幅下降
4. 最終信任 = 原信任 * 0.7 + 新指標 * 0.3（避免劇烈變動）

使用方式：
  python3 scripts/trust_adjustment.py              # 預覽（不修改）
  python3 scripts/trust_adjustment.py --apply       # 實際更新
  python3 scripts/trust_adjustment.py --min 0.3     # 只調整 trust < 0.3 的
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from guardrails_lite.guardrails_db import GuardrailsDB

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "guardrails.db")


def compute_quality_score(row):
    """計算一條知識的品質分數（0.0 ~ 1.0）"""
    score = 0.5  # 基準

    # 有 content_raw（完整內容）+0.1
    if row.get("content_raw") and len(row["content_raw"]) > 50:
        score += 0.1

    # 有 tags +0.1
    if row.get("tags") and row["tags"] not in ("", "[]", "null"):
        score += 0.1

    # category 不是 null +0.05
    if row.get("category") and row["category"] not in ("", "null"):
        score += 0.05

    # trust 已經很高 → 加分（代表過去被驗證過）
    if row.get("trust", 0) >= 0.8:
        score += 0.1

    # layer 是 L3（深度知識）→ 加分
    if row.get("layer") in ("L3", "3"):
        score += 0.05

    return min(score, 1.0)


def adjust_trust(db_path=DB_PATH, apply=False, min_trust=None):
    """調整信任分數"""
    db = GuardrailsDB(db_path)
    db.connect()

    rows = db.conn.execute(
        "SELECT id, title, trust, category, tags, layer, content_raw, "
        "length(content_raw) as raw_len, updated_at, created_at "
        "FROM knowledge ORDER BY id"
    ).fetchall()

    # 取得有 entity 關聯的知識 ID
    linked_ids = set()
    try:
        for r in db.conn.execute("SELECT DISTINCT knowledge_id FROM entity_knowledge").fetchall():
            linked_ids.add(r[0])
    except Exception:
        pass

    now = datetime.now()
    adjustments = []

    for row in rows:
        kid = row[0]
        old_trust = row[2]

        # 如果設定最低閾值，跳過高於閾值的
        if min_trust is not None and old_trust >= min_trust:
            continue

        # 1. 品質分數
        # row: id=0, title=1, trust=2, category=3, tags=4, layer=5,
        #      content_raw=6, raw_len=7, updated_at=8, created_at=9
        row_dict = {
            "content_raw": row[6],  # actual content
            "tags": row[4],
            "category": row[3],
            "trust": row[2],
            "layer": row[5],
        }
        quality = compute_quality_score(row_dict)

        # 2. 時間衰減
        updated = row[9] or row[10]  # updated_at or created_at
        time_factor = 1.0
        if updated:
            try:
                updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00").replace("+00:00", ""))
                days_old = (now - updated_dt).days
                # 每過 30 天衰減 5%，最多衰減 30%
                time_factor = max(0.7, 1.0 - (days_old / 30) * 0.05)
            except (ValueError, TypeError):
                pass

        # 3. 孤立懲罰
        isolation_factor = 1.0 if kid in linked_ids else 0.9

        # 4. 最終計算：原 trust * 0.7 + 品質 * 0.2 + 關聯 * 0.1
        new_trust = (
            old_trust * 0.7 * time_factor
            + quality * 0.2
            + (1.0 if kid in linked_ids else 0.5) * 0.1
        ) * isolation_factor

        # 限制在 0.1 ~ 1.0
        new_trust = round(max(0.1, min(1.0, new_trust)), 2)

        delta = new_trust - old_trust
        adjustments.append({
            "id": kid,
            "title": row[1][:50],
            "old_trust": old_trust,
            "new_trust": new_trust,
            "delta": round(delta, 3),
            "quality": round(quality, 2),
            "linked": kid in linked_ids,
        })

    # 按變動幅度排序
    adjustments.sort(key=lambda x: abs(x["delta"]), reverse=True)

    # 輸出報告
    if apply:
        for adj in adjustments:
            db.conn.execute(
                "UPDATE knowledge SET trust = ?, updated_at = ? WHERE id = ?",
                (adj["new_trust"], datetime.now().isoformat(), adj["id"])
            )
        db.conn.commit()
        print(f"✅ 已更新 {len(adjustments)} 條 trust 分數")
    else:
        print(f"📊 預覽：共 {len(adjustments)} 條將調整（加 --apply 實際更新）")
        print()

        # 分類統計
        up = sum(1 for a in adjustments if a["delta"] > 0.01)
        down = sum(1 for a in adjustments if a["delta"] < -0.01)
        same = len(adjustments) - up - down
        print(f"  上升: {up} 條 | 下降: {down} 條 | 不變: {same} 條")
        print()

        # 顯示變動最大的
        print("變動最大（前 10）：")
        for adj in adjustments[:10]:
            arrow = "🔺" if adj["delta"] > 0 else "🔻" if adj["delta"] < 0 else "➖"
            print(f"  {arrow} ID{adj['id']} {adj['old_trust']:.2f} → {adj['new_trust']:.2f} ({adj['delta']:+.3f}) 「{adj['title']}」")

    # 存報告
    report_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "trust_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "scan_time": datetime.now().isoformat(),
            "total_adjusted": len(adjustments),
            "applied": apply,
            "adjustments": adjustments
        }, f, ensure_ascii=False, indent=2)

    print(f"\n📄 報告已存：{report_path}")
    db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Guardrails 動態信任調整")
    parser.add_argument("--apply", action="store_true", help="實際更新（預設只預覽）")
    parser.add_argument("--min", type=float, dest="min_trust", help="只調整 trust 低於此值的")
    args = parser.parse_args()

    adjust_trust(apply=args.apply, min_trust=args.min_trust)
