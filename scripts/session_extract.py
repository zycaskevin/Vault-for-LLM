#!/usr/bin/env python3
"""
從最近的 Hermes 對話 session 中提取知識條目，寫入 Guardrails Lite DB。

策略：
1. 掃描最近 N 個 session 的對話
2. 用關鍵字和模式偵測「知識點」（踩坑、解法、錯誤、決策）
3. 去重後寫入 DB
4. 如果新增 > 5 筆，重建圖譜

用法：
  python session_extract.py              # 掃描最近 10 個 session
  python session_extract.py --days 3     # 掃描最近 3 天的 session
  python session_extract.py --dry-run    # 只顯示不寫入
"""
import os, sys, re, json, sqlite3
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, "/home/zycas/Guardrails-knowledge")
from guardrails_lite.guardrails_db import GuardrailsDB
from guardrails_lite.guardrails_embed import create_embedding_provider
from guardrails_lite.guardrails_graph import GuardrailsGraph

HERMES_DB = os.path.expanduser("~/.hermes/state.db")
GR_DB = "/home/zycas/Guardrails-knowledge/guardrails.db"
RAW_DIR = "/home/zycas/Guardrails-knowledge/raw"

# ── 知識偵測模式 ──────────────────────────────────────────

# 模式：這些關鍵字出現時代表可能有知識點
KNOWLEDGE_PATTERNS = [
    r"(?:踩坑|坑|陷阱|pitfall|gotcha)",
    r"(?:解法|解決|修復|fixed|solution|workaround)",
    r"(?:錯誤|error|bug|失敗|fail|crash|exception)",
    r"(?:注意|重要|cannot|必須|不要|never|always)",
    r"(?:發現|found|discovered|realized)",
    r"(?:因為|because|reason|原因|導致|caused)",
    r"(?:結果|result|outcome|效果|effect)",
    r"(?:比較|對比|versus|vs|比起|better than)",
    r"(?:架構|architecture|設計|design|決策|decision|選擇|chose)",
    r"(?:最佳實踐|best practice|建議|recommend|should)",
    r"(?:配置|config|設定|setup|安裝|install)",
    r"(?:速度|效能|performance|优化|optimize|快|慢)",
]

# 排除模式：這些對話不值得提取
EXCLUDE_PATTERNS = [
    r"^(hi|hello|hey|早|晚安|ok|好的|嗯|好)$",
    r"^\[SYSTEM\]",
    r"^\[Note:",
    r"^SILENT$",
]

def load_recent_sessions(days=3, limit=50):
    """從 Hermes state.db 載入最近的對話。"""
    if not os.path.exists(HERMES_DB):
        print(f"⚠️ Hermes DB 不存在: {HERMES_DB}")
        return []
    
    conn = sqlite3.connect(HERMES_DB)
    conn.row_factory = sqlite3.Row
    
    # started_at is unix timestamp
    cutoff_ts = (datetime.now() - timedelta(days=days)).timestamp()
    
    # Get recent sessions
    sessions = conn.execute("""
        SELECT id, started_at, source, model, title
        FROM sessions
        WHERE started_at > ? AND source = 'telegram'
        ORDER BY started_at DESC
        LIMIT ?
    """, (cutoff_ts, limit)).fetchall()
    
    results = []
    for s in sessions:
        # Get messages for this session
        msgs = conn.execute("""
            SELECT role, content FROM messages
            WHERE session_id = ? AND role IN ('user', 'assistant')
            ORDER BY timestamp ASC
        """, (s["id"],)).fetchall()
        
        content_parts = []
        for m in msgs:
            role_label = "U" if m["role"] == "user" else "A"
            text = (m["content"] or "")[:300]  # Cap each message
            content_parts.append(f"[{role_label}] {text}")
        
        if len(content_parts) < 3:  # Skip very short sessions
            continue
        
        results.append({
            "id": s["id"],
            "started_at": s["started_at"],
            "source": s["source"],
            "model": s["model"] or "",
            "title": s["title"] or "",
            "content": "\n".join(content_parts),
        })
    
    conn.close()
    return results

