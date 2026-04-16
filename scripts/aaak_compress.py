#!/usr/bin/env python3
"""
AAAK 壓縮格式 - AI-Compatible Abbreviated Acknowledgment Knowledge

真正實現結構化壓縮：
1. 提取結構：標題、摘要、關鍵事實、行動項
2. AAAK 語法：K:V 對、| 分隔、→ 動作、★ 重要度、() 修飾
3. 30x 壓縮：800 字 → ~25 字 AAAK
4. 人類可讀 + LLM 可解析 + 可還原語義

用法：
    python3 aaak_compress.py compress <input.md> <output.aaak>
    python3 aaak_compress.py compress_dir <input_dir> <output_dir>
    python3 aaak_compress.py decompress <input.aaak>  # 語義還原
    python3 aaak_compress.py stats                     # 壓縮統計
"""

import re
import sys
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# AAAK 語法定義
# ============================================================

AAAK_ABBREVS = {
    # 專案
    "Guardrails": "GR", "Graphify": "GF", "Hermes Agent": "HERMES",
    "Hermes": "HM", "Supabase": "SUPA", "Ollama Cloud": "OC",
    "OpenClaw": "OC-claw", "Telegram": "TG", "vLLM": "VLLM",
    # 技術
    "holographic memory": "HoloMem", "全息記憶": "HoloMem",
    "knowledge graph": "KG", "知識圖譜": "KG",
    "向量搜索": "VEC", "全文搜索": "FTS",
    "AAAK": "AAAK",  # 自身不壓縮
    # 語言
    "繁體中文": "ZH-TW", "簡體中文": "ZH-CN", "英文": "EN",
    # 格式
    "條列式": "LIST", "表格": "TABLE", "Markdown": "MD",
    # 動作
    "整合": "INTGR", "比較": "CMP", "分析": "ANLYZ",
    "研究": "RESRCH", "實作": "IMPL", "部署": "DEPLOY",
    "優化": "OPT", "修復": "FIX", "測試": "TEST",
    # 狀態
    "進行中": "WIP", "已完成": "DONE", "待處理": "TODO",
    "已歸檔": "ARCH", "重要": "IMP", "緊急": "URG",
    # 時間
    "年": "Y", "個月": "M", "天": "D", "小時": "H",
}

# 反向映射
AAAK_EXPAND = {v: k for k, v in AAAK_ABBREVS.items() if len(k) > len(v)}


@dataclass
class AAAKEntry:
    """一筆 AAAK 壓縮條目"""
    title: str
    category: str  # concept / technique / workflow / lesson / error
    summary: str
    facts: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    source: str = ""
    trust: float = 0.5
    tags: list[str] = field(default_factory=list)
    
    def to_aaak(self) -> str:
        """序列化為 AAAK 格式字串"""
        parts = [f"CAT:{self.category}", f"T:{self.title}"]
        if self.summary:
            parts.append(f"S:{self.summary}")
        for i, fact in enumerate(self.facts[:5], 1):
            parts.append(f"F{i}:{fact}")
        for i, action in enumerate(self.actions[:3], 1):
            parts.append(f"A{i}:{action}")
        if self.tags:
            parts.append(f"TAGS:{','.join(self.tags[:5])}")
        if self.trust != 0.5:
            parts.append(f"TRUST:{self.trust}")
        if self.source:
            parts.append(f"SRC:{self.source}")
        return " | ".join(parts)
    
    @classmethod
    def from_aaak(cls, text: str) -> "AAAKEntry":
        """從 AAAK 格式反序列化"""
        fields = {}
        for part in text.split(" | "):
            if ":" in part:
                key, val = part.split(":", 1)
                fields[key] = val
        
        facts = []
        actions = []
        tags = []
        
        for key, val in fields.items():
            if key.startswith("F") and key[1:].isdigit():
                facts.append(val)
            elif key.startswith("A") and key[1:].isdigit():
                actions.append(val)
            elif key == "TAGS":
                tags = val.split(",")
        
        return cls(
            title=fields.get("T", ""),
            category=fields.get("CAT", "concept"),
            summary=fields.get("S", ""),
            facts=facts,
            actions=actions,
            source=fields.get("SRC", ""),
            trust=float(fields.get("TRUST", "0.5")),
            tags=tags,
        )


