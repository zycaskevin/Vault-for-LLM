# B2 — Document Map Coverage Plan

> **For Hermes:** This is the B2 design contract for internal Guardrails dogfood. The Document Map architecture already exists; B2 is about coverage, prioritization, verification, and feeding gaps into Search QA. Do not treat search previews as final evidence.

**Last updated:** 2026-05-18 10:34 CST

**Phase:** Phase B / B2 — Document Map coverage strengthening

**Status:** Design complete, implementation pending

**Depends on:**

- `docs/document_map_upgrade_plan.md` — original Document Map architecture
- `docs/session_writeback_governance.md` — B1 promote/readback/search-miss rules
- `docs/privacy_scanner_design.md` — B6 privacy/redaction boundary before mapping
- `docs/session_capture_draft_queue_design.md` — B5 drafts are not normal knowledge until promoted

**Next after this:** B3 internal Search QA metrics plan

---

## 0. Goal

Move Document Map from:

```text
tools exist → some entries have nodes
```

to:

```text
high-value knowledge is map-first readable
  → coverage is measurable
  → gaps are tracked
  → search/map/read traces are enforceable
  → missing coverage feeds B3 Search QA
```

B2 does not redesign the Document Map system. It operationalizes coverage for the internal Guardrails knowledge base.

---

## 1. Non-goals

B2 does **not**:

- rewrite search ranking,
- implement CJK tokenizer improvements,
- implement capture draft queue or privacy scanner code,
- build maps for all 714 entries in one pass,
- include unpromoted B5 drafts in coverage,
- weaken citation policy,
- treat search result `best_claim` or `citation` as final evidence,
- sync private/local-only material to Supabase.

---

## 2. Source of truth and scope

### 2.1 Source of truth

Local SQLite is canonical:

```text
/home/zycas/Guardrails-knowledge/guardrails.db
```

Supabase / Dashboard / remote read paths are sync and observability targets. Coverage reports must always state:

- timestamp,
- DB path,
- sample limit,
- whether numbers come from local SQLite or remote snapshot.

### 2.2 Coverage denominator

B2 coverage counts only formal `knowledge` rows.

Excluded from coverage denominator:

- B5 unpromoted drafts,
- blocked/no-write candidates,
- private drafts,
- raw transcripts,
- local handoff artifacts.

A captured session counts only after curated promotion to `raw/` + compile.

### 2.3 Privacy boundary

Build Document Map only over content that has passed B6 privacy rules.

If B6 redaction changes content, map must be built on the final redacted/promoted content, not the pre-redaction raw text.

---

## 3. Current local coverage snapshot

Snapshot collected from local SQLite and health collector.

```yaml
snapshot_at: 2026-05-18 10:34 CST
db_path: /home/zycas/Guardrails-knowledge/guardrails.db
sample_limit: 50
total_entries: 714
entries_with_nodes: 22
entries_with_claims: 13
entries_without_nodes: 692
entries_without_claims: 701
node_count: 258
claim_count: 113
map_coverage: 3.08%
claim_coverage: 1.82%
sampled_search_results: 50
search_results_with_best_span: 2
citation_coverage: 4.0%
read_range_over_limit_violations: 11
```

Important interpretation:

- Current full-library map coverage is intentionally low; B2 should focus on P0/P1 high-value entries first.
- Historical Dashboard/PROGRESS snapshots may differ; local DB snapshot above is the B2 source of truth.
- `read_range` may work without nodes, but that is not Document Map coverage.

---

## 4. Coverage metrics

### 4.1 Global metrics

| Metric | Definition |
|---|---|
| `map_coverage` | entries with at least one `knowledge_nodes` row / total knowledge entries |
| `claim_coverage` | entries with at least one `knowledge_claims` row / total knowledge entries |
| `entries_without_nodes` | formal entries without map nodes |
| `entries_without_claims` | formal entries without claims |
| `read_range_over_limit_violations` | sampled read ranges or nodes that exceed policy bounds |
| `citation_coverage` | sampled search results with usable best span/navigation metadata |

### 4.2 High-value metrics

B2 acceptance should focus on P0/P1, not full-library completion.

| Metric | Definition |
|---|---|
| `p0_map_coverage` | P0 entries with map nodes / total P0 entries |
| `p0_claim_coverage` | P0 entries with claims / total P0 entries |
| `p0_read_smoke_pass_rate` | P0 entries where map_show + read_range smoke passes |
| `top50_map_coverage` | top 50 prioritized entries with nodes / 50 |
| `top50_claim_coverage` | top 50 prioritized entries with claims / 50 |
| `top50_trace_pass_rate` | top 50 entries that support search → map_show → read_range trace |

### 4.3 Trace/policy metrics

