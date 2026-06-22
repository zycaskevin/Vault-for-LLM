"""
Vault-for-LLM — CLI 入口。

用法：
  vault init              # 初始化專案
  vault add "標題"         # 加入知識
  vault import novel.md   # 匯入長文件（自動分塊）
  vault import obsidian   # 從既有 Obsidian vault 同步 Markdown notes
  vault compile           # 編譯 raw/ → db + compiled/
  vault search "查詢"     # 搜尋知識
  vault export obsidian   # 匯出成 Obsidian vault Markdown notes
  vault list              # 列出知識
  vault candidates        # 列出候選記憶
  vault remove <id>       # 刪除知識（需要 --confirm）
  vault lint              # 健康檢查
  vault doctor            # 環境診斷
  vault stats             # 統計
  vault install-embedding # 安裝嵌入模型
  vault config set/get    # 配置管理
"""

import argparse
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path


# ── 專案偵測 ─────────────────────────────────────────────

def find_project_dir() -> Path:
    """往上找含有 vault.db 或 raw/ 的目錄。"""
    cwd = Path.cwd()
    for d in [cwd] + list(cwd.parents):
        if (d / "vault.db").exists() or (d / "raw").is_dir():
            return d
    return cwd


def _arg_value(args, name: str, default=None):
    """Read argparse/Namespace values without letting MagicMock invent attrs."""
    return vars(args).get(name, default)


def _extract_project_dir_arg(argv: list[str]) -> tuple[list[str], str | None]:
    """Extract --project-dir from anywhere in the CLI command.

    Most agents pass runtime-specific options after the subcommand, for example
    ``vault search "query" --project-dir /path``. argparse global options only
    work before the subcommand, so we normalize this option before parsing.
    """
    cleaned: list[str] = []
    project_dir: str | None = None
    i = 0
    while i < len(argv):
        item = argv[i]
        if item == "--project-dir":
            if i + 1 >= len(argv):
                print("error: --project-dir requires a value", file=sys.stderr)
                raise SystemExit(2)
            project_dir = argv[i + 1]
            i += 2
            continue
        if item.startswith("--project-dir="):
            project_dir = item.split("=", 1)[1]
            i += 1
            continue
        cleaned.append(item)
        i += 1
    return cleaned, project_dir


def _privacy_block_message(label: str, privacy: dict) -> str:
    findings = privacy.get("findings", [])
    kinds = ", ".join(
        sorted(
            {
                str(item.get("type", "secret"))
                for item in findings
                if item.get("severity") == "fail"
            }
        )
    )
    return f"privacy gate blocked {label}: {kinds or 'secret-like content'}"


def _enforce_cli_privacy(content: str, *, allow_private: bool, label: str) -> None:
    if allow_private:
        return
    from vault.privacy import scan_privacy

    privacy = scan_privacy(content)
    if privacy.get("status") != "fail":
        return
    print(f"❌ {_privacy_block_message(label, privacy)}", file=sys.stderr)
    print("   Use --allow-private only for explicit local/private vault ingestion.", file=sys.stderr)
    raise SystemExit(2)


# ── 子命令 ──────────────────────────────────────────────

def cmd_init(args):
    """初始化 Vault-for-LLM 專案。"""
    project_dir = Path(args.project_dir or ".")
    dirs = ["raw", "compiled", "L0-identity", "L1-core-facts", "L2-context", "L3-knowledge"]

    for d in dirs:
        (project_dir / d).mkdir(parents=True, exist_ok=True)
        print(f"  ✅ {d}/")

    # 初始化資料庫
    from vault.db import VaultDB
    db_path = project_dir / "vault.db"
    with VaultDB(str(db_path)) as db:
        db.set_config("embedding_provider", "auto")
        db.set_config("embedding_model", "mix")
        db.set_config("embedding_dim", "384")

    # .gitignore 追加
    gitignore = project_dir / ".gitignore"
    gi_lines = []
    if gitignore.exists():
        gi_lines = gitignore.read_text().splitlines()

    additions = ["# Vault-for-LLM", "*.db", "__pycache__/", ".cache/"]
    for a in additions:
        if a not in gi_lines:
            gi_lines.append(a)
    gitignore.write_text("\n".join(gi_lines) + "\n", encoding="utf-8")

    print(f"\n✅ 專案初始化完成: {project_dir.resolve()}")
    print("下一步：")
    print("  1. 在 raw/ 放入 .md 知識檔案")
    print("  2. vault compile")
    print("  3. vault search \"查詢\"")


def cmd_add(args):
    """新增一筆知識。"""
    from vault.db import VaultDB, normalize_governance_metadata

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

    _enforce_cli_privacy(
        content,
        allow_private=getattr(args, "allow_private", False),
        label="vault add",
    )
    source = _arg_value(args, "source", "cli")
    if not isinstance(source, str) or not source:
        source = "cli"
    governance = normalize_governance_metadata(
        scope=_arg_value(args, "scope", "project"),
        sensitivity=_arg_value(args, "sensitivity", "low"),
        owner_agent=_arg_value(args, "owner_agent", ""),
        allowed_agents=_arg_value(args, "allowed_agents", ""),
        memory_type=_arg_value(args, "memory_type", "knowledge"),
        expires_at=_arg_value(args, "expires_at", ""),
    )

    with VaultDB(str(project_dir / "vault.db")) as db:
        kid = db.add_knowledge(
            title=args.title,
            content_raw=content,
            layer=args.layer or "L3",
            category=args.category or "general",
            tags=args.tags or "",
            trust=args.trust or 0.5,
            source=source,
            **governance,
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
        **governance,
    }
    raw_file.write_text(
        f"---\n{json.dumps(fm, ensure_ascii=False, indent=2)}\n---\n\n{content}\n",
        encoding="utf-8",
    )
    print(f"✅ 同步寫入 raw/{raw_file.name}")


def cmd_compile(args):
    """編譯 raw/ → db + compiled/。"""
    from vault.db import VaultDB
    from vault.compiler import VaultCompiler

    project_dir = find_project_dir()
    db_path = project_dir / "vault.db"

    # 載入嵌入（如果啟用）
    embed = None
    if not args.no_embed:
        try:
            from vault.embed import create_embedding_provider
            db_temp = VaultDB(str(db_path))
            db_temp.connect()
            provider_name = db_temp.get_config("embedding_provider", "auto")
            model_key = db_temp.get_config("embedding_model", "mix")
            db_temp.close()
            if provider_name != "none":
                embed = create_embedding_provider(provider=provider_name, model_key=model_key)
                print(f"[compile] 嵌入: {provider_name} ({model_key})")
        except Exception as e:
            print(f"[compile] ⚠️ 嵌入未啟用: {e}")

    db = VaultDB(str(db_path))
    db.connect()
    compiler = VaultCompiler(
        project_dir,
        db=db,
        embed_provider=embed,
        allow_private=getattr(args, "allow_private", False),
    )
    stats = compiler.compile(dry_run=args.dry_run)
    db.close()

    print("\n📊 編譯結果:")
    print(f"  檔案: {stats['total_files']}")
    print(f"  新增: {stats['new']}")
    print(f"  更新: {stats['updated']}")
    print(f"  跳過: {stats['skipped']}")
    print(f"  錯誤: {stats['errors']}")


def cmd_search(args):
    """搜尋知識。"""
    from vault.db import VaultDB
    from vault.search import VaultSearch
    from vault.embed import create_embedding_provider
    from vault.semantic import DeterministicHashEmbeddingProvider, SemanticProviderError

    project_dir = find_project_dir()
    db_path = project_dir / "vault.db"

    db = VaultDB(str(db_path))
    db.connect()

    # 嵌入
    embed = None
    if not args.keyword_only:
        try:
            provider_name = db.get_config("embedding_provider", "auto")
            model_key = db.get_config("embedding_model", "mix")
            if args.allow_hash:
                embed = DeterministicHashEmbeddingProvider(dim=args.hash_dim)
            elif provider_name == "hash-deterministic-v1":
                # Instantiate so semantic safety gates can fail closed explicitly.
                embed = DeterministicHashEmbeddingProvider(dim=args.hash_dim)
            elif provider_name != "none":
                embed = create_embedding_provider(provider=provider_name, model_key=model_key)
        except Exception:
            pass

    # 圖譜（如果需要擴展）
    graph = None
    if args.graph_expand > 0:
        try:
            from vault.graph import VaultGraph
            graph = VaultGraph(db)
        except Exception as e:
            print(f"[search] ⚠️ 圖譜未啟用: {e}")

    mode = "keyword" if args.keyword_only else args.mode
    search = VaultSearch(db, embed_provider=embed, graph=graph)

    try:
        results = search.search(
            args.query,
            mode=mode,
            limit=args.limit,
            min_trust=args.min_trust,
            layer=args.layer,
            category=args.category,
            graph_expand=args.graph_expand,
            use_rerank=not args.no_rerank,
            semantic_vector_kind=args.semantic_vector_kind,
            allow_hash=args.allow_hash,
            min_score=args.min_score,
            agent_id=getattr(args, "agent_id", ""),
            include_private=bool(getattr(args, "include_private", False)),
            max_sensitivity=getattr(args, "max_sensitivity", ""),
        )
    except SemanticProviderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        db.close()
        raise SystemExit(2) from exc

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
    from vault.db import VaultDB

    project_dir = find_project_dir()
    db = VaultDB(str(project_dir / "vault.db"))
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