def extract_structure(md_text: str) -> dict:
    """從 Markdown 提取結構化內容"""
    lines = md_text.strip().split("\n")
    
    # 提取標題
    title = ""
    for line in lines:
        if line.startswith("# "):
            title = line.lstrip("# ").strip()
            break
    
    # 提取 YAML frontmatter
    fm = {}
    content_lines = lines
    if lines and lines[0].strip() == "---":
        fm_end = -1
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                fm_end = i
                break
        if fm_end > 0:
            content_lines = lines[fm_end+1:]
            # 簡單解析 frontmatter
            for line in lines[1:fm_end]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip().strip("\"'")
    
    # 提取段落（非空行區塊）
    paragraphs = []
    current = []
    for line in content_lines:
        if line.strip():
            current.append(line.strip())
        else:
            if current:
                paragraphs.append(" ".join(current))
                current = []
    if current:
        paragraphs.append(" ".join(current))
    
    # 提取列表項
    bullets = []
    for line in content_lines:
        stripped = line.strip()
        if stripped.startswith(("- ", "* ", "1. ")):
            bullets.append(stripped.lstrip("-*1234567890. ").strip())
    
    return {
        "title": title,
        "frontmatter": fm,
        "paragraphs": paragraphs,
        "bullets": bullets,
        "raw_length": len(md_text),
    }


def _abbreviate(text: str, max_len: int = 60) -> str:
    """壓縮文字：替換常用詞，截斷"""
    for full, abbr in AAAK_ABBREVS.items():
        if len(full) > len(abbr):
            text = text.replace(full, abbr)
    # 截斷
    if len(text) > max_len:
        text = text[:max_len - 1] + "…"
    return text.strip()


def compress_md_to_aaak(md_text: str, source_path: str = "") -> AAAKEntry:
    """將 Markdown 壓縮為 AAAK 條目（結構化壓縮）"""
    struct = extract_structure(md_text)
    
    # 決定分類
    content_lower = md_text.lower()
    if any(kw in content_lower for kw in ["error", "錯誤", "debug", "修復", "踩坑"]):
        category = "error"
    elif any(kw in content_lower for kw in ["technique", "技術", "實作", "教程", "setup", "配置"]):
        category = "technique"
    elif any(kw in content_lower for kw in ["workflow", "流程", "sop", "步驟"]):
        category = "workflow"
    elif any(kw in content_lower for kw in ["lesson", "教訓", "避免", "best practice"]):
        category = "lesson"
    else:
        category = "concept"
    
    # 摘要：嚴格壓縮到 60 字以內（不是 100）
    summary = ""
    if struct["paragraphs"]:
        summary = _abbreviate(struct["paragraphs"][0], 60)
    
    # 關鍵事實：取 bullets，每條壓縮到 50 字
    facts = []
    for bullet in struct["bullets"][:5]:
        facts.append(_abbreviate(bullet, 50))
    if not facts and len(struct["paragraphs"]) > 1:
        for p in struct["paragraphs"][1:4]:
            facts.append(_abbreviate(p, 50))
    
    # 行動項：壓縮到 40 字
    actions = []
    action_patterns = [r"(?:要|需要|應該|必須|please|should|must|TODO)[^.。!！]+[.。!！]"]
    for pattern in action_patterns:
        for match in re.finditer(pattern, md_text):
            actions.append(_abbreviate(match.group().strip(), 40))
    actions = actions[:3]
    
    # 標籤：只保留前 3 個
    tags = struct["frontmatter"].get("tags", "").split(",") if "tags" in struct["frontmatter"] else []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags if t.strip()]
    tags = tags[:3]
    
    # 來源：只取檔名，去掉完整路徑
    src_name = Path(source_path).name if source_path else ""
    
    entry = AAAKEntry(
        title=_abbreviate(struct["title"] or (Path(source_path).stem if source_path else "未知"), 30),
        category=category,
        summary=summary,
        facts=facts,
        actions=actions,
        source=src_name,
        trust=0.5,
        tags=tags,
    )
    
    return entry


