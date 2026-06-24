# MCP Tool Reference

This page is the practical reference for connecting an MCP-capable agent to
Vault-for-LLM. For the policy behind the workflow, see
[`docs/mcp_memory_workflow.md`](mcp_memory_workflow.md).

## Pick A Profile

Start with the smallest profile. A smaller profile means fewer tool schemas in
the model context and fewer ways for an agent to choose the wrong action.

| Profile | Tools | Best For |
|---|---|---|
| `core` | `vault_search`, `vault_read_range`, `vault_memory_propose`, `vault_stats`, `vault_update_status`, `vault_automation_handoff` | Daily agent work: start from status/handoff, find memory, read bounded evidence, propose new memory. |
| `review` | Core plus `vault_memory_candidates`, `vault_memory_promote`, `vault_memory_review`, `vault_capture_discover`, `vault_capture_session`, `vault_automation_inbox`, `vault_dream_run` | A reviewer agent or operator session that discovers/captures, approves, rejects, or blocks candidate memories. |
| `remote` | Core plus `vault_remote_search`, `vault_remote_map_show`, `vault_remote_read_range` | Hosted or cross-host agents reading a Supabase-synced vault. |
| `maintenance` | Review plus Obsidian import, freshness, convergence, and curation tools | Scheduled maintenance or explicit operator-led cleanup. |
| `full` | Every MCP tool, including low-level compatibility tools | Trusted local operators and backwards compatibility. |

```bash
vault-mcp --project-dir ~/Vaults/project-memory --tool-profile core
```

Tool profiles reduce the exposed tool list. They are not a security boundary by
themselves. Use Vault read-policy fields and Supabase RLS/RPC for actual access
control.

## Default Agent Loop

Use this loop for normal project memory:

```text
vault_search -> vault_read_range -> answer with the returned citation
vault_memory_propose -> candidate created for later review
```

Search results are navigation hints. Final answers should cite only
`vault_read_range` output.

## Local Read Tools

### `vault_search`

Find likely memory entries.

```json
{
  "query": "release checklist",
  "limit": 5,
  "compact": true,
  "agent_id": "work-agent",
  "include_private": false,
  "max_sensitivity": "medium"
}
```

Typical result fields:

```json
{
  "id": 12,
  "title": "Release checklist",
  "summary": "Run tests, build, publish, and smoke check.",
  "recommended_next_tool": "vault_read_range",
  "next_action": {
    "tool": "vault_read_range",
    "arguments": {"knowledge_id": 12, "line_start": 8, "line_end": 22}
  }
}
```

Agent rule: call the `next_action` when present instead of reading the whole
entry.

### `vault_read_range`

Read bounded source text and return a stable citation.

```json
{
  "knowledge_id": 12,
  "line_start": 8,
  "line_end": 22,
  "agent_id": "work-agent",
  "include_private": false,
  "max_sensitivity": "medium"
}
```

Typical result fields:

```json
{
  "entry_id": 12,
  "range": "L8-L22",
  "citation": "#12 Release checklist L8-L22",
  "content": "8|Run tests...\n9|Build distributions..."
}
```

Agent rule: use the exact `citation` value when relying on this evidence.

### `vault_stats`

Read a small health snapshot. This is safe for daily agents and useful for
setup smoke tests.

```json
{}
```

### `vault_update_status`

Read local startup state: installed version, optional update hint, registered
agents, shared/private vault paths, and suggested startup handoff commands.

```json
{
  "latest_version": "",
  "check_pypi": false,
  "read_status": false,
  "agent_id": "",
  "write_status": false
}
```

Agent rule: keep `check_pypi=false` during normal startup unless the user asks
for a live update check. Prefer `read_status=true` first when another local
runtime may already have written `~/.vault-for-llm/update-status.json`. Keep
`write_status=false` unless a durable local status file is needed. Pass
`agent_id` when the runtime wants `current_agent_notice` and `startup_checklist`
for itself.

### `vault_automation_handoff`

