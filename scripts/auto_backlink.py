#!/usr/bin/env python3
"""Vault 自動 Backlink 生成器

Inspired by: Agentic Note-Taking pattern (community best practice)
作用：掃描 raw/ 和 compiled/ 的 .md 文件，識別可鏈接的實體（人名、技術、工具、概念），
     在首次出現處插入 [[wikilink]] 格式的交叉引用。

用法：
    python3 scripts/auto_backlink.py [--dry-run] [--dir raw/] [--verbose]

設計原則（對標community橙皮書 + Karpathy LLM Wiki）：
- 只在每個文件中每個實體的**首次出現**處插入鏈接
- 不修改 raw/ 文件的原始內容（僅在 compiled/ 中插入）
- 生成的鏈接記錄在 .backlinks.json 中供人工審核
- 支持干跑模式（--dry-run）查看將要插入的鏈接

2026-04-22 created
"""

import os
import re
import json
import glob
import sys
import argparse
from pathlib import Path
from collections import defaultdict

VAULT_DIR = Path(os.environ.get('VAULT_PATH', Path(__file__).resolve().parent.parent))
BACKLINKS_DB = VAULT_DIR / '.backlinks.json'


# ============================================================
# 實體定義 — 已知可鏈接的 public-safe 實體列表
# ============================================================

# 系統內建實體（public-safe baseline + 常見概念手動整理）
BUILTIN_ENTITIES = {
    # 技術工具
    "Vault": "vault",
    "Example Agent": "example-agent",
    "Claude Code": "claude-code",
    "OpenCode": "opencode",
    "Supabase": "supabase",
    "Ollama": "ollama",
    "vLLM": "vllm",
    "ComfyUI": "comfyui",
    "Flux": "flux",
    "Gemini": "gemini",
    "Graphify": "graphify",
    "Obsidian": "obsidian",
    "Docker": "docker",
    "PostgreSQL": "postgresql",
    "sqlite-vec": "sqlite-vec",
    "ONNX": "onnx",
    "ChromaDB": "chromadb",
    "Ghost": "ghost-blog",
    "n8n": "n8n",
    "OpenRouter": "openrouter",
    
    # 概念
    "AAAK": "aaak",
    "RAG": "rag",
    "MCP": "mcp",
    "CDP": "cdp",
    "TTS": "tts",
    "STT": "stt",
    "LLM": "llm",
    "frontmatter": "frontmatter",
    "wikilink": "wikilink",
    
    # 人名
    
    # 平台
    "GitHub": "github",
    
    # Windows/WSL
    "WSL2": "wsl2",
    "NVIDIA": "nvidia",
    
    # 模型
    "Qwen": "qwen",
    "GPT-4": "gpt4",
    "Claude": "claude",
}


def load_backlinks_db():
    """載入已有的 backlink 記錄"""
    if BACKLINKS_DB.exists():
        with open(BACKLINKS_DB, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"entities": {}, "links": []}


