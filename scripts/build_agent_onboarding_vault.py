#!/usr/bin/env python3
"""Build a repository-doc Vault for the exported-agent onboarding benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from vault.db import VaultDB
from vault.docmap import build_document_map_for_entry


REPO_DOCS = [
    {
        "path": "README.md",
        "title": "Vault README",
        "category": "overview",
        "tags": "readme,onboarding",
    },
    {
        "path": "docs/mcp_memory_workflow.md",
        "title": "MCP Memory Workflow",
        "category": "mcp",
        "tags": "mcp,candidate,governance",
    },
    {
        "path": "docs/mcp_tool_reference.md",
        "title": "MCP Tool Reference",
        "category": "mcp",
        "tags": "mcp,tools,agent-integration",
    },
    {
        "path": "docs/document_map_citation_policy.md",
        "title": "Document Map Citation Policy",
        "category": "citation",
        "tags": "document-map,citation,bounded-read",
    },
    {
        "path": "docs/db_backup_restore.md",
        "title": "SQLite Backup Restore",
        "category": "operations",
        "tags": "backup,restore,sqlite",
    },
    {
        "path": "docs/search_qa_benchmarking.md",
        "title": "Search QA Benchmarking",
        "category": "quality",
        "tags": "search-qa,benchmark",
    },
    {
        "path": "docs/semantic_search.md",
        "title": "Semantic Search",
        "category": "retrieval",
        "tags": "semantic,sqlite-vec",
    },
    {
        "path": "docs/repo_governance.md",
        "title": "Repo Governance",
        "category": "governance",
        "tags": "repo,git,safety",
    },
    {
        "path": "docs/agent_onboarding_benchmark.md",
        "title": "Agent Onboarding Benchmark",
        "category": "benchmark",
        "tags": "onboarding,benchmark",
    },
]


def build_repo_docs_vault(
    output_dir: Path,
    *,
    repo_root: Path = PROJECT_ROOT,
    db_name: str = "repo-docs-vault.db",
    force: bool = False,
) -> dict[str, Any]:
    """Build a local Vault database from public repository docs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / db_name
    if db_path.exists():
        if not force:
            raise FileExistsError(f"{db_path} already exists; pass --force to replace it")
        db_path.unlink()

    manifest: dict[str, Any] = {
        "db_path": str(db_path),
        "repo_root": str(repo_root),
        "doc_count": 0,
        "map_nodes": 0,
        "map_claims": 0,
        "docs": [],
    }

    db = VaultDB(db_path).connect()
    try:
        for spec in REPO_DOCS:
            rel_path = spec["path"]
            source_path = repo_root / rel_path
            if not source_path.exists():
                raise FileNotFoundError(f"required benchmark source is missing: {rel_path}")
            content = source_path.read_text(encoding="utf-8")
            knowledge_id = db.add_knowledge(
                spec["title"],
                content,
                source=rel_path,
                category=spec["category"],
                tags=spec["tags"],
                trust=0.9,
            )
            map_counts = build_document_map_for_entry(db.conn, knowledge_id)
            manifest["doc_count"] += 1
            manifest["map_nodes"] += map_counts["nodes"]
            manifest["map_claims"] += map_counts["claims"]
            manifest["docs"].append(
                {
                    "knowledge_id": knowledge_id,
                    "source": rel_path,
                    "title": spec["title"],
                    "nodes": map_counts["nodes"],
                    "claims": map_counts["claims"],
                }
            )
    finally:
        db.close()

    manifest_path = output_dir / "repo-docs-vault.manifest.json"
    manifest["manifest_path"] = str(manifest_path)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a repository-doc Vault DB for agent onboarding benchmarks."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--db-name", default="repo-docs-vault.db")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = build_repo_docs_vault(
            args.output_dir,
            repo_root=args.repo_root,
            db_name=args.db_name,
            force=args.force,
        )
    except Exception as exc:
        print(f"agent onboarding vault build failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=None if args.compact else 2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
