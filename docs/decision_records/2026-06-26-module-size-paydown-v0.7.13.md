# Module Size Paydown v0.7.13

## Context

v0.7.12 intentionally touched `vault/cli.py`, `vault/mcp.py`, and
`vault/search.py` to close review findings around temporal recall, graph ACL,
Base64 privacy gates, and signed MCP identity. The v0.7.12 decision record
accepted a short-term module-size increase but named the next split direction.

## Decision

v0.7.13 implements that split without changing public behavior:

- `vault/mcp_search.py` owns MCP search field allow-lists, limit clamping, and
  compact/full search result shaping.
- `vault/cli_search.py` owns CLI temporal search options and conversion into
  `VaultSearch.search()` keyword arguments.
- `vault/search_graph.py` owns graph expansion recall and keeps read-policy
  filtering before a neighbor can enter results.

## Result

The large-module baseline is tightened after the split:

- `vault/cli.py`: 3280 -> 3277 lines
- `vault/mcp.py`: 1581 -> 1475 lines
- `vault/search.py`: 2603 -> 2569 lines

This is a first paydown, not the final architecture. Future work should keep
new MCP tools, CLI subcommands, and recall strategies in focused modules before
they inflate the central routers again.

## Safety

The refactor is behavior-preserving:

- temporal search flags still pass through CLI and MCP,
- graph-expanded memories still honor the same governance read policy,
- the historical `VaultSearch._apply_graph_expand()` private test hook remains
  as a thin compatibility wrapper,
- MCP compact/full search payloads keep the same fields, including temporal
  metadata,
- signed MCP identity remains enforced by `vault/mcp_security.py`.
