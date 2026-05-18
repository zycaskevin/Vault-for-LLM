# Guardrails Internal Knowledge Capability — Progress

Last updated: 2026-05-18 11:55 CST

## Current Phase: Phase B — 內部百科真正能力建設 — B1/B6/B5/B2/B3/B4 COMPLETE / B7 NEXT

### Goal
Let Nancy / Hermes / Guardrails dogfood the internal knowledge base every day so real retrieval, citation, capture, privacy, CJK search, and multi-agent convergence problems surface before public Vault-for-LLM productization.

### Current Planning Artifacts
- `docs/phase_b_internal_knowledge_capability_plan.md` — Phase B internal roadmap and execution order.
- `docs/session_writeback_governance.md` — B1 governance contract for session → candidate → draft → review → promote.
- `docs/privacy_scanner_design.md` — B6 shared scanner design for add/capture/compile/sync/MCP privacy gates.
- `docs/session_capture_draft_queue_design.md` — B5 review-gated draft queue design for session capture.
- `docs/document_map_coverage_plan.md` — B2 coverage plan for high-value Document Map/read_range/citation gaps.
- `docs/search_qa_metrics_plan.md` — B3 internal Search QA metrics plan, internal dogfood QA set, baseline, self-compare, and daily reporting boundary.

### Phase B Priority Order
1. B1 對話回寫治理 — COMPLETE (design)
2. B6 privacy scanner — COMPLETE (design)
3. B5 session capture draft queue — COMPLETE (design)
4. B2 Document Map coverage strengthening — COMPLETE (design)
5. B3 internal Search QA metrics — COMPLETE (design/artifact baseline)
6. B4 CJK retrieval improvements — COMPLETE
7. B7 multi-agent writing and convergence workflow

### Immediate Next Task
Start B7 multi-agent writing and convergence workflow: duplicate detection, conflict handling, freshness/convergence checks, and safe sync flow from internal Guardrails source of truth to public-safe Vault-for-LLM slices.

---

## Current Sprint: Sprint 4G — CJK / Alias Keyword Retrieval — COMPLETED

### Goal
Fix keyword retrieval misses surfaced by the B3 internal QA baseline without weakening citation policy: score mixed-language candidates before final limiting, add conservative CJK Traditional/Simplified and domain-alias query expansion, and keep regression coverage explicit.

### Root Cause Findings
1. `search_keyword` currently orders SQL candidates by `trust DESC LIMIT ?` before Python relevance scoring, so high-trust weak matches can crowd out the actual best match.
2. `_tokenize` is brittle for mixed technical terms: hyphen/underscore/domain tokens are split into noisy fragments (`Vault-for-LLM`, `sqlite-vec`, `read_range`, `id-token`).
3. CJK tokenization uses non-overlapping 2–4 char chunks and lacks Traditional/Simplified normalization, so Simplified queries can pass only accidentally.
4. No domain alias layer exists for Phase B language pairs such as `對話回寫` ↔ `session writeback`, `草稿隊列` ↔ `draft queue`, and `隱私掃描` ↔ `privacy scanner`.
5. QA hygiene gap found: a redacted placeholder-like core QA case ID needed normalization; display-layer ellipsization was verified not to mutate the actual JSON IDs.

### Implementation Rules
- Add failing tests before changing search code.
- Keep expansion in query-time memory only; do not mutate stored knowledge rows.
- Keep alias dictionary narrow and Phase-B/domain specific.
- Do not change final citation policy; search citations remain navigation hints.

### Scope Delivered
1. Changed keyword search to gather the full SQL candidate pool before final Python relevance scoring, avoiding `trust DESC LIMIT` truncation of lower-trust exact matches.
2. Added deterministic mixed-language tokenization for hyphen/underscore technical identifiers (`Vault-for-LLM`, `sqlite-vec`, `read_range`, `id-token`) plus component tokens.
3. Added narrow Phase-B alias expansion for `對話回寫`/`session writeback`, `草稿隊列`/`draft queue`, `隱私掃描`/`privacy scanner`, and `內部百科`/`internal knowledge base`.
4. Added conservative Simplified→Traditional query normalization for the B4 CJK cases without mutating stored knowledge rows.
5. Hardened QA hygiene checks for stable unique core QA case IDs and fixed the script-style `tests/test_new_features.py` smoke test to use the active Python interpreter instead of assuming `conda` is on PATH.

### Final Metrics
```text
Search QA run complete
- total_cases: 14
- cases_with_results: 14
- top1_hits: 11
- topk_hits: 13
- mean_reciprocal_rank: 0.8452380952380951
- map_guidance_rate: 0.07142857142857142
- read_range_guidance_rate: 0.07142857142857142
- citation_policy_violations: 0

Before/after from B3 baseline:
- top1_hits: 4 -> 11 (+7)
- topk_hits: 5 -> 13 (+8)
- mean_reciprocal_rank: 0.32142857142857145 -> 0.8452380952380951 (+0.52380952381)
- citation_policy_violations: 0 -> 0 (0)
```

