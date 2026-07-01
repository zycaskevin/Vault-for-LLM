# uv Development Workflow

Date: 2026-07-02

## Decision

Vault-for-LLM commits `uv.lock` and supports `uv` as the reproducible
source-development workflow for maintainers, CI smoke checks, and coding
agents.

The public install path remains `pip install vault-for-llm`.

## Why

Vault is increasingly installed, tested, and modified by agents. A lockfile
gives those agents a stable way to rebuild the same development environment
without guessing dependency versions. This is useful for source checkouts,
release preparation, and local verification.

At the same time, Vault is a Python package. Normal users should not need to
learn a second tool before trying it.

## Policy

- Keep `pip` documentation as the public user path.
- Add `uv` documentation for source development and agent workflows.
- Commit `uv.lock`.
- Run `uv lock` in the same PR whenever `pyproject.toml` dependencies change.
- CI should keep the existing pip test/build matrix and add a small uv smoke
  check instead of replacing the pip path.
- Default uv smoke checks should use `dev,mcp`; semantic extras stay opt-in
  because they are much heavier.

## Non-Goals

This does not make uv mandatory for downstream package users. It also does not
replace trusted publishing, wheel smoke tests, or clean PyPI install checks.
