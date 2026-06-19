"""
Vault-for-LLM 搜尋效能基準測試工具。

比較不同搜尋策略的效果與效能：
- 關鍵詞搜尋 vs 混合搜尋 vs 語義搜尋
- 有無 rerank 的差異
- 輕量 rerank vs cross-encoder rerank
- 有無查詢擴展的差異

指標：召回率、準確率、NDCG、查詢耗時
"""

from __future__ import annotations

import json
import math
import time
import argparse
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from vault.db import VaultDB
from vault.search import VaultSearch
from vault.search_qa import evaluate_search_qa


# ── 測試數據生成 ──────────────────────────────────────

SAMPLE_DOCUMENTS = [
    {
        "title": "Python 程式設計基礎",
        "content": "Python 是一種直譯式、高階、通用型程式語言。Python 的設計哲學強調程式碼的可讀性和簡潔的語法。",
        "category": "programming",
        "tags": ["python", "programming", "language"],
    },
    {
        "title": "資料庫系統概論",
        "content": "資料庫是依照某種資料模型來組織的資料集合，常見的有關聯式資料庫、文件型資料庫、鍵值儲存等。SQL 是關聯式資料庫的標準查詢語言。",
        "category": "database",
        "tags": ["database", "sql", "rdbms"],
    },
    {
        "title": "機器學習入門",
        "content": "機器學習是人工智慧的一個分支，它讓電腦能夠從數據中學習。常見的算法包括線性迴歸、決策樹、隨機森林、類神經網路等。",
        "category": "ai",
        "tags": ["machine learning", "AI", "neural network"],
    },
    {
        "title": "深度學習與神經網路",
        "content": "深度學習是機器學習的子領域，使用多層神經網路進行特徵學習。常見的架構包括 CNN、RNN、Transformer 等。",
        "category": "ai",
        "tags": ["deep learning", "neural network", "CNN", "transformer"],
    },
    {
        "title": "自然語言處理技術",
        "content": "自然語言處理（NLP）是人工智慧和語言學的交叉領域，研究如何讓電腦理解和處理人類語言。常見任務包括文本分類、情感分析、機器翻譯等。",
        "category": "ai",
        "tags": ["nlp", "natural language processing", "text mining"],
    },
    {
        "title": "向量嵌入與語義搜尋",
        "content": "向量嵌入是將文本轉換為數值向量的技術，使得語義相似的文本在向量空間中距離更近。這是語義搜尋和檢索增強生成的基礎。",
        "category": "ai",
        "tags": ["embedding", "semantic search", "vector", "RAG"],
    },
    {
        "title": "檢索增強生成 (RAG) 技術",
        "content": "檢索增強生成結合了資訊檢索和文字生成技術，透過檢索相關文件來增強大型語言模型的生成品質，減少幻覺並提升事實準確性。",
        "category": "ai",
        "tags": ["RAG", "LLM", "retrieval", "generation"],
    },
    {
        "title": "網頁開發前端技術",
        "content": "前端開發涉及 HTML、CSS、JavaScript 等技術，用於建構網頁和網頁應用程式的使用者介面。常見框架有 React、Vue、Angular 等。",
        "category": "web",
        "tags": ["frontend", "html", "css", "javascript", "react", "vue"],
    },
    {
        "title": "後端開發與 API 設計",
        "content": "後端開發負責處理網站的商業邏輯和資料處理，常見技術包括 Node.js、Python Django/Flask、Java Spring 等。RESTful API 是常見的介面設計風格。",
        "category": "web",
        "tags": ["backend", "api", "rest", "nodejs", "django"],
    },
    {
        "title": "資訊安全與密碼學",
        "content": "資訊安全關注保護電腦系統和資料免受未經授權的存取、損壞或攻擊。密碼學是資訊安全的基礎，包括對稱加密、非對稱加密、雜湊函數等。",
        "category": "security",
        "tags": ["security", "cryptography", "encryption"],
    },
    {
        "title": "雲端運算與容器技術",
        "content": "雲端運算透過網路提供彈性的運算資源，容器技術如 Docker 和 Kubernetes 讓應用程式的部署和擴展更加簡單可靠。",
        "category": "cloud",
        "tags": ["cloud", "docker", "kubernetes", "container"],
    },
    {
        "title": "軟體工程與版本控制",
        "content": "軟體工程是將工程化方法應用於軟體開發的學科，包括需求分析、設計、實現、測試和維護。Git 是最流行的版本控制系統。",
        "category": "engineering",
        "tags": ["software engineering", "git", "version control", "devops"],
    },
    {
        "title": "Tool-gated Reading Guide",
        "content": (
            "Tool-gated reading keeps agents from reading whole documents. "
            "Agents should inspect a document map first, then use read_range for evidence."
        ),
        "category": "technique",
        "tags": ["search", "map", "read_range", "citation"],
    },
    {
        "title": "Citation Policy Boundary",
        "content": (
            "Search citations are navigation hints only. Final answer citations must come "
            "from bounded read_range output."
        ),
        "category": "decision",
        "tags": ["citation", "policy", "read_range"],
    },
    {
        "title": "Semantic Vector Lifecycle Runbook",
        "content": (
            "Semantic rebuild refreshes stored vectors and sqlite-vec shadow indexes. "
            "Unfiltered semantic searches can use sqlite-vec, while metadata-filtered "
            "queries keep a scan path to protect recall."
        ),
        "category": "search",
        "tags": ["semantic", "sqlite-vec", "runbook", "recall"],
    },
    {
        "title": "Candidate-first Memory Workflow",
        "content": (
            "Autonomous agents should propose memory candidates before promotion. "
            "Privacy, duplicate, metadata, and quality gates run before active knowledge writes."
        ),
        "category": "memory",
        "tags": ["memory", "candidate", "privacy", "metadata"],
    },
    {
        "title": "Provider Cache Key Design",
        "content": (
            "Semantic cache keys include provider id, dimension, vector kind, hash mode, "
            "and rerank strategy so different embedding modes do not collide."
        ),
        "category": "search",
        "tags": ["cache", "provider", "semantic", "rerank"],
    },
]

