# 90-Day Validation Plan

Do not build a large cloud platform before proving that teams want governed
agent memory in their daily workflows.

This plan validates the wedge in three stages.

## Days 0-30: OSS Core And Killer Demo

Goals:

- make the shared-memory governance demo easy to run
- publish the flagship article: "Agents Need Memory Governance, Not Just RAG"
- document the Hermes Agent, Claude Code, and Codex shared-memory path
- keep setup agent-driven and low-friction
- make daily review small enough that a user can tolerate it

Target proof points:

- 20 real installs
- 5 users connect Vault to an actual agent workflow
- 3 users ask about self-host or team usage
- at least one public demo showing candidate -> promote -> rollback -> audit

Do not optimize for enterprise features during this stage.

## Days 31-60: Self-Host Pilots

Goals:

- work with three AI-heavy teams or builders
- run Vault in their real workflow for at least one week
- observe which memories are worth keeping
- validate the review inbox and dashboard
- support the minimum remote sharing path they actually use

Questions to answer:

- Do they have agent memory pollution?
- Do they trust candidate-first review?
- Do they review memory weekly?
- Which memory types matter most: bugs, SOPs, decisions, customer context, or tasks?
- What scares them most: privacy, stale memory, wrong memory, permissions, or sync?

Useful pilot features:

- shared vault
- candidate queue
- promote / reject / delay
- rollback and deprecate
- basic team dashboard
- Supabase, Postgres, or gateway as optional bridge

## Days 61-90: Decide Cloud Or Enterprise

Cloud beta is justified if:

- five or more teams say self-host is useful but too much work
- the same integration path repeats
- the dashboard is used regularly
- teams want managed backup, API keys, uptime, and hosted review

Enterprise PoC is justified if:

- two or more teams explicitly ask for RBAC, SSO, audit, or retention
- they can describe their internal agent workflow
- there is budget or deployment urgency
- they are willing to pay for implementation or support

If those signals do not appear, keep improving OSS core and integrations.

## Anti-Goals

- Do not build cloud only because it feels like a company.
- Do not add full enterprise compliance before a committed pilot.
- Do not let silent auto-promote become the default.
- Do not measure success only by benchmark scores.

Measure whether Vault changes how teams let agents learn from work.
