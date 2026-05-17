# B1 — Session Writeback Governance

> **For Hermes:** This is the B1 governance contract for internal Guardrails dogfood. It defines what can become shared knowledge, what must stay private draft, and what must never be written. Do not implement capture automation until this document is satisfied.

**Last updated:** 2026-05-18 01:39 CST

**Phase:** Phase B / B1 — 對話回寫治理

**Status:** Design complete, implementation pending

**Scope:** Nancy / Hermes / Guardrails internal session writeback governance

---

## 0. Goal

Move from:

```text
valuable conversation happened → ask Arthur → write directly to百科
```

to:

```text
session
  → candidate extraction
  → classification
  → privacy preflight
  → dedupe / merge check
  → draft
  → review
  → promote / merge / discard / block
```

B1 is not a full capture queue implementation. B1 is the governance layer that future B5 draft queue, B6 privacy scanner, and B7 multi-agent convergence must obey.

## 1. Non-goals

B1 does **not** implement:

- full `capture_drafts` DB table,
- full privacy scanner engine,
- full CJK search improvements,
- full ranking / retrieval rewrite,
- automatic promotion into `raw/`,
- silent auto-capture,
- public Vault-for-LLM packaging or release hygiene.

B1 only defines the rules and acceptance criteria that make those later systems safe.

---

## 2. Core invariants

1. **Session capture never writes directly to normal search.**
   - It can produce candidates or drafts.
   - It cannot silently create trusted shared knowledge.

2. **Search previews are not evidence.**
   - Candidate discovery may use search.
   - Final claims still require promoted knowledge and, for long entries, `read_range` citation.

3. **Private raw material does not become shared memory.**
   - Personal life-profile raw text, client details, secrets, and internal credentials are never copied into shared knowledge.
   - At most, extract general collaboration rules after review.

4. **Local Guardrails remains source of truth.**
   - Supabase is a sync/read target.
   - MCP-only writes must not be allowed to bypass local governance.

5. **When uncertain, draft or block — do not promote.**
   - Default state for extracted session material is `pending` draft.
   - Promotion requires explicit review decision.

---

## 3. End-to-end lifecycle

```text
[1] Source session / transcript / message
        ↓
[2] Candidate extraction
        ↓
[3] Classification: shared / private / no-write
        ↓
[4] Privacy preflight
        ↓
[5] Dedupe and merge check
        ↓
[6] Draft creation or block
        ↓
[7] Review decision
        ├─ promote → raw/ + compile + map + verify
        ├─ merge   → update existing knowledge + compile + verify
        ├─ discard → audit reason only
        └─ block   → no raw content stored
```

No step may skip privacy preflight and dedupe before promotion.

---

## 4. Trigger model

### 4.1 Candidate extraction triggers

A session may produce writeback candidates when any of the following occurs:

| Trigger | Candidate? | Notes |
|---|---|---|
| Arthur explicitly says `寫入` / `記起來` / `這是踩坑` | yes | Still run classification, privacy, dedupe. |
| >5 tool calls and a reusable lesson appeared | yes | Candidate list only; no auto-promote. |
| Architecture decision | yes | Record option chosen, rejected alternatives, reason. |
| Bug fix or debugging >30 minutes | yes | Record symptom, root cause, fix, verification. |
| Workflow/SOP discovered | yes | Record exact order, commands, pitfalls. |
| Tool/API quirk discovered | yes | Record verified behavior and safe workaround. |
| Pure task progress | usually no | Use handoff/session history, not shared knowledge. |
| One-off operational action | usually no | Unless it reveals reusable SOP or pitfall. |
| Unverified guess | no | Can stay as private note until verified. |

### 4.2 Reply-only `寫入` behavior

If Arthur replies only `寫入` in Feishu, treat it as confirmation of the immediately previous writeback proposal.

Rules:

1. Do not ask Arthur to repeat the content.
2. Recover the proposal from current session context or `session_search`.
3. If the proposal listed multiple items and Arthur did not restrict scope, write all proposed items.
4. Still run classification, privacy, and dedupe.
5. If context cannot be recovered, ask one clarifying question instead of guessing.

---

## 5. Classification model

Every candidate must be classified before storage.

| Class | Definition | Normal search visibility | Default decision |
|---|---|---:|---|
| `shared_knowledge` | Reusable technical, operational, architectural, or workflow knowledge safe across agents | only after promote | pending review |
| `private_draft` | Contains personal context, client context, internal environment details, or sensitive raw session material | never by default | pending private review |
| `no_write` | Secrets, credentials, raw private life material, client PII, irrelevant one-off logs, unverifiable guesses | never | block/discard |

