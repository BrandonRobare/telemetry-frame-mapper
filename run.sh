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
FRONTEND_PID=""

cleanup() {
  # #862: the frontend must not outlive a failed or exited backend. The
  # waiter below also handles backend death; this covers normal shutdown.
  if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

URL="http://localhost:8000/docs"
if [ -d frontend ] && command -v npm >/dev/null 2>&1; then
  echo "Starting frontend on http://localhost:5173 ..."
  # Watch the backend from inside the frontend subshell and take npm with it
  # when the backend dies — a dead API must not leave :5173 serving (#862).
  (
    cd frontend
    npm run dev &
    NPM_PID=$!
    while kill -0 "$BACKEND_PID" 2>/dev/null; do
      sleep 1
    done
    pkill -TERM -P "$NPM_PID" 2>/dev/null || true
    kill "$NPM_PID" 2>/dev/null || true
    exit 0
  ) &
  FRONTEND_PID=$!
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
status=$?
if [ -n "$FRONTEND_PID" ]; then
  wait "$FRONTEND_PID" 2>/dev/null || true
fi
exit $status