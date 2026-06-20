#!/usr/bin/env bash
# Security audit - equivalent to Brakeman + Semgrep in the Rails API.
# Runs Bandit (static AST analysis) and Semgrep (pattern-based rules).
# Usage: ./scripts/security_audit.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FAILED=false

echo "============================================================"
echo " ProStaff VideoAI - Security Audit"
echo "============================================================"

# --- Bandit ---
echo ""
echo "[BANDIT] Running static security analysis..."
if ! command -v bandit &>/dev/null; then
  echo "[BANDIT] ERROR: bandit not installed. Run: pip install bandit[toml]"
  exit 1
fi

if bandit -r . -x ./tests,./.venv --configfile pyproject.toml --format txt; then
  echo "[BANDIT] Passed - no issues found."
else
  echo "[BANDIT] FAILED - review issues above."
  FAILED=true
fi

# --- Semgrep ---
echo ""
echo "[SEMGREP] Running pattern-based security rules (p/python + p/bandit)..."
if ! command -v semgrep &>/dev/null; then
  echo "[SEMGREP] ERROR: semgrep not installed. Run: pip install semgrep"
  exit 1
fi

# p/python: general Python security rules
# p/bandit: Bandit rule parity in Semgrep
if semgrep --config p/python --config p/bandit \
     --exclude tests --exclude .venv \
     --error .; then
  echo "[SEMGREP] Passed - no issues found."
else
  echo "[SEMGREP] FAILED - review issues above."
  FAILED=true
fi

echo ""
echo "============================================================"
if $FAILED; then
  echo " Security audit FAILED - address issues before merging."
  echo "============================================================"
  exit 1
else
  echo " Security audit PASSED."
  echo "============================================================"
fi
