#!/usr/bin/env python3
"""
Sync Guardrails-knowledge local DB → Supabase
把本地 sqlite DB 的知識同步到 Supabase guardrails_knowledge 表。

策略：
1. 讀取本地 DB 全部知識
2. 用 title 去重（本地有的才更新/新增）
3. 新增的插入，已有的更新
4. Supabase 多餘的不刪除
"""

import os
import sys
import json
import hashlib
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts._utils import find_db_path, load_dotenv_cascade

# 載入 .env：優先用專案目錄的 .env，其次 ~/.env
load_dotenv_cascade()

from supabase import create_client
from vault.guardrails_db import GuardrailsDB

DB_PATH = str(find_db_path())


def sync(db_path=DB_PATH):
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_ANON_KEY') or os.getenv('SUPABASE_KEY')
    if not url or not key:
        print("❌ SUPABASE_URL 或 SUPABASE_ANON_KEY 未設定")
        return

    sb = create_client(url, key)
    db = GuardrailsDB(db_path)
    db.connect()

    # 讀取本地知識
    rows = db.conn.execute(
        "SELECT id, title, layer, category, tags, trust, content_raw, content_aaak, "
        "content_hash, source, created_at, updated_at FROM knowledge ORDER BY id"
    ).fetchall()
    print(f"📚 本地知識: {len(rows)} 筆")

    # 讀取 Supabase 現有
    sb_rows = sb.table('guardrails_knowledge').select('id,title').execute().data
    sb_titles = {r['title']: r['id'] for r in sb_rows}
    print(f"☁️ Supabase 知識: {len(sb_rows)} 筆")

    inserted = 0
    updated = 0
    failed = 0

    for row in rows:
        kid, title, layer, category, tags, trust, content_raw, content_aaak, \
            content_hash, source, created_at, updated_at = row

        data = {
            'title': title,
            'layer': layer or 'L3',
            'category': category or 'general',
            'tags': tags or '[]',
            'trust': trust or 0.5,
            'content_raw': content_raw or '',
            'content_aaak': content_aaak or '',
            'content_hash': content_hash or '',
            'source': source or 'local',
            'updated_at': datetime.now().isoformat(),
        }

        try:
            if title in sb_titles:
                # Update
                sb.table('guardrails_knowledge').update(data).eq('id', sb_titles[title]).execute()
                updated += 1
            else:
                # Insert
                data['created_at'] = created_at or datetime.now().isoformat()
                sb.table('guardrails_knowledge').insert(data).execute()
                inserted += 1
        except Exception as e:
            err = str(e)
            if 'duplicate key' in err.lower():
                # Title 衝突，用 upsert
                try:
                    data['created_at'] = created_at or datetime.now().isoformat()
                    sb.table('guardrails_knowledge').upsert(data, on_conflict='title').execute()
                    updated += 1
                except Exception as e2:
                    failed += 1
                    print(f"  ❌ {title[:40]}: {str(e2)[:80]}")
            else:
                failed += 1
                print(f"  ❌ {title[:40]}: {err[:80]}")

        if (inserted + updated + failed) % 20 == 0:
            print(f"  {inserted + updated + failed}/{len(rows)} synced...")

    db.close()

    # 確認
    final = sb.table('guardrails_knowledge').select('id').execute().data
    print(f"\n✅ Sync complete:")
    print(f"   Inserted: {inserted}")
    print(f"   Updated: {updated}")
    print(f"   Failed: {failed}")
    print(f"   Supabase total: {len(final)}")


if __name__ == "__main__":
    sync()
