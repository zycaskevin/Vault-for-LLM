#!/usr/bin/env python3
"""Synthetic semantic index benchmark.

This measures the current stored-semantic query path directly. It intentionally
bulk-loads deterministic synthetic vectors so the result reflects query scan
cost and truncation behavior, not raw compile or Document Map build time.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vault.db import VaultDB
from vault.semantic import (
    DeterministicHashEmbeddingProvider,
    rebuild_semantic_vec_index,
    search_semantic_index,
    search_semantic_index_vec,
)


def _content_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 6)


def _setup_db(db_path: Path, *, size: int, dim: int) -> tuple[VaultDB, DeterministicHashEmbeddingProvider, str, int]:
    db = VaultDB(db_path).connect()
    provider = DeterministicHashEmbeddingProvider(dim=dim)
    now = datetime.now(timezone.utc).isoformat()
    needle_id = size
    needle_text = f"needle semantic benchmark target {size}"

    knowledge_rows = []
    vector_rows = []
    batch_size = 1000
    for idx in range(1, size + 1):
        is_needle = idx == needle_id
        source_text = needle_text if is_needle else f"filler semantic benchmark claim {idx}"
        title = f"Needle Doc {idx}" if is_needle else f"Filler Doc {idx}"
        knowledge_rows.append(
            (
                idx,
                title,
                "L3",
                "benchmark",
                "semantic,benchmark",
                0.9,
                source_text,
                f"TITLE: {title}\nCLAIMS:\n- [C1] {source_text} (L1)",
                _content_hash(source_text),
                "semantic-index-benchmark",
                now,
                now,
            )
        )
        vector = provider.encode(source_text)[0]
        vector_rows.append(
            (
                idx,
                "claim",
                f"claim-{idx}",
                provider.provider_id,
                provider.dim,
                json.dumps(vector),
                source_text,
                _content_hash(source_text),
                1,
                1,
                now,
                now,
            )
        )
        if len(knowledge_rows) >= batch_size:
            _insert_rows(db, knowledge_rows, vector_rows)
            knowledge_rows.clear()
            vector_rows.clear()

    if knowledge_rows:
        _insert_rows(db, knowledge_rows, vector_rows)

    db.conn.commit()
    return db, provider, needle_text, needle_id


def _insert_rows(db: VaultDB, knowledge_rows: list[tuple], vector_rows: list[tuple]) -> None:
    db.conn.executemany(
        """INSERT INTO knowledge
           (id, title, layer, category, tags, trust, content_raw, content_aaak,
            content_hash, source, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        knowledge_rows,
    )
    db.conn.executemany(
        """INSERT INTO semantic_vectors
           (knowledge_id, vector_kind, item_uid, provider_id, dimension, vector,
            source_text, content_hash, line_start, line_end, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        vector_rows,
    )


def _measure_backend(
    db: VaultDB,
    provider: DeterministicHashEmbeddingProvider,
    *,
    backend: str,
    needle_text: str,
    needle_id: int,
    repeats: int,
    limit: int,
) -> dict:
    latencies: list[float] = []
    hit_ranks: list[int | None] = []
    scanned_rows: list[int] = []
    truncated_flags: list[bool] = []
    search_fn = search_semantic_index_vec if backend == "sqlite_vec" else search_semantic_index
    for _ in range(repeats):
        started = time.perf_counter()
        results = search_fn(
            db,
            needle_text,
            provider=provider,
            vector_kind="claim",
            limit=limit,
            allow_hash=True,
        )
        latencies.append((time.perf_counter() - started) * 1000)
        ids = [int(row["knowledge_id"]) for row in results]
        hit_ranks.append(ids.index(needle_id) + 1 if needle_id in ids else None)
        scanned_rows.append(int(results[0].get("_semantic_scanned_rows", 0)) if results else 0)
        truncated_flags.append(bool(results[0].get("_semantic_truncated", False)) if results else False)

    hits = [rank for rank in hit_ranks if rank is not None]
    return {
        "backend": backend,
        "p50_latency_ms": round(statistics.median(latencies), 6) if latencies else 0.0,
        "p95_latency_ms": _percentile(latencies, 0.95),
        "mean_latency_ms": round(statistics.mean(latencies), 6) if latencies else 0.0,
        "min_latency_ms": round(min(latencies), 6) if latencies else 0.0,
        "max_latency_ms": round(max(latencies), 6) if latencies else 0.0,
        "mean_scanned_rows": round(statistics.mean(scanned_rows), 2) if scanned_rows else 0.0,
        "truncated_runs": sum(1 for flag in truncated_flags if flag),
        "hit_rate": round(len(hits) / repeats, 6) if repeats else 0.0,
        "hit_ranks": hit_ranks,
    }


def run_one(size: int, *, repeats: int, limit: int, dim: int, include_sqlite_vec: bool = True) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"vault-semantic-bench-{size}-") as tmp:
        db, provider, needle_text, needle_id = _setup_db(Path(tmp) / "vault.db", size=size, dim=dim)
        try:
            backends = [
                _measure_backend(
                    db,
                    provider,
                    backend="scan",
                    needle_text=needle_text,
                    needle_id=needle_id,
                    repeats=repeats,
                    limit=limit,
                )
            ]
            vec_index = None
            if include_sqlite_vec and getattr(db, "_vec_available", False):
                rebuild_started = time.perf_counter()
                vec_index = rebuild_semantic_vec_index(db, provider, vector_kind="claim", allow_hash=True)
                rebuild_ms = (time.perf_counter() - rebuild_started) * 1000
                sqlite_vec_result = _measure_backend(
                    db,
                    provider,
                    backend="sqlite_vec",
                    needle_text=needle_text,
                    needle_id=needle_id,
                    repeats=repeats,
                    limit=limit,
                )
                sqlite_vec_result["index_rebuild_ms"] = round(rebuild_ms, 6)
                sqlite_vec_result["indexed_vectors"] = vec_index.indexed_vectors
                backends.append(sqlite_vec_result)
        finally:
            db.close()

    result = {
        "size": size,
        "dimension": dim,
        "limit": limit,
        "repeats": repeats,
        "backends": backends,
        "notes": (
            "Needle is inserted as the last vector. Hit rate drops when the current "
            "Python scan cap truncates before reaching it. sqlite_vec uses a "
            "provider/kind/dimension-scoped shadow index when available."
        ),
    }
    result.update(backends[0])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark stored semantic index scan behavior")
    parser.add_argument("--sizes", nargs="+", type=int, default=[1000, 10000, 12000])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--dim", type=int, default=32)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    results = [run_one(size, repeats=args.repeats, limit=args.limit, dim=args.dim) for size in args.sizes]
    payload = {
        "benchmark": "semantic_index_backend",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
