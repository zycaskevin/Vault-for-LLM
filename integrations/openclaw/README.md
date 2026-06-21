# OpenClaw Adapter

This adapter lets OpenClaw expose Vault-for-LLM as governed project memory.

It provides two integration styles:

1. `vault-openclaw`, a small CLI wrapper around Vault's MCP tool handlers.
2. An OpenClaw plugin extension that registers manual tools:
   `vault_search`, `vault_read_range`, `vault_memory_propose`, and `vault_stats`.

Auto-recall is intentionally disabled by default. Vault-for-LLM is best used as
project memory governance: search, bounded read, then cite. New memories should
start as candidates.

## Install

From a source checkout:

```bash
bash integrations/openclaw/install.sh
```

The installer copies the wrapper, skill, and plugin extension into:

```text
~/.openclaw/skills/vault-for-llm/
~/.openclaw/extensions/vault-for-llm/
```

It also prints the config entry to add to `~/.openclaw/openclaw.json`.

During install, choose whether OpenClaw should use a shared Vault project or its
own isolated database:

| Scope | Meaning |
|---|---|
| `shared` | OpenClaw points to the same `projectDir` as Hermes, Codex, Claude Code, or n8n. |
| `private` | OpenClaw gets its own isolated Vault project. |
| `temporary` | OpenClaw uses a throwaway Vault for tests or demos. |

Non-interactive examples:

```bash
bash integrations/openclaw/install.sh --scope private --non-interactive

bash integrations/openclaw/install.sh \
  --scope shared \
  --project-dir ~/Vaults/my-project \
  --non-interactive
```

## Configure

Set the wrapper path and project directory in OpenClaw. Agents that use the same
`projectDir` share one `vault.db`; different `projectDir` values are isolated.

```json
{
  "plugins": {
    "entries": {
      "vault-for-llm": {
        "enabled": true,
        "config": {
          "wrapperPath": "~/.openclaw/skills/vault-for-llm/bin/vault-openclaw",
          "projectDir": "~/.openclaw/workspace/vault-project",
          "autoRecall": false,
          "autoRecallResults": 3
        }
      }
    },
    "allow": ["vault-for-llm"]
  }
}
```

Restart the gateway after editing config:

```bash
openclaw gateway restart
```

## Environment

| Variable | Purpose |
|---|---|
| `VAULT_OPENCLAW_PROJECT_DIR` | Vault project directory. Defaults to `~/.openclaw/workspace/vault-project`. |
| `VAULT_OPENCLAW_REPO` | Optional source checkout path when running without an installed wheel. |
| `VAULT_OPENCLAW_PYTHON` | Optional Python 3.10+ interpreter override. |

## Verify

```bash
bash integrations/openclaw/verify.sh
```

Or call the installed wrapper directly:

```bash
~/.openclaw/skills/vault-for-llm/bin/vault-openclaw init
~/.openclaw/skills/vault-for-llm/bin/vault-openclaw search "what should this agent know?" --limit 5
```

## MCP

OpenClaw can also use Vault through a generic stdio MCP configuration when the
runtime supports MCP server registration:

```bash
vault-openclaw mcp-config
```

The MCP server exposes the fuller Vault tool surface, including
`vault_memory_promote`, `vault_dream_run`, `vault_map_show`, and optional remote
read tools.
