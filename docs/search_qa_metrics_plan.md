# B3 — Internal Search QA Metrics Plan

> **For Hermes:** B3 does not rebuild search. It turns internal Guardrails dogfood needs into a measurable QA set and daily metrics loop. Search results are navigation hints only; final evidence must still come from `guardrails_read_range`.

**Last updated:** 2026-05-18 11:05 CST

**Phase:** Phase B / B3 — Search QA metrics and internal regression set

**Status:** Design complete + initial internal QA set created

**Primary artifacts:**

- `qa/internal_guardrails_search_qa/core.json` — internal dogfood Search QA core set
- `guardrails_lite/search_qa.py` — existing Sprint 4E evaluator, reused as-is
- `tests/fixtures/search_qa_set.json` — tiny deterministic smoke fixture, not the internal dogfood set
- `docs/document_map_coverage_plan.md` — B2 gap source

**Next after this:** B4 CJK retrieval improvement plan

---

## 0. Goal

Move Search QA from:

```text
small evaluator smoke exists
```

to:

```text
internal dogfood query set exists
  → B2 coverage/search gaps become regression cases
  → retrieval, map guidance, read_range guidance, and citation policy are measured
  → CJK/mixed-language misses are visible before B4
  → daily read-only reports can show regressions without auto-writing knowledge
```

B3 makes Guardrails searchable quality visible. It does not try to solve every miss in this phase.

---

## 1. Non-goals

B3 does **not**:

- rewrite `GuardrailsSearch`,
- change ranking, tokenizer, synonym expansion, or embedding behavior,
- rebuild the Sprint 4E evaluator from scratch,
- weaken citation policy,
- treat search result snippets or `best_claim` as final evidence,
- include B5 unpromoted drafts in normal search QA,
- write knowledge automatically from daily reports,
- sync metrics to Supabase by default.

B4 is the place to improve CJK/tokenization/synonym behavior. B3 only creates the measurement net.

---

## 2. Existing foundation to reuse

Sprint 4E already provides the evaluator foundation:

| Existing piece | Role |
|---|---|
| `guardrails_lite/search_qa.py` | Pure local Search QA evaluator and before/after comparer |
| `guardrails search-qa run` | Runs QA set and outputs JSON snapshot / compact text summary |
| `guardrails search-qa compare` | Compares two snapshots with stable metric deltas |
| `tests/fixtures/search_qa_set.json` | Tiny deterministic smoke fixture |
| `tests/test_search_quality_metrics.py` | Existing regression tests for evaluator behavior |

Current evaluator metrics:

- `total_cases`
- `cases_with_results`
- `top1_hits`
- `topk_hits`
- `mean_reciprocal_rank`
- `map_guidance_rate`
- `read_range_guidance_rate`
- `citation_policy_violations`

Important boundary:

- `tests/fixtures/search_qa_set.json` remains a small smoke fixture.
- Internal dogfood cases live separately under `qa/internal_guardrails_search_qa/`.

This avoids making unit tests brittle against Arthur's evolving private knowledge corpus.

---

## 3. Source of truth and scope

### 3.1 Canonical data source

Local SQLite is canonical:

```text
/home/zycas/Guardrails-knowledge/guardrails.db
```

Supabase / Dashboard are observability and sync targets, not the B3 source of truth.

### 3.2 Included corpus

B3 normal-search QA covers only formal `knowledge` rows.

### 3.3 Excluded corpus

Exclude:

- B5 unpromoted drafts,
- private drafts,
- blocked/no-write candidates,
- raw transcripts,
- private-only material,
- local `.hermes/` handoff artifacts.

If a session-derived lesson is useful, it must pass B1/B6/B5 review and be promoted before entering B3 normal-search QA.

---

## 4. Internal QA set artifact

Created:

```text
qa/internal_guardrails_search_qa/core.json
```

It contains 14 initial cases covering:

| Segment | Cases |
|---|---:|
| Phase B / dogfood anchor | 1 |
| Document Map / citation policy | 4 |
| Privacy / write governance | 2 |
| Vault-for-LLM release hygiene | 5 |
| CJK / mixed-language alias recall | 2 |
| Negative control | 1 |

