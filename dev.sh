#!/bin/bash
# dev.sh — start backend + frontend for local development (run from the repo root)
set -e
cd "$(dirname "$0")"

echo "Starting backend..."
if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required for source development. See docs/INSTALL.md."
  exit 1
fi
uv sync --group backend --group dev
# Reload mode uses one API worker.
# Run from the repo root: config.yaml and the ./processed static mount resolve from here
uv run --no-sync uvicorn backend.main:app --reload --port 8000 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID (http://localhost:8000)"

if [ -d frontend ]; then
  echo "Starting frontend..."
  (cd frontend && npm install && npm run dev) &
  FRONTEND_PID=$!
  echo "Frontend PID: $FRONTEND_PID"
  echo "Open http://localhost:5173"
  echo "Press Ctrl+C to stop both servers"
  wait $BACKEND_PID $FRONTEND_PID
else
  echo "frontend/ not found — skipping frontend dev server"
  echo "Backend running at http://localhost:8000"
  echo "Press Ctrl+C to stop"
  wait $BACKEND_PID
fi
