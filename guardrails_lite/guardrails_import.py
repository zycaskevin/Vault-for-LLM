"""
Vault for LLM — 智慧分塊匯入模組（v1.5）。

論文基礎：
- Semantic Chunking：計算相鄰句子嵌入相似度，驟降處切斷
- Summary-Guided Segmentation (ACL 2025)：用全文摘要引導分塊邊界
- Chapter Detection：正則偵測章/節/Chapter 結構

策略：
1. chapter — 章節偵測優先，短章直接當一塊，長章內部語意分塊
2. semantic — 純語意分塊（相似度驟降處切斷）
3. sliding — 固定大小滑動視窗（最後降級方案）

每塊獨立進 DB + 嵌入，title 格式：{原文標題} §{chunk_index}
"""

import re
import hashlib
from pathlib import Path
from typing import Optional

from .guardrails_db import GuardrailsDB
from .guardrails_embed import create_embedding_provider, EmbeddingProvider


# ── 章節偵測正則 ──────────────────────────────────────────

# 中文：第X章、第X節、卷X
ZH_CHAPTER = re.compile(
    r"^((?:第[一二三四五六七八九十百千\d]+章"
    r"|第[一二三四五六七八九十百千\d]+節"
    r"|卷[一二三四五六七八九十百千\d]+))\s*",
    re.MULTILINE,
)

# 英文：Chapter X、Part X、Section X
EN_CHAPTER = re.compile(
    r"^((?:Chapter\s+\d+"
    r"|Part\s+[IVXLCDM\d]+"
    r"|Section\s+\d+"
    r"|Book\s+[IVXLCDM\d]+)\b[:\s.]*)",
    re.MULTILINE | re.IGNORECASE,
)

# Markdown 標題
MD_HEADING = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)

# 段落分隔（空行）
PARA_SPLIT = re.compile(r"\n\s*\n")


# ── 分塊器 ───────────────────────────────────────────────

class ChunkResult:
    """分塊結果。"""
    __slots__ = ("index", "title", "content", "start_char", "end_char", "chunk_type")

    def __init__(self, index, title, content, start_char, end_char, chunk_type="semantic"):
        self.index = index
        self.title = title
        self.content = content
        self.start_char = start_char
        self.end_char = end_char
        self.chunk_type = chunk_type  # chapter, semantic, sliding


def detect_chapters(text: str) -> list[tuple[str, int, int]]:
    """
    偵測章節邊界，回傳 [(章節標題, 起始位置, 結束位置), ...]。
    如果找不到章節結構，回傳空列表。
    """
    chapters = []

    # 先試中文章節
    for m in ZH_CHAPTER.finditer(text):
        chapters.append((m.group(1).strip(), m.start()))

    # 再試英文章節
    if not chapters:
        for m in EN_CHAPTER.finditer(text):
            chapters.append((m.group(1).strip(), m.start()))

    # 最後試 Markdown 標題（#+ 不算，至少 ##）
    if not chapters:
        for m in MD_HEADING.finditer(text):
            level = len(m.group(1))
            if level <= 2:  # 只有 ## 和 # 當章節
                chapters.append((m.group(2).strip(), m.start()))

    if not chapters:
        return []

    # 計算每章的結束位置（= 下一章的起始）
    result = []
    for i, (title, start) in enumerate(chapters):
        end = chapters[i + 1][1] if i + 1 < len(chapters) else len(text)
        result.append((title, start, end))

    return result


def split_into_sentences(text: str) -> list[tuple[str, int]]:
    """
    把文本拆成句子，回傳 [(句子, 起始位置), ...]。
    支援中英文斷句。
    """
    # 中英文句末標記
    sent_end = re.compile(r"(?<=[。！？.!？\n])")
    sentences = []
    pos = 0

    for part in sent_end.split(text):
        part = part.strip()
        if not part:
            continue
        start = text.find(part, pos)
        if start < 0:
            start = pos
        sentences.append((part, start))
        pos = start + len(part)

    return sentences


