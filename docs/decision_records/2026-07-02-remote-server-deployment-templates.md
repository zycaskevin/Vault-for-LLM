# Remote Server Deployment Templates Are Generated But Inert

## Context

`vault remote-server` gives users a self-hosted central memory entrypoint. The
next adoption problem is deployment: normal users and agents should not need to
invent LaunchAgent, systemd, Docker Compose, or private-network guidance from
scratch.

At the same time, starting a remote memory server is a security-sensitive
operation. Setup should not expose a network listener automatically.

## Decision

`vault setup-agent` writes inert deployment templates into `agent-install/`:

- `README-remote-server.md`
- `vault-remote-server.launchagent.plist`
- `vault-remote-server.service`
- `vault-remote-server.compose.yaml`

The templates document and encode the same boundary:

- set a stable `VAULT_GATEWAY_TOKEN` first;
- prefer private networks such as Tailscale, WireGuard, or LAN-only routing;
- do not expose publicly without TLS, firewalling, and token rotation;
- remote writes remain candidate-first;
- this is centralized sharing, not offline active multi-master sync.

## Consequences

Agents can help users deploy a self-hosted Remote Server without memorizing
service-manager syntax, but setup remains safe by default because it only writes
templates. A human or explicitly instructed agent must still review, copy, and
start the service.
