@echo off
REM run.bat — start the app for everyday use (backend + frontend, then open the browser).
REM
REM This is the "just run it" launcher. It assumes dependencies are already
REM installed; to set the project up first, run dev.bat once.
cd /d "%~dp0"

REM --- Activate a virtualenv (prefer .venv, fall back to .venv-windows) ---
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else if exist ".venv-windows\Scripts\activate.bat" (
    call ".venv-windows\Scripts\activate.bat"
) else (
    echo No virtualenv found. Run dev.bat once, or:
    echo     python -m venv .venv ^&^& .venv\Scripts\activate ^&^& pip install -e ".[backend]"
    exit /b 1
)

REM --- Optional GPU training: gsplat's cached CUDA extension only loads when
REM     cl.exe is on PATH (torch re-checks the compiler on every load). If the
REM     Visual Studio C++ build tools are present, enter the x64 dev environment.
REM     Without them the app still runs; reconstructions complete colmap_only.
set "_VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
set "_VSPATH="
if exist "%_VSWHERE%" (
    for /f "usebackq delims=" %%i in (`"%_VSWHERE%" -latest -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "_VSPATH=%%i"
)
if defined _VSPATH if exist "%_VSPATH%\VC\Auxiliary\Build\vcvars64.bat" (
    call "%_VSPATH%\VC\Auxiliary\Build\vcvars64.bat" >nul
    echo GPU build environment ready (cl.exe on PATH).
) else (
    echo Visual Studio C++ tools not found - splat training will be skipped (colmap_only). See docs\SETUP.md.
)

echo Starting backend on http://localhost:8000 ...
start "Backend" cmd /k "uvicorn backend.main:app --port 8000"

where npm >nul 2>nul
if not errorlevel 1 if exist "frontend\" (
    echo Starting frontend on http://localhost:5173 ...
    start "Frontend" cmd /k "cd frontend && npm run dev"
    timeout /t 3 >nul
    start "" "http://localhost:5173"
) else if exist "frontend\dist\" (
    echo Node/npm not found, but frontend\dist is built - serving it from the backend on http://localhost:8000.
    timeout /t 2 >nul
    start "" "http://localhost:8000"
) else (
    echo Node/npm or frontend not found - backend only. Opening API docs.
    timeout /t 2 >nul
    start "" "http://localhost:8000/docs"
)
