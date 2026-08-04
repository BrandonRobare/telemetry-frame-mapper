#!/bin/bash
# dev.sh — start backend + frontend for local development (run from the repo root)
set -e
cd "$(dirname "$0")"

echo "Starting backend..."
if [ ! -d .venv ]; then
  python3 -m venv .venv 2>/dev/null || python -m venv .venv
fi
# Git Bash on Windows puts the activate script in Scripts/, Linux/macOS in bin/
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
else
  source .venv/Scripts/activate
fi
python -m pip install -e ".[backend,dev]"
# Reload mode uses one API worker.
# Run from the repo root: config.yaml and the ./processed static mount resolve from here
uvicorn backend.main:app --reload --port 8000 &
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
