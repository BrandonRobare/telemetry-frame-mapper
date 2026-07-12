# End-to-End Workflow: DJI Drone Video → Gaussian Splat

This walks the full pipeline on real data: extract frames from a DJI flight video, geotag them from the embedded telemetry, import them into the web app, review coverage and quality, run a 3D reconstruction, and view/export the result.

> **Note.** The full pipeline is functional. Gaussian-splat **training** (the second half of step 6) needs torch + gsplat and a CUDA GPU installed (see [SETUP.md](SETUP.md)); without them, reconstructions complete in `colmap_only` mode — a sparse point cloud with no splat — and everything else still works.

**Prerequisites:** everything in [INSTALL.md](INSTALL.md) — at minimum Python 3.10+, Node 18+, `ffmpeg`, `exiftool`; plus COLMAP and an NVIDIA GPU for reconstruction. When anything fails, check [TROUBLESHOOTING.md](TROUBLESHOOTING.md) first — most errors in this pipeline are missing-binary or path-rule issues with exact known fixes.

---

## 1. Extract frames from the flight video

DJI MP4s embed GPS telemetry as a subtitle track, but frames you extract from the video carry no location data. Extract frames first:

```bash
ffmpeg -i DJI_0081.MP4 -vf fps=2 frames/frame_%05d.jpg
```

`fps=2` (two frames per second) is a good default for mapping flights — enough overlap for reconstruction without thousands of near-duplicate images. A 146-second 4K flight yields ~291 frames.

> Frame filenames must contain the frame number — the geotagger reads the **last** number in each filename as the frame index (`frame_00042.jpg` → 42).

## 2. Geotag the frames (CLI)

```bash
drone-video-geotagger \
  --video DJI_0081.MP4 \
  --frames frames \
  --takeoff-altitude 334.0
```

- `--takeoff-altitude` is the launch point's elevation in **meters above sea level** (find it on a topo map or your flight log). DJI telemetry stores altitude relative to takeoff; the CLI adds the two so the EXIF carries absolute altitude, while DJI XMP relative altitude drives footprint sizing later.
- The SRT telemetry is extracted from the video automatically. If you already have it, pass `--srt flight.srt`; if you know the extraction rate, pass `--frame-rate 2` (otherwise it is estimated from the telemetry duration).
- After parsing the telemetry the CLI checks for signs of a weak or missing GPS lock — points stuck at (0, 0), coordinates frozen across many consecutive points, implausible position jumps — and prints a `WARNING:` line to stderr for each finding. Tagging still proceeds; treat the warnings as a prompt to inspect `frame_geotags.csv` before importing.
- Add `--in-place` to tag the original frames instead of writing copies.

Outputs, in `frames_geotagged/` by default:
- the geotagged JPGs,
- `frame_geotags.csv` — per-frame index, time offset, lat/lon, relative + absolute altitude, timestamp (inspect this to sanity-check the alignment before importing),
- `exiftool_geotags.args` — the generated ExifTool argument file (useful for debugging tag values).

At this point the frames already work in WebODM/OpenDroneMap, which reads GPS EXIF on import. The rest of this workflow uses this project's own web app.

## 3. Start the web app

From the repo root, in two terminals:

```bash
uvicorn backend.main:app --reload          # API on http://localhost:8000 (docs at /docs)
cd frontend && npm run dev                 # UI on  http://localhost:5173
```

The backend creates `data/drone_mapping.db` (SQLite) on first run. Start it from the repo root so `config.yaml` and the `processed/` static mount resolve correctly.

## 4. Import a session

1. Move or copy your geotagged folder **under the repo's `imports/` directory**, e.g. `imports/2026-06-11-tower-site/`.
2. In the UI, open the import modal and enter the path **relative to `imports/`** — just `2026-06-11-tower-site`. Absolute paths and `..` are rejected by design (path-traversal hardening).
3. The progress bar polls until done; the session then appears in the sidebar.

During import the backend reads GPS EXIF and DJI XMP (relative altitude, yaw, gimbal pitch), scores each image for sharpness/brightness, computes ground footprints, and generates thumbnails.

When the import finishes, the modal shows a Quick QA card. Alongside completeness and blur checks it runs GPS-lock heuristics over the imported coordinates: frames stuck at (0, 0), coordinates frozen across many consecutive frames, and implausible position jumps all produce warnings. If any appear, re-check the flight's GPS quality (or sync a flight log in the GPS Sync tab) before reconstructing.

## 5. Review on the map, plan, and flag

