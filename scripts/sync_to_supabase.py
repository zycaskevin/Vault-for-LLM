#!/usr/bin/env python3
"""
Sync Vault-knowledge local DB → Supabase
策略：每筆逐個處理，用 title/name 查 Supabase → 存在就更新，不存在就插入。
失敗時用 ilike 模糊匹配做 fallback。

用法：
  sync_to_supabase.py              # 同步知識表 metadata/summary/hash（預設不含全文）
  sync_to_supabase.py --include-content  # 明確同步 content_raw/content_aaak
  sync_to_supabase.py --skills     # 同步技能表 metadata/hash（預設不含技能全文）
  sync_to_supabase.py --document-map  # 同步 Document Map 表
  sync_to_supabase.py --health        # 同步 Vault health metrics snapshot
"""

import os
import sys
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts._utils import find_db_path, load_dotenv_cascade  # noqa: E402

# 載入 .env：優先用目前 project directory 的 .env，其次 ~/.env。
# CLI --db 會在 __main__ 解析後再補載一次指定 db 旁邊的 .env。
load_dotenv_cascade()

try:
    from supabase import create_client
except Exception:  # optional dependency for remote sync only
    create_client = None

from vault.db import VaultDB  # noqa: E402
from vault.health import (  # noqa: E402
    DEFAULT_SAMPLE_LIMIT,
    VaultHealthMetrics,
    collect_vault_health_metrics,
)
from vault.privacy import scan_privacy  # noqa: E402

DB_PATH = str(find_db_path())

DOCUMENT_MAP_NODE_TABLE = os.getenv('VAULT_SUPABASE_NODE_TABLE', 'vault_knowledge_nodes')
DOCUMENT_MAP_CLAIM_TABLE = os.getenv('VAULT_SUPABASE_CLAIM_TABLE', 'vault_knowledge_claims')
VAULT_HEALTH_TABLE = os.getenv('VAULT_SUPABASE_HEALTH_TABLE', 'vault_health_metrics')
KNOWLEDGE_TABLE = os.getenv('VAULT_SUPABASE_KNOWLEDGE_TABLE', 'vault_knowledge')
SKILLS_TABLE = os.getenv('VAULT_SUPABASE_SKILLS_TABLE', 'vault_skills')

DOCUMENT_MAP_NODE_COLUMNS = [
    'knowledge_id',
    'node_uid',
    'parent_uid',
    'level',
    'heading',
    'path',
    'summary',
    'line_start',
    'line_end',
    'token_estimate',
    'content_hash',
    'created_at',
    'updated_at',
]

DOCUMENT_MAP_CLAIM_COLUMNS = [
    'knowledge_id',
    'node_uid',
    'claim_uid',
    'claim',
    'claim_type',
    'line_start',
    'line_end',
    'confidence',
    'source',
    'content_hash',
    'created_at',
    'updated_at',
]

DOCUMENT_MAP_CONTEXT_COLUMNS = [
    'knowledge_title',
    'knowledge_source',
    'knowledge_content_hash',
]


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


