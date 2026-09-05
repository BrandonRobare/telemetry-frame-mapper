# Telemetry Frame Mapper

[![CI](https://github.com/BrandonRobare/telemetry-frame-mapper/actions/workflows/ci.yml/badge.svg)](https://github.com/BrandonRobare/telemetry-frame-mapper/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Latest release](https://img.shields.io/github/v/release/BrandonRobare/telemetry-frame-mapper)](https://github.com/BrandonRobare/telemetry-frame-mapper/releases/latest)

DJI drones record GPS telemetry into a subtitle track inside the video file. Pull still frames out
of that video and the location data does not come with them, which leaves photogrammetry software
with nothing to work from.

This project takes the telemetry back out, matches it to the extracted frames, and writes real GPS
EXIF tags. From there a web app carries the same footage through coverage review, COLMAP
reconstruction, gaussian-splat training, and export.

```
DJI video ──ffmpeg──> frames ──CLI──> geotagged JPGs ──import──> map/review/plan
                                                                      │
                                              COLMAP SfM ──> gsplat training ──> splat viewer,
                                                                                 LAS/mesh/GeoJSON export
```

Every stage also produces WebODM/OpenDroneMap-ready output, so you can stop at any point and take
the frames elsewhere.

New here? Start with the [end-to-end workflow tutorial](docs/WORKFLOW.md).

## Quickstart

The published Python wheel is CLI-only:

```bash
pip install drone-video-geotagger
```

For the web app, use a cloned source checkout, the [Docker image](#docker), the
[Windows installer](docs/WINDOWS-INSTALLER.md), or an arm64 unsigned local [macOS bundle](docs/MACOS-BUNDLE.md).
From a source checkout, install its source-only dependencies with:

```bash
uv sync --group backend --group dev
```

`backend` and `dev` are PEP 735 dependency groups for a source checkout, not pip-installable wheel
extras.

`ffmpeg` and `exiftool` must be on your `PATH` (or passed with `--ffmpeg` / `--exiftool`). COLMAP
and a CUDA GPU are needed only for reconstruction. Full setup, including per-platform binaries and
GPU training, is in [docs/INSTALL.md](docs/INSTALL.md).

Extract frames, then geotag them:

```bash
ffmpeg -i flight.mp4 -vf fps=8 extracted/frame_%05d.jpg
drone-video-geotagger --video flight.mp4 --frames extracted --takeoff-altitude 236.94
```

That writes geotagged copies to `extracted_geotagged/`, ready to upload to WebODM.

To use the web app instead:

```bash
./run.sh      # macOS / Linux
run.bat       # Windows
```

Then open `http://localhost:5173`. (`dev.sh` / `dev.bat` do the same, but also create the virtualenv
and install source-only dependencies on first run.)

## The CLI

`drone-video-geotagger` reads the telemetry, interpolates a position for each frame, and writes the
EXIF tags.

| Flag | Description |
|---|---|
| `--video` | Source DJI video (MP4). Required. |
| `--frames` | Folder of extracted JPG frames. Required. |
| `--takeoff-altitude` | Takeoff altitude in metres above sea level. Required. |
| `--output` | Folder for the geotagged copies. Defaults to `<frames>_geotagged`. |
| `--srt` | Existing DJI SRT file. Extracted from the video when omitted. |
| `--frame-rate` | Frame extraction rate. Estimated from the SRT when omitted. |
| `--ffmpeg` | Path to the ffmpeg binary, if it is not on `PATH`. |
| `--exiftool` | Path to the exiftool binary, if it is not on `PATH`. |
| `--in-place` | Write tags into the source folder instead of making copies. |

Frame numbering uses the **last** number in each filename, so `frame_00042.jpg` and
`DJI_0081_frame_42.jpg` both resolve to frame 42. Files with no digits are skipped.

Alongside the geotagged images it writes `frame_geotags.csv` — per-frame index, time offset,
coordinates, altitudes, timestamp — for checking the alignment, plus `exiftool_geotags.args`, the
generated ExifTool argument file.

### Batch jobs

`dvg-pipeline` runs a geotag → GPS validation → coverage sequence from a YAML job spec, with no web
UI involved. Reconstruction and export need COLMAP/gsplat and a database, so the CLI fails those
steps with exit code 1 rather than reporting work it did not do — start them from the app:

```bash
dvg-pipeline job.yml --dry-run   # print the step plan, change nothing
dvg-pipeline job.yml
```

`--output-root` and `--log-dir` override the matching spec keys, and `-v` turns on debug logging.
[docs/examples/pipeline-job-spec.yml](docs/examples/pipeline-job-spec.yml) is an annotated spec.

## The web app

The backend is a FastAPI service — 28 routers, self-documenting at `/docs` while running — covering
import, quality scoring, footprint geometry, coverage analysis, mission planning, the reconstruction
job pipeline, and the export formats. The frontend is a React app whose tabs follow the flight
itself: import and review frames, check coverage on a map, plan the next flight, run a
reconstruction, then explore the resulting splat and export it.

[docs/USER-MANUAL.md](docs/USER-MANUAL.md) is the full reference for both.

## Repository layout

```
src/              CLI package (drone-video-geotagger, dvg-pipeline)
backend/          FastAPI app (API server, DB models, services)
frontend/         Vite + React frontend
tests/            pytest suite (tests/cli/ and tests/backend/)
packaging/        Windows installer and arm64 macOS bundle build scripts
docs/             Documentation
```

`data/`, `imports/`, `processed/`, and `exports/` are created at runtime and gitignored.

## Documentation

| Doc | What it covers |
|---|---|
| [WORKFLOW.md](docs/WORKFLOW.md) | End-to-end tutorial: video → geotag → import → reconstruct → export |
| [USER-MANUAL.md](docs/USER-MANUAL.md) | Full reference for the backend, the frontend, and the splat trainer |
| [INSTALL.md](docs/INSTALL.md) | System requirements, per-platform setup, deployment and auth |
| [SETUP.md](docs/SETUP.md) | GPU / CUDA / gsplat training setup |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Exact error messages → causes → fixes |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Component map, reconstruction state machine, design rules |
| [WEBODM.md](docs/WEBODM.md) | WebODM round trip: upload, poll, download results |
| [CESIUM-ION.md](docs/CESIUM-ION.md) | Cesium ion tileset upload |
| [VENDOR-PROJECT-IMPORT.md](docs/VENDOR-PROJECT-IMPORT.md) | Importing Pix4D / DroneDeploy projects |
| [WINDOWS-INSTALLER.md](docs/WINDOWS-INSTALLER.md) | Building the distributable Windows installer |
| [MACOS-BUNDLE.md](docs/MACOS-BUNDLE.md) | Building and validating the local arm64 macOS `.app` bundle |
| [CHANGELOG.md](CHANGELOG.md) | Release history |

## Docker

A CPU-only image serves the backend and the built frontend from one container and one API process.
The Docker launcher uses the same validated deployment profile as `python -m backend`; its
non-loopback container bind is intentionally rejected unless PIN/API-key auth is enabled or the
explicit `deployment.allow_unauthenticated_lan` override is set. Enable auth in a mounted
`config.yaml` before launching:

```bash
docker build -t telemetry-frame-mapper .
docker run --rm -p 127.0.0.1:8000:8000 \
  -v "$PWD/config.yaml:/app/config.yaml:ro" \
  -e DRONE_MAPPING_PIN_HASH \
  -v "$PWD/data:/app/data" \
  -v "$PWD/imports:/app/imports" \
  -v "$PWD/processed:/app/processed" \
  -v "$PWD/exports:/app/exports" \
  telemetry-frame-mapper
```

Open `http://localhost:8000`. `-p 127.0.0.1:8000:8000` is deliberate: when auth is disabled
(and you have explicitly set `deployment.allow_unauthenticated_lan: true`), never publish the
container with `-p 8000:8000`; keep it loopback-only. The image bundles `ffmpeg`, `exiftool`, and
COLMAP. GPU training is out of scope for it — use the manual setup in [docs/SETUP.md](docs/SETUP.md).

## Testing

```bash
pytest                              # CLI + backend
ruff check .                        # linter
cd frontend && npm test -- --run    # frontend (vitest)
```

Tests use inline fixture data and temporary paths, and every external binary is mocked — no real
ffmpeg, exiftool, COLMAP, or GPU required.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Report security issues through
[private advisories](https://github.com/BrandonRobare/telemetry-frame-mapper/security/advisories/new)
rather than public issues — see [SECURITY.md](SECURITY.md).

## Privacy

Do not commit real drone videos, FlightRecord files, extracted frames, SRT files, or geotagged
images. `.gitignore` blocks them by default; run `git status --short` before pushing.

## License

MIT — see [LICENSE](LICENSE).
