# Drone Video Geotagger

Geotags DJI drone video frames with GPS EXIF metadata for WebODM/OpenDroneMap processing.

DJI videos can store GPS telemetry in an embedded subtitle track. Extracted still frames do not always keep that location data. This tool reads the DJI telemetry, lines it up with the extracted frame sequence, and writes GPS EXIF tags into the JPG files.

This repository is a monorepo containing two components:

- **CLI** (`src/drone_video_geotagger/`) — standalone command-line geotagging tool
- **Backend** (`backend/`) — FastAPI REST API for image import, quality analysis, coverage tracking, and mission planning

## Repository layout

```
backend/          FastAPI app (API server, DB models, services)
src/              CLI package (drone-video-geotagger command)
tests/            pytest suite covering both components
dashboard/        Dev-time status dashboard (stdlib only)
docs/             Architecture and planning docs
data/             SQLite database (gitignored)
imports/          Drop folder for raw images and flight logs (gitignored)
processed/        Thumbnails and processed outputs (gitignored)
exports/          KML/GPX mission plan exports (gitignored)
```

## Features

- Extracts DJI SRT telemetry from an MP4 with `ffmpeg`, or reads an existing `.srt` file.
- Interpolates latitude, longitude, and relative height for each extracted frame.
- Writes GPS EXIF tags with `exiftool`.
- Creates an audit CSV so you can inspect the frame timing and coordinates.
- Keeps raw videos, flight logs, and generated image folders out of git.
- REST API for image import, quality scoring, ground footprint computation, coverage analysis, and mission planning (Phase 2).

## Install

### CLI only

```bash
python -m pip install .
```

For development (adds pytest and ruff):

```bash
python -m pip install ".[dev]"
```

The CLI expects `ffmpeg` and `exiftool` on your PATH. You can also pass their paths with `--ffmpeg` and `--exiftool`.

### Backend

```bash
pip install -r backend/requirements.txt
```

The backend requires no external binaries. It creates a SQLite database at `data/drone_mapping.db` on first run (path overridable via `DATABASE_URL` env var).

To start the API server:

```bash
uvicorn backend.main:app --reload
```

The API is then available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

Optional: copy `config.yaml.example` to `config.yaml` and adjust mission parameters (altitude, FOV, overlap percentages, target CRS) before starting the server.

## Usage

Extract frames from the video first:

```bash
ffmpeg -i flight.mp4 -vf fps=8 extracted/frame_%05d.jpg
```

Then geotag the extracted JPGs:

```bash
drone-video-geotagger \
  --video flight.mp4 \
  --frames extracted \
  --takeoff-altitude 236.94
```

The command writes geotagged copies to `extracted_geotagged/` by default.

If you already have the SRT telemetry:

```bash
drone-video-geotagger \
  --video flight.mp4 \
  --frames extracted \
  --srt flight.srt \
  --takeoff-altitude 236.94 \
  --frame-rate 8
```

## Inputs

- `--video`: Source DJI video.
- `--frames`: Folder of extracted JPG frames.
- `--takeoff-altitude`: Takeoff altitude in meters above sea level.
- `--srt`: Optional DJI SRT file. If you skip it, the CLI extracts the subtitle track from the video.
- `--frame-rate`: Optional frame extraction rate. If you skip it, the CLI estimates the rate from the frame count and SRT duration.

## Outputs

- Geotagged JPG files.
- `frame_geotags.csv` with frame index, time offset, latitude, longitude, relative height, GPS altitude, and timestamp.
- `exiftool_geotags.args`, the generated ExifTool argument file.

Upload the geotagged JPG folder to WebODM. WebODM reads the EXIF GPS tags during import.

## Privacy Notes

Do not commit real drone videos, FlightRecord files, extracted frames, SRT files, credentials, or generated geotagged images. The `.gitignore` blocks those files by default. Run `git status --short` before pushing.

## Tests

```bash
pytest
ruff check .
```

The tests use inline strings and temporary paths. They do not include real flight data.
