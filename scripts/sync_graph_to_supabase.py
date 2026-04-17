#!/usr/bin/env python3
"""Sync graph data (entities, edges, entity_knowledge) from Lite → Supabase."""

import json
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from supabase import create_client

# --- Config ---
SUPABASE_URL = "https://example.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InptdHRscW1hbGxsdW9vcXhzd3F5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1OTM0Mzk0MywiZXhwIjoyMDc0OTE5OTQzfQ.9x5bQG-zMBwaFaCvlIxmcoIt2Cq0u9CHYHDsGdjyfPA"

DB_PATH = Path(__file__).resolve().parent.parent / "guardrails.db"

def get_supabase_id_map(sp_client):
    """Build mapping: Lite title → Supabase UUID."""
    rows = sp_client.table("guardrails_knowledge").select("id, title").execute()
    title_to_id = {}
    for r in rows.data:
        title_to_id[r["title"]] = r["id"]
    return title_to_id


def get_lite_data():
    """Read entities, edges, entity_knowledge from local SQLite."""
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    entities = [dict(r) for r in conn.execute("SELECT * FROM entities").fetchall()]
    edges = [dict(r) for r in conn.execute("SELECT * FROM edges").fetchall()]
    ek = [dict(r) for r in conn.execute("SELECT * FROM entity_knowledge").fetchall()]
    knowledge = [dict(r) for r in conn.execute("SELECT id, title FROM knowledge").fetchall()]

    conn.close()
    return entities, edges, ek, knowledge


def sync_entities(sp, entities, ek, knowledge_rows, lite_id_to_supabase_id):
    """Sync entities to Supabase, return mapping: lite entity_id → supabase entity id."""
    # Build lite knowledge_id → title
    lite_kid_to_title = {r["id"]: r["title"] for r in knowledge_rows}

    # Build entity_id → list of knowledge titles
    entity_knowledge_map = {}
    for row in ek:
        eid = row["entity_id"]
        kid = row["knowledge_id"]
        title = lite_kid_to_title.get(kid)
        if title and title in lite_id_to_supabase_id:
            entity_knowledge_map.setdefault(eid, []).append(lite_id_to_supabase_id[title])

    # Upsert entities
    entity_map = {}  # lite entity_id → supabase entity id
    batch = []
    for ent in entities:
        knowledge_ids = entity_knowledge_map.get(ent["id"], [])
        batch.append({
            "name": ent["name"],
            "entity_type": ent.get("entity_type", "tag"),
            "knowledge_ids": knowledge_ids,
            "mention_count": ent.get("mention_count", 1),
        })

    # Insert in batches of 50
    print(f"Syncing {len(batch)} entities to Supabase...")
    created = 0
    for i in range(0, len(batch), 50):
        chunk = batch[i:i+50]
        try:
            result = sp.table("gr_entities").upsert(chunk, on_conflict="name,entity_type").execute()
            created += len(result.data)
        except Exception as e:
            print(f"  Batch {i//50} error: {e}")
            # Try one by one
            for item in chunk:
                try:
                    r = sp.table("gr_entities").upsert(item, on_conflict="name,entity_type").execute()
                    created += 1
                except Exception as e2:
                    print(f"  Skipped entity '{item['name']}': {e2}")

    print(f"  Entities synced: {created}/{len(batch)}")

    # Build entity name→supabase_id mapping
    all_entities = sp.table("gr_entities").select("id, name, entity_type").execute()
    name_key_to_spid = {}
    for r in all_entities.data:
        name_key_to_spid[(r["name"], r["entity_type"])] = r["id"]

    # Map lite entity_id → supabase entity_id
    for ent in entities:
        key = (ent["name"], ent.get("entity_type", "tag"))
        sp_id = name_key_to_spid.get(key)
        if sp_id:
            entity_map[ent["id"]] = sp_id

    return entity_map


def sync_edges(sp, edges, lite_id_to_supabase_id, entity_map):
    """Sync edges to Supabase."""
    print(f"Syncing {len(edges)} edges to Supabase...")
    batch = []
    skipped = 0
    for edge in edges:
        source_sp = lite_id_to_supabase_id.get(edge["source_id"])
        target_sp = lite_id_to_supabase_id.get(edge["target_id"])
        if not source_sp or not target_sp:
            skipped += 1
            continue
        batch.append({
            "source_id": source_sp,
            "target_id": target_sp,
            "relation": edge.get("relation", "related_to"),
            "weight": edge.get("weight", 1.0),
            "auto_inferred": bool(edge.get("auto_inferred", False)),
        })

    # Insert in batches of 50
    created = 0
    for i in range(0, len(batch), 50):
        chunk = batch[i:i+50]
        try:
            result = sp.table("gr_edges").upsert(chunk, on_conflict="source_id,target_id,relation").execute()
            created += len(result.data)
        except Exception as e:
            print(f"  Batch {i//50} error: {e}")
            for item in chunk:
                try:
                    r = sp.table("gr_edges").upsert(item, on_conflict="source_id,target_id,relation").execute()
                    created += 1
                except Exception as e2:
                    print(f"  Skipped edge: {e2}")

    print(f"  Edges synced: {created}/{len(batch)} (skipped {skipped} with missing knowledge_id mapping)")


