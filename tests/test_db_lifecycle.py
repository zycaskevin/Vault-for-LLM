from datetime import datetime, timezone

from vault.db_lifecycle import build_cold_store_summary, cold_store_safety, parse_timestamp


def test_parse_timestamp_accepts_date_and_iso_datetime():
    assert parse_timestamp("2026-06-26").isoformat() == "2026-06-26T00:00:00+00:00"
    assert parse_timestamp("2026-06-26T10:30:00Z").isoformat() == "2026-06-26T10:30:00+00:00"
    assert parse_timestamp("") is None
    assert parse_timestamp("not-a-date") is None


def test_cold_store_summary_redacts_and_reports_usage():
    summary = build_cold_store_summary(
        {
            "title": "Token note",
            "content_raw": "Never store " + "password" + "=supersecret123 in public memory.",
            "access_count": 2,
            "citation_count": 1,
        },
        max_chars=160,
        now_text=datetime(2026, 6, 26, tzinfo=timezone.utc).isoformat(),
    )

    assert "supersecret123" not in summary
    assert "[REDACTED]" in summary
    assert "access=2, citations=1" in summary


def test_cold_store_safety_is_reversible():
    safety = cold_store_safety()
    assert safety["hard_delete"] is False
    assert safety["original_content_retained"] is True
    assert safety["normal_recall_removed"] is True
