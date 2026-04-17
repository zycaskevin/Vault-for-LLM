#!/usr/bin/env python3
"""
Vault for LLM 每日知識同步腳本。
從 agent runtime 記憶系統（fact_store + MEMORY.md）提取新知識，寫入本地百科。

策略：
1. 掃描 fact_store 中的新事實
2. 檢查是否已有相同標題
3. 新增知識 + 嵌入
4. 重建圖譜（如果新增 > 5 筆）
"""
import os, sys, json, re, hashlib
from datetime import datetime, timezone

sys.path.insert(0, "/home/user/Guardrails-knowledge")
from vault.guardrails_db import GuardrailsDB
from vault.guardrails_embed import create_embedding_provider
from vault.guardrails_graph import GuardrailsGraph

DB_PATH = "/home/user/Guardrails-knowledge/guardrails.db"

def extract_facts_from_memory():
    """從 MEMORY.md 和 fact_store 提取知識條目候選。"""
    candidates = []
    
    # 2. 從 raw/ 目錄掃描新檔案（尚未 compile 的）
    raw_dir = os.path.join(BASE, "raw")
    if os.path.exists(raw_dir):
        # 取得已經在 DB 中的 source 標記
        compiled_sources = set()
        for row in db.conn.execute(
            "SELECT DISTINCT source FROM knowledge"
        ).fetchall():
            compiled_sources.add(row[0])
        
        for fname in os.listdir(raw_dir):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(raw_dir, fname)
            # 用檔名作為 source 標記
            if fname in compiled_sources:
                continue
            
            try:
                content = open(fpath, encoding="utf-8").read()
                fm, body = parse_frontmatter(content)
                text = body if body else content
                title = fm.get("title", os.path.splitext(fname)[0])
                
                candidates.append({
                    "title": title,
                    "content": text[:5000],
                    "layer": fm.get("layer", "L3"),
                    "category": fm.get("category", "technique"),
                    "tags": fm.get("tags", ""),
                    "trust": float(fm.get("trust", 0.5)),
                    "source": fname,
                })
            except Exception as e:
                print(f"⚠️ 讀取 {fname} 失敗: {e}")
    
    # 1. 從 MEMORY.md 提取要點
    memory_path = os.path.expanduser("~/.agent-runtime/MEMORY.md")
    if os.path.exists(memory_path):
        try:
            with open(memory_path, encoding="utf-8") as f:
                content = f.read()
            # 按 § 分段
            sections = re.split(r'\n§\s*', content)
            for section in sections:
                section = section.strip()
                if not section or len(section) < 30:
                    continue
                first_line = section.split("\n")[0].strip()[:60]
                title = f"[MEM] {first_line}"
                candidates.append({
                    "title": title,
                    "content": section[:5000],
                    "layer": "L3",
                    "category": "memory-extraction",
                    "tags": "memory,daily-sync",
                    "trust": 0.6,
                    "source": "memory-sync",
                })
        except Exception as e:
            print(f"⚠️ MEMORY.md 讀取失敗: {e}")
    
    return candidates

def main():
    print(f"🔄 Guardrails 知識同步 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    db = GuardrailsDB(DB_PATH)
    db.connect()
    
    # 取得現有標題集合（用於去重）
    existing_titles = set()
    for row in db.conn.execute("SELECT title FROM knowledge").fetchall():
        existing_titles.add(row[0])
    print(f"📚 現有知識: {len(existing_titles)} 筆")
    
    # 提取候選
    candidates = extract_facts_from_memory()
    print(f"🔍 候選知識: {len(candidates)} 筆")
    
    # 去重 + 新增
    embed = create_embedding_provider(provider="onnx", model_key="mix")
    added = 0
    skipped = 0
    
    for c in candidates:
        if c["title"] in existing_titles:
            skipped += 1
            continue
        
        # Content hash 去重
        content_hash = hashlib.sha256(c["content"].encode()).hexdigest()[:16]
        hash_exists = db.conn.execute(
            "SELECT id FROM knowledge WHERE content_hash=?", (content_hash,)
        ).fetchone()
        if hash_exists:
            skipped += 1
            continue
        
        kid = db.add_knowledge(
            title=c["title"],
            content_raw=c["content"][:5000],
            layer=c["layer"],
            category=c["category"],
            tags=c["tags"],
            trust=c["trust"],
            source=c["source"],
            content_aaak=c["content"][:150],
        )
        
        try:
            vec = embed.encode(c["content"][:500])[0]
            db.add_embedding(kid, vec)
        except Exception:
            pass
        
        added += 1
        existing_titles.add(c["title"])
    
    print(f"✅ 新增: {added}, 跳過: {skipped}")
    
    # 重建圖譜（如果有新增）
    if added > 0:
        print("🕸️ 重建圖譜...")
        db.conn.execute("DELETE FROM edges")
        db.conn.execute("DELETE FROM entity_knowledge")
        db.conn.execute("DELETE FROM entities")
        db.conn.commit()
        
        g = GuardrailsGraph(db)
        result = g.infer_all()
        print(f"   實體: {result['entities_created']}, 邊: {result['edges_created']}")
    
    stats = db.stats()
    print(f"\n📊 最終: {stats['knowledge_count']} 筆, {stats['embedding_count']} 嵌入, {stats['db_size_mb']} MB")
    db.close()

if __name__ == "__main__":
    main()