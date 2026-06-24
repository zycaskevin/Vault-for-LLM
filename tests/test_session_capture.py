import json

from vault.db import VaultDB
from vault.session_capture import capture_session_candidates, discover_session_transcripts, load_session_units


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


def test_session_capture_preview_redacts_standalone_api_key(tmp_path):
    transcript = tmp_path / "codex-session.txt"
    token = "sk-proj-1234567890abcdefghij1234567890"
    transcript.write_text(
        f"Fix: session capture previews must redact {token} before showing candidate reports.",
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
    assert token not in rendered


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


def test_discover_session_transcripts_finds_project_exports_without_content(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    transcript = sessions / "codex-session.jsonl"
    secret_phrase = "password" + "=" + "runtimevalue123"
    transcript.write_text(
        json.dumps(
            {
                "role": "assistant",
                "content": f"Decision: discovery should not read {secret_phrase} from transcript content.",
            }
        ),
        encoding="utf-8",
    )

    payload = discover_session_transcripts(tmp_path, limit=5)
    rendered = json.dumps(payload, ensure_ascii=False)

    assert payload["status"] == "completed"
    assert payload["read_contents"] is False
    assert payload["count"] == 1
    item = payload["transcripts"][0]
    assert item["capture_path"] == "sessions/codex-session.jsonl"
    assert item["source_system"] == "codex"
    assert item["format"] == "jsonl"
    assert "session-like filename" in item["reasons"]
    assert "runtimevalue123" not in rendered


def test_discover_session_transcripts_skips_external_dirs_by_default(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (external / "hermes-session.md").write_text(
        "Decision: external discovery requires explicit permission.",
        encoding="utf-8",
    )

    payload = discover_session_transcripts(project, search_dirs=[external])

    assert payload["count"] == 0
    assert payload["scanned_roots"] == []


def test_discover_session_transcripts_can_allow_external_dirs(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (external / "hermes-session.md").write_text(
        "Decision: external discovery can be explicitly allowed.",
        encoding="utf-8",
    )

    payload = discover_session_transcripts(
        project,
        search_dirs=[external],
        allow_absolute_paths=True,
    )

    assert payload["count"] == 1
    assert payload["transcripts"][0]["path_scope"] == "absolute"
    assert payload["transcripts"][0]["source_system"] == "hermes"


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


def test_capture_discover_cli_lists_project_transcripts(tmp_path, capsys):
    from vault.cli import main

    project = tmp_path / "project"
    sessions = project / "sessions"
    sessions.mkdir(parents=True)
    with VaultDB(project / "vault.db"):
        pass
    (sessions / "openclaw-session.txt").write_text(
        "Workflow: discovery should list this session export before capture.",
        encoding="utf-8",
    )

    main(["capture", "discover", "--project-dir", str(project), "--pretty"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["action"] == "discover_session_transcripts"
    assert payload["count"] == 1
    assert payload["transcripts"][0]["capture_path"] == "sessions/openclaw-session.txt"
