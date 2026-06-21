# Headroom Integration Notes

Headroom and Vault-for-LLM solve adjacent problems.

- Vault decides **what project memory should be retrieved, trusted, cited, and
  stored**.
- Headroom decides **how much retrieved/tool context should reach the LLM**.

Use them together when an agent retrieves useful Vault context but the final
prompt is still too large because it also includes logs, shell output, code
search results, or other tool output.

## Agent Installer Policy

Agent installers should offer Headroom as an advanced optional feature, not as a
default recommendation:

```bash
vault setup-agent \
  --non-interactive \
  --agent codex \
  --scope shared \
  --agent-project-dir /path/to/project \
  --features core,mcp,headroom \
  --json
```

The prompt should be framed as context compression for long logs, terminal
output, code search results, or large retrieved context. If the user only needs
project memory search, source citations, Obsidian import, or MCP access,
Headroom is unnecessary.

## Recommended Layering

```text
Vault search/read_range
  -> compact source-grounded context
  -> optional Headroom compression
  -> LLM
  -> retrieve original Vault range when exact citation is needed
```

Vault should remain the source of truth for citations. Compressed text can help
the model navigate, but final claims should still be grounded in bounded Vault
reads.

## When To Use Headroom

Use Headroom when:

- The agent is reading large logs or code-search output.
- The agent combines Vault results with long terminal output.
- The agent repeatedly hits context limits.
- Token cost matters more than preserving every raw token in the prompt.

Do not use it as a substitute for:

- Vault Search QA.
- privacy gates.
- candidate memory review.
- backup/restore.
- source citations.

## MCP Strategy

If both tools are available through MCP, keep their responsibilities separate:

```text
vault_search        -> find source candidates
vault_read_range    -> read exact source evidence
headroom_compress   -> compress bulky non-citation context
headroom_retrieve   -> recover original compressed content when needed
```

Avoid compressing final source evidence before citation. If compression is used,
store the Vault citation handle next to the compressed text so the agent can
retrieve the original range.

## CLI Strategy

For shell-capable agents, a simple operator workflow is:

```bash
vault search "deployment gotcha" --project-dir /path/to/project --limit 5
vault map read <id> --lines 40-80 --project-dir /path/to/project
```

Then send large non-Vault context, such as logs or command output, through
Headroom if installed.

## Future Vault Features

Potential Vault-side additions:

- `vault search --budget <tokens>` for explicit compact response budgets.
- MCP response metadata that marks fields as `citation_safe` or
  `navigation_only`.
- Optional integration docs for Headroom proxy and MCP setup.
- A Search QA mode that measures token budget, source hit rate, and bounded
  read guidance together.

## Safety Notes

- Do not treat compressed summaries as source citations.
- Do not compress secrets into memory; keep privacy gates before memory writes.
- Do not require Headroom for core Vault usage.
- Keep Headroom as an optional integration, not a core dependency.

## Source

- Headroom repository: <https://github.com/chopratejas/headroom>
- Headroom PyPI package: <https://pypi.org/project/headroom-ai/>
