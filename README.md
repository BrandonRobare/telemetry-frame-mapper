# Drone Video Geotagger

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
frontend/         Vite + React frontend (11-tab workflow UI)
tests/            pytest suite (tests/cli/ and tests/backend/)
dashboard/        Dev-time status dashboard (stdlib only, http://localhost:7000)
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
- Exports: WebODM package, GeoJSON, LAS 1.4 point cloud, optional SuGaR mesh, flythrough video.
- SQLite database via SQLAlchemy (swappable for PostgreSQL via `DATABASE_URL`).

### Frontend (11 tabs, all functional)
- **Map** — Leaflet + ESRI satellite, footprint polygons, coverage overlay, session stats sidebar.
- **GPS Sync** — DJI FlightRecord CSV matching with timing deltas.
- **Review** — thumbnail grid, quality flags, COLMAP reprojection-error badges, reconstruction frame selection.
- **Plan** — target-area drawing, lawnmower plan generation, KML/GPX export.
- **Export** — WebODM zip, GeoJSON, LAS point cloud, mesh GLB/OBJ/MTL.
- **Session Log · Reconstruct · Jobs · Storage** — event history, preset-based job start, resource monitor with live logs, disk usage + file browser.
- **Splat Viewer** — in-browser gaussian-splat rendering, PSNR/SSIM sparklines, coverage-gap heatmap, GPS-pinned annotations, distance/area measurement, ortho/3D split view, flythrough recording.
- **Compare** — voxel change detection between two reconstructions of the same site.
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

### Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

Requires Node 18+.

## Usage

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

Writes geotagged copies to `extracted_geotagged/` by default.

If you already have the SRT telemetry file:

```bash
drone-video-geotagger \
  --video flight.mp4 \
  --frames extracted \
  --srt flight.srt \
  --takeoff-altitude 236.94 \
  --frame-rate 8
```

### Backend

```bash
uvicorn backend.main:app --reload
# API at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

Optional: copy `config.yaml.example` to `config.yaml` and adjust mission parameters (altitude, FOV, overlap, target CRS).

### Dev dashboard

```bash
python dashboard/server.py
# http://localhost:7000 — live task progress + Architecture Reference tab
```

## CLI inputs

| Flag | Description |
|---|---|
| `--video` | Source DJI video (MP4) |
| `--frames` | Folder of extracted JPG frames |
| `--takeoff-altitude` | Takeoff altitude in metres above sea level |
| `--srt` | Optional DJI SRT file (extracted from video if omitted) |
| `--frame-rate` | Optional frame extraction rate (estimated from SRT if omitted) |

## CLI outputs

- Geotagged JPG files in `<frames>_geotagged/`
- `frame_geotags.csv` — frame index, time offset, lat/lon, relative and GPS altitude, timestamp
- `exiftool_geotags.args` — generated ExifTool argument file

Upload the geotagged folder to WebODM; it reads GPS EXIF tags on import.

## Tests

```bash
pytest        # 204 tests (CLI + backend)
ruff check .  # linter
cd frontend && npm test -- --run   # frontend unit tests (vitest)
```

Tests use inline fixture data and temporary paths — no real flight files required. CI mocks all external binaries; see [V1_EXTERNAL_TOOL_RELEASE_GATES.md](V1_EXTERNAL_TOOL_RELEASE_GATES.md).

## Documentation

| Doc | What it covers |
|---|---|
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | End-to-end tutorial: DJI video → geotag → import → reconstruct → splat → export |
| [docs/INSTALL.md](docs/INSTALL.md) | System requirements and per-platform setup (ffmpeg, exiftool, COLMAP) |
| [docs/SETUP.md](docs/SETUP.md) | GPU / CUDA / gsplat training setup |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Exact error messages → causes → fixes |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Component map, reconstruction state machine, design rules |
| [docs/release-audit-v1.md](docs/release-audit-v1.md) | The 2026-06-11 v1.0 release audit |
| [V1_RELEASE_CHECKLIST.md](V1_RELEASE_CHECKLIST.md) | Remaining work to tag 1.0, as self-contained agent tasks |
| [CHANGELOG.md](CHANGELOG.md) | Release notes |

The backend API is self-documenting at `http://localhost:8000/docs` while running.

## Privacy

Do not commit real drone videos, FlightRecord files, extracted frames, SRT files, or geotagged images. The `.gitignore` blocks those by default. Run `git status --short` before pushing.
