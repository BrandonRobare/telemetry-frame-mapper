@echo off
REM dev.bat — start backend + frontend for local development (run from the repo root)
cd /d "%~dp0"

echo Starting backend...
REM Reload mode uses one API worker.
REM Run uvicorn from the repo root: config.yaml and the .\processed static mount resolve from here
start "Backend" cmd /k "uv sync --group backend --group dev && uv run --no-sync uvicorn backend.main:app --reload --port 8000"

where node >nul 2>nul
if errorlevel 1 (
    echo node/npm not found -- install Node 18+ from https://nodejs.org to run the frontend.
    echo Backend starting at http://localhost:8000
    goto :eof
)

if exist frontend\ (
    echo Starting frontend...
    start "Frontend" cmd /k "cd frontend && npm install && npm run dev"
    echo Open http://localhost:5173
) else (
    echo frontend/ not found -- skipping frontend dev server
    echo Backend starting at http://localhost:8000
)
