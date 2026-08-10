#!/bin/bash
# run.sh — start the app for everyday use (backend + frontend, then open the browser).
#
# This is the "just run it" launcher. It assumes dependencies are already
# installed; if you need to set the project up first, use ./dev.sh once.
set -e
cd "$(dirname "$0")"

# Activate an existing virtualenv (prefer .venv, fall back to .venv-windows).
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
elif [ -f .venv-windows/Scripts/activate ]; then
  source .venv-windows/Scripts/activate
else
  echo "No virtualenv found. Run ./dev.sh once, or:"
  echo "    uv sync --group backend --group dev"
  exit 1
fi

echo "Starting backend with config.yaml deployment settings ..."
python -m backend &
BACKEND_PID=$!

URL="http://localhost:8000/docs"
if [ -d frontend ] && command -v npm >/dev/null 2>&1; then
  echo "Starting frontend on http://localhost:5173 ..."
  (cd frontend && npm run dev) &
  URL="http://localhost:5173"
elif [ -d frontend/dist ]; then
  echo "Node/npm not found, but frontend/dist is built — serving it from the backend on http://localhost:8000."
  URL="http://localhost:8000"
else
  echo "Node/npm or frontend/ not found — running backend only (API docs at $URL)."
fi

# Open the browser (best-effort; ignore if no opener is available).
( command -v xdg-open >/dev/null 2>&1 && xdg-open "$URL" ) \
  || ( command -v open >/dev/null 2>&1 && open "$URL" ) \
  || echo "Open $URL in your browser."

echo "Running. Press Ctrl+C to stop."
wait $BACKEND_PID
