#!/usr/bin/env python3
"""Run local proof demos for Vault-for-LLM's project memory value.

The proofs are intentionally small, deterministic, and public-safe. They are not
research benchmarks. They demonstrate the workflow difference between "a pile
of notes" and governed project memory that agents can search, review, and cite.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from vault.db import VaultDB
from vault.docmap import build_document_map_for_entry
from vault.mcp import _vault_read_range_payload
from vault.memory import promote_candidate, propose_memory
from vault.search_qa import evaluate_search_qa, write_json


ONBOARDING_DOCS = [
    {
        "title": "Project Architecture Boundaries",
        "source": "docs/architecture/boundaries.md",
        "category": "architecture",
        "tags": "architecture,local-first,sqlite",
        "content": "\n".join(
            [
                "# Project Architecture Boundaries",
                "Vault-for-LLM keeps the canonical project memory in local SQLite and Markdown.",
                "The stable path must not require Docker, hosted services, or network access.",
                "Optional semantic, Supabase, and rerank features are additive rather than required.",
            ]
        ),
    },
    {
        "title": "MCP Change Safety Runbook",
        "source": "docs/runbooks/mcp-change-safety.md",
        "category": "runbook",
        "tags": "mcp,tests,schemas",
        "content": "\n".join(
            [
                "# MCP Change Safety Runbook",
                "Before changing MCP tool schemas, run the MCP map and memory tests.",
                "The minimum local gate is tests/test_vault_mcp_map.py and tests/test_mcp_memory.py.",
                "Keep compact search payloads as the default unless a caller asks for full output.",
            ]
        ),
    },
    {
        "title": "Release Quality Gate",
        "source": "docs/runbooks/release-quality-gate.md",
        "category": "release",
        "tags": "release,ci,quality",
        "content": "\n".join(
            [
                "# Release Quality Gate",
                "Before publishing, run full pytest, py_compile, README command smoke, Search QA regression gate, and release parity checks.",
                "Installed-wheel behavior must be checked when package metadata or entry points change.",
                "Do not publish until the working tree is clean and CI is green.",
            ]
        ),
    },
    {
        "title": "Source of Truth Policy",
        "source": "docs/policies/source-of-truth.md",
        "category": "policy",
        "tags": "citation,source-of-truth,read-range",
        "content": "\n".join(
            [
                "# Source of Truth Policy",
                "Search previews are navigation hints only, not final answer evidence.",
                "Final answers must cite bounded read_range output from the current source of truth.",
                "If old and current documents disagree, prefer the explicitly marked current source.",
            ]
        ),
    },
    {
        "title": "Agent Handoff Pitfalls",
        "source": "docs/runbooks/agent-handoff-pitfalls.md",
        "category": "runbook",
        "tags": "handoff,git,safety",
        "content": "\n".join(
            [
                "# Agent Handoff Pitfalls",
                "Never reset a dirty worktree while taking over an agent project.",
                "Inspect git status first, preserve unrelated user changes, and branch from latest main for incremental fixes.",
                "When a prior PR is merged, open a fresh branch instead of amending the old one.",
            ]
        ),
    },
]


ONBOARDING_CASES = [
    {
        "id": "stable_path_boundaries",
        "query": "stable path local SQLite Markdown no Docker hosted services",
        "expected_sources": ["docs/architecture/boundaries.md"],
        "expected_title_substrings": ["Architecture", "Boundaries"],
    },
    {
        "id": "mcp_schema_gate",
        "query": "MCP tool schema changes which tests should run compact payload",
        "expected_sources": ["docs/runbooks/mcp-change-safety.md"],
        "expected_title_substrings": ["MCP", "Safety"],
    },
    {
        "id": "release_quality_commands",
        "query": "publishing release full pytest py_compile readme smoke search qa parity",
        "expected_sources": ["docs/runbooks/release-quality-gate.md"],
        "expected_title_substrings": ["Release", "Quality"],
    },
    {
        "id": "citation_source_truth",
        "query": "final citations search preview bounded read_range source of truth",
        "expected_sources": ["docs/policies/source-of-truth.md"],
        "expected_title_substrings": ["Source", "Truth"],
    },
    {
        "id": "handoff_dirty_worktree",
        "query": "dirty worktree preserve unrelated changes branch latest main",
        "expected_sources": ["docs/runbooks/agent-handoff-pitfalls.md"],
        "expected_title_substrings": ["Agent", "Handoff"],
    },
]


def run_all_proofs(work_dir: Path | None = None) -> dict[str, Any]:
    """Run all proof demos and return a deterministic JSON-serializable report."""
    if work_dir is not None:
        root = Path(work_dir)
        root.mkdir(parents=True, exist_ok=True)
        return _run_all_in_dir(root)
    with tempfile.TemporaryDirectory(prefix="vault-project-memory-proofs-") as tmp:
        return _run_all_in_dir(Path(tmp))


def _run_all_in_dir(root: Path) -> dict[str, Any]:
    return {
        "proof_version": 1,
        "description": (
            "Public-safe local demos for project memory onboarding, "
            "candidate-first governance, and source-aware bounded reads."
        ),
        "proofs": {
            "agent_onboarding": run_agent_onboarding_proof(root / "agent_onboarding"),
            "candidate_first": run_candidate_first_proof(root / "candidate_first"),
            "wrong_source_bounded_read": run_wrong_source_bounded_read_proof(
                root / "wrong_source_bounded_read"
            ),
        },
    }


def run_agent_onboarding_proof(root: Path) -> dict[str, Any]:
    """Show that source-aware Search QA can answer project handoff questions."""
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "vault.db"
    qa_file = root / "onboarding_qa.json"
    _build_docs_db(db_path, ONBOARDING_DOCS, build_maps=True)
    _write_qa_file(qa_file, ONBOARDING_CASES)

    snapshot = evaluate_search_qa(
        db_path=db_path,
        qa_file=qa_file,
        mode="keyword",
        limit=5,
        generated_at="2026-01-02T03:04:05+00:00",
    )
    aggregate = snapshot["aggregate"]
    naive_hits = _naive_title_or_source_hits(ONBOARDING_DOCS, ONBOARDING_CASES)
    return {
        "claim": "A new agent can recover project onboarding facts from governed project memory.",
        "task_count": len(ONBOARDING_CASES),
        "naive_title_or_source_hits": naive_hits,
        "vault_top1_hits": aggregate["top1_hits"],
        "vault_topk_hits": aggregate["topk_hits"],
        "vault_source_hit_rate": aggregate["source_hit_rate"],
        "vault_read_range_guidance_rate": aggregate["read_range_guidance_rate"],
        "mean_reciprocal_rank": aggregate["mean_reciprocal_rank"],
        "passed": aggregate["topk_hits"] == len(ONBOARDING_CASES)
        and aggregate["source_hit_rate"] == 1.0,
        "snapshot": _compact_snapshot(snapshot),
    }


def run_candidate_first_proof(root: Path) -> dict[str, Any]:
    """Show that proposed memories are gated before entering active knowledge."""
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "vault.db"
    with VaultDB(db_path) as db:
        db.add_knowledge(
            "Ollama timeout runbook",
            "Ollama timeout failures are fixed by warming the model and setting timeout=120.",
            source="docs/runbooks/ollama-timeout.md",
            tags="ollama,timeout",
            category="runbook",
            trust=0.8,
        )
        active_before = _count_active(db)
        proposals = [
            _propose(
                db,
                root,
                label="ready_to_promote",
                title="Reviewed rollback SOP",
                content=(
                    "Rollback failures are caused by skipping verified backups; "
                    "the fix is to verify the backup before promoting or reverting a release."
                ),
                reason="Keep reviewed release rollback steps for future agents.",
                tags="release,rollback,backup",
                source_ref="demo-session#ready",
                category="runbook",
            ),
            _propose(
                db,
                root,
                label="duplicate",
                title="Ollama timeout runbook",
                content=(
                    "Ollama timeout failures are fixed by warming the model and setting timeout=120."
                ),
                reason="Duplicate regression candidate.",
                tags="ollama,timeout",
                source_ref="demo-session#duplicate",
            ),
            _propose(
                db,
                root,
                label="too_vague",
                title="note",
                content="remember this",
                reason="",
                tags="",
                source_ref="demo-session#vague",
            ),
            _propose(
                db,
                root,
                label="privacy_blocked",
                title="Secret candidate",
                content=f"Do not store {'api' + '_key'}={'abcdefghijklmnop'} in project memory.",
                reason="Privacy gate regression.",
                tags="security",
                source_ref="demo-session#secret",
            ),
            _propose(
                db,
                root,
                label="missing_source_review",
                title="Undersourced dependency decision",
                content=(
                    "The dependency decision should be reviewed because it lacks a durable source reference."
                ),
                reason="Show source-reference review bucket.",
                tags="dependency,decision",
                source_ref="",
            ),
        ]
        active_after_proposals = _count_active(db)

        first_candidate = proposals[0]["candidate_id"]
        promoted = promote_candidate(
            db,
            first_candidate,
            confirm=True,
            project_dir=root,
            compile=False,
        )
        active_after_promote = _count_active(db)

    review_buckets = Counter()
    gate_status_counts: dict[str, Counter] = {
        "privacy": Counter(),
        "duplicate": Counter(),
        "metadata": Counter(),
        "quality": Counter(),
        "source_reference": Counter(),
    }
    for proposal in proposals:
        gates = proposal["gates"]
        for gate, status in gates.items():
            gate_status_counts[gate][status] += 1
        if not proposal["source_ref"]:
            gate_status_counts["source_reference"]["warn"] += 1
            review_buckets["missing_source_reference"] += 1
        if proposal["status"] == "rejected":
            review_buckets["rejected"] += 1
        elif gates["duplicate"] == "warn":
            review_buckets["duplicate_review"] += 1
        elif gates["quality"] == "warn" or gates["metadata"] == "warn":
            review_buckets["quality_review"] += 1
        elif proposal["source_ref"]:
            review_buckets["ready_for_review"] += 1

    return {
        "claim": "Unreviewed agent memories stay out of active knowledge until promoted.",
        "candidate_count": len(proposals),
        "active_knowledge_before": active_before,
        "active_knowledge_after_proposals": active_after_proposals,
        "active_knowledge_after_one_promotion": active_after_promote,
        "active_knowledge_delta_before_promotion": active_after_proposals - active_before,
        "promoted_candidate_id": first_candidate,
        "promoted_knowledge_id": promoted["knowledge_id"],
        "review_buckets": dict(sorted(review_buckets.items())),
        "gate_status_counts": {
            gate: dict(sorted(counts.items()))
            for gate, counts in sorted(gate_status_counts.items())
        },
        "passed": active_after_proposals == active_before
        and active_after_promote == active_before + 1
        and review_buckets["rejected"] == 1
        and review_buckets["duplicate_review"] >= 1
        and review_buckets["quality_review"] >= 1,
        "candidates": proposals,
    }


def run_wrong_source_bounded_read_proof(root: Path) -> dict[str, Any]:
    """Show that title matches are not enough when old and current docs coexist."""
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "vault.db"
    qa_file = root / "wrong_source_qa.json"
    docs = [
        {
            "title": "Deployment Runbook",
            "source": "docs/archive/deployment-runbook.md",
            "category": "runbook",
            "tags": "deployment,archive,legacy",
            "content": "\n".join(
                [
                    "# Deployment Runbook",
                    "Archived source. The old customer portal deployment used docker compose on staging.",
                    "Legacy rollback advice: restart the staging container and retry the deploy.",
                    "This document is not the current source of truth.",
                ]
            ),
        },
        {
            "title": "Deployment Runbook",
            "source": "docs/runbooks/deployment-runbook.md",
            "category": "runbook",
            "tags": "deployment,current,rollback,backup",
            "content": "\n".join(
                [
                    "# Deployment Runbook",
                    "Current source of truth for customer portal deployment.",
                    "Rollback requires a verified SQLite backup before the release is reverted.",
                    "Use bounded read_range output for final citations.",
                ]
            ),
        },
    ]
    cases = [
        {
            "id": "current_deployment_runbook",
            "query": "customer portal deployment rollback verified SQLite backup source of truth",
            "expected_titles": ["Deployment Runbook"],
            "expected_sources": ["docs/runbooks/deployment-runbook.md"],
        }
    ]
    id_by_source = _build_docs_db(db_path, docs, build_maps=True)
    _write_qa_file(qa_file, cases)
    snapshot = evaluate_search_qa(
        db_path=db_path,
        qa_file=qa_file,
        mode="keyword",
        limit=5,
        generated_at="2026-01-02T03:04:05+00:00",
    )
    case = snapshot["cases"][0]
    correct_source = cases[0]["expected_sources"][0]
    matched = next(
        result for result in case["results"] if result.get("source") == correct_source
    )
    line_start = int(matched.get("line_start") or 2)
    line_end = int(matched.get("line_end") or 4)
    bounded = _vault_read_range_payload(
        id_by_source[correct_source],
        line_start=line_start,
        line_end=line_end,
        max_lines=20,
        db_path=str(db_path),
    )
    title_only_first_source = docs[0]["source"]

    return {
        "claim": "When duplicate titles exist, source-aware matching plus bounded reads prevents stale-source answers.",
        "title_only_first_source": title_only_first_source,
        "expected_current_source": correct_source,
        "would_title_only_pick_stale_source": title_only_first_source != correct_source,
        "source_aware_top1_hit": case["top1_hit"],
        "source_aware_topk_hit": case["topk_hit"],
        "source_aware_hit_rank": case["hit_rank"],
        "source_hit_rank": case["source_hit_rank"],
        "bounded_read_citation": bounded.get("citation", ""),
        "bounded_read_contains_current_policy": "Current source of truth" in bounded.get("content", ""),
        "passed": case["topk_hit"]
        and case["source_hit"]
        and title_only_first_source != correct_source
        and "Current source of truth" in bounded.get("content", ""),
        "snapshot": _compact_snapshot(snapshot),
        "bounded_read": {
            "title": bounded.get("title"),
            "range": bounded.get("range"),
            "citation": bounded.get("citation"),
            "content": bounded.get("content"),
        },
    }


def _propose(db: VaultDB, root: Path, *, label: str, **kwargs: Any) -> dict[str, Any]:
    payload = propose_memory(
        db,
        mode="candidate",
        project_dir=root,
        source="proof-demo",
        **kwargs,
    )
    payload["label"] = label
    payload["source_ref"] = kwargs.get("source_ref", "")
    return {
        "label": label,
        "candidate_id": payload["candidate_id"],
        "status": payload["status"],
        "source_ref": payload["source_ref"],
        "gates": payload["gates"],
    }


def _build_docs_db(db_path: Path, docs: list[dict[str, str]], *, build_maps: bool) -> dict[str, int]:
    source_to_id: dict[str, int] = {}
    db = VaultDB(db_path).connect()
    try:
        for doc in docs:
            knowledge_id = db.add_knowledge(
                doc["title"],
                doc["content"],
                category=doc.get("category", "general"),
                tags=doc.get("tags", ""),
                trust=0.8,
                source=doc["source"],
            )
            source_to_id[doc["source"]] = knowledge_id
            if build_maps:
                build_document_map_for_entry(db.conn, knowledge_id)
    finally:
        db.close()
    return source_to_id


def _write_qa_file(path: Path, cases: list[dict[str, Any]]) -> None:
    write_json(
        path,
        {
            "version": 1,
            "description": "Project memory proof fixture generated by scripts/project_memory_proofs.py",
            "cases": cases,
        },
    )


def _compact_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "aggregate": snapshot["aggregate"],
        "cases": [
            {
                "id": case["id"],
                "top1_hit": case["top1_hit"],
                "topk_hit": case["topk_hit"],
                "hit_rank": case["hit_rank"],
                "source_hit": case["source_hit"],
                "source_hit_rank": case["source_hit_rank"],
                "results": [
                    {
                        "title": result.get("title"),
                        "source": result.get("source"),
                        "score": result.get("score"),
                    }
                    for result in case["results"][:3]
                ],
            }
            for case in snapshot["cases"]
        ],
    }


def _naive_title_or_source_hits(
    docs: list[dict[str, str]],
    cases: list[dict[str, Any]],
) -> int:
    hits = 0
    for case in cases:
        query_terms = _tokens(case["query"])
        expected_sources = set(case.get("expected_sources") or [])
        found = False
        for doc in docs:
            haystack = f"{doc['title']} {doc['source']}"
            haystack_terms = _tokens(haystack)
            if query_terms and query_terms.issubset(haystack_terms):
                found = doc["source"] in expected_sources
                break
        if found:
            hits += 1
    return hits


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", text.lower())
        if len(token) > 2
        and token
        not in {
            "the",
            "and",
            "for",
            "with",
            "from",
            "which",
            "should",
            "before",
        }
    }


def _count_active(db: VaultDB) -> int:
    return int(db.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"])


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Vault-for-LLM project memory proof demos.")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path.")
    parser.add_argument("--work-dir", type=Path, default=None, help="Optional directory for generated demo DBs.")
    parser.add_argument("--compact", action="store_true", help="Print compact JSON instead of indented JSON.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_all_proofs(args.work_dir)
    rendered = json.dumps(report, ensure_ascii=False, indent=None if args.compact else 2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
