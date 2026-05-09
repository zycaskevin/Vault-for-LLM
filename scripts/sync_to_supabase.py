#!/usr/bin/env python3
"""
Sync Guardrails-knowledge local DB → Supabase
策略：每筆逐個處理，用 title/name 查 Supabase → 存在就更新，不存在就插入。
失敗時用 ilike 模糊匹配做 fallback。

用法：
  sync_to_supabase.py              # 同步知識表（預設）
  sync_to_supabase.py --skills     # 同步技能表
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts._utils import find_db_path, load_dotenv_cascade

# 載入 .env：優先用專案目錄的 .env，其次 ~/.env
load_dotenv_cascade()

from supabase import create_client
from vault.guardrails_db import GuardrailsDB

DB_PATH = str(find_db_path())


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


def _parse_capabilities(caps_str) -> list:
    """跟 _parse_tags 一樣的邏輯，用在技能能力欄位。"""
    if not caps_str:
        return []
    if isinstance(caps_str, list):
        return caps_str
    return [t.strip() for t in str(caps_str).split(',') if t.strip()]


def _get_sb_client():
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_ANON_KEY') or os.getenv('SUPABASE_KEY')
    if not url or not key:
        print("❌ SUPABASE_URL 或 SUPABASE_ANON_KEY 未設定")
        return None
    return create_client(url, key)


def sync(db_path=DB_PATH):
    sb = _get_sb_client()
    if not sb:
        return

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
            existing = sb.table('guardrails_knowledge').select('id').ilike('title', title).execute()
            if existing.data:
                for e in existing.data:
                    sb.table('guardrails_knowledge').update(data).eq('id', e['id']).execute()
                updated += len(existing.data)
            elif content_hash:
                # Fallback: match by content_hash (title may differ)
                hash_match = sb.table('guardrails_knowledge').select('id').eq('content_hash', content_hash).execute()
                if hash_match.data:
                    for h in hash_match.data:
                        sb.table('guardrails_knowledge').update(data).eq('id', h['id']).execute()
                    updated += len(hash_match.data)
                else:
                    data['created_at'] = created_at or datetime.now().isoformat()
                    sb.table('guardrails_knowledge').insert(data).execute()
                    inserted += 1
            else:
                data['created_at'] = created_at or datetime.now().isoformat()
                sb.table('guardrails_knowledge').insert(data).execute()
                inserted += 1
        except Exception as e:
            err = str(e)
            if 'duplicate' in err.lower():
                try:
                    # 1st: fuzzy title match
                    fuzzy = sb.table('guardrails_knowledge').select('id').ilike('title', f'%{title[:30]}%').execute()
                    if fuzzy.data:
                        for f in fuzzy.data:
                            sb.table('guardrails_knowledge').update(data).eq('id', f['id']).execute()
                        updated += len(fuzzy.data)
                    elif content_hash:
                        # 2nd: content_hash match
                        hash_match = sb.table('guardrails_knowledge').select('id').eq('content_hash', content_hash).execute()
                        if hash_match.data:
                            for h in hash_match.data:
                                sb.table('guardrails_knowledge').update(data).eq('id', h['id']).execute()
                            updated += len(hash_match.data)
                        else:
                            failed += 1
                            print(f"  ❌ {title[:40]}: no match & insert blocked")
                    else:
                        failed += 1
                        print(f"  ❌ {title[:40]}: no match & insert blocked")
                except Exception as e2:
                    failed += 1
                    print(f"  ❌ {title[:40]}: {str(e2)[:120]}")
            else:
                failed += 1
                print(f"  ❌ {title[:40]}: {err[:120]}")

        if (inserted + updated + failed) % 50 == 0:
            print(f"  {inserted + updated + failed}/{len(rows)}...")

    db.close()

    final = sb.table('guardrails_knowledge').select('id').execute().data
    print(f"\n✅ Knowledge sync complete:")
    print(f"   Inserted: {inserted}")
    print(f"   Updated: {updated}")
    print(f"   Failed: {failed}")
    print(f"   Supabase total: {len(final)}")


def sync_skills(db_path=DB_PATH):
    """
    同步技能表到 Supabase。
    Supabase 端需要先建立 guardrails_skills 表：
      CREATE TABLE guardrails_skills (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        version TEXT DEFAULT '1.0.0',
        agent_source TEXT DEFAULT '',
        category TEXT DEFAULT 'general',
        capabilities JSONB DEFAULT '[]',
        dependencies JSONB DEFAULT '[]',
        trust REAL DEFAULT 0.5,
        content_raw TEXT DEFAULT '',
        content_hash TEXT DEFAULT '',
        description TEXT DEFAULT '',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        last_synced TIMESTAMPTZ
      );
    """
    sb = _get_sb_client()
    if not sb:
        return

    db = GuardrailsDB(db_path)
    db.connect()

    rows = db.conn.execute(
        "SELECT id, name, version, agent_source, category, capabilities, dependencies, "
        "trust, content_raw, content_hash, description, created_at, updated_at "
        "FROM skills ORDER BY id"
    ).fetchall()
    print(f"🛠️  本地技能: {len(rows)} 筆")

    # 測試 Supabase 表是否存在
    try:
        sb.table('guardrails_skills').select('id', count='exact').limit(1).execute()
    except Exception as e:
        print(f"⚠️ Supabase guardrails_skills 表不存在或無權限。跳過技能同步。")
        print(f"   請手動執行上方註解中的 CREATE TABLE。")
        db.close()
        return

    inserted = 0
    updated = 0
    failed = 0

    for row in rows:
        sid, name, version, agent_source, category, capabilities, dependencies, \
            trust, content_raw, content_hash, description, created_at, updated_at = row

        data = {
            'name': name,
            'version': version or '1.0.0',
            'agent_source': agent_source or '',
            'category': category or 'general',
            'capabilities': _parse_capabilities(capabilities),
            'dependencies': _parse_capabilities(dependencies),
            'trust': trust or 0.5,
            'content_raw': content_raw or '',
            'content_hash': content_hash or '',
            'description': description or '',
            'updated_at': datetime.now().isoformat(),
        }

        try:
            existing = sb.table('guardrails_skills').select('id').eq('name', name).execute()
            if existing.data:
                for e in existing.data:
                    sb.table('guardrails_skills').update(data).eq('id', e['id']).execute()
                updated += len(existing.data)
            else:
                data['created_at'] = created_at or datetime.now().isoformat()
                sb.table('guardrails_skills').insert(data).execute()
                inserted += 1
        except Exception as e:
            failed += 1
            print(f"  ❌ {name[:40]}: {str(e)[:80]}")

    # 標記已同步
    for row in rows:
        try:
            db.mark_skill_synced(row[1])  # name
        except Exception:
            pass

    db.close()

    try:
        final = sb.table('guardrails_skills').select('id').execute().data
    except Exception:
        final = []
    print(f"\n✅ Skill sync complete:")
    print(f"   Inserted: {inserted}")
    print(f"   Updated: {updated}")
    print(f"   Failed: {failed}")
    print(f"   Supabase total: {len(final)}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sync local DB → Supabase")
    parser.add_argument("--skills", action="store_true", help="同步技能表（而非知識表）")
    args = parser.parse_args()

    if args.skills:
        sync_skills()
    else:
        sync()
