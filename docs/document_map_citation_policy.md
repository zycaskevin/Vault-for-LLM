# Document Map citation policy

Document Map is the citation-safe path for using Vault-for-LLM memory in agent answers. It separates **finding a likely memory** from **reading the bounded source text that can be cited**.

## Policy

1. Treat `vault search` / `vault_search` results as navigation hints, not final proof.
2. Inspect the selected entry with `vault map show <id>` or MCP `vault_map_show` before relying on it.
3. Read bounded source text with `vault map read <id> --lines START-END` or MCP `vault_read_range`.
4. Final answers should cite only `read_range` output, not search previews or snippets.
5. Keep reads bounded. MCP `vault_read_range` defaults to a maximum of 80 lines per call.
6. If an entry has no map nodes, run `vault map build` and then inspect the map again.

Search previews can help choose where to look, but they may be truncated and should not be treated as stable evidence. `read_range` returns numbered source lines plus a stable citation such as `#1 Release checklist L5-L6`.

## CLI demo

The following demo uses a temporary local project and public-safe sample Markdown.

```bash
mkdir -p /tmp/vault-docmap-demo
cd /tmp/vault-docmap-demo

vault init

vault add "Release checklist" --content "# Release checklist

## Build
Run the test suite before packaging.

## Verify
Review bounded source ranges before writing final answers.
Cite only text returned by map read."

vault compile --no-embed
vault map build

# Search finds a candidate entry. Treat this as a pointer, not proof.
vault search "bounded source ranges" --keyword-only

# Inspect sections and line ranges.
vault map show 1

# Read only the source lines needed for a final answer.
vault map read 1 --lines 6-8
```

Example agent workflow:

1. Use `vault search "bounded source ranges" --keyword-only` to find candidate entry `#1`.
2. Use `vault map show 1` to choose a section and line range.
3. Use `vault map read 1 --lines 6-8` to retrieve source text and the citation.
4. Cite the `vault map read` citation in the final answer if those lines support the claim.

If `vault map show 1` reports that no document map nodes exist, run:

```bash
vault map build
vault map show 1
```

## MCP agent loop

For MCP-compatible agents, prefer this loop:

```json
{
  "tool": "vault_search",
  "arguments": {
    "query": "bounded source ranges",
    "mode": "keyword"
  }
}
```

`vault_search` is compact by default for MCP use. Compact results omit raw content blobs and are intended to guide the next call. A result may include `next_action` or `next_actions`, for example:

```json
{
  "tool": "vault_map_show",
  "arguments": {"knowledge_id": 1}
}
```

Then inspect the map:

```json
{
  "tool": "vault_map_show",
  "arguments": {"knowledge_id": 1, "compact": true}
}
```

Finally read the bounded source range:

```json
{
  "tool": "vault_read_range",
  "arguments": {
    "knowledge_id": 1,
    "line_start": 6,
    "line_end": 8
  }
}
```

Use the citation returned by `vault_read_range` in the final answer. Do not cite `vault_search` previews.

If the map response reports missing nodes, call the CLI maintenance command `vault map build` in the project and retry `vault_map_show`.

## Notes for agents

- Prefer small ranges that directly support the answer.
- If more context is required, make multiple bounded `read_range` calls instead of requesting a whole entry.
- If a search result has `compact: false`, any `content_preview` is still a preview and should not be cited.
- If `vault_read_range` rejects a range as too large, split it into smaller ranges and cite only the lines actually used.