The JSON uses version `2` metadata while remaining compatible with the current evaluator. Unknown fields are forward-compatible and ignored by `search_qa.py` today.

### 4.1 Case schema

Current compatible fields:

```json
{
  "id": "phase-b-roadmap-mixed",
  "query": "Phase B 內部百科 Document Map Search QA privacy scanner draft queue",
  "expected_ids": [734],
  "expected_title_substrings": ["Phase B", "內部百科"]
}
```

Forward-compatible B3 metadata:

```json
{
  "source": "b2_gap",
  "priority": "P0",
  "language": "mixed",
  "query_variants": ["Phase B 內部百科真正能力建設"],
  "expected_k": 10,
  "map_expectation": "required_after_b2",
  "should_have_map_guidance": true,
  "should_require_read_range": true,
  "gap_types": ["no_document_map_nodes", "missing_claims"],
  "tags": ["phase-b", "document-map", "search-qa"]
}
```

### 4.2 Required semantics

- Prefer `expected_ids` when stable.
- Keep `expected_title_substrings` as fallback, with current `AND` semantics.
- `query_variants` should later expand into variant-level subcases or segmented metrics.
- `expected_hit: false` is reserved for future negative-control support; current evaluator records it as metadata only.
- `map_expectation` prevents premature failures before B2 map remediation:
  - `required_now`
  - `required_after_b2`
  - `known_missing_gap`
  - `not_required`

---

## 5. B2 gap ingestion protocol

B2 gaps should enter B3 like this:

```text
B2 coverage/search gap
  → verify formal knowledge only
  → exclude private/draft/no-write content
  → assign priority/source/language/gap_types
  → add expected_ids when stable
  → add query + variants
  → run baseline
  → classify as retrieval miss / map guidance gap / read_range guidance gap / policy gap
  → keep open until fixed or explicitly deferred
```

### 5.1 B2 gap type mapping

| B2 gap type | B3 handling |
|---|---|
| `no_document_map_nodes` | Add case with `map_expectation = required_after_b2`; retrieval may pass while map guidance is still open |
| `missing_claims` | Add guidance/enrichment expectation; do not treat as retrieval failure by itself |
| `search_miss` | Count as retrieval miss immediately |
| `no_best_span` | Count as guidance/enrichment failure |
| `read_range_over_limit` | Feed citation/policy harness; report beside Search QA |
| `remote_sync_gap` | Track separately from local retrieval metric |
| `cjk_recall` | Feed B4 candidate backlog |

### 5.2 B2 P0 anchors already represented

Initial `core.json` covers these P0/P1 anchors:

| Knowledge ID | Why included |
|---:|---|
| 734 | Phase B roadmap / internal dogfood anchor |
| 452 | Citation policy: search navigation vs final read_range citation |
| 454 | Document Map compile hook / Supabase sync |
| 456 | Remote Document Map read path |
| 483 | Local SQLite source of truth |
| 724 | Life/profile privacy write governance |
| 482 | Public release privacy/secret scan boundary |
| 683 / 714 / 730 / 732 | Vault-for-LLM release hygiene anchors |

---

## 6. Baseline run

Command:

```bash
cd /home/zycas/Guardrails-knowledge
/home/zycas/miniconda3/envs/guardrails-lite/bin/python \
  -m guardrails_lite.guardrails_cli search-qa run \
  --qa-file qa/internal_guardrails_search_qa/core.json \
  --mode keyword \
  --limit 10 \
  --output /tmp/guardrails_b3_search_qa_baseline.json
```

Baseline result on 2026-05-18:

```text
Search QA run complete
- total_cases: 14
- cases_with_results: 14
- top1_hits: 4
- topk_hits: 5
- mean_reciprocal_rank: 0.32142857142857145
- map_guidance_rate: 0.42857142857142855
- read_range_guidance_rate: 0.42857142857142855
- citation_policy_violations: 0
```

Self-compare smoke:

```bash
/home/zycas/miniconda3/envs/guardrails-lite/bin/python \
  -m guardrails_lite.guardrails_cli search-qa compare \
  --before /tmp/guardrails_b3_search_qa_baseline.json \
  --after /tmp/guardrails_b3_search_qa_baseline.json \
  --output /tmp/guardrails_b3_search_qa_self_compare.json
```

