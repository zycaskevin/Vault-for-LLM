"""Obsidian setup guides for human-facing Vault review surfaces."""

from __future__ import annotations

from pathlib import Path


def write_obsidian_human_gui_guide(
    *,
    output_dir: str | Path,
    project_dir: str | Path,
    obsidian_vault: str | Path,
) -> dict[str, str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    project = Path(project_dir).expanduser()
    vault = Path(obsidian_vault).expanduser()
    guide = out / "README-obsidian-human-gui.md"
    guide.write_text(
        "\n".join(
            [
                "# Obsidian as the Human Vault GUI",
                "",
                "Use Obsidian for reading and light review. Use Vault for governed agent memory.",
                "",
                "## Where to look",
                "",
                "- `00-Vault-Knowledge/_Inbox/Daily Memory Report.md`: the short daily review.",
                "- `00-Vault-Knowledge/_Inbox/Memory Candidates.md`: agent-proposed memories that still need review.",
                "- `00-Vault-Knowledge/_Inbox/Sync Status.md`: missing notes and remote sync conflicts.",
                "- `00-Vault-Knowledge/_Inbox/Folder Rules Preview.md`: how folders map to memory permissions.",
                "",
                "## Safe habit",
                "",
                "- Edit your own notes outside `00-Vault-Knowledge/`.",
                "- Treat `_Inbox` files as generated review cards.",
                "- Change folder permissions in `.vault/obsidian-folder-rules.yaml`, then rerun the import.",
                "",
                "## Paths",
                "",
                f"- Vault project: `{project}`",
                f"- Obsidian vault: `{vault}`",
                f"- Folder rules: `{project / '.vault' / 'obsidian-folder-rules.yaml'}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"guide": str(guide)}
