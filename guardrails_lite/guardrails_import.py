"""
Vault for LLM — 智慧分塊匯入模組（v2）。

論文基礎：
- Semantic Chunking：計算相鄰句子嵌入相似度，驟降處切斷
- Summary-Guided Segmentation (ACL 2025)：用全文摘要引導分塊邊界
- Chapter Detection：正則偵測章/節/Chapter 結構
- Contextual Retrieval (Anthropic 2024)：每塊前面加上下文摘要再嵌入

策略：
1. chapter — 章節偵測優先，短章直接當一塊，長章內部語意分塊
2. semantic — 純語意分塊（相似度驟降處切斷）
3. summary-guided — 摘要引導分塊（ACL 2025）
4. sliding — 固定大小滑動視窗（最後降級方案）
5. proposition — 命題拆解（v3）：LLM 把段落拆成原子命題

Contextual Retrieval：
- 用 Ollama 本地生成每塊的上下文摘要（1-2句）
- 嵌入時用 context + content 而非純 content
- 搜尋時 content_raw 存原文，content_aaak 存帶上下文的壓縮版
- Ollama 不可用時自動降級（不加上下文）
"""

from __future__ import annotations

import re
import hashlib
import json
import urllib.request
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


# ── Contextual Retrieval（Anthropic 2024）──────────────────────

