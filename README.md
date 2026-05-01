# Drone Video Geotagger

Geotags DJI drone video frames with GPS EXIF metadata for WebODM/OpenDroneMap processing, with a web UI for visualising coverage and planning missions.

DJI videos can store GPS telemetry in an embedded subtitle track. Extracted still frames do not always keep that location data. This tool reads the DJI telemetry, lines it up with the extracted frame sequence, and writes GPS EXIF tags into the JPG files.

This repository is a monorepo with three components:

- **CLI** (`src/drone_video_geotagger/`) — standalone command-line geotagging tool
- **Backend** (`backend/`) — FastAPI REST API for image import, quality analysis, coverage tracking, and mission planning
- **Frontend** (`frontend/`) — React web app with an interactive map for visualising footprints, coverage, and session stats

## Repository layout

```
src/              CLI package (drone-video-geotagger command)
backend/          FastAPI app (API server, DB models, services)
frontend/         Vite + React frontend (Map tab + 4 placeholder tabs)
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
- REST API for image import, quality scoring (sharpness + brightness via OpenCV), and ground footprint computation (Shapely/UTM).
- SQLite database via SQLAlchemy (swappable for PostgreSQL via `DATABASE_URL`).
- Coverage analysis and mission planning services (in progress).

### Frontend (Map tab — live)
- Interactive Leaflet map with ESRI satellite basemap.
- Footprint polygons (blue) and coverage overlay (green) toggled per-layer.
- Session sidebar: stats grid, coverage %, quality flags, Run Coverage Analysis button.
- Dark/light theme with persistence.
- GPS Sync, Review, Plan, and Export tabs scaffolded (coming soon).

## Install

All Python dependencies are managed through `pyproject.toml` optional extras:

```bash
# Everything (CLI + backend + dev tools)
pip install -e ".[backend,dev]"

# CLI + tests only (no backend dependencies)
pip install -e ".[dev]"
```

The CLI requires `ffmpeg` and `exiftool` on your PATH (or pass `--ffmpeg` / `--exiftool`).

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
pytest        # 31 tests (CLI + backend)
ruff check .  # linter
```

Tests use inline fixture data and temporary paths — no real flight files required.

## Privacy

Do not commit real drone videos, FlightRecord files, extracted frames, SRT files, or geotagged images. The `.gitignore` blocks those by default. Run `git status --short` before pushing.