# 查詢測試集，每個查詢包含相關文件的 id（1-based index）
QUERY_TEST_SET = [
    {
        "query": "Python 程式語言",
        "relevant_docs": [1],  # 文件 1 最相關
        "relevant_score": [1.0],
    },
    {
        "query": "資料庫與 SQL",
        "relevant_docs": [2],
        "relevant_score": [1.0],
    },
    {
        "query": "機器學習和神經網路",
        "relevant_docs": [3, 4],
        "relevant_score": [1.0, 0.8],
    },
    {
        "query": "自然語言處理 NLP",
        "relevant_docs": [5],
        "relevant_score": [1.0],
    },
    {
        "query": "向量嵌入語義搜尋",
        "relevant_docs": [6],
        "relevant_score": [1.0],
    },
    {
        "query": "RAG 檢索增強生成",
        "relevant_docs": [7, 6],
        "relevant_score": [1.0, 0.5],
    },
    {
        "query": "前端網頁開發",
        "relevant_docs": [8],
        "relevant_score": [1.0],
    },
    {
        "query": "後端 API 設計",
        "relevant_docs": [9],
        "relevant_score": [1.0],
    },
    {
        "query": "資訊安全加密技術",
        "relevant_docs": [10],
        "relevant_score": [1.0],
    },
    {
        "query": "雲端容器 Docker",
        "relevant_docs": [11],
        "relevant_score": [1.0],
    },
    {
        "query": "Git 版本控制軟體工程",
        "relevant_docs": [12],
        "relevant_score": [1.0],
    },
    {
        "query": "深度學習 Transformer",
        "relevant_docs": [4],
        "relevant_score": [1.0],
    },
    {
        "query": "人工智慧的應用",
        "relevant_docs": [3, 4, 5, 6, 7],
        "relevant_score": [1.0, 0.9, 0.8, 0.7, 0.6],
    },
    {
        "query": "如何學習程式設計",
        "relevant_docs": [1, 12],
        "relevant_score": [1.0, 0.5],
    },
    {
        "query": "網站開發全端技術",
        "relevant_docs": [8, 9],
        "relevant_score": [1.0, 0.9],
    },
]