Read the latest compact automation handoff for this project. It only reads
existing files under `reports/automation` and does not read raw transcript
contents or mutate memory.

```json
{
  "source": "auto",
  "handoff_path": ""
}
```

Agent rule: call this at startup before reading full reports. If it returns
`status=missing`, continue with normal search/read flow or run the CLI
automation cycle only after user approval.

## Candidate Memory Tools

### `vault_memory_propose`

Create a candidate memory. This is the recommended write path for autonomous
agents.

```json
{
  "title": "Release smoke test rule",
  "content": "After publishing a release, install from PyPI in a clean virtual environment before calling the release done.",
  "reason": "This prevents source-checkout-only validation from hiding package issues.",
  "layer": "L2",
  "category": "workflow",
  "tags": "release,smoke-test",
  "scope": "project",
  "sensitivity": "low",
  "owner_agent": "work-agent"
}
```

Typical result fields:

```json
{
  "status": "candidate_created",
  "candidate_id": "mem_...",
  "gates": {
    "privacy": "pass",
    "duplicate": "pass",
    "metadata": "pass",
    "quality": "pass"
  }
}
```

Agent rule: do not claim this memory is active until a reviewer promotes it.

### `vault_memory_candidates`

List pending candidates. This is in `review`, `maintenance`, and `full`, not
`core`.

```json
{
  "status": "candidate",
  "limit": 20,
  "include_content": false,
  "include_gates": true
}
```

### `vault_memory_promote`

Promote a reviewed candidate into active knowledge.

```json
{
  "candidate_id": "mem_...",
  "confirm": true,
  "compile": true,
  "build_map": true
}
```

Agent rule: only reviewer/operator agents should receive this tool.

### `vault_memory_review`

Record a rejected or blocked review outcome without promoting memory.

```json
{
  "candidate_id": "mem_...",
  "outcome": "rejected",
  "reason": "Too vague for durable project memory."
}
```

Typical result fields:

```json
{
  "status": "rejected",
  "candidate_id": "mem_...",
  "score": 0.0
}
```

Agent rule: use this when a candidate should become feedback for automation
learning but should not enter active knowledge.

### `vault_capture_discover`

Find likely agent session transcript exports without reading transcript
contents. Use this before `vault_capture_session` when the path is unknown.

```json
{
  "search_dirs": ["sessions", "exports"],
  "source_system": "auto",
  "limit": 10,
  "max_depth": 3,
  "max_file_mb": 5.0
}
```

Typical result fields:

```json
{
  "action": "discover_session_transcripts",
  "read_contents": false,
  "transcripts": [
    {
      "capture_path": "sessions/codex-session.jsonl",
      "source_system": "codex",
      "format": "jsonl",
      "score": 0.9
    }
  ]
}
```

By default, search directories are resolved under the current Vault project.
External absolute search directories require `allow_absolute_paths=true`.

### `vault_capture_session`

Extract reviewable candidate memories from an agent session transcript. This is
the MCP version of `vault capture session`: it previews by default and never
promotes active knowledge.

```json
{
  "transcript_path": "codex-session.jsonl",
  "format": "auto",
  "source_system": "codex",
  "agent_id": "codex",
  "write_candidates": false,
  "max_candidates": 20,
  "min_score": 0.55
}
```

Typical result fields:

```json
{
  "action": "capture_session",
  "status": "completed",
  "write_candidates": false,
  "extracted": 2,
  "written": 0,
  "safety": {
    "candidate_first": true,
    "auto_promote": false,
    "privacy_gate": true
  }
}
```

By default, relative transcript paths are resolved under the current Vault
project directory. Absolute paths require `allow_absolute_path=true`; use this
only when the user explicitly points the agent at an exported transcript.

### `vault_automation_inbox`

Read the compact automation review queue. This tool is available in the
`review`, `maintenance`, and `full` MCP tool profiles, but not in `core`.

```json
{
  "limit": 5,
  "include_content": false,
  "include_transcripts": false,
  "transcript_limit": 5,
  "write_handoff": false
}
```

