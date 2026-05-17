---
title: "Synthetic Agent Harness Example: Model + Body + Harness"
category: "concept"
tags: ["harness", "agent", "architecture", "LLM", "body", "model", "constraint", "verification", "sub-agent", "context-firewall"]
trust: 0.7
source: "synthetic public example for Vault-for-LLM documentation"
created: "2026-04-27"
summary: "Synthetic, public-safe example note explaining an agent harness as Model + Body + Harness. It uses generic product names and placeholder hooks so the public repo does not ship private operational memory."
---

# Synthetic Agent Harness Example: Model + Body + Harness

> Public-safety note: this is synthetic sample knowledge for demos and tests. It is not a private deployment note, incident record, or operational runbook.

## Core frame

**Agent = Model + Body + Harness**

- **Model**: the reasoning engine.
- **Body**: the tools the agent can use, such as a shell, filesystem, browser, or API client.
- **Harness**: the calibration layer around the model and tools, such as instructions, hooks, verification loops, and review gates.

The same model can behave differently when placed in a different harness because the available tools, constraints, and feedback loops change the distribution of actions.

## Example: two neutral agent runtimes

Imagine two fictional runtimes using the same model:

- **Example Code Agent** focuses on software changes. Its body includes shell commands, file editing, tests, and version-control helpers. Its harness emphasizes planning, small diffs, and verification before completion.
- **Example Research Agent** focuses on reading and synthesis. Its body includes search, document readers, citation tools, and note-taking helpers. Its harness emphasizes source tracking, bounded claims, and uncertainty labels.

The model is identical, but the work product differs because the body and harness differ.

## Harness techniques

### 1. System instructions

Keep stable rules close to the agent, such as coding style, safety boundaries, and repository-specific workflows. Instructions are helpful but soft: the model may still drift.

### 2. Hooks and policy checks

Use hard checks for actions that should never silently happen. Examples:

```text
R001 — block writes to protected config files without explicit approval
R002 — run syntax checks after Python file edits
R003 — warn before sending messages outside the current workspace
R004 — require a verification command before marking coding work complete
R005 — record failed policy checks for later review
```

A good hook stays quiet when work is safe and only speaks when intervention is needed.

### 3. Planner / generator / evaluator separation

Separate planning, implementation, and review when the task is large or risky. Independent review is more useful than asking the same process to grade its own work.

### 4. Sub-agent context boundaries

For large searches or noisy tool output, a sub-agent or isolated worker can summarize findings without flooding the main conversation context. This is a context-management pattern, not a product requirement.

### 5. Verification loop

Do not accept "done" without evidence. Run the smallest useful check: a syntax check, unit test, smoke command, or diff review.

### 6. Mistake to rule

Add rules when they trace back to real failures. Avoid piling generic warnings into instructions; precise checks and lightweight tests usually work better.

## Body examples

| Tool class | Public-safe example |
|---|---|
| Filesystem + Git | Preserve durable state and inspect diffs |
| Shell + scripts | Run build, tests, lint, or small data checks |
| Browser | Verify web UI behavior or docs rendering |
| API client | Sync to optional external systems when configured |
| Local database | Keep source-of-truth data inspectable and exportable |

## Conclusion

When an agent behaves poorly, ask which layer failed:

- Was the model unable to reason about the task?
- Did the body lack the right tool?
- Did the harness fail to constrain, verify, or route the work?

Better agent behavior usually comes from improving all three layers while keeping private deployment details out of public examples.