### Verification
```bash
/home/zycas/miniconda3/envs/guardrails-lite/bin/python tests/test_new_features.py
# PASS: RESULTS: 26/26 PASSED, 0 FAILED

/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m pytest -q
# PASS: 80 passed, 2 warnings in 27.97s

/home/zycas/miniconda3/envs/guardrails-lite/bin/python \
  -m guardrails_lite.guardrails_cli search-qa run \
  --qa-file qa/internal_guardrails_search_qa/core.json \
  --mode keyword \
  --limit 10 \
  --output /tmp/guardrails_b4_search_qa_final.json
# PASS: top1_hits=11; topk_hits=13; citation_policy_violations=0.

/home/zycas/miniconda3/envs/guardrails-lite/bin/python \
  -m guardrails_lite.guardrails_cli search-qa compare \
  --before /tmp/guardrails_b3_search_qa_baseline.json \
  --after /tmp/guardrails_b4_search_qa_final.json \
  --output /tmp/guardrails_b4_search_qa_final_compare.json
# PASS: top1 +7, topk +8, MRR +0.52380952381, citation policy unchanged.

/usr/bin/python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"
# PASS: graphify rebuilt graph.json and GRAPH_REPORT.md; graph.html skipped because graph exceeds viz node limit.
```

### Remaining Follow-up
- `negative-private-raw-transcript` remains a non-gating negative control; B7 or a later Search QA hardening sprint should implement first-class `expected_hit: false` evaluator semantics.
- The lower `map_guidance_rate` / `read_range_guidance_rate` reflects better direct retrieval of expected entries; B7 should continue improving Document Map coverage and convergence evidence rather than weakening citation policy.

---

## Current Sprint: Sprint 4F — Internal Search QA Dogfood Baseline — COMPLETED

### Goal
Create the internal dogfood Search QA artifact that turns Phase B retrieval/citation concerns into repeatable metrics before changing CJK tokenization, synonyms, ranking, or daily reporting.

### Scope Delivered
1. Added `docs/search_qa_metrics_plan.md` with:
   - internal QA schema,
   - baseline command and metrics,
   - before/after comparison protocol,
   - read-only daily reporting boundary,
   - B4 handoff cases,
   - implementation backlog.
2. Added `qa/internal_guardrails_search_qa/core.json` with 14 internal cases across B2 gaps, Phase B anchors, citation policy, privacy/release hygiene, CJK aliases, and one non-gating negative control.
3. Marked `negative-private-raw-transcript` as observational/non-gating until `expected_hit: false` evaluator semantics are implemented.
4. Kept citation policy strict: search citations remain navigation hints; final evidence still requires `read_range`.

### Baseline Metrics
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

### Verification
```bash
/home/zycas/miniconda3/envs/guardrails-lite/bin/python \
  -m guardrails_lite.guardrails_cli search-qa run \
  --qa-file qa/internal_guardrails_search_qa/core.json \
  --mode keyword \
  --limit 10 \
  --output /tmp/guardrails_b3_search_qa_baseline.json
# PASS: command exited 0; total_cases=14; citation_policy_violations=0.

/home/zycas/miniconda3/envs/guardrails-lite/bin/python \
  -m guardrails_lite.guardrails_cli search-qa compare \
  --before /tmp/guardrails_b3_search_qa_baseline.json \
  --after /tmp/guardrails_b3_search_qa_baseline.json
# PASS: all metric deltas are zero.

git diff --check
# PASS: no whitespace errors.
```

### Remaining Backlog
- Add segment-aware aggregate metrics to `search_qa.py`.
- Add real `expected_hit: false` support for negative controls.
- Expand `query_variants` into evaluated subcases.
- Add snapshot metadata: git SHA, DB path, QA hash, evaluator version.
- Add explicit misses/regressions arrays to JSON output.
- Add daily report renderer / cron only after Arthur approves schedule and destination.

---

## Previous Sprint: Sprint 4E — Search QA Set + Before/After Metrics — COMPLETED

### Goal
Create a deterministic Search QA Set and before/after metric runner so Guardrails search quality can be measured before changing ranking logic. This sprint is about observability and regression safety, not about making search ranking smarter yet.

