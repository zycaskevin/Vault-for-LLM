# LLM Integration

Vault-for-LLM is local-first. The core path does not require an LLM API key, a
local model, or network access.

LLM providers are optional helpers for workflows that benefit from judgment or
summarization. When a provider is missing, normal compile, keyword search,
bounded reads, candidate memory, and automation reports should still work.

## Where LLMs Are Used

| Area | Purpose | Safe fallback |
|---|---|---|
| `vault converge` | Ask a model whether a knowledge area is sufficient or still underspecified | Report remains rule-based or blocked with a clear message |
| `vault cross-validate` | Compare local and cloud model judgments for selected memories | Command can be skipped without affecting the vault |
| Import/contextual retrieval | Generate local context summaries around chunks | Use deterministic chunking instead |
| Optional query rewrite | Rewrite or decompose a search query | Use keyword/semantic search directly |

## Providers

`vault.llm.create_llm_provider()` supports:

- `ollama`: local Ollama server
- `claude`: Anthropic API through `ANTHROPIC_API_KEY`
- `openai`: OpenAI API through `OPENAI_API_KEY`
- `mock`: deterministic test provider
- `auto`: try Ollama first, then configured cloud providers

Cloud providers are not installed or called by default. Agent installers should
ask before enabling them, and should explain where the key will live.

## Compile And Embeddings

Embeddings are separate from LLM generation. `vault compile` can build the
SQLite knowledge database even when embedding dependencies are missing.

Use this for the most portable first-run path:

```bash
vault compile --no-embed
```

If embedding generation is enabled but the optional stack fails at encode time,
Vault keeps the compiled knowledge rows and reports `embedding_errors` instead
of failing the entire compile. Install semantic dependencies only when the user
explicitly wants semantic/vector retrieval.

## Security Notes

- Treat LLM output as suggestions, not a source of truth.
- Keep candidate-first writes for model-generated memory.
- Do not send private memories to cloud providers unless the user explicitly
  opts in.
- Keep citations tied to original `vault map read` / `vault_read_range` output,
  not to model summaries.
