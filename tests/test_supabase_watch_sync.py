import json


def test_watch_supabase_sync_once_dry_run_writes_report(tmp_path):
    from scripts.watch_supabase_sync import main

    db = tmp_path / "vault.db"
    db.write_bytes(b"sqlite placeholder")
    report = tmp_path / "reports" / "supabase-sync-latest.json"

    rc = main(
        [
            "--db",
            str(db),
            "--once",
            "--dry-run",
            "--report",
            str(report),
        ]
    )

    assert rc == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "dry_run"
    assert payload["mode"] == "near_realtime_push"
    assert payload["direction"] == "local_to_supabase"
    assert payload["bidirectional"] is False
    assert payload["realtime"] is True
    assert "scripts.sync_to_supabase" in payload["command"]


def test_watch_supabase_sync_missing_db_returns_error(tmp_path):
    from scripts.watch_supabase_sync import main

    rc = main(["--db", str(tmp_path / "missing.db"), "--once", "--dry-run"])

    assert rc == 2
