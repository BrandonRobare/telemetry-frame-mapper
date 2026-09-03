# Telemetry Frame Mapper — User Manual

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
ingest, analysis, planning, reconstruction, and export.

- **Import & quality:** session import; per-image sharpness and brightness
  scoring (OpenCV); DJI XMP parsing for relative altitude, yaw, and gimbal pitch.
- **Session organization:** tags (short labels, max 40 chars) and free-text
  operator notes per session via `PATCH /sessions/{id}`; edit them in the Map
  tab's session sidebar and filter the session picker by tag. The top-bar
  **Bulk** picker can select visible sessions to assign a project, add or
  replace tags, or archive each with the normal portable bundle. It reports an
  outcome for every selected session; deletion requires typing the exact value
  `DELETE` and uses the same cleanup path as a single-session delete.
- **Geometry & coverage:** ground-footprint computation (Shapely/UTM from
  altitude + heading); coverage analysis against drawn target areas with gap and
  overlap detection.
- **Mission planning:** lawnmower flight-plan generation with KML/GPX export and
  battery-count estimates.
- **Flight-log sync:** upload a supported telemetry CSV, preview timing deltas, then
  match positions to frames. Supported header contracts are DJI FlightRecord
  (`time(millisecond)`, `OSD.latitude`, `OSD.longitude`, optional
  `OSD.altitude[m]`), Autel (`Time(ms)`, `Latitude`, `Longitude`, `Altitude(m)`),
  Parrot fdr-lite (`time`, `latitude`, `longitude`, `altitude`), and ArduPilot
  MAVExplorer POS (`timestamp`, `TimeUS`, `Lat`, `Lng`, `Alt`). CSV uploads with
  missing or unrecognized coordinate headers are rejected; this app does not
  fabricate a position.
- **Battery/flight records:** per-session operator field records
  (`/sessions/{id}/flight-entries`) — battery ID, start/end charge %, flight
  duration (derived from flight-log telemetry when omitted), and notes.
- **Defect flagging:** per-session defect records (`/sessions/{id}/defects`) —
  category (crack, corrosion, vegetation, water damage, missing material,
  other), optional severity (low/medium/high) and note, linked to one or more
  source photos (which carry the GPS coordinates). Flagged from the Review tab;
  listed per-session in Session Log.
- **Reconstruction jobs:** COLMAP structure-from-motion plus gaussian-splat
  training, run as cancellable background jobs with live progress and logs.
- **Geo-registration:** a COLMAP↔UTM similarity transform, solved in-process from
  per-image camera centres and their EXIF GPS, so reconstructions carry real-world
  coordinates. It can fail: fewer than three usable GPS frames, or a near-collinear
  flight line, leaves the reconstruction **not georeferenced** rather than storing a
  placeholder. Exports then carry a local frame with no CRS, and GPS-dependent viewer
  features stay disabled.
- **Exports:** WebODM georeferencing CSV-only zip, GeoJSON, LAS 1.4 point cloud, optional SuGaR mesh
  (GLB/OBJ/MTL), and flythrough video.
- **Cesium 3D Tiles share bundle:** `POST /export/reconstructions/{id}/share-bundle` writes a real,
  geo-referenced 3D Tiles 1.1 `tileset.json` (loadable directly in CesiumJS) alongside the manifest
  and viewer page. The root tile's `boundingVolume.region` and ECEF `transform` are computed from
  the reconstruction's image GPS bounds/centroid; when a mesh GLB is available it's bundled and
  referenced as tile content, otherwise the tileset still carries a correct region/transform with
  no content. The mesh is assumed to sit in a local East-North-Up frame centered on that GPS
  centroid — good enough to place it on the globe, not a substitute for a full similarity-transform
  fit against ground control.
- **Cesium ion publishing:** with an explicitly enabled `cesium_ion` configuration and a token held
  only in its named environment variable, `POST /export/reconstructions/{id}/cesium-ion` uploads
  that existing share bundle and returns the ion asset ID. See [CESIUM-ION.md](CESIUM-ION.md).
