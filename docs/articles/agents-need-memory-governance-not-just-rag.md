# Agents Need Memory Governance, Not Just RAG

AI agents are becoming useful enough to work across sessions, tools, repos, and
teams. That creates a new problem: the hard part is no longer only retrieval.
The hard part is deciding what an agent is allowed to remember, what should be
trusted, what must stay private, what has become stale, and how a team can undo
bad memory.

RAG helps an agent read. Memory governance helps an agent write, review, reuse,
and roll back memory.

## Stateless Agents Forget The Work

A stateless agent starts every session like it is the first day on the project.
Teams compensate by pasting long context, keeping private chat threads open, or
letting each tool build its own hidden memory. That works for a while, but the
knowledge scatters:

- one agent remembers a deployment rule;
- another remembers a bug root cause;
- a third remembers a product decision;
- none of them share the same reviewed source of truth.

This is why project memory cannot live only inside one model, one chat product,
or one notebook.

## RAG Reads; Agents Also Write

Traditional RAG answers a narrower question: "Can I find the right chunk?"

Agent memory has a wider lifecycle:

```text
propose -> review -> promote -> search -> bounded read -> rollback -> audit
```

That lifecycle matters because agents do not only consume knowledge. They also
create new lessons while working. If every lesson goes straight into active
memory, the vault becomes polluted. If nothing is saved, every session repeats
the same onboarding.

The useful middle path is candidate-first memory: agents propose, humans or
trusted reviewers approve, and active memory stays clean.

## Shared Memory Needs Governance

Multi-agent workflows need shared memory, but shared memory has predictable
failure modes:

- **Pollution**: low-quality notes enter long-term memory.
- **Conflict**: two agents record different versions of the same fact.
- **Permission drift**: private profile memory leaks into shared project memory.
- **Staleness**: old facts remain searchable after they stop being true.
- **No rollback**: a bad promotion is hard to inspect or undo.

These are governance problems, not just retrieval problems.

## Vault-for-LLM's Approach

Vault-for-LLM is a local-first memory governance layer for agents. It keeps the
source of truth inspectable: Markdown, SQLite, bounded reads, backups, audit
events, and candidate-first workflows.

Its job is not to replace the model, a wiki, Obsidian, or hosted memory systems.
Its job is to sit between them and answer:

- Who proposed this memory?
- Did it pass privacy, duplicate, metadata, and quality gates?
- Who promoted it into active knowledge?
- Can another agent find it without reading private notes?
- Can the operator cite the exact source range?
- Can the system roll back or audit the change?

## The Killer Demo

Run:

```bash
vault demo agent-governance --json
```

The demo simulates three agent identities sharing one Vault:

- Codex proposes a reusable project lesson.
- Claude Code reviews and promotes it after gates pass.
- Hermes searches the shared vault and uses bounded read before citing it.

The generated report proves the full lifecycle:

```text
propose -> review -> promote -> search -> bounded read -> rollback -> audit
```

This is the difference between another RAG database and a memory foundation for
agent workflows.

## The Product Bet

The next generation of agents does not need one more place to dump text. It
needs a governed memory layer that can move across tools without becoming a
black box.

Agent memory is not about remembering more.

It is about remembering with trust, review, rollback, and audit.
