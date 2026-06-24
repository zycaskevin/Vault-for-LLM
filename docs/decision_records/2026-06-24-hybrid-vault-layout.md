# Decision Record: Hybrid Vault Layout in Agent Setup

Date: 2026-06-24

## Context

The local agent registry lets multiple local runtimes discover which Agents are
connected to Vault. The next step is preventing those Agents from mixing all
memory into one database while still sharing project knowledge.

## Decision

`vault setup-agent` should support a hybrid memory layout:

- shared project vault for project facts, decisions, SOPs, fixes, release
  process, benchmark evidence, and safety rules
- private Agent vault for identity, private preferences, personal notes, and
  agent-specific working style

The first implementation creates the layout and records it. It does not yet
merge search results across both vaults.

## Product Behavior

Setup should write a public-safe manifest under the generated `agent-install/`
directory. The manifest tells future Agents where the shared and private vaults
live and which startup commands are safe to run.

The local agent registry should also record the private vault path when hybrid
layout is used, so `vault update-status` can show both shared and private memory
locations.

## Boundary

Hybrid layout is a storage and coordination convention, not a permission system
by itself. Access control still depends on Vault metadata, read policies, and
future adapter behavior.

The private Agent vault is local-only by default. It should not be synced to
remote shared memory unless a future explicit policy allows reviewed summaries.

## Deferred

- Cross-vault search orchestration.
- MCP tools that search shared and private vaults together.
- Supabase sync policies for reviewed private summaries.
- Automatic migration of existing single-vault installs into hybrid layout.
