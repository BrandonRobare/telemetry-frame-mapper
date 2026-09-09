# macOS application bundle workflow

This is an arm64-only, unsigned local-build workflow. It creates a `.app` bundle for local validation; it does not sign, notarize, publish a release asset, or produce a universal2 binary.

## Build prerequisites

Build on an arm64 Mac with Python 3.12–3.13, macOS 14 or newer, [uv](https://docs.astral.sh/uv/), Node.js 20.19+, and the optional external tools described in [INSTALL.md](INSTALL.md). The application dependencies remain local: install ffmpeg and ExifTool for CLI geotagging, and COLMAP for reconstruction.

## Build and validate

From the repository root:

```bash
uv sync --frozen --group backend --group reconstruction --group splat-metal --group desktop-package
(
  cd frontend
  npm ci
  npm run build
)
uv run --frozen --no-sync bash packaging/macos/build.sh
uv run --frozen --no-sync bash packaging/macos/smoke.sh
```

The build emits `dist/Telemetry Frame Mapper.app`. The smoke script launches the bundle with a fresh temporary `HOME`, waits for `http://127.0.0.1:8000/health`, verifies its writable data paths under `~/Library/Application Support/Telemetry Frame Mapper`, and confirms the generated SQLite database is at the current Alembic head. It removes the temporary data directory and stops the app on exit.

`splat-metal` pins `msplat==1.1.4` only for arm64 macOS and Python 3.12–3.13. Other platforms never install it. If that young, single-maintainer dependency becomes unavailable, omit the group: reconstruction continues with the supported `colmap_only` result instead of making the base application depend on it.

On a supported Mac the app selects msplat automatically; there is no backend setting. Metal progress is synchronized before it reaches the UI, and cancellation writes a partial PLY plus a native `.checkpoint.msplat` file so the job can terminate as cancelled without masquerading as `colmap_only` success.

`build/` and `dist/` are local artifacts and are not committed. The required arm64 macOS CI job installs msplat, runs a native training/cancellation smoke, bundles it into the application, and executes the packaged startup smoke.