def cmd_remove(args):
    """刪除知識條目。"""
    from vault.db import VaultDB

    if not args.confirm:
        print("Refusing to remove knowledge without --confirm.")
        print(f"Preview: vault list --limit 20 --project-dir {find_project_dir()}")
        print(f"Delete:  vault remove {args.knowledge_id} --confirm")
        raise SystemExit(2)

    project_dir = find_project_dir()
    db = VaultDB(str(project_dir / "vault.db"))
    db.connect()
    try:
        item = db.get_knowledge(args.knowledge_id)
        if not item:
            payload = {"removed": False, "id": args.knowledge_id, "reason": "not_found"}
            if args.json or args.pretty:
                _json_print(payload, pretty=args.pretty)
            else:
                print(f"Knowledge ID {args.knowledge_id} not found.")
            raise SystemExit(1)

        removed = db.delete_knowledge(args.knowledge_id)
        payload = {
            "removed": removed,
            "id": args.knowledge_id,
            "title": item.get("title", ""),
            "project_dir": str(project_dir),
        }
        if args.json or args.pretty:
            _json_print(payload, pretty=args.pretty)
        else:
            print(f"Removed knowledge ID {args.knowledge_id}: {item.get('title', '')}")
    finally:
        db.close()


def cmd_lint(args):
    """健康檢查。"""
    from vault.db import VaultDB

    project_dir = find_project_dir()
    db = VaultDB(str(project_dir / "vault.db"))
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
            from vault.embed import create_embedding_provider
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
    print("🏥 Vault-for-LLM 環境診斷\n")

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
        if importlib.util.find_spec("optimum.onnxruntime") is None:
            raise ImportError
        checks.append(("optimum[onnxruntime]", "✅", True))
    except ImportError:
        try:
            import optimum
            # optimum v2.x may not have __version__ (use importlib.metadata fallback)
            try:
                opt_ver = optimum.__version__
            except AttributeError:
                import importlib.metadata as _meta
                opt_ver = _meta.version("optimum")
            checks.append(("optimum[onnxruntime]", f"⚠️ optimum {opt_ver} 已裝，缺 onnxruntime", False))
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
    db_exists = (project_dir / "vault.db").exists()
    raw_exists = (project_dir / "raw").is_dir()
    checks.append(("專案", f"{'✅' if db_exists else '❌'} DB | {'✅' if raw_exists else '❌'} raw/", db_exists and raw_exists))

    # 嵌入模型快取
    cache_dir = Path.home() / ".cache" / "vault-mcp" / "models"
    if cache_dir.exists():
        models = [d.name for d in cache_dir.iterdir() if d.is_dir()]
        checks.append(("嵌入模型快取", f"✅ {len(models)} 模型", True))
    else:
        checks.append(("嵌入模型快取", "❌ 無 (vault install-embedding)", False))

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
    from vault.embed import MODELS, ONNXEmbeddingProvider

    print("📦 Vault-for-LLM 嵌入模型安裝\n")
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
    from vault.db import VaultDB
    project_dir = find_project_dir()
    db = VaultDB(str(project_dir / "vault.db"))
    db.connect()
    db.set_config("embedding_provider", "onnx")
    db.set_config("embedding_model", model_key)
    db.set_config("embedding_dim", str(info["dim"]))
    db.close()

    # 重建向量表（維度可能不同）
    print("重建向量索引...")
    db2 = VaultDB(str(project_dir / "vault.db"))
    db2.connect()
    db2._init_vec_table()
    db2.close()

    print("\n✅ 完成！語意搜尋已啟用")
    print("   試試: vault search \"查詢\"")


def cmd_stats(args):
    """顯示統計。"""
    from vault.db import VaultDB

    project_dir = find_project_dir()
    db_path = project_dir / "vault.db"

    if not db_path.exists():
        print("❌ 尚未初始化，先執行 vault init")
        return

    db = VaultDB(str(db_path))
    db.connect()
    stats = db.stats()

    print("📊 Vault-for-LLM 統計\n")
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
    from vault.db import VaultDB
    from vault.graph import VaultGraph

    project_dir = find_project_dir()
    db_path = project_dir / "vault.db"

    if not db_path.exists():
        print("❌ 尚未初始化，先執行 vault init")
        return

    db = VaultDB(str(db_path))
    db.connect()
    graph = VaultGraph(db)

    action = args.graph_action

    if action == "build":
        """自動推斷實體和關聯。"""
        print("🔄 掃描知識庫，推斷圖譜...")
        result = graph.infer_all()
        print("\n✅ 圖譜建構完成！")
        print(f"   掃描條目: {result['total_knowledge']}")
        print(f"   新增實體: {result['entities_created']}")
        print(f"   新增關聯: {result['edges_created']}")
        print("\n   試試: vault graph show")
        print("         vault graph export --format mermaid")
        print("         vault search '查詢' --graph-expand 1")

    elif action == "show":
        """顯示圖譜摘要。"""
        stats = graph.stats()
        print("🕸️ Vault-for-LLM 圖譜\n")
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
        print("✅ 已建立關聯:")
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
    """匯入長文件，或從 Obsidian vault 同步 Markdown notes。"""
    project_dir = find_project_dir()
    db_path = project_dir / "vault.db"

    if args.file == "obsidian":
        from vault.import_obsidian import sync_obsidian_vault

        if not getattr(args, "vault", None):
            print("❌ vault import obsidian 需要 --vault /path/to/ObsidianVault")
            raise SystemExit(2)

        try:
            result = sync_obsidian_vault(
                project_dir=project_dir,
                vault_dir=args.vault,
                category=args.category,
                tags=args.tags,
                layer=args.layer,
                trust=args.trust,
                raw_subdir=args.obsidian_raw_subdir,
                excludes=set(args.exclude or []),
                dry_run=args.dry_run,
                allow_private=getattr(args, "allow_private", False),
            )
        except Exception as e:
            print(f"❌ Obsidian 匯入失敗: {e}")
            raise SystemExit(2) from e

        print("📥 Obsidian 匯入結果:")
        print(f"  掃描: {result['scanned']}")
        print(f"  新增: {result['added']}")
        print(f"  更新: {result['updated']}")
        print(f"  跳過: {result['skipped']}")
        print(f"  忽略: {result['ignored']}")
        if result["errors"]:
            print(f"  錯誤: {len(result['errors'])}")
            for error in result["errors"][:5]:
                print(f"    - {error}")
            if not getattr(args, "allow_private", False):
                print("  提示: 若這是明確的本機私人 vault，可加 --allow-private。")
        else:
            print("  錯誤: 0")

        if args.dry_run:
            print("  模式: dry-run，未寫入 raw/，也不會 compile")
            return

        if args.compile:
            import argparse

            compile_args = argparse.Namespace(
                dry_run=False,
                no_embed=args.no_embed,
                allow_private=getattr(args, "allow_private", False),
            )
            cmd_compile(compile_args)
        else:
            print("下一步：執行 vault compile，或下次同步時加 --compile。")
        return

    from vault.db import VaultDB
    from vault.importer import import_document

    file_path = Path(args.file)

    if not file_path.exists():
        print(f"❌ 檔案不存在: {file_path}")
        return
    if not getattr(args, "allow_private", False):
        _enforce_cli_privacy(
            file_path.read_text(encoding="utf-8"),
            allow_private=False,
            label="vault import",
        )

    # 載入嵌入
    embed = None
    if not args.no_embed:
        try:
            from vault.embed import create_embedding_provider
            db_temp = VaultDB(str(db_path))
            db_temp.connect()
            provider_name = db_temp.get_config("embedding_provider", "auto")
            model_key = db_temp.get_config("embedding_model", "mix")
            db_temp.close()
            if provider_name != "none":
                embed = create_embedding_provider(provider=provider_name, model_key=model_key)
                print(f"[import] 嵌入: {provider_name} ({model_key})")
        except Exception as e:
            print(f"[import] ⚠️ 嵌入未啟用: {e}")

    db = VaultDB(str(db_path))
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
            allow_private=getattr(args, "allow_private", False),
        )

        print("\n✅ 匯入完成！")
        print(f"   分塊數: {len(ids)}")
        print(f"   策略: {strategy}")
        if args.contextualize:
            # 檢查是否真的有上下文（Ollama 可能沒跑）
            from vault.db import VaultDB
            db_check = VaultDB(str(db_path))
            db_check.connect()
            has_context = db_check.conn.execute(
                "SELECT COUNT(*) FROM knowledge WHERE content_aaak LIKE '%【%' LIMIT 1"
            ).fetchone()[0]
            db_check.close()
            if has_context > 0:
                print("   上下文增強: ✅ (Contextual Retrieval)")
            else:
                print("   上下文增強: ⚠️ 未啟用（Ollama 未連線，已降級）")
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
        print("用法: vault skill {push|search|pull|list|stats}")


