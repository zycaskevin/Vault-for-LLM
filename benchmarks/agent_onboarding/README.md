# Agent onboarding benchmark fixtures

This directory contains public-safe fixtures for comparing exported agent
sessions with governed Vault project memory.

The fixtures intentionally do not include real Hermes, Codex, Claude, or user
session exports. Bring those from your own machine at run time and keep reports
outside the repository.

- `project_onboarding.repo.json` - 28 Search QA cases for the repository-doc
  onboarding benchmark.
- `session_candidates.example.json` - candidate-memory examples for the
  candidate-first gate check.

## Build the repository-doc Vault

Create a temporary Vault database from the current source checkout:

```bash
python scripts/build_agent_onboarding_vault.py \
  --output-dir /tmp/vault-agent-onboarding
```

The builder writes a local SQLite database and manifest under the output
directory. It parses the selected README/docs files into Document Map nodes so
Search QA can measure `read_range` guidance.

## Run with a real exported session

Pass one or more exported session files:

```bash
python scripts/agent_onboarding_benchmark.py \
  --provider codex \
  --session-file /path/to/codex-session.jsonl \
  --qa-file benchmarks/agent_onboarding/project_onboarding.repo.json \
  --db-path /tmp/vault-agent-onboarding/repo-docs-vault.db \
  --candidate-file benchmarks/agent_onboarding/session_candidates.example.json \
  --output /tmp/vault-agent-onboarding/report.json
```

This compares what the exported session text contains against what the governed
Vault can retrieve from project source-of-truth documents. It is not a test of
hidden runtime memory internals.

## Hermes exports

Hermes exports should be passed as local `.md`, `.txt`, `.json`, or `.jsonl`
files with `--session-file`. Keep those exports outside git unless they have
been explicitly scrubbed. The benchmark runner reads text-like fields from JSON
and JSONL exports, so a Hermes transcript export can use fields such as
`content`, `text`, `message`, `summary`, `body`, or `transcript`.

## Reference results

Private local exports have been used to validate the fixture without committing
session transcripts or generated reports:

| Provider export | Transcript baseline | Vault top-k | Vault source hit | Vault read-range guidance | Delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| Codex local review sessions | `7/28` | `28/28` | `1.0` | `1.0` | `+0.75` |
| Hermes profile session export | `3/28` | `28/28` | `1.0` | `1.0` | `+0.892857` |

For both runs, `candidate_active_delta_before_promotion` stayed `0`.
