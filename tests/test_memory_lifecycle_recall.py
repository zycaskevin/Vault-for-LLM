"""End-to-end recall checks for candidate-first memory lifecycle."""

from __future__ import annotations

from pathlib import Path

from vault.db import VaultDB
from vault.memory import create_candidate, promote_candidate
from vault.search import VaultSearch
from vault.search_qa import evaluate_search_qa


def test_memory_lifecycle_promote_search_and_search_qa(tmp_path: Path):
    qa_file = tmp_path / "qa.json"
    with VaultDB(tmp_path / "vault.db") as db:
        proposed = create_candidate(
            db,
            title="Agent Memory Promotion Guide",
            content=(
                "Agent memory promotion should use candidate-first review because it prevents "
                "untrusted notes from entering active recall. The fix for noisy memories is to "
                "promote only reviewed candidates with useful tags."
            ),
            reason="Verify promoted memories can be recalled by Search QA.",
            tags="agent,memory,promotion",
            category="workflow",
            source="test",
        )
        promoted = promote_candidate(db, proposed["candidate_id"], confirm=True, project_dir=tmp_path)
        assert promoted["status"] == "promoted"

        results = VaultSearch(db).search("candidate first active recall", mode="keyword", limit=5, use_rerank=False)
        assert any(result["title"] == "Agent Memory Promotion Guide" for result in results)

    qa_file.write_text(
        '{"version":1,"cases":[{"id":"promoted_memory","query":"candidate first active recall","expected_titles":["Agent Memory Promotion Guide"]}]}',
        encoding="utf-8",
    )
    snapshot = evaluate_search_qa(db_path=tmp_path / "vault.db", qa_file=qa_file, mode="keyword", limit=5)
    assert snapshot["aggregate"]["topk_hits"] == 1


def test_memory_lifecycle_cjk_recall(tmp_path: Path):
    with VaultDB(tmp_path / "vault.db") as db:
        proposed = create_candidate(
            db,
            title="中文記憶召回指南",
            content="中文記憶召回需要保留清楚標籤與原因，因為 CJK 查詢常依賴標題、標籤與關鍵短語共同命中。",
            reason="確認中文 query 可以找回 promoted memory。",
            tags="中文,記憶,召回",
            category="workflow",
            source="test",
        )
        promote_candidate(db, proposed["candidate_id"], confirm=True, project_dir=tmp_path)
        results = VaultSearch(db).search("中文 記憶 召回", mode="keyword", limit=5, use_rerank=False)
        assert any(result["title"] == "中文記憶召回指南" for result in results)