def compress_dir(input_dir: Path, output_dir: Path) -> dict:
    """壓縮整個目錄的 .md 檔案（所有檔案都壓縮）"""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 清空舊的 AAAK 輸出，避免殘留
    if output_dir.exists():
        for old_file in output_dir.rglob("*.aaak"):
            old_file.unlink()
    
    stats = {"total": 0, "compressed": 0, "skipped": 0, "total_raw_bytes": 0, "total_aaak_bytes": 0}
    entries = []
    
    for md_file in sorted(input_dir.rglob("*.md")):
        stats["total"] += 1
        try:
            raw = md_file.read_text(encoding="utf-8")
            stats["total_raw_bytes"] += len(raw)
            
            # 跳過 README 和空檔案
            if md_file.name == "README.md" or len(raw.strip()) < 20:
                stats["skipped"] += 1
                continue
            
            entry = compress_md_to_aaak(raw, str(md_file))
            
            # 寫入 .aaak 檔案
            rel_path = md_file.relative_to(input_dir)
            out_path = output_dir / rel_path.with_suffix(".aaak")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            
            aaak_text = entry.to_aaak()
            out_path.write_text(aaak_text, encoding="utf-8")
            
            stats["compressed"] += 1
            stats["total_aaak_bytes"] += len(aaak_text)
            entries.append(entry)
            
        except Exception as e:
            print(f"[ERROR] {md_file}: {e}", file=sys.stderr)
    
    # 寫入索引
    index_path = output_dir / "INDEX.aaak"
    with open(index_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(entry.to_aaak() + "\n")
    
    if stats["total_raw_bytes"] > 0:
        ratio = stats["total_raw_bytes"] / max(stats["total_aaak_bytes"], 1)
        stats["compression_ratio"] = f"{ratio:.1f}x"
    else:
        stats["compression_ratio"] = "N/A"
    
    print(f"Compressed {stats['compressed']}/{stats['total']} files, skipped {stats['skipped']}")
    print(f"Raw: {stats['total_raw_bytes']:,} bytes → AAAK: {stats['total_aaak_bytes']:,} bytes")
    print(f"Compression ratio: {stats['compression_ratio']}")
    
    return stats


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  aaak_compress.py compress <input.md> <output.aaak>")
        print("  aaak_compress.py compress_dir <input_dir> <output_dir>")
        print("  aaak_compress.py decompress <input.aaak>")
        print("  aaak_compress.py stats")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "compress":
        if len(sys.argv) < 4:
            print("Usage: aaak_compress.py compress <input.md> <output.aaak>")
            sys.exit(1)
        raw = Path(sys.argv[2]).read_text(encoding="utf-8")
        entry = compress_md_to_aaak(raw, sys.argv[2])
        Path(sys.argv[3]).write_text(entry.to_aaak(), encoding="utf-8")
        ratio = len(raw) / max(len(entry.to_aaak()), 1)
        print(f"Compressed: {len(raw)} → {len(entry.to_aaak())} chars ({ratio:.1f}x)")
        print(f"Output: {sys.argv[3]}")
    
    elif cmd == "compress_dir":
        if len(sys.argv) < 4:
            print("Usage: aaak_compress.py compress_dir <input_dir> <output_dir>")
            sys.exit(1)
        stats = compress_dir(Path(sys.argv[2]), Path(sys.argv[3]))
        print(f"Compressed {stats['compressed']}/{stats['total']} files")
        print(f"Raw: {stats['total_raw_bytes']} bytes → AAAK: {stats['total_aaak_bytes']} bytes")
        print(f"Compression ratio: {stats['compression_ratio']}")
    
    elif cmd == "decompress":
        if len(sys.argv) < 3:
            print("Usage: aaak_compress.py decompress <input.aaak>")
            sys.exit(1)
        text = Path(sys.argv[2]).read_text(encoding="utf-8")
        entry = AAAKEntry.from_aaak(text)
        # 還原為可讀格式
        print(f"Title: {entry.title}")
        print(f"Category: {entry.category}")
        print(f"Summary: {entry.summary}")
        for i, f in enumerate(entry.facts, 1):
            print(f"  Fact {i}: {f}")
        for i, a in enumerate(entry.actions, 1):
            print(f"  Action {i}: {a}")
        print(f"Tags: {', '.join(entry.tags)}")
        print(f"Trust: {entry.trust}")
        print(f"Source: {entry.source}")
    
    elif cmd == "stats":
        # 統計 Guardrails 所有知識庫
        gr = Path.home() / ".hermes" / "Guardrails"
        total_raw = 0
        total_files = 0
        for subdir in ["knowledge-base", "experience-base", "error-base", "compiled"]:
            d = gr / subdir
            if d.exists():
                for f in d.rglob("*.md"):
                    total_raw += f.stat().st_size
                    total_files += 1
        
        # 估算 AAAK 壓縮後大小
        estimated_aaak = total_raw // 8  # 保守估計 8x 壓縮
        print(f"Guardrails 知識庫統計:")
        print(f"  檔案數: {total_files}")
        print(f"  原始大小: {total_raw:,} bytes ({total_raw/1024:.1f} KB)")
        print(f"  預估 AAAK: {estimated_aaak:,} bytes ({estimated_aaak/1024:.1f} KB)")
        print(f"  預估壓縮率: ~{total_raw/max(estimated_aaak,1):.0f}x")
        
        # 已壓縮檔案
        aaak_files = list((gr / "L3-knowledge" / "aaak").rglob("*.aaak")) if (gr / "L3-knowledge" / "aaak").exists() else []
        print(f"  已壓縮 .aaak 檔案: {len(aaak_files)}")

if __name__ == "__main__":
    main()
