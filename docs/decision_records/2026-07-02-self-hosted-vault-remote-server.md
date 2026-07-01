# Self-Hosted Vault Remote Server

## Context

Vault needs to serve many agents and many platforms without forcing users to
scatter memory across separate systems. Supabase already works as an optional
cloud adapter for remote reads and candidate submission, but some users want to
keep the shared memory service on their own machine or server.

## Decision

Add `vault remote-server` as the self-hosted product entrypoint for the existing
Gateway contract.

It exposes the same narrow contract:

- health
- openapi
- search
- read-range
- submit-candidate

But its deployment posture is different from the local `gateway` helper:

- default host is `0.0.0.0`;
- `serve` requires a stable token from `VAULT_GATEWAY_TOKEN` or `--auth-token`;
- it reuses Gateway security defaults;
- remote writes still create review candidates;
- it does not write directly into active knowledge.

## Relationship To Supabase

Supabase remains an optional managed-cloud adapter.

Vault Remote Server can replace Supabase when agents and devices can reach one
trusted server directly:

```text
Agent / device / workflow
  -> Vault Remote Server
  -> one governed Vault project
```

Supabase remains useful when hosted tools need a managed cloud relay, RLS/RPC
policies, or the user does not want to operate a server.

## What This Does Not Solve Yet

This is centralized sharing, not offline multi-master sync.

It does not yet solve:

- multiple devices writing offline and merging later;
- automatic conflict-free active-memory replication;
- revision graph reconciliation across many writable replicas;
- rollback across distributed stores.

Those belong to a later sync layer. The safe bridge for now is candidate-first
remote contribution plus reviewed promotion.

## Consequences

The adapter model becomes clearer:

```text
Local MCP / CLI / Gateway
Supabase adapter
Vault Remote Server adapter
Future device adapters
  -> same governed memory model
```

Vault stays focused on unified memory governance. Transports can change, but
the memory source, access policy, candidate gates, and audit model stay stable.
