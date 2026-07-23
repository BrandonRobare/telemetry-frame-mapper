# Architecture

telemetry-frame-mapper is a monorepo with three runnable components sharing one repository and one data directory layout:

```
DJI video ──CLI──> geotagged JPGs ──import──> backend DB/services ──REST──> React UI
                                                      │
                                                      └──> COLMAP ──> gsplat trainer ──> splat.ply ──> viewer/exports
```

## Components

### CLI — `src/drone_video_geotagger/`

A standalone geotagging tool (`drone-video-geotagger`). Pipeline order inside `cli.py::run()`:

| Stage | Module | What it does |
|---|---|---|
| 1 | `video.py` | `ffmpeg` extracts the DJI subtitle telemetry track (stream `0:2`) to SRT; reads `creation_time` for the video start timestamp |
| 2 | `telemetry.py` | Parses DJI SRT into `TelemetryPoint`s (time window, lat/lon, relative altitude); linear interpolation between points |
| 3 | `frames.py` | Collects `*.jpg`, frame index = last number in the filename; infers extraction fps from telemetry duration when not given; builds `FrameTag`s (absolute altitude = takeoff + relative) |
| 4 | `exiftool.py` | Writes one ExifTool args file and invokes `exiftool -@ file` once for all frames |
| 5 | `audit.py` | Writes `frame_geotags.csv` for inspection |

`paths.py` translates WSL paths to Windows paths when the configured executable is a `.exe`. External binaries are always invoked as argv lists (no shell); missing binaries raise actionable install guidance.

### Backend — `backend/`

FastAPI app (`backend.main:app`), SQLite via SQLAlchemy (PostgreSQL-swappable through `DATABASE_URL`), with Alembic migrations in `backend/db/migrations/` for schema upgrades.

- **Routers** (20): sessions, images, footprints, coverage, flight_log, srt, plans, export, session_log, reconstruction, annotations, defects, comparisons, system, jobs, storage, target_areas, georeferencing, settings, uploads — self-documented at `/docs`.
- **Key services:**
  - `flight_log_sync.py` — uploads normalize DJI FlightRecord CSV plus three explicit
    vendor CSV contracts into `FlightLog` / `FlightLogPoint`: Autel
    `Time(ms),Latitude,Longitude,Altitude(m)`; Parrot fdr-lite
    `time,latitude,longitude,altitude`; and MAVExplorer/ArduPilot POS
    `timestamp,TimeUS,Lat,Lng,Alt`. The upload endpoint rejects missing or
    unrecognized headers with HTTP 422 rather than inferring coordinates.
  - `POST /sessions/bulk` — applies one typed operation to up to 100 selected sessions: archive with the existing portable bundle service, assign a project, replace/add tags, or delete after the literal `confirm: "DELETE"` guard. It commits each session independently and returns an outcome for every requested ID, so stale IDs and local filesystem failures do not hide completed work.
  - `ingest.py` / `ingest_orchestrator.py` — EXIF GPS + DJI XMP extraction (relative altitude → AGL, yaw, gimbal pitch), quality scoring (OpenCV sharpness/brightness), thumbnails, footprint computation, case-insensitive file dedupe. Each image (and its footprint) is committed individually as it's processed, so footprints are queryable mid-import, not just after it finishes.
  - `geometry.py` — ground footprint math: UTM projection, FOV-based extent from AGL, yaw rotation (Shapely/pyproj).
  - `GET /footprints` supports an optional `since_id` cursor (footprints with `id > since_id`) so a client can poll for newly-persisted footprints during an in-progress import instead of re-fetching the whole session each tick. This is a read-only view over rows ingest already writes — it does not trigger coverage computation, which stays behind its explicit "Run coverage analysis" button.
  - `GET /projects/{project_id}/trends` is another read-only projection: it time-orders that
    project's sessions and joins their latest persisted coverage run and completed reconstruction.
    It has no snapshot table, worker, or cross-project joins; unavailable metrics are `null`.
  - `mission planning` (`plans` router) — lawnmower path generation over a target area, KML/GPX export.
  - `geopackage_export.py` — writes the populated mapped-product layers in the configured
    target CRS. It reuses persisted geometry only; DSM/DEM sidecars are attribute-table
    references rather than embedded raster data.
  - `gis_project_files.py` — writes deterministic QGIS `.qgz` and ArcGIS Pro `.lyrx`
    references beside the current mapped-products GeoPackage, without a GIS SDK.
  - `reconstruction.py` — the heavy pipeline (below).
  - `colmap_io.py` / `ply_io.py` / `splat_trainer.py` — COLMAP sparse-model loader (numpy), INRIA-layout 3DGS PLY I/O + opacity-prune LODs (numpy), and the gsplat training loop (torch/gsplat, lazily imported so the backend never requires them).