### Baseline Findings
- Repository baseline: `/home/zycas/Guardrails-knowledge`, branch `main`, HEAD `72da9d9f0fabf514d30f66b2c05f500e57286be4`.
- Working tree before Sprint 4E implementation: `PROGRESS.md` modified by Sprint 4D documentation only; no search-quality code changes yet.
- Graphify baseline: 1081 nodes / 2320 edges / 72 communities.
- Existing search path:
  - `guardrails_lite/guardrails_search.py` owns keyword/vector/hybrid search, rerank, Document Map enrichment, and navigation hints.
  - `guardrails_lite/agent_policy.py` owns the behavior policy that keeps search citations as navigation-only and requires read-range citations for final answers.
  - `tests/test_search_map_integration.py`, `tests/test_agent_behavior_policy.py`, and `tests/test_guardrails_health_metrics.py` already cover the Document Map and citation-policy boundary.
- Current local DB health sample (`sample_limit=20`): total entries 424, entries with nodes 1, entries with claims 1, map coverage 0.24%, claim coverage 0.24%, citation coverage 0%, read_range over-limit violations 0. This local DB state differs from the latest synced Dashboard snapshot and confirms that QA metrics must read local SQLite as source of truth.
- Existing test baseline: `tests/test_search_map_integration.py tests/test_agent_behavior_policy.py tests/test_guardrails_health_metrics.py` passed (`16 passed in 3.27s`).

### Scope Delivered
1. Added `guardrails_lite/search_qa.py` as a pure Python local evaluator around `GuardrailsSearch`.
2. Added an extendable in-repo QA fixture at `tests/fixtures/search_qa_set.json`.
3. Added aggregate and per-case metrics:
   - `total_cases`
   - `cases_with_results`
   - `top1_hits`
   - `topk_hits`
   - `mean_reciprocal_rank`
   - `map_guidance_rate`
   - `read_range_guidance_rate`
   - `citation_policy_violations`
4. Added deterministic before/after snapshot comparison with JSON output and human-readable CLI formatting.
5. Added explicit CLI commands:
   - `guardrails search-qa run --qa-file --output --mode --limit --db-path`
   - `guardrails search-qa compare --before --after --output`
6. Added `tests/test_search_quality_metrics.py` with temporary SQLite fixtures and CLI smoke coverage; tests do not require network, Supabase, Ollama, or embedding providers.
7. Preserved citation policy boundaries: search result citations remain navigation hints only; the evaluator only measures guidance and flags suspicious final-citation labels.

### Review Findings Resolved
- Independent review found one blocking metric-correctness issue: `expected_title_substrings` originally used OR semantics, so `["citation", "policy"]` could falsely match `Citation Only` or `Policy Only`.
- Fixed by requiring all configured substrings to match the result title.
- Regression proof:
  - `Citation Policy Boundary` → `True`
  - `Citation Only` → `False`
  - `Policy Only` → `False`
- Re-review passed with no blocking or non-blocking findings.

### Non-Goals Preserved
- No search ranking tuning.
- No Supabase schema changes and no changes to `hermes_guardrails_health`.
- No citation policy weakening.
- No Dashboard frontend changes.
- No live DB `guardrails map build` as part of implementation; Document Map building only appears inside temporary test fixtures.

### Final Verification
```bash
# Targeted Search QA + policy + health regression
/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m pytest \
  tests/test_search_quality_metrics.py \
  tests/test_search_map_integration.py \
  tests/test_agent_behavior_policy.py \
  tests/test_guardrails_health_metrics.py -q
# PASS: 22 passed in 4.02s

# Full Guardrails regression
/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m pytest -q
# PASS: 74 passed, 2 warnings in 48.70s

# CLI smoke on local DB and in-repo QA set
/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m guardrails_lite.guardrails_cli \
  search-qa run --qa-file tests/fixtures/search_qa_set.json \
  --output /tmp/guardrails-search-qa.json --mode keyword --limit 5
# PASS: total_cases=2, cases_with_results=2, top1_hits=1, topk_hits=2, citation_policy_violations=0

/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m guardrails_lite.guardrails_cli \
  search-qa compare --before /tmp/guardrails-search-qa.json \
  --after /tmp/guardrails-search-qa.json \
  --output /tmp/guardrails-search-qa-compare.json
# PASS: deterministic zero-delta comparison generated.

# Git hygiene
git diff --check
# PASS: no whitespace errors.

# Graphify after code changes
/usr/bin/python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"
# PASS: 1126 nodes, 2416 edges, 73 communities.
```

Independent worktree verification from detached HEAD `72da9d9` also passed after applying the targeted patch:

```bash
/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m pytest \
  tests/test_search_quality_metrics.py \
  tests/test_search_map_integration.py \
  tests/test_agent_behavior_policy.py \
  tests/test_guardrails_health_metrics.py -q
# PASS: 22 passed in 4.16s

/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m pytest -q
# PASS: 74 passed, 2 warnings in 40.44s

/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m guardrails_lite.guardrails_cli search-qa run ...
/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m guardrails_lite.guardrails_cli search-qa compare ...
# PASS: CLI commands executed successfully in isolated worktree.

git diff --check
# PASS.
```

