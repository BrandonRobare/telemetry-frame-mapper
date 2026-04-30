#!/bin/bash
# dev.sh — start backend + frontend for local development
set -e
echo "Starting backend..."
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"
cd ..

echo "Starting frontend..."
cd frontend
npm install
npm run dev &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"
cd ..

echo "Open http://localhost:5173"
echo "Press Ctrl+C to stop both servers"
wait $BACKEND_PID $FRONTEND_PID
