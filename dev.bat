@echo off
REM dev.bat — start backend + frontend for local development
echo Starting backend...
start "Backend" cmd /k "cd backend && python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt && uvicorn main:app --reload --port 8000"
echo Starting frontend...
if exist frontend\ (
    start "Frontend" cmd /k "cd frontend && npm install && npm run dev"
    echo Open http://localhost:5173
) else (
    echo frontend/ not found -- skipping frontend dev server
    echo Backend running at http://localhost:8000
)
