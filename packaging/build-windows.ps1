# Build the Windows application bundle used by packaging/telemetry-frame-mapper.iss.
# Run from the repository root after building frontend/dist.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path "frontend/dist/index.html")) {
    throw "frontend/dist/index.html is missing. Run: cd frontend; npm ci; npm run build"
}

$repoRoot = (Get-Location).Path
python -m PyInstaller --noconfirm --clean --onedir --name "Telemetry Frame Mapper" --specpath build `
    --runtime-hook "$repoRoot/packaging/runtime_hook.py" `
    --add-data "$repoRoot/config.yaml;." `
    --add-data "$repoRoot/alembic.ini;." `
    --add-data "$repoRoot/backend/db/migrations;backend/db/migrations" `
    --add-data "$repoRoot/frontend/dist;frontend/dist" `
    --collect-all backend `
    --collect-all drone_video_geotagger `
    backend/__main__.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}
