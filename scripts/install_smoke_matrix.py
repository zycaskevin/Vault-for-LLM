#!/usr/bin/env python3
"""Run a release-oriented install smoke matrix.

The matrix intentionally checks behavior that can differ between a source
checkout and an installed wheel:

- CLI entrypoint availability
- project init/add/search/list
- Document Map bounded reads
- candidate-first memory writes
- automation brief/cycle/handoff
- DB schema status
- MCP stdio tool listing and basic search/read calls

The script is conservative: it uses temporary projects, writes no real user
memory, and does not publish or upload anything.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


class SmokeFailure(RuntimeError):
    pass


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = result.stdout.strip()
    if result.returncode != 0:
        joined = " ".join(command)
        raise SmokeFailure(f"Command failed ({result.returncode}): {joined}\n{output}")
    return output


def _python_exe(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _script_exe(venv_dir: Path, name: str) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / f"{name}.exe"
    return venv_dir / "bin" / name


def _prepare_wheel_env(wheel: Path, work_dir: Path, *, venv_python: str) -> dict[str, Any]:
    venv_dir = work_dir / "wheel-venv"
    if venv_dir.exists():
        shutil.rmtree(venv_dir)
    _run([venv_python, "-m", "venv", str(venv_dir)], cwd=work_dir)
    python = _python_exe(venv_dir)
    _run([str(python), "-m", "pip", "install", f"{wheel}[mcp]"], cwd=work_dir)
    return {
        "name": "wheel",
        "project_dir": work_dir / "wheel-project",
        "vault": [str(_script_exe(venv_dir, "vault"))],
        "vault_mcp": str(_script_exe(venv_dir, "vault-mcp")),
        "python": str(python),
        "env": os.environ.copy(),
    }


def _prepare_source_env(work_dir: Path) -> dict[str, Any]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(REPO_ROOT) + (os.pathsep + existing if existing else "")
    return {
        "name": "source",
        "project_dir": work_dir / "source-project",
        "vault": [sys.executable, "-m", "vault.cli"],
        "vault_mcp": str(REPO_ROOT / "vault" / "mcp.py"),
        "python": sys.executable,
        "env": env,
    }


def _vault(ctx: dict[str, Any], *args: str, cwd: Path | None = None) -> str:
    return _run(
        [*ctx["vault"], "--project-dir", str(ctx["project_dir"]), *args],
        cwd=cwd or ctx["project_dir"],
        env=ctx["env"],
    )


def _assert_contains(haystack: str, needle: str, label: str) -> None:
    if needle not in haystack:
        raise SmokeFailure(f"{label} did not contain {needle!r}:\n{haystack}")


def _exercise_cli(ctx: dict[str, Any]) -> dict[str, Any]:
    project = Path(ctx["project_dir"])
    project.mkdir(parents=True, exist_ok=True)

    version = _run([*ctx["vault"], "--version"], cwd=project, env=ctx["env"])
    _vault(ctx, "init")
    _vault(
        ctx,
        "add",
        "Install Smoke Runbook",
        "--content",
        "Install smoke should find this runbook. Document Map should cite bounded lines.",
        "--layer",
        "L3",
        "--category",
        "qa",
        "--tags",
        "smoke,install",
        "--scope",
        "project",
        "--sensitivity",
        "low",
    )
    search = _vault(ctx, "search", "install smoke runbook", "--limit", "3")
    _assert_contains(search, "Install Smoke Runbook", "search")
    listing = _vault(ctx, "list", "--limit", "5")
    _assert_contains(listing, "Install Smoke Runbook", "list")
    _vault(ctx, "map", "build")
    map_read = _vault(ctx, "map", "read", "1", "--lines", "1-5")
    _assert_contains(map_read, "bounded lines", "map read")
    remember = _vault(
        ctx,
        "remember",
        "Install smoke candidate",
        "--content",
        "Candidate-first memory write path works after install.",
        "--reason",
        "Verify candidate review queue in installed environments.",
        "--source",
        "session_capture",
        "--source-ref",
        "smoke://install",
        "--scope",
        "project",
        "--sensitivity",
        "low",
    )
    _assert_contains(remember, "candidate", "remember")
    candidates = _vault(ctx, "candidates", "--limit", "5")
    _assert_contains(candidates, "Install smoke candidate", "candidates")

    transcript = project / "session.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps({"role": "user", "content": "Verify install smoke."}),
                json.dumps({"role": "assistant", "content": "Wheel and source smoke passed."}),
            ]
        ),
        encoding="utf-8",
    )
    capture = _vault(ctx, "capture", "session", str(transcript), "--pretty")
    capture_payload = json.loads(capture)
    if capture_payload.get("action") != "capture_session":
        raise SmokeFailure(f"Unexpected capture payload: {capture_payload}")

    brief = json.loads(_vault(ctx, "automation", "brief", "--pretty"))
    if brief.get("action") != "brief":
        raise SmokeFailure(f"Unexpected automation brief payload: {brief}")
    cycle = json.loads(_vault(ctx, "automation", "cycle", "--write-workspace", "--pretty"))
    if cycle.get("action") != "cycle":
        raise SmokeFailure(f"Unexpected automation cycle payload: {cycle}")
    handoff = json.loads(_vault(ctx, "automation", "handoff", "--pretty"))
    if handoff.get("action") != "handoff":
        raise SmokeFailure(f"Unexpected automation handoff payload: {handoff}")
    db_status = json.loads(_vault(ctx, "db", "status"))
    if db_status.get("needs_migration"):
        raise SmokeFailure(f"New project unexpectedly needs migration: {db_status}")
    usage = json.loads(_vault(ctx, "usage", "stats", "--json"))
    if usage.get("knowledge_count") != 1:
        raise SmokeFailure(f"Unexpected usage stats: {usage}")

    return {
        "version": version,
        "project_dir": str(project),
        "search_ok": True,
        "map_read_ok": True,
        "candidate_ok": True,
        "capture_ok": True,
        "automation_ok": True,
        "db_status_ok": True,
    }


def _exercise_mcp(ctx: dict[str, Any]) -> dict[str, Any]:
    project = Path(ctx["project_dir"])
    if ctx["name"] == "source":
        server_command = sys.executable
        server_args = [
            "-c",
            "from vault.mcp import main; main()",
            "--project-dir",
            str(project),
            "--tool-profile",
            "core",
        ]
    else:
        server_command = ctx["vault_mcp"]
        server_args = ["--project-dir", str(project), "--tool-profile", "core"]

    script = textwrap.dedent(
        f"""
        import anyio
        import json
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def main():
            params = StdioServerParameters(
                command={server_command!r},
                args={server_args!r},
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    names = [tool.name for tool in tools.tools]
                    required = ["vault_search", "vault_read_range", "vault_automation_brief"]
                    missing = [name for name in required if name not in names]
                    if missing:
                        raise SystemExit(f"missing tools: {{missing}} from {{names}}")
                    search = await session.call_tool("vault_search", {{"query": "install smoke runbook", "limit": 3}})
                    search_text = search.content[0].text
                    if "Install Smoke Runbook" not in search_text:
                        raise SystemExit(search_text)
                    search_rows = json.loads(search_text)
                    knowledge_id = int(search_rows[0]["id"])
                    read_range = await session.call_tool("vault_read_range", {{"knowledge_id": knowledge_id, "line_start": 1, "line_end": 1}})
                    read_text = read_range.content[0].text
                    if "bounded lines" not in read_text:
                        raise SystemExit(read_text)
                    print(json.dumps({{"tool_count": len(names), "tools": names}}))

        anyio.run(main)
        """
    )
    output = _run([ctx["python"], "-c", script], cwd=project, env=ctx["env"])
    return json.loads(output) if output.startswith("{") else {"output": output}


def _find_default_wheel() -> Path | None:
    wheels = sorted((REPO_ROOT / "dist").glob("vault_for_llm-*.whl"))
    if not wheels:
        return None
    return wheels[-1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Vault-for-LLM install smoke matrix")
    parser.add_argument("--mode", choices=["source", "wheel", "both"], default="source")
    parser.add_argument("--wheel", type=Path, help="wheel file to install for wheel mode")
    parser.add_argument(
        "--venv-python",
        default=sys.executable,
        help="Python executable used to create the wheel-install virtual environment",
    )
    parser.add_argument("--keep-temp", action="store_true", help="keep temporary project dirs for debugging")
    parser.add_argument("--json", action="store_true", help="print machine-readable result")
    args = parser.parse_args()

    temp_ctx = tempfile.TemporaryDirectory(prefix="vault-install-smoke-")
    temp_dir = Path(temp_ctx.name)
    if args.keep_temp:
        temp_ctx.cleanup = lambda: None  # type: ignore[method-assign]

    contexts: list[dict[str, Any]] = []
    if args.mode in {"source", "both"}:
        contexts.append(_prepare_source_env(temp_dir))
    if args.mode in {"wheel", "both"}:
        wheel = args.wheel or _find_default_wheel()
        if not wheel or not wheel.exists():
            raise SystemExit("Wheel mode needs --wheel or an existing dist/vault_for_llm-*.whl")
        contexts.append(_prepare_wheel_env(wheel.resolve(), temp_dir, venv_python=args.venv_python))

    results = []
    for ctx in contexts:
        cli = _exercise_cli(ctx)
        mcp = _exercise_mcp(ctx)
        results.append({"mode": ctx["name"], "cli": cli, "mcp": mcp})

    payload = {
        "status": "passed",
        "temp_dir": str(temp_dir),
        "modes": [item["mode"] for item in results],
        "results": results,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("Install smoke matrix: PASS")
        print(f"  temp_dir: {temp_dir}")
        print(f"  modes: {', '.join(payload['modes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
