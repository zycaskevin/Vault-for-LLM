#!/usr/bin/env python3
"""Fix missing gr_entity_knowledge links — insert only links not yet in Supabase."""

import sqlite3
from pathlib import Path
from supabase import create_client

SUPABASE_URL = "https://zmttlqmallluooqxswqy.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InptdHRscW1hbGxsdW9vcXhzd3F5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1OTM0Mzk0MywiZXhwIjoyMDc0OTE5OTQzfQ.9x5bQG-zMBwaFaCvlIxmcoIt2Cq0u9CHYHDsGdjyfPA"

DB_PATH = Path(__file__).resolve().parent.parent / "guardrails.db"

def main():
    sp = create_client(SUPABASE_URL, SUPABASE_KEY)

    # 1. Load Supabase data
    print("Loading Supabase mappings...")
    titles = {r["title"]: r["id"] for r in sp.table("guardrails_knowledge").select("id,title").execute().data}
    
    # Get ALL existing EK links (handle pagination with range)
    existing_ek = set()
    offset = 0
    while True:
        batch = sp.table("gr_entity_knowledge").select("entity_id,knowledge_id").range(offset, offset + 999).execute()
        if not batch.data:
            break
        for row in batch.data:
            existing_ek.add((row["entity_id"], row["knowledge_id"]))
        offset += 1000
    
    print(f"  Existing EK links: {len(existing_ek)}")

    # 2. Build entity name→sp_id mapping
    sp_ents = sp.table("gr_entities").select("id,name,entity_type").execute().data
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
            r = sp.table("gr_entity_knowledge").upsert(
                chunk, on_conflict="entity_id,knowledge_id"
            ).execute()
            inserted += len(r.data)
        except Exception as e:
            print(f"  Batch {i//25} error: {e}")
            for item in chunk:
                try:
                    sp.table("gr_entity_knowledge").upsert(
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
        batch = sp.table("gr_entity_knowledge").select("id").range(offset, offset + 999).execute()
        if not batch.data:
            break
        total += len(batch.data)
        offset += 1000
    print(f"\nTotal gr_entity_knowledge rows: {total}")


if __name__ == "__main__":
    main()