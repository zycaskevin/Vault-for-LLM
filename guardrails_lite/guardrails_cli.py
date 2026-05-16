"""
Guardrails Lite — CLI 入口。

用法：
  guardrails init              # 初始化專案
  guardrails add "標題"         # 加入知識
  guardrails import novel.md   # 匯入長文件（自動分塊）
  guardrails compile           # 編譯 raw/ → db + compiled/
  guardrails search "查詢"     # 搜尋知識
  guardrails list              # 列出知識
  guardrails lint              # 健康檢查
  guardrails doctor            # 環境診斷
  guardrails stats             # 統計
  guardrails install-embedding # 安裝嵌入模型
  guardrails config set/get    # 配置管理
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Optional


# ── 專案偵測 ─────────────────────────────────────────────

def find_project_dir() -> Path:
    """往上找含有 guardrails.db 或 raw/ 的目錄。"""
    cwd = Path.cwd()
    for d in [cwd] + list(cwd.parents):
        if (d / "guardrails.db").exists() or (d / "raw").is_dir():
            return d
    return cwd


# ── 子命令 ──────────────────────────────────────────────

def cmd_init(args):
    """初始化 Guardrails Lite 專案。"""
    project_dir = Path(args.project_dir or ".")
    dirs = ["raw", "compiled", "L0-identity", "L1-core-facts", "L2-context", "L3-knowledge"]

    for d in dirs:
        (project_dir / d).mkdir(parents=True, exist_ok=True)
        print(f"  ✅ {d}/")

    # 初始化資料庫
    from guardrails_lite.guardrails_db import GuardrailsDB
    db_path = project_dir / "guardrails.db"
    with GuardrailsDB(str(db_path)) as db:
        db.set_config("embedding_provider", "auto")
        db.set_config("embedding_model", "mix")
        db.set_config("embedding_dim", "384")

    # .gitignore 追加
    gitignore = project_dir / ".gitignore"
    gi_lines = []
    if gitignore.exists():
        gi_lines = gitignore.read_text().splitlines()

    additions = ["# Guardrails Lite", "*.db", "__pycache__/", ".cache/"]
    for a in additions:
        if a not in gi_lines:
            gi_lines.append(a)
    gitignore.write_text("\n".join(gi_lines) + "\n", encoding="utf-8")

    print(f"\n✅ 專案初始化完成: {project_dir.resolve()}")
    print("下一步：")
    print("  1. 在 raw/ 放入 .md 知識檔案")
    print("  2. guardrails compile")
    print("  3. guardrails search \"查詢\"")


def cmd_add(args):
    """新增一筆知識。"""
    from guardrails_lite.guardrails_db import GuardrailsDB

    project_dir = find_project_dir()

    # 如果指定 --file，讀取檔案內容
    content = args.content
    if args.file:
        content = Path(args.file).read_text(encoding="utf-8")

    # 如果只有標題沒內容，開編輯器或 stdin
    if not content:
        print(f"標題: {args.title}")
        print("請輸入內容（Ctrl+D 結束）:")
        content = sys.stdin.read()

    with GuardrailsDB(str(project_dir / "guardrails.db")) as db:
        kid = db.add_knowledge(
            title=args.title,
            content_raw=content,
            layer=args.layer or "L3",
            category=args.category or "general",
            tags=args.tags or "",
            trust=args.trust or 0.5,
            source="cli",
        )
        print(f"✅ 新增知識 ID={kid}")

    # 也寫到 raw/
    raw_file = project_dir / "raw" / f"{args.title.replace(' ', '_').replace('/', '-')}.md"
    fm = {
        "title": args.title,
        "layer": args.layer or "L3",
        "category": args.category or "general",
        "tags": args.tags or "",
        "trust": args.trust or 0.5,
    }
    raw_file.write_text(
        f"---\n{json.dumps(fm, ensure_ascii=False, indent=2)}\n---\n\n{content}\n",
        encoding="utf-8",
    )
    print(f"✅ 同步寫入 raw/{raw_file.name}")


def cmd_compile(args):
    """編譯 raw/ → db + compiled/。"""
    from guardrails_lite.guardrails_db import GuardrailsDB
    from guardrails_lite.guardrails_compile import GuardrailsCompiler

    project_dir = find_project_dir()
    db_path = project_dir / "guardrails.db"

    # 載入嵌入（如果啟用）
    embed = None
    if not args.no_embed:
        try:
            from guardrails_lite.guardrails_embed import create_embedding_provider
            db_temp = GuardrailsDB(str(db_path))
            db_temp.connect()
            provider_name = db_temp.get_config("embedding_provider", "auto")
            model_key = db_temp.get_config("embedding_model", "mix")
            db_temp.close()
            if provider_name != "none":
                embed = create_embedding_provider(provider=provider_name, model_key=model_key)
                print(f"[compile] 嵌入: {provider_name} ({model_key})")
        except Exception as e:
            print(f"[compile] ⚠️ 嵌入未啟用: {e}")

    db = GuardrailsDB(str(db_path))
    db.connect()
    compiler = GuardrailsCompiler(project_dir, db=db, embed_provider=embed)
    stats = compiler.compile(dry_run=args.dry_run)
    db.close()

    print(f"\n📊 編譯結果:")
    print(f"  檔案: {stats['total_files']}")
    print(f"  新增: {stats['new']}")
    print(f"  更新: {stats['updated']}")
    print(f"  跳過: {stats['skipped']}")
    print(f"  錯誤: {stats['errors']}")


def cmd_search(args):
    """搜尋知識。"""
    from guardrails_lite.guardrails_db import GuardrailsDB
    from guardrails_lite.guardrails_search import GuardrailsSearch
    from guardrails_lite.guardrails_embed import create_embedding_provider

    project_dir = find_project_dir()
    db_path = project_dir / "guardrails.db"

    db = GuardrailsDB(str(db_path))
    db.connect()

    # 嵌入
    embed = None
    if not args.keyword_only:
        try:
            provider_name = db.get_config("embedding_provider", "auto")
            model_key = db.get_config("embedding_model", "mix")
            if provider_name != "none":
                embed = create_embedding_provider(provider=provider_name, model_key=model_key)
        except Exception:
            pass

    # 圖譜（如果需要擴展）
    graph = None
    if args.graph_expand > 0:
        try:
            from guardrails_lite.guardrails_graph import GuardrailsGraph
            graph = GuardrailsGraph(db)
        except Exception as e:
            print(f"[search] ⚠️ 圖譜未啟用: {e}")

    mode = "keyword" if args.keyword_only else args.mode
    search = GuardrailsSearch(db, embed_provider=embed, graph=graph)

    results = search.search(
        args.query,
        mode=mode,
        limit=args.limit,
        min_trust=args.min_trust,
        layer=args.layer,
        category=args.category,
        graph_expand=args.graph_expand,
        use_rerank=not args.no_rerank,
    )

    if not results:
        print("🔍 沒有找到匹配的知識")
    else:
        print(f"🔍 找到 {len(results)} 筆 ({results[0].get('_mode', 'unknown')} 模式):\n")
        for r in results:
            score = r.get("_score", 0)
            rerank = r.get("_rerank_score", None)
            mode = r.get("_mode", "?")
            trust = r.get("trust", 0)
            layer = r.get("layer", "?")
            freshness = r.get("freshness", None)
            conv_status = r.get("convergence_status", "")
            graph_dist = r.get("_graph_distance")
            graph_info = f", graph={graph_dist}" if graph_dist is not None else ""
            rerank_info = f", rerank={rerank:.3f}" if rerank is not None else ""
            conv_info = f", conv={conv_status}" if conv_status and conv_status != "unknown" else ""
            print(f"  [{layer}] {r['title']} (trust={trust}, score={score:.3f}{rerank_info}, {mode}{graph_info}{conv_info})")
            # 顯示 best_claim 和 AAAK 摘要
            best_claim = r.get("best_claim", "")
            if best_claim:
                print(f"       💬 {best_claim}")
            else:
                aaak = r.get("content_aaak", "") or r.get("content_raw", "")
                if aaak:
                    preview = aaak[:120].replace("\n", " ")
                    print(f"       {preview}...")
            print()

    db.close()


def cmd_list(args):
    """列出知識。"""
    from guardrails_lite.guardrails_db import GuardrailsDB

    project_dir = find_project_dir()
    db = GuardrailsDB(str(project_dir / "guardrails.db"))
    db.connect()

    items = db.list_knowledge(
        layer=args.layer,
        category=args.category,
        min_trust=args.min_trust,
        limit=args.limit,
    )

    if not items:
        print("📭 知識庫是空的")
    else:
        print(f"📋 {len(items)} 筆知識:\n")
        for item in items:
            print(f"  [{item['layer']}] {item['title']}")
            print(f"       cat={item['category']} trust={item['trust']} tags={item['tags']}")
            print()

    db.close()


def cmd_lint(args):
    """健康檢查。"""
    from guardrails_lite.guardrails_db import GuardrailsDB

    project_dir = find_project_dir()
    db = GuardrailsDB(str(project_dir / "guardrails.db"))
    db.connect()
    embed = None  # Will be loaded lazily for semantic duplicate detection

    issues = []

    # 1. 檢查空內容
    empty = db.conn.execute(
        "SELECT id, title FROM knowledge WHERE content_raw = '' OR content_raw IS NULL"
    ).fetchall()
    for row in empty:
        issues.append(f"⚠️ ID={row['id']} [{row['title']}]: 內容為空")

    # 2. 檢查重複 hash
    dupes = db.conn.execute(
        "SELECT content_hash, COUNT(*) as cnt FROM knowledge "
        "WHERE content_hash != '' GROUP BY content_hash HAVING cnt > 1"
    ).fetchall()
    for row in dupes:
        issues.append(f"⚠️ 重複內容: hash={row['content_hash']} ({row['cnt']} 筆)")

    # 3. 檢查低信任
    low_trust = db.conn.execute(
        "SELECT id, title, trust FROM knowledge WHERE trust < 0.3"
    ).fetchall()
    for row in low_trust:
        issues.append(f"⚠️ ID={row['id']} [{row['title']}]: 信任度過低 ({row['trust']})")

    # 4. 檢查缺嵌入
    if db._vec_available:
        no_embed = db.conn.execute(
            "SELECT COUNT(*) as cnt FROM knowledge k "
            "LEFT JOIN knowledge_vec v ON k.id = v.knowledge_id "
            "WHERE v.knowledge_id IS NULL"
        ).fetchone()
        if no_embed["cnt"] > 0:
            issues.append(f"ℹ️ {no_embed['cnt']} 筆知識缺少嵌入向量")

    # 5. 語意重複偵測（用嵌入向量）
    if db._vec_available and embed is None:
        try:
            from guardrails_lite.guardrails_embed import create_embedding_provider
            embed = create_embedding_provider(
                provider=db.get_config("embedding_provider", "auto"),
                model_key=db.get_config("embedding_model", "mix"),
            )
        except Exception:
            pass

    if db._vec_available and embed is not None:
        try:
            import numpy as np
            # 取所有嵌入
            rows = db.conn.execute("SELECT id, title FROM knowledge").fetchall()
            vec_rows = db.conn.execute("SELECT knowledge_id, embedding FROM knowledge_vec").fetchall()
            if len(vec_rows) > 1:
                import struct
                ids = [r["knowledge_id"] for r in vec_rows]
                vecs = []
                for r in vec_rows:
                    emb = r["embedding"]
                    if isinstance(emb, bytes):
                        dim = len(emb) // 4
                        vecs.append(list(struct.unpack(f"{dim}f", emb)))
                    else:
                        vecs.append(emb)
                vecs_np = np.array(vecs, dtype=np.float32)
                # Normalize
                norms = np.linalg.norm(vecs_np, axis=1, keepdims=True)
                norms = np.clip(norms, a_min=1e-9, a_max=None)
                vecs_np = vecs_np / norms
                # Cosine similarity matrix
                sim_matrix = vecs_np @ vecs_np.T
                # Find high-similarity pairs (excluding self)
                title_map = {r["id"]: r["title"] for r in rows}
                checked = set()
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        if sim_matrix[i][j] > 0.92:
                            pair = tuple(sorted([ids[i], ids[j]]))
                            if pair not in checked:
                                checked.add(pair)
                                t1 = title_map.get(ids[i], f"ID={ids[i]}")[:30]
                                t2 = title_map.get(ids[j], f"ID={ids[j]}")[:30]
                                issues.append(f"⚠️ 語意重複 (sim={sim_matrix[i][j]:.3f}): {t1} ↔ {t2}")
        except Exception as e:
            issues.append(f"ℹ️ 語意重複偵測失敗: {e}")

    # 6. 統計
    stats = db.stats()
    issues.append(f"📊 知識 {stats['knowledge_count']} 筆, 嵌入 {stats['embedding_count']} 筆")

    if all("📊" in i for i in issues):
        print("✅ Lint 通過，沒有問題！")
    else:
        print(f"🔍 Lint 結果 ({len([i for i in issues if '⚠️' in i])} 個問題):\n")
        for issue in issues:
            print(f"  {issue}")

    db.close()


def cmd_doctor(args):
    """環境診斷。"""
    print("🏥 Guardrails Lite 環境診斷\n")

    checks = []

    # Python 版本
    checks.append(("Python", f"{sys.version}", True))

    # sqlite-vec
    try:
        import sqlite_vec
        checks.append(("sqlite-vec", f"✅ {sqlite_vec.__version__ if hasattr(sqlite_vec, '__version__') else 'loaded'}", True))
    except ImportError:
        checks.append(("sqlite-vec", "❌ 未安裝 (pip install sqlite-vec)", False))

    # onnxruntime
    try:
        import onnxruntime
        checks.append(("onnxruntime", f"✅ {onnxruntime.__version__}", True))
    except ImportError:
        checks.append(("onnxruntime", "❌ 未安裝 (pip install onnxruntime)", False))

    # optimum[onnxruntime]
    try:
        from optimum.onnxruntime import ORTModelForFeatureExtraction
        checks.append(("optimum[onnxruntime]", "✅", True))
    except ImportError:
        try:
            import optimum
            checks.append(("optimum[onnxruntime]", f"⚠️ optimum {optimum.__version__} 已裝，缺 onnxruntime", False))
        except ImportError:
            checks.append(("optimum[onnxruntime]", "❌ 未安裝 (pip install optimum[onnxruntime])", False))

    # Ollama（非必要）
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]
            checks.append(("Ollama", f"✅ {len(models)} models (可作嵌入後端)", True))
    except Exception:
        checks.append(("Ollama", "— 未連線（非必要）", True))

    # 專案目錄
    project_dir = find_project_dir()
    db_exists = (project_dir / "guardrails.db").exists()
    raw_exists = (project_dir / "raw").is_dir()
    checks.append(("專案", f"{'✅' if db_exists else '❌'} DB | {'✅' if raw_exists else '❌'} raw/", db_exists and raw_exists))

    # 嵌入模型快取
    cache_dir = Path.home() / ".cache" / "guardrails-lite" / "models"
    if cache_dir.exists():
        models = [d.name for d in cache_dir.iterdir() if d.is_dir()]
        checks.append(("嵌入模型快取", f"✅ {len(models)} 模型", True))
    else:
        checks.append(("嵌入模型快取", "❌ 無 (guardrails install-embedding)", False))

    # 輸出
    all_ok = True
    for name, status, ok in checks:
        print(f"  {name:25s} {status}")
        if not ok:
            all_ok = False

    print()
    if all_ok:
        print("✅ 環境完好！")
    else:
        print("⚠️ 有些依賴缺失，但不影響基本關鍵字搜尋")
        print("   安裝語意搜尋: pip install onnxruntime optimum[onnxruntime]")


def cmd_install_embedding(args):
    """安裝嵌入模型。"""
    from guardrails_lite.guardrails_embed import MODELS, ONNXEmbeddingProvider

    print("📦 Guardrails Lite 嵌入模型安裝\n")
    print("可選模型:")
    for key, info in MODELS.items():
        print(f"  {key}: {info['name']} ({info['language']}, {info['dim']}d, ~{info['size_mb']}MB)")

    model_key = args.model
    if model_key not in MODELS:
        model_key = input("\n選擇模型 (zh/en/mix): ").strip().lower()
        if model_key not in MODELS:
            model_key = "mix"

    info = MODELS[model_key]
    print(f"\n下載 {info['name']} (~{info['size_mb']}MB)...")

    embed = ONNXEmbeddingProvider(model_key=model_key)
    # 觸發下載
    try:
        vec = embed.encode("測試")
        print(f"✅ 模型已安裝！維度: {len(vec[0])}d")
    except Exception as e:
        print(f"❌ 安裝失敗: {e}")
        return

    # 更新 config
    from guardrails_lite.guardrails_db import GuardrailsDB
    project_dir = find_project_dir()
    db = GuardrailsDB(str(project_dir / "guardrails.db"))
    db.connect()
    db.set_config("embedding_provider", "onnx")
    db.set_config("embedding_model", model_key)
    db.set_config("embedding_dim", str(info["dim"]))
    db.close()

    # 重建向量表（維度可能不同）
    print("重建向量索引...")
    db2 = GuardrailsDB(str(project_dir / "guardrails.db"))
    db2.connect()
    db2._init_vec_table()
    db2.close()

    print(f"\n✅ 完成！語意搜尋已啟用")
    print(f"   試試: guardrails search \"查詢\"")


def cmd_stats(args):
    """顯示統計。"""
    from guardrails_lite.guardrails_db import GuardrailsDB

    project_dir = find_project_dir()
    db_path = project_dir / "guardrails.db"

    if not db_path.exists():
        print("❌ 尚未初始化，先執行 guardrails init")
        return

    db = GuardrailsDB(str(db_path))
    db.connect()
    stats = db.stats()

    print("📊 Guardrails Lite 統計\n")
    print(f"  知識筆數:   {stats['knowledge_count']}")
    print(f"  嵌入筆數:   {stats['embedding_count']}")
    print(f"  圖譜邊數:   {stats.get('edge_count', 0)}")
    print(f"  圖譜實體:   {stats.get('entity_count', 0)}")
    print(f"  向量搜尋:   {'✅' if stats['vec_available'] else '❌'}")
    print(f"  DB 大小:    {stats['db_size_mb']} MB")
    print(f"  DB 路徑:    {stats['db_path']}")

    # 分層統計
    rows = db.conn.execute(
        "SELECT layer, COUNT(*) as cnt FROM knowledge GROUP BY layer ORDER BY layer"
    ).fetchall()
    if rows:
        print("\n  分層:")
        for row in rows:
            print(f"    {row['layer']}: {row['cnt']} 筆")

    # 分類統計
    rows = db.conn.execute(
        "SELECT category, COUNT(*) as cnt FROM knowledge GROUP BY category ORDER BY cnt DESC"
    ).fetchall()
    if rows:
        print("\n  分類:")
        for row in rows:
            print(f"    {row['category']}: {row['cnt']} 筆")

    # 圖譜連通度
    if stats.get('edge_count', 0) > 0:
        connected = db.conn.execute(
            "SELECT COUNT(DISTINCT n) FROM ("
            "SELECT source_id AS n FROM edges UNION "
            "SELECT target_id AS n FROM edges)"
        ).fetchone()[0]
        print(f"\n  圖譜連通: {connected}/{stats['knowledge_count']} 節點")

    db.close()


def cmd_graph(args):
    """圖譜操作：build / show / export / link / stats。"""
    from guardrails_lite.guardrails_db import GuardrailsDB
    from guardrails_lite.guardrails_graph import GuardrailsGraph

    project_dir = find_project_dir()
    db_path = project_dir / "guardrails.db"

    if not db_path.exists():
        print("❌ 尚未初始化，先執行 guardrails init")
        return

    db = GuardrailsDB(str(db_path))
    db.connect()
    graph = GuardrailsGraph(db)

    action = args.graph_action

    if action == "build":
        """自動推斷實體和關聯。"""
        print("🔄 掃描知識庫，推斷圖譜...")
        result = graph.infer_all()
        print(f"\n✅ 圖譜建構完成！")
        print(f"   掃描條目: {result['total_knowledge']}")
        print(f"   新增實體: {result['entities_created']}")
        print(f"   新增關聯: {result['edges_created']}")
        print(f"\n   試試: guardrails graph show")
        print(f"         guardrails graph export --format mermaid")
        print(f"         guardrails search '查詢' --graph-expand 1")

    elif action == "show":
        """顯示圖譜摘要。"""
        stats = graph.stats()
        print("🕸️ Guardrails Lite 圖譜\n")
        print(f"  邊（總計）: {stats['edges_total']}")
        print(f"    自動推斷: {stats['edges_auto']}")
        print(f"    手動建立: {stats['edges_manual']}")
        print(f"  實體數量:   {stats['entities_total']}")
        print(f"  連通節點:   {stats['connected_nodes']}")

        # 列出邊
        edges = db.get_edges()
        if edges:
            print(f"\n  最近 {min(len(edges), 20)} 條邊:")
            for e in edges[:20]:
                src = db.get_knowledge(e["source_id"])
                tgt = db.get_knowledge(e["target_id"])
                src_title = src["title"][:30] if src else f"ID={e['source_id']}"
                tgt_title = tgt["title"][:30] if tgt else f"ID={e['target_id']}"
                auto = "自動" if e.get("auto_inferred") else "手動"
                rel = e["relation"]
                print(f"    {src_title} → [{rel}] → {tgt_title} ({auto})")

        # 列出實體
        entities = db.conn.execute("SELECT * FROM entities ORDER BY id DESC LIMIT 20").fetchall()
        if entities:
            print(f"\n  最近 {min(len(entities), 20)} 個實體:")
            for e in entities:
                # 計算每個實體關聯的知識條目數
                cnt = db.conn.execute(
                    "SELECT COUNT(*) FROM entity_knowledge WHERE entity_id=?", (e["id"],)
                ).fetchone()[0]
                print(f"    [{e['entity_type']}] {e['name']} ({cnt} 筆知識)")

    elif action == "export":
        """匯出圖譜為 Mermaid 或 Graphviz 格式。"""
        node_id = args.node_id
        fmt = args.format
        max_depth = args.depth

        if fmt == "mermaid":
            output = graph.to_mermaid(node_id=node_id, max_depth=max_depth)
        elif fmt == "dot":
            output = graph.to_graphviz(node_id=node_id, max_depth=max_depth)
        else:
            print(f"❌ 不支援的格式: {fmt} (使用 mermaid 或 dot)")
            db.close()
            return

        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
            print(f"✅ 已匯出到 {args.output}")
        else:
            print(output)

    elif action == "link":
        """手動建立兩筆知識之間的關聯。"""
        source_id = args.source_id
        target_id = args.target_id
        relation = args.relation
        weight = args.weight

        # 檢查 ID 存在
        if not db.get_knowledge(source_id):
            print(f"❌ 找不到 ID={source_id} 的知識條目")
            db.close()
            return
        if not db.get_knowledge(target_id):
            print(f"❌ 找不到 ID={target_id} 的知識條目")
            db.close()
            return

        edge_id = db.add_edge(source_id, target_id, relation, weight)
        src = db.get_knowledge(source_id)
        tgt = db.get_knowledge(target_id)
        print(f"✅ 已建立關聯:")
        print(f"   {src['title']} → [{relation}] → {tgt['title']}")
        print(f"   權重: {weight}, Edge ID: {edge_id}")

    elif action == "unlink":
        """刪除一條邊。"""
        edge_id = args.edge_id
        if db.delete_edge(edge_id):
            print(f"✅ 已刪除邊 ID={edge_id}")
        else:
            print(f"❌ 找不到邊 ID={edge_id}")

    elif action == "clear":
        """清除所有自動推斷的邊。"""
        graph.clear_auto_inferred()
        print("✅ 已清除所有自動推斷的邊和孤立實體")

    elif action == "expand":
        """圖譜搜尋：從一個節點出發擴展。"""
        node_id = args.node_id
        max_depth = args.depth

        neighbors = graph.expand(node_id, max_depth=max_depth)
        if not neighbors:
            print("📭 沒有找到鄰居節點")
        else:
            print(f"🕸️ 從 ID={node_id} 出發，找到 {len(neighbors)} 個鄰居:\n")
            for n in neighbors:
                title = n.get("title", f"ID={n['id']}")
                print(f"  [距離 {n['distance']}] {title}")
                print(f"    關係: {n['relation']}, 權重: {n['weight']}")
                if n.get("content_preview"):
                    print(f"    {n['content_preview']}...")
                print()

    db.close()


def cmd_import(args):
    """匯入長文件，自動分塊進 DB。"""
    from guardrails_lite.guardrails_db import GuardrailsDB
    from guardrails_lite.guardrails_import import import_document

    project_dir = find_project_dir()
    db_path = project_dir / "guardrails.db"
    file_path = Path(args.file)

    if not file_path.exists():
        print(f"❌ 檔案不存在: {file_path}")
        return

    # 載入嵌入
    embed = None
    if not args.no_embed:
        try:
            from guardrails_lite.guardrails_embed import create_embedding_provider
            db_temp = GuardrailsDB(str(db_path))
            db_temp.connect()
            provider_name = db_temp.get_config("embedding_provider", "auto")
            model_key = db_temp.get_config("embedding_model", "mix")
            db_temp.close()
            if provider_name != "none":
                embed = create_embedding_provider(provider=provider_name, model_key=model_key)
                print(f"[import] 嵌入: {provider_name} ({model_key})")
        except Exception as e:
            print(f"[import] ⚠️ 嵌入未啟用: {e}")

    db = GuardrailsDB(str(db_path))
    db.connect()

    strategy = args.strategy
    title = args.title or file_path.stem.replace("-", " ").replace("_", " ")

    print(f"📖 匯入: {file_path.name}")
    print(f"   策略: {strategy}")
    print(f"   標題: {title}")

    try:
        ids = import_document(
            file_path=file_path,
            db=db,
            embed_provider=embed,
            strategy=strategy,
            title=title,
            layer=args.layer,
            category=args.category,
            tags=args.tags,
            trust=args.trust,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            contextualize=args.contextualize,
            ollama_model=args.ollama_model,
        )

        print(f"\n✅ 匯入完成！")
        print(f"   分塊數: {len(ids)}")
        print(f"   策略: {strategy}")
        if args.contextualize:
            # 檢查是否真的有上下文（Ollama 可能沒跑）
            from guardrails_lite.guardrails_db import GuardrailsDB
            db_check = GuardrailsDB(str(db_path))
            db_check.connect()
            has_context = db_check.conn.execute(
                "SELECT COUNT(*) FROM knowledge WHERE content_aaak LIKE '%【%' LIMIT 1"
            ).fetchone()[0]
            db_check.close()
            if has_context > 0:
                print(f"   上下文增強: ✅ (Contextual Retrieval)")
            else:
                print(f"   上下文增強: ⚠️ 未啟用（Ollama 未連線，已降級）")
        print(f"   ID 範圍: {ids[0]}-{ids[-1] if ids else '?'}")

    except Exception as e:
        print(f"❌ 匯入失敗: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


def cmd_skill(args):
    """技能子命令分派。"""
    if args.skill_action == "push":
        cmd_skill_push(args)
    elif args.skill_action == "search":
        cmd_skill_search(args)
    elif args.skill_action == "pull":
        cmd_skill_pull(args)
    elif args.skill_action == "list":
        cmd_skill_list(args)
    elif args.skill_action == "stats":
        cmd_skill_stats(args)
    else:
        print("用法: guardrails skill {push|search|pull|list|stats}")


def cmd_skill_push(args):
    """向技能市場註冊一個技能。"""
    from guardrails_lite.guardrails_db import GuardrailsDB

    project_dir = find_project_dir()
    db = GuardrailsDB(str(project_dir / "guardrails.db"))
    db.connect()

    # 讀取 SKILL.md
    skill_path = Path(args.file) if args.file else None
    if skill_path and not skill_path.exists():
        print(f"❌ 檔案不存在: {skill_path}")
        db.close()
        return

    content = skill_path.read_text(encoding="utf-8") if skill_path else sys.stdin.read()

    # 解析 frontmatter 提取 name
    name = args.name
    if not name and content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                import yaml
                fm = yaml.safe_load(parts[1])
                name = fm.get("name", "") if isinstance(fm, dict) else ""
            except Exception:
                pass
    if not name:
        name = skill_path.stem if skill_path else "unnamed-skill"

    kid = db.add_skill(
        name=name,
        content_raw=content,
        version=args.version or "1.0.0",
        agent_source=args.agent or "hermes-main",
        category=args.category or "general",
        capabilities=args.capabilities or "",
        dependencies=args.dependencies or "",
        trust=args.trust or 0.5,
        description=args.description or "",
    )

    if kid == -1:
        if getattr(args, 'force', False):
            db.update_skill(
                name,
                version=args.version or "1.0.0",
                content_raw=content,
                agent_source=args.agent or "hermes-main",
                category=args.category or "general",
                capabilities=args.capabilities or "",
                dependencies=args.dependencies or "",
                trust=args.trust or 0.5,
                description=args.description or "",
            )
            print(f"✅ 技能 '{name}' 已強制覆蓋")
        else:
            print(f"⚠️ 技能 '{name}' 已存在。用 --force 覆蓋或先刪除。")
    else:
        print(f"✅ 技能 '{name}' 已註冊 (ID={kid})")

    db.close()


def cmd_skill_search(args):
    """搜尋技能市場。"""
    from guardrails_lite.guardrails_db import GuardrailsDB

    project_dir = find_project_dir()
    db = GuardrailsDB(str(project_dir / "guardrails.db"))
    db.connect()

    results = db.search_skills(
        query=args.query or "",
        capabilities=args.capabilities,
        category=args.category,
        min_trust=args.min_trust or 0.0,
        agent_source=args.agent,
        limit=args.limit or 20,
    )

    if not results:
        print("🔍 沒有找到匹配的技能")
    else:
        print(f"🔍 找到 {len(results)} 個技能:\n")
        for r in results:
            print(f"  🛠️  {r['name']} v{r['version']}")
            print(f"      來源: {r['agent_source']} | 分類: {r['category']} | 信任: {r['trust']}")
            if r.get("capabilities"):
                print(f"      能力: {r['capabilities']}")
            if r.get("dependencies"):
                print(f"      依賴: {r['dependencies']}")
            if r.get("description"):
                print(f"      {r['description']}")
            print()

    db.close()


def cmd_skill_pull(args):
    """從技能市場下載技能到本機 skills/。"""
    from guardrails_lite.guardrails_db import GuardrailsDB

    project_dir = find_project_dir()
    db = GuardrailsDB(str(project_dir / "guardrails.db"))
    db.connect()

    skill = db.get_skill(args.name)
    if not skill:
        print(f"❌ 技能 '{args.name}' 不存在於技能市場")
        db.close()
        return

    # 寫入 ~/.hermes/skills/<name>/
    skills_dir = Path.home() / ".hermes" / "skills" / args.name
    skills_dir.mkdir(parents=True, exist_ok=True)

    skill_file = skills_dir / "SKILL.md"
    skill_file.write_text(skill["content_raw"], encoding="utf-8")
    print(f"✅ 技能 '{args.name}' v{skill['version']} → {skill_file}")

    db.close()


def cmd_skill_list(args):
    """列出技能市場所有技能。"""
    from guardrails_lite.guardrails_db import GuardrailsDB

    project_dir = find_project_dir()
    db = GuardrailsDB(str(project_dir / "guardrails.db"))
    db.connect()

    results = db.list_skills(
        agent_source=args.agent,
        category=args.category,
        min_trust=args.min_trust or 0.0,
        limit=args.limit or 100,
    )

    if not results:
        print("📭 技能市場是空的")
    else:
        print(f"🛠️  技能市場: {len(results)} 個技能\n")
        for r in results:
            print(f"  [{r['agent_source']}] {r['name']} v{r['version']} "
                  f"(trust={r['trust']}, {r['category']})")
            if r.get("description"):
                print(f"      {r['description']}")
            print()

    db.close()


def cmd_skill_stats(args):
    """技能市場統計。"""
    from guardrails_lite.guardrails_db import GuardrailsDB

    project_dir = find_project_dir()
    db = GuardrailsDB(str(project_dir / "guardrails.db"))
    db.connect()

    stats = db.stats()
    print(f"🛠️  技能市場統計")
    print(f"   技能總數: {stats.get('skill_count', 0)}")
    print(f"   知識總數: {stats.get('knowledge_count', 0)}")
    print(f"   向量嵌入: {stats.get('embedding_count', 0)}")
    print(f"   知識圖譜: {stats.get('entity_count', 0)} 實體, {stats.get('edge_count', 0)} 邊")
    print(f"   平均新鮮度: {stats.get('avg_freshness', 0)}")
    print(f"   DB 大小: {stats.get('db_size_mb', 0)} MB")

    db.close()


def cmd_map(args):
    """Document Map 操作：build / show / read / query。"""
    from guardrails_lite.guardrails_db import GuardrailsDB
    from guardrails_lite.guardrails_map import build_document_map_for_entry

    project_dir = find_project_dir()
    db_path = project_dir / "guardrails.db"
    action = args.map_action

    if action == "build":
        db = GuardrailsDB(str(db_path))
        db.connect()
        try:
            if args.knowledge_id is not None:
                knowledge_ids = [args.knowledge_id]
            else:
                knowledge_ids = [
                    row["id"]
                    for row in db.conn.execute("SELECT id FROM knowledge ORDER BY id").fetchall()
                ]

            total_nodes = 0
            total_claims = 0
            for knowledge_id in knowledge_ids:
                try:
                    result = build_document_map_for_entry(db.conn, knowledge_id)
                except ValueError as exc:
                    print(str(exc))
                    return
                total_nodes += result["nodes"]
                total_claims += result["claims"]

            print(
                f"built {len(knowledge_ids)} entries: "
                f"nodes={total_nodes} claims={total_claims}"
            )
        finally:
            db.close()
        return

    if action in {"show", "read", "query"}:
        conn = _connect_map_readonly(db_path)
        if conn is None:
            return
        try:
            if action == "show":
                entry = _get_map_entry(conn, args.knowledge_id)
                if not entry:
                    print(f"Knowledge id not found: {args.knowledge_id}")
                    return

                rows = conn.execute(
                    """SELECT node_uid, level, path, line_start, line_end
                       FROM knowledge_nodes
                       WHERE knowledge_id=?
                       ORDER BY line_start, level, id""",
                    (args.knowledge_id,),
                ).fetchall()

                print(f"#{args.knowledge_id} {entry['title']}")
                if not rows:
                    print(
                        "No document map nodes found. "
                        f"Run: guardrails map build {args.knowledge_id}"
                    )
                    return

                for row in rows:
                    level = max(0, int(row["level"] or 0) - 1)
                    indent = "  " * level
                    print(
                        f"{indent}- {row['path']} [{row['node_uid']}] "
                        f"L{row['line_start']}-L{row['line_end']}"
                    )

            elif action == "read":
                try:
                    start_line, end_line = _parse_map_line_range(args.lines)
                except ValueError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    raise SystemExit(2)

                entry = _get_map_entry(conn, args.knowledge_id)
                if not entry:
                    print(f"Knowledge id not found: {args.knowledge_id}")
                    return

                lines = (entry["content_raw"] or "").splitlines()
                total_lines = len(lines)
                if total_lines == 0:
                    print(f"#{args.knowledge_id} {entry['title']} L0-L0")
                    return

                clamped_start = min(max(1, start_line), total_lines)
                clamped_end = min(max(clamped_start, end_line), total_lines)

                print(f"#{args.knowledge_id} {entry['title']} L{clamped_start}-L{clamped_end}")
                for line_number in range(clamped_start, clamped_end + 1):
                    print(f"{line_number}|{lines[line_number - 1]}")

            elif action == "query":
                pattern = f"%{args.query}%"
                rows = conn.execute(
                    """SELECT c.knowledge_id, k.title, c.claim, c.node_uid,
                              c.line_start, c.line_end, COALESCE(n.path, '') AS path
                       FROM knowledge_claims c
                       JOIN knowledge k ON k.id = c.knowledge_id
                       LEFT JOIN knowledge_nodes n
                         ON n.knowledge_id = c.knowledge_id
                        AND n.node_uid = c.node_uid
                       WHERE c.claim LIKE ? OR k.title LIKE ? OR COALESCE(n.path, '') LIKE ?
                       ORDER BY c.knowledge_id, c.line_start, c.id
                       LIMIT ?""",
                    (pattern, pattern, pattern, args.limit),
                ).fetchall()

                if not rows:
                    print("No matching document map claims")
                    return

                for row in rows:
                    path = f" {row['path']}" if row["path"] else ""
                    node_uid = f" [{row['node_uid']}]" if row["node_uid"] else ""
                    print(
                        f"#{row['knowledge_id']} {row['title']} "
                        f"L{row['line_start']}-L{row['line_end']}{path}{node_uid}"
                    )
                    print(f"  {row['claim']}")
        finally:
            conn.close()
        return

    print("用法: guardrails map {build|show|read|query}")


def _connect_map_readonly(db_path: Path) -> sqlite3.Connection | None:
    """Open guardrails.db in SQLite read-only mode for map navigation commands."""
    if not db_path.exists():
        print(f"guardrails.db not found at {db_path}. Run guardrails init/compile first.")
        return None

    try:
        conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.OperationalError as exc:
        print(f"Unable to open guardrails.db read-only at {db_path}: {exc}")
        return None
    conn.row_factory = sqlite3.Row
    return conn


def _get_map_entry(conn: sqlite3.Connection, knowledge_id: int) -> sqlite3.Row | None:
    """Fetch a knowledge row through a raw SQLite connection."""
    return conn.execute("SELECT * FROM knowledge WHERE id=?", (knowledge_id,)).fetchone()


def _positive_int(value: str) -> int:
    """Argparse type requiring a positive integer."""
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _parse_map_line_range(value: str) -> tuple[int, int]:
    """Parse an inclusive START-END line range for `guardrails map read`."""
    if not value or "-" not in value:
        raise ValueError("--lines must be START-END")
    start_raw, end_raw = value.split("-", 1)
    try:
        start_line = int(start_raw)
        end_line = int(end_raw)
    except ValueError as exc:
        raise ValueError("--lines must be START-END") from exc
    if start_line < 1 or end_line < 1 or end_line < start_line:
        raise ValueError("--lines must be a positive START-END range")
    return start_line, end_line


def cmd_config(args):
    """配置管理。"""
    from guardrails_lite.guardrails_db import GuardrailsDB

    project_dir = find_project_dir()
    db = GuardrailsDB(str(project_dir / "guardrails.db"))
    db.connect()

    if args.config_action == "set" and len(args.config_args) >= 2:
        key, value = args.config_args[0], args.config_args[1]
        db.set_config(key, value)
        print(f"✅ {key} = {value}")
    elif args.config_action == "get" and len(args.config_args) >= 1:
        key = args.config_args[0]
        value = db.get_config(key)
        print(f"{key} = {value}")
    elif args.config_action == "list":
        rows = db.conn.execute("SELECT key, value FROM config").fetchall()
        for row in rows:
            print(f"  {row['key']} = {row['value']}")
    else:
        print("用法: guardrails config set <key> <value>")
        print("      guardrails config get <key>")
        print("      guardrails config list")

    db.close()


def cmd_converge(args):
    """收斂檢查 — 自問知識是否充足。"""
    from scripts.convergence_check import check_convergence

    db_path = str(find_project_dir() / "guardrails.db")
    check_convergence(
        db_path=db_path,
        apply=args.apply,
        limit=args.limit,
        min_trust=args.min_trust,
        ollama_model=args.ollama,
        api_url=args.api,
        api_key=args.api_key,
    )


def cmd_cross_validate(args):
    """跨模型不對稱驗證。"""
    from scripts.cross_validate import cross_validate

    db_path = str(find_project_dir() / "guardrails.db")
    cross_validate(
        db_path=db_path,
        apply=args.apply,
        limit=args.limit,
        min_trust=args.min_trust,
        local_only=args.local_only,
        local_model=args.local_model,
        cloud_model=args.cloud_model,
    )


def cmd_freshness(args):
    """知識新鮮度追蹤與審查排程。"""
    from scripts.freshness_check import check_freshness

    db_path = str(find_project_dir() / "guardrails.db")
    check_freshness(
        db_path=db_path,
        apply=args.apply,
        limit=args.limit,
        stale_only=args.stale_only,
    )


def cmd_dedup(args):
    """語意去重 — 檢測與合併重複知識。"""
    from scripts.deduplicate_semantic import find_duplicates, merge_duplicates

    db_path = str(find_project_dir() / "guardrails.db")
    duplicates = find_duplicates(db_path=db_path, threshold=args.threshold)
    if duplicates:
        if args.merge:
            print("\n" + "=" * 50)
            merge_duplicates(db_path=db_path, dry_run=False)
        elif args.dry_run:
            print("\n💡 加 --merge 實際合併")
        else:
            print("\n💡 加 --merge 實際合併，加 --dry-run 預覽計劃")
    else:
        print("✅ 沒有發現重複條目")


def cmd_search_qa(args):
    """Search QA snapshot run / before-after compare."""
    from guardrails_lite.search_qa import (
        compare_search_qa_snapshots,
        evaluate_search_qa,
        format_search_qa_comparison,
        format_search_qa_snapshot,
        write_json,
    )

    action = args.search_qa_action
    if action == "run":
        db_path = Path(args.db_path) if args.db_path else find_project_dir() / "guardrails.db"
        snapshot = evaluate_search_qa(
            db_path=db_path,
            qa_file=args.qa_file,
            mode=args.mode,
            limit=args.limit,
        )
        if args.output:
            write_json(args.output, snapshot)
        print(format_search_qa_snapshot(snapshot))
        return

    if action == "compare":
        comparison = compare_search_qa_snapshots(args.before, args.after)
        if args.output:
            write_json(args.output, comparison)
        print(format_search_qa_comparison(comparison))
        return

    print("error: search-qa requires action: run or compare", file=sys.stderr)
    raise SystemExit(2)

# ── CLI 入口 ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="vault",
        description="Vault-for-LLM — local-first knowledge vault for LLM agents",
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    # init
    p = sub.add_parser("init", help="初始化專案")
    p.add_argument("project_dir", nargs="?", default=".")

    # add
    p = sub.add_parser("add", help="新增知識")
    p.add_argument("title", help="標題")
    p.add_argument("--content", "-c", default="", help="內容")
    p.add_argument("--file", "-f", help="從檔案讀取內容")
    p.add_argument("--layer", choices=["L0", "L1", "L2", "L3"], default="L3")
    p.add_argument("--category", default="general")
    p.add_argument("--tags", default="")
    p.add_argument("--trust", type=float, default=0.5)

    # compile
    p = sub.add_parser("compile", help="編譯 raw/ → db + compiled/")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-embed", action="store_true", help="跳過嵌入生成")

    # search — 加入 --graph-expand
    p = sub.add_parser("search", help="搜尋知識")
    p.add_argument("query", help="搜尋查詢")
    p.add_argument("--mode", choices=["auto", "keyword", "vector", "hybrid"], default="auto")
    p.add_argument("--keyword-only", "-k", action="store_true")
    p.add_argument("--limit", "-n", type=int, default=10)
    p.add_argument("--min-trust", type=float, default=0.0)
    p.add_argument("--layer", choices=["L0", "L1", "L2", "L3"])
    p.add_argument("--category")
    p.add_argument("--graph-expand", type=int, default=0,
                   help="圖譜擴展跳數（0=不擴展，1=1跳，2=2跳）")
    p.add_argument("--no-rerank", action="store_true",
                   help="停用 reranker 重排序")

    # list
    p = sub.add_parser("list", help="列出知識")
    p.add_argument("--layer", choices=["L0", "L1", "L2", "L3"])
    p.add_argument("--category")
    p.add_argument("--min-trust", type=float, default=0.0)
    p.add_argument("--limit", "-n", type=int, default=50)

    # lint
    p = sub.add_parser("lint", help="健康檢查")

    # doctor
    p = sub.add_parser("doctor", help="環境診斷")

    # stats
    p = sub.add_parser("stats", help="統計")

    # install-embedding
    p = sub.add_parser("install-embedding", help="安裝嵌入模型")
    p.add_argument("--model", choices=["zh", "en", "mix"], default="mix")

    # import
    p = sub.add_parser("import", help="匯入長文件（自動分塊）")
    p.add_argument("file", help="檔案路徑 (.md, .txt)")
    p.add_argument("--title", "-t", help="文件標題（預設用檔名）")
    p.add_argument("--strategy", "-s", choices=["chapter", "semantic", "summary-guided", "sliding", "proposition"], default="chapter", help="分塊策略（預設: chapter，proposition 需要 Ollama）")
    p.add_argument("--layer", choices=["L0", "L1", "L2", "L3"], default="L3")
    p.add_argument("--category", default="general")
    p.add_argument("--tags", default="")
    p.add_argument("--trust", type=float, default=0.5)
    p.add_argument("--chunk-size", type=int, default=500, help="滑動視窗塊大小")
    p.add_argument("--overlap", type=int, default=100, help="滑動視窗重疊")
    p.add_argument("--no-embed", action="store_true", help="跳過嵌入生成")
    p.add_argument("--contextualize", action="store_true", help="Contextual Retrieval：用 Ollama 生成上下文摘要（Anthropic 2024）")
    p.add_argument("--ollama-model", default="qwen3:8b", help="Ollama 模型（用於 contextualize）")

    # config
    p = sub.add_parser("config", help="配置管理")
    p.add_argument("config_action", choices=["set", "get", "list"])
    p.add_argument("config_args", nargs="*")

    # map — Document Map read-only navigation + backfill
    p = sub.add_parser("map", help="Document Map 操作")
    map_sub = p.add_subparsers(dest="map_action", help="Document Map 子命令")

    mp = map_sub.add_parser("build", help="建立/回填 Document Map")
    mp.add_argument("knowledge_id", nargs="?", type=int, help="知識 ID；省略時回填全部")

    mp = map_sub.add_parser("show", help="顯示知識條目的章節地圖")
    mp.add_argument("knowledge_id", type=int, help="知識 ID")

    mp = map_sub.add_parser("read", help="讀取知識條目的指定行號範圍")
    mp.add_argument("knowledge_id", type=int, help="知識 ID")
    mp.add_argument("--lines", required=True, help="行號範圍，例如 1-40")

    mp = map_sub.add_parser("query", help="搜尋 Document Map claims")
    mp.add_argument("query", help="查詢文字")
    mp.add_argument("--limit", "-n", type=_positive_int, default=10)

    # skill — 跨 Agent 技能共享
    p = sub.add_parser("skill", help="技能市場（跨 Agent 共享）")
    skill_sub = p.add_subparsers(dest="skill_action", help="技能子命令")

    sp = skill_sub.add_parser("push", help="註冊技能到市場")
    sp.add_argument("--file", "-f", help="SKILL.md 路徑（預設讀 stdin）")
    sp.add_argument("--name", help="技能名稱（預設從 frontmatter 讀取）")
    sp.add_argument("--version", default="1.0.0", help="版本號")
    sp.add_argument("--agent", default="hermes-main", help="來源 Agent")
    sp.add_argument("--category", default="general", help="分類")
    sp.add_argument("--capabilities", default="", help="能力標籤（逗號分隔）")
    sp.add_argument("--dependencies", default="", help="依賴（逗號分隔）")
    sp.add_argument("--trust", type=float, default=0.5, help="信任分數")
    sp.add_argument("--description", default="", help="簡短描述")
    sp.add_argument("--force", action="store_true", help="同名技能時強制覆蓋")

    sp = skill_sub.add_parser("search", help="搜尋技能")
    sp.add_argument("query", nargs="?", default="", help="搜尋關鍵字")
    sp.add_argument("--capabilities", help="依能力過濾")
    sp.add_argument("--category", help="依分類過濾")
    sp.add_argument("--agent", help="依來源 Agent 過濾")
    sp.add_argument("--min-trust", type=float, default=0.0)
    sp.add_argument("--limit", "-n", type=int, default=20)

    sp = skill_sub.add_parser("pull", help="下載技能到本機")
    sp.add_argument("name", help="技能名稱")

    sp = skill_sub.add_parser("list", help="列出所有技能")
    sp.add_argument("--agent", help="依來源過濾")
    sp.add_argument("--category", help="依分類過濾")
    sp.add_argument("--min-trust", type=float, default=0.0)
    sp.add_argument("--limit", "-n", type=int, default=100)

    sp = skill_sub.add_parser("stats", help="技能市場統計")

    # graph
    p = sub.add_parser("graph", help="圖譜操作")
    graph_sub = p.add_subparsers(dest="graph_action", help="圖譜子命令")

    g = graph_sub.add_parser("build", help="自動推斷圖譜")
    g.add_argument("--clear", action="store_true", help="先清除舊的自動推斷")

    g = graph_sub.add_parser("show", help="顯示圖譜摘要")

    g = graph_sub.add_parser("export", help="匯出圖譜")
    g.add_argument("--format", "-f", choices=["mermaid", "dot"], default="mermaid")
    g.add_argument("--node-id", "-n", type=int, help="指定起點節點（預設全部）")
    g.add_argument("--depth", "-d", type=int, default=2, help="擴展深度")
    g.add_argument("--output", "-o", help="輸出檔案路徑")

    g = graph_sub.add_parser("link", help="手動建立關聯")
    g.add_argument("source_id", type=int, help="來源知識 ID")
    g.add_argument("target_id", type=int, help="目標知識 ID")
    g.add_argument("--relation", "-r", default="related_to", help="關係類型")
    g.add_argument("--weight", "-w", type=float, default=1.0, help="權重")

    g = graph_sub.add_parser("unlink", help="刪除關聯")
    g.add_argument("edge_id", type=int, help="邊 ID")

    g = graph_sub.add_parser("clear", help="清除自動推斷的邊")

    g = graph_sub.add_parser("expand", help="從節點擴展")
    g.add_argument("node_id", type=int, help="起始節點 ID")
    g.add_argument("--depth", "-d", type=int, default=2, help="擴展深度")


    # converge — self-questioning convergence check
    p = sub.add_parser("converge", help="收斂檢查 — 自問知識是否充足")
    p.add_argument("--apply", action="store_true", help="實際更新資料庫（預設為預覽模式）")
    p.add_argument("--limit", type=int, default=0, help="最多檢查幾條（0=全部）")
    p.add_argument("--min-trust", type=float, default=1.0, help="只檢查 trust 低於此值的條目")
    p.add_argument("--ollama", type=str, default="", help="使用 ollama 模型評分（如 qwen3）")
    p.add_argument("--api", type=str, default="", help="使用 OpenAI 相容 API 評分")
    p.add_argument("--api-key", type=str, default="", help="API key（如需要）")

    # cross-validate — asymmetric LLM verification
    p = sub.add_parser("cross-validate", help="跨模型不對稱驗證")
    p.add_argument("--apply", action="store_true", help="實際更新 DB（預設為預覽模式）")
    p.add_argument("--limit", type=int, default=0, help="最多驗證幾條（0=全部）")
    p.add_argument("--min-trust", type=float, default=0.8, help="只驗證 trust 低於此值的條目")
    p.add_argument("--local-only", action="store_true", help="只用本地模型（不用雲端）")
    p.add_argument("--local-model", type=str, default="qwen3-8b", help="本地模型名稱")
    p.add_argument("--cloud-model", type=str, default="glm-5.1", help="雲端模型名稱")

    # freshness — staleness tracking and review scheduling
    p = sub.add_parser("freshness", help="知識新鮮度追蹤與審查排程")
    p.add_argument("--apply", action="store_true", help="實際更新 DB（預設為預覽模式）")
    p.add_argument("--limit", type=int, default=0, help="最多處理幾條（0=全部）")
    p.add_argument("--stale-only", action="store_true", help="只顯示過期條目")

    # dedup — semantic duplicate detection and merge
    p = sub.add_parser("dedup", help="語意去重 — 檢測與合併重複知識")
    p.add_argument("--merge", action="store_true", help="實際合併（預設為預覽模式）")
    p.add_argument("--dry-run", action="store_true", help="預覽合併計劃（不修改資料庫）")
    p.add_argument("--threshold", type=float, default=0.85, help="相似度閾值（預設 0.85）")

    # search-qa — deterministic local search quality snapshots
    p = sub.add_parser("search-qa", help="搜尋品質 QA 評估與 before/after 比較")
    qa_sub = p.add_subparsers(dest="search_qa_action", help="Search QA 子命令")

    qp = qa_sub.add_parser("run", help="執行 Search QA Set 並輸出 snapshot JSON")
    qp.add_argument("--qa-file", required=True, help="Search QA Set JSON 路徑")
    qp.add_argument("--output", "-o", help="snapshot JSON 輸出路徑")
    qp.add_argument("--mode", choices=["auto", "keyword", "vector", "hybrid"], default="keyword")
    qp.add_argument("--limit", "-n", type=int, default=10)
    qp.add_argument("--db-path", help="SQLite DB 路徑（預設 project_dir/guardrails.db）")

    qp = qa_sub.add_parser("compare", help="比較兩個 Search QA snapshot JSON")
    qp.add_argument("--before", required=True, help="before snapshot JSON")
    qp.add_argument("--after", required=True, help="after snapshot JSON")
    qp.add_argument("--output", "-o", help="comparison JSON 輸出路徑")

    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "add": cmd_add,
        "compile": cmd_compile,
        "search": cmd_search,
        "list": cmd_list,
        "lint": cmd_lint,
        "doctor": cmd_doctor,
        "stats": cmd_stats,
        "install-embedding": cmd_install_embedding,
        "import": cmd_import,
        "config": cmd_config,
        "map": cmd_map,
        "graph": cmd_graph,
        "skill": cmd_skill,
        "converge": cmd_converge,
        "cross-validate": cmd_cross_validate,
        "freshness": cmd_freshness,
        "dedup": cmd_dedup,
        "search-qa": cmd_search_qa,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()