### Files Changed
- `guardrails_lite/search_qa.py`
- `guardrails_lite/guardrails_cli.py`
- `tests/test_search_quality_metrics.py`
- `tests/fixtures/search_qa_set.json`
- `PROGRESS.md`

## Previous Sprint: Sprint 4D — Dashboard Document Map Metrics Display — COMPLETED

### Goal
Render Guardrails Document Map health in the Hermes Dashboard frontend by reading Supabase `hermes_guardrails_health` snapshots and making coverage / citation / violation signals visible in the System Health tab.

### Scope Delivered
1. Kept local SQLite as the source of truth; Dashboard only reads synced Supabase snapshots.
2. Reused the deployed `hermes_guardrails_health` schema and removed the stale frontend `id` select assumption.
3. Renamed the Guardrails goal from generic `Guardrails 品質` to `Guardrails Document Map`.
4. Surfaced Document Map-specific metrics from existing schema slots:
   - `total_knowledge` → total Guardrails entries.
   - `convergence_rate` → Document Map coverage.
   - `avg_freshness` → citation navigation coverage.
   - `contradiction_count` → `read_range` over-limit violations.
   - `gap_count` → entries without nodes + entries without claims.
5. Added Guardrails-specific metric definitions in `GoalDetailSection.tsx`, explicitly stating that Dashboard metrics are observability only and final citations still require `read_range`.
6. Added a coverage sparkline and defensive percentage normalization so historical fraction rows (`0.94`) and percent rows (`94`) both render correctly.
7. Preserved citation policy boundaries: no search/final citation policy code was changed.

### Baseline Findings
- Dashboard stack: Vite + React + TypeScript under `/home/zycas/.hermes/dashboard/oa-cli/dashboard-src`.
- `useHermesData.ts` already queried `hermes_guardrails_health`, but only showed generic convergence / total / contradiction metrics and no Document Map-specific trend or definitions.
- `GoalDetailSection.tsx` already supported goal-specific metric definitions and default sparkline charts; Sprint 4D reused that existing UI pattern.
- Live Supabase rows include older fractional snapshots (`convergence_rate` around `0.94`), so the frontend normalizes both fraction and percent formats.

### Final Verification
```bash
# Dashboard TypeScript + production build
npm run build
# PASS: tsc + Vite build passed; existing large chunk warning only.

# Supabase read-path smoke
node --input-type=module <supabase hermes_guardrails_health select smoke>
# PASS: 3 rows returned; latest 2026-05-08 total_knowledge=368, convergence_rate=0.940217, avg_freshness=0.861, gap_count=22.

# HTTP + browser smoke
curl -I http://localhost:3460/
# PASS: HTTP/1.1 200 OK
# Browser DOM confirmed Guardrails Document Map card and detail render 94% coverage, 86% citation coverage, 368 entries, 0 read_range over-limit, 22 Map/Claim gaps.
# Browser console: no JavaScript errors.

# Guardrails backend regression
conda run -n guardrails-lite python3 -m pytest -q
# PASS: 68 passed, 2 warnings in 48.35s.

# Git hygiene
git diff --check
# PASS for Dashboard targeted diff and Guardrails PROGRESS.md.

# Graphify
/usr/bin/python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"
# PASS: 1081 nodes, 2320 edges, 72 communities.
```

Independent worktree verification also passed:

```bash
# Dashboard source patch applied to detached worktree from HEAD 62ac4aac
npm ci
npm run build
# PASS: tsc + Vite build passed; npm audit reported existing dependency vulnerabilities, not introduced by this source patch.

# Guardrails PROGRESS.md patch applied to detached worktree from HEAD 72da9d9
conda run -n guardrails-lite python3 -m pytest -q
# PASS: 68 passed, 2 warnings in 41.95s.
```

### Files Changed
- `/home/zycas/.hermes/dashboard/oa-cli/dashboard-src/src/hooks/useHermesData.ts`
- `/home/zycas/.hermes/dashboard/oa-cli/dashboard-src/src/types.ts`
- `/home/zycas/.hermes/dashboard/oa-cli/dashboard-src/src/components/GoalDetailSection.tsx`
- `/home/zycas/.hermes/dashboard/oa-cli/src/oa/dashboard/index.html` and hashed built asset from `npm run build`
- `/home/zycas/Guardrails-knowledge/PROGRESS.md`

## Previous Sprint: Sprint 4C — Dashboard Health Integration — COMPLETED

