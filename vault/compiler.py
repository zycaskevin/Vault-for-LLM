"""
Vault-for-LLM — 本地編譯器。

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
import re
import subprocess
import yaml
from datetime import datetime, timezone
from pathlib import Path

from .db import normalize_governance_metadata


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


def safe_path_segment(value: object, default: str = "general") -> str:
    """Return a filesystem-safe path segment for generated artifacts."""
    text = str(value or "").strip()
    text = text.replace("/", "-").replace("\\", "-")
    text = re.sub(r"[^\w.-]+", "-", text, flags=re.UNICODE)
    text = text.strip(" .-_")
    if not text or text in {".", ".."}:
        return default
    return text


def _is_within_path(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def extract_claims(title: str, content: str) -> list[dict]:
    """
    從內容提取原子主張（atomic claims），每條帶 source_span。
    回傳: [{"id": "C1", "claim": "...", "span": "L12-14"}, ...]
    """
    claims = []
    lines = content.strip().split("\n")
    claim_id = 0

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()

        # 跳過空行、標題、程式碼
        if not stripped or stripped.startswith("#") or stripped.startswith("```"):
            continue

        # 列表項 — 提取為原子主張
        if stripped.startswith("- ") or stripped.startswith("* "):
            item = stripped[2:].strip()
            # 去掉過長的，只取核心
            if len(item) > 10:
                # 取第一句或 KEY:VALUE
                if "：" in item or ":" in item:
                    core = item.split("。")[0] if "。" in item else item
                else:
                    core = item.split("。")[0] if "。" in item else item
                if len(core) > 120:
                    core = core[:117] + "..."
                claim_id += 1
                claims.append({
                    "id": f"C{claim_id}",
                    "claim": core,
                    "span": f"L{line_num}",
                })
            continue

        # 數字列表項
        import re
        num_match = re.match(r"^(\d+)\.\s(.+)", stripped)
        if num_match:
            item = num_match.group(2).strip()
            if len(item) > 10:
                core = item.split("。")[0] if "。" in item else item
                if len(core) > 120:
                    core = core[:117] + "..."
                claim_id += 1
                claims.append({
                    "id": f"C{claim_id}",
                    "claim": core,
                    "span": f"L{line_num}",
                })
            continue

        # 普通段落 — 如果足夠長，取第一句為主張
        if len(stripped) > 20 and not stripped.startswith("思考") and not stripped.startswith("//"):
            first_sentence = stripped.split("。")[0]
            if len(first_sentence) > 15:
                claim_id += 1
                claims.append({
                    "id": f"C{claim_id}",
                    "claim": first_sentence + "。" if "。" in stripped else first_sentence,
                    "span": f"L{line_num}",
                })

    return claims[:10]  # 最多 10 條主張


def simple_aaak_compress(title: str, content: str) -> str:
    """
    AAAK 壓縮：把 Markdown 知識壓縮成 KEY:VALUE 格式。
    目標：3-10x 壓縮率，保留核心資訊，人類可讀 + LLM 可解析。

    v3 新增：原子主張 CLAIMS 段，帶 source_span 指回原文行號。

    壓縮策略：
    1. 標題 → TITLE:
    2. 原子主張 → CLAIMS: 段
    3. 列表項 → 縮寫關鍵詞
    4. 段落 → 取第一句 + 核心結論
    5. 去除裝飾性內容（空行、重複、過度解釋）
    6. 程式碼/指令 → 保留關鍵指令
    """
    import re

    lines = content.strip().split("\n")

    # ── 提取原子主張 ──
    claims = extract_claims(title, content)

    # ── 第一輪：提取結構化資訊 ──
    sections = []  # (heading, items)
    current_heading = ""
    current_items = []

    for line in lines:
        stripped = line.strip()

        # 跳過空行
        if not stripped:
            continue

        # 跳過思考過程
        if stripped.startswith("思考:") or stripped.startswith("思考："):
            continue

        # 標題行
        if stripped.startswith("#"):
            # 保存上一個 section
            if current_items:
                sections.append((current_heading, current_items))
            current_heading = stripped.lstrip("#").strip()
            current_items = []
            continue

        # 列表項
        if stripped.startswith("- ") or stripped.startswith("* "):
            item = stripped[2:].strip()
            # 進一步壓縮列表項：移除過度解釋
            if "：" in item or ":" in item:
                # KEY: VALUE 格式，保留
                current_items.append(item)
            else:
                current_items.append(item)
            continue

        # 數字列表
        if re.match(r"^\d+\.\s", stripped):
            item = re.sub(r"^\d+\.\s", "", stripped)
            current_items.append(item)
            continue

        # 程式碼塊
        if stripped.startswith("```"):
            continue

        # 普通段落：取第一句
        if current_heading or current_items:
            # 附加到當前 section
            first_sentence = stripped.split("。")[0].split(". ")[0]
            if len(first_sentence) > 15:  # 只有有意義的才加
                current_items.append(first_sentence + "。")
        else:
            # 沒有 heading 的開頭段落
            current_items.append(stripped.split("。")[0] + "。")

    # 保存最後一個 section
    if current_items:
        sections.append((current_heading, current_items))

    # ── 第二輪：壓縮成 AAAK 格式 ──
    result_parts = [f"TITLE:{title}"]

    # ── 原子主張段 ──
    if claims:
        result_parts.append("CLAIMS:")
        for c in claims:
            result_parts.append(f"- [{c['id']}] {c['claim']} ({c['span']})")

    # AAAK 縮寫對照
    aaak_map = {
        "架構": "ARCH", "設計": "DESIGN", "部署": "DEPLOY", "錯誤": "ERR",
        "解法": "FIX", "步驟": "STEPS", "原因": "WHY", "結果": "RESULT",
        "注意": "WARN", "重要": "IMP", "配置": "CFG", "效能": "PERF",
        "安全": "SEC", "比較": "VS", "最佳實踐": "BEST", "踩坑": "PITFALL",
        "經驗": "EXP", "結論": "CONC", "背景": "BG", "問題": "Q",
        "方法": "HOW", "用途": "USE", "限制": "LIMIT",
    }

    total_items = sum(len(items) for _, items in sections)
    max_items = 8  # 最多保留 8 個要點

    item_count = 0
    for heading, items in sections:
        # 壓縮 heading
        h = heading
        for zh, en in aaak_map.items():
            h = h.replace(zh, en)

        for item in items[:3]:  # 每 section 最多 3 條
            if item_count >= max_items:
                break
            # 壓縮 item
            compressed_item = item
            for zh, en in aaak_map.items():
                compressed_item = compressed_item.replace(zh, en)
            # 截斷過長的 item
            if len(compressed_item) > 100:
                compressed_item = compressed_item[:97] + "..."

            result_parts.append(f"- {compressed_item}")
            item_count += 1

        if item_count >= max_items:
            remaining = total_items - item_count
            if remaining > 0:
                result_parts.append(f"... ({remaining} more)")
            break

    result = "\n".join(result_parts)

    # 長度上限：800 字元（從 500 放寬，容納 CLAIMS 段）
    if len(result) > 800:
        # 從後往前砍，保留 TITLE 和 CLAIMS
        result = result[:797] + "..."

    return result


def generate_summary(content: str, title: str = "", max_chars: int = 80) -> str:
    """
    從內容生成 30-80 字摘要。
    策略：取第一段的前 2-3 句，去空行、去標題、去列表符號。

    Args:
        content: 原始 Markdown 內容
        title: 知識標題（用於 fallback）
        max_chars: 最大字數（預設 80，符合 SCHEMA.md 的 30-80 字範圍）

    Returns:
        摘要字串，不含換行
    """
    lines = content.strip().split("\n")
    sentences = []

    for line in lines:
        stripped = line.strip()

        # 跳過空行、標題、frontmatter 殘留、程式碼
        if not stripped or stripped.startswith("#") or stripped.startswith("```"):
            continue
        if stripped.startswith("---") or stripped.startswith("TITLE:") or stripped.startswith("CLAIMS:"):
            continue

        # 列表項：去掉前綴
        if stripped.startswith("- ") or stripped.startswith("* "):
            stripped = stripped[2:].strip()
        # 數字列表
        import re as _re
        m = _re.match(r"^\d+\.\s", stripped)
        if m:
            stripped = stripped[m.end():]

        # 拆句
        parts = _re.split(r"[。！？\n](?=\S)", stripped)
        for p in parts:
            p = p.strip()
            if len(p) >= 8:  # 至少 8 字才算一句
                sentences.append(p)

    # 組合：盡量湊到 30-80 字
    summary = ""
    for s in sentences:
        candidate = (summary + "。" + s).strip("。") if summary else s
        if len(candidate) > max_chars:
            break
        summary = candidate

    # 太短？加更多句
    if len(summary) < 30 and len(sentences) > len(summary.split("。")):
        # 嘗試加到至少 30 字
        for s in sentences[len(summary.split("。")):]:
            candidate = summary + "。" + s
            if len(candidate) > max_chars:
                break
            summary = candidate

    # 還是太短？用 title fallback
    if len(summary) < 15 and title:
        summary = title

    # 確保結尾有句號
    summary = summary.rstrip("。，, \n")
    if summary and not summary.endswith("。") and not summary.endswith("！") and not summary.endswith("？"):
        summary += "。"

    return summary[:max_chars]  # 最後保險

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
    for d, layer_name in dir_map.items():
        if d in source:
            return layer_name

    # 根據分類推斷
    cat = metadata.get("category", "")
    if cat in ("error", "architecture"):
        return "L2"
    return "L3"


class VaultCompiler:
    """Vault-for-LLM 本地編譯器。"""

    def __init__(
        self,
        project_dir: str | Path = ".",
        db=None,
        embed_provider=None,
        allow_private: bool = False,
    ):
        self.project_dir = Path(project_dir)
        self.raw_dir = self.project_dir / "raw"
        self.compiled_dir = self.project_dir / "compiled"
        self.db = db  # VaultDB，延遲初始化
        self.embed = embed_provider  # 嵌入 provider，可選
        self.allow_private = allow_private

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
        from .db import VaultDB

        # 延遲連接
        close_db = False
        if self.db is None:
            db_path = self.project_dir / "vault.db"
            self.db = VaultDB(str(db_path))
            self.db.connect()
            close_db = True

        stats = {"total_files": 0, "new": 0, "updated": 0, "skipped": 0, "errors": 0}

        try:
            # 收集 raw/ 檔案
            if not self.raw_dir.exists():
                print(f"[compiler] ⚠️ raw/ 目錄不存在: {self.raw_dir}")
                return stats

            raw_root = self.raw_dir.resolve()
            md_files = []
            for candidate in sorted(self.raw_dir.rglob("*.md")):
                if candidate.is_symlink() or not candidate.is_file():
                    print(f"[compiler] ⚠️ 跳過非一般檔案: {candidate}")
                    continue
                if not _is_within_path(candidate, raw_root):
                    print(f"[compiler] ⚠️ 跳過 raw/ 外部檔案: {candidate}")
                    continue
                md_files.append(candidate)
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

            # ── Deduplicate：去除 title 重複（永遠執行）──
            if not dry_run:
                dupes = self.db.conn.execute(
                    "SELECT title, COUNT(*) as cnt FROM knowledge GROUP BY title HAVING cnt > 1"
                ).fetchall()
                for row in dupes:
                    # 保留最早的那筆（id 最小的）
                    ids = self.db.conn.execute(
                        "SELECT id FROM knowledge WHERE title = ? ORDER BY id",
                        (row["title"],),
                    ).fetchall()
                    for d in ids[1:]:  # 跳過第一筆（保留）
                        kid = d["id"]
                        # 先刪子表（避免 FOREIGN KEY 報錯/孤兒 map rows）
                        self.db.conn.execute("DELETE FROM knowledge_claims WHERE knowledge_id = ?", (kid,))
                        self.db.conn.execute("DELETE FROM knowledge_nodes WHERE knowledge_id = ?", (kid,))
                        self.db.conn.execute("DELETE FROM lint_cache WHERE knowledge_id = ?", (kid,))
                        self.db.conn.execute("DELETE FROM entity_knowledge WHERE knowledge_id = ?", (kid,))
                        self.db.conn.execute("DELETE FROM edges WHERE source_id = ? OR target_id = ?", (kid, kid))
                        # 再刪向量
                        try:
                            self.db.conn.execute("DELETE FROM knowledge_vec WHERE knowledge_id = ?", (kid,))
                        except Exception:
                            pass
                        # 最後刪主表
                        self.db.conn.execute("DELETE FROM knowledge WHERE id = ?", (kid,))
                    self.db.conn.commit()
                    removed = len(ids) - 1
                    if removed > 0:
                        print(f"[compiler] 🧹 去重: [{row['title']}] 刪除 {removed} 筆重複")
                        stats["skipped"] += removed

            # 更新 compiled/
            if not dry_run:
                self._backfill_summaries(stats)
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

        # 沒有 frontmatter？自動生成基本 metadata
        if not metadata:
            title = md_file.stem.replace("-", " ").replace("_", " ").strip()
            metadata = {
                "title": title,
                "category": classify_content(body, {}),
                "layer": "L3",
                "tags": "",
                "trust": 0.5,
                "source": str(md_file.relative_to(self.raw_dir)),
            }
            print(f"[compiler] ⚠️ {md_file.name} 缺 frontmatter，自動生成: {title}")

        # 計算 hash 做 change detection
        content_hash = hashlib.sha256(body.encode()).hexdigest()[:16]
        title = metadata.get("title", "") or md_file.stem.replace("-", " ").strip()
        if not self.allow_private:
            from .privacy import scan_privacy

            privacy = scan_privacy(
                "\n".join(
                    [
                        str(title),
                        str(metadata.get("category", "")),
                        str(metadata.get("tags", "")),
                        str(metadata.get("source", "")),
                        str(metadata.get("scope", "")),
                        str(metadata.get("sensitivity", "")),
                        str(metadata.get("owner_agent", "")),
                        str(metadata.get("allowed_agents", "")),
                        str(metadata.get("memory_type", "")),
                        str(metadata.get("valid_from", "")),
                        str(metadata.get("valid_until", "")),
                        body,
                    ]
                )
            )
            if privacy.get("status") == "fail":
                findings = ", ".join(
                    sorted({str(item.get("type", "secret")) for item in privacy.get("findings", [])})
                )
                raise ValueError(f"privacy gate failed for raw file ({findings})")

        # 檢查是否已存在（用 source_file 或 title）
        source_file = str(md_file.relative_to(self.raw_dir))
        # 先用 source_file 找
        existing = self.db.conn.execute(
            "SELECT id, content_hash FROM knowledge WHERE source LIKE ?",
            (f"%{source_file}%",),
        ).fetchone()
        if not existing:
            # 用 title 找同名知識（add 命令可能已經建了）
            existing = self.db.conn.execute(
                "SELECT id, content_hash FROM knowledge WHERE title = ?",
                (title,),
            ).fetchone()
            if existing:
                print(f"[compiler] 🔄 同名知識已存在 (id={existing['id']}), 更新: {title}")

        if existing and existing["content_hash"] == content_hash:
            return "skipped"  # 沒變

        # 分類
        category = safe_path_segment(metadata.get("category", "") or classify_content(body, metadata))
        layer = assign_layer(metadata)
        tags = metadata.get("tags", "")
        if isinstance(tags, list):
            tags = ",".join(str(t) for t in tags)
        trust = float(metadata.get("trust", 0.5))
        governance = normalize_governance_metadata(
            scope=metadata.get("scope", "project"),
            sensitivity=metadata.get("sensitivity", "low"),
            owner_agent=metadata.get("owner_agent", ""),
            allowed_agents=metadata.get("allowed_agents", ""),
            memory_type=metadata.get("memory_type", "knowledge"),
            expires_at=metadata.get("expires_at", ""),
            valid_from=metadata.get("valid_from", ""),
            valid_until=metadata.get("valid_until", ""),
            supersedes_id=metadata.get("supersedes_id"),
        )

        # AAAK 壓縮
        aaak = simple_aaak_compress(title, body)

        # Summary 生成
        summary = generate_summary(body, title=title)

        if dry_run:
            action = "更新" if existing else "新增"
            print(f"  [dry] {action}: {title} (layer={layer}, cat={category})")
            return "new" if not existing else "updated"

        if existing:
            # 更新
            knowledge_id = existing["id"]
            self.db.update_knowledge(
                knowledge_id,
                title=title,
                content_raw=body,
                content_aaak=aaak,
                summary=summary,
                summary_generated_at=datetime.now(timezone.utc).isoformat(),
                content_hash=content_hash,
                layer=layer,
                category=category,
                tags=tags,
                trust=trust,
                source=str(source_file),
                **governance,
            )
            self._refresh_document_map(knowledge_id)
            return "updated"
        else:
            # 新增
            knowledge_id = self.db.add_knowledge(
                title=title,
                content_raw=body,
                content_aaak=aaak,
                summary=summary,
                layer=layer,
                category=category,
                tags=tags,
                trust=trust,
                source=str(source_file),
                **governance,
            )
            self._refresh_document_map(knowledge_id)
            return "new"

    def _refresh_document_map(self, knowledge_id: int) -> None:
        """Refresh Document Map rows for a changed knowledge entry."""
        from .docmap import build_document_map_for_entry

        build_document_map_for_entry(self.db.conn, knowledge_id)

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

    def _backfill_summaries(self, stats: dict):
        """為既有 DB 條目補 summary（一次性修復）。"""
        rows = self.db.conn.execute(
            "SELECT id, title, content_raw FROM knowledge WHERE summary = '' OR summary IS NULL"
        ).fetchall()

        if not rows:
            print("[compiler] 所有條目已有 summary ✅")
            return

        print(f"[compiler] 補 summary: {len(rows)} 筆...")
        now = datetime.now(timezone.utc).isoformat()
        count = 0
        for row in rows:
            try:
                summary = generate_summary(row["content_raw"], title=row["title"])
                if summary:
                    self.db.conn.execute(
                        "UPDATE knowledge SET summary=?, summary_generated_at=? WHERE id=?",
                        (summary, now, row["id"]),
                    )
                    count += 1
            except Exception as e:
                print(f"  ⚠️ id={row['id']}: {e}")

        self.db.conn.commit()
        print(f"[compiler] ✅ 補 {count}/{len(rows)} 筆 summary")

    def _update_compiled(self):
        """從 DB 更新 compiled/ 目錄。"""
        self.compiled_dir.mkdir(parents=True, exist_ok=True)

        rows = self.db.conn.execute("SELECT * FROM knowledge ORDER BY layer, id").fetchall()
        for row in rows:
            d = dict(row)
            layer = d.get("layer", "L3")
            cat = safe_path_segment(d.get("category", "general"))
            title = d.get("title", "untitled").replace("/", "-").replace(" ", "_")

            # compiled/L2-error/vllm-timeout.md
            out_dir = self.compiled_dir / f"{layer}-{cat}"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / f"{title}.md"
            if not _is_within_path(out_file, self.compiled_dir):
                raise ValueError(f"compiled output escaped compiled/: {out_file}")

            # 寫出 AAAK 壓縮版
            aaak = d.get("content_aaak", "") or d.get("content_raw", "")
            fm = {
                "id": d["id"],
                "title": d["title"],
                "layer": layer,
                "category": cat,
                "tags": d.get("tags", ""),
                "trust": d.get("trust", 0.5),
                "summary": d.get("summary", ""),
                "hash": d.get("content_hash", ""),
                "updated_at": d.get("updated_at", ""),
            }
            # 內容：summary 置頂，然後 AAAK
            parts = []
            summary_text = d.get("summary", "")
            if summary_text and d.get("title") != summary_text:  # 避免跟 title fallback 重複
                parts.append(f"## Summary\n\n{summary_text}\n")
            parts.append(aaak)
            body = "\n".join(parts)
            content = f"---\n{yaml.dump(fm, allow_unicode=True, default_flow_style=False)}---\n\n{body}\n"
            out_file.write_text(content, encoding="utf-8")

        # ── 同時寫入 L3-knowledge/aaak/（純 AAAK，不帶 frontmatter）──
        aaak_dir = self.project_dir / "L3-knowledge" / "aaak"
        aaak_dir.mkdir(parents=True, exist_ok=True)
        for row in rows:
            d = dict(row)
            title = d.get("title", "untitled").replace("/", "-").replace(" ", "_")
            aaak = d.get("content_aaak", "") or d.get("content_raw", "")
            if aaak.strip():
                (aaak_dir / f"{title}.aaak.md").write_text(aaak + "\n", encoding="utf-8")

    def _git_commit(self, stats: dict):
        """自動 git commit（只加已 tracked 檔案，避免誤傷 runtime 檔案）。"""
        try:
            # 非 Git 工作樹（例如初次使用的臨時目錄）不嘗試 auto-commit，避免 git diff
            # fallback 到 --no-index 並把 raw stderr 洩漏到 CLI。
            work_tree = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if work_tree.returncode != 0 or work_tree.stdout.strip() != "true":
                return

            # 只用 -u（更新已 tracking 的檔案），不用 -A（避免加 untracked runtime 檔案）
            result = subprocess.run(
                ["git", "add", "-u"], cwd=str(self.project_dir),
                capture_output=True, timeout=10
            )
            if result.returncode != 0:
                return

            # 檢查是否有東西 staged
            diff_check = subprocess.run(
                ["git", "diff", "--cached", "--quiet"], cwd=str(self.project_dir),
                capture_output=True, timeout=5
            )
            if diff_check.returncode == 0:
                # 沒變更，跳過 commit
                return
            if diff_check.returncode != 1:
                return

            msg = f"vault: compile {stats['new']} new, {stats['updated']} updated"
            commit_result = subprocess.run(["git", "commit", "-m", msg],
                                           cwd=str(self.project_dir), capture_output=True, timeout=10)
            if commit_result.returncode == 0:
                print(f"[compiler] ✅ Git commit: {msg}")
        except Exception as e:
            print(f"[compiler] ⚠️ Git commit 失敗（不影響編譯）: {e}")
