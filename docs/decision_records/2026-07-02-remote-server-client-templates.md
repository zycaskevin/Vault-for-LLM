# Remote Server Client Templates Keep The Adapter Boundary Small

## Context

Vault Remote Server gives multiple agents and platforms one self-hosted memory
entrypoint. After deployment templates exist, the next adoption risk is client
configuration drift: Codex, Claude Code, Hermes, OpenClaw, Coze, and n8n should
not each invent a different memory contract.

At the same time, Vault should not become a thick SDK for every agent runtime.
The durable product boundary is the small Gateway HTTP contract.

## Decision

`vault setup-agent` writes remote client templates under `agent-install/`:

- `README-remote-clients.md`
- `vault-remote-client-config.json`
- `AGENT_REMOTE_GATEWAY_SNIPPETS.md`
- `coze-vault-remote-openapi.json`
- `n8n-vault-remote-client.workflow.json`

The templates all point to the same contract:

- set `VAULT_REMOTE_URL` and `VAULT_GATEWAY_TOKEN`;
- send `agent_id` on each request;
- search returns compact memory, not raw full content;
- read evidence through bounded `/read-range`;
- write new lessons through `/submit-candidate`;
- do not treat this as offline active multi-master sync.

## Consequences

Agents can connect to one shared remote memory host with short setup snippets,
while Vault keeps the adapter layer replaceable. Supabase, a future hosted
server, local MCP, and self-hosted Remote Server remain different transports
over the same governed memory boundary.