# ── 評估指標 ──────────────────────────────────────────

@dataclass
class SearchResult:
    """單一查詢的搜尋結果。"""
    query: str
    retrieved_docs: List[int]  # 文件 id 列表（按相關性排序）
    retrieved_scores: List[float]
    latency_ms: float


@dataclass
class BenchmarkMetrics:
    """基準測試的綜合指標。"""
    name: str
    num_queries: int = 0
    precision_at_1: float = 0.0
    precision_at_3: float = 0.0
    precision_at_5: float = 0.0
    recall_at_1: float = 0.0
    recall_at_3: float = 0.0
    recall_at_5: float = 0.0
    ndcg_at_3: float = 0.0
    ndcg_at_5: float = 0.0
    mean_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    results: List[SearchResult] = field(default_factory=list)


def dcg(scores: List[float], k: int) -> float:
    """計算 Discounted Cumulative Gain。"""
    dcg_val = 0.0
    for i in range(min(k, len(scores))):
        dcg_val += (2 ** scores[i] - 1) / math.log2(i + 2)
    return dcg_val


def ndcg(relevant_scores: List[float], retrieved_scores: List[float], k: int) -> float:
    """計算 Normalized Discounted Cumulative Gain。"""
    if not relevant_scores:
        return 0.0

    # 理想 DCG（相關文件按相關性排序）
    ideal_scores = sorted(relevant_scores, reverse=True)
    idcg = dcg(ideal_scores, k)
    if idcg == 0:
        return 0.0

    # 實際 DCG
    actual_dcg = dcg(retrieved_scores[:k], k)
    return actual_dcg / idcg


def precision_recall_at_k(
    relevant_docs: List[int],
    retrieved_docs: List[int],
    k: int,
) -> Tuple[float, float]:
    """計算 P@k 和 R@k。"""
    if not relevant_docs:
        return 0.0, 0.0

    retrieved_top_k = set(retrieved_docs[:k])
    relevant_set = set(relevant_docs)

    hits = len(retrieved_top_k & relevant_set)
    precision = hits / k if k > 0 else 0.0
    recall = hits / len(relevant_docs) if relevant_docs else 0.0

    return precision, recall


# ── 基準測試執行 ──────────────────────────────────────

