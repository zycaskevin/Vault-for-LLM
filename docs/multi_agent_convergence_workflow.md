# B7 — Multi-agent Writing and Convergence Workflow

> **For Hermes:** This is the B7 design contract for internal Guardrails dogfood. Multi-agent knowledge contribution must stay review-gated, local-first, provenance-rich, and privacy-safe. Do not let agents write directly into formal knowledge, delete duplicates automatically, or sync private material to public targets.

**Last updated:** 2026-05-18 12:11 CST

**Phase:** Phase B / B7 — 多 Agent 寫入與收斂流程

**Status:** Design complete, implementation pending

**Depends on:**

- `docs/session_writeback_governance.md` — B1 classification, review, dedupe, promote rules
- `docs/privacy_scanner_design.md` — B6 scanner outcomes, redaction, override, audit contract
- `docs/session_capture_draft_queue_design.md` — B5 draft queue lifecycle and promotion boundary
- `docs/document_map_coverage_plan.md` — B2 map/read_range/citation coverage rules
- `docs/search_qa_metrics_plan.md` — B3 internal Search QA regression set
- `PROGRESS.md` — B4 CJK / alias retrieval implementation status

**Next after this:** Implement the smallest safe B7 slice: report-only dedupe/conflict/convergence/freshness queue, with no auto-promote and no destructive merge.

---

## 0. Goal

B7 turns Guardrails from:

```text
one agent writes a useful note
  → maybe another agent writes a similar note
  → compile/sync might dedupe later
  → freshness/convergence reports exist but are not operational queues
```

into:

```text
many agents propose knowledge
  → candidates stay in append-only draft/review state
  → duplicate/conflict/freshness/convergence signals become queues
  → one coordinator promotes/merges with provenance
  → local SQLite/raw remains source of truth
  → Supabase and public Vault-for-LLM slices receive only verified safe material
```

The product promise is not “agents can write anything automatically.” The promise is:

> Multiple agents can contribute knowledge without overwriting, duplicating, leaking, or polluting the shared brain.

---

## 1. Non-goals

B7 does **not**:

- implement silent auto-capture,
- allow subagents, cron jobs, or MCP tools to auto-promote raw session content,
- make Supabase the merge source of truth,
- expose private/internal Guardrails entries directly as public Vault-for-LLM content,
- rewrite CJK ranking/tokenization after B4,
- weaken citation policy,
- use `scripts/deduplicate_semantic.py --merge` as the final merge engine,
- treat search snippets or `best_claim` as final evidence,
- solve all schema migrations in this design phase.

B7 is the governance and orchestration layer that decides **when** existing tools may be called, **who** may call them, and **what evidence** proves the result is safe.

---

## 2. Current implementation reality to preserve

### 2.1 CLI and storage surfaces

Current entry points include:

```text
vault add / guardrails add
vault compile / guardrails compile
vault dedup
vault converge
vault freshness
vault map build/show/read
vault search-qa run/compare
scripts/sync_to_supabase.py
```

Important current behavior:

- `cmd_add()` writes a SQLite `knowledge` row and a `raw/{title}.md` file.
- MCP `guardrails_add` writes a DB row only; it does not write `raw/`, compile, create Document Map nodes, or run Search QA.
- `compile` scans `raw/**/*.md`, updates SQLite, writes `compiled/`, writes AAAK files, refreshes Document Map for changed entries, and may attempt a git commit.
- Exact title dedupe currently happens inside non-dry-run compile and deletes later same-title rows.
- `dedup`, `converge`, and `freshness` “preview” commands are not fully read-only because they may write report JSON files.
- Search QA is report-only and currently ignores some forward-compatible metadata in `qa/internal_guardrails_search_qa/core.json`.
- Supabase sync is local → remote; remote is not canonical.

### 2.2 Immediate B7 consequence

B7 must not tell every agent to call `guardrails_add` or MCP `guardrails_add` freely. Formal writes must go through:

```text
candidate/draft
  → review decision
  → exact promoted content
  → B6 scan
  → raw write or controlled update
  → compile/map/readback/search-qa
  → optional sync
```

