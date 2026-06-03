#!/usr/bin/env python3
"""Fix missing remote graph entity-knowledge links in optional Supabase sync."""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts._utils import find_db_path, load_dotenv_cascade
load_dotenv_cascade()

try:
    from supabase import create_client
except Exception:  # optional dependency for remote sync only
    create_client = None

# 從環境變數讀取，勿硬編碼 key
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_ANON_KEY", "")

DB_PATH = find_db_path()
KNOWLEDGE_TABLE = os.getenv("VAULT_SUPABASE_KNOWLEDGE_TABLE", "vault_knowledge")
GRAPH_ENTITIES_TABLE = os.getenv("VAULT_SUPABASE_GRAPH_ENTITIES_TABLE", "vault_graph_entities")
GRAPH_ENTITY_KNOWLEDGE_TABLE = os.getenv(
    "VAULT_SUPABASE_GRAPH_ENTITY_KNOWLEDGE_TABLE",
    "vault_graph_entity_knowledge",
)


def _get_sb_client():
    if create_client is None:
        print("❌ Supabase Python client 未安裝，無法執行遠端同步")
        return None
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ SUPABASE_URL 或 SUPABASE_SERVICE_KEY（或 SUPABASE_ANON_KEY）未設定")
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def main():
    sp = _get_sb_client()
    if not sp:
        return None

    # 1. Load Supabase data
    print("Loading Supabase mappings...")
    titles = {r["title"]: r["id"] for r in sp.table(KNOWLEDGE_TABLE).select("id,title").execute().data}
    
    # Get ALL existing EK links (handle pagination with range)
    existing_ek = set()
    offset = 0
    while True:
        batch = sp.table(GRAPH_ENTITY_KNOWLEDGE_TABLE).select("entity_id,knowledge_id").range(offset, offset + 999).execute()
        if not batch.data:
            break
        for row in batch.data:
            existing_ek.add((row["entity_id"], row["knowledge_id"]))
        offset += 1000
    
    print(f"  Existing EK links: {len(existing_ek)}")

    # 2. Build entity name→sp_id mapping
    sp_ents = sp.table(GRAPH_ENTITIES_TABLE).select("id,name,entity_type").execute().data
    name_key_to_sp_eid = {(r["name"], r["entity_type"]): r["id"] for r in sp_ents}

    # 3. Load local data
    print("Loading local data...")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    ek_rows = [dict(r) for r in conn.execute("SELECT * FROM entity_knowledge").fetchall()]
    knowledge_rows = [dict(r) for r in conn.execute("SELECT id, title FROM knowledge").fetchall()]
    entity_rows = [dict(r) for r in conn.execute("SELECT * FROM entities").fetchall()]
    conn.close()

    # 4. Build mappings
    lite_kid_to_spid = {r["id"]: titles[r["title"]] for r in knowledge_rows if r["title"] in titles}
    lite_eid_to_sp_eid = {}
    for e in entity_rows:
        key = (e["name"], e.get("entity_type", "tag"))
        if key in name_key_to_sp_eid:
            lite_eid_to_sp_eid[e["id"]] = name_key_to_sp_eid[key]

    # 5. Find missing links
    missing = []
    skipped_no_entity = 0
    skipped_no_knowledge = 0
    skipped_duplicate = 0
    for row in ek_rows:
        sp_eid = lite_eid_to_sp_eid.get(row["entity_id"])
        sp_kid = lite_kid_to_spid.get(row["knowledge_id"])
        if not sp_eid:
            skipped_no_entity += 1
            continue
        if not sp_kid:
            skipped_no_knowledge += 1
            continue
        if (sp_eid, sp_kid) in existing_ek:
            skipped_duplicate += 1
            continue
        missing.append({"entity_id": sp_eid, "knowledge_id": sp_kid})

    print(f"  Missing links to insert: {len(missing)}")
    print(f"  Skipped: no_entity={skipped_no_entity}, no_knowledge={skipped_no_knowledge}, duplicate={skipped_duplicate}")

    if not missing:
        print("Nothing to insert!")
        return

    # 6. Insert in batches of 25
    print("Inserting missing links...")
    inserted = 0
    errors = 0
    for i in range(0, len(missing), 25):
        chunk = missing[i:i+25]
        try:
            r = sp.table(GRAPH_ENTITY_KNOWLEDGE_TABLE).upsert(
                chunk, on_conflict="entity_id,knowledge_id"
            ).execute()
            inserted += len(r.data)
        except Exception as e:
            print(f"  Batch {i//25} error: {e}")
            for item in chunk:
                try:
                    sp.table(GRAPH_ENTITY_KNOWLEDGE_TABLE).upsert(
                        item, on_conflict="entity_id,knowledge_id"
                    ).execute()
                    inserted += 1
                except:
                    errors += 1
        if (i // 25) % 5 == 0:
            print(f"  Progress: {min(i+25, len(missing))}/{len(missing)}")

    print(f"  Inserted: {inserted}, Errors: {errors}")

    # 7. Verify
    total = 0
    offset = 0
    while True:
        batch = sp.table(GRAPH_ENTITY_KNOWLEDGE_TABLE).select("id").range(offset, offset + 999).execute()
        if not batch.data:
            break
        total += len(batch.data)
        offset += 1000
    print(f"\nTotal {GRAPH_ENTITY_KNOWLEDGE_TABLE} rows: {total}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fix missing remote graph entity-knowledge links in optional Supabase sync."
    )
    parser.add_argument("--db", dest="db_path", help="Local vault.db path (default: auto-discover).")
    args = parser.parse_args()
    if args.db_path:
        DB_PATH = Path(args.db_path).expanduser().resolve()
    ok = main()
    sys.exit(0 if ok is not False else 1)