def contextualize_chunks(
    chunks: list[ChunkResult],
    doc_title: str,
    ollama_model: str = "qwen3:8b",
    ollama_url: str = "http://localhost:11434",
    max_context_length: int = 150,
) -> list[ChunkResult]:
    """
    Contextual Retrieval：為每個分塊生成上下文摘要。

    用 Ollama 本地生成 1-2 句上下文描述，前置到每塊。
    嵌入時用 context + content，搜尋時用原文。

    論文基礎：Anthropic Contextual Retrieval (2024/09)
    - 檢索失敗率降低 49%（結合 BM25 可達 67%）
    - 每塊只加 ~50 tokens，成本極低
    """
    # 檢查 Ollama 是否可用
    try:
        req = urllib.request.Request(
            f"{ollama_url}/api/tags",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            models = json.loads(resp.read()).get("models", [])
            model_names = [m["name"] for m in models]
            # 找最佳可用模型
            available = None
            for preferred in [ollama_model, "qwen3:8b", "llama3.2:3b", "gemma3:4b", "mistral:7b"]:
                for name in model_names:
                    if preferred in name or name.startswith(preferred.split(":")[0]):
                        available = name
                        break
                if available:
                    break
            if not available and model_names:
                available = model_names[0]  # 用第一個可用的
            if not available:
                print("[contextualize] ⚠️ Ollama 沒有可用模型，跳過上下文增強")
                return chunks
    except (urllib.error.URLError, ConnectionError, OSError):
        print("[contextualize] ⚠️ Ollama 未啟動，跳過上下文增強")
        return chunks

    print(f"[contextualize] 使用 {available} 生成上下文摘要...")

    for i, chunk in enumerate(chunks):
        prompt = (
            f"你是一個知識管理助手。以下是一份文件《{doc_title}》的第 {i+1}/{len(chunks)} 個片段。"
            f"請用1-2句話簡要說明這個片段在整份文件中的位置和上下文（它前面和後面大概在說什麼）。"
            f"只輸出上下文描述，不要解釋、不要加引號、不要加前綴。\n\n"
            f"---片段開始---\n{chunk.content[:1500]}\n---片段結束---"
        )

        try:
            payload = json.dumps({
                "model": available,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 100},
            }).encode()

            req = urllib.request.Request(
                f"{ollama_url}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read())
                context = result.get("response", "").strip()

            # 截斷過長的上下文
            if len(context) > max_context_length:
                context = context[:max_context_length - 3] + "..."

            # 加上上下文前綴，但保留原始 content 在 content_raw
            chunk.context_prefix = context

        except Exception as e:
            print(f"[contextualize] ⚠️ 塊 {i+1} 生成失敗: {e}")
            chunk.context_prefix = ""

    return chunks


# ── 分塊器 ───────────────────────────────────────────────

class ChunkResult:
    """分塊結果。"""
    __slots__ = ("index", "title", "content", "start_char", "end_char", "chunk_type", "context_prefix")

    def __init__(self, index, title, content, start_char, end_char, chunk_type="semantic", context_prefix=""):
        self.index = index
        self.title = title
        self.content = content
        self.start_char = start_char
        self.end_char = end_char
        self.chunk_type = chunk_type  # chapter, semantic, sliding, summary-guided
        self.context_prefix = context_prefix  # Contextual Retrieval 上下文


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


# ── 命題拆解（Proposition-level Chunking, v3）──────────────────

def proposition_chunk(
    text: str,
    doc_title: str = "",
    ollama_model: str = "qwen3:8b",
    ollama_url: str = "http://localhost:11434",
    max_propositions_per_chunk: int = 8,
    paragraph_max_chars: int = 2000,
) -> list[ChunkResult]:
    """
    命題拆解：把文本拆成原子命題（Atomic Propositions）。

    論文基礎：Dense X Retrieval (2023)
    - 一段 5-15 句的文本包含多個獨立事實
    - 傳統分塊把整段變一個向量，模糊了具體事實
    - 拆成命題後每條獨立嵌入，精準命中

    流程：
    1. 把文本切成段落（以空行或 ## 標題分隔）
    2. 對每個段落，用 Ollama 拆解成原子命題
    3. 每個命題成為獨立 ChunkResult
    4. Ollama 不可用時降級為句子級分塊（每句一命題）
    """
    # 先拆段落，跳過 frontmatter
    paragraphs = _split_into_paragraphs(text, max_chars=paragraph_max_chars)

    if not paragraphs:
        return [ChunkResult(0, "§1", text, 0, len(text), "proposition")]

    all_props: list[tuple[str, str]] = []  # (proposition, source_heading)

    for para_text, heading in paragraphs:
        # 短段落（<100字）直接當命題，不調 LLM
        if len(para_text) < 100:
            all_props.append((para_text.strip(), heading))
            continue

        # 程式碼塊段落也直接保留
        if para_text.strip().startswith("```") or para_text.strip().startswith("    "):
            all_props.append((para_text.strip(), heading))
            continue

        # 用 LLM 拆命題
        props = _decompose_with_ollama(
            para_text, doc_title=doc_title,
            heading=heading, ollama_model=ollama_model,
            ollama_url=ollama_url,
            max_propositions=max_propositions_per_chunk,
        )
        if props:
            for prop in props:
                all_props.append((prop, heading))
        else:
            # LLM 失敗，降級：把每句當一個命題
            for sent, _ in split_into_sentences(para_text):
                if len(sent.strip()) > 10:  # 太短的跳過
                    all_props.append((sent.strip(), heading))

    if not all_props:
        return [ChunkResult(0, "§1", text, 0, len(text), "proposition")]

    # 每個命題一個 ChunkResult
    results = []
    pos = 0
    for i, (prop, heading) in enumerate(all_props):
        end = pos + len(prop)
        title = f"§{i + 1}"
        if heading:
            title = f"{heading} §{i + 1}"
        results.append(ChunkResult(
            index=i, title=title, content=prop,
            start_char=pos, end_char=end, chunk_type="proposition",
        ))
        pos = end

    return results


def _split_into_paragraphs(
    text: str, max_chars: int = 2000,
) -> list[tuple[str, str]]:
    """
    拆文本成段落，回傳 [(段落文本, 標題), ...]。
    以 Markdown 標題 (##, ###) 或空行分隔。
    自動跳過 YAML frontmatter。
    過長的段落會被裁剪。
    """
    # 跳過 YAML frontmatter
    if text.strip().startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            text = text[end + 3:].strip()

    paragraphs = []
    current_heading = ""
    current_text = ""

    lines = text.split("\n")
    for line in lines:
        # 檢查 Markdown 標題
        heading_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading_match:
            # 存現有段落
            if current_text.strip():
                paragraphs.append((current_text.strip(), current_heading))
            current_heading = heading_match.group(2).strip()
            current_text = ""
            continue

        current_text += line + "\n"

        # 過長就切斷
        if len(current_text) >= max_chars:
            paragraphs.append((current_text.strip(), current_heading))
            current_text = ""

    # 最後一段
    if current_text.strip():
        paragraphs.append((current_text.strip(), current_heading))

    # 過濾太短的段落（可能是 frontmatter 殘留）
    return [(t, h) for t, h in paragraphs if len(t) >= 20]


def _decompose_with_ollama(
    text: str,
    doc_title: str = "",
    heading: str = "",
    ollama_model: str = "qwen3:8b",
    ollama_url: str = "http://localhost:11434",
    max_propositions: int = 8,
) -> list[str] | None:
    """
    用 Ollama 把一段文本拆成原子命題。
    回傳命題列表，失敗回傳 None。
    """
    # 檢查 Ollama 可用性
    try:
        req = urllib.request.Request(
            f"{ollama_url}/api/tags",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            models = json.loads(resp.read()).get("models", [])
            model_names = [m["name"] for m in models]
            available = None
            for preferred in [ollama_model, "qwen3:8b", "qwen2.5:0.5b", "llama3.2:3b", "gemma3:4b"]:
                for name in model_names:
                    if preferred in name or name.startswith(preferred.split(":")[0]):
                        available = name
                        break
                if available:
                    break
            if not available and model_names:
                available = model_names[0]
            if not available:
                return None
    except (urllib.error.URLError, ConnectionError, OSError):
        return None

    context = f"文件《{doc_title}》" if doc_title else "以下文本"
    if heading:
        context += f"的「{heading}」段落"

    prompt = (
        f"你是一個知識管理助手。請把{context}拆解成獨立的原子命題。\n"
        f"規則：\n"
        f"1. 每個命題是一個簡潔、自足的事實陳述\n"
        f"2. 一句話只包含一個事實\n"
        f"3. 保留原來的專有名詞和數字\n"
        f"4. 最多 {max_propositions} 個命題\n"
        f"5. 每行一個命題，不要編號，不要其他說明\n\n"
        f"---文本開始---\n{text[:1500]}\n---文本結束---"
    )

    try:
        payload = json.dumps({
            "model": available,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 300},
        }).encode()

        req = urllib.request.Request(
            f"{ollama_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            response = result.get("response", "").strip()

        # 解析命題（每行一個）
        # 過濾規則：
        # 1. 移除編號前綴（1. 2. - 等）
        # 2. 移除 Markdown 格式（**加粗**、```代碼塊```）
        # 3. 移除 LLM 冗餘回應（「好的」「以下是」「根據您的要求」）
        # 4. 移除太短的行（<10 字）和太長的行（>200 字可能是整段重述）
        # 5. 移除 prompt 洩漏（包含「命題」「拆解」等指令性文字）
        REJECT_PATTERNS = [
            r'^(好的|以下是|根據您|希望|我會|我明白了|我已|以下是拆解|根據上述|文檔標題|文档标题)',
            r'(命題|拆解|規則|簡潔|自足的事實|每行一個|不要編號|不要其他說明|情況性陳述|原子命題|原子命題)',
            r'^```',  # 代碼塊開始
            r'^[{}\[\]]',  # JSON/代碼
        ]
        propositions = []
        in_code_block = False
        for line in response.split("\n"):
            line = line.strip()
            # 跳過代碼塊
            if line.startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue
            # 移除編號前綴
            line = re.sub(r"^[\d\-\•\*\)]+[.\s)]*\s*", "", line)
            # 移除 Markdown 加粗
            line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
            # 移除引用符號
            line = line.strip("\"'" + "\u201c\u201d\u2018\u2019" + "\u300c\u300d\u300e\u300f")
            # 過濾條件
            if not line or len(line) < 10 or len(line) > 200:
                continue
            # 拒絕 prompt 洩漏和 LLM 冗餘
            rejected = False
            for pat in REJECT_PATTERNS:
                if re.search(pat, line):
                    rejected = True
                    break
            if rejected:
                continue
            propositions.append(line)

        return propositions[:max_propositions] if propositions else None

    except Exception as e:
        print(f"[proposition] ⚠️ LLM 拆解失敗: {e}")
        return None


# ── 統一匯入介面 ─────────────────────────────────────────

def import_document(
    file_path: str | Path,
    db: GuardrailsDB,
    embed_provider: Optional[EmbeddingProvider] = None,
    strategy: str = "chapter",  # chapter, semantic, summary-guided, sliding, proposition
    title: Optional[str] = None,
    layer: str = "L3",
    category: str = "general",
    tags: str = "",
    trust: float = 0.5,
    chunk_size: int = 500,
    overlap: int = 100,
    similarity_threshold: float = 0.3,
    contextualize: bool = False,
    ollama_model: str = "qwen3:8b",
    ollama_url: str = "http://localhost:11434",
) -> list[int]:
    """
    匯入長文件，自動分塊進 DB。

    策略：
    - "chapter": 章節偵測優先，長章內部語意分塊（預設）
    - "semantic": 純語意分塊
    - "summary-guided": 摘要引導分塊（ACL 2025）
    - "sliding": 固定滑動視窗

    contextualize: 是否用 Contextual Retrieval（Anthropic 2024）加上下文摘要
    - 需要本機有 Ollama 運行
    - 每塊生成 1-2 句上下文，嵌入時用 context+content

    回傳：[knowledge_id, ...]
    """
    file_path = Path(file_path)
    text = file_path.read_text(encoding="utf-8")

    if not title:
        title = file_path.stem.replace("-", " ").replace("_", " ")

    source = str(file_path)

    # ── 階段一：分塊 ──────────────────────────────────────
    all_chunks: list[tuple[ChunkResult, str, str]] = []  # (chunk, source_ref, parent_title)

    if strategy == "chapter":
        chapters = detect_chapters(text)
        if chapters:
            for ch_title, ch_start, ch_end in chapters:
                ch_text = text[ch_start:ch_end].strip()
                if not ch_text:
                    continue
                if len(ch_text) <= 2000:
                    all_chunks.append((
                        ChunkResult(0, f"§1", ch_text, ch_start, ch_end, "chapter"),
                        f"{source}#{ch_title}",
                        f"{title} — {ch_title}",
                    ))
                else:
                    sub_chunks = semantic_chunk(
                        ch_text, embed_provider,
                        similarity_threshold=similarity_threshold,
                        min_chunk_size=200, max_chunk_size=2000,
                    ) if embed_provider else sliding_window_chunk(
                        ch_text, chunk_size=chunk_size, overlap=overlap,
                    )
                    for sc in sub_chunks:
                        all_chunks.append((
                            sc, f"{source}#{ch_title}",
                            f"{title} — {ch_title} {sc.title}",
                        ))
        else:
            # 沒偵測到章節，降級到摘要引導
            if embed_provider is None:
                chunks = sliding_window_chunk(text, chunk_size=chunk_size, overlap=overlap)
            else:
                chunks = summary_guided_chunk(text, embed_provider, min_chunk_size=200, max_chunk_size=2000)
            for chunk in chunks:
                all_chunks.append((chunk, source, f"{title} {chunk.title}"))

    elif strategy == "semantic":
        if embed_provider is None:
            chunks = sliding_window_chunk(text, chunk_size=chunk_size, overlap=overlap)
        else:
            chunks = semantic_chunk(text, embed_provider, similarity_threshold=similarity_threshold, min_chunk_size=200, max_chunk_size=2000)
        for chunk in chunks:
            all_chunks.append((chunk, source, f"{title} {chunk.title}"))

    elif strategy in ("summary-guided", "summary"):
        if embed_provider is None:
            chunks = sliding_window_chunk(text, chunk_size=chunk_size, overlap=overlap)
        else:
            chunks = summary_guided_chunk(text, embed_provider, min_chunk_size=200, max_chunk_size=2000)
        for chunk in chunks:
            all_chunks.append((chunk, source, f"{title} {chunk.title}"))

    elif strategy == "sliding":
        chunks = sliding_window_chunk(text, chunk_size=chunk_size, overlap=overlap)
        for chunk in chunks:
            all_chunks.append((chunk, source, f"{title} {chunk.title}"))

    elif strategy == "proposition":
        chunks = proposition_chunk(
            text, doc_title=title,
            ollama_model=ollama_model, ollama_url=ollama_url,
            max_propositions_per_chunk=8, paragraph_max_chars=2000,
        )
        for chunk in chunks:
            heading = chunk.title.split(" §")[0] if " §" in chunk.title else chunk.title
            all_chunks.append((chunk, source, f"{title} — {chunk.title}"))

    else:
        raise ValueError(f"未知分塊策略: {strategy}。支援: chapter, semantic, summary-guided, sliding, proposition")

    # ── 階段二：Contextual Retrieval（可選）────────────────────
    if contextualize:
        chunk_list = [c for c, _, _ in all_chunks]
        contextualized = contextualize_chunks(
            chunk_list, doc_title=title,
            ollama_model=ollama_model, ollama_url=ollama_url,
        )
        # 更新回 all_chunks
        for i, (chunk, src, ttl) in enumerate(all_chunks):
            all_chunks[i] = (contextualized[i], src, ttl)

    # ── 階段三：寫入 DB ─────────────────────────────────
    knowledge_ids = []
    for chunk, src, ttl in all_chunks:
        context_prefix = chunk.context_prefix if hasattr(chunk, "context_prefix") and chunk.context_prefix else ""
        kid = _add_chunk(
            db=db,
            embed_provider=embed_provider,
            title=ttl,
            content=chunk.content,
            context_prefix=context_prefix,
            layer=layer,
            category=category,
            tags=tags,
            trust=trust,
            source=src,
        )
        knowledge_ids.append(kid)

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
    context_prefix: str = "",
) -> int:
    """新增一個分塊到 DB，包含嵌入。

    context_prefix: Contextual Retrieval 的上下文摘要。
    - content_raw 存原文（搜尋時顯示原文）
    - content_aaak 存帶上下文的壓縮版
    - 嵌入用 context_prefix + content（這是關鍵！）
    """
    from .guardrails_compile import simple_aaak_compress

    # AAAK 壓縮：如果有上下文，壓縮版包含上下文
    if context_prefix:
        content_for_aaak = f"【{context_prefix}】{content}"
    else:
        content_for_aaak = content
    aaak = simple_aaak_compress(title, content_for_aaak)

    kid = db.add_knowledge(
        title=title,
        content_raw=content,  # 原文，搜尋時顯示
        content_aaak=aaak,    # 帶上下文的壓縮版
        layer=layer,
        category=category,
        tags=tags,
        trust=trust,
        source=source,
    )

    # 生成嵌入：用 context + content（Contextual Retrieval 核心）
    if embed_provider is not None:
        try:
            embed_text = f"{context_prefix}\n{content}" if context_prefix else content
            vectors = embed_provider.encode([embed_text])
            db.add_embedding(kid, vectors[0])
        except Exception as e:
            print(f"[import] ⚠️ 嵌入失敗 (id={kid}): {e}")

    return kid