#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SRC_DIR}/../.." && pwd)"
WRAPPER="${VAULT_OPENCLAW_WRAPPER:-${SRC_DIR}/bin/vault-openclaw}"

export VAULT_OPENCLAW_REPO="${VAULT_OPENCLAW_REPO:-${REPO_ROOT}}"

echo "Checking Vault-for-LLM OpenClaw adapter..."
echo "  wrapper: ${WRAPPER}"

if [ ! -x "${WRAPPER}" ]; then
  echo "ERROR: wrapper is not executable: ${WRAPPER}" >&2
  exit 1
fi

echo ""
echo "[1/4] Initialize or open project"
"${WRAPPER}" init >/tmp/vault-openclaw-init.json
python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("/tmp/vault-openclaw-init.json").read_text())
print(f"  project_dir: {data.get('project_dir')}")
print(f"  db_exists: {data.get('db_exists')}")
print(f"  raw_exists: {data.get('raw_exists')}")
if not data.get("db_exists"):
    raise SystemExit("Vault DB was not initialized")
PY

echo ""
echo "[2/4] MCP config snippet"
"${WRAPPER}" mcp-config >/tmp/vault-openclaw-mcp.json
python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("/tmp/vault-openclaw-mcp.json").read_text())
server = data["mcpServers"]["vault-for-llm"]
print(f"  command: {server['command']}")
print(f"  args: {' '.join(server['args'])}")
PY

echo ""
echo "[3/4] Search smoke"
"${WRAPPER}" search "openclaw vault connection health check" --limit 3 >/tmp/vault-openclaw-search.json
python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("/tmp/vault-openclaw-search.json").read_text())
print(f"  result_type: {type(data).__name__}")
print(f"  result_count: {len(data) if isinstance(data, list) else 'n/a'}")
PY

echo ""
echo "[4/4] Source syntax smoke"
python3 -m py_compile "${WRAPPER}"

echo ""
echo "OK: OpenClaw can call Vault-for-LLM."
