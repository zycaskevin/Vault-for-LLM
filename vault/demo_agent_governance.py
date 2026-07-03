"""Agent memory governance demo helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import tempfile
from pathlib import Path
from typing import Any

from .db import VaultDB
from .db_backup import backup_database
from .mcp_read import _vault_read_range_payload
from .memory import promote_candidate, propose_memory
from .search import VaultSearch


DEFAULT_DEMO_AGENTS = ["codex", "claude-code", "hermes"]


def run_agent_governance_demo(
    *,
    project_dir: str | Path | None = None,
    agent_set: str | list[str] | tuple[str, ...] = DEFAULT_DEMO_AGENTS,
    keep_project: bool = False,
) -> dict[str, Any]:
    """Run a local, candidate-first multi-agent memory governance demo."""
    project, created_temp = _resolve_demo_project(project_dir)
    agents = _normalize_agents(agent_set)
    codex, claude_code, hermes = agents[:3]
    _ensure_demo_project(project)

    db_path = project / "vault.db"
    with VaultDB(db_path) as db:
        candidate = propose_memory(
            db,
            title="Agent governance demo lesson",
            content=_demo_memory_content(),
            reason="Show that shared agent memory should be reviewed before it becomes active knowledge.",
            source="demo",
            source_ref="demo://agent-governance/codex-session",
            layer="L3",
            category="workflow",
            tags="demo,agent-governance,shared-memory",
            trust=0.8,
            scope="shared",
            sensitivity="low",
            owner_agent=codex,
            allowed_agents=json.dumps([codex, claude_code, hermes]),
            memory_type="project_lesson",
        )
        candidate_id = str(candidate["candidate_id"])

        promoted = promote_candidate(
            db,
            candidate_id,
            confirm=True,
            project_dir=project,
            compile=False,
            build_map=True,
        )
        knowledge_id = int(promoted["knowledge_id"])

        backup = backup_database(db_path, verify=True)

        search_rows = VaultSearch(db, embed_provider=None, embed_provider_name="none").search(
            "agent memory governance rollback audit",
            mode="keyword",
            limit=5,
            compact=True,
            include_snippet=True,
            fields=["id", "title", "category", "layer", "trust", "_score", "_snippet", "source"],
            agent_id=hermes,
            max_sensitivity="low",
        )
        search_hit = next((row for row in search_rows if int(row.get("id", 0)) == knowledge_id), None)
        audit_events = db.list_memory_feedback(limit=20)

    read_range = _vault_read_range_payload(
        knowledge_id,
        line_start=1,
        line_end=8,
        max_lines=20,
        agent_id=hermes,
        max_sensitivity="low",
        db_path=str(db_path),
    )

    artifacts = _write_demo_artifacts(
        project=project,
        agents=agents,
        candidate_id=candidate_id,
        knowledge_id=knowledge_id,
        search_hit=search_hit,
        read_range=read_range,
        audit_events=audit_events,
        backup=backup,
        created_temp=created_temp,
        keep_project=keep_project,
    )

    return {
        "ok": True,
        "status": "ok",
        "scenario": "agent_memory_governance",
        "message": "Vault governs what agents remember, trust, cite, and can roll back.",
        "project_dir": str(project),
        "temporary_project": created_temp,
        "keep_project": bool(keep_project),
        "agents": [
            {"id": codex, "role": "proposer", "action": "proposed a reusable project lesson"},
            {"id": claude_code, "role": "reviewer", "action": "promoted the candidate after gates passed"},
            {"id": hermes, "role": "recaller", "action": "searched and bounded-read the promoted memory"},
        ],
        "lifecycle": [
            "propose",
            "review",
            "promote",
            "search",
            "bounded_read",
            "rollback_available",
            "audit",
        ],
        "candidate_id": candidate_id,
        "promoted_knowledge_id": knowledge_id,
        "search_hit": search_hit or {},
        "read_range_citation": read_range.get("citation", ""),
        "audit_events": _compact_audit_events(audit_events),
        "rollback_available": bool(backup.get("ok")),
        "rollback": {
            "backup_path": backup.get("backup_path", ""),
            "sha256": backup.get("sha256", ""),
            "verified": bool(backup.get("verified")),
        },
        "artifacts": artifacts,
        "next_action": [
            "Open demo-report.md to explain why this is memory governance, not just RAG.",
            "Copy the runtime snippets into Codex, Claude Code, and Hermes startup configs when running the real demo.",
            "Use the same lifecycle in public demos: propose -> review -> promote -> bounded read -> rollback/audit.",
        ],
    }


def _resolve_demo_project(project_dir: str | Path | None) -> tuple[Path, bool]:
    if project_dir:
        return Path(project_dir).expanduser().resolve(), False
    return Path(tempfile.mkdtemp(prefix="vault-agent-governance-demo-")).resolve(), True


def _ensure_demo_project(project: Path) -> None:
    for name in ["raw", "compiled", "reports/demo", "agent-config-snippets"]:
        (project / name).mkdir(parents=True, exist_ok=True)
    with VaultDB(project / "vault.db") as db:
        db.set_config("demo.agent_governance.created_at", datetime.now(timezone.utc).isoformat())


def _normalize_agents(agent_set: str | list[str] | tuple[str, ...]) -> list[str]:
    if isinstance(agent_set, str):
        agents = [item.strip() for item in agent_set.split(",") if item.strip()]
    else:
        agents = [str(item).strip() for item in agent_set if str(item).strip()]
    for default in DEFAULT_DEMO_AGENTS:
        if len(agents) >= 3:
            break
        agents.append(default)
    return agents[:3]


def _demo_memory_content() -> str:
    return "\n".join(
        [
            "# Agent Memory Governance Demo",
            "",
            "Decision: shared agent memory must enter Vault as a candidate before it becomes active knowledge.",
            "",
            "Why it matters:",
            "- Codex can propose a reusable lesson without silently polluting shared memory.",
            "- Claude Code can review and promote only if privacy, duplicate, metadata, and quality gates pass.",
            "- Hermes can later recall the reviewed memory with a bounded source citation.",
            "- Operators can audit who proposed the memory and keep a verified backup for rollback.",
        ]
    )


def _write_demo_artifacts(
    *,
    project: Path,
    agents: list[str],
    candidate_id: str,
    knowledge_id: int,
    search_hit: dict[str, Any] | None,
    read_range: dict[str, Any],
    audit_events: list[dict[str, Any]],
    backup: dict[str, Any],
    created_temp: bool,
    keep_project: bool,
) -> dict[str, str]:
    reports = project / "reports" / "demo"
    snippets = project / "agent-config-snippets"
    reports.mkdir(parents=True, exist_ok=True)
    snippets.mkdir(parents=True, exist_ok=True)

    payload = {
        "ok": True,
        "scenario": "agent_memory_governance",
        "project_dir": str(project),
        "temporary_project": created_temp,
        "keep_project": keep_project,
        "agents": agents,
        "candidate_id": candidate_id,
        "promoted_knowledge_id": knowledge_id,
        "search_hit": search_hit or {},
        "read_range": {
            "citation": read_range.get("citation", ""),
            "range": read_range.get("range", ""),
            "content_hash": read_range.get("content_hash", ""),
        },
        "audit_events": _compact_audit_events(audit_events),
        "rollback": {
            "backup_path": backup.get("backup_path", ""),
            "sha256": backup.get("sha256", ""),
            "verified": bool(backup.get("verified")),
        },
    }
    json_path = reports / "demo-report.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = reports / "demo-report.md"
    md_path.write_text(_render_demo_markdown(payload), encoding="utf-8")

    script_path = reports / "public-demo-script.md"
    script_path.write_text(_render_public_demo_script(project, agents), encoding="utf-8")

    checklist_path = reports / "acceptance-checklist.md"
    checklist_path.write_text(_render_acceptance_checklist(), encoding="utf-8")

    snippet_paths = _write_agent_snippets(snippets, project, agents)
    return {
        "report_md": str(md_path),
        "report_json": str(json_path),
        "public_demo_script": str(script_path),
        "acceptance_checklist": str(checklist_path),
        "snippet_dir": str(snippets),
        **snippet_paths,
    }


def _render_demo_markdown(payload: dict[str, Any]) -> str:
    agents = payload["agents"]
    rollback = payload["rollback"]
    return "\n".join(
        [
            "# Agents Need Memory Governance, Not Just RAG",
            "",
            "This demo proves Vault-for-LLM is a governed memory layer for agents.",
            "It does not just retrieve notes. It controls how shared agent memory is proposed, reviewed, promoted, cited, backed up, and audited.",
            "",
            "## Lifecycle",
            "",
            "1. **Propose** - `{}` submitted a reusable lesson as a memory candidate.".format(agents[0]),
            "2. **Review** - `{}` promoted it only after gates passed.".format(agents[1]),
            "3. **Recall** - `{}` searched the shared vault and used bounded read before citing.".format(agents[2]),
            "4. **Rollback** - Vault created a verified backup before publishing the evidence.",
            "5. **Audit** - Candidate feedback events preserve who changed memory and why.",
            "",
            "## Evidence",
            "",
            f"- Candidate ID: `{payload['candidate_id']}`",
            f"- Promoted knowledge ID: `{payload['promoted_knowledge_id']}`",
            f"- Citation: `{payload['read_range']['citation']}`",
            f"- Backup verified: `{rollback['verified']}`",
            f"- Backup SHA256: `{rollback['sha256']}`",
            "",
            "## Why This Is Not Just RAG",
            "",
            "RAG can retrieve text. This demo shows a memory lifecycle:",
            "",
            "`propose -> review -> promote -> search -> bounded read -> rollback -> audit`",
            "",
            "That lifecycle is the difference between a memory database and an agent memory governance layer.",
            "",
        ]
    )


def _render_public_demo_script(project: Path, agents: list[str]) -> str:
    codex, claude_code, hermes = agents
    return "\n".join(
        [
            "# Public Demo Script: Governed Shared Memory",
            "",
            "Use this script when recording or presenting the demo. The goal is to show",
            "memory governance, not only search quality.",
            "",
            "## Setup",
            "",
            "```bash",
            f"vault demo agent-governance --project-dir {project} --json",
            "```",
            "",
            "Open:",
            "",
            f"- `{project / 'reports' / 'demo' / 'demo-report.md'}`",
            f"- `{project / 'agent-config-snippets'}`",
            "",
            "## Talk Track",
            "",
            "1. Introduce the problem: three agents can work on the same repo, but shared",
            "   memory becomes dangerous if every agent writes directly into active context.",
            f"2. `{codex}` proposes a lesson as a candidate. It exists, but it is not active",
            "   shared memory yet.",
            f"3. `{claude_code}` reviews and promotes the candidate only after gates pass.",
            f"4. `{hermes}` searches the shared vault, then uses bounded read before citing.",
            "5. Show the verified backup and audit events. The memory can be rolled back or",
            "   deprecated instead of silently lingering forever.",
            "",
            "## One-Sentence Close",
            "",
            "Vault is not another place for agents to dump notes. It is the governance",
            "layer that controls what agents remember, trust, share, forget, and roll back.",
            "",
        ]
    )


def _render_acceptance_checklist() -> str:
    return "\n".join(
        [
            "# Acceptance Checklist",
            "",
            "A public demo is successful when it proves these points:",
            "",
            "- [ ] A memory starts as a candidate, not active shared knowledge.",
            "- [ ] Gate and review steps are visible before promotion.",
            "- [ ] A different agent can search the promoted memory.",
            "- [ ] The answer path uses bounded read with a citation.",
            "- [ ] A verified backup or rollback path exists.",
            "- [ ] Audit events show the lifecycle, not just the final text.",
            "- [ ] The demo does not require private data, cloud services, or hidden state.",
            "- [ ] The talk track says \"memory governance\", not \"better RAG\".",
            "",
            "If any item fails, fix the demo before using it as an external proof.",
            "",
        ]
    )


def _write_agent_snippets(snippets: Path, project: Path, agents: list[str]) -> dict[str, str]:
    codex, claude_code, hermes = agents
    common = f"vault-mcp --project-dir {project} --tool-profile core"
    data = {
        "codex_startup": (
            "codex-startup.md",
            f"# Codex Startup\n\nUse shared Vault memory through MCP:\n\n```bash\n{common}\n```\n\n"
            f"Agent id: `{codex}`\n\nFlow: search first, bounded-read before citing, propose durable lessons as candidates.\n",
        ),
        "claude_code_startup": (
            "claude-code-startup.md",
            f"# Claude Code Startup\n\nUse shared Vault memory through MCP:\n\n```bash\n{common}\n```\n\n"
            f"Agent id: `{claude_code}`\n\nFlow: review candidate memory before promotion; keep active memory clean.\n",
        ),
        "hermes_startup": (
            "hermes-startup.md",
            f"# Hermes Startup\n\nUse shared Vault memory through MCP:\n\n```bash\n{common}\n```\n\n"
            f"Agent id: `{hermes}`\n\nFlow: recall reviewed memory with bounded citations; private identity memory stays outside shared Vault.\n",
        ),
    }
    written: dict[str, str] = {}
    for key, (filename, content) in data.items():
        path = snippets / filename
        path.write_text(content, encoding="utf-8")
        written[key] = str(path)
    return written


def _compact_audit_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for row in events:
        compact.append(
            {
                "id": row.get("id"),
                "created_at": row.get("created_at"),
                "event_type": row.get("event_type"),
                "candidate_id": row.get("candidate_id"),
                "outcome": row.get("outcome"),
                "source": row.get("source"),
                "memory_type": row.get("memory_type"),
                "knowledge_id": row.get("knowledge_id"),
            }
        )
    return compact