def save_backlinks_db(db):
    """儲存 backlink 記錄"""
    with open(BACKLINKS_DB, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def scan_for_entities(text, entities=BUILTIN_ENTITIES):
    """掃描文本，找出首次出現的可鏈接實體
    
    返回: list of (entity_name, slug, position)
    每個實體只返回第一次出現的位置
    """
    found = []
    seen = set()
    
    # 按名稱長度降序排列，優先匹配長名（如 "Example Agent" 優先於 "Agent"）
    sorted_entities = sorted(entities.items(), key=lambda x: len(x[0]), reverse=True)
    
    for entity_name, slug in sorted_entities:
        if slug in seen:
            continue
        # 用 word boundary 匹配，避免部分匹配
        pattern = re.compile(r'(?<!\[\[)\b' + re.escape(entity_name) + r'\b(?!\]\])')
        match = pattern.search(text)
        if match:
            found.append((entity_name, slug, match.start()))
            seen.add(slug)
    
    return found


def insert_backlinks(text, entities_found):
    """在文本中插入 [[wikilink]]（從後往前插，保持位置不變）"""
    # 按位置降序排列
    sorted_found = sorted(entities_found, key=lambda x: x[2], reverse=True)
    
    for entity_name, slug, pos in sorted_found:
        # 找到原文中的精確出現
        end = pos + len(entity_name)
        original = text[pos:end]
        # 包裝成 wikilink
        wikilink = f"[[{slug}|{original}]]"
        text = text[:pos] + wikilink + text[end:]
    
    return text


def extract_frontmatter(filepath):
    """提取 YAML frontmatter"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read(2000)
        if not content.startswith('---'):
            return None, content
        end = content.find('---', 3)
        if end == -1:
            return None, content
        fm_text = content[3:end].strip()
        body = content[end+3:].lstrip('\n')
        return fm_text, body
    except:
        return None, None


def process_file(filepath, dry_run=False, verbose=False):
    """處理單個文件，插入 backlinks"""
    fm_text, body = extract_frontmatter(filepath)
    if body is None:
        return []
    
    # 跳過已有大量 wikilinks 的文件
    existing_links = body.count('[[')
    if existing_links > 10:
        if verbose:
            print(f"  ⏭️ {filepath.name}: 已有 {existing_links} 個鏈接，跳過")
        return []
    
    # 掃描實體
    entities_found = scan_for_entities(body)
    if not entities_found:
        return []
    
    links = []
    for entity_name, slug, pos in entities_found:
        links.append({
            "file": str(filepath),
            "entity": entity_name,
            "slug": slug,
            "position": pos
        })
    
    if not dry_run:
        # 插入 backlinks
        new_body = insert_backlinks(body, entities_found)
        # 重新組合文件
        if fm_text:
            new_content = f"---\n{fm_text}\n---\n{new_body}"
        else:
            new_content = new_body
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        if verbose:
            names = [e[0] for e in entities_found]
            print(f"  ✅ {filepath.name}: 插入 {len(entities_found)} 個鏈接 ({', '.join(names)})")
    else:
        if verbose:
            names = [e[0] for e in entities_found]
            print(f"  [DRY] {filepath.name}: 將插入 {len(entities_found)} 個鏈接 ({', '.join(names)})")
    
    return links


def run(directories=None, dry_run=False, verbose=False):
    """主流程：掃描目錄並插入 backlinks"""
    if directories is None:
        # Only process compiled/ (not raw/ — raw/ is "人的領地，只增不改")
        directories = [VAULT_DIR / "compiled"]
    
    db = load_backlinks_db()
    all_links = []
    total_files = 0
    total_links = 0
    
    for directory in directories:
        if not directory.exists():
            print(f"⚠️ {directory} 不存在，跳過")
            continue
        
        md_files = list(directory.rglob("*.md"))
        print(f"\n📂 {directory}: {len(md_files)} 個 .md 文件")
        
        for md_file in md_files:
            links = process_file(md_file, dry_run=dry_run, verbose=verbose)
            all_links.extend(links)
            total_files += 1
            total_links += len(links)
    
    # 更新 DB
    if not dry_run and all_links:
        db["links"].extend(all_links)
        from datetime import datetime
        db["last_run"] = datetime.now().isoformat()
        save_backlinks_db(db)
    
    mode = "[DRY RUN] " if dry_run else ""
    print(f"\n{mode}結果：{total_files} 個文件，{total_links} 個 backlinks")
    
    if dry_run and all_links:
        # 顯示待插入的鏈接摘要
        entity_counts = defaultdict(int)
        for link in all_links:
            entity_counts[link["slug"]] += 1
        print("\n待插入實體 Top 10:")
        for slug, count in sorted(entity_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"  {slug}: {count} 次")
    
    return all_links


def main():
    parser = argparse.ArgumentParser(description="Vault 自動 Backlink 生成器")
    parser.add_argument("--dry-run", action="store_true", help="只顯示將要插入的鏈接，不寫入文件")
    parser.add_argument("--dir", action="append", help="指定掃描目錄（可重複）")
    parser.add_argument("--include-raw", action="store_true", help="也處理 raw/（預設只處理 compiled/）")
    parser.add_argument("--verbose", "-v", action="store_true", help="顯示每個文件的處理詳情")
    args = parser.parse_args()
    
    directories = []
    if args.dir:
        directories = [Path(d) for d in args.dir]
    elif args.include_raw:
        directories = [VAULT_DIR / "compiled", VAULT_DIR / "raw"]
    else:
        directories = [VAULT_DIR / "compiled"]
    
    print("🔍 Vault 自動 Backlink 生成器")
    print(f"   模式: {'干跑' if args.dry_run else '正式'}")
    print(f"   目錄: {', '.join(str(d) for d in directories)}")
    
    links = run(directories=directories, dry_run=args.dry_run, verbose=args.verbose)
    
    if not args.dry_run and links:
        print(f"\n💾 Backlink 記錄已儲存到 {BACKLINKS_DB}")
        print("   執行 generate_index.py 更新索引...")


if __name__ == '__main__':
    main()