Result: all metric deltas are zero.

### 6.1 Baseline interpretation

The initial baseline is intentionally not green.

It proves three useful things:

1. The evaluator can run against the internal dogfood QA set.
2. Citation policy has no detected violations in this run.
3. Retrieval/map/read guidance has real gaps that B2/B4 must address.

### 6.2 Baseline hits

Currently passing top-k anchors:

| Case | Hit rank | Notes |
|---|---:|---|
| `phase-b-roadmap-mixed` | 1 | Mixed-language Phase B anchor works |
| `life-profile-write-governance` | 1 | Privacy governance exact Chinese query works |
| `pypi-non-git-stderr-noise` | 2 | Release hygiene anchor recalled, but not top1 |
| `cjk-session-writeback-alias` | 1 | Traditional Chinese alias query works |
| `cjk-simplified-session-writeback-alias` | 1 | Simplified alias query unexpectedly works for the Phase B anchor |

### 6.3 Baseline misses / backlog

Current top-k misses:

| Case | Expected ID | Category | Next owner |
|---|---:|---|---|
| `citation-policy-read-range` | 452 | citation/search recall | B2 map + B3 ranking baseline |
| `document-map-compile-sync` | 454 | Document Map recall | B2/B4 |
| `remote-document-map-read-path` | 456 | remote map recall | B2/B4 |
| `sqlite-source-of-truth` | 483 | source-of-truth recall | B2/B4 |
| `public-boundary-privacy-scan` | 482 | release/privacy recall | B4 |
| `pypi-wheel-real-cli-smoke` | 683 | release hygiene recall | B4 |
| `trusted-publishing-release-workflow` | 730 | release hygiene recall | B4 |
| `path-filter-release-hygiene` | 732 | release hygiene recall | B4 |

These misses should not be hidden by aggregate averages. Daily reports must list P0/P1 regressions and open misses explicitly.

### 6.4 Negative-control caveat

`negative-private-raw-transcript` currently returns results, because the existing evaluator does not yet understand `expected_hit: false`. The case is explicitly marked non-gating in `core.json` (`evaluation_scope: observational_until_expected_hit_false_supported`, `gating: false`). This is not a privacy leak by itself; it means B3 implementation should add negative-control semantics before using negative cases as gates.

---

## 7. Metrics model

### 7.1 Current evaluator metrics

| Metric | Meaning |
|---|---|
| `total_cases` | Number of evaluated cases |
| `cases_with_results` | Queries returning at least one result |
| `top1_hits` | Expected item appears rank 1 |
| `topk_hits` | Expected item appears within returned top-k |
| `mean_reciprocal_rank` | Average reciprocal rank of expected hit |
| `map_guidance_rate` | Any result includes map guidance metadata |
| `read_range_guidance_rate` | Any result includes read_range guidance metadata |
| `citation_policy_violations` | Search result violates navigation-only citation policy |

### 7.2 B3 implementation metrics to add later

| Metric | Why |
|---|---|
| `top1_hit_rate` | Easier daily reading than raw count |
| `hit_at_k` | Primary retrieval regression gate |
| `mean_hit_rank` | Helps catch ranking degradation even when top-k passes |
| `miss_count` | Explicit backlog pressure |
| `eligible_map_guidance_rate` | Exclude known `required_after_b2` gaps from denominator |
| `eligible_read_range_guidance_rate` | Same for read_range guidance |
| `no_best_span_count` | Search hit exists but citation navigation is weak |
| `negative_control_violations` | Expected no-hit cases returned unsafe or disallowed content |
| `p0_regressions` | P0 cases that changed from pass to fail |
| `cjk_hit_at_k` | First-class CJK recall metric for B4 |
| `mixed_language_hit_at_k` | Mixed Chinese/English queries |
| `alias_recall_rate` | Alias/synonym queries still hit target |
| `traditional_simplified_pair_delta` | zh-Hant/zh-Hans pair gap |

### 7.3 Segment dimensions

Every metric should be segmentable by:

- `priority`: P0 / P1 / P2
- `source`: `b2_gap`, `policy_regression`, `release_sop`, `cjk_recall`, `negative_control`
- `language`: `en`, `zh-Hant`, `zh-Hans`, `mixed`
- `mode`: keyword / vector / hybrid / auto
- `gap_types`
- `map_expectation`

---

## 8. Before/after protocol

Use before/after snapshots for any search, ranking, tokenizer, synonym, map enrichment, or indexing change.

### 8.1 Required command shape

```bash
# before
/home/zycas/miniconda3/envs/guardrails-lite/bin/python \
  -m guardrails_lite.guardrails_cli search-qa run \
  --db-path guardrails.db \
  --qa-file qa/internal_guardrails_search_qa/core.json \
  --mode keyword \
  --limit 10 \
  --output /tmp/search-qa-before.json

# after
/home/zycas/miniconda3/envs/guardrails-lite/bin/python \
  -m guardrails_lite.guardrails_cli search-qa run \
  --db-path guardrails.db \
  --qa-file qa/internal_guardrails_search_qa/core.json \
  --mode keyword \
  --limit 10 \
  --output /tmp/search-qa-after.json

# compare
/home/zycas/miniconda3/envs/guardrails-lite/bin/python \
  -m guardrails_lite.guardrails_cli search-qa compare \
  --before /tmp/search-qa-before.json \
  --after /tmp/search-qa-after.json \
  --output /tmp/search-qa-compare.json
```

### 8.2 Snapshot metadata to add later

Current snapshot includes:

- QA file path,
- mode,
- limit,
- generated timestamp,
- aggregate metrics,
- case summaries.

B3/B4 implementation should add:

- git SHA,
- DB path,
- QA file hash,
- evaluator version,
- search mode,
- rerank flag,
- embed provider availability,
- local/remote source marker.

---

## 9. Daily / cron metrics boundary

Daily reporting must be read-only.

Default behavior:

1. Run local SQLite only.
2. Run keyword mode as deterministic gate.
3. Write JSON/Markdown report to local artifact path.
4. Send compact Feishu summary only if cron delivery is configured.
5. Do not write knowledge.
6. Do not promote B5 drafts.
7. Do not sync Supabase unless a separate explicit sync job exists.
8. Do not fail the whole report because vector/embedding provider is unavailable.

Optional observational runs:

- hybrid/vector mode,
- remote Supabase comparison,
- CJK expanded query variants.

These must be labeled **observational**, not release-gating, until the environment is stable.

### 9.1 Feishu-friendly summary format

```text
Search QA daily — YYYY-MM-DD

DB: /home/zycas/Guardrails-knowledge/guardrails.db
QA set: qa/internal_guardrails_search_qa/core.json
Mode: keyword
Limit: 10

Overall:
- cases: 14
- top-k hits: 5/14
- top1 hits: 4/14
- MRR: 0.321
- map guidance: 42.9%
- read_range guidance: 42.9%
- citation policy violations: 0

P0/P1 open misses:
- citation-policy-read-range → expected 452
- document-map-compile-sync → expected 454
- remote-document-map-read-path → expected 456
- sqlite-source-of-truth → expected 483
- public-boundary-privacy-scan → expected 482
- pypi-wheel-real-cli-smoke → expected 683
- trusted-publishing-release-workflow → expected 730
- path-filter-release-hygiene → expected 732

Next:
- B2 map remediation for map/read guidance gaps
- B4 CJK/release-hygiene retrieval improvement
```

---

## 10. CJK and mixed-language handoff to B4

B3 intentionally includes CJK/mixed cases before B4 starts.

Current initial cases:

| Case | Query type | Current status |
|---|---|---|
| `cjk-session-writeback-alias` | zh-Hant alias query | hit rank 1 |
| `cjk-simplified-session-writeback-alias` | zh-Hans alias query | hit rank 1 |
| `phase-b-roadmap-mixed` | mixed English/Chinese | hit rank 1 |
| release hygiene mixed queries | mixed English/Chinese/technical tokens | many misses |

B4 should not start from vague complaints like "Chinese search is bad". It should start from concrete misses in `core.json` and expand with query variants.