---

## 3. Core invariants

1. **Local-first source of truth.**
   - Local SQLite plus curated `raw/` are canonical.
   - Supabase, Dashboard, remote map tools, and public exports are sync/observability targets only.

2. **Drafts are not knowledge.**
   - Unpromoted drafts must not enter `raw/`, `knowledge`, `knowledge_vec`, normal search, MCP search, or Supabase sync.

3. **No auto-promote.**
   - Subagents, cron jobs, Search QA, freshness reports, convergence reports, and dedupe reports may propose actions, not execute formal knowledge changes.

4. **Privacy gate before every boundary crossing.**
   - B6 scan must run before storing drafts, promoting raw, compiling, syncing, and exporting public slices.

5. **Append-only audit.**
   - Multi-agent decisions are recorded as events; history is preserved even when entries are merged or superseded.

6. **Merge beats duplicate.**
   - Same lesson should update/merge into existing knowledge unless there is a clear reason to create a linked new entry.

7. **Contradiction is review, not overwrite.**
   - Conflicting claims move to contradiction review and cannot silently replace existing knowledge.

8. **Search is not final evidence.**
   - Search result citations remain navigation hints. Final evidence requires `map_show/read_range` fixed citations.

9. **Public export is allowlisted.**
   - Public Vault-for-LLM slices are curated transformations with provenance, not raw internal dumps.

---

## 4. Actors and permissions

| Actor | Can propose candidate? | Can write draft? | Can promote formal knowledge? | Can sync/export? | Notes |
|---|---:|---:|---:|---:|---|
| Arthur | yes | yes | yes | approve | Final human approval for sensitive/public boundaries |
| Nancy coordinator | yes | yes | yes, when explicitly in task scope | yes, after gates | Must verify exact ID/path/readback before claiming success |
| Subagent | yes | no direct formal write | no | no | Returns evidence handles only; parent verifies |
| MCP `guardrails_add` | yes for curated direct add only | no | risky, should be restricted | no | B7 should steer away from direct MCP add for session capture |
| Cron job | yes, report-only | draft-only if explicitly configured | no | no | No recursive scheduling, no private text sync |
| Feishu review flow | yes | review action | explicit decision only | no | Reply-only “寫入” must recover proposal context safely |
| Sync script | no | no | no | yes | Local → remote target, never reverse-merge by itself |

---

## 5. Canonical state model

B7 reuses B5 draft isolation and adds convergence-oriented states.

```text
candidate_detected
  → classified
  → privacy_scanned
  → pending_dedupe
  → pending_review
  → duplicate_review
  → merge_review
  → contradiction_review
  → promote_ready
  → promoted
  → merged
  → discarded
  → blocked
  → sync_ready
  → synced
  → public_export_candidate
  → public_exported
```

### 5.1 State rules

| State | Meaning | Allowed next actions |
|---|---|---|
| `candidate_detected` | Extracted from session/subagent/cron/manual note | classify, discard |
| `classified` | B1 category decided | B6 scan |
| `privacy_scanned` | B6 outcome stored | dedupe, block, redact |
| `pending_dedupe` | Needs duplicate/conflict search | pending_review, duplicate_review, contradiction_review |
| `pending_review` | Safe enough for human/explicit agent review | promote_ready, merge_review, discard |
| `duplicate_review` | Same or near-same entry found | merge_review, discard, promote as linked entry |
| `merge_review` | Update existing entry instead of new entry | merged, contradiction_review |
| `contradiction_review` | Claim conflicts with existing knowledge | supersede, keep both, resolve, block |
| `promote_ready` | Exact content approved | final scan, raw write/update |
| `promoted` | Formal local knowledge exists and is read back | compile/map/search-qa/sync_ready |
| `merged` | Existing entry updated with provenance | compile/map/search-qa/sync_ready |
| `discarded` | Not useful enough | audit only |
| `blocked` | Secret/private/no-write content | audit only, no body |
| `sync_ready` | Local verification passed | Supabase sync dry-run/real sync |
| `synced` | Remote target verified | optional public export review |
| `public_export_candidate` | Internal entry can become public-safe slice | transform/redact/review |
| `public_exported` | Public slice emitted with manifest | maintain/revoke/update |

