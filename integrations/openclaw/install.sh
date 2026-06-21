#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SRC_DIR}/../.." && pwd)"
OPENCLAW_DIR="${OPENCLAW_DIR:-${HOME}/.openclaw}"
SKILL_DIR="${OPENCLAW_DIR}/skills/vault-for-llm"
EXT_DIR="${OPENCLAW_DIR}/extensions/vault-for-llm"
SCOPE=""
PROJECT_DIR="${VAULT_OPENCLAW_PROJECT_DIR:-}"
NON_INTERACTIVE=0

usage() {
  cat <<'EOF'
Usage:
  install.sh [options]

Options:
  --scope <mode>          shared | private | temporary
                          shared: use a cross-agent project vault
                          private: use OpenClaw's own isolated vault
                          temporary: use a throwaway vault for demos/tests
  --project-dir <path>    explicit Vault project directory; overrides --scope default
  --non-interactive       do not prompt; default scope is private
  --help                  show this help
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --scope)
      if [ $# -lt 2 ]; then
        echo "Missing value for --scope" >&2
        usage
        exit 1
      fi
      SCOPE="$2"
      shift 2
      ;;
    --project-dir)
      if [ $# -lt 2 ]; then
        echo "Missing value for --project-dir" >&2
        usage
        exit 1
      fi
      PROJECT_DIR="$2"
      shift 2
      ;;
    --non-interactive) NON_INTERACTIVE=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

expand_path() {
  local path="$1"
  if [[ "$path" == "~/"* ]]; then
    printf "%s/%s" "$HOME" "${path#~/}"
  elif [ "$path" = "~" ]; then
    printf "%s" "$HOME"
  else
    printf "%s" "$path"
  fi
}

select_project_dir() {
  if [ -n "$PROJECT_DIR" ]; then
    PROJECT_DIR="$(expand_path "$PROJECT_DIR")"
    return 0
  fi

  if [ -z "$SCOPE" ] && [ "$NON_INTERACTIVE" -eq 0 ] && [ -t 0 ]; then
    cat <<'EOF'
Choose Vault memory scope:

  1) shared     Use the same project memory across Hermes, OpenClaw, Codex, Claude Code, and n8n.
  2) private    Give OpenClaw its own isolated Vault project. Recommended for experiments.
  3) temporary  Use a throwaway Vault for demos/tests.

EOF
    printf "Selection [1-3, default 2]: "
    read -r pick
    case "${pick:-2}" in
      1) SCOPE="shared" ;;
      2) SCOPE="private" ;;
      3) SCOPE="temporary" ;;
      *) echo "Invalid selection: ${pick}" >&2; exit 1 ;;
    esac
  fi

  SCOPE="${SCOPE:-private}"
  case "$SCOPE" in
    shared)
      PROJECT_DIR="${HOME}/Vaults/project-memory"
      ;;
    private)
      PROJECT_DIR="${OPENCLAW_DIR}/workspace/vault-project"
      ;;
    temporary)
      PROJECT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/vault-openclaw.XXXXXX")"
      ;;
    *)
      echo "Invalid --scope '${SCOPE}' (expected shared|private|temporary)" >&2
      exit 1
      ;;
  esac

  if [ "$NON_INTERACTIVE" -eq 0 ] && [ -t 0 ] && [ "$SCOPE" != "temporary" ]; then
    printf "Vault project directory [%s]: " "$PROJECT_DIR"
    read -r custom_dir
    if [ -n "$custom_dir" ]; then
      PROJECT_DIR="$(expand_path "$custom_dir")"
    fi
  fi
}

select_project_dir

mkdir -p "${SKILL_DIR}/bin" "${EXT_DIR}"
cp "${SRC_DIR}/SKILL.md" "${SKILL_DIR}/SKILL.md"
cp "${SRC_DIR}/bin/vault-openclaw" "${SKILL_DIR}/bin/vault-openclaw"
cp "${SRC_DIR}/index.ts" "${EXT_DIR}/index.ts"
cp "${SRC_DIR}/openclaw.plugin.json" "${EXT_DIR}/openclaw.plugin.json"
chmod +x "${SKILL_DIR}/bin/vault-openclaw"

export VAULT_OPENCLAW_REPO="${VAULT_OPENCLAW_REPO:-${REPO_ROOT}}"
export VAULT_OPENCLAW_PROJECT_DIR="${PROJECT_DIR}"
"${SKILL_DIR}/bin/vault-openclaw" init >/dev/null

cat <<EOF
Vault-for-LLM OpenClaw adapter installed.

Vault memory scope:
  scope:       ${SCOPE:-explicit}
  projectDir:  ${PROJECT_DIR}

Agents that use the same projectDir share one vault.db. Use separate
projectDir values for isolated agent memory or experiments.

Add or merge this into ${OPENCLAW_DIR}/openclaw.json:

{
  "plugins": {
    "entries": {
      "vault-for-llm": {
        "enabled": true,
        "config": {
          "wrapperPath": "${SKILL_DIR}/bin/vault-openclaw",
          "projectDir": "${PROJECT_DIR}",
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