def sync_entity_knowledge(sp, ek, lite_id_to_supabase_id, entity_map):
    """Sync entity_knowledge junction table."""
    print(f"Syncing {len(ek)} entity_knowledge links to Supabase...")
    batch = []
    skipped = 0
    for row in ek:
        sp_entity_id = entity_map.get(row["entity_id"])
        kid_title = None  # Need title mapping
        sp_knowledge_id = lite_id_to_supabase_id.get(row["knowledge_id"])
        # knowledge_id in entity_knowledge refers to knowledge table id, not title
        # We need a different mapping here
        if not sp_entity_id:
            skipped += 1
            continue
        # knowledge_id mapping will be done below
        batch.append((row["entity_id"], row["knowledge_id"], sp_entity_id))

    # We need lite knowledge integer_id → supabase UUID
    # lite_id_to_supabase_id maps title → UUID, but entity_knowledge uses integer knowledge_id
    # Let's get the mapping from the knowledge table
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    knowledge_rows = [dict(r) for r in conn.execute("SELECT id, title FROM knowledge").fetchall()]
    conn.close()

    lite_intid_to_title = {r["id"]: r["title"] for r in knowledge_rows}
    lite_intid_to_sp_uuid = {}
    for k in knowledge_rows:
        sp_uuid = lite_id_to_supabase_id.get(k["title"])
        if sp_uuid:
            lite_intid_to_sp_uuid[k["id"]] = sp_uuid

    # Now build final batch
    final_batch = []
    skip2 = 0
    for (lite_eid, lite_kid, sp_eid) in batch:
        sp_kid = lite_intid_to_sp_uuid.get(lite_kid)
        if not sp_kid:
            skip2 += 1
            continue
        final_batch.append({
            "entity_id": sp_eid,
            "knowledge_id": sp_kid,
        })

    created = 0
    for i in range(0, len(final_batch), 50):
        chunk = final_batch[i:i+50]
        try:
            result = sp.table("gr_entity_knowledge").upsert(chunk, on_conflict="entity_id,knowledge_id").execute()
            created += len(result.data)
        except Exception as e:
            print(f"  Batch {i//50} error: {e}")
            for item in chunk:
                try:
                    r = sp.table("gr_entity_knowledge").upsert(item, on_conflict="entity_id,knowledge_id").execute()
                    created += 1
                except Exception as e2:
                    print(f"  Skipped ek link: {e2}")

    print(f"  Entity-knowledge links synced: {created}/{len(final_batch)} (skipped {skipped + skip2})")


def main():
    sp = create_client(SUPABASE_URL, SUPABASE_KEY)

    print("=== Guardrails Graph → Supabase Sync ===\n")

    # 1. Get Supabase knowledge id map (title → UUID)
    print("1. Loading Supabase knowledge IDs...")
    title_to_spid = get_supabase_id_map(sp)
    print(f"   Found {len(title_to_spid)} knowledge entries in Supabase")

    # 2. Get local data
    print("2. Loading local graph data...")
    entities, edges, ek, knowledge_rows = get_lite_data()
    print(f"   Entities: {len(entities)}, Edges: {len(edges)}, EK links: {len(ek)}, Knowledge: {len(knowledge_rows)}")

    # 3. Build int_key → supabase UUID mapping for edges
    #    edges.source_id/target_id are knowledge table integer IDs
    lite_intid_to_spid = {}
    for k in knowledge_rows:
        sp_uuid = title_to_spid.get(k["title"])
        if sp_uuid:
            lite_intid_to_spid[k["id"]] = sp_uuid
    print(f"   Mapped {len(lite_intid_to_spid)}/{len(knowledge_rows)} local knowledge IDs → Supabase UUIDs")

    # 4. Sync entities
    print("\n3. Syncing entities...")
    entity_map = sync_entities(sp, entities, ek, knowledge_rows, title_to_spid)
    print(f"   Mapped {len(entity_map)} lite entities → Supabase entity IDs")

    # 5. Sync entity_knowledge (before edges, since edges reference knowledge)
    print("\n4. Syncing entity_knowledge links...")
    sync_entity_knowledge(sp, ek, title_to_spid, entity_map)

    # 6. Sync edges — use int→UUID mapping, NOT title mapping
    print("\n5. Syncing edges...")
    sync_edges(sp, edges, lite_intid_to_spid, entity_map)

    # 6. Summary
    print("\n=== Sync Complete ===")
    # Verify counts
    for table in ["gr_entities", "gr_edges", "gr_entity_knowledge"]:
        count = sp.table(table).select("id", count="exact").execute()
        print(f"   {table}: {len(count.data)} rows")

    # Compare with local
    print(f"\n   Local: {len(entities)} entities, {len(edges)} edges, {len(ek)} ek links")


if __name__ == "__main__":
    main()