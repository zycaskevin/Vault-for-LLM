# Decision Record: Split CLI Semantic Command Helpers

Date: 2026-06-25

## Context

`vault/cli.py` still owns many command handlers, so small semantic workflow changes require reviewers to inspect a very large file. The semantic command group is a good split candidate because it has a clear boundary: semantic index lifecycle commands, provider construction, cache payloads, and search-QA query warming.

## Decision

Move semantic CLI helpers into `vault.cli_semantic` while keeping compatibility imports in `vault.cli`.

The moved surface includes:

- `cmd_semantic`
- `_create_semantic_provider`
- `_load_unique_qa_queries`
- `_semantic_vectors_exist`
- `_semantic_stats_payload`
- `_persistent_cache_payload`
- `_close_provider`

## Expected Impact

- Smaller review surface for future CLI and semantic-index changes.
- No change to command-line behavior.
- No new runtime dependency, model-loading path, remote call, or memory mutation behavior.

## Follow-Up

Continue splitting large modules around stable command or workflow boundaries before adding new automation features. Public import compatibility should be preserved unless a major version explicitly changes it.
