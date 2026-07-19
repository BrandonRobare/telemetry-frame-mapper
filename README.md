# Drone Video Geotagger

[![CI](https://github.com/BrandonRobare/telemetry-frame-mapper/actions/workflows/ci.yml/badge.svg)](https://github.com/BrandonRobare/telemetry-frame-mapper/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Latest release](https://img.shields.io/github/v/release/BrandonRobare/telemetry-frame-mapper)](https://github.com/BrandonRobare/telemetry-frame-mapper/releases/latest)

A full pipeline from DJI drone video to a GPS-registered 3D gaussian splat: geotag extracted frames from the embedded telemetry, review coverage on a map, run COLMAP + gaussian-splat reconstruction, and explore/export the result — plus WebODM/OpenDroneMap-ready output at every step.

DJI videos can store GPS telemetry in an embedded subtitle track. Extracted still frames do not keep that location data. The CLI reads the DJI telemetry, lines it up with the extracted frame sequence, and writes GPS EXIF tags into the JPG files; the web app takes it from there:

```
DJI video ──ffmpeg──> frames ──CLI──> geotagged JPGs ──import──> map/review/plan
                                                                      │
                                              COLMAP SfM ──> gsplat training ──> splat viewer,
                                                                                 LAS/mesh/GeoJSON export
```

New here? Follow the [end-to-end workflow tutorial](docs/WORKFLOW.md).

This repository is a monorepo with three components:

- **CLI** (`src/drone_video_geotagger/`) — standalone command-line geotagging tool
- **Backend** (`backend/`) — FastAPI REST API for image import, quality analysis, coverage tracking, and mission planning
- **Frontend** (`frontend/`) — React web app with an interactive map for visualising footprints, coverage, and session stats

## Repository layout

```
src/              CLI package (drone-video-geotagger command)
backend/          FastAPI app (API server, DB models, services)
frontend/         Vite + React frontend (13-tab workflow UI)
tests/            pytest suite (tests/cli/ and tests/backend/)
data/             SQLite database (gitignored)
imports/          Drop folder for raw images and flight logs (gitignored)
processed/        Thumbnails and processed outputs (gitignored)
exports/          KML/GPX mission plan exports (gitignored)
```

## Features

### CLI
- Extracts DJI SRT telemetry from an MP4 with `ffmpeg`, or reads an existing `.srt` file.
- Interpolates latitude, longitude, and relative height for each extracted frame.
- Writes GPS EXIF tags with `exiftool`.
- Creates an audit CSV for inspecting frame timing and coordinates.

### Backend
- REST API for image import, quality scoring (sharpness + brightness via OpenCV), and ground footprint computation from DJI XMP altitude/yaw (Shapely/UTM).
- Coverage analysis, lawnmower mission planning with KML/GPX export, and flight-log sync.
- Reconstruction job pipeline: COLMAP SfM (quick/full presets, target-area crop, frame selection), GPS geo-registration, gaussian-splat training, LOD generation, and per-frame reprojection-error reporting.
- Exports: WebODM georeferencing CSV-only zip, GeoJSON, LAS 1.4 point cloud, optional SuGaR mesh, flythrough video.
- SQLite database via SQLAlchemy (swappable for PostgreSQL via `DATABASE_URL`) with Alembic-managed schema migrations.

### Frontend (13 tabs, all functional)
- **Overview** — pipeline status, session summary, import call-to-action, and reconstruction readiness.
- **Map** — Leaflet + ESRI satellite, footprint polygons, coverage overlay, session stats sidebar.
- **GPS Sync** — DJI FlightRecord CSV matching with timing deltas.
- **Review** — thumbnail grid, quality flags, COLMAP reprojection-error badges, reconstruction frame selection.
- **Plan** — target-area drawing, lawnmower plan generation, KML/GPX export.
- **Export** — WebODM georeferencing CSV-only zip, GeoJSON, LAS point cloud, mesh GLB/OBJ/MTL.
- **Session Log · Reconstruct · Jobs · Storage** — event history, preset-based job start, resource monitor with live logs, disk usage + file browser.
- **Splat Viewer** — in-browser gaussian-splat rendering, PSNR/SSIM sparklines, coverage-gap heatmap, GPS-pinned annotations, distance/area measurement, ortho/3D split view, flythrough recording, presentation/narration mode.
- **Compare** — voxel change detection plus a project-scoped, read-only flight trend table. It
  reuses stored usable-frame, coverage, and completed-reconstruction metrics; missing values stay
  blank rather than triggering new analysis.
- **Settings** — app preferences, import/storage paths, mission parameters, reconstruction presets, rendering/export defaults.
- Dark/light theme with persistence.

## Install

All Python dependencies are managed through `pyproject.toml` optional extras:

```bash
# Everything (CLI + backend + dev tools)
pip install -e ".[backend,dev]"

# CLI + tests only (no backend dependencies)
pip install -e ".[dev]"
```

The CLI requires `ffmpeg` and `exiftool` on your PATH (or pass `--ffmpeg` / `--exiftool`).

### Backend logs

The backend writes local JSON Lines logs by default to `logs/backend.jsonl`. Configure the
`logging` block in `config.yaml` to change its level, directory, file name, rotation size, or
retention count; set `enabled: false` to disable it. The log path is resolved relative to the
configuration file, and rotation is handled locally by Python's standard library.

### External tool gates

Required for v1.0 release smoke:

| Tool | Required for | Gate |
|---|---|---|
| `ffmpeg` | CLI SRT extraction from DJI MP4 files | Must be on `PATH` or passed with `--ffmpeg`; missing binaries fail with install guidance. |
| `exiftool` | CLI GPS EXIF writes | Must be on `PATH` or passed with `--exiftool`; missing binaries fail with install guidance. |

Optional/manual reconstruction gates:

| Tool/dependency | Required for | Expected failure mode when absent |
|---|---|---|
| `colmap` | Reconstruct tab SfM workspace pipeline | Reconstruction job fails with `COLMAP executable not found` install guidance. |
| `torch` + `gsplat` + CUDA-capable GPU | Gaussian splat training, thumbnails, optional server video renderer | Manual two-step install (see [docs/SETUP.md](docs/SETUP.md)) — intentionally not in the `[reconstruction]` extra; without it training is skipped and the job completes COLMAP-only; thumbnail generation degrades silently; server video rendering tells users to use browser recording or install optional reconstruction dependencies. |
| SuGaR (`sugar_scene`/`sugar`) | Mesh export | Not installed by the Python extra; install from the upstream SuGaR project when mesh export is needed. Mesh export job fails with `SuGaR is not installed` optional dependency guidance. |

CI should use fakes/mocks for these tools. Real `ffmpeg`/`exiftool` CLI smoke is must-pass for v1.0; real COLMAP/gsplat/SuGaR/video-render smoke is optional/manual unless the release explicitly advertises reconstruction as production-ready.

The backend creates a SQLite database at `data/drone_mapping.db` on first run.

### Docker single-container app

Build and run a CPU-only image that serves the FastAPI backend and built frontend from one container:

```bash
docker build -t telemetry-frame-mapper .
docker run --rm -p 8000:8000 \
  -v "$PWD/data:/app/data" \
  -v "$PWD/imports:/app/imports" \
  -v "$PWD/processed:/app/processed" \
  -v "$PWD/exports:/app/exports" \
  telemetry-frame-mapper
```

Open `http://localhost:8000`. The image installs `ffmpeg`, `exiftool`, and COLMAP for CPU-only reconstruction. CUDA/torch/gsplat GPU training is intentionally out of scope for this image; use the manual GPU setup in `docs/SETUP.md` when needed. CI runs a Docker build smoke test so the image stays buildable; runtime GPU reconstruction remains a manual/local support tier.

### Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

Requires Node 18+.

## Usage

### Quick launch (web app)

Once installed, start the backend + frontend and open the browser with one command:

```bash
./run.sh      # macOS / Linux
run.bat       # Windows (enters the VS build environment so GPU training works)
```

`run.bat`/`run.sh` are for everyday use; `dev.bat`/`dev.sh` do the same but also create the venv and install dependencies on first run.

### CLI — geotag frames

Extract frames from the video first:

```bash
ffmpeg -i flight.mp4 -vf fps=8 extracted/frame_%05d.jpg
```

Then geotag:

```bash
drone-video-geotagger \
  --video flight.mp4 \
  --frames extracted \
  --takeoff-altitude 236.94
```

Writes geotagged copies to `extracted_geotagged/` by default. Add `--in-place` to write EXIF tags directly into the source frame folder instead of creating copies.

If you already have the SRT telemetry file:

```bash
drone-video-geotagger \
  --video flight.mp4 \
  --frames extracted \
  --srt flight.srt \
  --takeoff-altitude 236.94 \
  --frame-rate 8
```


### Browser upload import

The Import dialog defaults to **Browser upload**: choose or drag a folder of frames in the browser, and the app streams files to the backend in chunks before starting the same import pipeline used by server-side paths. This is the easiest path when the image folder is on your workstation but not already under `imports/`. The legacy **Server path** mode remains available for folders that already live under the backend's `imports/` directory.

### SD-card / watch-folder auto-import

Set `auto_import.enabled` and explicitly list each mounted card or staging folder in `config.yaml`, then restart the backend. The watcher uses polling, waits until a media directory is unchanged for `stable_seconds`, and starts the existing image-import pipeline. It never discovers drives or imports paths outside `roots`; `GET /auto-import/status` reports missing, unsupported, and watched roots. A persisted media-manifest fingerprint prevents a completed claim from being imported again after a restart.

```yaml
auto_import:
  enabled: true
  roots:
    - "E:/DCIM"
  poll_interval_seconds: 10
  stable_seconds: 30
```

The watcher imports directories containing configured image extensions (JPEG by default). It does not copy card contents, watch video-only folders, or retry a folder once its fingerprint has been claimed; move/copy edited media to a new folder if a new import is intended.

### Backend

```bash
uvicorn backend.main:app --reload
# API at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

Optional: copy `config.yaml.example` to `config.yaml` and adjust mission parameters (altitude, FOV, overlap, target CRS). Upload limits are configurable in `config.yaml` under `upload_limits` (`flight_log_max_bytes` and `srt_max_bytes`, both 10 MiB by default).

### Reconstruction share links

The Export tab creates a revocable, opaque link for a completed reconstruction. New links default
to seven days and may be protected with an optional password. The bearer token is shown only in the
creation response and lives only in the viewer URL; it is never stored as plaintext or appended to
artifact URLs. Password verification issues a `HttpOnly`, `SameSite=Lax`, `/share`-scoped session
cookie (marked `Secure` for HTTPS or a TLS proxy). Owners can inspect lifecycle state with
`GET /export/reconstructions/{id}/share-links` and revoke one with
`POST /export/reconstructions/{id}/share-links/{share_link_id}/revoke`.

Public responses use `401` when password unlock is required, `403` for an incorrect password or
token/reconstruction mismatch, and `410` after expiry or revocation. Existing signed links remain
supported until their signed expiry; their legacy artifact query-token format is not emitted for new
links.

### Artifact backup

`POST /storage/backup` creates an additive, versioned snapshot of the live SQLite database,
sanitized `config.yaml`, and the selected `imports`, `processed`, and/or `exports` directories.
Every copied file is SHA-256 recorded in `manifest.json`; the SQLite file is created with SQLite's
backup API, so WAL/SHM sidecars are not copied. Configure the allowed destination first:

```yaml
backup:
  local_destinations:
    - "E:/telemetry-backups"
  rclone_remote: "archive:telemetry-backups"  # credentials stay in rclone config
```

Then submit either `{ "destination": "local", "local_destination": "E:/telemetry-backups" }`
or `{ "destination": "rclone" }`, with an optional `artifacts` list (defaults to
`["processed", "exports"]`). Local paths must exactly match the allowlist. Remote backups use
`rclone copy`, never `sync` or deletion flags; rclone credentials and command output are never
persisted in the snapshot or returned by the API.

To schedule one opt-in daily backup, define a named target from the same allowlist and select it
by name. `daily_at` uses the server's local clock. `GET /storage/backup-schedule` returns only
operational status (last run, next run, and success/failure result), never target credentials or
command output.

```yaml
backup:
  local_destinations:
    - "E:/telemetry-backups"
  targets:
    nightly_local:
      destination: local
      local_destination: "E:/telemetry-backups"
      artifacts: ["processed", "exports"]
  schedule:
    enabled: true
    target: nightly_local
    daily_at: "02:00"
```

The scheduler runs only one backup at a time, so a slow remote copy is not overlapped by the next
scheduled run. Leave `enabled: false` (the default) to keep it off.

## CLI inputs

| Flag | Description |
|---|---|
| `--video` | Source DJI video (MP4) |
| `--frames` | Folder of extracted JPG frames |
| `--takeoff-altitude` | Takeoff altitude in metres above sea level |
| `--srt` | Optional DJI SRT file (extracted from video if omitted) |
| `--frame-rate` | Optional frame extraction rate (estimated from SRT if omitted) |
| `--in-place` | Write EXIF tags into the original frame folder instead of `<frames>_geotagged/` copies |

Frame index rule: the index is the **last** number in each filename — `frame_00042.jpg` and `DJI_0081_frame_42.jpg` both index as frame 42. Files with no digits in the name are skipped.

## CLI outputs

- Geotagged JPG files in `<frames>_geotagged/`
- `frame_geotags.csv` — frame index, time offset, lat/lon, relative and GPS altitude, timestamp
- `exiftool_geotags.args` — generated ExifTool argument file

Upload the geotagged folder to WebODM; it reads GPS EXIF tags on import.

For an opt-in API upload, polling, cancellation, and result-download workflow, see
[WebODM round trip](docs/WEBODM.md). Credentials stay in an environment variable.

## Tests

```bash
pytest        # 355 tests (CLI + backend)
ruff check .  # linter
cd frontend && npm test -- --run   # 83 frontend unit tests (vitest)
```

Tests use inline fixture data and temporary paths — no real flight files required. CI mocks all external binaries (no real ffmpeg, exiftool, COLMAP, or GPU).

## Documentation

| Doc | What it covers |
|---|---|
| [docs/USER-MANUAL.md](docs/USER-MANUAL.md) | Full reference: capabilities, both data pipelines, and the gaussian-splat trainer |
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | End-to-end tutorial: DJI video → geotag → import → reconstruct → splat → export |
| [docs/INSTALL.md](docs/INSTALL.md) | System requirements and per-platform setup (ffmpeg, exiftool, COLMAP) |
| [docs/SETUP.md](docs/SETUP.md) | GPU / CUDA / gsplat training setup |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Exact error messages → causes → fixes |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Component map, reconstruction state machine, design rules |
| [CHANGELOG.md](CHANGELOG.md) | Release notes |

The backend API is self-documenting at `http://localhost:8000/docs` while running.

## Privacy

Do not commit real drone videos, FlightRecord files, extracted frames, SRT files, or geotagged images. The `.gitignore` blocks those by default. Run `git status --short` before pushing.