- **Session archive/restore:** `POST /sessions/{id}/archive` bundles a session's
  full DB state (images, flight logs, reconstructions with lineage,
  measurements, annotations, defects, etc.) plus its artifact files into one
  `.zip`, for moving a session to another machine without manual filesystem
  surgery. `POST /sessions/restore` (given the zip's path) recreates it as a
  brand-new session with fresh IDs — it never overwrites an existing session,
  and any reconstruction lineage (`parent_reconstruction_id`) is remapped to
  the new IDs or dropped if the parent isn't in the bundle.
- **Compact web `.splat` export:** `POST /export/reconstructions/{id}/splat?preset=web|preview|medium`
  writes a dependency-free, 32-bytes-per-gaussian `.splat` (the antimatter15
  gsplat web-viewer format) — no Node/`splat-transform` binary required.
  Higher-order SH is dropped and the DC term is baked into a flat RGBA byte
  per gaussian (that *is* the web/SH-quantization compaction); opacity is
  sigmoid-activated to alpha, log-space scale is exponentiated, and gaussians
  are written sorted by opacity descending. `preview`/`medium` additionally
  prune by opacity keep-ratio (10%/50%) before writing. For heavier SPZ/SOG
  compression via the external Node tool, see `splat_transform.py` instead.
- **System reporting:** CPU/RAM/GPU/VRAM resource readout and
  `colmap_available` / `gsplat_available` tool-presence flags.

### Frontend — React web app (14 tabs)

| Tab | What it does |
|-----|--------------|
| **Overview** | Pipeline status, session summary, import call-to-action, and reconstruction readiness |
| **Map** | Leaflet + ESRI satellite basemap, footprint polygons, coverage overlay, session stats sidebar with tags and operator notes. While a session is still importing, footprints stream in live (an "Importing…" badge shows frame progress) so coverage gaps are visible before the import finishes — the coverage-gap analysis itself still requires the explicit "Run coverage analysis" button |
| **GPS Sync** | DJI FlightRecord CSV matching with timing deltas |
| **Review** | Thumbnail grid, quality flags, COLMAP reprojection-error badges, per-session frame selection for reconstruction, flag a defect (category + optional severity/note) directly from a photo |
| **Plan** | Target-area drawing, lawnmower plan generation, KML/GPX export, shutter-interval calculator (photo spacing and timed-shot interval from speed, altitude, overlap, and camera FOV); plan validation includes RTH/terrain sanity checks (return-path terrain clearance, cruise-below-terrain, battery-reserve distance) when a DEM is configured |
| **Export** | WebODM georeferencing CSV-only zip, GeoJSON, LAS point cloud, mesh (GLB/OBJ/MTL) |
| **Session Log** | Event history per session, plus battery/flight records (battery ID, start/end %, duration, note) and flagged defects (category, severity, note, linked photos) |
| **Field Checklist** | Pre-flight and post-flight operator reminders — checkboxes for defaults (batteries charged, SD card formatted, propellers inspected, firmware/RTH height set, GPS lock, takeoff altitude recorded; video+SRT copied, frames extracted, battery state noted), plus custom items you add/remove and a reset-checks action. Saved to this browser's local storage — no session or backend involved |
| **Reconstruct** | Start quick/full reconstruction jobs |
| **Jobs** | Resource monitor (CPU/RAM/GPU) with live job logs; job completion/failure fires an in-app toast (and a desktop notification when the tab is hidden and permission is granted) |
| **Storage** | Disk usage by category, a file browser, and configured artifact backups |
| **Splat Viewer** | In-browser gaussian-splat rendering, PSNR/SSIM sparklines, coverage-gap heatmap, GPS-pinned annotations, distance/area measurement, ortho/3D split view, flythrough recording, presentation/narration mode |
| **Compare** | Voxel change detection between two reconstructions of the same site, plus a selected-project trend table of existing session quality, coverage, and completed-reconstruction metrics. It is read-only: `—` means a metric has not yet been recorded. |
| **Settings** | App preferences, import/storage paths, mission parameters, reconstruction presets, rendering/export defaults |

Light/dark theme with persistence.

### Mobile quick-check (PWA)

`/mobile` (or the `/m` shorthand) is a phone-sized, read-only view for an
operator glancing at their phone in the field — it bypasses the desktop tab
shell entirely. It shows:

- A compact session picker (auto-selects the most recent session).
- Session status: frame/usable counts, coverage %, and which pipeline stage
  is active.
- The post-landing quick QA summary — the same `RapidQACard` and
  `/sessions/{id}/quick-report` data as the Overview tab's Rapid QA card,
  with GPS-lock heuristic warnings (frozen fix, no-lock points, implausible
  jumps — see #384) surfaced ahead of other warnings since space is tight.
- Running-job progress, both for the selected session and any other session
  with a job in flight.

Everything is read-only and reuses existing queries — no new endpoints.
`GET /` from a phone still opens the full desktop app.

The app is installable: `frontend/public/manifest.webmanifest` sets
`start_url` to `/mobile`, so "Add to Home Screen" opens straight to the
quick-check view. A minimal service worker (`frontend/public/sw.js`,
production-only) cache-first-serves the app shell (`/`, `/mobile`, the
manifest, and icons) — it does not cache API responses or provide offline
data sync.

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
COLMAP SfM:  feature_extractor → matcher → mapper →                10–95%
   │         model_converter
   │         → sparse/0 model (cameras, images, points3D)
   ▼
geo-transform: solve COLMAP→UTM similarity from frame GPS (may fail → not georeferenced)
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

**Feature matching** is chosen by `reconstruction.matcher` in `config.yaml` —
one global setting, *not* a per-preset one. Accepted values are `sequential`,
`sequential_guided`, `exhaustive` (the default) and `exhaustive_guided`;
`_guided` adds COLMAP's `--SiftMatching.guided_matching=1`, and anything
unrecognised silently falls back to `exhaustive`. Sequential matching is O(N)
and suits a single continuous flight line; exhaustive is O(N²) and is the most
expensive stage in the pipeline on large captures.

One override runs automatically: when the session has GPS, has at least
`reconstruction.spatial_matcher_min_images` frames (default 150), and the
installed COLMAP reports `spatial_matcher` support, the pipeline uses
`spatial_matcher` instead of the configured matcher — O(N·k) rather than O(N²),
tuned for lawnmower surveys (GPS priors, ignore Z, 50 neighbours, 100 m). Most
real surveys therefore never use the `matcher` value at all; drop
`spatial_matcher_min_images` below the frame count to see it take effect, or
raise it above to force the configured matcher.

Per-frame reprojection errors from COLMAP are stored and surfaced as badges in
the Review tab. If torch/gsplat are not installed, the job completes gracefully
as **`colmap_only`** — you still get the sparse cloud, LAS export, and coverage
data, just no splat.

**Outputs you can download** (Splat Viewer / Export tab / API):
`splat.ply` and its `_preview`/`_medium` LODs, LAS 1.4 point cloud, optional
SuGaR mesh, a server-rendered or browser-recorded flythrough MP4, GeoJSON, and a
WebODM/OpenDroneMap georeferencing CSV-only zip.

### Pix4D and DroneDeploy control-point CSVs

The API can translate surveyed WGS84 control points for either **Pix4D** or
**DroneDeploy** without storing them in the project database:

This is not a DroneDeploy or Pix4D project/package importer. See
[DroneDeploy and Pix4D project import](VENDOR-PROJECT-IMPORT.md) for the
documented boundary, supported migration path, and requirements for a future
safe importer.

- `POST /georeferencing/control-points/import` accepts `{"format":"pix4d"|"dronedeploy","contents":"..."}`.
- `POST /georeferencing/control-points/export` accepts `{"format":"pix4d"|"dronedeploy","points":[...]}` and returns CSV text.

Both supported mappings are deliberately limited to the shared geographic
contract: no header row, one row per point as
`label,latitude,longitude,elevation_m` in WGS84/EPSG:4326. Latitude is column
2 and longitude is column 3. The importer rejects headers, empty labels,
duplicate labels, non-numeric elevations, malformed rows, and coordinates
outside WGS84 ranges. Pix4D projected-coordinate/accuracy variants are not
converted by this WGS84 endpoint; choose the coordinate system in Pix4D when
importing a projected survey file.

Example export request:

```json
{
  "format": "dronedeploy",
  "points": [{"label": "north-pad", "latitude": 41.2, "longitude": -81.5, "altitude_m": 300.25}]
}
```

The returned `contents` is `north-pad,41.20000000,-81.50000000,300.250` plus a
newline, ready to save as a `.csv` for either supported WGS84 workflow.

### GeoPackage mapped-product export

`GET /export/reconstructions/{reconstruction_id}/geopackage` downloads a QGIS-ready
GeoPackage in the configured project target CRS. Add `?comparison_id={id}` to include
the completed comparison's changed voxel cells. The exporter writes only available
layers, in this stable order: `image_locations`, `footprints`, `flight_paths`,
`coverage_gaps`, `measurements`, and `comparison_change_cells`. Invalid or unavailable
source geometry is skipped; the request remains useful for the layers that exist.

If `exports/{reconstruction_id}/dsm.tif` or `dem.tif` already exists, the package adds
the non-spatial `raster_references` table with its path. It does not create, copy, or
embed raster data, so add that TIFF separately in QGIS when needed.

### QGIS and ArcGIS Pro project files

`POST /export/reconstructions/{reconstruction_id}/gis-project-files` first refreshes
`mapped_products.gpkg`, then writes these deterministic sibling files in
`exports/{reconstruction_id}/`: `mapped_products.qgz`, `mapped_products.lyrx`, and
`mapped_products_gis_manifest.json`. The response and manifest list their fixed file
names, the GeoPackage layers that were present, and optional `dsm.tif`/`dem.tif` sidecars.
Both GIS files use relative sibling references, so move the complete directory together.
Add `?comparison_id={id}` to include the same completed comparison layer as the
GeoPackage export. QGIS gets a zipped XML project; ArcGIS Pro gets a CIM layer-document
JSON file. Neither export creates, copies, or embeds raster data.

---

### Orthomosaic tiles (WMS / WMTS-style)

After an orthomosaic export finishes, discover its layer with
`GET /tiles/{reconstruction_id}/wms?SERVICE=WMS&REQUEST=GetCapabilities`.
The layer name is `reconstruction-{reconstruction_id}`. Request a WMS PNG in Web
Mercator with `REQUEST=GetMap`, `LAYERS`, `CRS=EPSG:3857`, `BBOX=west,south,east,north`,
`WIDTH`, and `HEIGHT`; only `image/png` is supported. Slippy-map clients can instead use
`GET /tiles/{reconstruction_id}/wmts/{z}/{x}/{y}.png` (XYZ/Web Mercator, zoom 0-22).
These endpoints reproject the exported GeoTIFF on demand; they neither create imagery nor cache tiles.

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

Use **quick** to validate a capture in minutes; **full** for a final,
high-quality splat. Presets only affect gsplat training — the COLMAP stages,
feature matching included, run identically under both (see §2b).

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
- **Presentation mode**: in the Splat Viewer, once you've captured at least two
  flythrough keyframes, click **▶ Present** to enter a chrome-free walkthrough —
  the sidebar, toolbar, and split-pane map hide and the camera flies the same
  keyframe path with pause/resume and 0.5x/1x/1.5x/2x speed. GPS-pinned
  annotations surface as narration callouts as the camera passes near them.
  Keyboard: `Space` pause/resume, `←`/`→` jump to the previous/next keyframe,
  `Esc` exit.

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
python -m backend                           # one API process; API at http://localhost:8000, docs at /docs

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


## 5. Sharing a reconstruction

The Export tab creates a revocable, opaque link to one completed reconstruction. Links default to
seven days and can carry an optional password.

The bearer token is returned once, in the creation response, and lives only in the viewer URL — it
is never stored in plaintext and never appended to artifact URLs. Password unlock issues an
`HttpOnly`, `SameSite=Lax` session cookie scoped to `/share` (marked `Secure` over HTTPS or behind a
TLS proxy). A cookie unlocked for one link cannot be replayed against another reconstruction.

Public responses distinguish the failure modes:

| Status | Meaning |
|---|---|
| `401` | The link is password-protected and not yet unlocked |
| `403` | Wrong password, or the token does not match this reconstruction |
| `410` | Expired or revoked |

Owners can inspect and revoke links:

```bash
GET  /export/reconstructions/{id}/share-links
POST /export/reconstructions/{id}/share-links/{share_link_id}/revoke
```

Links signed before 2.0.0 keep working until their signed expiry, but the legacy query-token
artifact format is no longer issued for new links.

## 6. Backups

`POST /storage/backup` takes an additive, versioned snapshot of the live SQLite database, a
sanitized `config.yaml`, and whichever of `imports`, `processed`, and `exports` you select. Every
copied file is SHA-256 recorded in `manifest.json`. The database is copied through SQLite's backup
API, so the WAL and SHM sidecars are deliberately not included.

Startup takes its own copy as well. When the app starts against an existing database that is
behind the migration head, it copies the database — through the same SQLite backup API — into a
`pre-migration/` directory beside the database file, and only then runs the migration. A fresh
database and one already at head are skipped, so an up-to-date install pays nothing. The copy is
logged at INFO with its path and how long it took, and `backup.pre_migration_keep` (default 3)
bounds how many are retained; the oldest is deleted first. If the copy cannot be written — a full
disk, an unwritable directory — startup fails and the migration does not run, because that copy is
the only rollback point.

Destinations must be allowlisted in `config.yaml` first — a local path has to match an entry
exactly:

```yaml
backup:
  local_destinations:
    - "E:/telemetry-backups"
  rclone_remote: "archive:telemetry-backups"   # credentials stay in the rclone config
```

Then submit `{"destination": "local", "local_destination": "E:/telemetry-backups"}` or
`{"destination": "rclone"}`, optionally with an `artifacts` list (default
`["processed", "exports"]`). Remote backups shell out to `rclone copy` — never `sync`, and never a
deletion flag — and rclone credentials and command output are never written into the snapshot or
returned by the API.

For a scheduled backup, define a named target drawn from the same allowlist and select it by name.
`daily_at` uses the server's local clock:

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

Only one backup runs at a time, so a slow remote copy is never overlapped by the next scheduled
run. `GET /storage/backup-schedule` reports operational status only — last run, next run, result —
never target credentials or command output. The scheduler is off unless `enabled: true`.

## 7. Importing

The Import dialog defaults to **Browser upload**: pick or drag a folder of frames and the app
streams it to the backend in chunks, then runs the same import pipeline as any other source. This
is the easiest route when the images are on your workstation but not already under `imports/`. The
**Server path** mode remains for folders that already live there.

**Upload / cloud drive** covers files a desktop client has already synced from OneDrive, Google
Drive, Dropbox, or similar. The provider's own client and the operating system authorize access;
the browser only submits the files you explicitly select, through the same chunked upload. There is
deliberately no "import from URL" endpoint, and the backend never stores cloud-provider OAuth
tokens — a direct provider integration would need a registered OAuth client and redirect URI,
least-privilege scopes, an encrypted token lifecycle, and a redirect/DNS policy before it could be
added safely.

### SD-card and watch-folder auto-import

Set `auto_import.enabled` and list each mounted card or staging folder explicitly, then restart the
backend:

```yaml
auto_import:
  enabled: true
  roots:
    - "E:/DCIM"
  poll_interval_seconds: 10
  stable_seconds: 30
```

The watcher polls, waits for a media directory to sit unchanged for `stable_seconds`, and then
starts the normal image-import pipeline. It never discovers drives on its own and never imports
outside `roots`. `GET /auto-import/status` reports which roots are watched, missing, or
unsupported.

It imports directories containing the configured image extensions (JPEG by default). It does not
copy card contents, watch video-only folders, or revisit a folder once its media-manifest
fingerprint has been claimed — that fingerprint is persisted, so a completed import is not repeated
after a restart. Move or copy edited media into a new folder when you want it imported again.

## 8. API-only workflows

These endpoints have no button in the UI. They exist for scripting and for the batch pipeline, and
they are live in `/docs` alongside everything else.

**Reproducibility manifest** — records exactly how an artifact was produced, for audit trails.

```bash
curl -X POST "http://127.0.0.1:8000/export/reproducibility-manifest?workflow=reconstruction"
```

`workflow` is the stage to describe; add `artifact_path` to pin the manifest to one output file.

**WebODM package** — a complete OpenDroneMap job: the images plus an options manifest, rather than
the CSV-only georeferencing zip the Export tab produces.

```bash
curl -X POST "http://127.0.0.1:8000/export/webodm-package?session_id=1&mode=exif&include_images=true"
```

Set `mode=gcp` with `include_gcp=true` to drive it from ground control points instead of EXIF.

**Reconstruction bundle** — the completed mesh GLB and its sidecars as a single download. Returns
`202` while the reconstruction or its mesh export is still running, `404` if no GLB was produced.

```bash
curl -O -J "http://127.0.0.1:8000/reconstruction/1/download-bundle"
```

**Checkpoint validation** — scores a finished reconstruction against independently surveyed points,
which is the honest way to measure accuracy (points used for registration cannot also validate it).
Coordinates are in the reconstruction's **local frame**, not lat/lon, and at least one is required.

```bash
curl -X POST http://127.0.0.1:8000/reconstruction/1/validate-checkpoints \
  -H "Content-Type: application/json" \
  -d '{"points": [{"label": "CP1", "x": 12.40, "y": -3.15, "z": 0.87}]}'
```

**GCP list** — converts marked ground control points into a list for downstream tools. Each point
ties a pixel in a named image to a world coordinate, so `image_filename`, `pixel_x`, `pixel_y`,
`longitude` and `latitude` are all required; `altitude_m` and `label` are optional.

```bash
curl -X POST http://127.0.0.1:8000/georeferencing/gcp-list \
  -H "Content-Type: application/json" \
  -d '[{"image_filename": "frame_00042.jpg", "pixel_x": 2011, "pixel_y": 1488,
        "longitude": -81.5, "latitude": 41.1, "altitude_m": 297.4, "label": "GCP1"}]'
```

**Duplicate import check** — advisory only. Flags a folder that looks like an already-imported
session; it never blocks the import, so it is useful as a pre-flight step in a script.

```bash
curl -X POST http://127.0.0.1:8000/uploads/imports/check-duplicate \
  -H "Content-Type: application/json" \
  -d '{"folder_path": "incoming/flight-07"}'
```

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

## ML-assisted defect detection: investigation verdict

No automatic defect-detection workflow is currently available. The Semantic
Labels workflow is **not** a crack, corrosion, water-damage, or missing-material
classifier: its SegFormer-B0 model is trained for ADE20K scene parsing and its
output is deliberately collapsed to the six broad classes above. In particular,
the `structure` label means a scene region is structural; it is not evidence that
the region is defect-free or defective. The model card identifies this checkpoint
as ADE20K `scene_parse_150`, not an aerial-inspection or defect dataset
([model card](https://huggingface.co/nvidia/segformer-b0-finetuned-ade-512-512)).

Use the existing **Review** tab to flag a defect, select one or more supporting
photos, and record category, severity, and notes. Semantic Labels can be used as
an optional scene-context overlay while reviewing, but never to create defect
records automatically or to prioritize a safety decision without operator review.

Before an automatic workflow can ship, a candidate must use a defect-labelled,
representative aerial-inspection dataset and produce a localized candidate plus
confidence for each supported defect class. It is accepted only after an
independent held-out survey validates the agreed per-class precision/recall and
false-negative limits at the intended operating threshold, with every candidate
remaining reviewable in the existing manual workflow. Reject a candidate that
only produces broad scene classes, lacks held-out validation, cannot localize the
defect to source imagery, or cannot expose a threshold/confidence for review.

The next experiment is to collect or license representative, image-level and
defect-localized crack/corrosion examples for one narrowly defined asset type;
write the class definitions and pass/fail metrics before training; then compare a
defect-specific baseline against a held-out flight before proposing any API or UI
automation. This keeps the current manual evidence trail useful whether the
experiment succeeds or is rejected.
