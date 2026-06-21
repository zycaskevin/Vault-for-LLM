# Agent Onboarding Benchmark

The project-memory proof demos show the workflow on controlled fixtures. The next step is to compare Vault-for-LLM against exported agent sessions from tools such as Hermes or Codex.

`scripts/agent_onboarding_benchmark.py` does that comparison locally:

- **Session baseline:** searches exported session text, Markdown, JSON, or JSONL.
- **Vault baseline:** runs the same onboarding questions through source-aware Search QA.
- **Candidate-first check:** optionally gates candidate memories extracted from the session.
- **Wrong-source check:** keeps the stale-title bounded-read proof in the same report.

The benchmark is deterministic and local. It does not call an LLM, Hermes, Codex, Supabase, embeddings, or network services.

## Quick Demo

Run without arguments to use a public-safe Codex-like fixture:

```bash
python scripts/agent_onboarding_benchmark.py \
  --output /tmp/vault-agent-onboarding-benchmark.json
```

Expected demo summary:

```json
{
  "session_hit_rate": 0.4,
  "vault_topk_hit_rate": 1.0,
  "vault_source_hit_rate": 1.0,
  "vault_read_range_guidance_rate": 1.0,
  "topk_hit_rate_delta": 0.6,
  "candidate_active_delta_before_promotion": 0,
  "wrong_source_guard_passed": true
}
```

This means the exported session transcript contains enough information for 2 of 5 onboarding questions, while the governed Vault fixture answers all 5 with source-aware retrieval and bounded-read guidance.

## Run Against A Real Session Export

Prepare three inputs:

1. A Hermes/Codex session export, such as `.md`, `.txt`, `.json`, or `.jsonl`.
2. A Search QA file with the onboarding questions.
3. A `vault.db` that contains the governed project memory.

For a repository-doc benchmark that is safe to commit, build the Vault database
from the current source checkout and keep the generated database/report in
`/tmp`:

```bash
python scripts/build_agent_onboarding_vault.py \
  --output-dir /tmp/vault-agent-onboarding \
  --force
```

Then run the exported-session comparison:

Example:

```bash
python scripts/agent_onboarding_benchmark.py \
  --provider codex \
  --session-file /path/to/codex-session.md \
  --qa-file benchmarks/agent_onboarding/project_onboarding.repo.json \
  --db-path /tmp/vault-agent-onboarding/repo-docs-vault.db \
  --candidate-file benchmarks/agent_onboarding/session_candidates.example.json \
  --output /tmp/codex-vs-vault-onboarding.json
```

You can pass `--session-file` more than once. The runner will merge the exported text into transcript chunks.

Real session exports and benchmark reports may contain private work context.
Keep them outside the repository unless they have been explicitly scrubbed.

## QA Case Shape

The benchmark uses the regular Search QA fields for the Vault side:

```json
{
  "id": "release_quality_commands",
  "query": "publishing release full pytest py_compile readme smoke search qa parity",
  "expected_sources": ["docs/runbooks/release-quality-gate.md"],
  "expected_title_substrings": ["Release", "Quality"],
  "expected_session_substrings": [
    "full pytest",
    "py_compile",
    "README command smoke"
  ]
}
```

`expected_session_substrings` tells the transcript baseline what evidence would count as a session hit. If it is omitted, the runner falls back to expected source/title fields, which is stricter and often less useful for chat transcripts.

## Candidate-First Input

If you extract candidate memories from a real agent session, save them as JSON:

```json
{
  "candidates": [
    {
      "title": "Release rollback SOP",
      "content": "Rollback requires a verified SQLite backup before reverting a release.",
      "reason": "Extracted from Codex handoff session.",
      "tags": "release,rollback,backup",
      "category": "runbook",
      "source_ref": "codex-session-2026-06-21#turn-18"
    }
  ]
}
```

Then pass it to the benchmark:

```bash
python scripts/agent_onboarding_benchmark.py \
  --provider hermes \
  --session-file /path/to/hermes-session.jsonl \
  --qa-file /path/to/project-onboarding.json \
  --db-path /path/to/vault.db \
  --candidate-file /path/to/session-candidates.json \
  --output /tmp/hermes-vs-vault-onboarding.json
```

The benchmark writes candidate proposals into a temporary copy of the benchmark database state, not into your real active project memory. The important metric is:

- `candidate_active_delta_before_promotion` should remain `0`.

That proves extracted memories can be reviewed before they become formal project knowledge.

## Reading The Report

Key fields:

- `session_baseline.hit_rate` — how often the exported session transcript contains expected evidence.
- `vault_onboarding.topk_hit_rate` — how often Vault finds the expected project memory.
- `vault_onboarding.source_hit_rate` — how often Vault finds the expected source.
- `vault_onboarding.read_range_guidance_rate` — how often results guide the agent toward bounded reads.
- `summary.topk_hit_rate_delta` — Vault hit rate minus session baseline hit rate.
- `summary.candidate_active_delta_before_promotion` — active knowledge rows added by candidate proposals before promotion.
- `summary.wrong_source_guard_passed` — whether duplicate-title stale-source protection still works.

This is not a benchmark of hidden Hermes or Codex memory internals. It is a practical, reproducible comparison between:

- what is present in exported agent sessions, and
- what a governed Vault project memory can retrieve, source-check, and read with bounded evidence.

## Reproducible Repo-Doc Fixture

The source-checkout fixture lives under `benchmarks/agent_onboarding/`:

- `project_onboarding.repo.json` contains 28 onboarding questions.
- `session_candidates.example.json` contains public-safe candidate-memory examples.
- `benchmarks/agent_onboarding/README.md` has the short command sequence.

The matching database is generated rather than committed. This avoids shipping
runtime artifacts while still making the benchmark repeatable against the
current README/docs source of truth.

Hermes session exports can be used the same way as Codex exports as long as they
are saved locally as `.md`, `.txt`, `.json`, or `.jsonl`. Keep Hermes exports and
reports outside git unless they have been scrubbed for private context.
