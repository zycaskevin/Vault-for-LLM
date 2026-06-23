def test_main_accepts_project_dir_for_init(tmp_path):
    from vault.cli import main

    project = tmp_path / "agent-vault"
    main(["init", "--project-dir", str(project)])

    assert (project / "vault.db").exists()
    assert (project / "raw").is_dir()


def test_main_accepts_project_dir_after_search_args(tmp_path, capsys):
    from vault.cli import main

    project = tmp_path / "agent-vault"
    main(["init", "--project-dir", str(project)])
    main([
        "add",
        "Release Checklist",
        "--content",
        "Run README smoke before release.",
        "--project-dir",
        str(project),
    ])
    main([
        "search",
        "README smoke",
        "--limit",
        "1",
        "--project-dir",
        str(project),
    ])

    captured = capsys.readouterr()
    assert "Release Checklist" in captured.out


def test_extract_project_dir_requires_value():
    import pytest
    from vault.cli import _extract_project_dir_arg

    with pytest.raises(SystemExit):
        _extract_project_dir_arg(["search", "query", "--project-dir"])


def test_explicit_project_dir_does_not_climb_to_parent_vault(tmp_path, capsys):
    import json
    from vault.cli import main

    parent = tmp_path / "parent-vault"
    child = parent / "empty-child"
    main(["init", "--project-dir", str(parent)])
    capsys.readouterr()
    child.mkdir()

    main(["--project-dir", str(child), "automation", "doctor", "--pretty"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["project_dir"] == str(child.resolve())
    checks = {item["name"]: item for item in payload["checks"]}
    assert checks["vault_db_exists"]["ok"] is False
    assert checks["raw_dir_exists"]["ok"] is False


def test_remove_requires_confirm_and_delete_alias_removes_entry(tmp_path, capsys):
    import json
    import pytest
    from vault.cli import main

    project = tmp_path / "agent-vault"
    main(["init", "--project-dir", str(project)])
    main(
        [
            "add",
            "Temporary Knowledge",
            "--content",
            "This entry should be removable.",
            "--project-dir",
            str(project),
        ]
    )

    with pytest.raises(SystemExit) as exc:
        main(["remove", "1", "--project-dir", str(project)])
    assert exc.value.code == 2

    main(["delete", "1", "--confirm", "--json", "--project-dir", str(project)])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["removed"] is True
    assert payload["id"] == 1

    main(["search", "Temporary Knowledge", "--project-dir", str(project), "--limit", "1"])
    captured = capsys.readouterr()
    assert "Temporary Knowledge" not in captured.out
