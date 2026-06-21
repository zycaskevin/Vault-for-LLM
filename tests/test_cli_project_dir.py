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