| Metric | Definition |
|---|---|
| `trace_compliance_rate` | traces that include search, map_show, read_range, final exact citation |
| `search_only_citation_violations` | answers using search preview as evidence |
| `invented_citation_violations` | final citations not returned by read_range |
| `missing_map_show_violations` | read_range/final answer without prior map_show |
| `wrong_entry_citation_violations` | search/map/read knowledge_id mismatch |
| `overwide_read_violations` | attempts to read too many lines at once |

### 4.4 Gap metrics

| Gap | Meaning |
|---|---|
| `no_document_map_nodes` | entry has no nodes |
| `missing_claims` | entry has no claims |
| `map_stale_hash` | content hash changed after map build |
| `node_over_80_lines` | node too large for bounded read policy |
| `search_miss_but_exact_readable` | exact ID read works but search misses expected query |
| `no_best_span` | search result lacks useful span/navigation hint |
| `remote_sync_gap` | local has nodes/claims but remote read target does not |
| `local_remote_drift` | local and remote node hashes/counts differ |

---

## 5. Prioritization rules

B2 uses P0/P1/P2 rather than full-library blanket mapping.

### 5.1 P0 — must map first

P0 entries are rules that future agents rely on for safe behavior.

Include:

1. Phase B roadmap and design artifacts.
2. B1/B5/B6 governance/scanner/draft queue knowledge.
3. Document Map / read_range / citation policy entries.
4. Guardrails write/compile/sync/MCP/Supabase source-of-truth SOPs.
5. Privacy / no-write / private draft / Arthur profile boundary decisions.
6. Arthur-confirmed architecture or safety decisions likely to guide future agents.

### 5.2 P1 — second wave

Include:

1. release / repo hygiene / PyPI / GitHub Release / first-user smoke rules,
2. public/private boundary decisions,
3. agent behavior policy / Dashboard health / Search QA lessons,
4. high-trust long SOPs,
5. entries repeatedly missed by search but exact-readable.

### 5.3 P2 — backlog

Include:

1. short one-off notes,
2. daily/radar summaries,
3. low-trust or low-reuse items,
4. incomplete/unknown items not yet safe to cite,
5. private-only/no-write materials.

### 5.4 Priority score

Suggested formula:

```text
priority_score =
  +40 if Phase B / B1 / B2 / B3 / B5 / B6
  +30 if Guardrails SOP / compile / sync / MCP / Supabase
  +25 if Document Map / read_range / citation policy
  +25 if privacy / no-write / private draft / Arthur profile boundary
  +20 if Arthur-confirmed decision
  +15 if release / repo hygiene
  +10 if trust >= 0.8
  +10 if content length >= 40 lines or >= 1000 chars
  +5  if convergence_status = complete
  -20 if radar / daily report / one-off log
  -30 if private_only / no_write / blocked
```

---

## 6. Initial P0/P1 backlog

Current local DB inspection shows the following high-value entries need coverage.

### 6.1 P0 backlog

| ID | Title | Why | Nodes | Claims |
|---:|---|---|---:|---:|
| 734 | Phase B 內部百科真正能力建設路線：dogfood 逼出記憶治理問題 | Phase B master rule | 0 | 0 |
| 724 | 人生側寫寫入治理：原始心事不共享，協作規則才共享 | private/raw boundary | 0 | 0 |
| 679 | Guardrails 到 Harness 缺口：需要 Mistake-to-Rule 候選審查閉環 | governance/review loop | 0 | 0 |
| 439 | guardrails map read CLI 與 MCP read_range 參數差異 | Document Map tool pitfall | 0 | 0 |
| 454 | Guardrails Document Map Sprint 4A：compile hook + opt-in Supabase sync | compile hook / sync | 0 | 0 |
| 483 | Vault-for-LLM Document Map sync 原則：Local SQLite 是 source of truth，Supabase 只是 sync target | source-of-truth rule | 0 | 0 |
| 452 | Document Map citation policy：search citation 只能導航，final citation 必須來自 read_range | citation rule | 0 | 0 |
| 451 | Guardrails Document Map Sprint 3：Agent 行為閉環必須用 deterministic harness 驗證 | behavior harness | 0 | 0 |
| 456 | Sprint 4B remote Document Map read path | remote read path | 0 | 0 |
| 469 | Search QA expected_title_substrings 必須使用 AND 語義避免 false positive | Search QA correctness | 0 | 0 |

Already-mapped anchor:

| ID | Title | Nodes | Claims |
|---:|---|---:|---:|
| 405 | PageIndex 的可借鑑價值：Document Map + Tool-gated Reading | 6 | 10 |

### 6.2 P1 backlog