### Goal
Expose Document Map health to the Hermes Dashboard by collecting local SQLite coverage metrics and upserting a daily snapshot into Supabase `hermes_guardrails_health`, without changing the Dashboard frontend or weakening the Sprint 3 citation policy harness.

### Scope Delivered
1. Added `guardrails_lite/guardrails_health.py` with a small, testable local SQLite collector for:
   - `map_coverage = entries_with_nodes / total_entries`
   - `claim_coverage = entries_with_claims / total_entries`
   - `citation_coverage = sampled_search_results_with_best_span / sampled_search_results`
   - `read_range_over_limit_violations` from local Document Map node bounds.
2. Added `scripts/sync_to_supabase.py --health` / `--guardrails-health` with `--health-sample-limit` to write one daily Dashboard snapshot.
3. Preserved SQLite as source of truth; Supabase remains a Dashboard/read target only.
4. Reused the existing deployed `hermes_guardrails_health` schema instead of adding unverified columns:
   - `total_knowledge = total_entries`
   - `convergence_rate = map_coverage * 100`
   - `avg_freshness = citation_coverage * 100`
   - `contradiction_count = read_range_over_limit_violations`
   - `gap_count = entries_without_nodes + entries_without_claims`
5. Added fake-client and local SQLite tests in `tests/test_guardrails_health_metrics.py`; no real network/Supabase access is required.
6. Preserved Sprint 3/4B behavior harness: search citations remain navigation hints only; final citations must come from local or remote `read_range`.

### Guardrails Observed
- Document-first: this progress file was updated before the implementation slice.
- Schema-drift control: the first review found that deployed `hermes_guardrails_health` has no `id` column; the writer now upserts by `check_date` instead of the generic `id`-based helper.
- Surgical scope: no Dashboard frontend changes and no citation policy relaxation.
- Push safety: verification included an independent worktree checkout with the same patch applied before commit.

### Final Verification
```bash
/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m pytest \
  tests/test_guardrails_health_metrics.py \
  tests/test_sprint4a_document_map_sync.py \
  tests/test_agent_behavior_policy.py \
  tests/test_guardrails_mcp_map.py \
  tests/test_search_map_integration.py -q
# 30 passed in 5.60s

/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m pytest -q
# 68 passed, 2 warnings in 41.29s

git diff --check
# passed

/home/zycas/miniconda3/bin/python -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"
# 1081 nodes, 2320 edges, 72 communities
```

Independent worktree verification also passed from detached HEAD `0076424` after applying the uncommitted patch:

```bash
git worktree add --detach /tmp/guardrails-s4c-worktree-verify HEAD
git apply --whitespace=error-all /tmp/guardrails-s4c.patch
git diff --check
/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m pytest \
  tests/test_guardrails_health_metrics.py \
  tests/test_sprint4a_document_map_sync.py \
  tests/test_agent_behavior_policy.py \
  tests/test_guardrails_mcp_map.py \
  tests/test_search_map_integration.py -q
# 30 passed in 5.60s
/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m pytest -q
# 68 passed, 2 warnings in 41.29s
```

## Previous Sprint: Sprint 4B — Remote Document Map Read Path + Supabase DDL — COMPLETED

### Goal
Complete the remote Document Map loop by adding Supabase DDL/migration support for synced map tables, exposing a remote MCP read path backed by `guardrails_knowledge_nodes` / `guardrails_knowledge_claims`, and extending the Sprint 3 citation policy harness to cover remote trace events.

### Scope Delivered
1. Added `supabase/migrations/20260509_document_map_sprint4b.sql` for `guardrails_knowledge_nodes` and `guardrails_knowledge_claims`, including UUID primary keys, natural-key uniqueness, indexes, RLS, `agents_rw` policies, and source-of-truth comments.
2. Added remote MCP tools:
   - `guardrails_remote_map_show(knowledge_id, compact=false)` reads synced Supabase nodes and returns remote `read_range` next actions.
   - `guardrails_remote_read_range(knowledge_id, node_uid, line_start, line_end)` reads bounded remote ranges and returns fixed citations.
3. Preserved local SQLite as canonical source; Supabase remains a sync/read target only.
4. Extended deterministic policy tests so remote traces are accepted only when they follow `search → remote_map_show → remote_read_range → final answer with read_range citation`.
5. Kept Sprint 4A sync behavior backward-compatible: `scripts/sync_to_supabase.py --document-map` remains opt-in.
6. Added fake Supabase tests; no real network/Supabase access is required for test coverage.

### Guardrails Observed
- Surgical scope: no Dashboard metrics or repo hygiene in this sprint.
- Citation policy preserved: search citations remain navigation hints only; final citations must come from local or remote `read_range`.
- Review agent requested one fix: remote claim fallback must hash the returned claim content, not reuse node `content_hash`. Fixed with regression coverage.

