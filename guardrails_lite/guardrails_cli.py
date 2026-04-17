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
    )

    if not results:
        print("🔍 沒有找到匹配的知識")
    else:
        print(f"🔍 找到 {len(results)} 筆 ({results[0].get('_mode', 'unknown')} 模式):\n")
        for r in results:
            score = r.get("_score", 0)
            mode = r.get("_mode", "?")
            trust = r.get("trust", 0)
            layer = r.get("layer", "?")
            graph_dist = r.get("_graph_distance")
            graph_info = f", graph={graph_dist}" if graph_dist is not None else ""
            print(f"  [{layer}] {r['title']} (trust={trust}, score={score:.3f}, {mode}{graph_info})")
            # 顯示 AAAK 摘要
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


# ── CLI 入口 ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="guardrails",
        description="Guardrails Lite — 純本地下知識系統",
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

    args = parser.parse_args()

    cmd_map = {
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
        "graph": cmd_graph,
    }

    if args.command in cmd_map:
        cmd_map[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()