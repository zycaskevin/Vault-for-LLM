"""Static browser app loader for the local Vault GUI."""

from __future__ import annotations

from importlib.resources import files


def _load_app_html() -> str:
    return files("vault").joinpath("assets/gui_app.html").read_text(encoding="utf-8")


APP_HTML = _load_app_html()