- **Config:** `config.yaml` at repo root → `AppConfig` dataclass; relative directory settings resolve against the config file's location. Reconstruction presets (`quick`/`full`) live under the `reconstruction:` key. The `logging:` block configures a local stdlib rotating JSONL handler for the `backend` logger; it has no remote transport and writes under the config directory by default.
- **Backups:** `artifact_backup.py` creates versioned SQLite/config/artifact snapshots. An opt-in
  stdlib thread schedules exactly one named backup target per day; it calls that same service,
  prevents overlap with a lock, and exposes safe run state at `GET /storage/backup-schedule`.
- **Share links:** `ShareLink` stores only a SHA-256 digest of each random opaque link token, an
  expiry, optional stdlib-scrypt password hash, and revocation time. Password unlocks and all new
  artifact downloads use a server-persisted, HttpOnly `/share` cookie session; legacy signed links
  retain their URL-token artifact access until they expire.

### Frontend — `frontend/`

Vite + React 19 + TypeScript, feature-sliced (`src/features/<tab>/` + `src/shared/`). Server state via TanStack Query, UI state via Zustand, Leaflet/react-leaflet for maps, `@mkkellogg/gaussian-splats-3d` (Three.js) for the splat canvas, Tailwind v4.

Fourteen tabs: **Overview** (pipeline status and import CTA), **Map** (footprints + coverage on satellite imagery — while an import is running for the selected session, footprints poll incrementally via `since_id` and render live so coverage gaps are visible before the import finishes), **GPS Sync** (flight-log matching), **Review** (quality flags, frame selection, reprojection-error badges), **Plan** (target areas, lawnmower plans), **Export** (WebODM georeferencing CSV-only zip, GeoJSON, LAS, mesh), **Session Log** (event history + battery/flight records), **Field Checklist** (pre-flight/post-flight operator reminders, localStorage-only), **Reconstruct** (presets, job start), **Jobs** (resource monitor + job logs), **Storage** (disk breakdown + file browser), **Splat Viewer** (3D canvas, sparklines, coverage-gap heatmap, annotations, measurements, ortho/3D split, flythrough, presentation/narration mode), **Compare** (voxel change detection plus a selected-project trend table), **Settings** (app, storage, mission, reconstruction, and render preferences).

## The reconstruction job

Jobs run as a background daemon thread with a `threading.Event` cancel flag, writing progress directly to the `Reconstruction` row (no task queue — single-user tool, GPU jobs are serial anyway).

**State machine:**

```
pending ──> running_colmap (0–95%) ──> running_gsplat (95–100%) ──> complete (step=done)
                 │                            │
                 │                            ├── training deps absent ──> complete (step=colmap_only)
                 │                            ├── CUDA OOM ──> failed ("switch to 'quick' preset…")
                 │                            └── cancel    ──> failed ("Cancelled by user")
                 └── COLMAP error / cancel ──> failed (stage + stderr recorded)
```