### Final Verification
```bash
/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m pytest \
  tests/test_agent_behavior_policy.py \
  tests/test_guardrails_mcp_map.py \
  tests/test_search_map_integration.py \
  tests/test_sprint4a_document_map_sync.py -q
# 24 passed in 3.67s

/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m pytest -q
# 62 passed, 2 warnings in 38.88s

git diff --check
# passed
```

Graphify was rebuilt after code changes:

```bash
/home/zycas/miniconda3/bin/python -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"
# 1031 nodes, 2170 edges, 73 communities
```

## Previous Sprint: Sprint 4A — Supabase Document Map Sync + Compile Hook — COMPLETED

### Goal
Keep Document Map rows fresh on local compile and add an explicit Supabase sync path for `knowledge_nodes` / `knowledge_claims`, while preserving SQLite as source of truth and the Sprint 3 citation policy harness.

### Scope Delivered
1. Added compile hook in `guardrails_lite/guardrails_compile.py`: successful non-dry-run new/update entries now refresh Document Map rows via `build_document_map_for_entry()`.
2. Kept `dry_run` and unchanged/skipped entries side-effect free for Document Map rebuilds.
3. Extended duplicate cleanup to delete `knowledge_claims` and `knowledge_nodes` before removing duplicate `knowledge` rows, preventing orphan map rows.
4. Added `scripts/sync_to_supabase.py --document-map` to sync SQLite `knowledge_nodes` / `knowledge_claims` into Supabase tables `guardrails_knowledge_nodes` / `guardrails_knowledge_claims`.
5. Document Map sync uses natural-key select/update/insert upsert: nodes by `(knowledge_id, node_uid)`, claims by `(knowledge_id, claim_uid)`.
6. Added fake-client tests in `tests/test_sprint4a_document_map_sync.py`; no network is required for sync tests.

### Guardrails Observed
- Document-first: this progress note was updated before code changes.
- Minimal scope: only sync, compile hook, and targeted tests were changed.
- Backward compatibility: default Supabase knowledge sync behavior remains unchanged; `--document-map` is opt-in.
- Local-first: SQLite remains source of truth; Supabase is a sync target only.
- Citation policy: Sprint 3 behavior harness remains untouched and passing.

### Final Verification
```bash
/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m pytest \
  tests/test_agent_behavior_policy.py \
  tests/test_guardrails_mcp_map.py \
  tests/test_search_map_integration.py \
  tests/test_sprint4a_document_map_sync.py -q
# 16 passed in 3.57s

/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m pytest -q
# 54 passed, 2 warnings in 38.81s

git diff --check
# passed
```

Graphify was updated after verification. The `guardrails-lite` conda env cannot import `graphify`; use base conda Python for the AGENTS.md rebuild command:

```bash
/home/zycas/miniconda3/bin/python -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"
# 987 nodes, 1945 edges, 71 communities
```

### Review Notes
- Review agent verdict: APPROVED.
- Follow-up for Sprint 4B / operations: create Supabase DDL for `guardrails_knowledge_nodes` and `guardrails_knowledge_claims`, including unique constraints on `(knowledge_id,node_uid)` and `(knowledge_id,claim_uid)`.

## Previous Sprint: Sprint 3 — Agent Behavior Loop + Citation Policy Harness — COMPLETED

### Goal
Ensure external agents do not merely have Document Map tools available, but are guided and tested to follow the intended reading loop:

```text
guardrails_search → guardrails_map_show → guardrails_read_range → final answer with read_range citation
```

### Scope Delivered
1. Added deterministic agent behavior policy harness in `guardrails_lite/agent_policy.py`.
2. Added `tests/test_agent_behavior_policy.py` to reject unsupported traces:
   - citation-free answers when citation is required;
   - invented citations;
   - search-only citation claims;
   - `read_range` without prior `map_show`;
   - mismatched `knowledge_id` loops.
3. Treated search-result citations as navigation hints only; final answer citations must come from `guardrails_read_range`.
4. Added additive `next_action` / `next_actions` metadata in search/map/read_range payloads.
5. Added opt-in `compact=true` support for search and map payloads without changing default output shapes.
6. Normalized MCP failure responses with `failure_mode` and actionable `next_action` metadata while preserving existing `error` values.
7. Updated `docs/document_map_upgrade_plan.md` with the Sprint 3 agent behavior contract.
8. Updated `/home/zycas/.hermes/skills/guardrails/SKILL.md` with Sprint 3 citation policy discipline.