---

## 6. Required metadata and audit trail

Every candidate/draft/review action should preserve safe metadata.

### 6.1 Candidate/draft metadata

```json
{
  "schema_version": 1,
  "candidate_id": "cand_...",
  "draft_id": "draft_...",
  "status": "pending_review",
  "classification": "shared_knowledge",
  "privacy_outcome": "clear",
  "source_agent": "nancy|subagent:<id>|cron:<job>|manual",
  "source_session_id": "safe-session-ref",
  "source_channel": "feishu|local|telegram|cron",
  "source_refs": [],
  "proposed_title": "...",
  "summary": "...",
  "content_fingerprint": "sha256:...",
  "nearest_existing_ids": [],
  "conflict_candidate_ids": [],
  "trust_initial": 0.4,
  "freshness_initial": 1.0,
  "convergence_status_initial": "unknown",
  "reviewer": "",
  "decision_reason": ""
}
```

### 6.2 Audit events

Append-only events should record:

- timestamp,
- actor,
- action,
- before state,
- after state,
- redacted reason,
- evidence handle,
- affected local `knowledge_id`,
- affected `raw/` path,
- sync target/result if any.

Do not store raw secrets, raw customer data, or raw private life material in audit notes.

---

## 7. Write lock and idempotency protocol

B7 needs a lightweight lock even before full schema implementation.

### 7.1 Lock scope

Lock by the strongest available key:

```text
content_fingerprint
  → normalized_title
  → existing knowledge_id
  → source_session_id + candidate ordinal
```

A lock protects the promotion/merge critical section:

```text
final B6 scan
  → write raw/update existing raw
  → compile
  → exact readback
  → map/read_range verification
  → Search QA smoke
  → sync decision
```

### 7.2 Idempotency requirements

- Same candidate imported twice should return the same draft/candidate state, not create duplicates.
- Same title + same content hash should become `already_promoted` or `already_merged`.
- Same title + different content hash should enter `merge_review` or `contradiction_review`.
- MCP add + local sync must not create two formal entries for the same lesson.
- Sync retries must be safe; remote duplicate detection should report drift instead of silently updating broad fuzzy matches.

---

## 8. Duplicate detection workflow

Promotion must run duplicate detection before writing formal knowledge.

```text
candidate
  → exact title lookup
  → normalized title lookup
  → tag/category keyword lookup
  → semantic/hybrid search
  → graph neighbor search
  → source-known ID lookup
  → content fingerprint lookup
  → duplicate decision
```

### 8.1 Duplicate classes

| Class | Condition | Decision |
|---|---|---|
| `exact_same` | same normalized title + same content hash | do not write; mark already present |
| `same_lesson` | same root lesson with updated evidence | merge/update existing entry |
| `same_topic_new_edge_case` | same topic but new constraint/pitfall | append dated update or linked entry |
| `near_duplicate_uncertain` | similar but not clear | human/explicit reviewer decision |
| `not_duplicate` | materially different | can promote as new entry |

### 8.2 Current tool use boundary

Existing commands can provide signals:

```bash
python -m guardrails_lite.guardrails_cli search "<title/keywords>"
python -m guardrails_lite.guardrails_cli dedup --threshold 0.85 --dry-run
```

But current semantic dedup merge is not safe as the final B7 merge engine because it may delete rows and does not preserve rich history. Treat it as a report source only.

---

## 9. Merge and update policy

### 9.1 Prefer update notes for same knowledge

If the new candidate improves an existing entry, update the existing entry with a dated section:

```md
## Update YYYY-MM-DD — {short reason}

- New observation: ...
- What changed: ...
- What remains true: ...
- Evidence/source handle: ...
- Reviewer: ...
```

### 9.2 Create linked entries when needed

Create a new entry only when:

- the scope is genuinely different,
- the old entry would become too broad,
- the new lesson belongs to another subsystem,
- public-safe transformation requires a separate product-neutral entry,
- contradiction is unresolved and both claims must remain visible.

### 9.3 Never merge by deleting history

Do not merge by:

- keeping only the higher-trust row,
- deleting later entries without copying evidence,
- overwriting old conclusions without dated context,
- letting remote sync overwrite local source of truth.

---

## 10. Conflict and contradiction handling

### 10.1 Conflict types

| Type | Example | Handling |
|---|---|---|
| `title_conflict` | Same title, different content | merge review |
| `claim_conflict` | One entry says tool X is source of truth, another says tool Y | contradiction review |
| `freshness_conflict` | Old SOP is stale after API change | dated update + freshness reset |
| `privacy_conflict` | Useful lesson includes private raw detail | transform to general rule or block |
| `sync_conflict` | Remote has row that local does not recognize | report drift; do not reverse overwrite |
| `public_export_conflict` | Public slice would reveal internal implementation | transform/redact/reject |

### 10.2 Contradiction review decisions

A contradiction can resolve to:

- `superseded`: old claim no longer true; keep history and mark superseded.
- `contextual`: both claims true under different conditions; document conditions.
- `unresolved`: keep both and require future verification.
- `blocked`: conflict involves unsafe/private material; no formal shared write.

---

## 11. Convergence queue

Existing `converge` can score incomplete entries, but B7 must turn the result into a review queue.

### 11.1 Queue inputs

- `convergence_status = unknown`,
- `convergence_status = partial`,
- low trust but high usage,
- Search QA misses for important entries,
- Document Map entries with missing claims,
- newly promoted entries without follow-up verification.

### 11.2 Queue item fields

```json
{
  "knowledge_id": 123,
  "title": "...",
  "current_status": "partial",
  "score": 0.62,
  "reason": "missing edge-case explanation",
  "required_evidence": ["read_range", "test command", "source doc"],
  "owner": "nancy",
  "priority": "P0|P1|P2",
  "review_action": "expand|merge|verify|defer|discard",
  "created_at": "..."
}
```

### 11.3 Operating rule

`converge --apply` may update status fields, but it must not rewrite knowledge content. Content changes require merge/update review and normal promotion gates.

---

## 12. Freshness queue

Freshness is not a passive score. B7 uses it as a re-verification queue.

### 12.1 Queue inputs

- freshness status `stale` or `critical`,
- old entries touched by new contradictory evidence,
- entries about fast-moving tools/APIs,
- public-safe exports whose internal source changed,
- entries that fail current smoke commands.

### 12.2 Review actions

| Freshness state | Action |
|---|---|
| `fresh` | no action |
| `stale` | verify source, run smoke if applicable, update `last_verified` |
| `critical` | prioritize review; mark warnings in search/result metadata if needed |
| `superseded` | preserve old entry, link to replacement |

Freshness reports should feed queue items. They should not automatically demote valuable knowledge into invisibility.

---

## 13. Promotion pipeline

Formal promotion should be one controlled transaction-like flow.

```text
review decision
  → exact final content assembled
  → B6 final scan
  → acquire write lock
  → duplicate/conflict check refreshed
  → raw write or existing raw update
  → compile --no-embed or controlled compile path
  → exact SQLite readback by id/title/content_hash
  → Document Map build/show
  → read_range smoke for changed entry
  → Search QA smoke / backlog update
  → git diff review
  → scoped commit
  → optional Supabase sync
```

### 13.1 Minimum verification before claiming success

Do not say “已寫入 / 已同步 / 已完成” unless the same turn verifies:

- target raw path or exact local ID,
- SQLite title/summary/tags readback,
- privacy classification/outcome,
- compile/map result or explicit reason it was not run,
- sync result if claiming remote sync,
- Search QA status if claiming no regression.

### 13.2 Search miss after promote

If exact ID/title readback passes but semantic search does not rank it, classify as:

```text
write success + retrieval backlog
```

Do not re-add the same knowledge to “fix search.”

---

## 14. Safe sync to Supabase

Supabase remains a sync target.

