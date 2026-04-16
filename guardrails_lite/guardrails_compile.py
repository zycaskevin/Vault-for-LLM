"""
Vault for LLM — 本地編譯器。

將 raw/ 目錄的 Markdown 知識編譯進 SQLite + sqlite-vec，
同時產出 compiled/ 的 AAAK 壓縮版本。

流程：
1. 掃描 raw/ 所有 .md 檔案
2. 解析 YAML frontmatter
3. AAAK 壓縮（如果可用）
4. 寫入 SQLite + 向量嵌入
5. 更新 compiled/ 目錄
6. Git auto-commit
"""

import hashlib
import json
import re
import subprocess
import yaml
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional


def extract_frontmatter(content: str) -> tuple[dict, str]:
    """從 Markdown 提取 YAML frontmatter，回傳 (metadata, body)。"""
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, content

    fm_lines = []
    end_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
        fm_lines.append(lines[i])

    if end_idx < 0:
        return {}, content

    try:
        metadata = yaml.safe_load("\n".join(fm_lines)) or {}
    except yaml.YAMLError:
        metadata = {}

    body = "\n".join(lines[end_idx + 1:]).strip()
    return metadata, body


def simple_aaak_compress(title: str, content: str) -> str:
    """
    簡易 AAAK 壓縮：保留結構，去除冗餘。
    不依賴 LLM，純規則壓縮。
    """
    lines = content.strip().split("\n")
    compressed = []

    for line in lines:
        # 去空行
        if not line.strip():
            continue
        # 去思考過程
        if line.strip().startswith("思考:") or line.strip().startswith("思考："):
            continue
        # 保留標題、列表、段落
        compressed.append(line.strip())

    result = "\n".join(compressed)

    # 如果壓縮後仍然很長，做一次斷行去冗餘
    if len(result) > 500:
        # 只取前 5 個要點段落
        paragraphs = []
        current = []
        for line in result.split("\n"):
            if line.startswith("#") or line.startswith("- ") or line.startswith("* "):
                if current:
                    paragraphs.append("\n".join(current))
                current = [line]
            else:
                current.append(line)
        if current:
            paragraphs.append("\n".join(current))

        if len(paragraphs) > 5:
            result = "\n".join(paragraphs[:5]) + f"\n... (原 {len(paragraphs)} 段，取前 5 段)"

    return result


def classify_content(content: str, metadata: dict) -> str:
    """簡易分類器：關鍵字匹配。"""
    text = content[:500].lower()
    source = str(metadata.get("source", "")).lower()

    patterns = {
        "error": ["錯誤", "失敗", "bug", "error", "fail", "超時", "timeout", "oom", "crash"],
        "architecture": ["架構", "設計", "architecture", "部署", "deploy", "系統", "模式"],
        "technique": ["方法", "步驟", "how", "步驟", "指南", "最佳實踐", "最佳", "技巧"],
        "decision": ["決策", "選擇", "比較", "vs", "權衡", "取捨", "偏好"],
        "general": [],
    }

    best_cat = "general"
    best_score = 0
    for cat, keywords in patterns.items():
        score = sum(1 for kw in keywords if kw in text)
        # 來源加權
        if source in cat:
            score += 2
        if score > best_score:
            best_score = score
            best_cat = cat

    return best_cat


def assign_layer(metadata: dict) -> str:
    """決定分層。"""
    # frontmatter 指定優先
    layer = metadata.get("layer", "")
    if layer in ("L0", "L1", "L2", "L3"):
        return layer

    # 根據目錄推斷
    source = str(metadata.get("source", ""))
    dir_map = {
        "L0-identity": "L0",
        "L1-core-facts": "L1",
        "L2-context": "L2",
        "L3-knowledge": "L3",
    }
    for d, l in dir_map.items():
        if d in source:
            return l

    # 根據分類推斷
    cat = metadata.get("category", "")
    if cat in ("error", "architecture"):
        return "L2"
    return "L3"