def run_benchmark(
    db: VaultDB,
    search: VaultSearch,
    test_set: List[dict],
    mode: str = "keyword",
    use_rerank: bool = True,
    use_query_expansion: bool = True,
    use_llm_rewrite: bool = False,
    name: Optional[str] = None,
) -> BenchmarkMetrics:
    """
    執行單一配置的基準測試。

    Args:
        db: VaultDB 實例
        search: VaultSearch 實例
        test_set: 測試查詢集
        mode: 搜尋模式
        use_rerank: 是否使用 rerank
        use_query_expansion: 是否使用查詢擴展
        use_llm_rewrite: 是否使用 LLM 查詢改寫
        name: 測試名稱

    Returns:
        BenchmarkMetrics 對象
    """
    if name is None:
        name = f"{mode}_rerank={use_rerank}_qe={use_query_expansion}"

    metrics = BenchmarkMetrics(name=name)
    latencies = []

    for test_case in test_set:
        query = test_case["query"]
        relevant_docs = test_case["relevant_docs"]
        relevant_scores = test_case.get("relevant_score", [1.0] * len(relevant_docs))

        # 執行搜尋並計時
        start_time = time.perf_counter()
        results = search.search(
            query,
            mode=mode,
            limit=5,
            use_rerank=use_rerank,
            use_query_expansion=use_query_expansion,
            use_llm_rewrite=use_llm_rewrite,
        )
        end_time = time.perf_counter()

        latency_ms = (end_time - start_time) * 1000
        latencies.append(latency_ms)

        # 提取檢索到的文件 id
        retrieved_ids = [r["id"] for r in results]
        retrieved_scores = [r.get("_score", 0.0) for r in results]

        # 計算檢索到的文件的相關性分數
        rel_map = {doc_id: score for doc_id, score in zip(relevant_docs, relevant_scores)}
        retrieved_rel_scores = [rel_map.get(doc_id, 0.0) for doc_id in retrieved_ids]

        # 計算指標
        p1, r1 = precision_recall_at_k(relevant_docs, retrieved_ids, 1)
        p3, r3 = precision_recall_at_k(relevant_docs, retrieved_ids, 3)
        p5, r5 = precision_recall_at_k(relevant_docs, retrieved_ids, 5)
        ndcg3 = ndcg(relevant_scores, retrieved_rel_scores, 3)
        ndcg5 = ndcg(relevant_scores, retrieved_rel_scores, 5)

        metrics.precision_at_1 += p1
        metrics.precision_at_3 += p3
        metrics.precision_at_5 += p5
        metrics.recall_at_1 += r1
        metrics.recall_at_3 += r3
        metrics.recall_at_5 += r5
        metrics.ndcg_at_3 += ndcg3
        metrics.ndcg_at_5 += ndcg5

        metrics.results.append(SearchResult(
            query=query,
            retrieved_docs=retrieved_ids,
            retrieved_scores=retrieved_scores,
            latency_ms=latency_ms,
        ))

    # 計算平均值
    n = len(test_set)
    metrics.num_queries = n
    if n > 0:
        metrics.precision_at_1 /= n
        metrics.precision_at_3 /= n
        metrics.precision_at_5 /= n
        metrics.recall_at_1 /= n
        metrics.recall_at_3 /= n
        metrics.recall_at_5 /= n
        metrics.ndcg_at_3 /= n
        metrics.ndcg_at_5 /= n

    # 計算延遲統計
    latencies.sort()
    metrics.mean_latency_ms = sum(latencies) / len(latencies) if latencies else 0
    metrics.p95_latency_ms = latencies[int(len(latencies) * 0.95)] if latencies else 0
    metrics.total_latency_ms = sum(latencies)

    return metrics


# ── 結果輸出 ──────────────────────────────────────────

def print_comparison_table(all_metrics: List[BenchmarkMetrics]) -> None:
    """以表格形式列印多個配置的比較結果。"""
    if not all_metrics:
        print("沒有測試結果")
        return

    # 列印表頭
    headers = [
        "配置", "P@1", "P@3", "P@5",
        "R@1", "R@3", "R@5",
        "NDCG@3", "NDCG@5",
        "平均延遲(ms)", "P95延遲(ms)",
    ]

    # 計算每列的寬度
    col_widths = [len(h) for h in headers]
    for m in all_metrics:
        values = [
            m.name,
            f"{m.precision_at_1:.3f}",
            f"{m.precision_at_3:.3f}",
            f"{m.precision_at_5:.3f}",
            f"{m.recall_at_1:.3f}",
            f"{m.recall_at_3:.3f}",
            f"{m.recall_at_5:.3f}",
            f"{m.ndcg_at_3:.3f}",
            f"{m.ndcg_at_5:.3f}",
            f"{m.mean_latency_ms:.1f}",
            f"{m.p95_latency_ms:.1f}",
        ]
        for i, v in enumerate(values):
            col_widths[i] = max(col_widths[i], len(v))

    # 列印分隔線
    separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    print(separator)

    # 列印表頭
    header_line = "|"
    for i, h in enumerate(headers):
        header_line += f" {h.center(col_widths[i])} |"
    print(header_line)
    print(separator)

    # 列印數據
    for m in all_metrics:
        values = [
            m.name,
            f"{m.precision_at_1:.3f}",
            f"{m.precision_at_3:.3f}",
            f"{m.precision_at_5:.3f}",
            f"{m.recall_at_1:.3f}",
            f"{m.recall_at_3:.3f}",
            f"{m.recall_at_5:.3f}",
            f"{m.ndcg_at_3:.3f}",
            f"{m.ndcg_at_5:.3f}",
            f"{m.mean_latency_ms:.1f}",
            f"{m.p95_latency_ms:.1f}",
        ]
        line = "|"
        for i, v in enumerate(values):
            line += f" {v.rjust(col_widths[i])} |"
        print(line)

    print(separator)


