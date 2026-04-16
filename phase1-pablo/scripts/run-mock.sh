#!/usr/bin/env bash
# Boot the mock server + Vite dev server for frontend refinement.
#
# Usage:
#   ./scripts/run-mock.sh
#
# Stops both on Ctrl+C. Mock server serves /ws with realistic timings and
# tool-call events replayed from examples/sample-run/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

cleanup() {
  echo
  echo "Stopping services..."
  [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "${FRONTEND_PID:-}" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[1/2] Starting mock backend on :8000..."
uv run uvicorn decisionlab.mock_server:app --port 8000 --log-level warning &
BACKEND_PID=$!

echo "[2/2] Starting Vite dev server on :5173..."
(cd web && pnpm dev) &
FRONTEND_PID=$!

echo
echo "Mock backend  : http://localhost:8000/docs"
echo "Frontend      : http://localhost:5173"
echo "Press Ctrl+C to stop both."
echo

wait
