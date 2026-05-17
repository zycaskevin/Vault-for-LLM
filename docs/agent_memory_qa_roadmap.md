# Vault-for-LLM Agent Memory QA Roadmap

**Date:** 2026-05-17  
**Status:** Planning / review artifact  
**Scope:** Public open-source roadmap, not private deployment notes  

> Goal: upgrade Vault-for-LLM from a local-first knowledge vault into a clear, credible **Agent Memory QA Layer**: a tool that helps LLM agents store, find, read, cite, and maintain project memory correctly.

---

## 1. Executive summary

Vault-for-LLM should not become a clone of capture-first agent memory runtimes. Its stronger public position is:

> **Local-first Markdown + SQLite memory vault for LLM agents, with bounded reading, citation-safe retrieval, and measurable memory quality checks.**

The adjacent `agentmemory` project demonstrates strong patterns worth borrowing:

- first-run onboarding (`doctor`, `demo`, `connect` style flows),
- session/coding-agent capture,
- memory tiers,
- BM25 + vector + graph retrieval fusion,
- privacy filtering,
- progressive disclosure,
- repository benchmark fixtures.

But Vault-for-LLM should borrow those as **patterns**, not copy its product shape. Vault should preserve:

- Markdown as the human-readable source material,
- SQLite as the local source of truth,
- optional embeddings and optional remote sync,
- a small MCP surface,
- review-before-commit for captured memory,
- explicit alpha maturity language.

---

## 2. Product positioning

### 2.1 What Vault-for-LLM is

Vault-for-LLM is a local memory toolkit for projects and AI coding agents:

```text
Markdown raw/ entries
        ↓
vault compile
        ↓
local SQLite vault.db
        ↓
vault search / vault map / vault-mcp
```

It helps an agent answer:

1. What did we learn before?
2. Where is the exact source section?
3. Can I cite a bounded source range instead of trusting a search preview?
4. Is this knowledge stale, duplicated, incomplete, or low quality?
5. Did a retrieval change improve or regress search quality?

### 2.2 What Vault-for-LLM is not

Vault-for-LLM should be explicit about non-goals:

- Not a hosted enterprise memory platform.
- Not a cloud-first service.
- Not a production-ready team collaboration backend.
- Not a full replacement for a notes app.
- Not a hidden personal data collector.
- Not a hosted or mature workflow marketplace.
- Not dependent on Supabase, Docker, ONNX, Ollama, or vector search for the core path.

### 2.3 Positioning against adjacent tools

| Tool style | Primary strength | Vault-for-LLM response |
|---|---|---|
| Capture-first agent memory runtime | Automatically records agent sessions and actions | Add opt-in capture/import, but keep review-before-commit |
| Vector database / RAG stack | Fast similarity search | Keep retrieval, but emphasize bounded reading and memory QA |
| Notes app | Human note-taking UX | Keep Markdown compatibility, but optimize for agent retrieval and citation |
| Cloud memory platform | Shared hosted memory | Preserve local-first core; remote sync stays optional |

### 2.4 Recommended public tagline

> **Local-first memory QA for LLM agents.**
>
> Store project memory as Markdown, compile it into SQLite, and let agents search, inspect, and cite the right source ranges through CLI or MCP.

---

## 3. Borrow from agentmemory — carefully

