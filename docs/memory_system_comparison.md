# Memory System Comparison

This page positions Vault-for-LLM against common agent-memory systems. It is not a vendor benchmark; it is an operator checklist for choosing the right memory layer for a project.

## Short answer

Vault-for-LLM is strongest when you want a **local-first, inspectable, file-backed memory QA layer** for coding agents or project agents. It emphasizes candidate review, deterministic gates, bounded citations, Search QA snapshots, SQLite backups, and Markdown source control.

If you need hosted personalization memory with minimal infrastructure, Mem0 may be a better fit. If you want a complete stateful-agent runtime, Letta/MemGPT is closer. If you need enterprise temporal graph memory and managed scale, Zep is built for that class of deployment. If you already build in LangGraph, its long-term memory stores are the native framework path.

## Comparison table

| System | Primary shape | Best fit | Storage / control | Memory write model | Recall / retrieval model | QA / audit posture | Trade-offs vs Vault-for-LLM |
|---|---|---|---|---|---|---|---|
| **Vault-for-LLM** | Local SQLite + Markdown source + MCP tools | Project/coding-agent memory where operators want inspectability, backups, and regression tests | Local SQLite is source of truth; Markdown `raw/` can be reviewed and versioned | Candidate-first `remember`/`promote`, privacy/duplicate/metadata/quality gates, direct `vault_add` only for trusted compatibility | Keyword-first FTS/BM25 with fallback; optional semantic/hybrid vectors; Document Map for bounded reads | Built-in Search QA snapshots, public PR gate, privacy/history scan, artifact audit, backup/verify/restore | Not a hosted SaaS memory platform; semantic quality depends on configured embedding provider; no enterprise auth layer in local MCP server |
| **Mem0** | Universal/self-improving memory layer for LLM apps | Fast product integration for personalized agents across sessions | Managed platform or self-hosted open source stack depending on edition | Application/API-driven memory updates | Memory layer optimized for persistent user/application context | Product/platform oriented; external QA depends on integration | Less file-first/source-review oriented; less focused on local Markdown/SQLite workflows |
| **Letta / MemGPT** | Stateful agent runtime/platform with memory | Long-lived agents that remember, learn, and run inside a stateful agent framework | Letta platform/API and agent runtime abstractions | Agent-managed memory blocks, archival memory, and runtime state | Memory is part of the agent loop/context hierarchy | Provides agent/runtime concepts and eval tooling | Heavier runtime commitment; Vault can be used by many agents over MCP without making them run inside one runtime |
| **Zep** | Enterprise temporal graph memory / Context Graph / Context Lake | Enterprise agents needing governed context from chat, business data, documents, and JSON at scale | Managed/service-oriented enterprise memory | Graph/context ingestion from multiple sources | Temporal knowledge graph and token-efficient context serving | Enterprise governance/compliance posture | More infrastructure/platform dependence; Vault is smaller, local-first, and operator-readable |
| **LangGraph long-term memory** | Framework-native JSON document store | LangGraph applications that need cross-thread memory | In-memory or DB-backed stores such as PostgreSQL | Tools read/write namespaced memories through runtime store | Store search with optional indexing/embeddings | Framework-level responsibility; app teams define evals | Best inside LangGraph; Vault is framework-agnostic over CLI/MCP and emphasizes source files + Search QA |

## Practical selection guide

- Choose **Vault-for-LLM** when memory should be local, inspectable, backed up, cited from bounded source ranges, and measured with deterministic regression checks.
- Choose **Mem0** when the priority is quick product memory integration and managed/self-hosted persistent personalization.
- Choose **Letta/MemGPT** when you want the agent runtime itself to own memory and state.
- Choose **Zep** when you need enterprise-scale temporal graph context with governance and managed retrieval latency.
- Choose **LangGraph memory** when the app already lives in LangGraph and memory should be a framework store abstraction.

## Current Vault-for-LLM performance posture

Vault-for-LLM's default recall path is keyword-first and local, so small-to-medium project vaults should have low local latency without network calls. In local deterministic smoke tests, candidate promotion and CJK keyword recall can be validated without embeddings. Semantic/hybrid quality should be measured separately with the same provider/model/dimension used to build `semantic_vectors`.

Important limits:

- Search QA fixtures are regression smoke tests, not universal memory benchmarks.
- Hash embeddings validate semantic plumbing only; they are not semantic-quality evidence.
- Keyword search suppresses very weak multi-term matches by default, but production agents should still treat `vault_search` as navigation and use Document Map / `read_range` before final answers.
- Private or secret-like content is blocked by deterministic patterns, but privacy scanning is not a replacement for a full DLP system.

## Sources checked

- Mem0 docs describe Mem0 as a universal, self-improving memory layer for LLM applications: <https://docs.mem0.ai/introduction>
- Letta docs describe a platform for stateful agents that remember, learn, and improve over time: <https://docs.letta.com/guides/get-started/intro>
- Zep docs describe enterprise agent memory using temporal Context Graphs and a governed Context Lake: <https://help.getzep.com/overview>
- LangChain docs describe LangGraph long-term memories as JSON documents in namespaced stores: <https://docs.langchain.com/oss/python/langchain/long-term-memory>
