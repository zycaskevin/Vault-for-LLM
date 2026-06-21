# Document Tree Navigation Design

This design adapts PageIndex-style tree navigation to Vault-for-LLM without
turning Vault into a PDF RAG system.

## Goal

Let agents navigate long or structured project documents the way a careful
human would:

```text
search for likely source
  -> inspect document tree
  -> choose heading or node
  -> read bounded range
  -> answer with citation
```

## Existing Building Blocks

Vault already has most of the substrate:

- Markdown source files under `raw/`.
- compiled SQLite knowledge rows.
- Document Map nodes with headings and line ranges.
- `vault map show`.
- `vault map read`.
- MCP `vault_read_range`.

The missing piece is a more explicit agent-facing navigation contract.

## Proposed Retrieval Flow

### Stage 1: Source Recall

Use existing `vault_search` to find likely knowledge entries. Results should
remain compact and navigational:

- title
- category/layer/trust
- best claim
- source path
- document-map availability
- recommended next tool

### Stage 2: Tree Inspection

Expose a compact tree view for the selected document:

```text
#12 README.md
  1. Installation L240-L293
    1.1 Install from PyPI L243-L268
    1.2 Optional semantic search L270-L282
  2. Common CLI Commands L430-L461
```

This can be implemented with existing Document Map data first. No new storage
engine is required for the initial version.

### Stage 3: Bounded Read

The agent reads only the relevant node or line range:

```bash
vault map read 12 --node node_install_pypi
```

or, through MCP:

```text
vault_read_range({knowledge_id: 12, node_uid: "node_install_pypi"})
```

### Stage 4: Answer With Source

The answer should cite the bounded read, not the search result.

## CLI Shape

Candidate commands:

```bash
vault map tree <knowledge_id> --compact
vault map tree <knowledge_id> --depth 2
vault search "install from PyPI" --show-tree
```

The first implementation can alias or format existing `map show` output. The
important part is the agent contract, not a new database table.

## MCP Shape

Keep `core` small. Possible profile strategy:

| Profile | Tools |
|---|---|
| `core` | `vault_search`, `vault_read_range`, `vault_memory_propose`, `vault_stats` |
| `review` | core plus memory promotion and dream report |
| `maintenance` | review plus Obsidian import, freshness, convergence |
| future `navigation` | core plus explicit tree/map tools if token cost is acceptable |

For now, prefer improving response fields and docs before adding more MCP tools.

## Search QA

Add fixtures where success requires tree navigation:

- Query asks for a specific setup detail inside README.
- Expected source includes the document path and heading.
- Expected read range must sit inside the right node.
- Hard negative checks ensure old or generated Obsidian export pages are not
  treated as source of truth.

## Risks

- Too many MCP tools increase schema tokens.
- LLM reasoning over trees can be slower and nondeterministic.
- Tree-only retrieval can miss cross-document project facts.
- PDF-style parsing can make the project heavier than needed.

## Recommendation

Start with a small, local, Document Map-backed tree view. Measure it on
project-memory tasks before adding LLM-based tree reasoning or external PDF
parsers.
