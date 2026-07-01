"""
Vault-for-LLM — 輕量知識圖譜模組。

功能：
- 自動從 tags/title 內容推斷實體和關聯
- BFS 圖譜遍歷（get_neighbors）
- Mermaid / Graphviz 可視化匯出
- search 時圖譜擴展（graph_expand）
- 支援從 entity_rules.yaml 載入自訂規則（包含中文 domain）
"""

import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .db import VaultDB
from .log import log

_OBSIDIAN_WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]\n]+)\]\]")

# ── 預設規則（YAML 不存在時的 fallback）────────────────────
_DEFAULT_ENTITY_RULES = {
    "tool": ["ollama", "sqlite", "sqlite-vec", "onnx", "onnxruntime", "python",
             "conda", "docker", "ffmpeg", "supabase", "chromadb", "vllm",
             "langchain", "llamaindex", "git", "github", "n8n", "redis"],
    "model": ["qwen", "gpt", "claude", "llama", "mistral", "glm", "gemini",
              "phi", "deepseek", "mixtral", "miniLM"],
    "concept": ["embed", "vector", "rag", "chunk", "token", "prompt",
                "fine-tuning", "推理", "嵌入", "分塊", "圖譜", "搜尋",
                "編譯", "知識庫", "語意", "降級", "context"],
    "platform": ["windows", "wsl", "wsl2", "linux", "macos", "gpu", "cpu"],
}


def _load_entity_rules(project_dir: Optional[Path] = None) -> dict:
    """
    從 entity_rules.yaml 載入規則。
    搜尋順序：
      1. project_dir/entity_rules.yaml
      2. 此檔案同目錄的 ../entity_rules.yaml（repo root）
      3. fallback 使用內建預設規則
    """
    candidates = []
    if project_dir:
        # 規範化路徑，消除 ../ 等路徑遍歷元件
        safe_project_dir = Path(project_dir).resolve()
        candidates.append(safe_project_dir / "entity_rules.yaml")
    # templates/ directory in repo root
    candidates.append(Path(__file__).parent.parent / "templates" / "entity_rules.yaml")
    # repo root（backward compat）
    candidates.append(Path(__file__).parent.parent / "entity_rules.yaml")

    for path in candidates:
        if path.exists():
            try:
                import yaml
                raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                # 確保每個 value 都是 list[str]，並統一轉小寫
                rules = {}
                for etype, keywords in raw.items():
                    if isinstance(keywords, list):
                        rules[etype] = [str(k).lower() for k in keywords if k]
                if rules:
                    return rules
            except Exception as e:
                log.warning(f"⚠️ 無法載入 entity_rules.yaml: {e}，使用預設規則")

    return _DEFAULT_ENTITY_RULES