### 14.1 Pre-sync gates

Before `scripts/sync_to_supabase.py` or `--document-map`:

- local exact readback passed,
- B6 scan clear or redacted/approved,
- no `private_only` / `blocked` material,
- no draft/private/no-write entries included,
- drift report reviewed for high-risk conflicts,
- if syncing Document Map, local nodes/claims exist or missing coverage is explicitly logged.

### 14.2 Remote drift handling

Remote/local differences should produce a sync gap report:

- `remote_extra`: remote row not recognized locally,
- `local_missing_remote`: local row not synced,
- `title_collision`: broad/fuzzy title match could update multiple rows,
- `content_hash_mismatch`: same title, different content hash,
- `map_or_claim_gap`: remote map target missing nodes/claims.

Do not let remote overwrite local automatically.

---

## 15. Public-safe Vault-for-LLM slice export

Public Vault-for-LLM output must be allowlisted and transformed.

### 15.1 Public-safe criteria

A public slice must be:

- product-neutral,
- free of Arthur/customer/private life raw details,
- free of secrets, tokens, private endpoints, and local credentials,
- testable in a clean environment,
- understandable without internal Guardrails context,
- backed by public-safe provenance.

### 15.2 Export manifest

Each exported slice should record:

```json
{
  "public_slice_id": "...",
  "internal_knowledge_ids": [123],
  "source_content_hashes": ["sha256:..."],
  "transform_hash": "sha256:...",
  "redaction_policy_version": "...",
  "reviewer": "...",
  "export_decision": "approved|rejected|needs_redaction",
  "target_repo": "Vault-for-LLM",
  "target_paths": []
}
```

Public export is not `sync_to_supabase.py`. It is a separate curated transform pipeline.

---

## 16. Metrics and reporting

B7 reporting should answer “is the shared brain getting cleaner?”

| Metric | Meaning |
|---|---|
| candidate count | How many proposed lessons were found |
| blocked/no-write count | Privacy/safety filtering volume |
| duplicate_review count | Potential duplicates needing merge |
| merge count | Successful consolidation |
| contradiction_review count | Conflicting claims awaiting decision |
| unknown/partial convergence count | Knowledge not yet complete |
| stale/critical freshness count | Entries needing re-verification |
| Search QA deltas | Retrieval quality change after writes/merges |
| sync drift count | Remote/local divergence |
| public export candidates | Internal lessons potentially safe for Vault-for-LLM |
| public export rejected count | Material that must stay internal |

Feishu reports should show decisions and next actions, not raw private content.

---

## 17. CLI / MCP / Feishu / cron UX sketch

These are future commands; they are not implemented yet.

```bash
# Report-only import
vault capture import --file session.jsonl --dry-run

# Write review-gated drafts only
vault capture import --file session.jsonl --write-drafts

# List queues
vault queue list --type duplicate
vault queue list --type contradiction
vault queue list --type convergence
vault queue list --type freshness

# Review decisions
vault draft review <draft_id> --decision promote
vault draft review <draft_id> --decision merge --with <knowledge_id>
vault draft review <draft_id> --decision block

# Report-only B7 health
vault b7 report --dedupe --convergence --freshness --search-qa

# Safe sync dry-run
vault sync plan --supabase --document-map

# Public-safe export plan
vault export public-plan --manifest public_slices/manifest.json
```

MCP tools should expose only safe review/report actions by default. Any direct write tool must include explicit content, scanner outcome, idempotency key, and a final evidence handle.

---

## 18. Edge cases

### 18.1 MCP add bypass

If an agent uses MCP add directly for a session lesson, B7 must mark it as a bypass risk and reconcile:

```text
exact title/id readback
  → raw file missing?
  → compile/map missing?
  → duplicate local row?
  → create remediation queue item
```

### 18.2 Concurrent agents propose same lesson

Only the first promote lock may write. Other candidates become duplicate/merge review items linked to the promoted ID.

### 18.3 Private story contains reusable rule

Store only the abstracted rule:

```text
private raw story → no-write/private draft
reusable operational lesson → separate shared_knowledge candidate
```