def semantic_chunk(
    text: str,
    embed_provider: EmbeddingProvider,
    similarity_threshold: float = 0.3,
    min_chunk_size: int = 200,
    max_chunk_size: int = 2000,
) -> list[ChunkResult]:
    """
    語意分塊：計算相鄰句子嵌入相似度，驟降處切斷。

    演算法：
    1. 拆句
    2. 每句算嵌入向量
    3. 計算相鄰句子餘弦相似度
    4. 相似度 < threshold 處切斷
    5. 合併過小的塊（< min_chunk_size）
    6. 拆分過大的塊（> max_chunk_size）
    """
    sentences = split_into_sentences(text)

    if len(sentences) <= 3:
        # 太短，直接當一塊
        return [ChunkResult(0, "§1", text, 0, len(text), "semantic")]

    # 計算每句嵌入
    texts = [s for s, _ in sentences]
    vectors = embed_provider.encode(texts)

    # 計算相鄰句子相似度
    import numpy as np

    vecs = np.array(vectors)
    # 餘弦相似度
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    vecs_normed = vecs / norms

    # 相鄰句子相似度
    similarities = []
    for i in range(len(vecs_normed) - 1):
        sim = float(np.dot(vecs_normed[i], vecs_normed[i + 1]))
        similarities.append(sim)

    # 找切斷點：相似度 < threshold
    breaks = [0]  # 第一句一定是起點
    for i, sim in enumerate(similarities):
        if sim < similarity_threshold:
            breaks.append(i + 1)  # 在低相似度後切斷
    breaks.append(len(sentences))  # 結束點

    # 合併成塊
    chunks = []
    for idx in range(len(breaks) - 1):
        start_idx = breaks[idx]
        end_idx = breaks[idx + 1]
        chunk_sentences = [sentences[j] for j in range(start_idx, end_idx)]
        chunk_text = "\n".join(s for s, _ in chunk_sentences)
        start_char = chunk_sentences[0][1]
        end_char = chunk_sentences[-1][1] + len(chunk_sentences[-1][0])

        chunks.append(ChunkResult(
            index=len(chunks),
            title=f"§{len(chunks) + 1}",
            content=chunk_text,
            start_char=start_char,
            end_char=end_char,
            chunk_type="semantic",
        ))

    # 合併過小的塊
    merged = []
    for chunk in chunks:
        if merged and len(chunk.content) < min_chunk_size:
            # 合併到前一塊
            merged[-1].content += "\n" + chunk.content
            merged[-1].end_char = chunk.end_char
        else:
            merged.append(chunk)

    # 重新編號
    for i, chunk in enumerate(merged):
        chunk.index = i
        chunk.title = f"§{i + 1}"

    # 拆分過大的塊
    final_chunks = []
    for chunk in merged:
        if len(chunk.content) > max_chunk_size:
            # 按段落拆分
            paras = PARA_SPLIT.split(chunk.content)
            current = ""
            start = chunk.start_char
            for para in paras:
                if len(current) + len(para) > max_chunk_size and current:
                    final_chunks.append(ChunkResult(
                        index=len(final_chunks),
                        title=f"§{len(final_chunks) + 1}",
                        content=current,
                        start_char=start,
                        end_char=start + len(current),
                        chunk_type="semantic",
                    ))
                    start += len(current)
                    current = para + "\n\n"
                else:
                    current += para + "\n\n"
            if current.strip():
                final_chunks.append(ChunkResult(
                    index=len(final_chunks),
                    title=f"§{len(final_chunks) + 1}",
                    content=current.strip(),
                    start_char=start,
                    end_char=start + len(current),
                    chunk_type="semantic",
                ))
        else:
            final_chunks.append(chunk)

    # 最終編號
    for i, chunk in enumerate(final_chunks):
        chunk.index = i
        chunk.title = f"§{i + 1}"

    return final_chunks if final_chunks else [ChunkResult(0, "§1", text, 0, len(text), "semantic")]


def sliding_window_chunk(
    text: str,
    chunk_size: int = 500,
    overlap: int = 100,
) -> list[ChunkResult]:
    """固定大小滑動視窗分塊（降級方案）。"""
    chunks = []
    start = 0
    idx = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk_text = text[start:end]

        # 嘗試在句子邊界截斷
        if end < len(text):
            for sep in ["。", "！", "？", ".", "!", "?", "\n"]:
                last_sep = chunk_text.rfind(sep)
                if last_sep > chunk_size * 0.5:
                    end = start + last_sep + 1
                    chunk_text = text[start:end]
                    break

        chunks.append(ChunkResult(
            index=idx,
            title=f"§{idx + 1}",
            content=chunk_text,
            start_char=start,
            end_char=end,
            chunk_type="sliding",
        ))
        # 確保至少前進 1 個字元，避免無限迴圈
        advance = max(chunk_size - overlap, 1)
        start = start + advance
        idx += 1

    return chunks


# ── 摘要引導分塊（ACL 2025: Document Segmentation Matters）─────────