- **Map tab** — footprint polygons and the coverage overlay on ESRI satellite imagery. The sidebar shows session stats, coverage %, quality flags, and editable session tags and operator notes; "Run Coverage Analysis" recomputes coverage. The session picker in the top bar can filter by tag.
- **Review tab** — thumbnail grid; cycle per-image flags (good / blurry / no_gps / dark / bright), and toggle which frames feed reconstruction. After a reconstruction has run, per-frame COLMAP reprojection-error badges appear here — sort by them to find weak frames.
- **Plan tab** — draw a target-area polygon, set altitude/overlap, generate a lawnmower flight plan, export KML/GPX (written under `exports/`). The Shutter Interval panel converts the current altitude/overlap plus a flight speed and camera preset into the photo spacing (m) and timed-shot interval (s) to dial into the DJI controller, and warns when the interval drops below the ~2 s DJI minimum. The Weather Advisor panel fetches the current + next few hours' forecast for the drawn area from Open-Meteo (no API key needed) and shows a GO / CAUTION / NO-GO signal based on sustained wind, gusts, precipitation chance, and temperature — it lists the specific factor(s) driving the verdict, and reports "weather unavailable" instead of failing if the request can't complete (e.g. offline).
- **GPS Sync tab** — optionally match a DJI FlightRecord CSV against the session to refine timestamps.

## 6. Reconstruct: COLMAP → gaussian splat

**Reconstruct tab** → pick a preset → Start.

| Preset | Iterations | Intended use |
|---|---|---|
| `quick` | 1 000 | sanity check, small frame subsets, CPU-feasible COLMAP |
| `full` | 30 000 | final quality; expect hours, GPU required for training |

Optional: crop to a drawn target area, or use the Review tab's frame selection to limit input frames.

The job pipeline (watch it in the **Jobs tab**, which also shows CPU/RAM/GPU/VRAM):

1. `running_colmap` (0–95 %): feature extraction → matching → sparse mapping. CPU-heavy; ~4 min for 40 4K frames on a typical desktop, much longer for hundreds of frames.
2. `running_gsplat` (95–100 %): gaussian-splat training on the COLMAP poses *(requires the T1–T6 trainer plus the GPU setup in [SETUP.md](SETUP.md))*. Produces `exports/{id}/splat.ply` plus 10 % / 50 % LOD variants and a nadir thumbnail.
3. `complete` — or `complete / colmap_only` if training dependencies are absent (you still get the sparse cloud, LAS export, and coverage gaps; the splat-specific features stay empty).

If a job fails, the Jobs tab's log panel has the stage-specific error; match it against [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

When a job finishes (complete, failed, or cancelled) the app shows a toast from any tab, so you don't have to sit on the Jobs tab. If you grant the browser's notification permission (the app asks once, while a job is running), a desktop notification also fires when the tab is in the background.

## 7. View the splat

**Splat Viewer tab** (needs a `complete` reconstruction with a splat):
- streams the preview LOD into an interactive 3D canvas; PSNR/SSIM training sparklines in the sidebar,
- GPS-pinned annotations (exportable as GeoJSON), distance/area measurement tools, ortho/3D split view synced with the Leaflet map,
- coverage-gap heatmap overlay showing under-observed regions — use it to plan a re-fly,
- flythrough: set keyframes, preview, and record in-browser (WebM) or request a server-rendered MP4.

## 8. Export

**Export tab:**
- **WebODM georeferencing CSV** — zip containing only `odm_georeferencing.csv` for ODM processing,
- **GeoJSON** — frame positions/footprints,
- **Point cloud (LAS 1.4)** — from the COLMAP sparse model, colorized from the splat when present, UTM CRS embedded,
- **Mesh (GLB/OBJ/MTL)** — optional, requires a manual [SuGaR](https://github.com/Anttwo/SuGaR) install (not on PyPI); always writes `mesh_georef.json` so the mesh keeps its UTM transform.

**Compare tab** — after a second flight of the same site, run voxel change detection between two reconstructions: green = new, red = removed, exportable as GeoJSON.

---

## Quick reference: one site, end to end

```bash
ffmpeg -i DJI_0081.MP4 -vf fps=2 frames/frame_%05d.jpg
drone-video-geotagger --video DJI_0081.MP4 --frames frames --takeoff-altitude 334.0
mv frames_geotagged imports/tower-site
uvicorn backend.main:app --reload   # terminal 1
cd frontend && npm run dev          # terminal 2
# UI: import "tower-site" → Review → Reconstruct (quick) → Splat Viewer → Export
```
