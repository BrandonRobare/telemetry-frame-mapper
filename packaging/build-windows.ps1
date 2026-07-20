# Build the Windows application bundle used by packaging/telemetry-frame-mapper.iss.
# Run from the repository root after building frontend/dist.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path "frontend/dist/index.html")) {
    throw "frontend/dist/index.html is missing. Run: cd frontend; npm ci; npm run build"
}

python -m PyInstaller --noconfirm --clean --onedir --name "Telemetry Frame Mapper" --specpath build `
    --runtime-hook packaging/runtime_hook.py `
    --add-data "config.yaml;." `
    --add-data "frontend/dist;frontend/dist" `
    --collect-all backend `
    --collect-all drone_video_geotagger `
    backend/__main__.py