| agentmemory pattern | Borrow into Vault-for-LLM | Guardrail |
|---|---|---|
| Auto-capture hooks | `vault capture import` / `vault import-session` from Claude/Codex logs | Opt-in only; captured entries start as drafts, not trusted knowledge |
| Session timeline | Local `sessions` / `session_events` / `capture_queue` tables | Timeline data does not appear in normal search until promoted |
| Working / episodic / semantic / procedural memory | Explain how L0/L1/L2/L3 map to these ideas | Do not rename existing architecture prematurely |
| BM25 + vector + graph + RRF | Add deterministic hybrid ranking with Search QA gates | Never make embeddings required for base install |
| CJK tokenizer | Add CJK-aware keyword/FTS baseline | Keep graceful fallback if tokenizer package is absent |
| Privacy filter | Scan capture/add/compile/sync paths for secrets | Make clear regex filters are best-effort, not a compliance guarantee |
| Progressive disclosure | Search → map show → bounded read_range | Search preview is navigation only; final citation comes from bounded read |
| Benchmarks | Keep Search QA examples as source-checkout repository fixtures and provide before/after metrics | Report retrieval metrics honestly; do not equate them with end-to-end agent success or wheel-installed data |
| Doctor/demo/connect UX | `vault doctor`, `vault demo`, `vault connect --print` | No silent writes into external agent config by default |

---

## 4. Public maturity model

Public docs should separate stable, usable-alpha, and experimental features.

| Tier | Features | Public promise |
|---|---|---|
| Stable core | `vault init`, `vault add`, `vault compile`, `vault search`, `vault list`, `vault stats`, keyword search, local SQLite | Should work without cloud, Docker, embeddings, or remote services |
| Usable alpha | `vault-mcp`, Document Map, bounded `read_range`, graph expansion, Search QA snapshots | Useful, but APIs and payloads may evolve |
| Experimental lab | convergence, cross-validation, freshness, dedup, skills, Supabase sync, capture/import | Available for early testing; not production platform claims |

This avoids overclaiming while still showing the direction.

---

## 5. Target architecture

### 5.1 Core architecture

```text
Human / Agent
   ↓
CLI or MCP
   ↓
Vault command layer
   ↓
Markdown raw/       compiled artifacts
   ↓                       ↓
SQLite vault.db  ←  compile / migrations / indexes
   ↓
Search / map / read_range / QA checks
   ↓
Optional: Supabase sync/read target
```

### 5.2 Retrieval stack

Recommended future retrieval order:

```text
Keyword / FTS search
  → optional vector search
  → optional graph expansion
  → deterministic RRF fusion
  → trust / freshness / Document Map availability signals
  → compact result with next_action
  → map show
  → bounded read_range citation
```

Key rule:

> Search discovers candidates. Bounded reads support final claims.

### 5.3 Capture stack

Capture should be intentionally conservative:

```text
agent log / transcript / JSONL
        ↓
vault capture import --dry-run
        ↓
privacy scan + source metadata
        ↓
capture queue / draft Markdown
        ↓
human or explicit agent review
        ↓
promote to raw/
        ↓
vault compile
```

Captured memory must not silently become trusted L3 knowledge.

### 5.4 MCP surface policy

Default MCP tools should remain small:

```text
vault_search
vault_add
vault_stats
vault_map_show
vault_read_range
```

Optional remote read tools can exist only when explicitly configured:

```text
vault_remote_map_show
vault_remote_read_range
```

Advanced QA tools should stay CLI-first unless there is a strong agent-in-conversation use case.

---

## 6. Roadmap

## Phase 0 — Public boundary cleanup

**Goal:** make the repo genuinely open-source-user facing before adding more features.

### Work items

1. Run a public string audit for internal/private terms.
2. Remove or neutralize private raw memory entries.
3. Split optional public Supabase sync from any private remote-health sync.
4. Keep `vault skill` product-neutral as an experimental local skill registry, or hide it until that remains true.
5. Build a README claim matrix: claim → proof → maturity.

### Acceptance criteria

- No public-facing private names, paths, or internal deployment assumptions remain.
- Any remaining internal historical term has an explicit documented reason.
- README does not imply enterprise maturity, cloud requirement, or mature marketplace capability.
- Supabase is described only as an optional sync/read target.

### Suggested checks

```bash
git grep -nE 'private|internal|product-specific|deployment-specific' -- .
git diff --check
python -m compileall vault scripts tests
python -m pytest -q
```

---

## Phase 1 — Stable local core verification

**Goal:** make the base user journey boringly reliable.

### Stable flow