| ID | Title | Why | Nodes | Claims |
|---:|---|---|---:|---:|
| 714 | PyPI fresh install smoke 要在非 Git 目錄捕捉 git diff --cached 噪音 | release smoke pitfall | 0 | 0 |
| 683 | PyPI release smoke must install the built wheel and run real CLI flows | release gate | 0 | 0 |
| 710 | PyPI release docs truthfulness：repo fixtures 不等於 wheel-installed files | docs truthfulness | 0 | 0 |
| 719 | Git-assuming CLI hooks can leak stderr in non-Git first-user smoke | CLI hygiene | 0 | 0 |
| 561 | 網路技能安裝前必做安全、功能、系統符合度三軸審核 | Arthur-confirmed safety decision | 0 | 0 |
| 552 | Arthur Hermes Kanban 架構決策：Feishu 作入口與通知，Kanban 作任務作戰中樞 | Arthur architecture decision | 0 | 0 |
| 690 | Vault-for-LLM 與 agentmemory 借鑑：內部百科先行、開源版產品化輸出 | internal/public split | 0 | 0 |
| 691 | Vault-for-LLM P0 public boundary cleanup：Kanban 驅動開源治理流程 | public boundary process | 0 | 0 |

---

## 7. Build / verify workflow

For each prioritized entry:

```text
inventory entry
  → verify it is formal shared knowledge (not draft/private/no-write)
  → run privacy/safety check if needed
  → build Document Map
  → verify map_show
  → verify read_range
  → verify search enrichment/navigation hint
  → record coverage snapshot
  → if search/citation gap exists, create B3 Search QA backlog case
```

### 7.1 Build command

Preferred local command:

```bash
cd /home/zycas/Guardrails-knowledge
/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m guardrails_lite.guardrails_cli map build <knowledge_id>
```

If CLI syntax differs, check:

```bash
/home/zycas/miniconda3/envs/guardrails-lite/bin/python -m guardrails_lite.guardrails_cli map --help
```

### 7.2 Required map_show checks

`guardrails_map_show(id)` must return:

- non-empty `nodes`,
- stable `node_uid`,
- `heading`,
- `path`,
- `line_start`,
- `line_end`,
- `next_action` or `next_actions` pointing to `guardrails_read_range`.

### 7.3 Required read_range checks

`guardrails_read_range(id, node_uid=...)` must return:

- fixed `citation`,
- bounded range,
- line-numbered content,
- content from the same `knowledge_id`,
- no invented line numbers.

### 7.4 Over-limit checks

Any read over policy bounds should fail closed with:

- `failure_mode`,
- actionable `next_action`,
- segmentation guidance.

### 7.5 Search enrichment checks

For each P0/P1 entry, define at least one expected query.

If search does not find the entry but exact ID/read_range works:

- do not mark map build failed,
- record `search_miss_but_exact_readable`,
- create B3 Search QA backlog case.

---

## 8. Trace requirements

Standard answer trace when relying on encyclopedia content:

```text
guardrails_search(query)
  → guardrails_map_show(knowledge_id)
  → guardrails_read_range(knowledge_id, node_uid or line range)
  → final answer using exact read_range citation
```

### 8.1 Policy violations

| Violation | Meaning |
|---|---|
| `search_only_evidence` | final answer relies on search preview/best_claim only |
| `missing_map_show` | answer uses read_range without map_show when map exists |
| `invented_citation` | citation not returned by read_range |
| `wrong_entry_citation` | search/map/read IDs do not match |
| `overwide_read` | attempt to read too many lines at once |
| `no_nodes_unhandled` | map_show returns no nodes but gap is not recorded |

### 8.2 Missing map nuance

`read_range` can return a valid citation even if no map nodes exist. That counts as:

- citation validity: pass,
- Document Map coverage: fail,
- trace policy: gap unless missing map is explicitly recorded and followed up.

Example observed:

- #734 has no nodes and `map_show` returns `no_document_map_nodes`.
- `read_range #734 L1-L20` still returns a valid citation.
- B2 should build map for #734 and add search/trace cases to B3.

---

## 9. Gap schema and B3 Search QA feed

Every coverage gap should be representable as:

```yaml
gap_id: "b2-gap-YYYYMMDD-001"
knowledge_id: 734
title: "Phase B 內部百科真正能力建設路線：dogfood 逼出記憶治理問題"
gap_type:
  - no_document_map_nodes
  - missing_claims
  - search_miss
  - no_best_span
  - read_range_over_limit
  - remote_sync_gap
priority: P0
expected_query:
  - "Phase B 內部百科 Document Map"
  - "對話回寫治理 privacy scanner draft queue"
expected_title_substrings:
  - "Phase B"
  - "內部百科"
expected_knowledge_ids:
  - 734
should_have_map_guidance: true
should_require_read_range: true
language: zh-Hant
owner: "B2/B3"
status: open
```

