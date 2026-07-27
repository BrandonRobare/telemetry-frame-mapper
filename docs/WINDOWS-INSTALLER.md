# Windows installer release workflow

The installer bundles the FastAPI backend, built React frontend, and default `config.yaml` into a Windows application directory. At first launch the app creates `%LOCALAPPDATA%\Telemetry Frame Mapper\` and copies the default config there. SQLite data, imports, processed files, exports, and logs stay in that writable per-user directory; uninstalling deliberately preserves them.

## Build prerequisites

Build on 64-bit Windows with:

- Python 3.11–3.12 and a clean virtual environment
- Node.js 20.19+ (to build `frontend/dist`)
- [PyInstaller](https://pyinstaller.org/) installed in that virtual environment
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`ISCC.exe`) on `PATH`

The app's optional external tools are not redistributed: install `ffmpeg` and ExifTool for CLI geotagging, and COLMAP for reconstruction, as described in [INSTALL.md](INSTALL.md). CUDA/torch/gsplat remains a manual, optional setup.

## Build and validate

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[backend]" pyinstaller
Push-Location frontend
npm ci
npm run build
Pop-Location
.\packaging\build-windows.ps1
ISCC.exe .\packaging\telemetry-frame-mapper.iss
```

The installer is written to `dist-installer\telemetry-frame-mapper-2.0.0-setup.exe`. Run it, launch **Telemetry Frame Mapper** from the Start menu, and open `http://127.0.0.1:8000`. Confirm `%LOCALAPPDATA%\Telemetry Frame Mapper\config.yaml` and its `data`, `imports`, `processed`, and `exports` directories exist, then check `http://127.0.0.1:8000/health` returns `{"status":"ok"}`.

The generated `build/`, `dist/`, and `dist-installer/` folders are release artifacts and are not committed.