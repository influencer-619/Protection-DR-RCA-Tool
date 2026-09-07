#!/usr/bin/env bash
# Run Protection RCA backend + frontend tests.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Backend pytest"
cd "$ROOT/backend"
export PYTHONPATH="${PYTHONPATH:-}:$ROOT/backend"
if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
pytest -q "$@"

echo "==> Frontend vitest"
cd "$ROOT/frontend"
if [[ ! -d node_modules ]]; then
  npm install
fi
npm test

echo "==> All tests finished"