def cmd_skill_push(args):
    """向本機技能登錄註冊一個技能。"""
    from vault.db import VaultDB

    project_dir = find_project_dir()
    db = VaultDB(str(project_dir / "vault.db"))
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
        agent_source=args.agent or "vault-cli",
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
                agent_source=args.agent or "vault-cli",
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
    """搜尋本機技能登錄。"""
    from vault.db import VaultDB

    project_dir = find_project_dir()
    db = VaultDB(str(project_dir / "vault.db"))
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
    """從本機技能登錄下載技能到本機 skills/。"""
    from vault.db import VaultDB
    from vault.compiler import safe_path_segment

    project_dir = find_project_dir()
    db = VaultDB(str(project_dir / "vault.db"))
    db.connect()

    skill = db.get_skill(args.name)
    if not skill:
        print(f"❌ 技能 '{args.name}' 不存在於本機技能登錄")
        db.close()
        return

    # 寫入 public-neutral local skill cache（預設 ~/.vault/skills/<name>/）
    skills_root = Path(os.environ.get("VAULT_SKILLS_DIR", Path.home() / ".vault" / "skills"))
    skill_dir_name = safe_path_segment(args.name, default="")
    if not skill_dir_name:
        print(f"❌ 技能名稱不可作為本機目錄: {args.name}")
        db.close()
        return
    skills_dir = skills_root / skill_dir_name
    try:
        skills_dir.resolve().relative_to(skills_root.resolve())
    except ValueError:
        print(f"❌ 技能名稱不可越界寫入: {args.name}")
        db.close()
        return
    skills_dir.mkdir(parents=True, exist_ok=True)

    skill_file = skills_dir / "SKILL.md"
    skill_file.write_text(skill["content_raw"], encoding="utf-8")
    print(f"✅ 技能 '{args.name}' v{skill['version']} → {skill_file}")

    db.close()


def cmd_skill_list(args):
    """列出本機技能登錄所有技能。"""
    from vault.db import VaultDB

    project_dir = find_project_dir()
    db = VaultDB(str(project_dir / "vault.db"))
    db.connect()

    results = db.list_skills(
        agent_source=args.agent,
        category=args.category,
        min_trust=args.min_trust or 0.0,
        limit=args.limit or 100,
    )

    if not results:
        print("📭 本機技能登錄是空的")
    else:
        print(f"🛠️  本機技能登錄: {len(results)} 個技能\n")
        for r in results:
            print(f"  [{r['agent_source']}] {r['name']} v{r['version']} "
                  f"(trust={r['trust']}, {r['category']})")
            if r.get("description"):
                print(f"      {r['description']}")
            print()

    db.close()


def cmd_skill_stats(args):
    """本機技能登錄統計。"""
    from vault.db import VaultDB

    project_dir = find_project_dir()
    db = VaultDB(str(project_dir / "vault.db"))
    db.connect()

    stats = db.stats()
    print("🛠️  本機技能登錄統計")
    print(f"   技能總數: {stats.get('skill_count', 0)}")
    print(f"   知識總數: {stats.get('knowledge_count', 0)}")
    print(f"   向量嵌入: {stats.get('embedding_count', 0)}")
    print(f"   知識圖譜: {stats.get('entity_count', 0)} 實體, {stats.get('edge_count', 0)} 邊")
    print(f"   平均新鮮度: {stats.get('avg_freshness', 0)}")
    print(f"   DB 大小: {stats.get('db_size_mb', 0)} MB")

    db.close()


def cmd_map(args):
    """Document Map 操作：build / show / read / query。"""
    from vault.db import VaultDB
    from vault.docmap import build_document_map_for_entry

    project_dir = find_project_dir()
    db_path = project_dir / "vault.db"
    action = args.map_action

    if action == "build":
        db = VaultDB(str(db_path))
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
                        f"Run: vault map build {args.knowledge_id}"
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

    print("用法: vault map {build|show|read|query}")


def cmd_remote(args):
    """Supabase remote read workflow: search / map / read."""
    from vault.mcp import (
        _vault_remote_map_show_payload,
        _vault_remote_read_range_payload,
        _vault_remote_search_payload,
    )

    action = args.remote_action
    if action == "search":
        payload = _vault_remote_search_payload(
            query=args.query or "",
            agent_id=args.agent_id or "",
            include_private=bool(args.include_private),
            max_sensitivity=args.max_sensitivity or "medium",
            limit=args.limit,
            compact=bool(args.compact),
        )
    elif action == "map":
        payload = _vault_remote_map_show_payload(
            args.knowledge_id,
            compact=bool(args.compact),
        )
    elif action == "read":
        line_start = 0
        line_end = 0
        if args.lines:
            try:
                line_start, line_end = _parse_map_line_range(args.lines)
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                raise SystemExit(2)
        payload = _vault_remote_read_range_payload(
            args.knowledge_id,
            node_uid=args.node_uid or "",
            line_start=line_start,
            line_end=line_end,
            max_lines=args.max_lines,
        )
    elif action == "smoke":
        search_payload = _vault_remote_search_payload(
            query=args.query or "",
            agent_id=args.agent_id or "",
            include_private=bool(args.include_private),
            max_sensitivity=args.max_sensitivity or "medium",
            limit=args.limit,
            compact=True,
        )
        payload = {
            "ok": not bool(search_payload.get("error")),
            "check": "vault_search_readable",
            "agent_id": args.agent_id or "",
            "query": args.query or "",
            "search": search_payload,
        }
        if not payload["ok"]:
            payload["next_action"] = search_payload.get("next_action") or {
                "message": "Set SUPABASE_URL and SUPABASE_ANON_KEY, apply docs/supabase_read_policy.sql, then retry."
            }
    else:
        print("用法: vault remote {search|map|read|smoke}")
        return

    if args.json or args.pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
        return

    if payload.get("error"):
        print(f"error: {payload['error']}: {payload.get('message', '')}", file=sys.stderr)
        if payload.get("next_action"):
            print(json.dumps({"next_action": payload["next_action"]}, ensure_ascii=False))
        raise SystemExit(2)

    if action == "search":
        print(f"remote search: {payload.get('count', 0)} result(s)")
        for item in payload.get("results", []):
            print(f"  #{item.get('id')} {item.get('title', '')}")
            summary = item.get("summary")
            if summary:
                print(f"    {summary}")
            next_action = item.get("next_action")
            if next_action:
                print(f"    next: {next_action.get('tool')} {json.dumps(next_action.get('arguments', {}), ensure_ascii=False)}")
        return

    if action == "smoke":
        if payload.get("ok"):
            count = payload.get("search", {}).get("count", 0)
            print(f"remote smoke: ok ({count} readable result(s))")
            return
        error = payload.get("search", {}).get("error", "unknown")
        message = payload.get("search", {}).get("message", "")
        print(f"remote smoke: failed ({error}) {message}", file=sys.stderr)
        raise SystemExit(2)

    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _connect_map_readonly(db_path: Path) -> sqlite3.Connection | None:
    """Open vault.db in SQLite read-only mode for map navigation commands."""
    if not db_path.exists():
        print(f"vault.db not found at {db_path}. Run vault init/compile first.")
        return None

    try:
        conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.OperationalError as exc:
        print(f"Unable to open vault.db read-only at {db_path}: {exc}")
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
    """Parse an inclusive START-END line range for `vault map read`."""
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
    from vault.db import VaultDB

    project_dir = find_project_dir()
    db = VaultDB(str(project_dir / "vault.db"))
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
        print("用法: vault config set <key> <value>")
        print("      vault config get <key>")
        print("      vault config list")

    db.close()


def cmd_converge(args):
    """收斂檢查 — 自問知識是否充足。"""
    from scripts.convergence_check import check_convergence

    db_path = str(find_project_dir() / "vault.db")
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

    db_path = str(find_project_dir() / "vault.db")
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

    db_path = str(find_project_dir() / "vault.db")
    check_freshness(
        db_path=db_path,
        apply=args.apply,
        limit=args.limit,
        stale_only=args.stale_only,
    )