def _nonempty_content_hash(existing_hash, *parts) -> str:
    """Return a deterministic non-empty hash for Supabase NOT NULL schemas."""
    cleaned_hash = str(existing_hash or "").strip()
    if cleaned_hash:
        return cleaned_hash
    text = "\n".join(str(part or "") for part in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _get_sb_client():
    if create_client is None:
        print("❌ Supabase Python client 未安裝，無法執行遠端同步")
        return None
    url = os.getenv('SUPABASE_URL')
    key = (
        os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        or os.getenv('SUPABASE_ANON_KEY')
        or os.getenv('SUPABASE_KEY')
    )
    if not url or not key:
        print("❌ SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY/SUPABASE_ANON_KEY 未設定")
        return None
    return create_client(url, key)


def _check_document_map_tables(sb) -> bool:
    """Return False with an actionable message if remote map tables are unavailable."""
    missing = []
    for table_name in (DOCUMENT_MAP_NODE_TABLE, DOCUMENT_MAP_CLAIM_TABLE):
        try:
            sb.table(table_name).select('id').limit(1).execute()
        except Exception as e:
            missing.append((table_name, str(e)[:160]))

    if not missing:
        return True

    print("❌ Supabase Document Map tables 不存在或無權限，無法同步。")
    print(
        f"   請先建立 tables: {DOCUMENT_MAP_NODE_TABLE}, {DOCUMENT_MAP_CLAIM_TABLE} "
        "（需支援 nodes UNIQUE(knowledge_id,node_uid)、claims UNIQUE(knowledge_id,claim_uid)）。"
    )
    for table_name, reason in missing:
        print(f"   - {table_name}: {reason}")
    return False


def _upsert_by_key(sb, table_name: str, payload: dict, key_fields: tuple[str, ...]) -> str:
    """Small select→update/insert upsert to avoid duplicate natural keys."""
    query = sb.table(table_name).select('id')
    for field in key_fields:
        query = query.eq(field, payload[field])
    existing = query.execute()

    if existing.data:
        for row in existing.data:
            sb.table(table_name).update(payload).eq('id', row['id']).execute()
        return 'updated'

    sb.table(table_name).insert(payload).execute()
    return 'inserted'


def _upsert_vault_health_by_check_date(sb, payload: dict) -> str:
    """Upsert remote Vault health snapshots by check_date without requiring an id column."""
    check_date = payload['check_date']
    existing = (
        sb.table(VAULT_HEALTH_TABLE)
        .select('check_date')
        .eq('check_date', check_date)
        .execute()
    )

    if existing.data:
        sb.table(VAULT_HEALTH_TABLE).update(payload).eq('check_date', check_date).execute()
        return 'updated'

    sb.table(VAULT_HEALTH_TABLE).insert(payload).execute()
    return 'inserted'


def _content_allowed_for_remote(text: str) -> bool:
    return scan_privacy(text or "").get("status") != "fail"


def _knowledge_sync_payload(row, *, include_content: bool = False) -> dict:
    kid, title, layer, category, tags, trust, content_raw, content_aaak, \
        content_hash, source, summary, scope, sensitivity, owner_agent, \
        allowed_agents, memory_type, expires_at, created_at, updated_at = row
    content_raw = content_raw or ''
    content_aaak = content_aaak or ''
    include_raw = include_content and _content_allowed_for_remote(
        "\n".join([str(title or ""), str(tags or ""), content_raw, content_aaak])
    )
    return {
        'title': title,
        'layer': _parse_layer(layer),
        'category': category or 'general',
        'tags': _parse_tags(tags),
        'trust': trust or 0.5,
        'content_raw': content_raw if include_raw else '',
        'content_aaak': content_aaak if include_raw else '',
        'content_hash': _nonempty_content_hash(
            content_hash,
            content_raw,
            content_aaak,
            summary,
            title,
        ),
        'summary': summary or '',
        'source': source or 'local',
        'scope': scope or 'project',
        'sensitivity': sensitivity or 'low',
        'owner_agent': owner_agent or '',
        'allowed_agents': _parse_tags(allowed_agents),
        'memory_type': memory_type or 'knowledge',
        'expires_at': expires_at or None,
        'updated_at': datetime.now().isoformat(),
    }


def _skill_sync_payload(row, *, include_content: bool = False) -> dict:
    sid, name, version, agent_source, category, capabilities, dependencies, \
        trust, content_raw, content_hash, description, created_at, updated_at = row
    content_raw = content_raw or ''
    include_raw = include_content and _content_allowed_for_remote(
        "\n".join([str(name or ""), str(capabilities or ""), content_raw])
    )
    return {
        'name': name,
        'version': version or '1.0.0',
        'agent_source': agent_source or '',
        'category': category or 'general',
        'capabilities': _parse_capabilities(capabilities),
        'dependencies': _parse_capabilities(dependencies),
        'trust': trust or 0.5,
        'content_raw': content_raw if include_raw else '',
        'content_hash': _nonempty_content_hash(content_hash, content_raw, description, name),
        'description': description or '',
        'updated_at': datetime.now().isoformat(),
    }


def sync(db_path=DB_PATH, *, include_content: bool = False):
    sb = _get_sb_client()
    if not sb:
        return

    db = VaultDB(db_path)
    db.connect()

    rows = db.conn.execute(
        "SELECT id, title, layer, category, tags, trust, content_raw, content_aaak, "
        "content_hash, source, summary, scope, sensitivity, owner_agent, "
        "allowed_agents, memory_type, expires_at, created_at, updated_at "
        "FROM knowledge ORDER BY id"
    ).fetchall()
    print(f"📚 本地知識: {len(rows)} 筆")

    inserted = 0
    updated = 0
    failed = 0

    for row in rows:
        kid, title, layer, category, tags, trust, content_raw, content_aaak, \
            content_hash, source, summary, scope, sensitivity, owner_agent, \
            allowed_agents, memory_type, expires_at, created_at, updated_at = row
        data = _knowledge_sync_payload(row, include_content=include_content)

        try:
            sync_hash = data['content_hash']
            existing = sb.table(KNOWLEDGE_TABLE).select('id').ilike('title', title).execute()
            if existing.data:
                for e in existing.data:
                    sb.table(KNOWLEDGE_TABLE).update(data).eq('id', e['id']).execute()
                updated += len(existing.data)
            elif sync_hash:
                # Fallback: match by content_hash (title may differ)
                hash_match = sb.table(KNOWLEDGE_TABLE).select('id').eq('content_hash', sync_hash).execute()
                if hash_match.data:
                    for h in hash_match.data:
                        sb.table(KNOWLEDGE_TABLE).update(data).eq('id', h['id']).execute()
                    updated += len(hash_match.data)
                else:
                    data['created_at'] = created_at or datetime.now().isoformat()
                    sb.table(KNOWLEDGE_TABLE).insert(data).execute()
                    inserted += 1
            else:
                data['created_at'] = created_at or datetime.now().isoformat()
                sb.table(KNOWLEDGE_TABLE).insert(data).execute()
                inserted += 1
        except Exception as e:
            err = str(e)
            if 'duplicate' in err.lower():
                try:
                    # 1st: fuzzy title match
                    fuzzy = sb.table(KNOWLEDGE_TABLE).select('id').ilike('title', f'%{title[:30]}%').execute()
                    if fuzzy.data:
                        for f in fuzzy.data:
                            sb.table(KNOWLEDGE_TABLE).update(data).eq('id', f['id']).execute()
                        updated += len(fuzzy.data)
                    elif data['content_hash']:
                        # 2nd: content_hash match
                        hash_match = sb.table(KNOWLEDGE_TABLE).select('id').eq('content_hash', data['content_hash']).execute()
                        if hash_match.data:
                            for h in hash_match.data:
                                sb.table(KNOWLEDGE_TABLE).update(data).eq('id', h['id']).execute()
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

    final = sb.table(KNOWLEDGE_TABLE).select('id').execute().data
    print("\n✅ Knowledge sync complete:")
    print(f"   Inserted: {inserted}")
    print(f"   Updated: {updated}")
    print(f"   Failed: {failed}")
    print(f"   Supabase total: {len(final)}")


def sync_skills(db_path=DB_PATH, *, include_content: bool = False):
    """
    同步技能表到 Supabase。
    Supabase 端需要先建立 vault_skills 表：
      CREATE TABLE vault_skills (
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

    db = VaultDB(db_path)
    db.connect()

    rows = db.conn.execute(
        "SELECT id, name, version, agent_source, category, capabilities, dependencies, "
        "trust, content_raw, content_hash, description, created_at, updated_at "
        "FROM skills ORDER BY id"
    ).fetchall()
    print(f"🛠️  本地技能: {len(rows)} 筆")

    # 測試 Supabase 表是否存在
    try:
        sb.table(SKILLS_TABLE).select('id', count='exact').limit(1).execute()
    except Exception:
        print(f"⚠️ Supabase {SKILLS_TABLE} 表不存在或無權限。跳過技能同步。")
        print("   請手動執行上方註解中的 CREATE TABLE。")
        db.close()
        return

    inserted = 0
    updated = 0
    failed = 0

    for row in rows:
        sid, name, version, agent_source, category, capabilities, dependencies, \
            trust, content_raw, content_hash, description, created_at, updated_at = row
        data = _skill_sync_payload(row, include_content=include_content)

        try:
            existing = sb.table(SKILLS_TABLE).select('id').eq('name', name).execute()
            if existing.data:
                for e in existing.data:
                    sb.table(SKILLS_TABLE).update(data).eq('id', e['id']).execute()
                updated += len(existing.data)
            else:
                data['created_at'] = created_at or datetime.now().isoformat()
                sb.table(SKILLS_TABLE).insert(data).execute()
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
        final = sb.table(SKILLS_TABLE).select('id').execute().data
    except Exception:
        final = []
    print("\n✅ Skill sync complete:")
    print(f"   Inserted: {inserted}")
    print(f"   Updated: {updated}")
    print(f"   Failed: {failed}")
    print(f"   Supabase total: {len(final)}")


def sync_document_map(db_path=DB_PATH):
    """同步 SQLite Document Map tables 到 Supabase。"""
    sb = _get_sb_client()
    if not sb:
        return None

    db = VaultDB(db_path)
    db.connect()

    try:
        if not _check_document_map_tables(sb):
            return None

        node_rows = db.conn.execute(
            "SELECT "
            + ", ".join(f"n.{col}" for col in DOCUMENT_MAP_NODE_COLUMNS)
            + ", k.title AS knowledge_title, k.source AS knowledge_source, "
            + "k.content_hash AS knowledge_content_hash "
            + "FROM knowledge_nodes n "
            + "JOIN knowledge k ON k.id = n.knowledge_id "
            + "ORDER BY n.knowledge_id, n.node_uid"
        ).fetchall()
        claim_rows = db.conn.execute(
            "SELECT "
            + ", ".join(f"c.{col}" for col in DOCUMENT_MAP_CLAIM_COLUMNS)
            + ", k.title AS knowledge_title, k.source AS knowledge_source, "
            + "k.content_hash AS knowledge_content_hash "
            + "FROM knowledge_claims c "
            + "JOIN knowledge k ON k.id = c.knowledge_id "
            + "ORDER BY c.knowledge_id, c.claim_uid"
        ).fetchall()

        print(f"🗺️  本地 Document Map nodes: {len(node_rows)} 筆")
        print(f"🧾 本地 Document Map claims: {len(claim_rows)} 筆")

        stats = {
            'nodes_inserted': 0,
            'nodes_updated': 0,
            'nodes_failed': 0,
            'claims_inserted': 0,
            'claims_updated': 0,
            'claims_failed': 0,
        }

        for row in node_rows:
            payload = {key: row[key] for key in DOCUMENT_MAP_NODE_COLUMNS + DOCUMENT_MAP_CONTEXT_COLUMNS}
            try:
                action = _upsert_by_key(sb, DOCUMENT_MAP_NODE_TABLE, payload, ('knowledge_id', 'node_uid'))
                stats[f"nodes_{action}"] += 1
            except Exception as e:
                stats['nodes_failed'] += 1
                print(f"  ❌ node {row['knowledge_id']}/{row['node_uid']}: {str(e)[:120]}")

        for row in claim_rows:
            payload = {key: row[key] for key in DOCUMENT_MAP_CLAIM_COLUMNS + DOCUMENT_MAP_CONTEXT_COLUMNS}
            try:
                action = _upsert_by_key(sb, DOCUMENT_MAP_CLAIM_TABLE, payload, ('knowledge_id', 'claim_uid'))
                stats[f"claims_{action}"] += 1
            except Exception as e:
                stats['claims_failed'] += 1
                print(f"  ❌ claim {row['knowledge_id']}/{row['claim_uid']}: {str(e)[:120]}")

        print("\n✅ Document Map sync complete:")
        print(f"   Nodes inserted: {stats['nodes_inserted']}")
        print(f"   Nodes updated: {stats['nodes_updated']}")
        print(f"   Nodes failed: {stats['nodes_failed']}")
        print(f"   Claims inserted: {stats['claims_inserted']}")
        print(f"   Claims updated: {stats['claims_updated']}")
        print(f"   Claims failed: {stats['claims_failed']}")
        return stats
    finally:
        db.close()


def _health_check_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _vault_health_payload(
    metrics: VaultHealthMetrics,
    check_date: str | None = None,
) -> dict:
    """Map Document Map health metrics into the public remote health schema.

    SQLite remains the source of truth; this optional Supabase payload is a
    compact sync/read target. The default public table name is configurable via
    VAULT_SUPABASE_HEALTH_TABLE and intentionally uses neutral Vault naming.
    The metric names below preserve the existing lightweight schema shape:
    - total_knowledge = total_entries
    - convergence_rate = map_coverage * 100
    - avg_freshness = citation_coverage * 100
    - contradiction_count = read_range_over_limit_violations
    - gap_count = entries_without_nodes + entries_without_claims
    """
    return {
        'check_date': check_date or _health_check_date(),
        'total_knowledge': metrics.total_entries,
        'convergence_rate': metrics.map_coverage * 100,
        'avg_freshness': metrics.citation_coverage * 100,
        'contradiction_count': metrics.read_range_over_limit_violations,
        'gap_count': metrics.entries_without_nodes + metrics.entries_without_claims,
    }


def _print_vault_health(metrics: VaultHealthMetrics, payload: dict) -> None:
    print("📊 Vault Document Map health:")
    print(f"   Total entries: {metrics.total_entries}")
    print(f"   Entries with nodes: {metrics.entries_with_nodes}")
    print(f"   Entries without nodes: {metrics.entries_without_nodes}")
    print(f"   Entries with claims: {metrics.entries_with_claims}")
    print(f"   Entries without claims: {metrics.entries_without_claims}")
    print(f"   Sampled search results: {metrics.sampled_search_results}")
    print(f"   Search results with best span: {metrics.search_results_with_best_span}")
    print(f"   Map coverage: {metrics.map_coverage:.2%}")
    print(f"   Claim coverage: {metrics.claim_coverage:.2%}")
    print(f"   Citation coverage: {metrics.citation_coverage:.2%}")
    print(f"   Read-range over-limit violations: {metrics.read_range_over_limit_violations}")
    print("   Remote health payload mapping:")
    print(f"     total_knowledge = {payload['total_knowledge']}")
    print(f"     convergence_rate = {payload['convergence_rate']:.2f}")
    print(f"     avg_freshness = {payload['avg_freshness']:.2f}")
    print(f"     contradiction_count = {payload['contradiction_count']}")
    print(f"     gap_count = {payload['gap_count']}")


def sync_vault_health(
    db_path=DB_PATH,
    sample_limit=DEFAULT_SAMPLE_LIMIT,
    sb_client=None,
    check_date: str | None = None,
):
    """Collect local Document Map health and upsert one optional remote snapshot."""
    sb = sb_client or _get_sb_client()
    if not sb:
        return None

    metrics = collect_vault_health_metrics(db_path, sample_limit=sample_limit)
    payload = _vault_health_payload(metrics, check_date=check_date)
    _print_vault_health(metrics, payload)

    action = _upsert_vault_health_by_check_date(sb, payload)
    print(f"\n✅ Vault health sync complete: {action}")
    return {
        'action': action,
        'payload': payload,
        'metrics': metrics.to_dict(),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sync local DB → Supabase")
    parser.add_argument("--db", default=DB_PATH, help="vault.db 路徑；預設從 VAULT_PATH/cwd 搜尋")
    parser.add_argument("--skills", action="store_true", help="同步技能表（而非知識表）")
    parser.add_argument(
        "--include-content",
        action="store_true",
        help="明確同步 content_raw/content_aaak；預設只同步 metadata/summary/hash",
    )
    parser.add_argument("--document-map", action="store_true", help="同步 Document Map 表（而非知識表）")
    parser.add_argument(
        "--health",
        "--vault-health",
        dest="health",
        action="store_true",
        help="同步 Vault / Document Map remote health snapshot",
    )
    parser.add_argument(
        "--health-sample-limit",
        type=int,
        default=DEFAULT_SAMPLE_LIMIT,
        help="Document Map citation health sampling size（預設 20）",
    )
    args = parser.parse_args()
    load_dotenv_cascade(str(Path(args.db).expanduser().resolve().parent / ".env"))

    if args.skills:
        sync_skills(args.db, include_content=args.include_content)
    if args.document_map:
        sync_document_map(args.db)
    if args.health:
        sync_vault_health(args.db, sample_limit=args.health_sample_limit)
    if not (args.skills or args.document_map or args.health):
        sync(args.db, include_content=args.include_content)
