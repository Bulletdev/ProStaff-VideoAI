#!/usr/bin/env bash
# Full quality gate: lint + security audit.
# Run before opening a PR.
# Usage: ./scripts/full_audit.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "============================================================"
echo " ProStaff VideoAI - Full Audit"
echo "============================================================"

echo ""
"$SCRIPT_DIR/lint.sh"

echo ""
"$SCRIPT_DIR/security_audit.sh"

echo ""
echo "============================================================"
echo " Full audit PASSED - ready to merge."
echo "============================================================"
