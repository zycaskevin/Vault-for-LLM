#!/usr/bin/env bash
# push_fixes.sh — 一鍵 commit 並 push 所有修復
# 用法：bash push_fixes.sh

set -e

echo "🔄 Vault-for-LLM 修復 Push 腳本"
echo "================================="

# 確認在正確目錄
if [ ! -f "pyproject.toml" ]; then
  echo "❌ 請在 Vault-for-LLM 根目錄執行此腳本"
  exit 1
fi

echo ""
echo "📋 修改摘要："
git diff --stat HEAD
echo ""

echo "🔐 安全掃描..."
LEAKED=$(grep -rn 'eyJ[A-Za-z0-9_-]\{50,\}' --include="*.py" . 2>/dev/null | grep -v ".git/" || true)
if [ -n "$LEAKED" ]; then
  echo "❌ 仍有 hardcoded JWT token！請先處理："
  echo "$LEAKED"
  exit 1
fi
echo "✅ 安全掃描通過"

echo ""
echo "📦 Staging all changes..."
git add .
git rm --cached duplicate_report.json trust_report.json 2>/dev/null || true

echo ""
echo "💾 Committing..."
git commit -m "fix(security): remove hardcoded supabase service key from scripts & tests

- scripts/sync_graph_to_supabase.py: read SUPABASE_URL/KEY from env
- scripts/fix_ek_links.py: same
- tests/test_e2e.py: skip Supabase test if env vars not set

fix(paths): replace all hardcoded personal paths with dynamic discovery

- scripts/_utils.py: new shared find_db_path() / load_dotenv_cascade()
- scripts/daily_knowledge_sync.py: use VAULT_DIR env + vault CLI
- scripts/deduplicate_semantic.py: use _utils.find_db_path
- scripts/sync_to_supabase.py: use _utils.load_dotenv_cascade
- scripts/suggest_new_knowledge.py: use _utils.find_db_path
- scripts/manual_review.py: use _utils.find_db_path
- tests/test_e2e.py: use PROJECT_ROOT, shutil.which('vault')

fix(bugs): CLI, lint, compile, frontmatter

- guardrails_lite/guardrails_cli.py: fix cmd_lint logic, yaml frontmatter
- guardrails_lite/guardrails_cli.py: add vault dedup command
- guardrails_lite/guardrails_compile.py: safe git add (raw/+compiled/ only)
- pyproject.toml: add vault-mcp entrypoint

chore: remove committed runtime artifacts

- duplicate_report.json: untracked (already in .gitignore)
- trust_report.json: untracked (already in .gitignore)

docs: update all READMEs

- Fix guardrails→vault command names in zh-Hant, zh-CN
- Add vault dedup, vault import, vault graph expand, vault config to CLI table
- Add MCP Server setup section (Claude Code / Cursor config)

ci: rebuild GitHub Actions workflow

- Correct trigger paths (raw/, guardrails_lite/, tests/)
- Add 3 jobs: lint-knowledge, test (pytest), security-check (secret scan)"

echo ""
echo "🚀 Pushing to GitHub..."
git push

echo ""
echo "✅ 全部完成！"
echo ""
echo "⚠️  重要提醒："
echo "   Supabase Service Role Key 已洩漏到 git history"
echo "   請立刻到 Supabase Dashboard → Settings → API → Rotate 金鑰"
echo "   舊 key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InptdHRscW1hbGxsdW9vcXhzd3F5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1OTM0Mzk0MywiZXhwIjoyMDc0OTE5OTQzfQ..."
