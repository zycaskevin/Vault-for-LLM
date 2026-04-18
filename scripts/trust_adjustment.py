#!/usr/bin/env python3
"""
Guardrails 動態信任調整腳本
根據使用頻率、時間衰減、品質指標自動調整 trust 分數。

策略：
1. 時間衰減：越久沒更新的知識，trust 微幅下降
2. 存取頻率加分：access_count 高的知識代表實際有用
3. 品質加分：有完整 tags、category、content_raw 的加分
4. 孤立懲罰：沒有任何 entity 關聯的微幅下降
5. 最終信任 = 原信任 * 0.7 + 新指標 * 0.3（避免劇烈變動）

使用方式：
  python3 scripts/trust_adjustment.py              # 預覽（不修改）
  python3 scripts/trust_adjustment.py --apply       # 實際更新
  python3 scripts/trust_adjustment.py --min 0.3     # 只調整 trust < 0.3 的
  python3 scripts/trust_adjustment.py --db /path/to/guardrails.db
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from vault.guardrails_db import GuardrailsDB


def _find_db(explicit_path: str | None) -> Path:
    """
    搜尋 guardrails.db：
      1. CLI 明確指定的路徑（--db）
      2. 環境變數 GUARDRAILS_PATH
      3. 往上找含 guardrails.db 的目錄（從 cwd 開始）
      4. 此腳本的 repo root（scripts/ 的上一層）
    """
    if explicit_path:
        return Path(explicit_path)

    env = os.environ.get("GUARDRAILS_PATH")
    if env:
        p = Path(env)
        return p if p.suffix == ".db" else p / "guardrails.db"

    cwd = Path.cwd()
    for d in [cwd] + list(cwd.parents):
        candidate = d / "guardrails.db"
        if candidate.exists():
            return candidate

    # fallback：repo root
    return Path(__file__).parent.parent / "guardrails.db"


def compute_quality_score(row: dict) -> float:
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


def compute_access_bonus(access_count: int) -> float:
    """
    根據存取次數計算加分（0.0 ~ 0.15）。
    access_count 越高代表這筆知識實際被使用，trust 應該維持較高。
    """
    if access_count <= 0:
        return 0.0
    # log scale：1次 → 0.03, 5次 → 0.08, 20次 → 0.13, 50+次 → 0.15
    import math
    return min(0.15, round(0.05 * math.log1p(access_count), 3))


def adjust_trust(
    db_path: Path,
    apply: bool = False,
    min_trust: float | None = None,
    output_report: bool = True,
) -> list[dict]:
    """調整信任分數，回傳 adjustments 列表。"""
    if not db_path.exists():
        print(f"❌ 找不到資料庫：{db_path}")
        sys.exit(1)

    db = GuardrailsDB(str(db_path))
    db.connect()

    rows = db.conn.execute(
        "SELECT id, title, trust, category, tags, layer, content_raw, "
        "updated_at, created_at, "
        "COALESCE(access_count, 0) as access_count, "
        "COALESCE(last_accessed_at, '') as last_accessed_at "
        "FROM knowledge ORDER BY id"
    ).fetchall()

    # 取得有 entity 關聯的知識 ID
    linked_ids: set[int] = set()
    try:
        for r in db.conn.execute(
            "SELECT DISTINCT knowledge_id FROM entity_knowledge"
        ).fetchall():
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

        row_dict = {
            "content_raw": row[6],
            "tags": row[4],
            "category": row[3],
            "trust": row[2],
            "layer": row[5],
        }
        quality = compute_quality_score(row_dict)
        access_bonus = compute_access_bonus(row[9])  # access_count

        # 時間衰減（基於 last_accessed_at，fallback 到 updated_at / created_at）
        last_touch = row[10] or row[7] or row[8]  # last_accessed_at > updated_at > created_at
        time_factor = 1.0
        if last_touch:
            try:
                # 處理各種 ISO 格式：Z 結尾、+00:00 結尾、無時區
                ts = last_touch.replace("Z", "+00:00")
                # Python 3.7+ fromisoformat 支援 +00:00
                dt = datetime.fromisoformat(ts)
                days_idle = (now - dt).days
                # 每 30 天衰減 5%，最多 30%（有存取紀錄的衰減更慢）
                decay_rate = 0.03 if row[9] > 0 else 0.05
                time_factor = max(0.7, 1.0 - (days_idle / 30) * decay_rate)
            except (ValueError, TypeError):
                pass

        # 孤立懲罰（無圖譜關聯 → 乘 0.95）
        isolation_factor = 1.0 if kid in linked_ids else 0.95

        # 最終計算
        new_trust = (
            old_trust * 0.7 * time_factor
            + quality * 0.2
            + access_bonus
            + (1.0 if kid in linked_ids else 0.5) * 0.1
        ) * isolation_factor

        new_trust = round(max(0.1, min(1.0, new_trust)), 2)
        delta = new_trust - old_trust

        adjustments.append({
            "id": kid,
            "title": row[1][:50],
            "old_trust": old_trust,
            "new_trust": new_trust,
            "delta": round(delta, 3),
            "quality": round(quality, 2),
            "access_count": row[9],
            "access_bonus": access_bonus,
            "linked": kid in linked_ids,
        })

    adjustments.sort(key=lambda x: abs(x["delta"]), reverse=True)

    if apply:
        for adj in adjustments:
            db.conn.execute(
                "UPDATE knowledge SET trust = ?, updated_at = ? WHERE id = ?",
                (adj["new_trust"], now.isoformat(), adj["id"])
            )
        db.conn.commit()
        print(f"✅ 已更新 {len(adjustments)} 條 trust 分數")
    else:
        print(f"📊 預覽：共 {len(adjustments)} 條將調整（加 --apply 實際更新）")
        print()
        up = sum(1 for a in adjustments if a["delta"] > 0.01)
        down = sum(1 for a in adjustments if a["delta"] < -0.01)
        same = len(adjustments) - up - down
        print(f"  上升: {up} 條 | 下降: {down} 條 | 不變: {same} 條")
        print()
        print("變動最大（前 10）：")
        for adj in adjustments[:10]:
            arrow = "🔺" if adj["delta"] > 0 else "🔻" if adj["delta"] < 0 else "➖"
            access_info = f" 存取{adj['access_count']}次" if adj["access_count"] > 0 else ""
            print(
                f"  {arrow} ID{adj['id']} {adj['old_trust']:.2f} → {adj['new_trust']:.2f} "
                f"({adj['delta']:+.3f}){access_info} 「{adj['title']}」"
            )

    if output_report:
        # 報告放在 db 同目錄，不進 git（已加入 .gitignore）
        report_path = db_path.parent / "trust_report.json"
        report_path.write_text(
            json.dumps({
                "scan_time": now.isoformat(),
                "db_path": str(db_path),
                "total_adjusted": len(adjustments),
                "applied": apply,
                "adjustments": adjustments,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n📄 報告已存：{report_path}")

    db.close()
    return adjustments


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Guardrails 動態信任調整")
    parser.add_argument("--apply", action="store_true", help="實際更新（預設只預覽）")
    parser.add_argument("--min", type=float, dest="min_trust", help="只調整 trust 低於此值的")
    parser.add_argument("--db", type=str, dest="db_path", help="指定 guardrails.db 路徑")
    parser.add_argument("--no-report", action="store_true", help="不輸出 trust_report.json")
    args = parser.parse_args()

    db = _find_db(args.db_path)
    print(f"🗄️  使用資料庫：{db}")
    adjust_trust(
        db_path=db,
        apply=args.apply,
        min_trust=args.min_trust,
        output_report=not args.no_report,
    )
