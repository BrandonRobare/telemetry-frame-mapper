# macOS application bundle workflow

This is an arm64-only, unsigned local-build workflow. It creates a `.app` bundle for local validation; it does not sign, notarize, publish a release asset, or produce a universal2 binary.

## Build prerequisites

Build on an arm64 Mac with Python 3.11–3.12, [uv](https://docs.astral.sh/uv/), Node.js 20.19+, and the optional external tools described in [INSTALL.md](INSTALL.md). The application dependencies remain local: install ffmpeg and ExifTool for CLI geotagging, and COLMAP for reconstruction.

## Build and validate

From the repository root:

```bash
uv sync --frozen --group backend --group reconstruction --group desktop-package
(
  cd frontend
  npm ci
  npm run build
)
uv run --frozen --no-sync bash packaging/macos/build.sh
uv run --frozen --no-sync bash packaging/macos/smoke.sh
```

The build emits `dist/Telemetry Frame Mapper.app`. The smoke script launches the bundle with a fresh temporary `HOME`, waits for `http://127.0.0.1:8000/health`, verifies its writable data paths under `~/Library/Application Support/Telemetry Frame Mapper`, and confirms the generated SQLite database is at the current Alembic head. It removes the temporary data directory and stops the app on exit.

`build/` and `dist/` are local artifacts and are not committed. A real arm64 macOS execution remains a required gate for the macOS CI follow-up (#789); this workflow does not claim release readiness.
