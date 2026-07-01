"""Core CLI command handlers."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

from .cli_context import _arg_value, _enforce_cli_privacy, _json_print, find_project_dir
from .cli_search import temporal_search_kwargs


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
    json_output = _arg_value(args, "json", False) is True
    pretty_output = _arg_value(args, "pretty", False) is True

    # 如果指定 --file，讀取檔案內容。省略 --content 才讀 stdin；
    # 明確傳入 --content "" 時要快速失敗，避免 n8n/agent subprocess 卡住。
    content = _arg_value(args, "content", None)
    file_arg = _arg_value(args, "file", None)
    if file_arg:
        content = Path(file_arg).read_text(encoding="utf-8")
    elif content is None:
        if not json_output:
            print(f"標題: {args.title}")
            print("請輸入內容（Ctrl+D 結束）:")
        content = sys.stdin.read()
    if content == "":
        message = "content is empty; pass non-empty --content, --file, or stdin input"
        if json_output:
            _json_print({"ok": False, "status": "error", "error": message}, pretty=pretty_output)
        else:
            print(f"error: {message}", file=sys.stderr)
        raise SystemExit(2)

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
        valid_from=_arg_value(args, "valid_from", ""),
        valid_until=_arg_value(args, "valid_until", ""),
        supersedes_id=_arg_value(args, "supersedes_id", None),
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
        if not json_output:
            print(f"✅ 新增知識 ID={kid}")

    # 也寫到 raw/
    raw_file = project_dir / "raw" / _safe_raw_filename(args.title)
    fm = {
        "title": args.title,
        "layer": args.layer or "L3",
        "category": args.category or "general",
        "tags": args.tags or "",
        "trust": args.trust or 0.5,
        **governance,
    }
    try:
        raw_file.write_text(
            f"---\n{json.dumps(fm, ensure_ascii=False, indent=2)}\n---\n\n{content}\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raw_synced = False
        raw_error = str(exc)
        if not json_output:
            print(f"warning: active knowledge was added, but raw sync failed: {exc}", file=sys.stderr)
    else:
        raw_synced = True
        raw_error = ""
        if not json_output:
            print(f"✅ 同步寫入 raw/{raw_file.name}")

    if json_output:
        _json_print(
            {
                "ok": True,
                "status": "ok",
                "id": kid,
                "title": args.title,
                "layer": args.layer or "L3",
                "category": args.category or "general",
                "tags": args.tags or "",
                "trust": args.trust or 0.5,
                "source": source,
                "raw_path": str(raw_file),
                "raw_synced": raw_synced,
                "raw_error": raw_error,
                **governance,
            },
            pretty=pretty_output,
        )


def _safe_raw_filename(title: object, *, max_stem_chars: int = 80) -> str:
    stem = re.sub(r"[^\w.-]+", "_", str(title or "untitled").strip(), flags=re.UNICODE)
    stem = re.sub(r"_+", "_", stem).strip("._-") or "untitled"
    if len(stem) > max_stem_chars:
        digest = hashlib.sha256(str(title).encode("utf-8")).hexdigest()[:12]
        keep = max(1, max_stem_chars - len(digest) - 1)
        stem = f"{stem[:keep].rstrip('._-')}-{digest}"
    return f"{stem}.md"


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
    if stats.get("embedding_errors"):
        print(f"  嵌入錯誤: {stats['embedding_errors']} (知識已編譯；可用 --no-embed 跳過)")


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
            **temporal_search_kwargs(args),
        )
    except SemanticProviderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        db.close()
        raise SystemExit(2) from exc

    if bool(_arg_value(args, "json", False)):
        payload = {
            "query": args.query,
            "requested_mode": mode,
            "mode": results[0].get("_mode", mode) if results else mode,
            "count": len(results),
            "results": results,
        }
        indent = 2 if bool(_arg_value(args, "pretty", False)) else None
        print(json.dumps(payload, ensure_ascii=False, indent=indent, default=str))
        db.close()
        return

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
    if db_exists:
        from vault.diagnostics import sqlite_vec_runtime_status
        checks.append(("sqlite-vec runtime", sqlite_vec_runtime_status(project_dir), True))

    # 嵌入模型快取
    cache_dir = Path.home() / ".cache" / "vault-mcp" / "models"
    if cache_dir.exists():
        models = [d.name for d in cache_dir.iterdir() if d.is_dir()]
        checks.append(("嵌入模型快取", f"✅ {len(models)} 模型", True))
    else:
        checks.append(("嵌入模型快取", "❌ 無 (vault install-embedding)", False))

    all_ok = all(bool(ok) for _name, _status, ok in checks)
    payload = {
        "ok": all_ok,
        "status": "ok" if all_ok else "warning",
        "checks": [
            {"name": name, "status": status, "ok": bool(ok)}
            for name, status, ok in checks
        ],
        "next_action": (
            "Vault environment is ready."
            if all_ok
            else "Install optional semantic dependencies only if you need semantic search."
        ),
    }
    if _arg_value(args, "json", False) is True or _arg_value(args, "pretty", False) is True:
        _json_print(payload, pretty=_arg_value(args, "pretty", False) is True)
        return

    print("🏥 Vault-for-LLM 環境診斷\n")
    for name, status, ok in checks:
        print(f"  {name:25s} {status}")

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
    layers = [
        dict(row)
        for row in db.conn.execute(
            "SELECT layer, COUNT(*) as cnt FROM knowledge GROUP BY layer ORDER BY layer"
        ).fetchall()
    ]
    categories = [
        dict(row)
        for row in db.conn.execute(
            "SELECT category, COUNT(*) as cnt FROM knowledge GROUP BY category ORDER BY cnt DESC"
        ).fetchall()
    ]
    connected = None
    if stats.get("edge_count", 0) > 0:
        connected = db.conn.execute(
            "SELECT COUNT(DISTINCT n) FROM ("
            "SELECT source_id AS n FROM edges UNION "
            "SELECT target_id AS n FROM edges)"
        ).fetchone()[0]

    json_output = getattr(args, "json", False) is True
    pretty_output = getattr(args, "pretty", False) is True
    if json_output:
        _json_print(
            {
                "stats": stats,
                "layers": layers,
                "categories": categories,
                "graph_connected_nodes": connected,
            },
            pretty=pretty_output,
        )
        db.close()
        return

    print("📊 Vault-for-LLM 統計\n")
    from vault.diagnostics import stats_summary_lines
    for line in stats_summary_lines(stats):
        print(line)

    # 分層統計
    if layers:
        print("\n  分層:")
        for row in layers:
            print(f"    {row['layer']}: {row['cnt']} 筆")

    # 分類統計
    if categories:
        print("\n  分類:")
        for row in categories:
            print(f"    {row['category']}: {row['cnt']} 筆")

    # 圖譜連通度
    if connected is not None:
        print(f"\n  圖譜連通: {connected}/{stats['knowledge_count']} 節點")

    db.close()