```bash
vault doctor
vault init
vault add "First lesson" --content "What broke, why, and how to avoid it."
vault compile
vault search "what broke"
```

### Work items

1. Verify fresh install in a clean environment.
2. Verify all README commands exist and match CLI help.
3. Ensure optional dependencies fail gracefully.
4. Keep base path keyword-only capable.
5. Add or update release checklist.

### Acceptance criteria

- No cloud/model/vector dependency is needed for quickstart.
- `vault doctor` distinguishes core errors from optional missing dependencies.
- README command table matches real parser behavior.
- Tests do not fail at collection time because optional dependencies are missing.

### Suggested checks

```bash
python -m vault.cli --help
python -m vault.cli doctor
python -m pytest -q
git diff --check
```

---

## Phase 2 — Document Map as the primary differentiator

**Goal:** make bounded reading and citation-safe memory use the obvious reason to choose Vault.

### Work items

1. Provide a public-safe demo for search → map → read.
2. Make search results compact by default for MCP use.
3. Add clear `next_action` hints when Document Map metadata exists.
4. Make missing map behavior actionable: recommend `vault map build`.
5. Document citation policy: search preview is navigation; read_range is proof.

### Acceptance criteria

- Agents can follow `vault_search → vault_map_show → vault_read_range` without reading full documents.
- `vault_read_range` enforces bounded output and returns stable citations.
- Search QA or policy tests reject invented/search-only citations.
- Long documents can be handled without context flooding.

### Suggested checks

```bash
python -m pytest -q tests/test_document_map.py tests/test_document_map_cli.py
python -m pytest -q tests/test_search_map_integration.py tests/test_vault_mcp_map.py
```

---

## Phase 3 — Search QA and repository benchmark fixtures

**Goal:** measure memory retrieval changes instead of trusting vibes.

### Work items

1. Add public-safe Search QA fixtures under the repository `benchmarks/search_qa/` directory.
2. Include English and CJK cases.
3. Track top1, hit@k, MRR, and citation-policy violations.
4. Add before/after comparison examples.
5. Keep benchmarks retrieval-focused and label their limits.

### Acceptance criteria

- `vault search-qa run` can produce deterministic snapshots.
- `vault search-qa compare` highlights regressions.
- CI can run a local-only Search QA smoke test.
- Public benchmark docs do not imply end-to-end agent task success or PyPI wheel inclusion for top-level repository fixtures.

### Suggested checks

```bash
python -m pytest -q tests/test_search_quality_metrics.py
vault search-qa run --qa-file benchmarks/search_qa/basic.zh-Hant.json --mode keyword --output /tmp/vault-searchqa.json
```

The `benchmarks/search_qa/` paths above assume a repository source checkout; PyPI installs can use `vault search-qa` with user-provided QA files.

---

## Phase 4 — Retrieval upgrade: FTS/BM25 + vector + graph + RRF

**Goal:** borrow agentmemory's retrieval fusion idea while keeping Vault simple and local.

### Work items

1. Add SQLite FTS5/BM25 where available.
2. Keep LIKE/keyword fallback.
3. Add CJK-aware tokenization or n-gram fallback.
4. Fuse keyword, vector, and graph ranks using deterministic RRF.
5. Use Search QA before/after metrics as a gate.
6. Add index integrity checks to avoid stale or ghost index rows.

### Acceptance criteria

- No embedding provider required for base search.
- Ranking changes are measurable and reversible.
- CJK retrieval has explicit fixtures.
- Vector/table dimension mismatches are detected, not silently ignored.
- Graph expansion improves recall without overwhelming compact results.

### Suggested checks

```bash
python -m pytest -q tests/test_retrieval_fts.py tests/test_retrieval_cjk.py tests/test_retrieval_rrf.py
python -m pytest -q tests/test_search_quality_metrics.py
```

---

## Phase 5 — Review-gated session capture

**Goal:** borrow auto-capture benefits without turning Vault into an uncontrolled recorder.

### Work items