class GuardrailsCompiler:
    """Vault for LLM 本地編譯器。"""

    def __init__(
        self,
        project_dir: str | Path = ".",
        db=None,
        embed_provider=None,
    ):
        self.project_dir = Path(project_dir)
        self.raw_dir = self.project_dir / "raw"
        self.compiled_dir = self.project_dir / "compiled"
        self.db = db  # GuardrailsDB，延遲初始化
        self.embed = embed_provider  # 嵌入 provider，可選

    def compile(self, dry_run: bool = False) -> dict:
        """
        執行編譯：raw/ → db + compiled/。

        回傳統計：
        {
            "total_files": N,
            "new": N,
            "updated": N,
            "skipped": N,
            "errors": N,
        }
        """
        from .guardrails_db import GuardrailsDB

        # 延遲連接
        close_db = False
        if self.db is None:
            db_path = self.project_dir / "guardrails.db"
            self.db = GuardrailsDB(str(db_path))
            self.db.connect()
            close_db = True

        stats = {"total_files": 0, "new": 0, "updated": 0, "skipped": 0, "errors": 0}

        try:
            # 收集 raw/ 檔案
            if not self.raw_dir.exists():
                print(f"[compiler] ⚠️ raw/ 目錄不存在: {self.raw_dir}")
                return stats

            md_files = sorted(self.raw_dir.rglob("*.md"))
            stats["total_files"] = len(md_files)

            for md_file in md_files:
                try:
                    result = self._compile_file(md_file, dry_run)
                    stats[result] += 1
                except Exception as e:
                    print(f"[compiler] ❌ {md_file.name}: {e}")
                    stats["errors"] += 1

            # 重建向量索引（如果有嵌入）
            if self.embed is not None and stats["new"] + stats["updated"] > 0:
                self._rebuild_embeddings(dry_run)

            # 更新 compiled/
            if not dry_run:
                self._update_compiled()

            # Git commit
            if not dry_run and stats["new"] + stats["updated"] > 0:
                self._git_commit(stats)

        finally:
            if close_db:
                self.db.close()

        return stats

    def _compile_file(self, md_file: Path, dry_run: bool) -> str:
        """處理單個 raw/ 檔案。回傳 'new' / 'updated' / 'skipped'。"""
        content = md_file.read_text(encoding="utf-8")
        metadata, body = extract_frontmatter(content)

        if not body.strip():
            return "skipped"

        # 計算 hash 做 change detection
        content_hash = hashlib.sha256(body.encode()).hexdigest()[:16]
        title = metadata.get("title", "") or md_file.stem.replace("-", " ").strip()

        # 檢查是否已存在（用 title 或 source_file）
        source_file = str(md_file.relative_to(self.raw_dir))
        existing = self.db.conn.execute(
            "SELECT id, content_hash FROM knowledge WHERE source LIKE ?",
            (f"%{source_file}%",),
        ).fetchone()

        if existing and existing["content_hash"] == content_hash:
            return "skipped"  # 沒變

        # 分類
        category = metadata.get("category", "") or classify_content(body, metadata)
        layer = assign_layer(metadata)
        tags = metadata.get("tags", "")
        if isinstance(tags, list):
            tags = ",".join(str(t) for t in tags)
        trust = float(metadata.get("trust", 0.5))
        source = metadata.get("source", source_file)

        # AAAK 壓縮
        aaak = simple_aaak_compress(title, body)

        if dry_run:
            action = "更新" if existing else "新增"
            print(f"  [dry] {action}: {title} (layer={layer}, cat={category})")
            return "new" if not existing else "updated"

        if existing:
            # 更新
            self.db.update_knowledge(
                existing["id"],
                title=title,
                content_raw=body,
                content_aaak=aaak,
                content_hash=content_hash,
                layer=layer,
                category=category,
                tags=tags,
                trust=trust,
                source=str(source_file),
            )
            return "updated"
        else:
            # 新增
            self.db.add_knowledge(
                title=title,
                content_raw=body,
                content_aaak=aaak,
                layer=layer,
                category=category,
                tags=tags,
                trust=trust,
                source=str(source_file),
            )
            return "new"

    def _rebuild_embeddings(self, dry_run: bool):
        """對所有缺嵌入的知識補向量。"""
        if dry_run or self.embed is None:
            return

        # 找出沒有嵌入的知識
        try:
            rows = self.db.conn.execute(
                "SELECT k.id, k.content_raw FROM knowledge k "
                "LEFT JOIN knowledge_vec v ON k.id = v.knowledge_id "
                "WHERE v.knowledge_id IS NULL"
            ).fetchall()
        except Exception:
            # knowledge_vec 可能不存在
            rows = self.db.conn.execute("SELECT id, content_raw FROM knowledge").fetchall()

        if not rows:
            print("[compiler] 所有知識已有嵌入 ✅")
            return

        print(f"[compiler] 生成 {len(rows)} 筆嵌入...")
        texts = [r["content_raw"] for r in rows]
        ids = [r["id"] for r in rows]

        # 批次嵌入
        batch_size = 16
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_ids = ids[i:i + batch_size]
            vectors = self.embed.encode(batch_texts)
            for j, kid in enumerate(batch_ids):
                self.db.add_embedding(kid, vectors[j])

        print(f"[compiler] ✅ {len(rows)} 筆嵌入完成")

    def _update_compiled(self):
        """從 DB 更新 compiled/ 目錄。"""
        self.compiled_dir.mkdir(parents=True, exist_ok=True)

        rows = self.db.conn.execute("SELECT * FROM knowledge ORDER BY layer, id").fetchall()
        for row in rows:
            d = dict(row)
            layer = d.get("layer", "L3")
            cat = d.get("category", "general")
            title = d.get("title", "untitled").replace("/", "-").replace(" ", "_")

            # compiled/L2-error/vllm-timeout.md
            out_dir = self.compiled_dir / f"{layer}-{cat}"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / f"{title}.md"

            # 寫出 AAAK 壓縮版
            aaak = d.get("content_aaak", "") or d.get("content_raw", "")
            fm = {
                "id": d["id"],
                "title": d["title"],
                "layer": layer,
                "category": cat,
                "tags": d.get("tags", ""),
                "trust": d.get("trust", 0.5),
                "hash": d.get("content_hash", ""),
                "updated_at": d.get("updated_at", ""),
            }
            content = f"---\n{yaml.dump(fm, allow_unicode=True, default_flow_style=False)}---\n\n{aaak}\n"
            out_file.write_text(content, encoding="utf-8")

    def _git_commit(self, stats: dict):
        """自動 git commit。"""
        try:
            # 加 guardrails.db 到 git（如果 .gitignore 沒排除）
            subprocess.run(["git", "add", "-A"], cwd=str(self.project_dir),
                           capture_output=True, timeout=10)
            msg = f"guardrails: compile {stats['new']} new, {stats['updated']} updated"
            subprocess.run(["git", "commit", "-m", msg, "--allow-empty"],
                           cwd=str(self.project_dir), capture_output=True, timeout=10)
            print(f"[compiler] ✅ Git commit: {msg}")
        except Exception as e:
            print(f"[compiler] ⚠️ Git commit 失敗（不影響編譯）: {e}")