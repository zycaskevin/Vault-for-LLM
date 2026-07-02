# Product Architecture

Vault-for-LLM should grow in layers. Each layer should preserve the local-first
trust boundary while adding more team and enterprise governance.

## Layer 1: Open-Source Local Memory Engine

This layer should remain open source and simple enough to trust.

It includes:

- Markdown and SQLite source of truth
- CLI and MCP tools
- local search and bounded reads
- candidate memory and promotion flow
- privacy, duplicate, metadata, and quality gates
- Obsidian import/export and review-friendly Markdown
- backup, restore, and verification
- basic audit metadata
- optional local semantic search

Primary users:

- solo developers
- agent-heavy builders
- open-source agent framework users
- local-first teams
- users of Hermes Agent, Claude Code, Codex, OpenClaw, OpenCode, n8n, or similar tools

This layer builds trust, adoption, and the shared protocol surface.

## Layer 2: Self-Host Team Edition

This is the first commercial or pilot-ready layer.

It should help small teams share memory without giving every agent the same
unbounded view.

Capabilities:

- shared project vault
- private plus shared memory layout
- multi-agent identity and access profiles
- review inbox for memory candidates
- promote / reject / delay workflow
- rollback and deprecation workflow
- team dashboard
- memory health reports
- optional Supabase or Postgres-backed sharing
- gateway or remote server deployment

The core promise:

> Multiple agents can share experience without polluting each other or leaking
> private memory.

## Layer 3: Hosted Cloud

Hosted cloud should be delayed until self-host usage proves that teams want the
workflow but do not want to maintain the infrastructure.

Possible hosted features:

- managed memory gateway
- hosted review dashboard
- team API key management
- managed backups
- managed embeddings
- usage analytics
- integration templates
- memory health reports

Cloud beta should require real traction signals:

- multiple teams already using self-host
- repeated requests for managed hosting
- clear integration path
- evidence that review dashboards are used weekly

## Layer 4: Enterprise Governance Platform

Enterprise should sell governance, not storage.

Capabilities:

- SSO / SAML
- advanced RBAC and agent roles
- audit log export
- retention and deletion policy
- PII and secret redaction
- BYOC, VPC, or on-prem deployment
- compliance review reports
- dedicated support
- custom agent integrations

The enterprise value proposition:

> The organization can control what its agents remember, who may use that
> memory, when it expires, and how mistakes are audited or rolled back.

## Open-Core Boundary

Keep open source:

- local vault
- SQLite and Markdown storage
- CLI and MCP basics
- search and bounded reads
- candidate-first review
- basic gates
- backup / restore
- import / export
- example adapters

Consider paid tiers for:

- hosted dashboards
- team review queues
- multi-agent fleet views
- managed gateway
- team analytics
- advanced policy engine
- SSO and enterprise RBAC
- retention and audit exports
- BYOC / VPC / on-prem support