def save_results(all_metrics: List[BenchmarkMetrics], output_path: Path) -> None:
    """保存測試結果到 JSON 文件。"""
    results = []
    for m in all_metrics:
        d = asdict(m)
        # 轉換 SearchResult 對象
        d["results"] = [asdict(r) for r in m.results]
        results.append(d)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n結果已保存到: {output_path}")


def print_search_qa_summary(snapshot: dict, *, label: str) -> None:
    aggregate = snapshot["aggregate"]
    print(f"\nSearch QA fixture: {label}")
    print(f"- total_cases: {aggregate['total_cases']}")
    print(f"- top1_hits: {aggregate['top1_hits']}")
    print(f"- topk_hits: {aggregate['topk_hits']}")
    print(f"- mean_reciprocal_rank: {aggregate['mean_reciprocal_rank']:.3f}")
    print(f"- mean_latency_ms: {aggregate['mean_latency_ms']:.3f}")
    print(f"- p95_latency_ms: {aggregate['p95_latency_ms']:.3f}")


# ── 主程序 ────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Vault-for-LLM 搜尋基準測試")
    parser.add_argument(
        "--db-path",
        type=str,
        default="/tmp/vault_benchmark.db",
        help="測試數據庫路徑",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="結果輸出文件路徑（JSON）；未指定時寫到 /tmp，避免污染 repo",
    )
    parser.add_argument(
        "--embed-provider",
        type=str,
        default="auto",
        help="嵌入模型提供者（auto/None）",
    )
    parser.add_argument(
        "--qa-file",
        type=str,
        default=None,
        help="額外執行 Search QA fixture（例如 benchmarks/search_qa/basic.en.json）",
    )
    parser.add_argument(
        "--qa-modes",
        type=str,
        default="keyword",
        help="Search QA fixture 要跑的模式，逗號分隔（預設 keyword）",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)

    # 確保數據庫不存在（新鮮開始）
    if db_path.exists():
        db_path.unlink()

    # 初始化數據庫
    db = VaultDB(str(db_path))
    db.connect()

    try:
        # 插入測試數據
        print("載入測試數據...")
        for i, doc in enumerate(SAMPLE_DOCUMENTS, 1):
            db.add_knowledge(
                title=doc["title"],
                content_raw=doc["content"],
                category=doc["category"],
                tags=",".join(doc["tags"]),
                trust=0.8 + (i % 5) * 0.04,  # 不同的信任分數
            )
        print(f"已載入 {len(SAMPLE_DOCUMENTS)} 個文件")

        # 初始化搜尋引擎
        embed_provider = None
        if args.embed_provider and args.embed_provider != "None":
            try:
                from vault.embed import create_embedding_provider
                embed_provider = create_embedding_provider(provider=args.embed_provider)
                # 測試嵌入提供者是否真的可用
                try:
                    test_vec = embed_provider.encode("test")
                    if test_vec and len(test_vec) > 0:
                        print(f"使用嵌入提供者: {args.embed_provider}")
                        print(f"  向量維度: {len(test_vec[0])}")
                    else:
                        raise RuntimeError("嵌入返回空結果")
                except Exception as e:
                    print(f"嵌入提供者無法正常工作: {e}")
                    embed_provider = None
                    print("將僅使用關鍵詞搜尋進行基準測試")
            except Exception as e:
                print(f"無法載入嵌入模型: {e}")
                print("將僅使用關鍵詞搜尋進行基準測試")

        search = VaultSearch(db, embed_provider=embed_provider)

        # 列印能力資訊
        print("\n" + "=" * 60)
        print("搜尋引擎能力資訊")
        print("=" * 60)
        info = search.info()
        for tier, capabilities in info.items():
            if tier == "配置":
                continue
            print(f"\n{tier}:")
            for cap, available in capabilities.items():
                status = "✓" if available else "✗"
                print(f"  {status} {cap}")

        # 執行基準測試
        print("\n" + "=" * 60)
        print("開始基準測試")
        print("=" * 60)
        print(f"查詢數量: {len(QUERY_TEST_SET)}")
        print(f"文件數量: {len(SAMPLE_DOCUMENTS)}")
        print()

        all_metrics = []

        # 1. 基礎關鍵詞搜尋（無 rerank）
        print("執行: 關鍵詞搜尋 (無 rerank)...")
        metrics = run_benchmark(
            db, search, QUERY_TEST_SET,
            mode="keyword",
            use_rerank=False,
            use_query_expansion=False,
            name="keyword_no_rerank",
        )
        all_metrics.append(metrics)

        # 2. 關鍵詞搜尋 + 輕量 rerank
        print("執行: 關鍵詞搜尋 + 輕量 rerank...")
        metrics = run_benchmark(
            db, search, QUERY_TEST_SET,
            mode="keyword",
            use_rerank=True,
            use_query_expansion=False,
            name="keyword_lightweight_rerank",
        )
        all_metrics.append(metrics)

        # 3. 關鍵詞搜尋 + 查詢擴展
        print("執行: 關鍵詞搜尋 + 查詢擴展...")
        metrics = run_benchmark(
            db, search, QUERY_TEST_SET,
            mode="keyword",
            use_rerank=False,
            use_query_expansion=True,
            name="keyword_query_expansion",
        )
        all_metrics.append(metrics)

        # 4. 關鍵詞搜尋 + rerank + 查詢擴展
        print("執行: 關鍵詞搜尋 + rerank + 查詢擴展...")
        metrics = run_benchmark(
            db, search, QUERY_TEST_SET,
            mode="keyword",
            use_rerank=True,
            use_query_expansion=True,
            name="keyword_full",
        )
        all_metrics.append(metrics)

        # 如果有嵌入能力，測試向量和混合搜尋
        if search.has_embeddings:
            # 5. 純向量搜尋
            print("執行: 向量搜尋...")
            metrics = run_benchmark(
                db, search, QUERY_TEST_SET,
                mode="vector",
                use_rerank=False,
                use_query_expansion=False,
                name="vector_only",
            )
            all_metrics.append(metrics)

            # 6. 混合搜尋
            print("執行: 混合搜尋...")
            metrics = run_benchmark(
                db, search, QUERY_TEST_SET,
                mode="hybrid",
                use_rerank=True,
                use_query_expansion=True,
                name="hybrid_full",
            )
            all_metrics.append(metrics)

            # 7. 語義搜尋
            print("執行: 語義搜尋...")
            metrics = run_benchmark(
                db, search, QUERY_TEST_SET,
                mode="semantic",
                use_rerank=True,
                use_query_expansion=True,
                name="semantic_full",
            )
            all_metrics.append(metrics)

        # 列印比較結果
        print("\n" + "=" * 60)
        print("基準測試結果比較")
        print("=" * 60)
        print_comparison_table(all_metrics)

        qa_snapshots = []
        if args.qa_file:
            for qa_mode in [mode.strip() for mode in args.qa_modes.split(",") if mode.strip()]:
                snapshot = evaluate_search_qa(
                    db_path=db_path,
                    qa_file=args.qa_file,
                    mode=qa_mode,
                    limit=5,
                    embed_provider=embed_provider,
                    allow_hash=False,
                )
                qa_snapshots.append(snapshot)
                print_search_qa_summary(snapshot, label=f"{Path(args.qa_file).name}:{qa_mode}")

        output_path = Path(args.output) if args.output else Path("/tmp/vault_search_benchmark_results.json")
        if qa_snapshots:
            payload = {
                "metrics": [asdict(m) | {"results": [asdict(r) for r in m.results]} for m in all_metrics],
                "search_qa": qa_snapshots,
            }
            output_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"\n結果已保存到: {output_path}")
        else:
            save_results(all_metrics, output_path)

    finally:
        db.close()
        # 清理測試數據庫
        if db_path.exists():
            db_path.unlink()


if __name__ == "__main__":
    main()
