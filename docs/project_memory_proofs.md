# Project Memory Proof Demos

Vault-for-LLM should not be judged as "another Markdown vector store." The useful claim is narrower:

> Vault-for-LLM helps agents use project memory as a governed handoff layer: search the right source, propose before storing, read bounded evidence, and verify retrieval behavior with local tests.

This repository includes a public-safe proof script that turns that claim into local, repeatable numbers.

```bash
python scripts/project_memory_proofs.py --output /tmp/vault-project-memory-proofs.json
```

The script creates temporary SQLite vaults and demo notes. It does not need network access, embeddings, Supabase, Docker, or private data.

## Proof 1: Agent Onboarding

Question: can a new agent recover project handoff facts without rereading a whole chat history?

The proof builds a small project vault with architecture boundaries, MCP safety rules, release gates, source-of-truth policy, and handoff pitfalls. It then runs source-aware Search QA over five onboarding questions.

Reported metrics include:

- `task_count`
- `naive_title_or_source_hits`
- `vault_top1_hits`
- `vault_topk_hits`
- `vault_source_hit_rate`
- `vault_read_range_guidance_rate`
- `mean_reciprocal_rank`

Expected demo result:

```json
{
  "task_count": 5,
  "naive_title_or_source_hits": 0,
  "vault_top1_hits": 5,
  "vault_topk_hits": 5,
  "vault_source_hit_rate": 1.0,
  "vault_read_range_guidance_rate": 1.0
}
```

What this proves: the value is not that notes exist; it is that an agent can find the right project source and get a bounded-read next step.

## Proof 2: Candidate-First Memory

Question: can agent-proposed memory be reviewed before it pollutes active project knowledge?

The proof creates one active runbook, then proposes five candidate memories:

- ready to promote
- duplicate
- too vague
- privacy blocked
- missing source reference

The important metric is `active_knowledge_delta_before_promotion`: it should stay `0` after proposals. Only an explicit promotion should write a new active knowledge row.

Expected demo result:

```json
{
  "candidate_count": 5,
  "active_knowledge_delta_before_promotion": 0,
  "review_buckets": {
    "duplicate_review": 1,
    "missing_source_reference": 1,
    "quality_review": 1,
    "ready_for_review": 1,
    "rejected": 1
  }
}
```

What this proves: Vault-for-LLM is not only a memory store. It can be used as a review gate between agent suggestions and formal project knowledge.

## Proof 3: Wrong Source vs Bounded Read

Question: can the workflow avoid stale answers when old and current docs share the same title?

The proof creates two notes named `Deployment Runbook`:

- archived source: `docs/archive/deployment-runbook.md`
- current source: `docs/runbooks/deployment-runbook.md`

A title-only handoff would pick the first matching title, which is stale. The source-aware Search QA case expects the current source, then the proof reads the bounded range used for final citation.

Expected demo result:

```json
{
  "would_title_only_pick_stale_source": true,
  "source_aware_topk_hit": true,
  "source_hit_rank": 1,
  "bounded_read_contains_current_policy": true
}
```

What this proves: the workflow is about "find the right source and cite a bounded range," not merely "find a similar chunk."

## Interpreting The Output

These are proof demos, not academic benchmarks. They are meant to validate product direction and prevent vague positioning:

- Agent onboarding should be measurable.
- Candidate memory should be review-gated.
- Duplicate-title and stale-source scenarios should be caught by source-aware retrieval plus bounded reads.

The next step is to run the same three patterns against real agent sessions, for example comparing:

- runtime memory alone
- Markdown notes without Search QA
- Vault keyword Search QA
- Vault source-aware Search QA plus bounded reads

Useful outcome metrics for real projects include answer accuracy, citation correctness, source freshness, token usage, and repeated-mistake reduction.
