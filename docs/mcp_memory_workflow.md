# MCP Memory Workflow

Vault-for-LLM now exposes a safer agent memory workflow over MCP. Autonomous agents should prefer candidate-first memory tools instead of writing directly to active knowledge.

## Tool profiles

Use the smallest MCP tool profile that fits the session:

| Profile | Tools | Use when |
|---|---|---|
| `core` | `vault_search`, `vault_read_range`, `vault_memory_propose`, `vault_stats` | Daily agent use with fewer tool-schema tokens |
| `review` | Core plus `vault_memory_promote`, `vault_dream_run` | Reviewing and promoting candidate memory |
| `remote` | Core plus `vault_remote_map_show`, `vault_remote_read_range` | Reading a Supabase-synced cross-host memory view |
| `maintenance` | Review plus Obsidian import and freshness/convergence checks | Scheduled or operator-led curation |
| `full` | All tools, including compatibility `vault_add` | Backward compatibility or explicit power-user setups |

```bash
vault-mcp --project-dir /path/to/project --tool-profile core
```

`full` remains the default for backward compatibility. Production agents should
prefer `core` unless they need review, remote, or maintenance tools.

Tool profiles reduce the tool schemas advertised to the client; they are not an
access-control boundary. Only run `vault-mcp` for agents you trust with the
selected project directory.

## Recommended agent flow

```text
1. vault_memory_propose  # candidate-first write with gates
2. human/agent review    # inspect privacy/duplicate/metadata gate result
3. vault_memory_promote  # explicit confirm=true promotion
4. vault_search          # find active memory later
5. vault_read_range      # read bounded source range and cite it
```

## Why not direct `vault_add`?

`vault_add` is still available for compatibility and controlled scripts, but it writes directly to active knowledge. It blocks obvious privacy failures and builds a Document Map when possible, but it still bypasses candidate review. For autonomous agents and unreviewed memories, use `vault_memory_propose` so the memory passes deterministic gates first.

## Tools

### `vault_obsidian_import`

Imports an existing Obsidian vault into `raw/obsidian/`. This tool is available
in `maintenance` and `full`, not `core`, so daily agent sessions keep a smaller
tool schema.

Run a preview first:

```json
{
  "vault_dir": "/path/to/ObsidianVault",
  "dry_run": true
}
```

After the user confirms the preview, apply and compile:

```json
{
  "vault_dir": "/path/to/ObsidianVault",
  "dry_run": false,
  "compile": true
}
```

### `vault_memory_propose`

Creates a memory candidate. It does not alter active knowledge unless `mode=promote_if_safe` is explicitly requested and gates allow it.

Required fields:

```json
{
  "title": "Short stable title",
  "content": "Markdown memory content",
  "reason": "Why this is worth remembering"
}
```

Optional fields:

```json
{
  "source": "mcp",
  "source_ref": "session or artifact reference",
  "layer": "L3",
  "category": "general",
  "tags": "sqlite,memory",
  "trust": 0.5,
  "mode": "candidate"
}
```

Return shape:

```json
{
  "status": "candidate_created",
  "candidate_id": "mem_...",
  "knowledge_id": null,
  "gates": {
    "privacy": "pass",
    "duplicate": "pass",
    "metadata": "pass",
    "quality": "pass"
  },
  "next_action": {
    "tool": "vault_memory_promote",
    "arguments": {"candidate_id": "mem_...", "confirm": true}
  }
}
```

### `vault_memory_promote`

Promotes a reviewed candidate into `raw/` plus active SQLite knowledge.

```json
{
  "candidate_id": "mem_...",
  "confirm": true,
  "compile": true,
  "build_map": true
}
```

Rules:

- `confirm=true` is required.
- Privacy and metadata gates are rerun.
- Privacy `fail` blocks promotion.
- Duplicate findings are surfaced but do not delete or merge automatically.
- A Markdown source file is written under `raw/`.
- Active knowledge is inserted or compiled and can then be searched/read.

## Citation-safe reading

Search snippets are navigation hints only. Final answers should cite ranges returned by `vault_read_range`, not `vault_search` snippets.

Required sequence:

```text
vault_search → vault_read_range → final answer citation
```

`vault_search` returns compact source and range hints when available.
`vault_read_range` returns a fixed citation string. Use that exact citation when
relying on the range. Use `vault_map_show` from a broader profile only when the
agent needs section navigation before choosing a range.

## Safety notes

- Candidate memories are intentionally lower trust by default.
- Secret-like content is blocked or warned by the deterministic privacy gate.
- Duplicate title/content matches, near duplicates, weak metadata, and weak quality are reported before promotion.
- Direct low-level writes should be reserved for trusted scripts and operators.