---

## 11. Edge cases

B3 and B4 must account for:

1. CJK queries without spaces.
2. Traditional/Simplified Chinese variants.
3. English technical terms embedded in Chinese sentences.
4. Alias pairs:
   - `對話回寫` / `session writeback`
   - `草稿隊列` / `draft queue`
   - `隱私掃描` / `privacy scanner`
   - `引用政策` / `citation policy`
5. Multiple valid expected entries.
6. `expected_title_substrings` false positives.
7. Missing Document Map nodes but correct retrieval hit.
8. Retrieval hit but missing map/read guidance.
9. Search result citation accidentally treated as final citation.
10. Local SQLite vs Supabase drift.
11. Private/draft/no-write content appearing in normal QA.
12. Negative-control cases before evaluator support exists.
13. Embedding provider unavailable.
14. Ranking ties or non-deterministic hybrid/vector runs.

---

## 12. Smoke checks

### 12.1 Existing smoke fixture

```bash
/home/zycas/miniconda3/envs/guardrails-lite/bin/python \
  -m guardrails_lite.guardrails_cli search-qa run \
  --qa-file tests/fixtures/search_qa_set.json \
  --mode keyword \
  --limit 5
```

Observed 2026-05-18:

```text
- total_cases: 2
- cases_with_results: 2
- top1_hits: 0
- topk_hits: 0
- mean_reciprocal_rank: 0.0
- map_guidance_rate: 0.0
- read_range_guidance_rate: 0.0
- citation_policy_violations: 0
```

Interpretation: evaluator runs, but fixture is no longer aligned with current corpus. Keep it as evaluator smoke only.

### 12.2 Internal core smoke

```bash
/home/zycas/miniconda3/envs/guardrails-lite/bin/python \
  -m guardrails_lite.guardrails_cli search-qa run \
  --qa-file qa/internal_guardrails_search_qa/core.json \
  --mode keyword \
  --limit 10
```

Expected now:

- command exits 0,
- `total_cases = 14`,
- `citation_policy_violations = 0`,
- misses are reported as backlog, not hidden.

### 12.3 Self-compare smoke

```bash
/home/zycas/miniconda3/envs/guardrails-lite/bin/python \
  -m guardrails_lite.guardrails_cli search-qa compare \
  --before /tmp/guardrails_b3_search_qa_baseline.json \
  --after /tmp/guardrails_b3_search_qa_baseline.json
```

Expected: all deltas zero.

---

## 13. Implementation backlog after design

B3 design is complete, but implementation improvements remain:

1. Add segment-aware aggregate metrics to `search_qa.py`.
2. Add `expected_hit: false` support for negative controls.
3. Expand `query_variants` into evaluated subcases.
4. Add snapshot metadata: git SHA, DB path, QA hash, evaluator version.
5. Add explicit `misses` / `regressions` arrays to output JSON.
6. Add daily report renderer with Feishu-friendly Markdown.
7. Add optional cron job only after Arthur approves schedule/destination.
8. Add tests for version-2 schema metadata being ignored or consumed safely.
9. Add B4-generated CJK alias/synonym expansion cases.
10. Add remote/local comparison only after sync status is stable.

---

## 14. Acceptance criteria

B3 is accepted at the design/artifact level when:

- [x] It reuses Sprint 4E `search_qa.py` and CLI instead of rebuilding evaluator.
- [x] It keeps `tests/fixtures/search_qa_set.json` as tiny smoke fixture.
- [x] It creates a separate internal dogfood QA set.
- [x] The internal QA set includes B2/Phase B/citation/privacy/release/CJK anchors.
- [x] The internal QA set can run through existing CLI.
- [x] Baseline metrics are recorded.
- [x] Self-compare smoke passes with zero deltas.
- [x] Current misses are listed as backlog.
- [x] Daily metrics boundary is read-only and does not auto-write knowledge.
- [x] Citation policy remains strict: final evidence must come from `read_range`.
- [x] B4 has concrete CJK/mixed-language cases to start from.

Implementation-level acceptance remains pending for segment metrics, negative-control semantics, query variants, and daily renderer.
