#!/usr/bin/env python3
"""
Vault 智能去重腳本
透過語意向量計算相似度，找出並合併重複知識。

純 Python 實作，不依賴 numpy。

使用方式：
  python3 scripts/deduplicate_semantic.py              # 掃描（不修改）
  python3 scripts/deduplicate_semantic.py --merge       # 自動合併
  python3 scripts/deduplicate_semantic.py --threshold 0.9  # 自訂閾值
"""

import os
import sys
import json
import math
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vault.db import VaultDB
from vault.embed import create_embedding_provider


def _find_db_path() -> str:
    """從 cwd 往上搜尋 vault.db，找不到就用 cwd/vault.db。"""
    cwd = Path.cwd()
    for d in [cwd] + list(cwd.parents):
        candidate = d / "vault.db"
        if candidate.exists():
            return str(candidate)
    return str(cwd / "vault.db")

DB_PATH = _find_db_path()


def cosine_similarity(a, b):
    """純 Python 餘弦相似度"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def flatten(vec):
    """把嵌套 list 攤平成一維"""
    if isinstance(vec, (int, float)):
        return [vec]
    result = []
    for item in vec:
        if isinstance(item, (list, tuple)):
            result.extend(flatten(item))
        elif isinstance(item, (int, float)):
            result.append(item)
    return result


def find_duplicates(db_path=DB_PATH, threshold=0.85, embed_provider=None):
    """找出語意重複的知識條目"""
    db = VaultDB(db_path)
    db.connect()

    rows = db.conn.execute(
        "SELECT id, title, content_aaak, trust, category FROM knowledge ORDER BY id"
    ).fetchall()

    if not rows:
        print("⚠️ 沒有知識可處理")
        db.close()
        return []

    print(f"📚 載入 {len(rows)} 條知識")

    # 建立嵌入
    if embed_provider is None:
        # 先嘗試從數據庫讀取 provider 設定
        try:
            provider_name = db.get_config("embedding_provider", "auto")
        except Exception:
            provider_name = "auto"
        embedder = create_embedding_provider(provider=provider_name)
    else:
        embedder = embed_provider
    embed_dim = embedder.dim  # 動態取得維度，避免硬編碼
    texts = [r[2] if r[2] else r[1] for r in rows]

    print("🔄 計算嵌入向量（批次處理中）...")
    vectors = []
    batch_size = 16
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            batch_vecs = embedder.encode(batch)
            for v in batch_vecs:
                vectors.append(flatten(v))
        except Exception as e:
            # 如果批次失敗，逐條處理
            for t in batch:
                try:
                    v = embedder.encode(t)
                    vectors.append(flatten(v))
                except Exception:
                    vectors.append([0.0] * embed_dim)  # fallback：使用實際維度
        done = min(i + batch_size, len(texts))
        if done % 32 == 0 or done == len(texts):
            print(f"  已處理 {done}/{len(texts)}")

    dim = len(vectors[0]) if vectors else 0
    print(f"✅ 嵌入計算完成，維度: {dim}")

    # 計算相似度
    duplicates = []
    total_pairs = len(rows) * (len(rows) - 1) // 2
    checked = 0
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            sim = cosine_similarity(vectors[i], vectors[j])
            if sim > threshold:
                duplicates.append({
                    "id1": rows[i][0],
                    "id2": rows[j][0],
                    "title1": rows[i][1],
                    "title2": rows[j][1],
                    "trust1": rows[i][3],
                    "trust2": rows[j][3],
                    "category1": rows[i][4],
                    "category2": rows[j][4],
                    "similarity": round(sim, 4)
                })
            checked += 1
        if (i + 1) % 50 == 0:
            print(f"  比對進度: {i+1}/{len(rows)} ({len(duplicates)} 組重複)")

    duplicates.sort(key=lambda x: x["similarity"], reverse=True)

    # 存報告（放在 DB 同目錄）
    report_path = str(Path(db_path).parent / "duplicate_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "scan_time": datetime.now().isoformat(),
            "total_knowledge": len(rows),
            "threshold": threshold,
            "duplicates_found": len(duplicates),
            "duplicates": duplicates
        }, f, ensure_ascii=False, indent=2)

    print(f"\n🔍 掃描結果：{len(duplicates)} 組重複（閾值 {threshold}）")
    if duplicates:
        print(f"📄 報告：{report_path}")
        print("\n重複列表：")
        for d in duplicates[:10]:
            keep = d["id1"] if d["trust1"] >= d["trust2"] else d["id2"]
            drop = d["id2"] if keep == d["id1"] else d["id1"]
            print(f"  sim={d['similarity']:.3f}")
            print(f"    ID{d['id1']} (trust={d['trust1']}) 「{d['title1'][:50]}」")
            print(f"    ID{d['id2']} (trust={d['trust2']}) 「{d['title2'][:50]}」")
            print(f"    → 保留 ID{keep}，刪除 ID{drop}")
    else:
        print("✅ 沒有發現重複知識")

    db.close()
    return duplicates


def merge_duplicates(db_path=DB_PATH, report_path=None, dry_run=True):
    """根據報告合併重複知識"""
    if report_path is None:
        # 放在 DB 同目錄，不再寫回 scripts/ 旁邊
        report_path = str(Path(db_path).parent / "duplicate_report.json")

    if not os.path.exists(report_path):
        print(f"❌ 找不到報告：{report_path}")
        return

    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    duplicates = report.get("duplicates", [])
    if not duplicates:
        print("✅ 無需合併")
        return

    db = VaultDB(db_path)
    db.connect()

    merged = 0
    for d in duplicates:
        id1, id2 = d["id1"], d["id2"]
        keep_id = id1 if d["trust1"] >= d["trust2"] else id2
        drop_id = id2 if keep_id == id1 else id1

        if dry_run:
            print(f"[DRY RUN] 刪除 ID{drop_id} → 保留 ID{keep_id}")
        else:
            try:
                db.conn.execute(
                    "UPDATE entity_knowledge SET knowledge_id = ? WHERE knowledge_id = ?",
                    (keep_id, drop_id)
                )
            except Exception:
                pass
            db.conn.execute("DELETE FROM knowledge WHERE id = ?", (drop_id,))
            print(f"✅ 合併：刪除 ID{drop_id} → 保留 ID{keep_id}")
        merged += 1

    if not dry_run:
        db.conn.commit()
        print(f"\n🎉 已合併 {merged} 組")
    else:
        print(f"\n📋 DRY RUN：{merged} 組待合併（加 --merge 執行）")

    db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vault 智能去重")
    parser.add_argument("--merge", action="store_true", help="實際合併")
    parser.add_argument("--threshold", type=float, default=0.85, help="相似度閾值")
    args = parser.parse_args()

    duplicates = find_duplicates(threshold=args.threshold)
    if duplicates and args.merge:
        print("\n" + "=" * 50)
        merge_duplicates(dry_run=False)
    elif duplicates:
        print(f"\n💡 加 --merge 實際合併")