Typical result fields:

```json
{
  "action": "inbox",
  "summary": {
    "pending_candidates": 3,
    "privacy_blocked": 1,
    "needs_review": 4,
    "uncaptured_transcripts": 1
  },
  "review_queue": [
    {
      "id": "mem_...",
      "recommended_action": "block_or_redact",
      "reason": "Privacy gate failed..."
    }
  ]
}
```

Agent rule: call this before reading full automation reports. It is read-only by
default and hides candidate content unless `include_content` is explicitly set.
Set `include_transcripts=true` when the agent also needs metadata-only hints for
session exports that have not yet been captured.

## Remote Supabase Tools

Remote tools are for a Supabase-synced read replica. Local SQLite remains the
source of truth.

Use this sequence:

```text
vault_remote_search -> vault_remote_map_show -> vault_remote_read_range
```

### `vault_remote_search`

```json
{
  "query": "deployment",
  "agent_id": "remote-agent",
  "include_private": false,
  "max_sensitivity": "medium",
  "limit": 5,
  "compact": true
}
```

This calls the guarded `vault_search_readable` RPC and returns metadata and
summaries only.

### `vault_remote_map_show`

```json
{
  "knowledge_id": "a4c5294e-239c-4b1f-a0d8-afa82ef43031",
  "compact": true,
  "agent_id": "remote-agent",
  "include_private": false,
  "max_sensitivity": "medium"
}
```

Use the `id` returned by `vault_remote_search` directly. Depending on the
Supabase schema, this may be a local integer ID or a UUID.

This requires the guarded Supabase RPCs from
[`docs/supabase_read_policy.sql`](supabase_read_policy.sql). Reapply that SQL
after upgrading to v0.6.61 or newer if your remote IDs are UUIDs.

### `vault_remote_read_range`

```json
{
  "knowledge_id": "a4c5294e-239c-4b1f-a0d8-afa82ef43031",
  "node_uid": "deployment-checklist",
  "agent_id": "remote-agent",
  "include_private": false,
  "max_sensitivity": "medium"
}
```

Remote read returns bounded content only after the same read policy allows the
entry. Use the same `knowledge_id` value from search/map; do not coerce UUIDs
into integers.

## Maintenance Tools

Use these only in operator or scheduled maintenance sessions.

| Tool | Use |
|---|---|
| `vault_dream_run` | Report-first memory curation. It should not delete memory automatically. |
| `vault_freshness` | Find stale entries that need review. |
| `vault_converge` | Find weak or incomplete knowledge areas. |
| `vault_obsidian_import` | Import an Obsidian vault after user confirmation. |

## Low-Level Compatibility Tools

`vault_add` writes directly to active knowledge. Keep it for trusted scripts and
manual operator sessions. Autonomous agents should use `vault_memory_propose`
instead.

## Common Mistakes

| Mistake | Better Pattern |
|---|---|
| Giving every agent the `full` profile. | Start with `core`; add `review`, `remote`, or `maintenance` only when needed. |
| Treating search snippets as final citations. | Call `vault_read_range` and cite the returned range. |
| Letting daily agents promote memory. | Give promotion tools only to reviewer/operator agents. |
| Exposing local MCP over a public network. | Use local stdio MCP only; use Supabase RPC for cross-host readers. |
| Giving hosted agents a Supabase service role key. | Use anon/authenticated keys plus guarded RPC/RLS policies. |

## Minimal Agent Instruction

Paste this into an agent system or project instruction when you need a short
policy:

```text
Use Vault-for-LLM through the smallest available MCP profile.
Search before answering. Treat search snippets as navigation hints only.
Use vault_read_range for final evidence and cite its returned citation exactly.
Use vault_memory_propose for new lessons; do not use direct writes unless the
user explicitly asks. Do not promote candidate memory unless acting as a
reviewer/operator. Pass agent_id and max_sensitivity when the vault is shared.
```
