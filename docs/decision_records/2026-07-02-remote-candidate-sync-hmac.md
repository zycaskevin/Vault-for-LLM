# Remote Candidate Sync HMAC

Date: 2026-07-02

## Decision

Remote candidate sync supports optional HMAC integrity metadata for payloads
submitted through Supabase-backed candidate requests.

When `VAULT_SYNC_HMAC_SECRET` is configured, outgoing candidate requests include:

- `hmac_algorithm`
- `payload_hash`
- `hmac_signature`

Trusted pull hosts can require valid signatures before importing remote requests
into the local `memory_candidates` queue. Invalid or missing signatures are
marked as `signature_invalid` and are not imported.

## Why

Remote candidate sync is the first safe bidirectional path: other machines can
propose memory, but active knowledge is still created only through local review
or narrowly scoped low-risk automation.

Token auth and Supabase RLS protect access, but they do not prove that a
candidate payload was unchanged between submission and pull. HMAC adds an
application-level integrity check without turning Vault into a heavyweight
distributed database.

## Boundary

This is not active multi-master sync. HMAC protects candidate request payloads;
it does not resolve active knowledge conflicts, replace TLS, or authorize an
agent to promote memory.

The shared HMAC secret is separate from Supabase keys:

- `SUPABASE_SERVICE_ROLE_KEY` remains only on trusted sync hosts.
- `VAULT_SYNC_HMAC_SECRET` is shared only with trusted submitters and pull hosts
  that need payload integrity verification.

## Compatibility

HMAC is optional for existing deployments. If no HMAC secret is configured,
remote candidate sync keeps the previous unsigned behavior.

Advanced Supabase setup templates include the new columns and RPC parameters so
new deployments can carry signatures. Existing deployments can continue running
unsigned until their SQL policy is updated.

## Follow-Up

- Add an offline sync package format with HMAC metadata.
- Add a compact `vault sync integrity` report for operators.
- Add sync audit surfacing in the multi-agent dashboard.
