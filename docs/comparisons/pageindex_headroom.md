# PageIndex And Headroom Comparison

This note compares Vault-for-LLM with PageIndex-style document retrieval and
Headroom-style context compression. It is not a benchmark. It is a product and
architecture positioning note for future work.

## Short Answer

Vault-for-LLM should borrow ideas from both projects, but it should not become
either of them.

- PageIndex is useful inspiration for **document tree navigation**.
- Headroom is useful inspiration for a **context budget and reversible
  compression layer**.
- Vault-for-LLM should stay focused on **local-first project memory governance**:
  candidate review, source of truth, bounded reads, Search QA, backup/restore,
  and agent-friendly install paths.

## What They Optimize For

| System | Primary problem | Primary method | Best fit |
|---|---|---|---|
| PageIndex | Long professional documents are hard to search accurately. | Build a hierarchical tree index and let an LLM navigate it through reasoning. | PDFs, filings, manuals, papers, contracts, long SOPs. |
| Headroom | Agents waste context on verbose tool outputs, logs, files, and RAG chunks. | Compress before content reaches the LLM, while keeping originals retrievable. | Coding agents, log/debug sessions, large tool outputs, repeated context. |
| Vault-for-LLM | Agents forget project decisions and may write messy or unsafe memory. | Governed Markdown/SQLite project memory with search, bounded reads, candidates, QA, and recovery. | Multi-agent project memory, repo docs, decisions, pitfalls, onboarding, operations. |

## What Vault Should Borrow From PageIndex

PageIndex's strongest lesson is that document structure is retrieval signal.
Its public README describes a vectorless, reasoning-based RAG system that builds
a hierarchical tree index from long documents and retrieves through tree search
rather than vector similarity.

Vault already has a compatible foundation:

- Markdown headings and file paths.
- Document Map nodes.
- `vault map show` and bounded `vault map read`.
- Search results that should be treated as navigation hints, not final
  evidence.

Good next steps for Vault:

1. Promote Document Map into a first-class tree navigation workflow.
2. Add agent guidance like `search -> map/tree -> read_range -> cite`.
3. Add Search QA cases that require finding the right heading before the right
   line range.
4. Keep this local and SQLite-backed; do not add a PDF-heavy pipeline to core.

Non-goals:

- Do not replace Vault's project memory model with PDF RAG.
- Do not require LLM tree reasoning for every local search.
- Do not make vectorless retrieval a slogan; measure it on Vault's own
  project-memory tasks.

## What Vault Should Borrow From Headroom

Headroom's strongest lesson is that the LLM should not see everything raw.
Its public README and PyPI page describe local-first compression for tool
outputs, logs, RAG chunks, files, and conversations, with library, proxy, and
MCP modes plus reversible retrieval of originals.

Vault already shares the same design instinct:

- `compact=true` MCP defaults.
- Bounded reads instead of full-document dumping.
- Candidate-first memory rather than automatic active writes.
- Search QA and source-aware retrieval checks.

Good next steps for Vault:

1. Add an explicit context budget concept to search and MCP responses.
2. Return compact summaries with stable source handles.
3. Let agents fetch original ranges only when needed.
4. Document how to use Headroom alongside Vault instead of embedding a
   compressor into core.

Non-goals:

- Do not train or bundle a compression model in Vault core.
- Do not make compressed text a citation source; final claims still need
  bounded source reads.
- Do not hide source fidelity behind token-saving claims.

## Integration Direction

The clean layering is:

```text
Vault governance/search/read_range
  -> optional compression/budget layer
  -> LLM answer with bounded citations
```

For PageIndex-like workflows:

```text
Vault Document Map
  -> tree navigation
  -> bounded range read
  -> answer with source
```

For Headroom-like workflows:

```text
Vault compact search results
  -> Headroom compression if configured
  -> retrieve original Vault range when needed
```

## Product Positioning

The external message should be:

> PageIndex shows why structure-aware retrieval matters. Headroom shows why
> context should be budgeted before it reaches the LLM. Vault-for-LLM applies
> both ideas to governed project memory: find the right source, read only the
> bounded range, propose before storing, and keep the memory recoverable.

## Sources Checked

- PageIndex repository: <https://github.com/VectifyAI/PageIndex>
- PageIndex MCP repository: <https://github.com/VectifyAI/pageindex-mcp>
- Headroom repository: <https://github.com/chopratejas/headroom>
- Headroom PyPI package: <https://pypi.org/project/headroom-ai/>
