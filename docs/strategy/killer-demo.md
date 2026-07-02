# Killer Demo: Governed Shared Memory Across Agents

The most important demo is not "Vault can search memory." That sounds like RAG.

The demo should prove this:

> Multiple agents can share project memory, but only through reviewable,
> source-grounded, rollbackable governance.

## Agents

Use common public agent surfaces:

- Claude Code
- Codex
- Hermes Agent

Avoid private agent lore or personal names in public demo material.

## Scenario

A repo has a testing pitfall. One agent discovers that a test command requires
specific environment setup before it can be trusted.

### Step 1: Agent Proposes A Memory

An agent fixes or diagnoses the issue and proposes:

```text
Title: Test runs require the documented environment setup before pytest
Source: PR, commit, CI log, or issue reference
Trust: 0.6
Sensitivity: low
Status: candidate
```

The key point: the lesson exists, but it is not active shared memory yet.

### Step 2: Another Agent Can See It Is A Candidate

Another agent searches and sees a warning:

```text
Found candidate memory, not promoted.
Use with caution and cite the source before relying on it.
```

This proves that unreviewed memory does not silently pollute active knowledge.

### Step 3: Operator Promotes It

A human or authorized review agent checks the source, then promotes:

```text
Status: promoted
Trust: 0.9
Promoted by: authorized reviewer
Evidence: CI log + commit reference
```

### Step 4: A Third Agent Uses It Correctly

A new session starts. The agent searches Vault, finds the promoted memory, reads
only the bounded evidence range, cites it, and runs the correct test command.

This proves cross-agent continuity.

### Step 5: Rollback Or Deprecate

Later, the repo changes and the old setup rule is no longer true.

The operator deprecates it:

```text
Status: deprecated
Reason: replaced by new testing workflow
Replaced by: current testing SOP
```

This proves that memory can stop being active without disappearing from audit
history.

## Existing Demo Command

Run:

```bash
vault demo agent-governance --json
```

The demo should stay aligned with this lifecycle:

```text
propose -> review -> promote -> search -> bounded read -> rollback -> audit
```

## What The Demo Must Not Become

Do not frame it as:

- "semantic search is better"
- "another project wiki"
- "Obsidian with vectors"
- "a chatbot remembers a preference"

Frame it as:

> Agents can learn from each other without turning shared memory into a garbage
> pile.
