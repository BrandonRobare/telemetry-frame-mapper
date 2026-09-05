# Windows installer release workflow

The installer bundles one FastAPI API process, the built React frontend, default `config.yaml`, and the Alembic migration assets into a Windows application directory. At first launch the app creates `%LOCALAPPDATA%\Telemetry Frame Mapper\` and copies the default config there. SQLite data, imports, processed files, exports, and logs stay in that writable per-user directory; uninstalling deliberately preserves them.

## Build prerequisites

Build on 64-bit Windows with:

- Python 3.11–3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 20.19+ (to build `frontend/dist`)
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`ISCC.exe`) on `PATH`

The app's optional external tools are not redistributed: install `ffmpeg` and ExifTool for CLI geotagging, and COLMAP for reconstruction, as described in [INSTALL.md](INSTALL.md). CUDA/torch/gsplat remains a manual, optional setup.

## Build and validate

From the repository root in PowerShell:

```powershell
uv sync --frozen --group backend --group reconstruction --group desktop-package
Push-Location frontend
npm ci
npm run build
Pop-Location
uv run --frozen --no-sync powershell -ExecutionPolicy Bypass -File packaging/windows/build.ps1
uv run --frozen --no-sync powershell -ExecutionPolicy Bypass -File packaging/windows/smoke.ps1
ISCC.exe .\packaging\windows\telemetry-frame-mapper.iss
```

The smoke script starts the unpacked application against a fresh temporary `LOCALAPPDATA`, waits for `http://127.0.0.1:8000/health`, and verifies the SQLite database reached the current Alembic head. The installer is then written to `dist-installer\telemetry-frame-mapper-2.0.0-setup.exe`. Run it, launch **Telemetry Frame Mapper** from the Start menu, and confirm its persisted config and data directories exist under `%LOCALAPPDATA%\Telemetry Frame Mapper\`.

The generated `build/`, `dist/`, and `dist-installer/` folders are release artifacts and are not committed.