### 5.1 Shared knowledge examples

Can become shared knowledge after review:

- Debugging root cause and reusable fix.
- Architecture decision with trade-offs.
- Tool workflow or verified command sequence.
- Agent behavior observation that prevents future errors.
- Public-safe release or repo hygiene rule.
- Guardrails operation SOP.

### 5.2 Private draft examples

Must stay private draft unless manually transformed:

- Arthur personal life context.
- Marriage, family, child, relationship, or mental-state raw conversation.
- Client/customer context even if anonymized poorly.
- Internal deployment detail useful only in Arthur's private environment.
- Messages that mix a reusable rule with private story.

Private draft transformation rule:

```text
raw private material → extract general collaboration rule → discard raw text → review → optional shared knowledge
```

Example:

- Raw: private life event and emotional details.
- Shared-safe transformed rule: `For Arthur life-profile work, store only collaboration rules and safety boundaries; do not share raw personal narrative across agents.`

### 5.3 No-write examples

Always block from shared or private draft storage unless explicitly redacted before storage:

- API keys, PyPI tokens, GitHub tokens, bearer tokens.
- Private keys, `.env`, `.pypirc`, cookies, session tokens.
- Customer names, phones, emails, addresses, treatment records, payment data.
- Raw intimate/personal messages that do not need operational memory.
- One-off task status, PR numbers, commit SHAs, temporary file paths, unless part of a reusable SOP.
- Unverified speculation.

---

## 6. Candidate schema

B1 does not mandate storage implementation, but every draft candidate must be representable as:

```yaml
draft_id: "draft_YYYYMMDD_HHMMSS_slug"
source_session_id: "Hermes session id or platform thread id"
source_agent: "nancy|subagent|cron|manual"
source_channel: "feishu|cli|mcp|cron|telegram|local"
source_refs:
  - "message id / handoff path / transcript path, if safe"
extracted_at: "YYYY-MM-DDTHH:MM:SS+08:00"
proposed_title: "Concise searchable title"
summary: "30-80 Chinese chars or one clear English sentence"
content_draft: "Redacted candidate content"
classification: "shared_knowledge|private_draft|no_write"
category: "error|technique|decision|workflow|observation|general"
tags: ["tag1", "tag2"]
privacy_flags: []
dedupe_candidates:
  - knowledge_id: 0
    title: "Existing related entry"
    reason: "title/tag/semantic match"
decision: "pending|promote|merge|discard|blocked"
decision_reason: "Why this decision was made"
trust_initial: 0.4
freshness_initial: 1.0
convergence_status_initial: "unknown"
reviewer: ""
reviewed_at: ""
audit_log:
  - timestamp: ""
    actor: ""
    action: "created|classified|privacy_checked|dedupe_checked|reviewed|promoted|merged|discarded|blocked"
    note: "Redacted operational note"
```

Schema rules:

- `content_draft` must never contain raw secrets.
- `source_refs` must not include credentials or private tokenized URLs.
- `summary` is required before review.
- `tags` must include at least two useful search terms.
- `decision_reason` is required for `discard`, `blocked`, and `merge`.

---

## 7. Trust, freshness, and convergence defaults

| Source / review state | Initial trust | Freshness | Convergence |
|---|---:|---:|---|
| automatic session extraction | 0.4 | 1.0 | `unknown` |
| manual assistant proposal accepted by Arthur | 0.6 | 1.0 | `unknown` |
| Arthur explicitly states the rule/decision | 0.8 | 1.0 | `unknown` or `complete` if self-contained |
| verified with tool output / tests / docs | 0.8-0.9 | 1.0 | `complete` if enough context |
| inferred but not verified | 0.4-0.5 | 1.0 | `partial` |
| private draft | no shared trust score | no normal freshness | not applicable until transformed |
| no-write | none | none | none |

Rules:

- Trust measures confidence and reusability, not emotional importance.
- `freshness = 1.0` at promotion time; later freshness jobs can decay it.
- `convergence_status = partial` if the candidate is useful but lacks root cause, commands, boundaries, or verification.
- Promote cannot set `complete` unless the entry contains enough context for a future agent to act without asking Arthur again.

---

## 8. Privacy preflight

B1 defines the preflight contract; B6 will implement the scanner.

### 8.1 High-risk blockers

Block or redact before draft storage:

- `pypi-...`, `ghp_...`, `github_pat_...`, `sk-...`, bearer tokens.
- Private keys: `-----BEGIN ... PRIVATE KEY-----`.
- `.env`, `.pypirc`, cookie/session header values.
- Customer PII: names tied to phone/email/address/payment/treatment details.
- Medical aesthetics treatment records or CRM financial details.
- Arthur raw private life story unless transformed into a general collaboration rule.

### 8.2 Preflight outcomes

| Outcome | Meaning | Storage |
|---|---|---|
| `clear` | no sensitive flags | candidate can proceed |
| `redact_required` | usable after redaction | store only redacted draft |
| `private_only` | useful but not shareable | private draft only |
| `blocked` | too risky or no long-term value | no content storage; audit reason only |

### 8.3 Override policy

Overrides are allowed only when all are true:

1. Arthur explicitly approves the exact scope.
2. Raw secrets are still not stored.
3. Audit log records actor, time, and reason.
4. The result remains local/private if any personal/client context is present.

---

## 9. Dedupe and merge strategy

Before promotion, run dedupe checks in this order:

1. Exact title search.
2. Tag + keyword search.
3. Semantic search / hybrid search.
4. Graph neighbor check if relevant.
5. Existing known IDs from the session proposal.

Decision rules:

| Case | Action |
|---|---|
| same title and same lesson | merge/update existing entry |
| same topic but new pitfall | append update note or create linked entry |
| contradiction with existing entry | mark contradiction/review; do not overwrite |
| search does not find new ID after add but ID read works | mark indexing/search backlog |
| MCP-only and local DB conflict | local DB is source of truth; reconcile before sync |

Merge entry must preserve history:

```text
## Update YYYY-MM-DD
- New observation
- Why prior guidance changed or remains valid
- Source session / evidence
```

Do not erase old context unless it contains secrets or private data.

---

## 10. Review lifecycle

| State | Meaning | Allowed next states |
|---|---|---|
| `candidate` | extracted but not classified | `pending`, `blocked` |
| `pending` | classified and waiting review | `promote`, `merge`, `discard`, `blocked` |
| `blocked` | privacy/no-write failure | terminal |
| `discarded` | not valuable enough | terminal |
| `promoted` | formal knowledge entry created | terminal, later update possible |
| `merged` | integrated into existing entry | terminal, later update possible |

### 10.1 Promote checklist

A candidate can promote only if:

- classification is `shared_knowledge`,
- privacy preflight is `clear` or redacted safely,
- summary is clear,
- tags are useful,
- dedupe check completed,
- trust/freshness/convergence defaults are assigned,
- review decision and reason are recorded.

### 10.2 Post-promote verification

After promote:

1. Compile/update local DB.
2. Verify by exact ID / exact title.
3. If long entry, build or verify Document Map.
4. Run `read_range` if available.
5. Run search query; if not found, record `indexing/search backlog` rather than treating promote as failure.
6. Sync to Supabase only after local verification.

---

## 11. Entry-point boundaries

### 11.1 Feishu

Feishu is a conversation source, not an automatic shared-memory writer.

Allowed:

- user-confirmed writeback proposal,
- transcript candidate extraction,
- manual review commands.

Not allowed:

- storing whole Feishu conversation as shared knowledge,
- storing customer/private raw text,
- promoting without review.

### 11.2 CLI

`guardrails add` may remain a manual formal write path, but session capture commands must default to dry-run/draft.

Rule:

```text
manual add ≠ session capture
```

Manual add requires the user/agent to provide curated content. Session capture starts as candidates.

### 11.3 MCP

MCP write tools are high-risk because agents can call them inside conversation loops.

Rules:

- `guardrails_add` is for curated, explicit knowledge only.
- Session-derived candidates should use a future draft-only MCP tool, not formal add.
- MCP adds must run privacy preflight and dedupe.
- MCP-only writes must be reconciled back to local source of truth before sync.

### 11.4 Cron

Cron jobs may:

- scan sessions,
- propose candidates,
- compute freshness/convergence,
- report pending drafts.

Cron jobs must not:

- auto-promote,
- sync private draft material,
- silently store secrets,
- recursively schedule writeback jobs.

### 11.5 Subagents

Subagents may propose candidates and provide review evidence.

They must not claim final successful writeback unless parent verifies:

- returned ID/path,
- exact title/readback,
- privacy classification,
- local source-of-truth state.

---

## 12. Multi-agent traceability

Every writeback candidate should preserve enough metadata to answer:

1. Which session produced this?
2. Which agent extracted it?
3. Which reviewer approved it?
4. Why was it promoted/merged/discarded/blocked?
5. Which existing entries were considered duplicates?
6. Was private/raw material redacted?
7. Is search/indexing healthy for this entry?

