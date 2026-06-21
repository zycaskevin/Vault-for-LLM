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
FEATURES=""
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
  --features <csv>        optional features: core,mcp,semantic,supabase,dev
                          default is core; core is always included
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
    --features)
      if [ $# -lt 2 ]; then
        echo "Missing value for --features" >&2
        usage
        exit 1
      fi
      FEATURES="$2"
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

normalize_features() {
  local raw="${1:-core}"
  raw="${raw// /}"
  if [ -z "$raw" ]; then
    raw="core"
  fi
  if [[ ",${raw}," != *",core,"* ]]; then
    raw="core,${raw}"
  fi
  IFS=',' read -r -a parts <<< "$raw"
  local normalized=""
  local feature
  for feature in "${parts[@]}"; do
    case "$feature" in
      ""|core|mcp|semantic|supabase|dev) ;;
      *)
        echo "Invalid feature '${feature}' (expected core,mcp,semantic,supabase,dev)" >&2
        exit 1
        ;;
    esac
    if [ -n "$feature" ] && [[ ",${normalized}," != *",${feature},"* ]]; then
      if [ -z "$normalized" ]; then
        normalized="$feature"
      else
        normalized="${normalized},${feature}"
      fi
    fi
  done
  FEATURES="${normalized:-core}"
}

select_features() {
  if [ -z "$FEATURES" ] && [ "$NON_INTERACTIVE" -eq 0 ] && [ -t 0 ]; then
    cat <<'EOF'
Choose optional Vault features:

  core      Local SQLite + Markdown + keyword search. Always included.
  mcp       Local stdio MCP tools for MCP-capable agents.
  semantic  Embedding-backed semantic/hybrid retrieval. Larger optional deps.
  supabase  Optional remote sync/read path. Requires credentials.
  dev       Source checkout tests, benchmarks, and PR validation.

EOF
    printf "Features [comma-separated, default core]: "
    read -r FEATURES
  fi

  normalize_features "${FEATURES:-core}"
}

has_feature() {
  [[ ",${FEATURES}," == *",$1,"* ]]
}

print_feature_plan() {
  cat <<EOF
Selected optional features:
  features:    ${FEATURES}

Recommended install commands:
  core:        python -m pip install vault-for-llm
EOF
  if has_feature mcp; then
    cat <<'EOF'
  mcp:         python -m pip install "vault-for-llm[mcp]"
               vault-mcp --project-dir <projectDir>
EOF
  fi
  if has_feature semantic; then
    cat <<'EOF'
  semantic:    python -m pip install "vault-for-llm[semantic]"
               vault install-embedding --model mix
               vault semantic rebuild --project-dir <projectDir> --persist-cache --pretty
EOF
  fi
  if has_feature supabase; then
    cat <<'EOF'
  supabase:    python -m pip install "vault-for-llm[supabase]"
               export SUPABASE_URL=...
               export SUPABASE_SERVICE_ROLE_KEY=...
               python scripts/sync_to_supabase.py --document-map
EOF
  fi
  if has_feature dev; then
    cat <<'EOF'
  dev:         python -m pip install -e ".[dev]"
               python scripts/readme_command_smoke.py
               python -m pytest -q
EOF
  fi
  cat <<'EOF'

Do not enable semantic or Supabase extras silently. Ask the user first because
they add heavier dependencies, model/provider setup, or remote credentials.

EOF
}

select_project_dir
select_features

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

EOF

print_feature_plan

cat <<EOF
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
