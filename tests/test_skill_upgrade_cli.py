import json

from vault.cli import main
from vault.db import VaultDB


def test_skill_upgrade_plan_reads_installed_file(tmp_path, monkeypatch, capsys):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    with VaultDB(project / "vault.db") as db:
        db.add_skill(name="review-helper", version="1.1.0", content_raw="Review workflow v2")

    installed_file = project / "installed-skills.json"
    installed_file.write_text(
        json.dumps({"review-helper": {"version": "1.0.0", "content_hash": "oldhash"}}),
        encoding="utf-8",
    )

    main(["skill", "upgrade-plan", "--installed-file", str(installed_file), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["upgrade_count"] == 1
    assert payload["skills"][0]["status"] == "upgrade_available"
    assert payload["skills"][0]["installed_hash"] == "oldhash"


def test_skill_upgrade_plan_outdated_only_hides_current(tmp_path, monkeypatch, capsys):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    with VaultDB(project / "vault.db") as db:
        db.add_skill(name="current-helper", version="1.0.0", content_raw="Current workflow")
        current = db.get_skill("current-helper")

    installed_file = project / "installed-skills.json"
    installed_file.write_text(
        json.dumps({"current-helper": {"version": "1.0.0", "content_hash": current["content_hash"]}}),
        encoding="utf-8",
    )

    main(["skill", "upgrade-plan", "--installed-file", str(installed_file), "--outdated-only"])

    out = capsys.readouterr().out
    assert "Skill upgrade plan" in out
    assert "current-helper:" not in out
