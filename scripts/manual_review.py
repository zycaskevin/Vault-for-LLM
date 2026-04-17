#!/usr/bin/env python3
"""
Guardrails 審核佇列
標記需要人工審核的知識（低 trust、缺少分類、內容太短、可疑來源）。

使用方式：
  python3 scripts/manual_review.py                  # 檢視待審核佇列
  python3 scripts/manual_review.py --approve ID     # 通過審核（trust → 0.8）
  python3 scripts/manual_review.py --reject ID      # 退回（trust → 0.2）
  python3 scripts/manual_review.py --fix ID --category technique --trust 0.85
  python3 scripts/manual_review.py --queue          # 只顯示佇列摘要
"""

import os
import sys
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vault.guardrails_db import GuardrailsDB

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "guardrails.db")

# 審核閾值
LOW_TRUST = 0.4
MIN_CONTENT_LEN = 30
SUSPECT_SOURCES = ["session-extract", "test"]


def get_review_queue(db_path=DB_PATH):
    """取得待審核佇列"""
    db = GuardrailsDB(db_path)
    db.connect()

    rows = db.conn.execute(
        "SELECT id, title, trust, category, tags, layer, "
        "length(content_raw) as raw_len, source, created_at "
        "FROM knowledge ORDER BY trust ASC, id ASC"
    ).fetchall()

    queue = []
    for row in rows:
        kid, title, trust, category, tags, layer, raw_len, source, created = row
        reasons = []

        if trust < LOW_TRUST:
            reasons.append(f"低信任 ({trust:.2f})")
        if raw_len < MIN_CONTENT_LEN:
            reasons.append(f"內容過短 ({raw_len}字)")
        if not category or category in ("null", ""):
            reasons.append("缺少分類")
        if not tags or tags in ("null", "", "[]"):
            reasons.append("缺少標籤")
        if source and any(s in (source or "") for s in SUSPECT_SOURCES):
            reasons.append(f"可疑來源 ({source})")
        if title and len(title) > 80:
            reasons.append("標題過長（可能是殘留 session extract）")

        if reasons:
            queue.append({
                "id": kid,
                "title": (title or "")[:60],
                "trust": trust,
                "category": category,
                "raw_len": raw_len,
                "source": source or "",
                "reasons": reasons,
                "created": created or "",
            })

    db.close()
    return queue


def approve(kid, db_path=DB_PATH):
    """通過審核"""
    db = GuardrailsDB(db_path)
    db.connect()
    row = db.conn.execute("SELECT title, trust FROM knowledge WHERE id = ?", (kid,)).fetchone()
    if not row:
        print(f"❌ ID{kid} 不存在")
        db.close()
        return
    db.conn.execute("UPDATE knowledge SET trust = 0.8, updated_at = ? WHERE id = ?",
                    (datetime.now().isoformat(), kid))
    db.conn.commit()
    print(f"✅ ID{kid}「{row[0][:50]}」已通過審核 (trust {row[1]:.2f} → 0.80)")
    db.close()


def reject(kid, db_path=DB_PATH):
    """退回"""
    db = GuardrailsDB(db_path)
    db.connect()
    row = db.conn.execute("SELECT title, trust FROM knowledge WHERE id = ?", (kid,)).fetchone()
    if not row:
        print(f"❌ ID{kid} 不存在")
        db.close()
        return
    db.conn.execute("UPDATE knowledge SET trust = 0.2, updated_at = ? WHERE id = ?",
                    (datetime.now().isoformat(), kid))
    db.conn.commit()
    print(f"🔻 ID{kid}「{row[0][:50]}」已退回 (trust {row[1]:.2f} → 0.20)")
    db.close()


def fix(kid, category=None, trust=None, tags=None, db_path=DB_PATH):
    """修補知識"""
    db = GuardrailsDB(db_path)
    db.connect()
    row = db.conn.execute("SELECT title FROM knowledge WHERE id = ?", (kid,)).fetchone()
    if not row:
        print(f"❌ ID{kid} 不存在")
        db.close()
        return

    updates = []
    params = []
    if category:
        updates.append("category = ?")
        params.append(category)
    if trust is not None:
        updates.append("trust = ?")
        params.append(trust)
    if tags:
        updates.append("tags = ?")
        params.append(tags)

    if not updates:
        print("⚠️ 沒有指定要修改的欄位")
        db.close()
        return

    updates.append("updated_at = ?")
    params.append(datetime.now().isoformat())
    params.append(kid)

    db.conn.execute(f"UPDATE knowledge SET {', '.join(updates)} WHERE id = ?", params)
    db.conn.commit()
    print(f"✅ ID{kid}「{row[0][:50]}」已更新: {', '.join(updates[:-1])}")
    db.close()


def show_queue(queue, summary_only=False):
    """顯示佇列"""
    if summary_only:
        by_reason = {}
        for item in queue:
            for r in item["reasons"]:
                by_reason[r] = by_reason.get(r, 0) + 1
        print(f"📋 待審核: {len(queue)} 條")
        for reason, count in sorted(by_reason.items(), key=lambda x: -x[1]):
            print(f"  {reason}: {count} 條")
        return

    print(f"📋 審核佇列: {len(queue)} 條待審\n")
    for item in queue:
        print(f"  ID{item['id']} [trust={item['trust']:.2f}] 「{item['title']}」")
        print(f"    原因: {' | '.join(item['reasons'])}")
        print(f"    分類={item['category']} 長度={item['raw_len']} 來源={item['source']}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Guardrails 審核佇列")
    parser.add_argument("--queue", action="store_true", help="只顯示摘要")
    parser.add_argument("--approve", type=int, metavar="ID", help="通過審核")
    parser.add_argument("--reject", type=int, metavar="ID", help="退回")
    parser.add_argument("--fix", type=int, metavar="ID", help="修補指定 ID")
    parser.add_argument("--category", type=str, help="設定分類")
    parser.add_argument("--trust", type=float, help="設定 trust")
    parser.add_argument("--tags", type=str, help="設定標籤（逗號分隔）")
    args = parser.parse_args()

    if args.approve:
        approve(args.approve)
    elif args.reject:
        reject(args.reject)
    elif args.fix:
        fix(args.fix, category=args.category, trust=args.trust, tags=args.tags)
    else:
        queue = get_review_queue()
        show_queue(queue, summary_only=args.queue)