### Guardrails Observed
- Document-first: this file was updated before feature implementation.
- TDD: behavior/payload tests were added for the Sprint 3 slice.
- Surgical changes only: no Supabase sync, compile hook, dashboard metrics, or unrelated refactors were included.
- Backward compatibility: default payload shapes were preserved; compact mode is opt-in.

### Final Verification
```bash
/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m pytest \
  tests/test_agent_behavior_policy.py \
  tests/test_guardrails_mcp_map.py \
  tests/test_search_map_integration.py -q
# 12 passed in 2.04s

/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m pytest -q
# 50 passed, 2 warnings in 36.71s

git diff --check
# passed
```

Graphify was updated after verification:

```bash
/home/zycas/miniconda3/bin/graphify update .
# 947 nodes, 1736 edges, 71 communities
```

Final commit is performed after this verification block.

## Current Maintenance Pass: Full Test Environment + Repo Hygiene + Audit — COMPLETED

### Goal
Restore the project to a cleaner post-Sprint-2 working state before Sprint 3 by:
1. Auditing current repo/test/documentation state.
2. Reproducing and fixing full `pytest -q` collection blockers when they are environment/dependency related.
3. Classifying and resolving non-Sprint untracked files without mixing unrelated work into Sprint 2.

### Guardrails
- Do not start Sprint 3 feature work in this pass.
- Do not hide real product test failures behind dependency changes.
- Do not delete untracked files without evidence of what they contain.
- Keep Sprint 2 commit `970784a Add document map MCP tools` as the baseline.

### Results

#### Audit ✅
- Sprint 2 baseline remains `970784a Add document map MCP tools`.
- Graphify report was reviewed after Sprint 2; main hubs remain `GuardrailsDB`, `GuardrailsSearch`, `EmbeddingProvider`, `GuardrailsGraph`, and Document Map MCP helpers.
- Branch state observed during audit: local `main` is ahead of and behind `origin/main`; do not push/merge this maintenance commit until a sync/rebase strategy is chosen.

#### Full test environment ✅
- The earlier full-suite blockers were environment/dependency issues, not Sprint 2 product regressions.
- Correct interpreter for verification is:
  `/home/zycas/miniconda3/envs/guardrails-lite/bin/python`
- Full suite now passes with the direct interpreter:
  `45 passed`.
- Caveat: `conda run -n guardrails-lite python` can be polluted by the previously activated `/tmp/research-scrapling-tinyfish/venv-scrapling` environment in this shell. Use the direct interpreter path above for reliable verification until shell environment state is reset.

#### Untracked file classification ✅
- `_knowledge_base/` contains local research notes (`ai-website-cloner`, `scrapling-tinyfish`, `siami-reading-ghost-fields`) unrelated to Sprint 2 source changes. It is now ignored as local research/scratch material.
- `scripts/cross_validate_cloud_only.py` is a local cron-style wrapper around `scripts/cross_validate.py`. It compiles, but changes runtime behavior (`apply=True`, cloud-only, model/timeouts) and needs a separate operational review before becoming project source.
- `scripts/guardrails_gap_scanner.py` is a local daily gap-scanner draft. It compiles, but has hard-coded local paths and the docstring mentions Telegram delivery while the current implementation only prints. It needs a separate operational review before becoming project source.
- The two draft scripts are now ignored explicitly to keep Sprint maintenance commits clean.

#### Final verification ✅
- `git diff --check` passed.
- Targeted Document Map suite passed: `41 passed in 23.33s`.
- Script syntax check passed for `scripts/cross_validate.py`, `scripts/cross_validate_cloud_only.py`, and `scripts/guardrails_gap_scanner.py`.
- Full suite passed with direct interpreter: `45 passed in 33.44s`.
- Graphify was not rebuilt in this maintenance commit because no code files changed; only `.gitignore` and `PROGRESS.md` changed.

## Previous Sprint: Sprint 2 (B/E1) — COMPLETED

### Goal
Make Guardrails usable as an agent brain: search results point to Document Map spans, and MCP clients can inspect structure before reading bounded line ranges with fixed citations.

### Scope Delivered

#### B1 — Search result enrichment ✅
- Modified `guardrails_lite/guardrails_search.py`.
- Search results are enriched with Document Map metadata when available:
  - `node_uid`
  - `path`
  - `heading`
  - `line_start`
  - `line_end`
  - `best_span`
  - `best_node`
  - `citation`
  - `recommended_next_tool`
- Backward compatibility preserved: entries without populated map rows still return normally with map fields absent/empty.

#### B2 — MCP tools ✅
- Modified `guardrails_lite/guardrails_mcp.py`.
- Added MCP-callable tools:
  - `guardrails_map_show(knowledge_id)` — returns entry metadata and section structure from `knowledge_nodes`.
  - `guardrails_read_range(knowledge_id, node_uid, line_start, line_end)` — returns bounded line-numbered source content.