**Stage detail:**
1. *Workspace* — selected frames are linked/copied into `colmap_dir/images/`, single PINHOLE camera derived from configured FOV.
2. *COLMAP* (subprocess): `feature_extractor → exhaustive_matcher → mapper → model_converter` — the sparse model lands in `sparse/0/` in both BIN and TXT form. Per-image reprojection errors are parsed from the TXT model and surfaced in the Review tab. A similarity geo-transform (COLMAP space ↔ UTM, seeded by the GPS EXIF) is stored as JSON on the record — this is what lets the viewer do GPS-accurate annotations and measurements. `GET /reconstruction/{id}/calibration-drift-report` compares multiple completed COLMAP camera estimates when available; it returns `unavailable` for the normal single-camera result and never treats EXIF metadata as self-calibration output.
3. *Splat training* (in-process, torch + `gsplat.rasterization` with default densification): initialized from the sparse points, capped gaussian count for small GPUs, periodic PSNR/SSIM eval feeding the viewer's sparklines; exports standard INRIA-layout `splat.ply` plus 10 %/50 % opacity-pruned LODs and a nadir thumbnail.
4. *Lazy derivatives on first request:* LAS point cloud (laspy), DSM/ground-classified DEM GeoTIFF (laspy + rasterio), cached DSM slope PNG, coverage-gap voxelization, voxel diff for Compare — each cached to `exports/{id}/` with its path stored on the record. DEM output refuses point clouds without ASPRS ground labels instead of inventing bare-earth terrain. Slope uses local NumPy gradients and makes no-data/adjacent cells transparent instead of inventing terrain.
5. *Optional:* SuGaR mesh export (manual upstream install), server-side MP4 flythrough (browser MediaRecorder is the primary path).

### Calibration-drift workflow

Reconstructions keep COLMAP's shared-camera mode by default (`reconstruction.single_camera: true`).
For an investigation that needs the calibration-drift report to compare multiple COLMAP estimates,
set `reconstruction.single_camera: false` in `config.yaml` (or PATCH `/settings` with
`{"reconstruction":{"single_camera":false}}`) before starting a new reconstruction. This lets
COLMAP create separate camera estimates instead of tying all frames to one shared estimate. It
adds parameters to bundle adjustment and can make a sparse reconstruction less constrained, so use
it only with adequate overlap and treat the report as a consistency signal, not calibration or GCP
accuracy. The default shared-camera workflow remains the preferred production path.

**Process isolation (or lack of it):** training runs in a background thread inside the API process, not a subprocess. A Python-level exception during training — OOM, missing deps, cancellation — is already caught in the pipeline thread and reported as a failed (or degraded `colmap_only`) job; it cannot bring down the API, since an uncaught exception in a thread just ends that thread. The one scenario that would still take the whole process down is a genuine native crash (a CUDA driver abort or a segfault inside libtorch/gsplat's C extension), because nothing short of OS-level process isolation stops that. This is a deliberately deferred hardening item: a real fix means moving training into a separate process with pipe-based progress/cancel IPC (today's `progress_cb` closure writes straight to a live DB session and `cancel` is a shared `threading.Event`, neither of which crosses a process boundary as-is) — a rewrite that isn't justified today for a single-user local app with no reported crash incidents.

## Data layout

```
data/        SQLite DB + runtime data        (gitignored)
imports/     drop folder for image sessions  (gitignored)  ← import paths are relative to here
processed/   thumbnails, derived images      (gitignored, served at /processed)
exports/     plans, splats, LODs, LAS, diffs (gitignored)  ← exports/{reconstruction_id}/…
```

**Key DB entities:** `Session` (one import) → `Image` (per frame: GPS, AGL, yaw, quality, flags, footprint WKT/GeoJSON) → `Reconstruction` (preset, status/step/progress, splat/LOD/thumb paths, geo-transform, metrics) → `Comparison` (voxel diff between two reconstructions), plus target areas, plans, flight logs, annotations, session log entries.

## Design rules that matter when contributing

- **External tools are subprocesses behind gates** — argv lists, never shell; missing binaries must produce install guidance, not tracebacks; CI never gets real binaries (all external tools are mocked).
- **Heavy Python deps are lazy** — torch/gsplat/SuGaR/laspy import inside functions; `pip install .[backend]` and backend import must always work without them, degrading per the state machine above.
- **The splat PLY layout is a contract** — exact INRIA property order, channel-major `f_rest`, wxyz quaternions; the browser viewer, LAS colorization, and coverage gaps all parse it.
- **Paths are `Path` objects; Python 3.11+; `from __future__ import annotations`; ruff E/F/I/UP/B at line length 100.**
- Tests use inline fixtures only — real flight data never enters the repo (`.gitignore` enforces).
