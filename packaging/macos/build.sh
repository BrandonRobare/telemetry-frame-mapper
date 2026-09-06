#!/usr/bin/env bash
# Build the arm64 macOS application bundle. Run from the repository root after building frontend/dist.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

if [[ "$(uname -m)" != "arm64" ]]; then
    printf '%s\n' "macOS bundle builds are arm64-only; run this script on an arm64 Mac." >&2
    exit 1
fi

if [[ ! -f "frontend/dist/index.html" ]]; then
    printf '%s\n' "frontend/dist/index.html is missing. Run: cd frontend; npm ci; npm run build" >&2
    exit 1
fi

uv run --frozen --no-sync python -m PyInstaller --noconfirm --clean --onedir --windowed --name "Telemetry Frame Mapper" --specpath build \
    --runtime-hook "$repo_root/packaging/common/runtime_paths.py" \
    --add-data "$repo_root/config.yaml:." \
    --add-data "$repo_root/alembic.ini:." \
    --add-data "$repo_root/backend/db/migrations:backend/db/migrations" \
    --add-data "$repo_root/frontend/dist:frontend/dist" \
    --collect-all backend \
    --collect-all drone_video_geotagger \
    backend/__main__.py