- Implementation remains local-first; no Supabase schema changes in Sprint 2.

#### B3 — Range limit and citation guard ✅
- `guardrails_read_range` defaults to maximum 80 lines.
- Over-limit requests return `range_too_large` and ask the caller to split ranges.
- Successful reads include a fixed citation string from the tool, e.g. `#405 Title L1-L8`.
- Agents should not invent citations; citations come from `guardrails_read_range` output.

#### E1 — Guardrails skill update ✅
- Updated `/home/zycas/.hermes/skills/guardrails/SKILL.md`.
- Added reading discipline:
  - For long knowledge entries: `search → guardrails_map_show → guardrails_read_range`.
  - Answers based on encyclopedia content should prefer `#id + line range` citations.
- Corrected CLI fallback syntax:
  - CLI: `guardrails map read <knowledge_id> --lines 12-36`
  - MCP: `guardrails_read_range` supports `node_uid` or `line_start` + `line_end`.

### Verification Results

#### Automated tests ✅
```bash
conda run -n guardrails-lite python -m pytest \
  tests/test_document_map.py \
  tests/test_document_map_cli.py \
  tests/test_search_map_integration.py \
  tests/test_guardrails_mcp_map.py -q
```

Result: `41 passed in 6.81s`

#### Manual CLI verification ✅
```bash
conda run -n guardrails-lite guardrails map show 405
conda run -n guardrails-lite guardrails map read 405 --lines 1-8
```

Verified output includes line-numbered source content and citation:
`#405 PageIndex 的可借鑑價值：Document Map + Tool-gated Reading L1-L8`

#### Manual MCP handler verification ✅
Direct `handle_tool_call()` checks passed for:
- `guardrails_map_show` with `knowledge_id=405`
- `guardrails_read_range` with `knowledge_id=405, line_start=1, line_end=8`
- `guardrails_read_range` with `knowledge_id=405, node_uid="摘要-1"`

Verified outputs include:
- tool registration names: `guardrails_map_show`, `guardrails_read_range`
- `nodes[]` from Document Map
- bounded `content`
- `content_hash`
- fixed `citation`
- node metadata when reading by `node_uid`

#### Manual search enrichment verification ✅
Keyword searches for mapped entry #405 were verified:
- Query: `PageIndex`
- Query: `先看全局地圖`

Returned enriched fields include:
- `node_uid='摘要-1'`
- `path='摘要'`
- `line_start=3`
- `line_end=3`
- `best_span='L3-L3'`
- `citation='#405 PageIndex 的可借鑑價值：Document Map + Tool-gated Reading L3-L3'`
- `recommended_next_tool='guardrails_read_range'`

Entries without map rows were also observed to remain backward-compatible with empty map fields.

#### Diff hygiene ✅
- `git diff --check` passed with no whitespace errors.

#### Full test suite note ⚠️
Full `pytest -q` was attempted but blocked during collection by existing environment dependencies unrelated to Sprint 2:
- `ModuleNotFoundError: No module named 'onnxruntime'` in `tests/test_e2e.py`
- `ModuleNotFoundError: No module named 'yaml'` in `tests/test_lite.py` and `tests/test_new_features.py`

Sprint 2 targeted tests pass.

#### Graphify update ✅
The AGENTS.md Python import command failed because the active Python environment cannot import `graphify` as a module. Correct current CLI path was found at `/home/zycas/miniconda3/bin/graphify`; code graph was updated with:

```bash
/home/zycas/miniconda3/bin/graphify update .
```

Result:
- `785 nodes`
- `1434 edges`
- `61 communities`
- Updated `graphify-out/graph.json` and `graphify-out/GRAPH_REPORT.md`

### Files Changed

#### Modified
- `guardrails_lite/guardrails_search.py`
- `guardrails_lite/guardrails_mcp.py`
- `/home/zycas/.hermes/skills/guardrails/SKILL.md`

#### Added
- `PROGRESS.md`
- `tests/test_search_map_integration.py`
- `tests/test_guardrails_mcp_map.py`

#### Preserved / Not Sprint 2
The following pre-existing untracked files were not touched:
- `_knowledge_base/`
- `scripts/cross_validate_cloud_only.py`
- `scripts/guardrails_gap_scanner.py`

### Next Sprint
Sprint 3 should focus on agent-loop behavior:
1. Ensure external agents actually follow `search → map_show → read_range`.
2. Add integration examples or harness checks that reject unsupported, citation-free answers.
3. Decide whether MCP result payloads should be more compact for high-volume agent use.

Sprint 4 remains the Supabase/schema synchronization phase and was intentionally not started in Sprint 2.