1. Design `vault capture import` / `vault import-session` for Claude/Codex JSONL or transcripts.
2. Store imports in a local pending queue or draft folder.
3. Add privacy scan before draft creation and before promotion.
4. Add `promote` / `discard` flow.
5. Set default trust low for captured entries.
6. Keep auto-capture off by default.

### Acceptance criteria

- Captured data is local-only and opt-in.
- Drafts do not appear in normal `vault search` until promoted.
- Secrets are redacted or blocked before compile/sync.
- A captured lesson can be promoted into normal Markdown and compiled through the same path as manual entries.

### Suggested commands

```bash
vault capture import --file session.jsonl --dry-run
vault capture list
vault capture promote <id>
vault capture discard <id>
```

---

## Phase 6 — Privacy and safety layer

**Goal:** prevent Vault from becoming a place where agents permanently store secrets or private data by accident.

### Work items

1. Add shared privacy scanner for CLI add, capture import, compile, and sync.
2. Include default patterns for API keys, bearer tokens, private keys, emails, and common secret markers.
3. Support project-level rule config.
4. Add redaction preview.
5. Add explicit override for advanced users.

### Acceptance criteria

- High-risk secrets are blocked or redacted by default.
- Privacy scanner behavior is documented as best-effort.
- Remote sync uses the same safety checks.
- Tests verify that raw secrets are not searchable after default ingestion.

### Suggested checks

```bash
python -m pytest -q tests/test_privacy_filter.py tests/test_vault_mcp_add_privacy.py
```

---

## Phase 7 — First-hour UX: doctor, demo, connect

**Goal:** make a new open-source user understand and trust Vault within five minutes.

### Work items

1. Extend `vault doctor` to check DB, schema, FTS, optional embeddings, MCP, and remote config.
2. Add `vault demo` with a temporary local vault and public-safe sample entries.
3. Add `vault connect --print` to show MCP config without silently modifying external app config.
4. Add agent instruction templates for Claude/Codex/MCP-compatible agents.

### Acceptance criteria

- `vault demo` works offline and keyword-only.
- `vault connect --print` has no side effects by default.
- Doctor separates fatal core issues from optional missing features.
- README quickstart links to the demo path.

---

## 7. Kanban execution graph

Use board: `vault-for-llm-public-cleanup` or a dedicated board such as `vault-agent-memory-qa-roadmap`.

### Epic A — Public boundary and privacy cleanup

| Card | Assignee type | Depends on | Acceptance |
|---|---|---|---|
| A1 Public string audit | reviewer | none | all internal/private terms classified as remove/neutralize/allowed |
| A2 Raw/example cleanup | writer / engineer | A1 | no private raw memory ships as public default; examples are neutral |
| A3 Supabase/remote-health split | backend / reviewer | A1 | optional sync separated from private remote-health assumptions |
| A4 Skill feature neutralization decision | analyst / backend | A1 | `vault skill` is hidden, clearly experimental, or product-neutral |

### Epic B — Public positioning

| Card | Assignee type | Depends on | Acceptance |
|---|---|---|---|
| B1 README claim matrix | analyst | A1 | every claim has proof, maturity, and command/test evidence |
| B2 README rewrite pass | writer | B1 | first 100 lines explain what/why/who/not-for/maturity |
| B3 Localized README sync | writer | B2 | English, Traditional Chinese, Simplified Chinese claims match |

### Epic C — Core verification

| Card | Assignee type | Depends on | Acceptance |
|---|---|---|---|
| C1 Fresh install smoke | QA | B1 | quickstart works in clean env without cloud/embedding deps |
| C2 MCP minimal smoke | QA | C1 | `vault-mcp` starts and exposes expected `vault_*` tools |
| C3 CLI/docs parity | QA / writer | C1 | every documented command exists; experimental commands marked |

### Epic D — Differentiator demos