Traceability must not preserve raw secrets or raw private life content.

---

## 13. Smoke cases

### Case 1 — reusable SOP from technical session

Input: session fixes a repeated GitHub Actions release problem.

Expected:

- classification: `shared_knowledge`
- privacy: `clear`
- decision: `promote` or `merge`
- search visibility: after promote only
- trust: `0.7-0.9` if verified

### Case 2 — >5 tool calls but only one-off task progress

Input: many tools used to update a temporary file or one-time status.

Expected:

- candidate list may be empty
- classification: no shared candidate
- decision: `discard`
- no formal knowledge entry

### Case 3 — mixed private story and reusable collaboration rule

Input: Arthur discusses private life details and a useful rule for future support.

Expected:

- raw story: `private_draft` or `no_write`
- extracted rule: possible `shared_knowledge` only after review
- raw details never appear in normal search

### Case 4 — token pasted during release

Input: PyPI/GitHub token appears in transcript.

Expected:

- privacy: `blocked`
- raw token not stored
- safe lesson may be extracted: token hygiene SOP
- audit says token was redacted, never echoes token

### Case 5 — customer CRM details

Input: session contains customer name, phone, treatment, payment context.

Expected:

- raw data: `no_write` or private operational store outside shared百科
- possible shared lesson: anonymized CRM safety rule
- no PII in `raw/`, compiled DB, Supabase, or search

### Case 6 — duplicate lesson

Input: candidate matches existing entry.

Expected:

- dedupe finds existing ID
- decision: `merge`
- preserve history with dated update note
- no duplicate title unless intentionally linked

### Case 7 — contradiction

Input: candidate conflicts with existing SOP.

Expected:

- decision: pending contradiction review
- no overwrite
- both claims preserved until resolved

### Case 8 — write succeeds but search misses

Input: promoted entry can be read by exact ID, but semantic search misses it.

Expected:

- promote is not considered failed
- record `indexing/search backlog`
- add query to Search QA backlog

### Case 9 — MCP bypass risk

Input: agent tries to call MCP add with raw session capture.

Expected:

- governance labels this as bypass risk
- future implementation should route to draft-only tool
- parent agent must verify exact write path

### Case 10 — cron-generated candidates

Input: daily scanner finds 20 possible writebacks.

Expected:

- cron outputs candidate report only
- no auto-promote
- high-risk items blocked/redacted before display if needed

---

## 14. Acceptance criteria

B1 is accepted when all are true:

- [ ] A future agent can classify any session candidate into `shared_knowledge`, `private_draft`, or `no_write`.
- [ ] The document clearly forbids silent auto-capture into normal search.
- [ ] Privacy preflight outcomes and blockers are defined.
- [ ] Dedupe/merge/contradiction behavior is defined.
- [ ] Trust, freshness, and convergence defaults are defined.
- [ ] Feishu, CLI, MCP, cron, and subagent boundaries are defined.
- [ ] Smoke cases cover shared, private, no-write, duplicate, contradiction, token, customer data, search miss, MCP bypass, and cron noise.
- [ ] The document can directly feed B6 privacy scanner design and B5 draft queue design.

---

## 15. Implementation tasks after B1

### Task B1-T1 — Add draft schema design

Create an implementation-ready schema for either SQLite `capture_drafts` or `drafts/` Markdown files.

Depends on: this B1 governance document.

### Task B1-T2 — Add writeback candidate extractor spec

Define deterministic candidate extraction prompts / rules and output JSON schema.

Depends on: B1 classification model.

### Task B1-T3 — Add privacy scanner contract tests

Translate B1 privacy preflight smoke cases into B6 tests.

Depends on: B6 implementation.

### Task B1-T4 — Add Feishu reply-only writeback flow

Turn current operational knowledge into a guarded handler: recover previous proposal, classify, privacy-check, dedupe, draft/promote only after review.

Depends on: B5 draft queue or manual review path.

### Task B1-T5 — Add Search QA backlog hook

When promoted entries are exact-readable but not searchable, add the miss to internal Search QA backlog.

Depends on: B3 internal Search QA set.

---

## 16. Current decision

Proceed next to **B6 privacy scanner design**, then **B5 session capture draft queue design**.

Rationale:

- Capture without privacy scanning risks dirty writes.
- Draft queue without governance risks becoming silent auto-capture in disguise.
- Search/Document Map improvements are important, but safe write boundaries come first.