### 18.4 Search QA regresses after merge

Do not revert blindly. Classify:

- retrieval ranking regression,
- title/tag/summary degradation,
- CJK alias gap,
- Document Map guidance gap,
- expected QA case stale.

### 18.5 Public export duplicate

If two internal entries map to the same public-safe lesson, produce one public slice with multiple internal provenance IDs.

---

## 19. Smoke checks

B7 implementation should add deterministic tests for:

1. **Draft invisibility**
   - A draft exists, but `guardrails search` cannot find it.

2. **Idempotent import**
   - Same session/candidate imported twice yields one draft/candidate.

3. **Duplicate no-double-write**
   - Same title/content promoted twice does not create two `knowledge` rows.

4. **Same title different content**
   - Enters merge/contradiction review instead of overwriting.

5. **MCP bypass remediation**
   - DB-only row is detected as missing raw/map/compiled artifacts.

6. **Privacy block before sync**
   - `private_only` or `blocked` material cannot enter Supabase sync plan.

7. **Convergence queue creation**
   - `unknown` / `partial` entries become queue items without content rewrite.

8. **Freshness queue creation**
   - stale/critical entries become review items, not hidden entries.

9. **Search QA snapshot metadata**
   - Before/after snapshot carries git SHA, DB path/hash, QA set hash, evaluator version.

10. **Public slice manifest**
    - Exported public content has manifest, hashes, reviewer, and redaction decision.

---

## 20. Acceptance criteria

B7 is acceptable when:

- the same knowledge cannot be duplicated by MCP add + local sync without a warning/remediation item,
- sync never overwrites new local knowledge without drift reporting,
- partial/unknown convergence states feed a fixed queue,
- stale/critical freshness states feed a fixed queue,
- multi-agent writes preserve source_agent/source_session/trust/reviewer metadata,
- subagents can propose but cannot directly promote formal knowledge,
- promoted knowledge can be verified by exact ID/title/readback and `read_range`,
- public-safe Vault-for-LLM slices require allowlist/manifest/redaction provenance,
- Feishu reports show redacted decisions and next actions only.

---

## 21. Implementation backlog

### B7-T1 — Queue schema and audit tables

- Add tables for queue items and audit events.
- Include state, source metadata, content fingerprint, nearest IDs, reviewer, decision reason.
- Migration must preserve existing `knowledge` rows.

### B7-T2 — Report-only dedupe/conflict detector

- Produce exact-title, normalized-title, content-hash, semantic, and graph-neighbor duplicate candidates.
- No destructive merge.
- Output queue-ready JSON.

### B7-T3 — Convergence/freshness queue integration

- Wrap existing `converge` and `freshness` outputs into review queue items.
- Redirect report JSON to controlled output paths to avoid multi-agent overwrites.

### B7-T4 — Promotion lock and idempotency

- Implement lock/idempotency key around promote/merge.
- Add same-candidate retry tests.

### B7-T5 — MCP/direct-add bypass detection

- Detect DB-only entries missing raw/compiled/map provenance.
- Create remediation queue items instead of silently syncing.

### B7-T6 — Safe sync plan

- Add dry-run sync planner with local/remote drift classes.
- Gate sync on scanner outcome and draft exclusion.

### B7-T7 — Public slice exporter design-to-implementation

- Implement allowlist manifest and redaction transform.
- Verify generated public files are clean and testable.

### B7-T8 — Search QA hardening needed by B7

- Implement `expected_hit: false` semantics for negative controls.
- Add segment metrics.
- Add misses/regressions arrays.
- Add snapshot metadata: git SHA, DB path/hash, QA hash, evaluator version.

---

## 22. Suggested first implementation slice

The safest first slice is report-only:

```text
B7-T2 + B7-T3 small subset
  → no schema mutation except optional queue tables
  → no destructive merge
  → no sync
  → produces Feishu-friendly report
  → lets Nancy see duplicate/conflict/convergence/freshness pressure before building write automation
```

This matches Phase B’s principle: dogfood the internal brain first, then extract public-safe product slices later.
