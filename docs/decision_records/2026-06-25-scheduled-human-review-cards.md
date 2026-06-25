# Scheduled Human Review Cards

Date: 2026-06-25

## Decision

Vault-for-LLM generated memory automation schedules should write the compact
review-summary artifact on every scheduled pass:

1. `vault memory pipeline --write-candidates`
2. `vault memory reflection --write-candidates`
3. `vault automation cycle`
4. `vault automation inbox --write-handoff`
5. `vault automation review-summary --write-summary`
6. `vault automation learning-health --write-health`

## Rationale

The automatic memory loop should reduce human review work, not create a larger
report pile. The daily human surface should start from a few approval cards that
name the decision, explain why it matters, and suggest the safest next step.

## Safety Boundary

- Review-summary is read-only.
- It does not include raw candidate content.
- It does not promote, archive, delete, compress, or change access policy.
- Feedback about a card is recorded separately through
  `vault automation review-feedback`.
