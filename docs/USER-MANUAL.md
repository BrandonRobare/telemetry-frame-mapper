# Drone Video Geotagger — User Manual

A complete pipeline that turns a DJI drone video into GPS-registered, explorable
3D — geotagged frames, coverage maps, mission plans, and gaussian-splat
reconstructions, with WebODM/OpenDroneMap-ready output at every step.

This manual covers **what the tool can do**, **how data flows through it**, and
**how the gaussian-splat trainer works**. For installation see
[INSTALL.md](INSTALL.md) and [SETUP.md](SETUP.md); for a guided first run see
[WORKFLOW.md](WORKFLOW.md); for error messages see
[TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## 1. Capabilities

The project is a monorepo with three independently usable components.

### CLI — `drone-video-geotagger`

A standalone command-line geotagging tool. Given a DJI video and a folder of
extracted JPG frames, it writes GPS EXIF tags into the frames so any
photogrammetry tool (WebODM, OpenDroneMap, COLMAP) can ingest them.

- Extracts the DJI telemetry track (SRT) from the MP4 with `ffmpeg`, or reads an
  existing `.srt` you supply.
- Parses DJI SRT into GPS fixes and interpolates latitude, longitude, and
  relative height for every frame's timestamp.
- Computes absolute altitude as `takeoff altitude (ASL) + relative height`.
- Writes GPS EXIF tags with `exiftool` (copies by default, or in place with `--in-place`).
- Emits an audit CSV (`frame_geotags.csv`) and the generated ExifTool argument
  file for inspection.
- WSL-aware path handling for `.exe` binaries on Windows.

### Backend — FastAPI service

A local REST API (binds to localhost, self-documented at `/docs`) covering
ingest, analysis, planning, reconstruction, and export — 77 endpoints
across 19 routers.

- **Import & quality:** session import; per-image sharpness and brightness
  scoring (OpenCV); DJI XMP parsing for relative altitude, yaw, and gimbal pitch.
- **Session organization:** tags (short labels, max 40 chars) and free-text
  operator notes per session via `PATCH /sessions/{id}`; edit them in the Map
  tab's session sidebar and filter the session picker by tag.
- **Geometry & coverage:** ground-footprint computation (Shapely/UTM from
  altitude + heading); coverage analysis against drawn target areas with gap and
  overlap detection.
- **Mission planning:** lawnmower flight-plan generation with KML/GPX export and
  battery-count estimates.
- **Flight-log sync:** match DJI FlightRecord CSV timestamps to frames.
- **Battery/flight records:** per-session operator field records
  (`/sessions/{id}/flight-entries`) — battery ID, start/end charge %, flight
  duration (derived from flight-log telemetry when omitted), and notes.
- **Reconstruction jobs:** COLMAP structure-from-motion plus gaussian-splat
  training, run as cancellable background jobs with live progress and logs.
- **Geo-registration:** a COLMAP↔UTM similarity transform so reconstructions
  carry real-world coordinates.
- **Exports:** WebODM georeferencing CSV-only zip, GeoJSON, LAS 1.4 point cloud, optional SuGaR mesh
  (GLB/OBJ/MTL), and flythrough video.
- **System reporting:** CPU/RAM/GPU/VRAM resource readout and
  `colmap_available` / `gsplat_available` tool-presence flags.

### Frontend — React web app (13 tabs)

| Tab | What it does |
|-----|--------------|
| **Overview** | Pipeline status, session summary, import call-to-action, and reconstruction readiness |
| **Map** | Leaflet + ESRI satellite basemap, footprint polygons, coverage overlay, session stats sidebar with tags and operator notes |
| **GPS Sync** | DJI FlightRecord CSV matching with timing deltas |
| **Review** | Thumbnail grid, quality flags, COLMAP reprojection-error badges, per-session frame selection for reconstruction |
| **Plan** | Target-area drawing, lawnmower plan generation, KML/GPX export, shutter-interval calculator (photo spacing and timed-shot interval from speed, altitude, overlap, and camera FOV) |
| **Export** | WebODM georeferencing CSV-only zip, GeoJSON, LAS point cloud, mesh (GLB/OBJ/MTL) |
| **Session Log** | Event history per session, plus battery/flight records: log battery ID, start/end %, duration, and a note per flight (duration is auto-filled from the flight log when left blank) |
| **Reconstruct** | Start quick/full reconstruction jobs |
| **Jobs** | Resource monitor (CPU/RAM/GPU) with live job logs; job completion/failure fires an in-app toast (and a desktop notification when the tab is hidden and permission is granted) |
| **Storage** | Disk usage by category and a file browser |
| **Splat Viewer** | In-browser gaussian-splat rendering, PSNR/SSIM sparklines, coverage-gap heatmap, GPS-pinned annotations, distance/area measurement, ortho/3D split view, flythrough recording |
| **Compare** | Voxel change detection between two reconstructions of the same site |
| **Settings** | App preferences, import/storage paths, mission parameters, reconstruction presets, rendering/export defaults |

Light/dark theme with persistence.

---

## 2. The data pipeline

There are two pipelines: the **CLI geotagging pipeline** (video → geotagged
frames) and the **reconstruction pipeline** (geotagged frames → 3D splat). They
chain end to end.

### 2a. CLI geotagging pipeline

```
DJI video.mp4
   │  ffmpeg: extract subtitle/telemetry stream (0:2) → flight.srt
   │          read creation_time → video start timestamp
   ▼
telemetry.py: parse SRT → TelemetryPoint[]  (time window + lat/lon/rel-alt)
   │          interpolate() linearly between fixes for any time offset
   ▼
frames.py:   glob *.jpg, read frame index (LAST number in filename),
   │          time = (index − first_index) / frame_rate,
   │          interpolate GPS, abs_alt = takeoff_alt + rel_alt → FrameTag[]
   ▼
exiftool.py: build one -Tag=value arg file, write GPS EXIF in a single call
   │
audit.py:    write frame_geotags.csv (index, time, lat/lon, alt, timestamp)
   ▼
<frames>_geotagged/  ← upload to WebODM, or import into the web app
```

Key rules:
- **Frame index = the last number in the filename**, so `frame_00042.jpg` and
  `DJI_0081_frame_42.jpg` both index as frame 42; files with no digits are
  skipped.
- **Frame rate** is taken from `--frame-rate` if given, otherwise estimated from
  the telemetry duration and frame count (snapping to common rates).
- **`--takeoff-altitude`** is meters above sea level of the launch point, not
  flight height; the DJI telemetry height is relative and gets added on top.

### 2b. Reconstruction pipeline (backend)

Once geotagged frames are imported as a session, a reconstruction job runs these
stages in a background thread (`backend/services/reconstruction.py`), reporting
progress from 0–100%:

```
selected frames
   │  write COLMAP workspace (images + PINHOLE cameras.txt)         ~2%
   ▼
COLMAP SfM:  feature_extractor → matcher (exhaustive=full,         10–95%
   │         sequential=quick) → mapper → model_converter
   │         → sparse/0 model (cameras, images, points3D)
   ▼
geo-transform: derive COLMAP→UTM similarity from frame GPS
   ▼
gsplat training (running_gsplat):  see §3                          95–99.5%
   ▼
LOD generation:  ply_io opacity-prune → _preview.ply (10%),        ~99.6%
   │              _medium.ply (50%)
   ▼
thumbnail:  render a 512×512 nadir-ish JPEG                        100%
   ▼
exports/{id}/splat.ply  + LODs  + processed/thumbs/splat_{id}.jpg
```

Per-frame reprojection errors from COLMAP are stored and surfaced as badges in
the Review tab. If torch/gsplat are not installed, the job completes gracefully
as **`colmap_only`** — you still get the sparse cloud, LAS export, and coverage
data, just no splat.

**Outputs you can download** (Splat Viewer / Export tab / API):
`splat.ply` and its `_preview`/`_medium` LODs, LAS 1.4 point cloud, optional
SuGaR mesh, a server-rendered or browser-recorded flythrough MP4, GeoJSON, and a
WebODM/OpenDroneMap georeferencing CSV-only zip.

---

## 3. The gaussian-splat trainer

![Data flow of the gaussian-splat trainer: COLMAP produces poses and points; our custom code seeds Gaussians and runs a training loop that calls gsplat and torch, applies a VRAM cap, and exports a splat PLY. Purple boxes are our code; orange boxes are external dependencies.](images/splat-trainer.svg)

*Purple = our custom code (the training loop, initialization, loss, VRAM cap, I/O). Orange = external dependencies it calls — the gsplat library (in-process), torch/CUDA, and the COLMAP binary (subprocess). The logic is custom; it is not dependency-free.*

The 1.0 headline feature. Earlier builds called a `gsplat.train` API that does
not exist in the real `gsplat` package, so splat training always failed silently.
1.0 replaces it with a real, in-process training loop
(`backend/services/splat_trainer.py`) built on `gsplat.rasterization`, supported
by two pure-numpy modules:

- **`colmap_io.py`** — reads the COLMAP sparse model (BIN, falling back to TXT):
  camera intrinsics, image poses (world→cam quaternions), and the sparse point
  cloud. Stdlib + numpy only.
- **`ply_io.py`** — reads/writes gaussian-splat PLY files in the exact INRIA
  3DGS layout the frontend viewer consumes, plus an opacity-based prune used for
  LOD generation.

The trainer imports torch, gsplat, and PIL **inside functions only**, so the
backend runs (and all tests pass) without the GPU stack installed.

### How training works

1. **Initialize from the sparse cloud.** Gaussian centers are the COLMAP points;
   colors come from point RGB (converted to zeroth-order spherical harmonics);
   per-gaussian scale is the log mean distance to the 3 nearest neighbors;
   opacities start at a logit of 0.1; rotations start as identity quaternions.
2. **Per-attribute Adam optimizers** (separate learning rates for means, scales,
   quaternions, opacities, and the SH bands), with the means learning rate on an
   exponential decay over the run.
3. **Each iteration** renders one random training view via
   `gsplat.rasterization` (packed mode, fp32) and computes a
   `0.8 · L1 + 0.2 · (1 − SSIM)` loss (a pure-torch 11×11 Gaussian-window SSIM —
   no extra dependency). `gsplat.DefaultStrategy` handles adaptive densification
   and pruning.
4. **VRAM safety cap.** Once the gaussian count reaches the preset's
   `max_gaussians`, densification is frozen so the run cannot exhaust GPU memory.
5. **Spherical-harmonic warmup** raises the active SH degree gradually for stable
   view-dependent color.
6. **Evaluation** every N iterations renders held sample views and records PSNR +
   SSIM; these become the sparkline you see in the Splat Viewer. (Metrics are on
   training views — at drone-survey frame counts a holdout split would cost
   reconstruction quality.)
7. **Export** the final gaussians to `splat.ply` in INRIA layout.

The whole run holds a process-wide GPU lock (one training job at a time, sized
for a 4 GB card) and clears the CUDA cache on exit.

### Presets

Two presets ship in `config.yaml` under `reconstruction.presets`; the trainer
derives its full hyperparameter set from the preset's iteration count.

| Parameter | `quick` (1,000 iters) | `full` (30,000 iters) |
|-----------|----------------------|-----------------------|
| Source downscale | ÷4 (≈1000×750) | ÷2 (≈2000×1500) |
| SH degree | 1 | 2 |
| Max gaussians (VRAM cap) | 350,000 | 1,000,000 |
| Densify start/stop/every | 300 / 800 / 100 | 500 / 15,000 / 100 |
| Opacity reset | disabled | every 3,000 |
| Eval every / views | 250 / 4 | 1,000 / 4 |
| SH warmup | +1 degree / 500 iters | +1 degree / 1,000 iters |
| COLMAP matching | sequential | exhaustive |

Use **quick** to validate a capture in minutes; **full** for a final,
high-quality splat.

### Graceful degradation (contracts)

- **No torch/gsplat** → training raises a "COLMAP sparse cloud only" error and the
  job completes as `colmap_only`.
- **CUDA out of memory** → surfaced as a user-facing hint to switch to the quick
  preset or reduce the frame count.
- **Cancellation** is polled every iteration; a mid-training cancel marks the job
  failed ("Cancelled by user"), not a false success.
- **Thumbnail rendering** is best-effort and never raises.
- **Flythrough**: the in-browser recorder is the primary path; the server-side
  MP4 render (raw frames piped to `ffmpeg`/libx264, smoothstep keyframe easing
  that matches the browser preview exactly) needs the full GPU stack.

### Validated performance (RTX 3050 Ti, 4 GB)

End-to-end runs on an 86-frame, 4K house orbit:

| Preset | Wall time | Gaussians | PSNR | SSIM | Peak VRAM |
|--------|-----------|-----------|------|------|-----------|
| quick  | ~6 min | 85,635 | 23.19 dB | 0.589 | 3.9 GB |
| full   | ~70 min | 1,015,964 (cap fired) | 27.45 dB | 0.794 | 3.9 GB |

Peak VRAM in both runs is COLMAP's GPU feature extraction; training itself held
≈2.3 GB. The full preset hit and held the 1,000,000-gaussian cap with no OOM.

> **Windows GPU note:** because torch's extension loader re-runs a `where cl`
> compiler check on every load, the backend itself must be launched from a Visual
> Studio `vcvars64` environment (with `cl.exe` on PATH), even when gsplat's
> kernels are already compiled and cached. See [SETUP.md](SETUP.md).

---

## 4. Quick start

### Geotag from the CLI

```bash
# 1. Extract frames from the video
ffmpeg -i flight.mp4 -vf fps=8 extracted/frame_%05d.jpg

# 2. Geotag them (takeoff altitude is meters above sea level)
drone-video-geotagger --video flight.mp4 --frames extracted --takeoff-altitude 236.94
```

Output lands in `extracted_geotagged/`. Add `--in-place` to update the original frame folder instead. Full flag list: `drone-video-geotagger --help`.


### Browser upload import

From **Overview** or **Map**, open **Import**. The default **Browser upload** mode lets you choose or drag a local folder of frames; the browser streams those files to the backend in chunks, then the backend starts the normal import pipeline. Use this when the frames are on your workstation and not already under the backend `imports/` folder. Use **Server path** mode only when the folder already exists under `imports/` on the machine running the backend.

### Run the web app

```bash
# Backend (from the repo root)
uvicorn backend.main:app --reload          # API at http://localhost:8000, docs at /docs

# Frontend
cd frontend && npm install && npm run dev   # http://localhost:5173
```

Then: drop a geotagged frame folder under `imports/`, import it from the app,
mark usable frames in **Review**, and start a reconstruction from **Reconstruct**
(start with the `quick` preset). Watch progress in **Jobs**, then open the result
in **Splat Viewer**.

External binaries: `ffmpeg` and `exiftool` are required for the CLI; `colmap`
plus a CUDA GPU with torch + gsplat are required for reconstruction (all optional
and detected at runtime). See [INSTALL.md](INSTALL.md) and [SETUP.md](SETUP.md).


## Semantic labels

For completed splat reconstructions, the Semantic Labels workflow can attach a
sidecar `semantic_labels.npz` without changing `splat.ply`. The workflow maps
each gaussian to one of six operator classes: ground, vegetation, structure,
vehicle, water, or other. The viewer can use the sidecar as a class overlay, and
LAS exports use it to populate ASPRS classification codes when present.

Quality expectations are intentionally conservative. The default SegFormer/ADE20K
model is small enough for field hardware, but ADE20K is not an aerial-survey
dataset. Expect good separation for broad ground/vegetation/structure regions and
more mistakes on oblique imagery, tiny vehicles, reflective water, shadows, or
classes absent from ADE20K. Treat the output as an operator QA aid, not a surveyed
truth layer. If more than about 30% of points are unlabeled on a normal survey,
recheck frame coverage, COLMAP registration, and GPU dependency status before
trusting downstream LAS classifications.
