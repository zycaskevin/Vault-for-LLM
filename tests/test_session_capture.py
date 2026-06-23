import json

from vault.db import VaultDB
from vault.session_capture import capture_session_candidates, load_session_units


def test_session_capture_preview_does_not_write_candidates(tmp_path):
    transcript = tmp_path / "codex-session.md"
    transcript.write_text(
        "\n".join(
            [
                "Decision: Use Supabase only as an optional remote sharing layer, not the local source of truth.",
                "Noise.",
                "Bug fix: remote map failed because UUID IDs were treated as integers, so map/read must accept UUIDs.",
            ]
        ),
        encoding="utf-8",
    )

    with VaultDB(tmp_path / "vault.db") as db:
        payload = capture_session_candidates(
            db,
            transcript,
            source_system="codex",
            agent_id="codex",
            write_candidates=False,
        )
        assert payload["write_candidates"] is False
        assert payload["extracted"] == 2
        assert payload["written"] == 0
        assert payload["candidates"][0]["status"] == "preview"
        assert db.list_memory_candidates() == []


def test_session_capture_writes_reviewable_candidates(tmp_path):
    transcript = tmp_path / "hermes-session.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "role": "assistant",
                        "content": "Workflow: Always run vault remote doctor after applying Supabase SQL so hosted readers are checked before use.",
                    }
                ),
                json.dumps(
                    {
                        "role": "assistant",
                        "content": "Decision: Keep remote readers on anon keys and never give hosted agents service role keys.",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    with VaultDB(tmp_path / "vault.db") as db:
        payload = capture_session_candidates(
            db,
            transcript,
            source_system="hermes",
            agent_id="automation-agent",
            write_candidates=True,
        )
        rows = db.list_memory_candidates(limit=10)

    assert payload["write_candidates"] is True
    assert payload["written"] == 2
    assert len(rows) == 2
    assert {row["source"] for row in rows} == {"session_capture"}
    assert all(row["memory_type"] == "session_lesson" for row in rows)
    assert all(row["owner_agent"] == "automation-agent" for row in rows)
    assert any("remote doctor" in row["content"] for row in rows)


def test_session_capture_privacy_gate_rejects_secret_like_content(tmp_path):
    transcript = tmp_path / "openclaw-session.txt"
    secret_phrase = "password" + "=" + "runtimevalue123"
    transcript.write_text(
        f"Bug fix: do not store {secret_phrase} in memory because session captures must keep secrets out.",
        encoding="utf-8",
    )

    with VaultDB(tmp_path / "vault.db") as db:
        payload = capture_session_candidates(
            db,
            transcript,
            source_system="openclaw",
            write_candidates=True,
            include_content=True,
        )
        rows = db.list_memory_candidates(status=None, limit=10)

    assert payload["written"] == 1
    assert payload["rejected"] == 1
    assert "runtimevalue123" not in payload["candidates"][0]["content"]
    assert rows[0]["status"] == "rejected"
    assert rows[0]["privacy_status"] == "fail"
    assert "runtimevalue123" not in rows[0]["content"]


def test_session_capture_preview_redacts_secret_like_payload(tmp_path):
    transcript = tmp_path / "codex-session.txt"
    secret_phrase = "password" + "=" + "runtimevalue123"
    transcript.write_text(
        f"Decision: never store {secret_phrase} in active memory because captures are candidate-only.",
        encoding="utf-8",
    )

    with VaultDB(tmp_path / "vault.db") as db:
        payload = capture_session_candidates(
            db,
            transcript,
            source_system="codex",
            write_candidates=False,
            include_content=True,
        )

    rendered = json.dumps(payload, ensure_ascii=False)
    assert payload["candidates"][0]["gates"]["privacy"] == "fail"
    assert "runtimevalue123" not in rendered


def test_session_capture_loads_jsonl_nested_content(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "response_item": {
                    "content": [
                        {
                            "text": "Decision: Capture adapters should parse nested JSONL message content from agent exports."
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    units = load_session_units(transcript)

    assert len(units) == 1
    assert "nested JSONL" in units[0].text


def test_capture_session_cli_writes_candidates(tmp_path, capsys):
    from vault.cli import main

    project = tmp_path / "project"
    project.mkdir()
    with VaultDB(project / "vault.db"):
        pass
    transcript = tmp_path / "codex-session.md"
    transcript.write_text(
        "Workflow: Always review captured candidates before promotion because active memory must stay governed.",
        encoding="utf-8",
    )

    main(
        [
            "capture",
            "session",
            str(transcript),
            "--source-system",
            "codex",
            "--agent-id",
            "codex",
            "--write-candidates",
            "--project-dir",
            str(project),
            "--pretty",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "completed"
    assert payload["written"] == 1
    assert payload["candidates"][0]["candidate_id"].startswith("mem_")
