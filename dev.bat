@echo off
REM dev.bat — start backend + frontend for local development (run from the repo root)
cd /d "%~dp0"

echo Starting backend...
REM Reload mode uses one API worker; python -m backend validates the bind before serving.
REM Run from the repo root: config.yaml (deployment host/port, default 127.0.0.1:8000) and the
REM .\processed static mount resolve from here
start "Backend" cmd /k "set BACKEND_RELOAD=1&& uv sync --group backend --group dev && uv run --no-sync python -m backend"

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
