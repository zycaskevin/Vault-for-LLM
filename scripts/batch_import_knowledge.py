#!/usr/bin/env python3
"""批次匯入 knowledge-base, error-base, L0-L2 目錄的 .md 檔案到 Vault for LLM DB。"""
import os, glob, re
sys_path = "/home/user/Guardrails-knowledge"
import sys
sys.path.insert(0, sys_path)

from vault.guardrails_db import GuardrailsDB
from vault.guardrails_embed import create_embedding_provider

BASE = "/home/user/Guardrails-knowledge"
db = GuardrailsDB(os.path.join(BASE, "guardrails.db"))
db.connect()
embed = create_embedding_provider(provider="onnx", model_key="mix")

# Map directory to (layer, category)
DIR_MAP = {
    "knowledge-base/concepts": ("L3", "concept"),
    "knowledge-base/best-practices": ("L3", "technique"),
    "knowledge-base/integrations": ("L3", "technique"),
    "knowledge-base/core-concepts": ("L2", "architecture"),
    "knowledge-base/skills": ("L3", "technique"),
    "error-base/error-catalog": ("L3", "error"),
    "L0-identity": ("L0", "identity"),
    "L1-core-facts": ("L1", "core-facts"),
    "L2-context": ("L2", "context"),
}

# Determine layer/category from file path
def classify(filepath):
    rel = os.path.relpath(filepath, BASE)
    for prefix, (layer, cat) in DIR_MAP.items():
        if rel.startswith(prefix):
            return layer, cat
    return "L3", "general"

# Parse YAML frontmatter from markdown
def parse_frontmatter(content):
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            body = parts[2].strip()
            fm = {}
            for line in fm_text.strip().split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    fm[key.strip()] = val.strip().strip('"').strip("'")
            return fm, body
    return {}, content

# Find all .md files
patterns = [
    "knowledge-base/**/*.md",
    "error-base/**/*.md",
    "L0-identity/**/*.md",
    "L1-core-facts/**/*.md",
    "L2-context/**/*.md",
]

files = []
for pattern in patterns:
    files.extend(glob.glob(os.path.join(BASE, pattern), recursive=True))

# Filter out README
files = [f for f in files if not os.path.basename(f).startswith("README")]

# Check which titles already exist in DB
existing_titles = set()
for row in db.conn.execute("SELECT title FROM knowledge").fetchall():
    existing_titles.add(row[0])

added = 0
skipped = 0
errors = 0

for fpath in sorted(files):
    try:
        content = open(fpath, encoding="utf-8").read()
        fm, body = parse_frontmatter(content)
        
        # Use body (after frontmatter) as content
        text = body if body else content
        
        # Title from frontmatter or filename
        title = fm.get("title", os.path.splitext(os.path.basename(fpath))[0])
        # Clean title - remove date prefix
        title = re.sub(r"^\d{8}-", "", title)
        
        # Skip if already exists
        if title in existing_titles:
            skipped += 1
            continue
        
        layer, category = classify(fpath)
        # Frontmatter overrides
        layer = fm.get("layer", layer)
        category = fm.get("category", category)
        tags = fm.get("tags", "")
        trust = float(fm.get("trust", 0.5))
        source = fm.get("source", "batch-import")
        
        kid = db.add_knowledge(
            title=title,
            content_raw=text[:5000],  # Cap at 5000 chars
            layer=layer,
            category=category,
            tags=tags,
            trust=trust,
            source=source,
            content_aaak=text[:200],  # First 200 chars as AAAK
        )
        
        # Add embedding
        try:
            vec = embed.encode(text[:500])[0]
            db.add_embedding(kid, vec)
        except Exception:
            pass  # Skip embedding if too short
        
        added += 1
        if added % 10 == 0:
            print(f"  {added} imported...")
            
    except Exception as e:
        errors += 1
        print(f"  ❌ {os.path.basename(fpath)}: {e}")

db.close()
print(f"\n✅ 匯入完成: {added} 新增, {skipped} 跳過(已存在), {errors} 錯誤")