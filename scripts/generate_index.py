#!/usr/bin/env python3
"""Vault INDEX.md auto-generator.

Scans raw/ and compiled/ for .md files with frontmatter,
builds a navigable index sorted by category, date, and tags.

Usage:
    python3 scripts/generate_index.py [--output INDEX.md]
"""
import argparse
import os
import re
import glob
from collections import Counter

VAULT_DIR = os.environ.get('VAULT_PATH', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def extract_frontmatter(filepath):
    """Extract YAML frontmatter fields from a .md file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read(2000)
        if not content.startswith('---'):
            return None
        end = content.find('---', 3)
        if end == -1:
            return None
        fm_text = content[3:end].strip()
        result = {}
        for line in fm_text.split('\n'):
            if ':' in line:
                key, _, val = line.partition(':')
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key == 'tags' and val.startswith('['):
                    tags = re.findall(r'"([^"]+)"', val)
                    if not tags:
                        tags = re.findall(r"'([^']+)'", val)
                    if not tags:
                        tags = [t.strip() for t in val.strip('[]').split(',') if t.strip()]
                    result[key] = tags
                elif key in ('title', 'category', 'created', 'updated', 'summary', 
                             'trust', 'source', 'layer', 'status'):
                    result[key] = val
        return result if result.get('title') else None
    except Exception:
        return None


def generate_index(output_path=None):
    """Generate INDEX.md from all knowledge files."""
    raw_files = glob.glob(os.path.join(VAULT_DIR, "raw", "**/*.md"), recursive=True)
    compiled_files = glob.glob(os.path.join(VAULT_DIR, "compiled", "**/*.md"), recursive=True)
    
    all_entries = []
    for f in raw_files:
        fm = extract_frontmatter(f)
        if fm:
            rel = os.path.relpath(f, VAULT_DIR)
            all_entries.append({**fm, 'path': rel, 'type': 'raw'})
    for f in compiled_files:
        fm = extract_frontmatter(f)
        if fm:
            rel = os.path.relpath(f, VAULT_DIR)
            all_entries.append({**fm, 'path': rel, 'type': 'compiled'})
    
    cat_counts = Counter(e.get('category', 'unknown') for e in all_entries)
    tag_counts = Counter()
    for e in all_entries:
        tags = e.get('tags', [])
        if isinstance(tags, list):
            tag_counts.update(tags)
    
    all_entries.sort(key=lambda x: x.get('created', '0000'), reverse=True)
    
    raw_count = len([e for e in all_entries if e['type'] == 'raw'])
    compiled_count = len([e for e in all_entries if e['type'] == 'compiled'])
    
    lines = []
    lines.append("# Vault Knowledge Base索引\n")
    lines.append(f"_最後更新：{__import__('datetime').date.today().isoformat()} | 共 {len(all_entries)} 筆（raw: {raw_count}，compiled: {compiled_count}）_\n")
    lines.append("> 由 `scripts/generate_index.py` 自動生成。Compiler 完成後自動執行。\n")
    lines.append("---\n")
    
    # Quick overview
    lines.append("## 概覽\n")
    lines.append(f"- **Cloud storage**: available if configured")
    lines.append(f"- **Local**: check with `vault stats`")
    lines.append(f"- **raw/ 原始知識**：{raw_count} 筆")
    lines.append(f"- **compiled/ 結構化**：{compiled_count} 筆")
    lines.append("")
    
    # By category
    lines.append("## 按類別\n")
    lines.append("| 類別 | 數量 |")
    lines.append("|------|------|")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {cat} | {count} |")
    lines.append("")
    
    # Top tags
    lines.append("## 熱門標籤（Top 15）\n")
    lines.append("| 標籤 | 出現次數 |")
    lines.append("|------|----------|")
    for tag, count in tag_counts.most_common(15):
        lines.append(f"| {tag} | {count} |")
    lines.append("")
    
    # Raw entries
    raw_entries = sorted(
        [e for e in all_entries if e['type'] == 'raw'],
        key=lambda x: x.get('created', '0000'), reverse=True
    )
    lines.append(f"## raw/ 原始知識（{len(raw_entries)} 筆）\n")
    lines.append("| 標題 | 類別 | 日期 | 標籤 | Summary |")
    lines.append("|------|------|------|------|---------|")
    for e in raw_entries:
        title = e.get('title', '?')[:50]
        cat = e.get('category', '—')
        created = e.get('created', '—')
        tags = ', '.join(e.get('tags', [])[:3]) if isinstance(e.get('tags'), list) else '—'
        summary = e.get('summary', '—')[:50]
        lines.append(f"| {title} | {cat} | {created} | {tags} | {summary} |")
    lines.append("")
    
    # Compiled with real titles
    compiled_entries = [e for e in all_entries if e['type'] == 'compiled']
    meaningful = [e for e in compiled_entries 
                  if not (e.get('title', '').startswith('2026') and 'test_' in e.get('title', ''))]
    
    lines.append(f"## compiled/ 精選（{len(meaningful)} 筆有明確標題）\n")
    if meaningful:
        lines.append("| 標題 | 類別 | Summary |")
        lines.append("|------|------|---------|")
        for e in sorted(meaningful, key=lambda x: x.get('title', ''))[:30]:
            title = e.get('title', '?')[:50]
            cat = e.get('category', '—')
            summary = e.get('summary', '—')[:60]
            lines.append(f"| {title} | {cat} | {summary} |")
        lines.append("")
    
    # Quality metrics
    no_summary = len([e for e in all_entries if not e.get('summary')])
    lines.append("## 品質指標\n")
    pct = (no_summary / max(len(all_entries), 1)) * 100
    lines.append(f"- **缺 summary**：{no_summary}/{len(all_entries)} 筆（{pct:.0f}%）← 需補")
    lines.append(f"- **有明確標題**：{len(meaningful)}/{len(compiled_entries)} 筆 compiled")
    lines.append("")
    
    index_content = '\n'.join(lines)
    
    if output_path is None:
        output_path = os.path.join(VAULT_DIR, "INDEX.md")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(index_content)
    
    print(f"✅ INDEX.md generated: {len(lines)} lines, {len(all_entries)} entries")
    return output_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generate INDEX.md from raw/ and compiled/ Markdown entries.")
    parser.add_argument("--output", default=None, help="Output path (default: VAULT_PATH/INDEX.md).")
    args = parser.parse_args()
    generate_index(args.output)