B3 Search QA should consume these fields for:

- top1 hit,
- hit@k,
- MRR,
- map guidance rate,
- read_range guidance rate,
- citation policy violations,
- CJK recall.

---

## 10. Edge cases

1. **Short entry without headings**
   - Build a root node; do not leave unmapped only because the entry is short.

2. **Code fence headings**
   - Markdown parser must not treat `#` inside code fences as headings.

3. **Duplicate CJK headings**
   - `node_uid` must remain stable and collision-safe.

4. **Emoji or punctuation headings**
   - heading parsing should preserve readability while making safe `node_uid`.

5. **Content hash drift**
   - If `content_hash` differs, mark map stale and rebuild.

6. **Nodes without claims / claims without nodes**
   - Track independently; both are coverage gaps.

7. **Node over 80 lines**
   - Split or recommend segmented reads; do not recommend one huge read.

8. **Local/remote drift**
   - Local coverage is canonical; remote mismatch is sync gap.

9. **B5 draft not promoted**
   - Drafts are excluded from B2 normal coverage.

10. **B6 redaction changed content**
    - Build maps only on final redacted/promoted content.

11. **Search miss but exact-readable**
    - Treat as Search QA issue, not mapping failure.

12. **search result has best_span but no read_range citation**
    - Search span remains navigation only.

---

## 11. Acceptance criteria

B2 coverage pass is accepted when:

- [ ] P0 backlog has 100% map nodes.
- [ ] P0 backlog has at least 90% claims coverage.
- [ ] P0 `map_show` smoke passes for every entry.
- [ ] P0 `read_range` smoke passes for at least one useful node per entry.
- [ ] P0 read-range over-limit violations are zero or have explicit segmentation backlog.
- [ ] Top 50 high-value entries are inventoried and prioritized.
- [ ] Every gap can be serialized into B3 Search QA backlog schema.
- [ ] Policy harness rejects search-only, invented, wrong-ID, and over-wide citations.
- [ ] Coverage reports include timestamp, DB path, and sample limit.
- [ ] Local/remote coverage differences are reported as sync gaps, not local failures.

---

## 12. Smoke checks

### 12.1 Health snapshot

```bash
cd /home/zycas/Guardrails-knowledge
/home/zycas/miniconda3/envs/guardrails-lite/bin/python - <<'PY'
from guardrails_lite.guardrails_health import collect_guardrails_health_metrics
m = collect_guardrails_health_metrics('guardrails.db', sample_limit=50)
print(m.to_dict())
PY
```

Expected fields:

- `total_entries`
- `entries_with_nodes`
- `entries_with_claims`
- `map_coverage`
- `claim_coverage`
- `citation_coverage`
- `read_range_over_limit_violations`

### 12.2 Missing-map smoke

Use #734:

```text
guardrails_map_show(734)
```

Expected before B2 build:

- `failure_mode = no_document_map_nodes`,
- actionable `next_action.tool = guardrails_map_build`.

### 12.3 Mapped-entry smoke

Use #405:

```text
guardrails_map_show(405)
```

Expected:

- non-empty nodes,
- `next_action.tool = guardrails_read_range`,
- stable node UIDs.

### 12.4 read_range citation smoke

```text
guardrails_read_range(405, node_uid="...")
```

Expected:

- fixed `citation`,
- bounded line-numbered content,
- final answer can quote exactly that citation.

### 12.5 Search / trace smoke

Queries:

- `Phase B 內部百科 Document Map`
- `privacy scanner draft queue`
- `PyPI release smoke`
- `guardrails read_range MCP`

Expected:

- intended ID appears in top-k after backlog remediation,
- result includes map/read guidance when nodes exist,
- misses create B3 backlog case.

---

## 13. Implementation tasks after B2

### Task B2-T1 — Add coverage inventory script

Create a script that outputs P0/P1 missing nodes/claims with priority score.

### Task B2-T2 — Build maps for P0 entries

Run map build for P0 entries and verify `map_show` / `read_range`.

### Task B2-T3 — Add coverage report output

Produce JSON/Markdown report with metrics, gaps, and B3 backlog cases.

### Task B2-T4 — Add Search QA backlog fixtures

Convert gaps into internal B3 QA cases.

### Task B2-T5 — Add local/remote drift smoke

Compare local map nodes with remote read targets when Supabase credentials are available.

---

## 14. Current decision

Proceed next to **B3 internal Search QA metrics plan**, unless Arthur asks to start implementation for B1/B6/B5/B2 first.

Rationale:

- B1/B6/B5 define safe write/capture boundaries.
- B2 defines map/citation coverage and gap schema.
- B3 is needed before changing retrieval or CJK behavior, so improvements can be measured rather than judged by vibes.