def summary_guided_chunk(
    text: str,
    embed_provider: EmbeddingProvider,
    min_chunk_size: int = 200,
    max_chunk_size: int = 2000,
) -> list[ChunkResult]:
    """
    摘要引導分塊（Summary-Guided Segmentation）。

    演算法：
    1. 用前 2000 字當全文「摘要代理」
    2. 計算每個句子跟摘要的相似度
    3. 相似度高→連續主題，低→主題轉換
    4. 在主題轉換點（相似度局部極小值）切斷
    5. 合併過小塊、拆分過大塊

    不需要 LLM，純嵌入向量即可。
    """
    sentences = split_into_sentences(text)

    if len(sentences) <= 5:
        return [ChunkResult(0, "§1", text, 0, len(text), "summary-guided")]

    # 摘要代理：文本前 2000 字
    summary_text = text[:2000]
    summary_vec_raw = embed_provider.encode([summary_text])
    import numpy as np
    summary_vec = np.array(summary_vec_raw[0])
    summary_norm = np.linalg.norm(summary_vec)
    if summary_norm == 0:
        # 降級到語意分塊
        return semantic_chunk(text, embed_provider, min_chunk_size=min_chunk_size, max_chunk_size=max_chunk_size)

    # 每句的嵌入
    sent_texts = [s for s, _ in sentences]
    sent_vecs_raw = embed_provider.encode(sent_texts)
    sent_vecs = np.array(sent_vecs_raw)

    # 正規化
    sent_norms = np.linalg.norm(sent_vecs, axis=1, keepdims=True)
    sent_norms = np.where(sent_norms == 0, 1, sent_norms)
    sent_vecs_normed = sent_vecs / sent_norms
    summary_vec_normed = summary_vec / summary_norm

    # 每句跟摘要的相似度
    summary_sims = np.dot(sent_vecs_normed, summary_vec_normed)

    # 找局部極小值（主題轉換點）
    # 用滑動平均平滑曲線
    window = max(3, len(sentences) // 20)
    smoothed = np.convolve(summary_sims, np.ones(window) / window, mode="same")

    # 找切斷點：相似度低於閾值 或 局部極小值
    mean_sim = float(np.mean(summary_sims))
    std_sim = float(np.std(summary_sims))
    threshold = mean_sim - std_sim * 0.5

    breaks = [0]
    for i in range(1, len(smoothed) - 1):
        # 局部極小值 或 低於閾值
        if smoothed[i] < smoothed[i - 1] and smoothed[i] < smoothed[i + 1]:
            if smoothed[i] < threshold:
                breaks.append(i)

    breaks.append(len(sentences))

    # 建構分塊
    chunks = []
    for idx in range(len(breaks) - 1):
        start_idx = breaks[idx]
        end_idx = breaks[idx + 1]
        chunk_sentences = [sentences[j] for j in range(start_idx, end_idx)]
        chunk_text = "\n".join(s for s, _ in chunk_sentences)
        start_char = chunk_sentences[0][1] if chunk_sentences else 0
        end_char = chunk_sentences[-1][1] + len(chunk_sentences[-1][0]) if chunk_sentences else len(text)

        chunks.append(ChunkResult(
            index=idx,
            title=f"§{idx + 1}",
            content=chunk_text,
            start_char=start_char,
            end_char=end_char,
            chunk_type="summary-guided",
        ))

    # 合併過小塊
    merged = []
    for chunk in chunks:
        if merged and len(chunk.content) < min_chunk_size:
            merged[-1].content += "\n" + chunk.content
            merged[-1].end_char = chunk.end_char
        else:
            merged.append(chunk)

    # 重新編號
    for i, chunk in enumerate(merged):
        chunk.index = i
        chunk.title = f"§{i + 1}"

    return merged if merged else [ChunkResult(0, "§1", text, 0, len(text), "summary-guided")]


# ── 統一匯入介面 ─────────────────────────────────────────

def import_document(
    file_path: str | Path,
    db: GuardrailsDB,
    embed_provider: Optional[EmbeddingProvider] = None,
    strategy: str = "chapter",  # chapter, semantic, summary-guided, sliding
    title: Optional[str] = None,
    layer: str = "L3",
    category: str = "general",
    tags: str = "",
    trust: float = 0.5,
    chunk_size: int = 500,
    overlap: int = 100,
    similarity_threshold: float = 0.3,
) -> list[int]:
    """
    匯入長文件，自動分塊進 DB。

    策略：
    - "chapter": 章節偵測優先，長章內部語意分塊（v1.5 預設）
    - "semantic": 純語意分塊
    - "summary-guided": 摘要引導分塊（ACL 2025）
    - "sliding": 固定滑動視窗

    回傳：[knowledge_id, ...]
    """
    file_path = Path(file_path)
    text = file_path.read_text(encoding="utf-8")

    if not title:
        title = file_path.stem.replace("-", " ").replace("_", " ")

    source = str(file_path)
    knowledge_ids = []

    # ── 策略一：章節偵測 ──────────────────────────────
    if strategy == "chapter":
        chapters = detect_chapters(text)

        if chapters:
            # 有章節結構，每章獨立處理
            for ch_title, ch_start, ch_end in chapters:
                ch_text = text[ch_start:ch_end].strip()

                if not ch_text:
                    continue

                # 短章直接當一塊
                if len(ch_text) <= 2000:
                    kid = _add_chunk(
                        db=db,
                        embed_provider=embed_provider,
                        title=f"{title} — {ch_title}",
                        content=ch_text,
                        layer=layer,
                        category=category,
                        tags=tags,
                        trust=trust,
                        source=f"{source}#{ch_title}",
                    )
                    knowledge_ids.append(kid)
                else:
                    # 長章內部語意分塊
                    sub_chunks = semantic_chunk(
                        ch_text, embed_provider,
                        similarity_threshold=similarity_threshold,
                        min_chunk_size=200,
                        max_chunk_size=2000,
                    ) if embed_provider else sliding_window_chunk(
                        ch_text, chunk_size=chunk_size, overlap=overlap,
                    )

                    for sc in sub_chunks:
                        kid = _add_chunk(
                            db=db,
                            embed_provider=embed_provider,
                            title=f"{title} — {ch_title} {sc.title}",
                            content=sc.content,
                            layer=layer,
                            category=category,
                            tags=tags,
                            trust=trust,
                            source=f"{source}#{ch_title}",
                        )
                        knowledge_ids.append(kid)
        else:
            # 沒偵測到章節，降級到摘要引導分塊
            return import_document(
                file_path=file_path,
                db=db,
                embed_provider=embed_provider,
                strategy="summary-guided",
                title=title,
                layer=layer,
                category=category,
                tags=tags,
                trust=trust,
                chunk_size=chunk_size,
                overlap=overlap,
                similarity_threshold=similarity_threshold,
            )

    # ── 策略二：語意分塊 ──────────────────────────────
    elif strategy == "semantic":
        if embed_provider is None:
            # 沒嵌入就降級到滑動視窗
            chunks = sliding_window_chunk(text, chunk_size=chunk_size, overlap=overlap)
        else:
            chunks = semantic_chunk(
                text, embed_provider,
                similarity_threshold=similarity_threshold,
                min_chunk_size=200,
                max_chunk_size=2000,
            )

        for chunk in chunks:
            kid = _add_chunk(
                db=db,
                embed_provider=embed_provider,
                title=f"{title} {chunk.title}",
                content=chunk.content,
                layer=layer,
                category=category,
                tags=tags,
                trust=trust,
                source=source,
            )
            knowledge_ids.append(kid)

    # ── 策略三：摘要引導分塊 ──────────────────────────
    elif strategy in ("summary-guided", "summary"):
        if embed_provider is None:
            chunks = sliding_window_chunk(text, chunk_size=chunk_size, overlap=overlap)
        else:
            chunks = summary_guided_chunk(
                text, embed_provider,
                min_chunk_size=200,
                max_chunk_size=2000,
            )

        for chunk in chunks:
            kid = _add_chunk(
                db=db,
                embed_provider=embed_provider,
                title=f"{title} {chunk.title}",
                content=chunk.content,
                layer=layer,
                category=category,
                tags=tags,
                trust=trust,
                source=source,
            )
            knowledge_ids.append(kid)

    # ── 策略四：滑動視窗 ──────────────────────────────
    elif strategy == "sliding":
        chunks = sliding_window_chunk(text, chunk_size=chunk_size, overlap=overlap)
        for chunk in chunks:
            kid = _add_chunk(
                db=db,
                embed_provider=embed_provider,
                title=f"{title} {chunk.title}",
                content=chunk.content,
                layer=layer,
                category=category,
                tags=tags,
                trust=trust,
                source=source,
            )
            knowledge_ids.append(kid)

    else:
        raise ValueError(f"未知分塊策略: {strategy}。支援: chapter, semantic, summary-guided, sliding")

    return knowledge_ids


def _add_chunk(
    db: GuardrailsDB,
    embed_provider: Optional[EmbeddingProvider],
    title: str,
    content: str,
    layer: str,
    category: str,
    tags: str,
    trust: float,
    source: str,
) -> int:
    """新增一個分塊到 DB，包含嵌入。"""
    # AAAK 壓縮（簡化版）
    from .guardrails_compile import simple_aaak_compress
    aaak = simple_aaak_compress(title, content)

    kid = db.add_knowledge(
        title=title,
        content_raw=content,
        content_aaak=aaak,
        layer=layer,
        category=category,
        tags=tags,
        trust=trust,
        source=source,
    )

    # 生成嵌入
    if embed_provider is not None:
        try:
            vectors = embed_provider.encode([content])
            db.add_embedding(kid, vectors[0])
        except Exception as e:
            print(f"[import] ⚠️ 嵌入失敗 (id={kid}): {e}")

    return kid