class VaultGraph:
    """Vault-for-LLM 圖譜引擎。"""

    def __init__(self, db: VaultDB, project_dir: Optional[Path] = None):
        self.db = db
        # 從 YAML 動態載入規則，讓不同 domain 的使用者可以自訂
        self.ENTITY_RULES = _load_entity_rules(project_dir)

    # ── 自動推斷 ────────────────────────────────────────────

    def infer_from_knowledge(self, knowledge_id: int, build_edges: bool = True) -> list[int]:
        """
        從一筆知識的 tags/title/content 自動推斷實體和關聯。
        回傳新建/關聯的 entity ID 列表。
        
        build_edges=False 時只提取實體，不建邊（用於批次建邊場景）。
        """
        k = self.db.get_knowledge(knowledge_id)
        if not k:
            return []

        # 收集所有文字
        text = f"{k['title']} {k['tags']} {k['content_raw']} {k['category']}"

        # 1. 推斷實體
        entity_ids = self._extract_entities(text, knowledge_id)

        # 2. 推斷關聯（只在單條建構時才用）
        if build_edges:
            self._infer_edges_from_shared_entities(knowledge_id)

        return entity_ids

    def infer_all(self) -> dict:
        """
        掃描所有知識條目，推斷實體和關聯。
        回傳統計：新建實體數、新建邊數。
        用批次 SQL 替代 O(N²) 逐條查詢。
        """
        rows = self.db.conn.execute("SELECT id FROM knowledge").fetchall()
        entities_created = 0

        for row in rows:
            kid = row[0]
            result = self.infer_from_knowledge(kid, build_edges=False)
            entities_created += len(result)

        # 批次推斷邊：共用實體的知識條目自動連邊
        edges_created = self._infer_all_edges_batch()
        obsidian_edges_created = self._infer_obsidian_wikilink_edges()

        total_knowledge = len(rows)
        return {
            "entities_created": entities_created,
            "edges_created": edges_created + obsidian_edges_created,
            "obsidian_edges_created": obsidian_edges_created,
            "total_knowledge": total_knowledge,
        }

    def _infer_obsidian_wikilink_edges(self) -> int:
        """Infer graph edges from Obsidian-style wikilinks in imported notes."""
        rows = self.db.conn.execute(
            "SELECT id, title, source, content_raw FROM knowledge"
        ).fetchall()
        if not rows:
            return 0

        def keys_for(row) -> set[str]:
            keys: set[str] = set()
            title = str(row["title"] or "").strip()
            source = str(row["source"] or "").strip()
            for value in (title, source):
                if value:
                    keys.add(value.lower())
            if source:
                normalized = source.replace("\\", "/")
                keys.add(normalized.lower())
                if normalized.startswith("obsidian/"):
                    without_prefix = normalized[len("obsidian/"):]
                    keys.add(without_prefix.lower())
                    keys.add(Path(without_prefix).with_suffix("").as_posix().lower())
                keys.add(Path(normalized).stem.lower())
                keys.add(Path(normalized).with_suffix("").as_posix().lower())
            return {key for key in keys if key}

        index: dict[str, int] = {}
        for row in rows:
            for key in keys_for(row):
                index.setdefault(key, row["id"])

        now = datetime.now(timezone.utc).isoformat()
        existing_edges = {
            (row["source_id"], row["target_id"], row["relation"])
            for row in self.db.conn.execute(
                "SELECT source_id, target_id, relation FROM edges WHERE relation = ?",
                ("obsidian_link",),
            ).fetchall()
        }
        pending_edges: set[tuple[int, int, str]] = set()
        edges_to_add: list[tuple[int, int, str, float, int, str]] = []
        for row in rows:
            source_id = row["id"]
            content = str(row["content_raw"] or "")
            for match in _OBSIDIAN_WIKILINK_RE.finditer(content):
                target = match.group(1).split("|", 1)[0].strip()
                if not target:
                    continue
                candidates = [
                    target,
                    f"{target}.md",
                    Path(target).stem,
                    Path(target).with_suffix("").as_posix(),
                ]
                target_id = None
                for candidate in candidates:
                    target_id = index.get(candidate.replace("\\", "/").lower())
                    if target_id:
                        break
                if not target_id or target_id == source_id:
                    continue
                edge_key = (source_id, target_id, "obsidian_link")
                if edge_key in existing_edges or edge_key in pending_edges:
                    continue
                pending_edges.add(edge_key)
                edges_to_add.append((source_id, target_id, "obsidian_link", 0.8, 1, now))

        if not edges_to_add:
            return 0
        self.db.conn.executemany(
            "INSERT OR IGNORE INTO edges(source_id, target_id, relation, weight, auto_inferred, created_at) "
            "VALUES(?,?,?,?,?,?)",
            edges_to_add,
        )
        self.db.conn.commit()
        return len(edges_to_add)

    def _infer_all_edges_batch(self) -> int:
        """批次推斷所有共用實體的邊，用 INSERT 批次寫入。"""
        # 找出至少被 2 筆知識共用的實體
        # 只保留連接 2-8 筆知識的實體（最具區分度）
        # 超連接的（>8 筆）實體如 "error"、"git" 沒有區分度，會產生太多噪音邊
        shared = self.db.conn.execute(
            "SELECT entity_id, COUNT(DISTINCT knowledge_id) as cnt "
            "FROM entity_knowledge "
            "GROUP BY entity_id HAVING cnt >= 2 AND cnt <= 8"
        ).fetchall()

        if not shared:
            return 0

        # 批次收集所有 (source_id, target_id, relation)
        edges_to_add = []
        now = datetime.now(timezone.utc).isoformat()

        # 先查所有需要的 entity names（參數化查詢防 SQL injection）
        entity_ids = [row[0] for row in shared]
        entity_names = {}
        if entity_ids:
            placeholders = ",".join("?" for _ in entity_ids)
            for row in self.db.conn.execute(
                f"SELECT id, name FROM entities WHERE id IN ({placeholders})",
                entity_ids,
            ).fetchall():
                entity_names[row[0]] = row[1]

        # 批次查所有 entity_knowledge
        ek_rows = []
        if entity_ids:
            placeholders = ",".join("?" for _ in entity_ids)
            ek_rows = self.db.conn.execute(
                f"SELECT entity_id, knowledge_id FROM entity_knowledge "
                f"WHERE entity_id IN ({placeholders})",
                entity_ids,
            ).fetchall()

        # 按 entity_id 分組
        entity_to_kids = defaultdict(list)
        for ek in ek_rows:
            entity_to_kids[ek[0]].append(ek[1])

        # 限制每個實體最多連 20 筆知識，避免邊爆炸
        MAX_KIDS_PER_ENTITY = 20

        edges_created = 0
        for entity_id, kids in entity_to_kids.items():
            kids = kids[:MAX_KIDS_PER_ENTITY]
            name = entity_names.get(entity_id, "entity")
            for i in range(len(kids)):
                for j in range(i + 1, len(kids)):
                    edges_to_add.append((kids[i], kids[j], f"shared_{name}", 0.5, 1, now))

        # 批次 INSERT（用 executemany + 忽略重複）
        if edges_to_add:
            try:
                self.db.conn.executemany(
                    "INSERT OR IGNORE INTO edges(source_id, target_id, relation, weight, auto_inferred, created_at) "
                    "VALUES(?,?,?,?,?,?)",
                    edges_to_add,
                )
                self.db.conn.commit()
                edges_created = len(edges_to_add)
            except Exception as e:
                log.warning(f"⚠️ 批次建邊失敗，回退逐條: {e}")
                for edge in edges_to_add:
                    try:
                        self.db.add_edge(edge[0], edge[1], edge[2], edge[3], auto_inferred=True)
                        edges_created += 1
                    except Exception:
                        pass

        return edges_created

    def _extract_entities(self, text: str, knowledge_id: int) -> list[int]:
        """從文字中提取實體，存入 DB 並連結到知識條目。"""
        text_lower = text.lower()
        entity_ids = []

        for entity_type, keywords in self.ENTITY_RULES.items():
            for kw in keywords:
                if kw in text_lower:
                    eid = self.db.add_entity(kw, entity_type)
                    self.db.link_entity_knowledge(eid, knowledge_id)
                    entity_ids.append(eid)

        # 從知識條目的 tags 欄位提取（逗號/空格分隔，# 前綴）
        k = self.db.get_knowledge(knowledge_id)
        if k and k.get("tags"):
            tags_str = k["tags"]
            for token in re.split(r'[,;，；\s]+', tags_str):
                token = token.strip("# \t")
                if 2 <= len(token) <= 20 and any(c.isalpha() for c in token):
                    token_lower = token.lower()
                    # 跳過停用詞
                    stopwords = {"the", "a", "an", "is", "or", "and", "not", "if",
                                 "of", "in", "on", "to", "for", "with", "from"}
                    if token_lower in stopwords:
                        continue
                    eid = self.db.add_entity(token_lower, "tag")
                    self.db.link_entity_knowledge(eid, knowledge_id)
                    entity_ids.append(eid)

        # 從 title 提取關鍵概念（短詞組）
        if k and k.get("title"):
            title = k["title"]
            # 提取英文關鍵字（2+ 字母的單詞）
            en_words = re.findall(r'\b[a-z]{3,}\b', title.lower())
            # 跳過太通用的詞
            skip_words = {"the", "for", "and", "with", "from", "this", "that",
                          "how", "why", "what", "when", "are", "can", "all",
                          "not", "but", "has", "its", "our", "you", "was"}
            for word in en_words:
                if word not in skip_words:
                    # 已有同名 entity 就不重複建立（add_entity 本身會去重）
                    eid = self.db.add_entity(word, "concept")
                    self.db.link_entity_knowledge(eid, knowledge_id)
                    entity_ids.append(eid)

        return entity_ids

    def _infer_edges_from_shared_entities(self, knowledge_id: int) -> int:
        """
        如果兩筆知識共用同一個實體，自動建立 related_to 邊。
        回傳新建邊數。
        """
        # 找出此條知識關聯的所有實體
        entities = self.db.get_entities_for_knowledge(knowledge_id)
        if not entities:
            return 0

        new_edges = 0
        for entity in entities:
            # 找出同實體的其他知識條目
            related_ids = self.db.get_knowledge_for_entity(entity["name"])
            for other_id in related_ids:
                if other_id != knowledge_id:
                    self.db.add_edge(
                        knowledge_id, other_id,
                        relation=f"shared_{entity['name']}",
                        weight=0.5,
                        auto_inferred=True,
                    )
                    # add_edge 會去重，但回傳的 id 可能是舊的
                    # 我們無法直接判斷是否新建，簡單處理
                    new_edges += 1

        return new_edges

    # ── 手動建立邊 ─────────────────────────────────────────

    def link(self, source_id: int, target_id: int,
             relation: str = "related_to", weight: float = 1.0) -> int:
        """手動建立知識條目之間的關聯。"""
        return self.db.add_edge(source_id, target_id, relation, weight)

    def unlink(self, edge_id: int) -> bool:
        """刪除一條邊。"""
        return self.db.delete_edge(edge_id)

    # ── 圖譜查詢 ────────────────────────────────────────────

    def expand(self, node_id: int, max_depth: int = 2) -> list[dict]:
        """
        從一個節點出發，BFS 擴展到鄰居。
        回傳鄰居列表，每個包含 id, distance, relation, weight。
        """
        neighbors = self.db.get_neighbors(node_id, max_depth=max_depth)

        # 補上鄰居的標題和摘要
        for n in neighbors:
            k = self.db.get_knowledge(n["id"])
            if k:
                n["title"] = k["title"]
                n["layer"] = k.get("layer", "")
                n["category"] = k.get("category", "")
                n["content_preview"] = (k.get("content_aaak") or k.get("content_raw", ""))[:80]

        return neighbors

    def graph_search(self, query: str, limit: int = 10) -> list[dict]:
        """
        圖譜搜尋：根據關鍵字找到起始節點，再沿邊擴展。
        回傳帶 _graph_distance 的結果列表。
        """
        # 先用關鍵字找起始節點
        seed_results = self.db.search_keyword(query, limit=5)
        if not seed_results:
            return []

        # 收集所有直接+間接鄰居
        all_ids = set()
        results = []

        for seed in seed_results:
            seed_id = seed["id"]
            if seed_id in all_ids:
                continue
            all_ids.add(seed_id)
            seed["_graph_distance"] = 0
            results.append(seed)

            # 擴展 1 跳
            neighbors = self.db.get_neighbors(seed_id, max_depth=1)
            for n in neighbors:
                if n["id"] not in all_ids:
                    all_ids.add(n["id"])
                    k = self.db.get_knowledge(n["id"])
                    if k:
                        d = dict(k)
                        d["_graph_distance"] = n["distance"]
                        d["_relation"] = n["relation"]
                        d["_score"] = 0.3  # 圖譜擴展的基礎分數
                        d["_mode"] = "graph"
                        results.append(d)

        # 按距離排序，同距離按 trust
        results.sort(key=lambda x: (x.get("_graph_distance", 99), -x.get("trust", 0)))
        return results[:limit]

    # ── 可視化匯出 ────────────────────────────────────────────

    def to_mermaid(self, node_id: Optional[int] = None, max_depth: int = 2) -> str:
        """
        匯出為 Mermaid 圖表語法。
        - node_id: 指定起點（None = 全部）
        - max_depth: 擴展深度
        """
        lines = ["graph LR"]

        # 決定節點範圍
        if node_id is not None:
            neighbors = self.db.get_neighbors(node_id, max_depth=max_depth)
            node_ids = {node_id} | {n["id"] for n in neighbors}
            edges = self.db.get_edges(node_id=node_id, direction="both")
            # 也加入鄰居的邊
            for n in neighbors:
                edges.extend(self.db.get_edges(node_id=n["id"], direction="both"))
        else:
            all_edges = self.db.get_edges()
            node_ids = set()
            edges = []
            seen_edge_ids = set()
            for e in all_edges:
                if e["id"] not in seen_edge_ids:
                    edges.append(e)
                    seen_edge_ids.add(e["id"])
                node_ids.add(e["source_id"])
                node_ids.add(e["target_id"])

        # 去重邊
        seen = set()
        unique_edges = []
        for e in edges:
            key = (e["source_id"], e["target_id"], e["relation"])
            if key not in seen:
                seen.add(key)
                unique_edges.append(e)

        # 生成節點聲明
        for nid in sorted(node_ids):
            k = self.db.get_knowledge(nid)
            if k:
                label = k["title"][:20].replace('"', "'")
                layer = k.get("layer", "L3")
                style = {"L0": ":::core", "L1": ":::fact", "L2": ":::ctx", "L3": ""}.get(layer, "")
                lines.append(f'    N{nid}["{label}"]{style}')

        # 生成邊
        for e in unique_edges:
            # 通用格式
            rel = e["relation"]
            if rel.startswith("shared_"):
                label = rel.replace("shared_", "")
                arrow = f'--"{label}"-->'
            else:
                arrow = "-->"
            lines.append(f"    N{e['source_id']} {arrow} N{e['target_id']}")

        lines.append("")
        lines.append("    classDef core fill:#f96,stroke:#333,stroke-width:2px")
        lines.append("    classDef fact fill:#9cf,stroke:#333")
        lines.append("    classDef ctx fill:#9f9,stroke:#333")

        return "\n".join(lines)

    def to_graphviz(self, node_id: Optional[int] = None, max_depth: int = 2) -> str:
        """
        匯出為 Graphviz DOT 語法。
        """
        lines = ['digraph VaultGraph {',
                 '    rankdir=LR;',
                 '    node [shape=box, style=filled];',
                 '']

        # 收集節點和邊（邏輯同 to_mermaid）
        if node_id is not None:
            neighbors = self.db.get_neighbors(node_id, max_depth=max_depth)
            node_ids = {node_id} | {n["id"] for n in neighbors}
            all_edges = self.db.get_edges(node_id=node_id, direction="both")
            for n in neighbors:
                all_edges.extend(self.db.get_edges(node_id=n["id"], direction="both"))
        else:
            all_edges = self.db.get_edges()
            node_ids = set()
            for e in all_edges:
                node_ids.add(e["source_id"])
                node_ids.add(e["target_id"])

        # 節點
        layer_colors = {"L0": "#ff6666", "L1": "#6699ff", "L2": "#66ff66", "L3": "#ffffff"}
        for nid in sorted(node_ids):
            k = self.db.get_knowledge(nid)
            if k:
                label = k["title"][:25].replace('"', '\\"')
                color = layer_colors.get(k.get("layer", "L3"), "#ffffff")
                lines.append(f'    N{nid} [label="{label}", fillcolor="{color}"];')

        # 邊（去重）
        seen = set()
        for e in all_edges:
            key = (e["source_id"], e["target_id"], e["relation"])
            if key in seen:
                continue
            seen.add(key)
            rel = e["relation"].replace("shared_", "")
            auto = " [auto]" if e.get("auto_inferred") else ""
            lines.append(f'    N{e["source_id"]} -> N{e["target_id"]} '
                        f'[label="{rel}{auto}"];')

        lines.append('}')
        return "\n".join(lines)

    # ── 清理 ────────────────────────────────────────────────

    def clear_auto_inferred(self):
        """清除所有自動推斷的邊和實體（保留手動建立的）。"""
        self.db.conn.execute("DELETE FROM edges WHERE auto_inferred=1")
        self.db.conn.commit()

        # 清除沒有關聯的實體
        self.db.conn.execute(
            "DELETE FROM entities WHERE id NOT IN "
            "(SELECT DISTINCT entity_id FROM entity_knowledge)"
        )
        self.db.conn.commit()

    def stats(self) -> dict:
        """圖譜統計。"""
        edge_count = self.db.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        entity_count = self.db.conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        auto_edges = self.db.conn.execute(
            "SELECT COUNT(*) FROM edges WHERE auto_inferred=1"
        ).fetchone()[0]
        manual_edges = edge_count - auto_edges

        # 連通分量（簡單估算）
        nodes_in_edges = self.db.conn.execute(
            "SELECT DISTINCT source_id FROM edges UNION "
            "SELECT DISTINCT target_id FROM edges"
        ).fetchall()
        connected_nodes = len(nodes_in_edges)

        return {
            "edges_total": edge_count,
            "edges_auto": auto_edges,
            "edges_manual": manual_edges,
            "entities_total": entity_count,
            "connected_nodes": connected_nodes,
        }
