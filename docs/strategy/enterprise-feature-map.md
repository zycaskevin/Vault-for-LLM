# Enterprise Feature Map

Enterprise Vault should sell memory governance. The storage engine matters, but
the buyer pays for control, accountability, policy, and integration.

## RBAC And Agent Access Control

Enterprise deployments need role-based permissions for both humans and agents.

Examples:

| Role | Can read | Can write | Can promote |
|---|---|---|---|
| Coding agent | engineering SOPs, low/medium project memory | bug candidates, implementation lessons | no |
| Review agent | candidates in assigned scopes | review notes | low-sensitivity project memory |
| Manager agent | project status and decisions | decision candidates | project decisions |
| Finance agent | finance scope only | finance candidates | finance-approved memory |
| External agent | public or explicitly shared memory | no default writes | no |
| Admin | all governed scopes | policy changes | yes |

The important boundary: role controls should apply to tools, memory scopes,
sensitivity, and lifecycle actions separately.

## Audit Trail

Every promoted memory should answer:

- who or what created it
- source reference and evidence
- gate results
- who promoted it
- when it was promoted
- who modified or deprecated it
- which memory replaced it
- which agents searched or cited it
- which tasks or workflows used it

Auditability is a product feature, not a log file afterthought.

## Policy Engine

Teams should eventually define policies such as:

```yaml
engineering:
  auto_promote:
    allowed_sources: ["github_pr", "ci_failure", "human_approved"]
    min_trust: 0.75
    max_sensitivity: "medium"

customer_data:
  auto_promote: false
  require_human_review: true
  retention_days: 90

strategy:
  readable_by: ["founder-agent", "strategy-agent"]
  writable_by: ["authorized-human", "strategy-agent"]
  require_review: true
```

The policy engine should make automation safer, not more mysterious.

## Retention, Expiry, And Forgetting

Enterprise memory is not useful just because it is long-lived.

Required lifecycle controls:

- expire after a fixed duration
- deprecate when replaced
- archive project memory after project close
- delete or redact customer data after retention windows
- keep rollback history for governed changes
- protect high-value memory from accidental cold storage

Forgetting should be reviewable and recoverable where policy allows.

## PII And Secret Redaction

Enterprise buyers will ask whether long-term memory can leak:

- API keys
- passwords
- bearer tokens
- customer emails
- phone numbers
- financial records
- sensitive profile data
- internal strategy

Vault should keep deterministic scanning in OSS and reserve advanced policy,
reporting, and organization-specific detectors for enterprise deployments.

## Memory Health Dashboard

The dashboard should help teams see whether shared agent memory is becoming
healthier or noisier.

Useful metrics:

- pending candidates
- promoted memories
- deprecated memories
- stale memory ratio
- duplicate ratio
- low-trust memory count
- high-sensitivity memory count
- most active writing agents
- most cited memories
- memories with conflicts
- memories waiting for human review

This dashboard should stay focused on memory operations, not generic analytics.

## Paid Boundary

Likely paid capabilities:

- SSO / SAML
- enterprise RBAC
- audit exports
- retention policy enforcement
- BYOC, VPC, and on-prem
- advanced PII detectors
- organization-wide dashboards
- dedicated integration support

Keep the local OSS core strong enough that developers trust the system before
enterprises are asked to adopt it.
