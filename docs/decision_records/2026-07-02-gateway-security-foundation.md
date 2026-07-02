# Gateway Security Foundation

Date: 2026-07-02

## Decision

Vault Gateway and self-hosted Vault Remote Server must ship with transport-edge
safety controls before broader beta use. The Gateway remains a thin HTTP JSON
adapter, but it now has a built-in security foundation:

- IP allowlist / denylist.
- Per-IP request rate limiting.
- Per-token request rate limiting.
- Authentication failure lockout.
- Optional built-in HTTPS with user-provided certificate and key paths.
- A bounded request worker pool. If the pool is full, Gateway returns `503`
  instead of creating unbounded threads.
- Audit entries that include client IP, User-Agent, endpoint, method, and block
  reason.
- Audit log rotation with bounded local retention.
- Compact audit summaries through `vault gateway audit`,
  `vault remote-server audit`, and the `vault_gateway_audit` MCP tool.

These controls are configured by CLI flags or environment variables:

- `VAULT_GATEWAY_RATE_LIMIT_PER_MINUTE`
- `VAULT_GATEWAY_TOKEN_RATE_LIMIT_PER_MINUTE`
- `VAULT_GATEWAY_AUTH_FAILURE_LIMIT`
- `VAULT_GATEWAY_AUTH_LOCKOUT_SECONDS`
- `VAULT_GATEWAY_IP_ALLOWLIST`
- `VAULT_GATEWAY_IP_DENYLIST`
- `VAULT_GATEWAY_TLS_CERT`
- `VAULT_GATEWAY_TLS_KEY`
- `VAULT_GATEWAY_MAX_WORKERS`
- `VAULT_GATEWAY_AUDIT_MAX_BYTES`
- `VAULT_GATEWAY_AUDIT_BACKUPS`

## Why

Gateway is the shared doorway for same-machine and cross-host agents. Token auth
alone is not enough for beta users because brute-force attempts, accidental
public exposure, and noisy clients can still affect the memory service.
Unbounded per-request threads are also a risk on personal machines where many
agents may share one local gateway.

The first safety layer should be deterministic, local-first, and dependency-free
so users can run it anywhere. Built-in HTTPS covers private LAN/lab/beta
deployments where a reverse proxy is not available, while production internet
deployments should still prefer Caddy, Nginx, or another proxy for certificate
renewal and extra network controls.

## Scope

Built-in HTTPS requires both a certificate and key. It does not generate
self-signed certificates, manage certificate renewal, or replace the need for a
private network, firewall, or reverse proxy in public deployments.

The built-in worker pool is a resource boundary, not a full traffic-management
layer. Public deployments should still use a reverse proxy for connection
limits, request body limits, TLS renewal, logging, and abuse protection.

Audit rotation is local file hygiene. It prevents runaway `audit.jsonl` growth
for long-running personal gateways, but it is not a compliance archive or SIEM.
Users who need long retention should export `reports/gateway/audit*.jsonl` to
their own log store.

Follow-up work:

- Offline sync package integrity checks.
- Interactive conflict review UI for multi-host sync.
