#!/usr/bin/env bash
# Linting and formatting checks - equivalent to RuboCop in the Rails API.
# Usage:
#   ./scripts/lint.sh          # check only (CI mode)
#   ./scripts/lint.sh --fix    # auto-fix safe violations

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FIX=false
if [[ "${1:-}" == "--fix" ]]; then
  FIX=true
fi

echo "[LINT] Ruff v$(ruff --version | awk '{print $2}')"

if $FIX; then
  echo "[LINT] Running ruff format (auto-format)..."
  ruff format .

  echo "[LINT] Running ruff check --fix (auto-fix linting)..."
  ruff check . --fix
else
  echo "[LINT] Running ruff format --check..."
  ruff format . --check

  echo "[LINT] Running ruff check..."
  ruff check .
fi

echo "[LINT] Done - no violations found."
