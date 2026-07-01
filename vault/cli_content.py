"""Content import/export, graph, and skill CLI handlers."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sqlite3
import sys
from pathlib import Path

from .cli_context import _arg_value, _enforce_cli_privacy, _json_print, find_project_dir
from .cli_search import temporal_search_kwargs


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
    json_output = _arg_value(args, "json", False) is True or _arg_value(args, "pretty", False) is True
    pretty_output = _arg_value(args, "pretty", False) is True

    if action == "build":
        """自動推斷實體和關聯。"""
        if _arg_value(args, "clear", False) is True:
            graph.clear_auto_inferred()
        if not json_output:
            print("🔄 掃描知識庫，推斷圖譜...")
        result = graph.infer_all()
        payload = {"ok": True, "status": "ok", "action": "build", **result}
        if json_output:
            _json_print(payload, pretty=pretty_output)
            db.close()
            return
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
        edges = db.get_edges()
        entities = db.conn.execute("SELECT * FROM entities ORDER BY id DESC LIMIT 20").fetchall()
        edge_items = []
        for e in edges[:20]:
            src = db.get_knowledge(e["source_id"])
            tgt = db.get_knowledge(e["target_id"])
            item = dict(e)
            item["source_title"] = src["title"] if src else ""
            item["target_title"] = tgt["title"] if tgt else ""
            edge_items.append(item)
        entity_items = []
        for e in entities:
            item = dict(e)
            item["knowledge_count"] = db.conn.execute(
                "SELECT COUNT(*) FROM entity_knowledge WHERE entity_id=?", (e["id"],)
            ).fetchone()[0]
            entity_items.append(item)
        payload = {
            "ok": True,
            "status": "ok",
            "action": "show",
            "stats": stats,
            "edges": edge_items,
            "entities": entity_items,
        }
        if json_output:
            _json_print(payload, pretty=pretty_output)
            db.close()
            return
        print("🕸️ Vault-for-LLM 圖譜\n")
        print(f"  邊（總計）: {stats['edges_total']}")
        print(f"    自動推斷: {stats['edges_auto']}")
        print(f"    手動建立: {stats['edges_manual']}")
        print(f"  實體數量:   {stats['entities_total']}")
        print(f"  連通節點:   {stats['connected_nodes']}")

        # 列出邊
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

    if args.file == "memory":
        from vault.db import VaultDB
        from vault.memory_migration import migrate_memory_source

        source = getattr(args, "source", None)
        if not source:
            print("❌ vault import memory 需要 --source /path/to/export")
            raise SystemExit(2)
        try:
            with VaultDB(db_path) as db:
                payload = migrate_memory_source(
                    db,
                    source,
                    source_format=getattr(args, "format", "auto"),
                    dry_run=getattr(args, "dry_run", False) or not getattr(args, "write_candidates", False),
                    layer=args.layer,
                    category=args.category if args.category != "general" else "",
                    tags=args.tags,
                    trust=args.trust,
                    reason=getattr(args, "reason", ""),
                    scope=_arg_value(args, "scope", "project"),
                    sensitivity=_arg_value(args, "sensitivity", "low"),
                    owner_agent=_arg_value(args, "owner_agent", ""),
                    allowed_agents=_arg_value(args, "allowed_agents", ""),
                    memory_type=_arg_value(args, "memory_type", ""),
                    expires_at=_arg_value(args, "expires_at", ""),
                    valid_from=_arg_value(args, "valid_from", ""),
                    valid_until=_arg_value(args, "valid_until", ""),
                    supersedes_id=_arg_value(args, "supersedes_id", None),
                    only=getattr(args, "only", ""),
                    limit=getattr(args, "limit", None),
                    max_file_bytes=getattr(args, "max_file_bytes", 2_000_000),
                )
        except Exception as e:
            print(f"❌ 外部記憶匯入失敗: {e}")
            raise SystemExit(2) from e

        if getattr(args, "json", False) or getattr(args, "pretty", False):
            _json_print(payload, pretty=getattr(args, "pretty", False))
        else:
            print("🧳 外部記憶搬家結果:")
            print(f"  來源: {payload['source']}")
            print(f"  格式: {payload['format']}")
            print(f"  模式: {'dry-run preview' if payload['dry_run'] else 'write candidates'}")
            print(f"  項目: {payload['item_count']}")
            print(f"  候選: {payload['candidate_count']}")
            print(f"  已建立: {payload['created_count']}")
            print(f"  已拒絕: {payload['rejected_count']}")
            print(f"  隱私阻擋: {payload['privacy_fail']}")
            print(f"  重複提醒: {payload['duplicate_warn']}")
            if payload.get("errors"):
                print(f"  錯誤: {payload['error_count']}")
                for error in payload["errors"][:5]:
                    print(f"    - {error.get('path', '')}: {error.get('message', '')}")
            for item in payload.get("candidates", [])[:10]:
                ident = item.get("candidate_id") or item.get("external_id") or item.get("source_ref")
                print(f"    - {item.get('status')}: {item.get('title')} ({ident})")
            if payload["dry_run"]:
                print("下一步：確認 preview 後，加 --write-candidates 寫入候選記憶。")
            elif payload["created_count"]:
                print("下一步：執行 vault candidates，審查後再 vault promote <candidate_id> --confirm。")
        if payload["status"] == "error":
            raise SystemExit(1)
        return

    if args.file == "okf":
        from vault.db import VaultDB
        from vault.okf import import_okf_bundle

        if not getattr(args, "bundle", None):
            print("❌ vault import okf 需要 --bundle /path/to/okf-bundle")
            raise SystemExit(2)

        try:
            with VaultDB(db_path) as db:
                payload = import_okf_bundle(
                    db,
                    args.bundle,
                    dry_run=args.dry_run,
                    max_file_bytes=args.max_file_bytes,
                    layer=args.layer,
                    category=args.category if args.category != "general" else "",
                    tags=args.tags,
                    trust=args.trust,
                    reason=getattr(args, "reason", ""),
                    scope=_arg_value(args, "scope", "project"),
                    sensitivity=_arg_value(args, "sensitivity", "low"),
                    owner_agent=_arg_value(args, "owner_agent", ""),
                    allowed_agents=_arg_value(args, "allowed_agents", ""),
                    memory_type=_arg_value(args, "memory_type", "okf_concept"),
                    expires_at=_arg_value(args, "expires_at", ""),
                    valid_from=_arg_value(args, "valid_from", ""),
                    valid_until=_arg_value(args, "valid_until", ""),
                    supersedes_id=_arg_value(args, "supersedes_id", None),
                    limit=getattr(args, "limit", None),
                )
        except Exception as e:
            print(f"❌ OKF 匯入失敗: {e}")
            raise SystemExit(2) from e

        if getattr(args, "json", False) or getattr(args, "pretty", False):
            _json_print(payload, pretty=getattr(args, "pretty", False))
        else:
            print("📦 OKF 匯入結果:")
            print(f"  Bundle: {payload['bundle_dir']}")
            print(f"  模式: {'dry-run' if payload['dry_run'] else 'write candidates'}")
            print(f"  Validation: {payload['validation']['status']} ({payload['validation']['error_count']} errors, {payload['validation']['warning_count']} warnings)")
            print(f"  候選: {payload['candidate_count']}")
            print(f"  已建立: {payload['created_count']}")
            print(f"  已拒絕: {payload['rejected_count']}")
            for item in payload.get("candidates", [])[:10]:
                ident = item.get("candidate_id") or item.get("path")
                print(f"    - {item.get('status')}: {item.get('title')} ({ident})")
            if not payload["dry_run"] and payload["created_count"]:
                print("下一步：執行 vault candidates，審查後再 vault promote <candidate_id> --confirm。")
        if payload["status"] == "error":
            raise SystemExit(1)
        return

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
                prune_missing=getattr(args, "prune_missing", False),
                folder_rules_path=getattr(args, "obsidian_rules", None),
            )
        except Exception as e:
            print(f"❌ Obsidian 匯入失敗: {e}")
            raise SystemExit(2) from e

        if getattr(args, "json", False) or getattr(args, "pretty", False):
            payload = {"import": result}
            if not args.dry_run and args.compile:
                import argparse
                from .cli_core import cmd_compile

                compile_args = argparse.Namespace(
                    dry_run=False,
                    no_embed=args.no_embed,
                    allow_private=getattr(args, "allow_private", False),
                )
                captured = io.StringIO()
                with contextlib.redirect_stdout(captured):
                    cmd_compile(compile_args)
                payload["compile_output"] = captured.getvalue()
            _json_print(payload, pretty=getattr(args, "pretty", False))
            return

        print("📥 Obsidian 匯入結果:")
        print(f"  掃描: {result['scanned']}")
        print(f"  新增: {result['added']}")
        print(f"  更新: {result['updated']}")
        print(f"  跳過: {result['skipped']}")
        print(f"  來源已移除: {result.get('missing', 0)}")
        print(f"  已刪除 raw copy: {result.get('deleted', 0)}")
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
            from .cli_core import cmd_compile

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
    elif args.skill_action == "versions":
        cmd_skill_versions(args)
    elif args.skill_action == "diff":
        cmd_skill_diff(args)
    elif args.skill_action == "upgrade-plan":
        cmd_skill_upgrade_plan(args)
    else:
        print("用法: vault skill {push|search|pull|list|stats|versions|diff|upgrade-plan}")


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

    existed_before = db.get_skill(name) is not None
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
        force=bool(getattr(args, "force", False)),
    )

    if kid == -1:
        print(f"⚠️ 技能 '{name}' 已存在，且版本未更新。用較新的 --version 或 --force 覆蓋。")
    elif existed_before and getattr(args, "force", False):
        print(f"✅ 技能 '{name}' 已強制覆蓋")
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


def cmd_skill_versions(args):
    """列出一個技能的版本歷史。"""
    from vault.db import VaultDB

    project_dir = find_project_dir()
    db = VaultDB(str(project_dir / "vault.db")).connect()
    try:
        payload = {"ok": True, "name": args.name, "versions": db.list_skill_versions(args.name)}
        if getattr(args, "json", False) or getattr(args, "pretty", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2 if getattr(args, "pretty", False) else None))
            return
        if not payload["versions"]:
            print(f"📭 技能 '{args.name}' 沒有版本紀錄")
            return
        print(f"🛠️  {args.name} versions:")
        for row in payload["versions"]:
            print(f"  - v{row['version']} hash={row['content_hash']} updated={row['updated_at']}")
    finally:
        db.close()


def cmd_skill_diff(args):
    """比較技能版本。"""
    from vault.db import VaultDB

    project_dir = find_project_dir()
    db = VaultDB(str(project_dir / "vault.db")).connect()
    try:
        payload = db.diff_skill_versions(args.name, args.from_version, args.to_version)
        if getattr(args, "json", False) or getattr(args, "pretty", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2 if getattr(args, "pretty", False) else None))
            return
        if not payload.get("ok"):
            print(f"❌ {payload.get('error')}: {args.name}")
            return
        print(f"🛠️  {args.name}: v{args.from_version} → v{args.to_version}")
        print(f"   content_changed: {payload['content_changed']}")
        for field, change in payload["changed_fields"].items():
            print(f"   {field}: {change['from']} → {change['to']}")
    finally:
        db.close()


def cmd_skill_upgrade_plan(args):
    """列出技能升級計畫。"""
    from vault.db import VaultDB

    installed = {}
    if getattr(args, "installed_file", ""):
        installed_path = Path(args.installed_file)
        if not installed_path.exists():
            print(f"❌ --installed-file 不存在: {installed_path}")
            return
        try:
            loaded_file = json.loads(installed_path.read_text(encoding="utf-8"))
            if isinstance(loaded_file, dict):
                installed = loaded_file
        except json.JSONDecodeError as exc:
            print(f"❌ --installed-file 必須是 JSON object: {exc}")
            return
    if getattr(args, "installed", ""):
        try:
            loaded = json.loads(args.installed)
            if isinstance(loaded, dict):
                installed.update(loaded)
        except json.JSONDecodeError as exc:
            print(f"❌ --installed 必須是 JSON object: {exc}")
            return
    project_dir = find_project_dir()
    db = VaultDB(str(project_dir / "vault.db")).connect()
    try:
        payload = db.skill_upgrade_plan(installed=installed)
        if getattr(args, "json", False) or getattr(args, "pretty", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2 if getattr(args, "pretty", False) else None))
            return
        counts = payload.get("status_counts", {})
        print(f"🛠️  Skill upgrade plan: {payload['upgrade_count']} upgrades / {payload['skill_count']} skills")
        if counts:
            summary = ", ".join(f"{key}={counts[key]}" for key in sorted(counts))
            print(f"   狀態: {summary}")
        for row in payload["skills"]:
            if getattr(args, "outdated_only", False) and row["status"] in {"current", "not_installed"}:
                continue
            print(
                f"  - {row['name']}: {row['current_version'] or '-'} → {row['latest_version']} "
                f"({row['status']}; action={row['recommended_action']})"
            )
        if payload.get("next_action"):
            print(f"Next: {payload['next_action']}")
    finally:
        db.close()