def extract_knowledge_from_session(session):
    """從單一 session 的內容中提取知識候選。"""
    content = session["content"]
    if not content or len(content) < 200:
        return []
    
    # 只提取 assistant 的回答（更有結構性）
    assistant_parts = []
    for chunk in content.split("\n"):
        if chunk.startswith("[A]"):
            assistant_parts.append(chunk[4:])  # Remove [A] prefix
    
    if not assistant_parts:
        # Fallback: use full content but higher threshold
        assistant_parts = [content]
    
    candidates = []
    
    for text in assistant_parts:
        if len(text.strip()) < 80:  # Skip short responses
            continue
        
        # Count knowledge pattern matches (need at least 2)
        match_count = 0
        matched_patterns = []
        for pattern in KNOWLEDGE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                match_count += 1
                matched_patterns.append(pattern)
        
        if match_count < 2:  # Need at least 2 knowledge indicators
            continue
        
        # Skip conversational patterns
        conv_patterns = [
            r"^(嗨|嗨|好喔|好呀|好的|對啊|沒錯|OK|ok|ok!|了解|收到|明白)",
            r"^(讓我|我可以|我來|我會幫你|要不要)",
            r"^(你有|你想|你可以|你覺得)",
        ]
        skip = False
        first_line = text.strip().split("\n")[0]
        for cp in conv_patterns:
            if re.match(cp, first_line, re.IGNORECASE):
                skip = True
                break
        if skip:
            continue
        
        # Generate title
        # Look for markdown headers or key sentences
        headers = re.findall(r"^#+\s*(.+)$", text, re.MULTILINE)
        if headers:
            title = re.sub(r"^#+\s*", "", headers[0])[:60]
        else:
            # Take first meaningful line
            lines = text.strip().split("\n")
            title = lines[0][:60]
        
        # Clean title
        title = re.sub(r"^\*\*|^\[.\]\s*", "", title).strip()
        title = re.sub(r"\*+$", "", title).strip()
        
        if len(title) < 5:
            title = text[:40] + "..."
        
        # Only add if content is substantial enough
        if len(text.strip()) >= 80:
            candidates.append({
                "title": title,
                "content": text.strip()[:2000],  # Cap at 2000 chars
                "source": f"session-{session['id'][:12]}",
                "matched_patterns": match_count,
                "session_time": session.get("started_at", ""),
            })
    
    # Keep only top candidates (sorted by pattern match count)
    candidates.sort(key=lambda x: x.get("matched_patterns", 0), reverse=True)
    return candidates[:3]  # Max 3 per session

def deduplicate(candidates, existing_titles, existing_hashes):
    """去除重複候選。"""
    seen = set()
    unique = []
    
    for c in candidates:
        # 標題去重
        if c["title"] in existing_titles:
            continue
        
        # 內容 hash 去重
        import hashlib
        content_hash = hashlib.sha256(c["content"].encode()).hexdigest()[:16]
        if content_hash in existing_hashes:
            continue
        
        # 候選內去重（同標題前綴）
        key = c["title"][:30]
        if key in seen:
            continue
        seen.add(key)
        
        unique.append(c)
        c["content_hash"] = content_hash
    
    return unique

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=3, help="掃描最近 N 天")
    parser.add_argument("--limit", type=int, default=50, help="最多掃描 N 個 session")
    parser.add_argument("--dry-run", action="store_true", help="只顯示不寫入")
    args = parser.parse_args()
    
    print(f"🔍 掃描最近 {args.days} 天的 session...")
    
    # 1. 載入 session
    sessions = load_recent_sessions(days=args.days, limit=args.limit)
    print(f"   找到 {len(sessions)} 個 session")
    
    # 2. 提取知識候選
    all_candidates = []
    for session in sessions:
        candidates = extract_knowledge_from_session(session)
        all_candidates.extend(candidates)
    
    print(f"   提取 {len(all_candidates)} 個知識候選")
    
    # 3. 去重
    db = GuardrailsDB(GR_DB)
    db.connect()
    
    existing_titles = set()
    existing_hashes = set()
    for row in db.conn.execute("SELECT title, content_hash FROM knowledge").fetchall():
        existing_titles.add(row[0])
        existing_hashes.add(row[1])
    
    unique = deduplicate(all_candidates, existing_titles, existing_hashes)
    print(f"   去重後 {len(unique)} 個新知識")
    
    if not unique:
        print("📭 沒有新知識需要寫入")
        db.close()
        return
    
    for c in unique:
        print(f"   📝 {c['title'][:50]}")
    
    if args.dry_run:
        print("\n🐌 Dry run 模式，不寫入 DB")
        db.close()
        return
    
    # 4. 寫入 DB
    embed = create_embedding_provider(provider="onnx", model_key="mix")
    added = 0
    
    for c in unique:
        kid = db.add_knowledge(
            title=c["title"],
            content_raw=c["content"],
            layer="L3",
            category="session-extract",
            tags="auto-extract,session",
            trust=0.4,  # session 提取的信任度較低
            source=c["source"],
            content_aaak=c["content"][:150],
        )
        
        try:
            vec = embed.encode(c["content"][:500])[0]
            db.add_embedding(kid, vec)
            added += 1
        except Exception:
            pass
    
    print(f"\n✅ 新增 {added} 筆知識")
    
    # 5. 如果新增 > 5 筆，重建圖譜
    if added > 5:
        print("🕸️ 圖譜重建中...")
        db.conn.execute("DELETE FROM edges")
        db.conn.execute("DELETE FROM entity_knowledge")
        db.conn.execute("DELETE FROM entities")
        db.conn.commit()
        
        g = GuardrailsGraph(db)
        result = g.infer_all()
        print(f"   實體: {result['entities_created']}, 邊: {result['edges_created']}")
    
    stats = db.stats()
    print(f"\n📊 最終: {stats['knowledge_count']} 筆, {stats['embedding_count']} 嵌入")
    db.close()

if __name__ == "__main__":
    main()