def cmd_dedup(args):
    """語意去重 — 檢測與合併重複知識。"""
    from scripts.deduplicate_semantic import find_duplicates, merge_duplicates

    db_path = str(find_project_dir() / "vault.db")
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
    from vault.search_qa import (
        compare_search_qa_snapshots,
        evaluate_search_qa,
        format_search_qa_comparison,
        format_search_qa_snapshot,
        write_json,
    )

    action = args.search_qa_action
    if action == "run":
        db_path = Path(args.db_path) if args.db_path else find_project_dir() / "vault.db"
        embed_provider = None
        needs_provider = args.mode in {"semantic", "hybrid", "vector"} or (
            args.mode == "auto" and (
                getattr(args, "allow_hash", False) or _semantic_vectors_exist(db_path)
            )
        )
        if needs_provider:
            semantic_args = argparse.Namespace(
                db_path=str(db_path),
                allow_hash=getattr(args, "allow_hash", False),
                hash_dim=getattr(args, "hash_dim", 32),
            )
            embed_provider = _create_semantic_provider(
                semantic_args,
                cached=args.mode in {"auto", "semantic", "hybrid"},
            )
        snapshot = evaluate_search_qa(
            db_path=db_path,
            qa_file=args.qa_file,
            mode=args.mode,
            limit=args.limit,
            embed_provider=embed_provider,
            semantic_vector_kind=args.semantic_vector_kind,
            allow_hash=args.allow_hash,
            min_score=args.min_score,
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


def cmd_remember(args):
    """Create a memory candidate or promote it immediately if gates allow."""
    from vault.db import VaultDB
    from vault.memory import propose_memory

    project_dir = find_project_dir()
    content = args.content or ""
    if args.file:
        content = Path(args.file).read_text(encoding="utf-8")
    if not content:
        content = sys.stdin.read()
    try:
        with VaultDB(project_dir / "vault.db") as db:
            payload = propose_memory(
                db,
                title=args.title,
                content=content,
                reason=args.reason,
                mode=_arg_value(args, "mode", "candidate"),
                layer=_arg_value(args, "layer", "L3"),
                category=_arg_value(args, "category", "general"),
                tags=_arg_value(args, "tags", ""),
                trust=_arg_value(args, "trust", 0.5),
                source=_arg_value(args, "source", "cli"),
                source_ref=_arg_value(args, "source_ref", ""),
                scope=_arg_value(args, "scope", "project"),
                sensitivity=_arg_value(args, "sensitivity", "low"),
                owner_agent=_arg_value(args, "owner_agent", ""),
                allowed_agents=_arg_value(args, "allowed_agents", ""),
                memory_type=_arg_value(args, "memory_type", "knowledge"),
                expires_at=_arg_value(args, "expires_at", ""),
            )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    _json_print(payload, pretty=args.pretty)


def cmd_promote(args):
    """Promote a memory candidate into raw/ plus active SQLite knowledge."""
    from vault.db import VaultDB
    from vault.memory import promote_candidate

    project_dir = find_project_dir()
    try:
        with VaultDB(project_dir / "vault.db") as db:
            payload = promote_candidate(
                db,
                args.candidate_id,
                confirm=args.confirm,
                project_dir=project_dir,
                compile=not args.no_compile,
                build_map=not args.no_build_map,
            )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    _json_print(payload, pretty=args.pretty)


def _format_memory_candidate(row: dict, *, include_content: bool = False, include_gates: bool = False) -> dict:
    item = {
        "id": row.get("id"),
        "title": row.get("title"),
        "status": row.get("status"),
        "layer": row.get("layer"),
        "category": row.get("category"),
        "tags": row.get("tags"),
        "trust": row.get("trust"),
        "scope": row.get("scope"),
        "sensitivity": row.get("sensitivity"),
        "owner_agent": row.get("owner_agent"),
        "allowed_agents": row.get("allowed_agents"),
        "memory_type": row.get("memory_type"),
        "expires_at": row.get("expires_at"),
        "source": row.get("source"),
        "source_ref": row.get("source_ref"),
        "reason": row.get("reason"),
        "privacy_status": row.get("privacy_status"),
        "duplicate_status": row.get("duplicate_status"),
        "quality_status": row.get("quality_status"),
        "promoted_knowledge_id": row.get("promoted_knowledge_id"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }
    content = row.get("content") or ""
    item["content_length"] = len(content)
    if include_content:
        item["content"] = content
    elif content:
        item["content_preview"] = " ".join(content.split())[:180]
    if include_gates:
        raw_gates = row.get("gate_payload_json") or "{}"
        try:
            item["gates"] = json.loads(raw_gates)
        except json.JSONDecodeError:
            item["gates"] = {"raw": raw_gates}
    return item


def cmd_candidates(args):
    """List memory candidates without reading the SQLite database by hand."""
    from vault.db import VaultDB

    project_dir = find_project_dir()
    status = None if args.all else args.status
    try:
        with VaultDB(project_dir / "vault.db") as db:
            rows = db.list_memory_candidates(status=status, limit=args.limit)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    payload = {
        "count": len(rows),
        "status": status or "all",
        "candidates": [
            _format_memory_candidate(
                row,
                include_content=args.include_content,
                include_gates=args.include_gates,
            )
            for row in rows
        ],
    }
    _json_print(payload, pretty=args.pretty)


def cmd_dream(args):
    """Run a deterministic report-first dream curation pass."""
    from vault.dream import run_dream

    project_dir = find_project_dir()
    try:
        payload = run_dream(
            project_dir,
            mode=args.mode,
            checks=args.checks,
            limit=args.limit,
            write_report=args.write_report,
            backup=not args.no_backup,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    _json_print(payload, pretty=args.pretty)


def _json_print(payload: dict, *, pretty: bool = False) -> None:
    indent = 2 if pretty else None
    print(json.dumps(payload, ensure_ascii=False, indent=indent, sort_keys=True))


def cmd_db(args):
    """SQLite schema migration/status/backup workflows."""
    from vault.db import VaultDB
    from vault.db_backup import BackupError, backup_database, restore_database, verify_backup

    action = args.db_action
    if action not in {"status", "migrate", "backup", "verify-backup", "restore"}:
        print(
            "error: db requires action: status, migrate, backup, verify-backup, or restore",
            file=sys.stderr,
        )
        raise SystemExit(2)

    try:
        if action == "verify-backup":
            payload = verify_backup(args.backup_path)
            _json_print(payload, pretty=args.pretty)
            return

        db_path = Path(args.db_path) if args.db_path else find_project_dir() / "vault.db"
        if action == "backup":
            payload = backup_database(db_path, args.output, verify=args.verify)
        elif action == "restore":
            payload = restore_database(args.backup_path, db_path, force=args.force)
        else:
            with VaultDB(db_path) as db:
                payload = db.schema_status() if action == "status" else db.migrate()
    except BackupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    _json_print(payload, pretty=args.pretty)


def _semantic_vectors_exist(db_path: Path) -> bool:
    try:
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute("SELECT 1 FROM semantic_vectors LIMIT 1").fetchone()
            return row is not None
    except sqlite3.Error:
        return False


def _semantic_stats_payload(stats, provider) -> dict:
    return {
        "provider_id": provider.provider_id,
        "is_semantic": bool(provider.is_semantic),
        "dimension": int(provider.dim),
        "knowledge_rows": int(stats.knowledge_rows),
        "node_vectors": int(stats.node_vectors),
        "claim_vectors": int(stats.claim_vectors),
    }


def _persistent_cache_payload(provider) -> dict:
    return {
        "memory_rows": int(getattr(provider, "cache_size", 0)),
        "persistent_hits": int(getattr(provider, "persistent_hits", 0)),
        "persistent_misses": int(getattr(provider, "persistent_misses", 0)),
        "writes": int(getattr(provider, "writes", 0)),
    }


def _close_provider(provider) -> None:
    close = getattr(provider, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def _load_unique_qa_queries(qa_file: str | Path) -> list[str]:
    from vault.search_qa import load_search_qa_set

    qa = load_search_qa_set(qa_file)
    seen: set[str] = set()
    queries: list[str] = []
    for case in qa["cases"]:
        query = str(case["query"])
        if query not in seen:
            seen.add(query)
            queries.append(query)
    return queries


def _create_semantic_provider(args, *, cached: bool = False):
    from vault.db import VaultDB
    from vault.embed import create_embedding_provider
    from vault.semantic import (
        CachedEmbeddingProvider,
        DeterministicHashEmbeddingProvider,
        validate_embedding_provider,
    )

    if args.allow_hash:
        provider = DeterministicHashEmbeddingProvider(dim=args.hash_dim)
        return CachedEmbeddingProvider(provider) if cached else provider

    db_path = Path(args.db_path) if args.db_path else find_project_dir() / "vault.db"
    with VaultDB(db_path) as db:
        provider_name = db.get_config("embedding_provider", "auto")
        model_key = db.get_config("embedding_model", "mix")
    provider = create_embedding_provider(provider=provider_name, model_key=model_key)
    validate_embedding_provider(provider, require_semantic=True, allow_hash=False)
    return CachedEmbeddingProvider(provider) if cached else provider


def _create_persistent_semantic_provider(args, db):
    from vault.semantic import PersistentCachedEmbeddingProvider

    provider = _create_semantic_provider(args, cached=False)
    return PersistentCachedEmbeddingProvider(provider, db)


def cmd_semantic(args):
    """Operator-facing semantic index workflows."""
    from vault.db import VaultDB
    from vault.search_qa import evaluate_search_qa, write_json
    from vault.semantic import embedding_cache_stats, prune_embedding_cache, rebuild_semantic_index
    from vault.semantic_lifecycle import run_semantic_daemon, run_semantic_startup

    action = args.semantic_action
    if action not in {"rebuild", "warm", "smoke", "cache-stats", "cache-prune", "startup", "daemon"}:
        print(
            "error: semantic requires action: rebuild, warm, smoke, cache-stats, cache-prune, startup, or daemon",
            file=sys.stderr,
        )
        raise SystemExit(2)

    db_path = Path(args.db_path) if args.db_path else find_project_dir() / "vault.db"

    try:
        if action in {"startup", "daemon"}:
            lifecycle_kwargs = {
                "db_path": db_path,
                "qa_file": args.qa_file,
                "allow_hash": args.allow_hash,
                "hash_dim": args.hash_dim,
                "persist_cache": not args.no_persist_cache,
                "rebuild": args.rebuild,
                "smoke": args.smoke,
                "mode": args.mode,
                "limit": args.limit,
                "semantic_vector_kind": args.semantic_vector_kind,
                "older_than_days": args.older_than_days,
                "max_rows": args.max_rows,
            }
            if action == "startup":
                payload = run_semantic_startup(**lifecycle_kwargs)
            else:
                payload = run_semantic_daemon(
                    repeat=args.repeat,
                    interval=args.interval,
                    **lifecycle_kwargs,
                )
            if args.output:
                write_json(args.output, payload)
            _json_print(payload, pretty=args.pretty)
            return

        if action == "cache-stats":
            with VaultDB(db_path) as db:
                stats = embedding_cache_stats(
                    db,
                    provider_id=args.provider_id,
                    dimension=args.dimension,
                )
            _json_print({"action": "cache-stats", **stats}, pretty=args.pretty)
            return

        if action == "cache-prune":
            with VaultDB(db_path) as db:
                deleted = prune_embedding_cache(
                    db,
                    provider_id=args.provider_id,
                    dimension=args.dimension,
                    older_than_days=args.older_than_days,
                    max_rows=args.max_rows,
                )
            _json_print({"action": "cache-prune", "deleted_rows": deleted}, pretty=args.pretty)
            return

        if action == "rebuild":
            if args.persist_cache:
                with VaultDB(db_path) as db:
                    provider = _create_persistent_semantic_provider(args, db)
                    try:
                        stats = rebuild_semantic_index(
                            db,
                            provider,
                            knowledge_id=args.knowledge_id,
                            require_semantic=not args.allow_hash,
                            allow_hash=args.allow_hash,
                        )
                        payload = {"action": "rebuild", **_semantic_stats_payload(stats, provider)}
                        payload["persistent_cache"] = _persistent_cache_payload(provider)
                    finally:
                        _close_provider(provider)
            else:
                provider = _create_semantic_provider(args, cached=False)
                try:
                    with VaultDB(db_path) as db:
                        stats = rebuild_semantic_index(
                            db,
                            provider,
                            knowledge_id=args.knowledge_id,
                            require_semantic=not args.allow_hash,
                            allow_hash=args.allow_hash,
                        )
                    payload = {"action": "rebuild", **_semantic_stats_payload(stats, provider)}
                finally:
                    _close_provider(provider)
            _json_print(payload, pretty=args.pretty)
            return

        if action == "warm":
            queries = _load_unique_qa_queries(args.qa_file)
            if args.persist_cache:
                with VaultDB(db_path) as db:
                    provider = _create_persistent_semantic_provider(args, db)
                    try:
                        if queries:
                            provider.encode(queries)
                        payload = {
                            "action": "warm",
                            "provider_id": provider.provider_id,
                            "is_semantic": bool(provider.is_semantic),
                            "dimension": int(provider.dim),
                            "warmed_queries": len(queries),
                            "cache_size": provider.cache_size,
                            "persistent_cache": _persistent_cache_payload(provider),
                        }
                    finally:
                        _close_provider(provider)
            else:
                provider = _create_semantic_provider(args, cached=True)
                try:
                    if queries:
                        provider.encode(queries)
                    payload = {
                        "action": "warm",
                        "provider_id": provider.provider_id,
                        "is_semantic": bool(provider.is_semantic),
                        "dimension": int(provider.dim),
                        "warmed_queries": len(queries),
                        "cache_size": provider.cache_size,
                    }
                finally:
                    _close_provider(provider)
            _json_print(payload, pretty=args.pretty)
            return

        queries = _load_unique_qa_queries(args.qa_file)
        if args.persist_cache:
            with VaultDB(db_path) as db:
                provider = _create_persistent_semantic_provider(args, db)
                try:
                    stats = rebuild_semantic_index(
                        db,
                        provider,
                        knowledge_id=args.knowledge_id,
                        require_semantic=not args.allow_hash,
                        allow_hash=args.allow_hash,
                    )
                    if queries:
                        provider.encode(queries)
                    cache_payload = _persistent_cache_payload(provider)
                finally:
                    _close_provider(provider)
        else:
            provider = _create_semantic_provider(args, cached=True)
            try:
                with VaultDB(db_path) as db:
                    stats = rebuild_semantic_index(
                        db,
                        provider,
                        knowledge_id=args.knowledge_id,
                        require_semantic=not args.allow_hash,
                        allow_hash=args.allow_hash,
                    )
                if queries:
                    provider.encode(queries)
                cache_payload = None
            finally:
                _close_provider(provider)
        qa_snapshot = evaluate_search_qa(
            db_path=db_path,
            qa_file=args.qa_file,
            mode=args.mode,
            limit=args.limit,
            embed_provider=provider,
            semantic_vector_kind=args.semantic_vector_kind,
            allow_hash=args.allow_hash,
        )
        payload = {
            "action": "smoke",
            "provider_id": provider.provider_id,
            "is_semantic": bool(provider.is_semantic),
            "dimension": int(provider.dim),
            "rebuild": {
                "knowledge_rows": int(stats.knowledge_rows),
                "node_vectors": int(stats.node_vectors),
                "claim_vectors": int(stats.claim_vectors),
            },
            "warmed_queries": len(queries),
            "cache_size": provider.cache_size,
            "qa": {"aggregate": qa_snapshot["aggregate"]},
            "output_written": bool(args.output),
        }
        if cache_payload is not None:
            payload["persistent_cache"] = cache_payload
        if args.output:
            write_json(args.output, payload)
        _json_print(payload, pretty=args.pretty)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def cmd_export(args):
    """One-way export commands for human-readable knowledge browsing."""
    if args.export_target != "obsidian":
        print("error: export requires target: obsidian", file=sys.stderr)
        raise SystemExit(2)

    from vault.export_obsidian import export_obsidian_vault

    try:
        result = export_obsidian_vault(
            project_dir=find_project_dir(),
            vault_dir=args.vault,
            category=args.category,
            tag=args.tag,
            layer=args.layer,
            limit=args.limit,
            min_trust=args.min_trust,
            source=args.source,
            dry_run=args.dry_run,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(
        "Obsidian export: "
        f"matched={result['matched']} written={result['written']} "
        f"dry_run={result['dry_run']} vault={result['vault_dir']}"
    )
    for path in result["paths"][:10]:
        print(f"  {path}")
    if len(result["paths"]) > 10:
        print(f"  ... {len(result['paths']) - 10} more")


def cmd_setup_agent(args):
    """Interactive/non-interactive agent setup wizard."""
    from vault.agent_setup import (
        AgentSetupConfig,
        default_stable_venv_path,
        default_project_dir,
        interactive_setup,
        normalize_features,
        run_agent_setup,
    )

    if getattr(args, "non_interactive", False):
        scope = args.scope or "private"
        project_dir = Path(args.agent_project_dir or default_project_dir(scope, agent=args.agent))
        config = AgentSetupConfig(
            project_dir=project_dir,
            scope=scope,
            agent=args.agent,
            features=normalize_features(args.features),
            language=args.language,
            tool_profile=args.tool_profile,
            install_optional_deps=bool(args.install_optional_deps),
            install_embedding_model=args.install_embedding_model,
            obsidian_vault=Path(args.obsidian_vault).expanduser() if args.obsidian_vault else None,
            import_obsidian=bool(args.import_obsidian),
            sync_targets=args.obsidian_sync,
            sync_interval_minutes=args.sync_interval_minutes,
            supabase_sync_targets=args.supabase_sync,
            supabase_setup_mode=args.supabase_setup or "simple",
            supabase_sync_interval_minutes=args.supabase_sync_interval_minutes,
            remote_reader_targets=args.remote_reader,
            remote_reader_query=args.remote_reader_query,
            agent_roster=args.agent_roster,
            validation_pack_targets=args.validation_pack,
            template_dir=Path(args.template_dir).expanduser() if args.template_dir else None,
            allow_private=bool(args.allow_private),
            stable_venv_path=(
                Path(args.stable_venv).expanduser()
                if args.stable_venv
                else (default_stable_venv_path() if args.write_stable_venv_script else None)
            ),
        )
    else:
        setup_values = {
            "agent": args.agent,
            "scope": args.scope,
            "project_dir": args.agent_project_dir,
            "features": args.features,
            "language": args.language,
            "tool_profile": args.tool_profile,
            "install_optional_deps": args.install_optional_deps,
            "install_embedding_model": args.install_embedding_model,
            "obsidian_vault": args.obsidian_vault,
            "supabase_setup_mode": args.supabase_setup,
            "remote_reader_query": args.remote_reader_query,
            "agent_roster": args.agent_roster,
            "sync_interval_minutes": args.sync_interval_minutes,
            "supabase_sync_interval_minutes": args.supabase_sync_interval_minutes,
            "template_dir": args.template_dir,
            "allow_private": args.allow_private,
            "stable_venv_path": args.stable_venv,
            "write_stable_venv_script": args.write_stable_venv_script,
        }
        if args.import_obsidian:
            setup_values["import_obsidian"] = True
        if args.obsidian_sync != "none":
            setup_values["sync_targets"] = args.obsidian_sync
        if args.supabase_sync != "none":
            setup_values["supabase_sync_targets"] = args.supabase_sync
        if args.remote_reader != "none":
            setup_values["remote_reader_targets"] = args.remote_reader
        if args.validation_pack != "none":
            setup_values["validation_pack_targets"] = args.validation_pack
        config = interactive_setup(setup_values)

    payload = run_agent_setup(config)
    if args.pretty or args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print("Agent setup complete")
    print(f"  project_dir: {payload['project_dir']}")
    print(f"  db_path: {payload['db_path']}")
    print(f"  features: {', '.join(payload['features'])}")
    print(f"  language: {payload['language']}")
    if payload.get("obsidian"):
        obsidian = payload["obsidian"]
        dry = obsidian.get("dry_run") or {}
        imported = obsidian.get("import") or {}
        print(f"  obsidian_vault: {obsidian.get('vault')}")
        if dry:
            print(
                "  obsidian_dry_run: "
                f"scanned={dry.get('scanned')} added={dry.get('added')} updated={dry.get('updated')}"
            )
        if imported:
            print(
                "  obsidian_import: "
                f"added={imported.get('added')} updated={imported.get('updated')} skipped={imported.get('skipped')}"
            )
    if payload.get("sync_templates"):
        print("  sync_templates:")
        for name, path in payload["sync_templates"].items():
            print(f"    {name}: {path}")
    if payload.get("supabase_setup"):
        print("  supabase_setup:")
        for name, path in payload["supabase_setup"].items():
            print(f"    {name}: {path}")
    if payload.get("supabase_sync_templates"):
        print("  supabase_sync_templates:")
        for name, path in payload["supabase_sync_templates"].items():
            print(f"    {name}: {path}")
    if payload.get("remote_reader_templates"):
        print("  remote_reader_templates:")
        for name, path in payload["remote_reader_templates"].items():
            print(f"    {name}: {path}")
    if payload.get("agent_roster"):
        print("  agent_roster:")
        for name, path in payload["agent_roster"].items():
            if name == "env":
                continue
            print(f"    {name}: {path}")
    if payload.get("live_validation_pack"):
        print("  live_validation_pack:")
        for name, path in payload["live_validation_pack"].items():
            print(f"    {name}: {path}")
    if payload.get("memory_agents"):
        print("  memory_agents:")
        for name, path in payload["memory_agents"].items():
            print(f"    {name}: {path}")
    if payload.get("stable_venv"):
        print("  stable_venv:")
        for name, path in payload["stable_venv"].items():
            print(f"    {name}: {path}")
    print("Next steps:")
    for step in payload["next_steps"]:
        print(f"  {step}")

# ── CLI 入口 ─────────────────────────────────────────────

def _add_governance_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scope", choices=["private", "project", "shared", "public"], default="project", help="記憶範圍：private/project/shared/public")
    parser.add_argument("--sensitivity", choices=["low", "medium", "high", "restricted"], default="low", help="敏感度：low/medium/high/restricted")
    parser.add_argument("--owner-agent", default="", help="擁有者 Agent，例如 profile-agent、work-agent、codex")
    parser.add_argument("--allowed-agents", default="", help="可讀 Agent 清單；可用 JSON array 或逗號分隔")
    parser.add_argument("--memory-type", default="knowledge", help="記憶類型，例如 knowledge/profile/dream/care_summary/decision")
    parser.add_argument("--expires-at", default="", help="可選過期時間，ISO-8601 字串")


def main(argv: list[str] | None = None):
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    normalized_argv, explicit_project_dir = _extract_project_dir_arg(raw_argv)

    parser = argparse.ArgumentParser(
        prog="vault",
        description="Vault-for-LLM — local-first knowledge vault for LLM agents",
        epilog="Global agent option: --project-dir PATH may be passed before or after the subcommand.",
    )
    from vault import __version__

    parser.add_argument("--version", action="version", version=f"vault-for-llm {__version__}")
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
    p.add_argument("--source", default="cli", help="來源標籤或檔案路徑")
    p.add_argument("--allow-private", action="store_true", help="允許含秘密模式的內容直接寫入本機 vault")
    _add_governance_args(p)

    # remember/promote — safe memory curator workflow
    p = sub.add_parser("remember", help="提出記憶候選（預設不寫入 active knowledge）")
    p.add_argument("title", help="記憶標題")
    p.add_argument("--content", "-c", default="", help="記憶內容；省略時讀 stdin")
    p.add_argument("--file", "-f", help="從檔案讀取記憶內容")
    p.add_argument("--reason", required=True, help="為什麼值得記住")
    p.add_argument("--mode", choices=["candidate", "promote_if_safe"], default="candidate")
    p.add_argument("--layer", choices=["L0", "L1", "L2", "L3"], default="L3")
    p.add_argument("--category", default="general")
    p.add_argument("--tags", default="")
    p.add_argument("--trust", type=float, default=0.5)
    p.add_argument("--source", default="cli")
    p.add_argument("--source-ref", default="")
    _add_governance_args(p)
    p.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    p = sub.add_parser("promote", help="將記憶候選提升為 active knowledge")
    p.add_argument("candidate_id", help="memory candidate id")
    p.add_argument("--confirm", action="store_true", help="必要：確認提升候選")
    p.add_argument("--no-compile", action="store_true", help="跳過 raw/ 編譯，直接寫 active DB")
    p.add_argument("--no-build-map", action="store_true", help="搭配 --no-compile 時跳過 Document Map 建置")
    p.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    p = sub.add_parser("candidates", help="列出候選記憶（預設只列待審候選）")
    p.add_argument("--status", default="candidate", help="候選狀態，例如 candidate/promoted/rejected")
    p.add_argument("--all", action="store_true", help="列出所有狀態")
    p.add_argument("--limit", "-n", type=int, default=50)
    p.add_argument("--include-content", action="store_true", help="包含完整候選內容")
    p.add_argument("--include-gates", action="store_true", help="包含完整 gate payload")
    p.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    # compile
    p = sub.add_parser("compile", help="編譯 raw/ → db + compiled/")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-embed", action="store_true", help="跳過嵌入生成")
    p.add_argument("--allow-private", action="store_true", help="允許含秘密模式的 raw/ 檔案進入編譯")

    # search — 加入 --graph-expand
    p = sub.add_parser("search", help="搜尋知識")
    p.add_argument("query", help="搜尋查詢")
    p.add_argument("--mode", choices=["auto", "keyword", "vector", "semantic", "hybrid"], default="auto")
    p.add_argument("--keyword-only", "-k", action="store_true")
    p.add_argument("--limit", "-n", type=int, default=10)
    p.add_argument("--min-trust", type=float, default=0.0)
    p.add_argument("--min-score", type=float, default=None,
                   help="minimum keyword match score before returning weak/no-result matches")
    p.add_argument("--layer", choices=["L0", "L1", "L2", "L3"])
    p.add_argument("--category")
    p.add_argument("--semantic-vector-kind", choices=["claim", "node"], default="claim",
                   help="stored semantic_vectors kind for --mode semantic/hybrid")
    p.add_argument("--allow-hash", action="store_true",
                   help="explicitly allow deterministic hash provider for tests/dev")
    p.add_argument("--hash-dim", type=int, default=32,
                   help="hash provider dimension when --allow-hash or hash config is used")
    p.add_argument("--graph-expand", type=int, default=0,
                   help="圖譜擴展跳數（0=不擴展，1=1跳，2=2跳）")
    p.add_argument("--no-rerank", action="store_true",
                   help="停用 reranker 重排序")
    p.add_argument("--agent-id", default="", help="可選 Agent 身份；提供後套用治理 metadata 讀取過濾")
    p.add_argument("--include-private", action="store_true", help="搭配 --agent-id 允許讀取 owner/allow-list 授權的 private 記憶")
    p.add_argument("--max-sensitivity", choices=["", "low", "medium", "high", "restricted"], default="", help="最高可讀敏感度")

    # list
    p = sub.add_parser("list", help="列出知識")
    p.add_argument("--layer", choices=["L0", "L1", "L2", "L3"])
    p.add_argument("--category")
    p.add_argument("--min-trust", type=float, default=0.0)
    p.add_argument("--limit", "-n", type=int, default=50)

    def add_remove_args(ap):
        ap.add_argument("knowledge_id", type=int, help="要刪除的 knowledge ID")
        ap.add_argument("--confirm", action="store_true", help="必要：確認刪除")
        ap.add_argument("--json", action="store_true", help="輸出 JSON")
        ap.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    p = sub.add_parser("remove", help="刪除知識條目（需要 --confirm）")
    add_remove_args(p)
    p = sub.add_parser("delete", help="remove 的別名")
    add_remove_args(p)

    # lint
    p = sub.add_parser("lint", help="健康檢查")

    # doctor
    p = sub.add_parser("doctor", help="環境診斷")

    # stats
    p = sub.add_parser("stats", help="統計")

    # install-embedding
    p = sub.add_parser("install-embedding", help="安裝嵌入模型")
    p.add_argument("--model", choices=["zh", "en", "mix"], default="mix")

    def add_agent_setup_args(ap):
        ap.add_argument("--agent", default="generic", help="Agent/runtime 名稱，例如 hermes/openclaw/codex/n8n")
        ap.add_argument("--scope", choices=["shared", "private", "domain", "temporary"], help="Vault 資料庫範圍")
        ap.add_argument("--agent-project-dir", "--project", dest="agent_project_dir",
                        help="要初始化/使用的 Vault project directory")
        ap.add_argument("--features", default=None,
                        help="可選功能 CSV，例如 core,mcp,obsidian_import,semantic,supabase,headroom,memory_agents")
        ap.add_argument("--language", choices=["en", "zh-Hant", "zh-CN"], default=None,
                        help="互動式安裝與產生文件的語言；非互動模式預設 en")
        ap.add_argument("--tool-profile", choices=["core", "review", "remote", "maintenance", "full"],
                        default="core", help="建議的 MCP tool profile")
        ap.add_argument("--install-optional-deps", action="store_true",
                        help="立即安裝已選功能需要的 Python optional dependencies")
        ap.add_argument("--install-embedding-model", choices=["zh", "en", "mix"],
                        help="semantic feature 啟用時，下載並設定本地 ONNX embedding model")
        ap.add_argument("--obsidian-vault", help="既有 Obsidian vault 路徑；提供後會先 dry-run")
        ap.add_argument("--import-obsidian", action="store_true",
                        help="dry-run 後執行第一次 Obsidian 匯入並 compile")
        ap.add_argument("--obsidian-sync", choices=["none", "cron", "launchagent", "n8n", "all"],
                        default="none", help="產生後續自動同步模板")
        ap.add_argument("--sync-interval-minutes", type=int, default=15,
                        help="同步模板排程間隔分鐘數")
        ap.add_argument("--supabase-sync", choices=["none", "cron", "launchagent", "n8n", "all"],
                        default="none", help="產生每日 Supabase sync 模板")
        ap.add_argument("--supabase-setup", choices=["none", "simple", "advanced"],
                        default=None, help="產生 Supabase 連線導覽文件；非互動模式預設 simple")
        ap.add_argument("--supabase-sync-interval-minutes", type=int, default=1440,
                        help="Supabase sync LaunchAgent/n8n 排程間隔分鐘數（預設每日）")
        ap.add_argument("--remote-reader", choices=["none", "shell", "n8n", "coze", "all"],
                        default="none", help="產生 Supabase remote reader 範本給 shell/n8n/Coze")
        ap.add_argument("--remote-reader-query", default="deployment SOP",
                        help="remote reader smoke/template 使用的示範查詢")
        ap.add_argument("--agent-roster",
                        help="產生多 Agent roster/access matrix，例如 profile-agent:profile,work-agent:work,remote-agent:remote")
        ap.add_argument("--validation-pack", choices=["none", "remote", "n8n", "coze", "all"],
                        default="none", help="產生 Supabase/n8n/Coze live validation pack")
        ap.add_argument("--stable-venv",
                        help="產生穩定 Python virtualenv bootstrap 腳本，建議 ~/.hermes/venvs/vault-for-llm")
        ap.add_argument("--write-stable-venv-script", action="store_true",
                        help="用預設穩定 venv 路徑產生 setup-stable-venv.sh")
        ap.add_argument("--template-dir", help="同步模板輸出目錄；預設 project/agent-install")
        ap.add_argument("--allow-private", action="store_true",
                        help="允許 Obsidian 匯入含 secret-like pattern 的本機私人資料")
        ap.add_argument("--non-interactive", action="store_true", help="不要詢問，使用參數/defaults")
        ap.add_argument("--json", action="store_true", help="輸出 JSON")
        ap.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    # setup-agent / install-agent
    p = sub.add_parser("setup-agent", help="互動式 Agent 安裝精靈")
    add_agent_setup_args(p)
    p = sub.add_parser("install-agent", help="setup-agent 的別名")
    add_agent_setup_args(p)

    # import
    p = sub.add_parser("import", help="匯入長文件，或從 Obsidian 同步 notes")
    p.add_argument("file", help="檔案路徑 (.md, .txt)，或使用 obsidian 搭配 --vault")
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
    p.add_argument("--allow-private", action="store_true", help="允許含秘密模式的文件直接匯入本機 vault")
    p.add_argument("--vault", help="Obsidian vault 目錄；僅用於 `vault import obsidian`")
    p.add_argument("--obsidian-raw-subdir", default="obsidian", help="Obsidian notes 寫入 raw/ 下的子目錄")
    p.add_argument("--exclude", action="append", default=[], help="Obsidian 匯入時額外忽略的目錄或檔名，可重複")
    p.add_argument("--dry-run", action="store_true", help="Obsidian 匯入時只列出新增/更新，不寫入")
    p.add_argument("--compile", action="store_true", help="Obsidian 匯入完成後立刻執行 vault compile")

    # export — read-only export targets
    p = sub.add_parser("export", help="匯出知識（單向、唯讀）")
    export_sub = p.add_subparsers(dest="export_target", help="匯出目標")

    ep = export_sub.add_parser("obsidian", help="匯出 Markdown notes 到 Obsidian vault")
    ep.add_argument("--vault", required=True, help="Obsidian vault 目錄")
    ep.add_argument("--category", help="只匯出指定 category")
    ep.add_argument("--tag", help="只匯出含指定 tag 的條目")
    ep.add_argument("--layer", choices=["L0", "L1", "L2", "L3"], help="只匯出指定 layer")
    ep.add_argument("--limit", type=int, help="最多匯出幾條")
    ep.add_argument("--min-trust", type=float, default=0.0, help="最低 trust 門檻")
    ep.add_argument("--source", choices=["db", "raw", "compiled"], default="db", help="來源（MVP 支援 db）")
    ep.add_argument("--dry-run", action="store_true", help="只列出將寫入的檔案，不建立檔案")

    # config
    p = sub.add_parser("config", help="配置管理")
    p.add_argument("config_action", choices=["set", "get", "list"])
    p.add_argument("config_args", nargs="*")

    # db — explicit SQLite schema status/migration/backup workflow
    p = sub.add_parser("db", help="SQLite schema status/migration/backup")
    db_sub = p.add_subparsers(dest="db_action", help="DB 子命令")

    dp = db_sub.add_parser("status", help="顯示 schema 狀態")
    dp.add_argument("--db-path", help="SQLite DB 路徑（預設 project_dir/vault.db）")
    dp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    dp = db_sub.add_parser("migrate", help="執行 idempotent schema migration")
    dp.add_argument("--db-path", help="SQLite DB 路徑（預設 project_dir/vault.db）")
    dp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    dp = db_sub.add_parser("backup", help="建立一致的 SQLite 備份")
    dp.add_argument("--db-path", help="SQLite DB 路徑（預設 project_dir/vault.db）")
    dp.add_argument("--output", help="備份輸出路徑（預設 db 旁 backups/vault-*.db）")
    dp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")
    dp.add_argument("--verify", action="store_true", help="備份後執行 integrity/schema/table-count 驗證")

    dp = db_sub.add_parser("verify-backup", help="驗證 SQLite 備份檔")
    dp.add_argument("backup_path", help="備份 DB 路徑")
    dp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    dp = db_sub.add_parser("restore", help="從已驗證的備份還原 SQLite DB")
    dp.add_argument("backup_path", help="備份 DB 路徑")
    dp.add_argument("--db-path", help="SQLite DB 路徑（預設 project_dir/vault.db）")
    dp.add_argument("--force", action="store_true", help="允許覆蓋既有 DB；覆蓋前會自動備份")
    dp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

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

    # remote — optional Supabase read-only navigation
    p = sub.add_parser("remote", help="Supabase 遠端唯讀搜尋與 bounded read")
    remote_sub = p.add_subparsers(dest="remote_action", help="Remote 子命令")

    def add_remote_output_args(rp):
        rp.add_argument("--json", action="store_true", help="輸出 JSON")
        rp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    rp = remote_sub.add_parser("search", help="透過 Supabase vault_search_readable RPC 搜尋")
    rp.add_argument("query", nargs="?", default="", help="搜尋文字；省略時回傳最新可讀記憶")
    rp.add_argument("--agent-id", default="", help="Agent 身份，用於 owner/allowed_agents 過濾")
    rp.add_argument("--include-private", action="store_true", help="允許讀取此 agent 被授權的 private 記憶")
    rp.add_argument("--max-sensitivity", choices=["low", "medium", "high", "restricted"], default="medium")
    rp.add_argument("--limit", "-n", type=_positive_int, default=10)
    rp.add_argument("--compact", action=argparse.BooleanOptionalAction, default=True, help="回傳精簡欄位")
    add_remote_output_args(rp)

    rp = remote_sub.add_parser("map", help="讀取 Supabase 同步的 Document Map")
    rp.add_argument("knowledge_id", type=int, help="知識 ID")
    rp.add_argument("--compact", action=argparse.BooleanOptionalAction, default=False, help="回傳精簡節點欄位")
    add_remote_output_args(rp)

    rp = remote_sub.add_parser("read", help="讀取 Supabase 同步的 bounded range")
    rp.add_argument("knowledge_id", type=int, help="知識 ID")
    rp.add_argument("--node-uid", default="", help="Document Map node_uid；可單獨指定")
    rp.add_argument("--lines", help="行號範圍，例如 1-40")
    rp.add_argument("--max-lines", type=_positive_int, default=80, help="最大讀取行數")
    add_remote_output_args(rp)

    rp = remote_sub.add_parser("smoke", help="檢查 Supabase remote reader RPC 是否可用")
    rp.add_argument("--query", default="deployment SOP", help="測試查詢文字")
    rp.add_argument("--agent-id", default="", help="Agent 身份，用於 owner/allowed_agents 過濾")
    rp.add_argument("--include-private", action="store_true", help="允許讀取此 agent 被授權的 private 記憶")
    rp.add_argument("--max-sensitivity", choices=["low", "medium", "high", "restricted"], default="medium")
    rp.add_argument("--limit", "-n", type=_positive_int, default=3)
    add_remote_output_args(rp)

    # skill — 本機跨 Agent 技能登錄（實驗性）
    p = sub.add_parser("skill", help="本機技能登錄（實驗性）")
    skill_sub = p.add_subparsers(dest="skill_action", help="技能子命令")

    sp = skill_sub.add_parser("push", help="註冊技能到本機登錄")
    sp.add_argument("--file", "-f", help="SKILL.md 路徑（預設讀 stdin）")
    sp.add_argument("--name", help="技能名稱（預設從 frontmatter 讀取）")
    sp.add_argument("--version", default="1.0.0", help="版本號")
    sp.add_argument("--agent", default="vault-cli", help="來源 Agent")
    sp.add_argument("--category", default="general", help="分類")
    sp.add_argument("--capabilities", default="", help="能力標籤（逗號分隔）")
    sp.add_argument("--dependencies", default="", help="依賴（逗號分隔）")
    sp.add_argument("--trust", type=float, default=0.5, help="信任分數")
    sp.add_argument("--description", default="", help="簡短描述")
    sp.add_argument("--force", action="store_true", help="同名技能時強制覆蓋")

    sp = skill_sub.add_parser("search", help="搜尋本機登錄技能")
    sp.add_argument("query", nargs="?", default="", help="搜尋關鍵字")
    sp.add_argument("--capabilities", help="依能力過濾")
    sp.add_argument("--category", help="依分類過濾")
    sp.add_argument("--agent", help="依來源 Agent 過濾")
    sp.add_argument("--min-trust", type=float, default=0.0)
    sp.add_argument("--limit", "-n", type=int, default=20)

    sp = skill_sub.add_parser("pull", help="從本機登錄下載技能")
    sp.add_argument("name", help="技能名稱")

    sp = skill_sub.add_parser("list", help="列出本機登錄技能")
    sp.add_argument("--agent", help="依來源過濾")
    sp.add_argument("--category", help="依分類過濾")
    sp.add_argument("--min-trust", type=float, default=0.0)
    sp.add_argument("--limit", "-n", type=int, default=100)

    sp = skill_sub.add_parser("stats", help="本機技能登錄統計")

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

    # dream — deterministic report-first curation
    p = sub.add_parser("dream", help="Dream 記憶整理報告（預設 report-only）")
    p.add_argument("--mode", choices=["report", "apply_safe"], default="report")
    p.add_argument("--checks", nargs="*", choices=["freshness", "dedup", "convergence", "metadata", "orphans"],
                   help="要執行的檢查；預設全部")
    p.add_argument("--limit", "-n", type=int, default=50)
    p.add_argument("--write-report", action="store_true", help="寫入 reports/dream/*.md")
    p.add_argument("--no-backup", action="store_true", help="apply_safe 時不建立 DB backup")
    p.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

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
    qp.add_argument("--mode", choices=["auto", "keyword", "vector", "semantic", "hybrid"], default="keyword")
    qp.add_argument("--limit", "-n", type=int, default=10)
    qp.add_argument("--min-score", type=float, default=None,
                    help="minimum keyword match score before counting weak/no-result matches")
    qp.add_argument("--db-path", help="SQLite DB 路徑（預設 project_dir/vault.db）")
    qp.add_argument("--semantic-vector-kind", choices=["claim", "node"], default="claim",
                    help="stored semantic_vectors kind for semantic/hybrid QA")
    qp.add_argument("--allow-hash", action="store_true", help="明確允許測試用 deterministic hash provider")
    qp.add_argument("--hash-dim", type=int, default=32, help="hash provider 維度（僅 --allow-hash）")

    qp = qa_sub.add_parser("compare", help="比較兩個 Search QA snapshot JSON")
    qp.add_argument("--before", required=True, help="before snapshot JSON")
    qp.add_argument("--after", required=True, help="after snapshot JSON")
    qp.add_argument("--output", "-o", help="comparison JSON 輸出路徑")

    # semantic — operator semantic-index workflows
    p = sub.add_parser("semantic", help="語意索引工作流程（rebuild/warm/smoke）")
    semantic_sub = p.add_subparsers(dest="semantic_action", help="Semantic workflow 子命令")

    def add_semantic_common(sp):
        sp.add_argument("--db-path", help="SQLite DB 路徑（預設 project_dir/vault.db）")
        sp.add_argument("--allow-hash", action="store_true", help="明確允許測試用 deterministic hash provider")
        sp.add_argument("--hash-dim", type=int, default=32, help="hash provider 維度（僅 --allow-hash）")
        sp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    def add_cache_filters(sp):
        sp.add_argument("--provider-id", help="只處理指定 embedding provider")
        sp.add_argument("--dimension", type=int, help="只處理指定 embedding 維度")
        sp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")
        sp.add_argument("--db-path", help="SQLite DB 路徑（預設 project_dir/vault.db）")

    sp = semantic_sub.add_parser("rebuild", help="重建 semantic_vectors")
    add_semantic_common(sp)
    sp.add_argument("--knowledge-id", type=int, help="只重建指定 knowledge id")
    sp.add_argument("--persist-cache", action="store_true", help="使用 durable embedding_cache 快取")

    sp = semantic_sub.add_parser("warm", help="預熱 QA 查詢 embedding cache（不寫入向量列）")
    add_semantic_common(sp)
    sp.add_argument("--qa-file", required=True, help="Search QA Set JSON 路徑")
    sp.add_argument("--persist-cache", action="store_true", help="使用 durable embedding_cache 快取")

    sp = semantic_sub.add_parser("smoke", help="重建、預熱並執行 Search QA smoke snapshot")
    add_semantic_common(sp)
    sp.add_argument("--qa-file", required=True, help="Search QA Set JSON 路徑")
    sp.add_argument("--knowledge-id", type=int, help="只重建指定 knowledge id")
    sp.add_argument("--mode", choices=["auto", "keyword", "vector", "semantic", "hybrid"], default="keyword")
    sp.add_argument("--semantic-vector-kind", choices=["claim", "node"], default="claim",
                    help="stored semantic_vectors kind for semantic/hybrid smoke")
    sp.add_argument("--limit", "-n", type=int, default=10)
    sp.add_argument("--output", "-o", help="combined semantic workflow JSON 輸出路徑")
    sp.add_argument("--persist-cache", action="store_true", help="使用 durable embedding_cache 快取")

    sp = semantic_sub.add_parser("cache-stats", help="顯示 durable embedding cache 統計")
    add_cache_filters(sp)

    sp = semantic_sub.add_parser("cache-prune", help="清理 durable embedding cache")
    add_cache_filters(sp)
    sp.add_argument("--older-than-days", type=int, help="刪除 last_used_at 早於 N 天的列")
    sp.add_argument("--max-rows", type=int, help="保留最新 N 列，其餘刪除")

    def add_semantic_lifecycle(sp):
        sp.add_argument("--qa-file", help="Search QA Set JSON 路徑（用於 warm/smoke）")
        sp.add_argument("--allow-hash", action="store_true", help="明確允許測試用 deterministic hash provider")
        sp.add_argument("--hash-dim", type=int, default=32, help="hash provider 維度（僅 --allow-hash）")
        sp.add_argument("--db-path", help="SQLite DB 路徑（預設 project_dir/vault.db）")
        sp.add_argument("--no-persist-cache", action="store_true", help="停用預設 durable embedding cache")
        sp.add_argument("--rebuild", action="store_true", help="在啟動流程中重建 semantic_vectors")
        sp.add_argument("--smoke", action="store_true", help="若提供 --qa-file，執行 Search QA smoke aggregate")
        sp.add_argument("--mode", choices=["auto", "keyword", "vector", "semantic", "hybrid"], default="keyword")
        sp.add_argument("--semantic-vector-kind", choices=["claim", "node"], default="claim",
                        help="stored semantic_vectors kind for semantic/hybrid smoke")
        sp.add_argument("--limit", "-n", type=int, default=10)
        sp.add_argument("--older-than-days", type=int, help="啟動流程結尾清理早於 N 天的 cache rows")
        sp.add_argument("--max-rows", type=int, help="啟動流程結尾最多保留 N 個 cache rows")
        sp.add_argument("--output", "-o", help="JSON 輸出檔案路徑")
        sp.add_argument("--pretty", action="store_true", help="縮排 JSON 輸出")

    sp = semantic_sub.add_parser("startup", help="執行一次 importable semantic startup hook")
    add_semantic_lifecycle(sp)

    sp = semantic_sub.add_parser("daemon", help="執行 bounded semantic warm daemon（預設 repeat=1）")
    add_semantic_lifecycle(sp)
    sp.add_argument("--repeat", type=int, default=1, help="迭代次數；0=forever（只限 supervisor 管理）")
    sp.add_argument("--interval", type=float, default=60.0, help="迭代間隔秒數；測試可用 0")

    args = parser.parse_args(normalized_argv)

    if explicit_project_dir:
        if args.command == "init":
            args.project_dir = explicit_project_dir
        elif args.command in {"setup-agent", "install-agent"}:
            args.agent_project_dir = explicit_project_dir
        else:
            os.chdir(explicit_project_dir)

    commands = {
        "init": cmd_init,
        "add": cmd_add,
        "remember": cmd_remember,
        "promote": cmd_promote,
        "candidates": cmd_candidates,
        "compile": cmd_compile,
        "search": cmd_search,
        "list": cmd_list,
        "remove": cmd_remove,
        "delete": cmd_remove,
        "lint": cmd_lint,
        "doctor": cmd_doctor,
        "stats": cmd_stats,
        "install-embedding": cmd_install_embedding,
        "setup-agent": cmd_setup_agent,
        "install-agent": cmd_setup_agent,
        "import": cmd_import,
        "export": cmd_export,
        "config": cmd_config,
        "db": cmd_db,
        "map": cmd_map,
        "remote": cmd_remote,
        "graph": cmd_graph,
        "skill": cmd_skill,
        "converge": cmd_converge,
        "cross-validate": cmd_cross_validate,
        "freshness": cmd_freshness,
        "dream": cmd_dream,
        "dedup": cmd_dedup,
        "search-qa": cmd_search_qa,
        "semantic": cmd_semantic,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
