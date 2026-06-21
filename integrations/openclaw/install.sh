#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SRC_DIR}/../.." && pwd)"
OPENCLAW_DIR="${OPENCLAW_DIR:-${HOME}/.openclaw}"
SKILL_DIR="${OPENCLAW_DIR}/skills/vault-for-llm"
EXT_DIR="${OPENCLAW_DIR}/extensions/vault-for-llm"

mkdir -p "${SKILL_DIR}/bin" "${EXT_DIR}"
cp "${SRC_DIR}/SKILL.md" "${SKILL_DIR}/SKILL.md"
cp "${SRC_DIR}/bin/vault-openclaw" "${SKILL_DIR}/bin/vault-openclaw"
cp "${SRC_DIR}/index.ts" "${EXT_DIR}/index.ts"
cp "${SRC_DIR}/openclaw.plugin.json" "${EXT_DIR}/openclaw.plugin.json"
chmod +x "${SKILL_DIR}/bin/vault-openclaw"

export VAULT_OPENCLAW_REPO="${VAULT_OPENCLAW_REPO:-${REPO_ROOT}}"
"${SKILL_DIR}/bin/vault-openclaw" init >/dev/null

cat <<EOF
Vault-for-LLM OpenClaw adapter installed.

Add or merge this into ${OPENCLAW_DIR}/openclaw.json:

{
  "plugins": {
    "entries": {
      "vault-for-llm": {
        "enabled": true,
        "config": {
          "wrapperPath": "${SKILL_DIR}/bin/vault-openclaw",
          "autoRecall": false,
          "autoRecallResults": 3
        }
      }
    },
    "allow": ["vault-for-llm"]
  }
}

Then restart OpenClaw:
  openclaw gateway restart

Verify:
  bash ${SRC_DIR}/verify.sh
EOF
