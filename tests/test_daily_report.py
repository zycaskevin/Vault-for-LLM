from __future__ import annotations

import json

from vault.cli import main
from vault.daily_report import build_daily_report, render_daily_report_text
from vault.db import VaultDB
from vault.memory import create_candidate


def _project_with_candidate(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    with VaultDB(project / "vault.db") as db:
        db.add_knowledge(
            "Daily Report Existing Memory",
            "This reviewed memory is already active.",
            category="general",
            trust=0.8,
        )
        candidate = create_candidate(
            db,
            title="Daily Report Candidate",
            content="Decision: keep this as a reviewed project memory after the user confirms it.",
            reason="A useful daily report test candidate.",
            category="decision",
            trust=0.7,
            source="test",
            source_ref="tests/test_daily_report.py",
        )
    return project, candidate["candidate_id"]


def test_daily_report_is_read_only_and_writes_artifacts(tmp_path):
    project, candidate_id = _project_with_candidate(tmp_path)

    payload = build_daily_report(project, write_report=True)

    assert payload["action"] == "daily-report"
    assert payload["safety"]["read_only"] is True
    assert payload["safety"]["writes_active_memory"] is False
    assert payload["summary"]["pending_candidates"] >= 1
    assert payload["review_cards"]
    assert any(card["id"] == candidate_id for card in payload["review_cards"])
    assert payload["paths"]["json"] == "reports/daily/daily-report-latest.json"
    assert payload["paths"]["markdown"] == "reports/daily/daily-report-latest.md"
    assert (project / payload["paths"]["json"]).exists()
    assert "Vault Daily Memory Report" in (project / payload["paths"]["markdown"]).read_text(encoding="utf-8")


def test_render_daily_report_text_is_short_and_human_first(tmp_path):
    project, _candidate_id = _project_with_candidate(tmp_path)

    text = render_daily_report_text(build_daily_report(project, limit=3))

    assert "Vault Daily Memory Report" in text
    assert "Needs Your Decision" in text
    assert "choices:" in text
    assert "raw candidate" not in text.lower()


def test_daily_report_supports_traditional_and_simplified_chinese(tmp_path):
    project, _candidate_id = _project_with_candidate(tmp_path)

    zh_hant = build_daily_report(project, limit=3, language="zh-Hant")
    zh_cn = build_daily_report(project, limit=3, language="zh-CN")

    assert zh_hant["language"] == "zh-Hant"
    assert zh_cn["language"] == "zh-CN"
    assert "需要你確認" in zh_hant["headline"]
    assert "需要你确认" in zh_cn["headline"]
    assert "Vault 每日記憶報告" in render_daily_report_text(zh_hant)
    assert "Vault 每日记忆报告" in render_daily_report_text(zh_cn)


def test_daily_report_does_not_escalate_observe_cards_to_human_decisions(tmp_path, monkeypatch):
    import vault.daily_report as daily_report

    project = tmp_path / "project"
    project.mkdir()
    with VaultDB(project / "vault.db"):
        pass

    monkeypatch.setattr(
        daily_report,
        "automation_brief",
        lambda *args, **kwargs: {
            "status": "completed",
            "summary": {
                "pending_candidates": 0,
                "learning_rules": 0,
                "expired_active": 0,
            },
            "agent_health": {"agent_count": 1},
        },
    )
    monkeypatch.setattr(
        daily_report,
        "automation_review_summary",
        lambda *args, **kwargs: {
            "cards": [
                {
                    "kind": "memory_importance",
                    "id": 1,
                    "title": "Observed useful memory",
                    "recommended_action": "keep_observing",
                    "reason": "This is useful but does not need a human decision.",
                    "requires_human_decision": False,
                }
            ]
        },
    )

    payload = daily_report.build_daily_report(project, language="zh-Hant")

    assert payload["summary"]["needs_confirmation"] == 0
    assert payload["review_cards"] == []
    assert "今天沒有需要人決定" in payload["headline"]


def test_cli_daily_report_json_and_write_report(tmp_path, capsys):
    project, _candidate_id = _project_with_candidate(tmp_path)

    main(["--project-dir", str(project), "daily-report", "--write-report", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "daily-report"
    assert payload["paths"]["json"] == "reports/daily/daily-report-latest.json"
    assert (project / "reports" / "daily" / "daily-report-latest.md").exists()


def test_cli_daily_report_accepts_language(tmp_path, capsys):
    project, _candidate_id = _project_with_candidate(tmp_path)

    main(["--project-dir", str(project), "daily-report", "--language", "zh-CN", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["language"] == "zh-CN"
    assert payload["labels"]["title"] == "Vault 每日记忆报告"
