#!/usr/bin/env python3
"""Compare exported agent sessions with Vault-backed project onboarding.

This runner is deliberately local and deterministic. It can consume real
Hermes/Codex session exports as text, Markdown, JSON, or JSONL, then compare a
transcript-retrieval baseline against Vault Search QA over the same questions.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from vault.db import VaultDB
from vault.memory import propose_memory
from vault.search_qa import evaluate_search_qa, write_json

from scripts.project_memory_proofs import (
    ONBOARDING_CASES,
    ONBOARDING_DOCS,
    _build_docs_db,
    _write_qa_file,
    run_wrong_source_bounded_read_proof,
)


DEMO_SESSION_TEXT = """
Codex handoff session

The prior agent changed MCP schema handling and said to rerun
tests/test_vault_mcp_map.py plus tests/test_mcp_memory.py before merging.

The release checklist mentioned full pytest, py_compile, README command smoke,
Search QA regression gate, and release parity checks.

The session did not include every source file path or every formal project
policy. It is useful context, but it is not a governed source of truth.
"""


DEMO_SESSION_CASES = [
    {
        **case,
        "expected_session_substrings": expected,
    }
    for case, expected in zip(
        ONBOARDING_CASES,
        [
            ["local SQLite", "Markdown", "no Docker"],
            ["tests/test_vault_mcp_map.py", "tests/test_mcp_memory.py"],
            ["full pytest", "py_compile", "README command smoke"],
            ["bounded read_range", "current source of truth"],
            ["dirty worktree", "preserve unrelated"],
        ],
    )
]


DEMO_CANDIDATES = [
    {
        "title": "MCP schema safety note",
        "content": (
            "MCP schema changes require rerunning map and memory tests because "
            "tool payload regressions can break agent integrations."
        ),
        "reason": "Extracted from a public-safe Codex handoff session.",
        "tags": "mcp,tests",
        "category": "runbook",
        "source_ref": "codex-demo#1",
    },
    {
        "title": "note",
        "content": "remember the thing",
        "reason": "",
        "tags": "",
        "source_ref": "codex-demo#2",
    },
    {
        "title": "Secret candidate",
        "content": f"Do not store {'api' + '_key'}={'abcdefghijklmnop'} in memory.",
        "reason": "Privacy gate demo.",
        "tags": "security",
        "source_ref": "codex-demo#3",
    },
]


def run_benchmark(
    *,
    session_files: list[Path] | None = None,
    qa_file: Path | None = None,
    db_path: Path | None = None,
    candidate_file: Path | None = None,
    work_dir: Path | None = None,
    provider: str = "agent-session",
) -> dict[str, Any]:
    """Run the exported-session vs Vault onboarding benchmark."""
    if work_dir is not None:
        root = Path(work_dir)
        root.mkdir(parents=True, exist_ok=True)
        return _run_benchmark_in_dir(
            root,
            session_files=session_files,
            qa_file=qa_file,
            db_path=db_path,
            candidate_file=candidate_file,
            provider=provider,
        )
    with tempfile.TemporaryDirectory(prefix="vault-agent-onboarding-benchmark-") as tmp:
        return _run_benchmark_in_dir(
            Path(tmp),
            session_files=session_files,
            qa_file=qa_file,
            db_path=db_path,
            candidate_file=candidate_file,
            provider=provider,
        )


def _run_benchmark_in_dir(
    root: Path,
    *,
    session_files: list[Path] | None,
    qa_file: Path | None,
    db_path: Path | None,
    candidate_file: Path | None,
    provider: str,
) -> dict[str, Any]:
    demo_mode = not session_files and qa_file is None and db_path is None
    if demo_mode:
        session_file = root / "demo-codex-session.md"
        session_file.write_text(DEMO_SESSION_TEXT.strip() + "\n", encoding="utf-8")
        session_files = [session_file]
        qa_file = root / "demo-onboarding-qa.json"
        write_json(
            qa_file,
            {
                "version": 1,
                "description": "Public-safe demo agent onboarding benchmark QA.",
                "cases": DEMO_SESSION_CASES,
            },
        )
        db_path = root / "demo-vault.db"
        _build_docs_db(db_path, ONBOARDING_DOCS, build_maps=True)
        candidate_file = root / "demo-candidates.json"
        write_json(candidate_file, {"candidates": DEMO_CANDIDATES})
        provider = "codex-demo"
    elif session_files is None or qa_file is None or db_path is None:
        raise ValueError("--session-file, --qa-file, and --db-path are required outside demo mode")

    assert session_files is not None
    assert qa_file is not None
    assert db_path is not None

    cases = _load_cases(qa_file)
    session_chunks = load_session_chunks(session_files)
    session = evaluate_session_baseline(session_chunks, cases)
    vault = evaluate_vault_onboarding(db_path, qa_file)
    candidate = evaluate_candidate_gate(candidate_file, root) if candidate_file else {
        "status": "not_configured",
        "candidate_count": 0,
    }
    wrong_source = run_wrong_source_bounded_read_proof(root / "wrong_source")

    session_hit_rate = session["hit_rate"]
    vault_hit_rate = vault["topk_hit_rate"]
    return {
        "benchmark_version": 1,
        "mode": "demo_fixture" if demo_mode else "external_session",
        "provider": provider,
        "inputs": {
            "session_files": [str(path) for path in session_files],
            "qa_file": str(qa_file),
            "db_path": str(db_path),
            "candidate_file": str(candidate_file) if candidate_file else "",
        },
        "summary": {
            "task_count": len(cases),
            "session_hit_rate": session_hit_rate,
            "vault_topk_hit_rate": vault_hit_rate,
            "vault_source_hit_rate": vault["source_hit_rate"],
            "vault_read_range_guidance_rate": vault["read_range_guidance_rate"],
            "topk_hit_rate_delta": round(vault_hit_rate - session_hit_rate, 6),
            "candidate_active_delta_before_promotion": candidate.get(
                "active_knowledge_delta_before_promotion"
            ),
            "wrong_source_guard_passed": wrong_source["passed"],
        },
        "session_baseline": session,
        "vault_onboarding": vault,
        "candidate_first": candidate,
        "wrong_source_bounded_read": {
            "passed": wrong_source["passed"],
            "would_title_only_pick_stale_source": wrong_source[
                "would_title_only_pick_stale_source"
            ],
            "source_aware_topk_hit": wrong_source["source_aware_topk_hit"],
            "bounded_read_citation": wrong_source["bounded_read_citation"],
        },
        "notes": [
            "Session baseline is transcript retrieval over exported session text; it is not a claim about a vendor runtime's hidden memory internals.",
            "Vault onboarding uses the same QA cases against source-aware Search QA and bounded-read guidance.",
        ],
    }


def evaluate_vault_onboarding(db_path: Path, qa_file: Path) -> dict[str, Any]:
    snapshot = evaluate_search_qa(
        db_path=db_path,
        qa_file=qa_file,
        mode="keyword",
        limit=5,
        generated_at="2026-01-02T03:04:05+00:00",
    )
    aggregate = snapshot["aggregate"]
    total = max(1, int(aggregate["total_cases"]))
    return {
        "total_cases": aggregate["total_cases"],
        "top1_hits": aggregate["top1_hits"],
        "topk_hits": aggregate["topk_hits"],
        "topk_hit_rate": aggregate["topk_hits"] / total,
        "source_hit_rate": aggregate["source_hit_rate"],
        "read_range_guidance_rate": aggregate["read_range_guidance_rate"],
        "mean_reciprocal_rank": aggregate["mean_reciprocal_rank"],
        "cases": [
            {
                "id": case["id"],
                "top1_hit": case["top1_hit"],
                "topk_hit": case["topk_hit"],
                "hit_rank": case["hit_rank"],
                "source_hit": case["source_hit"],
                "source_hit_rank": case["source_hit_rank"],
                "first_result_source": (
                    case["results"][0].get("source") if case["results"] else ""
                ),
            }
            for case in snapshot["cases"]
        ],
    }


def evaluate_session_baseline(chunks: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    case_results = [score_session_case(chunks, case) for case in cases]
    hits = sum(1 for case in case_results if case["hit"])
    reciprocal_ranks = [
        (1 / case["hit_rank"]) if case["hit_rank"] else 0.0
        for case in case_results
    ]
    return {
        "description": "Deterministic transcript retrieval baseline over exported agent sessions.",
        "chunk_count": len(chunks),
        "total_cases": len(cases),
        "hits": hits,
        "hit_rate": hits / len(cases) if cases else 0.0,
        "mean_reciprocal_rank": (
            sum(reciprocal_ranks) / len(reciprocal_ranks)
            if reciprocal_ranks
            else 0.0
        ),
        "cases": case_results,
    }


def score_session_case(chunks: list[dict[str, Any]], case: dict[str, Any]) -> dict[str, Any]:
    expected = [str(item).lower() for item in _as_list(case.get("expected_session_substrings"))]
    if not expected:
        expected = [
            str(item).lower()
            for item in (
                _as_list(case.get("expected_sources"))
                + _as_list(case.get("expected_titles"))
                + _as_list(case.get("expected_title_substrings"))
            )
        ]
    query_tokens = _tokens(str(case.get("query", "")))
    ranked = []
    for chunk in chunks:
        chunk_tokens = chunk["tokens"]
        overlap = len(query_tokens & chunk_tokens)
        contains_expected = all(fragment in chunk["text_lower"] for fragment in expected)
        ranked.append((contains_expected, overlap, chunk))
    ranked.sort(key=lambda item: (int(item[0]), item[1], -int(item[2]["index"])), reverse=True)

    hit_rank = None
    hit_chunk = None
    for rank, (contains_expected, _overlap, chunk) in enumerate(ranked, start=1):
        if contains_expected:
            hit_rank = rank
            hit_chunk = chunk
            break
    best = ranked[0][2] if ranked else None
    return {
        "id": str(case.get("id", "")),
        "hit": hit_rank is not None,
        "hit_rank": hit_rank,
        "best_file": best["file"] if best else "",
        "best_snippet": _snippet(best["text"]) if best else "",
        "hit_file": hit_chunk["file"] if hit_chunk else "",
        "hit_snippet": _snippet(hit_chunk["text"]) if hit_chunk else "",
        "expected_session_substrings": expected,
    }


def evaluate_candidate_gate(candidate_file: Path | None, root: Path) -> dict[str, Any]:
    candidates = load_candidates(candidate_file)
    db_path = root / "candidate-gate.db"
    with VaultDB(db_path) as db:
        db.add_knowledge(
            "Existing MCP schema safety note",
            "MCP schema changes require rerunning map and memory tests because tool payload regressions can break agent integrations.",
            source="docs/runbooks/mcp-schema-safety.md",
            tags="mcp,tests",
        )
        active_before = _count_active(db)
        proposals = []
        for idx, candidate in enumerate(candidates, start=1):
            payload = propose_memory(
                db,
                mode="candidate",
                title=str(candidate.get("title", f"candidate {idx}")),
                content=str(candidate.get("content", "")),
                reason=str(candidate.get("reason", "")),
                tags=candidate.get("tags", ""),
                category=str(candidate.get("category", "general")),
                source="agent-session-benchmark",
                source_ref=str(candidate.get("source_ref", "")),
                project_dir=root,
            )
            proposals.append(
                {
                    "candidate_id": payload["candidate_id"],
                    "status": payload["status"],
                    "gates": payload["gates"],
                    "source_ref": str(candidate.get("source_ref", "")),
                }
            )
        active_after = _count_active(db)

    buckets = Counter()
    for proposal in proposals:
        gates = proposal["gates"]
        if proposal["status"] == "rejected":
            buckets["rejected"] += 1
        elif gates["duplicate"] == "warn":
            buckets["duplicate_review"] += 1
        elif gates["quality"] == "warn" or gates["metadata"] == "warn":
            buckets["quality_review"] += 1
        elif not proposal["source_ref"]:
            buckets["missing_source_reference"] += 1
        else:
            buckets["ready_for_review"] += 1
    return {
        "status": "evaluated",
        "candidate_count": len(candidates),
        "active_knowledge_before": active_before,
        "active_knowledge_after_proposals": active_after,
        "active_knowledge_delta_before_promotion": active_after - active_before,
        "review_buckets": dict(sorted(buckets.items())),
        "proposals": proposals,
        "passed": active_after == active_before,
    }


def load_session_chunks(paths: Iterable[Path]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for path in paths:
        text = "\n".join(load_session_texts(path))
        for idx, chunk in enumerate(split_chunks(text), start=1):
            chunks.append(
                {
                    "file": str(path),
                    "index": len(chunks) + 1,
                    "local_index": idx,
                    "text": chunk,
                    "text_lower": chunk.lower(),
                    "tokens": _tokens(chunk),
                }
            )
    return chunks


def load_session_texts(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        texts: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                texts.extend(_strings_from_json(json.loads(line)))
            except json.JSONDecodeError:
                texts.append(line)
        return texts
    if suffix == ".json":
        try:
            return _strings_from_json(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            return [path.read_text(encoding="utf-8")]
    return [path.read_text(encoding="utf-8")]


def split_chunks(text: str, *, max_chars: int = 1400) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > max_chars:
            chunks.append(current)
            current = paragraph
        elif current:
            current = f"{current}\n\n{paragraph}"
        else:
            current = paragraph
    if current:
        chunks.append(current)
    return chunks or ([text.strip()] if text.strip() else [])


def load_candidates(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates = payload.get("candidates") if isinstance(payload, dict) else payload
    if not isinstance(candidates, list):
        raise ValueError("candidate file must contain a list or an object with candidates")
    return [candidate for candidate in candidates if isinstance(candidate, dict)]


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("QA file must contain a cases list")
    return [case for case in cases if isinstance(case, dict)]


def _strings_from_json(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        texts: list[str] = []
        for item in value:
            texts.extend(_strings_from_json(item))
        return texts
    if isinstance(value, dict):
        texts: list[str] = []
        for key, item in value.items():
            if key in {"content", "text", "message", "summary", "body", "transcript"}:
                texts.extend(_strings_from_json(item))
            elif isinstance(item, (dict, list)):
                texts.extend(_strings_from_json(item))
        return texts
    return []


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", text.lower())
        if len(token) > 2
        and token
        not in {"the", "and", "for", "with", "from", "which", "should", "before"}
    }


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _snippet(text: str, *, limit: int = 220) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 3] + "..."


def _count_active(db: VaultDB) -> int:
    return int(db.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"])


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare exported Hermes/Codex sessions with Vault onboarding QA."
    )
    parser.add_argument("--session-file", type=Path, action="append", default=[])
    parser.add_argument("--qa-file", type=Path, default=None)
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--candidate-file", type=Path, default=None)
    parser.add_argument("--provider", default="agent-session")
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = run_benchmark(
            session_files=args.session_file or None,
            qa_file=args.qa_file,
            db_path=args.db_path,
            candidate_file=args.candidate_file,
            work_dir=args.work_dir,
            provider=args.provider,
        )
    except Exception as exc:
        print(f"agent onboarding benchmark failed: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(report, ensure_ascii=False, indent=None if args.compact else 2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
