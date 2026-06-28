# OKF Integration

Open Knowledge Format, or OKF, is a portable Markdown bundle pattern for agent
knowledge. An OKF bundle is a directory of concept files with YAML frontmatter,
ordinary Markdown body content, optional `index.md` files, and a `log.md` update
history.

Vault-for-LLM should treat OKF as an exchange format, not as a replacement for
the local vault.

```text
OKF bundle          portable agent knowledge files
Vault-for-LLM       local governance, search, review, automation, and MCP layer
```

## Why It Matters

OKF and Vault share the same basic belief: agent knowledge should be inspectable
files that can be reviewed, versioned, moved, and improved over time.

OKF contributes a simple interoperability shape:

- a knowledge package is a folder
- each Markdown file is a concept
- each concept has YAML frontmatter
- `type` identifies how consumers should route the concept
- Markdown links form a lightweight graph
- `index.md` supports progressive disclosure
- `log.md` records bundle changes

Vault contributes the runtime layer OKF does not define:

- SQLite-backed search and bounded reads
- candidate-first memory review
- privacy and quality gates
- temporal validity, freshness, and lifecycle automation
- access metadata for multi-agent use
- MCP and CLI integration
- local GUI governance

## Concept Mapping

| OKF field | Vault field |
|---|---|
| `type` | `memory_type` or `category` |
| `title` | `title` |
| `description` | `summary` |
| `resource` | `source_ref` or `source` |
| `tags` | `tags` |
| `timestamp` | `updated_at`, `valid_from`, or source timestamp |
| Markdown body | `content_raw` |
| Markdown links | graph edges or Document Map references |

Vault-specific governance fields can be preserved as custom frontmatter:

```yaml
scope: project
sensitivity: low
owner_agent: ""
allowed_agents: []
memory_type: playbook
valid_from: 2026-06-28T00:00:00Z
valid_until: ""
expires_at: ""
```

OKF consumers should ignore unknown fields. That makes it reasonable for Vault
to export extra governance metadata while still producing readable Markdown.

## Import Direction

`vault import okf` should turn an OKF bundle into reviewable Vault knowledge.

Current command:

```bash
vault import okf --bundle ./okf-bundle --dry-run --json --pretty
vault import okf --bundle ./okf-bundle --scope shared --owner-agent work-agent
```

This import is candidate-first. It writes OKF concepts into
`memory_candidates`, not active knowledge. Each imported concept still goes
through the normal privacy, duplicate, metadata, and quality gates before it can
be promoted. Use `vault candidates` and
`vault promote <candidate_id> --confirm` to review and activate entries.

Recommended behavior:

- parse each Markdown concept with YAML frontmatter
- require a non-empty `type`
- map OKF fields into Vault metadata
- preserve unknown frontmatter fields in metadata where possible
- extract Markdown links into graph candidates
- use candidate mode by default for untrusted bundles
- allow `--promote-if-safe` only when privacy and metadata gates pass
- tolerate broken links and report them as warnings, not hard failures

Candidate-first import is important. An OKF bundle is portable, but portability
does not make it trusted.

## Export Direction

`vault export okf` should make Vault knowledge portable for other agents and
tools.

Current command:

```bash
vault export okf --bundle ./okf-bundle --dry-run --json --pretty
vault export okf --bundle ./okf-bundle --category workflow --min-trust 0.7
```

The exporter is read-only against `vault.db`. It writes `index.md`, `log.md`,
and `concepts/<type>/*.md`. By default it excludes `scope: private` and
`sensitivity: restricted` memories. Use `--include-private` or
`--include-restricted` only when intentionally creating a private/internal
bundle.

Recommended output:

```text
okf-bundle/
  index.md
  log.md
  concepts/
    deployment-sop.md
    database-schema.md
    support-playbook.md
```

Export rules:

- one active knowledge entry becomes one concept file
- `type` is derived from `memory_type` first, then `category`
- `description` uses `summary`
- `resource` uses `source_ref` when available
- `timestamp` uses the last updated timestamp
- `index.md` groups concepts by type/category
- `log.md` summarizes recent promotions, updates, reviews, and archives
- private or restricted memory is excluded unless explicitly requested

## Validation Direction

`vault okf validate` should check bundle structure before import or publication.

Current command:

```bash
vault okf validate ./okf-bundle
vault okf validate ./okf-bundle --json --pretty
```

The validator is read-only. It exits with status code `0` when the bundle has no
errors, and `1` when required structure is missing or invalid. Warnings, such as
broken local Markdown links, are reported without blocking the bundle.

Minimum checks:

- every concept file has parseable YAML frontmatter
- every concept file has a non-empty `type`
- `index.md` and `log.md` are allowed and parsed separately
- broken links are warnings
- duplicate concept paths are errors
- unsupported fields are informational, not errors

Optional checks:

- missing `title`
- missing `description`
- stale `timestamp`
- invalid temporal fields
- unsafe governance downgrade, such as `sensitivity: restricted` exported as
  `low`

## Product Positioning

Vault should say:

> Vault-for-LLM can import and export OKF-style bundles, then add what a file
> format does not provide: local search, candidate review, privacy gates,
> temporal memory, MCP access, automation, and GUI governance.

This keeps the boundary clear:

- OKF is the portable knowledge package.
- Vault is the user-owned memory engine that makes the package safe and useful.

## Implementation Plan

1. Add documentation and decision record for the OKF boundary.
2. Add `vault okf validate` for local bundle checks. Done.
3. Add `vault import okf` in candidate-first mode. Done.
4. Add `vault export okf` with safe defaults that exclude private/restricted
   memory. Done.
5. Add Search QA fixtures that verify imported concepts are searchable and
   bounded reads cite the exported source. Done with an export -> validate ->
   import candidates -> promote -> Search QA -> bounded read roundtrip test.
