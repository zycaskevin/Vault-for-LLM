#!/usr/bin/env python3
"""
Sync Guardrails-knowledge local DB → Supabase
策略：每筆逐個處理，用 title 查 Supabase → 存在就更新，不存在就插入。
失敗時用 ilike 模糊匹配做 fallback。
"""

import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv(os.path.expanduser('~/.agent-runtime/.env'))

from supabase import create_client
from vault.guardrails_db import GuardrailsDB

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "guardrails.db")


def _parse_layer(layer_str) -> int:
    if not layer_str:
        return 3
    stripped = str(layer_str).strip().upper()
    if stripped.startswith("L"):
        try:
            return int(stripped[1:])
        except (ValueError, IndexError):
            pass
    return 3


def _parse_tags(tags_str) -> list:
    if not tags_str:
        return []
    if isinstance(tags_str, list):
        return tags_str
    s = str(tags_str).strip()
    if s.startswith('[') and s.endswith(']'):
        try:
            return json.loads(s)
        except (json.JSONDecodeError):
            pass
    return [t.strip() for t in s.split(',') if t.strip()]


def sync(db_path=DB_PATH):
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_ANON_KEY') or os.getenv('SUPABASE_KEY')
    if not url or not key:
        print("❌ SUPABASE_URL 或 SUPABASE_ANON_KEY 未設定")
        return

    sb = create_client(url, key)
    db = GuardrailsDB(db_path)
    db.connect()

    rows = db.conn.execute(
        "SELECT id, title, layer, category, tags, trust, content_raw, content_aaak, "
        "content_hash, source, summary, created_at, updated_at FROM knowledge ORDER BY id"
    ).fetchall()
    print(f"📚 本地知識: {len(rows)} 筆")

    inserted = 0
    updated = 0
    failed = 0

    for row in rows:
        kid, title, layer, category, tags, trust, content_raw, content_aaak, \
            content_hash, source, summary, created_at, updated_at = row

        data = {
            'title': title,
            'layer': _parse_layer(layer),
            'category': category or 'general',
            'tags': _parse_tags(tags),
            'trust': trust or 0.5,
            'content_raw': content_raw or '',
            'content_aaak': content_aaak or '',
            'content_hash': content_hash or '',
            'summary': summary or '',
            'source': source or 'local',
            'updated_at': datetime.now().isoformat(),
        }

        try:
            # 直接用 title 查 Supabase
            existing = sb.table('guardrails_knowledge').select('id').eq('title', title).execute()
            if existing.data:
                for e in existing.data:
                    sb.table('guardrails_knowledge').update(data).eq('id', e['id']).execute()
                updated += len(existing.data)
            else:
                data['created_at'] = created_at or datetime.now().isoformat()
                sb.table('guardrails_knowledge').insert(data).execute()
                inserted += 1
        except Exception as e:
            err = str(e)
            if 'duplicate' in err.lower():
                # 可能 title 不完全一致的 dupe，用 ilike 模糊查
                try:
                    fuzzy = sb.table('guardrails_knowledge').select('id').ilike('title', f'%{title[:30]}%').execute()
                    if fuzzy.data:
                        for f in fuzzy.data:
                            sb.table('guardrails_knowledge').update(data).eq('id', f['id']).execute()
                        updated += len(fuzzy.data)
                    else:
                        failed += 1
                        print(f"  ❌ {title[:40]}: no match & insert blocked")
                except Exception as e2:
                    failed += 1
                    print(f"  ❌ {title[:40]}: {str(e2)[:80]}")
            else:
                failed += 1
                print(f"  ❌ {title[:40]}: {err[:80]}")

        if (inserted + updated + failed) % 50 == 0:
            print(f"  {inserted + updated + failed}/{len(rows)}...")

    db.close()

    final = sb.table('guardrails_knowledge').select('id').execute().data
    print(f"\n✅ Sync complete:")
    print(f"   Inserted: {inserted}")
    print(f"   Updated: {updated}")
    print(f"   Failed: {failed}")
    print(f"   Supabase total: {len(final)}")


if __name__ == "__main__":
    sync()