| Card | Assignee type | Depends on | Acceptance |
|---|---|---|---|
| D1 Bounded retrieval demo | writer / QA | C1 | search → map → read demo works with neutral sample data |
| D2 Citation policy doc | writer / reviewer | D1 | docs clearly state search is navigation, read_range is proof |
| D3 Search QA benchmark fixtures | QA | D1 | local-only fixtures cover English + CJK + citation cases |

### Epic E — Retrieval and capture roadmap

| Card | Assignee type | Depends on | Acceptance |
|---|---|---|---|
| E1 FTS/BM25/RRF design spike | backend | D3 | retrieval design includes fallback and Search QA gates |
| E2 Capture/import design spike | backend / reviewer | A1 | capture is opt-in, local-only, review-gated |
| E3 Privacy scanner design | security / backend | E2 | add/capture/compile/sync share one safety layer |

### Epic F — Release hygiene

| Card | Assignee type | Depends on | Acceptance |
|---|---|---|---|
| F1 SECURITY and CONTRIBUTING docs | writer / reviewer | B2 | public vulnerability and contribution paths exist |
| F2 CI optional dependency hardening | backend / QA | C1 | full local suite does not fail from missing optional deps |
| F3 Release checklist | reviewer | A*, B*, C* | private scan, command smoke, package metadata, and git clean gates documented |

### Recommended start sequence

```text
A1 → A2/A3/A4 → B1 → B2/B3 → C1/C2/C3 → D1/D2/D3 → E1/E2/E3 → F1/F2/F3
```

Do not start feature expansion before A/B/C are clean. The current pain is not lack of features; it is public clarity, evidence, and safety boundaries.

---

## 8. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Copying too much from agentmemory | Vault loses local-first simplicity | Borrow patterns only; keep Markdown + SQLite + small MCP surface |
| Overclaiming advanced features | Public trust damage | Use stable/alpha/experimental maturity table |
| Hidden private context in repo | Open-source release risk | Public string audit and neutral examples |
| Optional deps break core tests | Poor install experience | Guard imports; skip optional tests gracefully |
| Auto-capture stores secrets | Security and privacy risk | Opt-in capture, privacy scan, review-before-promote |
| Large MCP surface confuses agents | More hallucinated tool use | Keep default MCP minimal; advanced actions CLI-first |
| Benchmarks become marketing theater | Misleading claims | Label retrieval-only metrics and include caveats |
| Remote sync mistaken as source of truth | Data conflict risk | Repeat: SQLite local DB is canonical; remote is rebuildable target |

---

## 9. Documentation changes recommended after this roadmap

1. Rewrite README first screen around:
   - what it is,
   - who it is for,
   - who it is not for,
   - stable vs experimental features.
2. Add `docs/security_privacy.md`.
3. Add `docs/quickstart_agent.md`.
4. Add `docs/benchmarking.md`.
5. Add `docs/capture_adapters.md` only after capture design is approved.
6. Add public-safe examples for Document Map and Search QA.
7. Update package metadata description to match keyword-first, local-first positioning.

---

## 10. Current known findings from review

These findings should be verified and addressed in Phase 0/1:

- Full test collection can fail if optional Supabase dependency import is not guarded.
- Some public docs and code paths may still expose private/internal vocabulary or remote-service assumptions.
- `vault skill` is positioned as an experimental local registry; it should not be marketed as a hosted or mature marketplace until safety-reviewed.
- Raw tracked knowledge entries should be checked for public suitability.
- README currently has the right direction but should be stricter about maturity and proof.

---

## 11. Definition of done for this roadmap

This roadmap is complete when:

- the public repo has no hidden private deployment assumptions,
- the README promises only what a fresh user can run or clearly labels alpha/experimental features,
- quickstart works in a clean environment without cloud/model dependencies,
- Document Map has a working public demo,
- Search QA has public-safe fixtures,
- capture/import, if added, is opt-in and review-gated,
- MCP remains small and agent-friendly,
- release checks include private string scan, command smoke, optional dependency safety, and README claim verification.
