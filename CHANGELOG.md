# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/).


## [1.2.0] — Unreleased

### Added
- **Semantic Splats** (#331): per-gaussian class labels (ground / vegetation / structure / vehicle / water / other) stored in an atomic NPZ sidecar that never mutates `splat.ply`. Produced by an opt-in background job using a GPU segmentation pipeline (SegFormer-B0/ADE20K → multi-view opacity-weighted vote with gsplat expected-depth rasterization).
  - `prune_order` extracted from `ply_io.prune_by_opacity` so LOD subsets and label arrays stay index-aligned (#334).
  - Lazy `[semantic]` extra (`transformers>=4.48`, `safetensors`) with runtime gating via `/system/resources` `semantic_labeling` workflow (#335).
  - Pure-NumPy voting core (`project_to_view`, `visibility_mask`, `accumulate_votes`, `finalize_labels`), background job runner, atomic NPZ sidecar write, 3 DB columns + Alembic migration, and REST routes for status / summary / binary overlay (#336).
  - Viewer class overlay in the Splat Viewer tab with per-class Three.js `Points` groups, legend chips, and filter toggles (#337).
  - LAS 1.4 / LAZ point-cloud exports now carry real ASPRS classification codes (ground→2, vegetation→5, structure→6, water→9, vehicle→1, other→1, unlabeled→0) when a semantic sidecar is present (#338).
  - GPU smoke-guide micro-check (`render_mode="ED"`) in `docs/SETUP.md` and a quality-expectations section in the user manual documenting the ADE20K aerial domain gap (#339).

## [1.0.0] — 2026-06-14

First stable release: a complete drone video → gaussian-splat pipeline. The headline of the 1.0 cycle was replacing a non-functional gsplat hook with a real in-process trainer, validated end-to-end on GPU hardware (PSNR 27.5 / SSIM 0.79 on a full-preset run).

### Added
- **CLI geotagger** (`drone-video-geotagger`): extracts DJI SRT telemetry from MP4 with ffmpeg, interpolates per-frame GPS positions, writes EXIF via ExifTool, produces an audit CSV. WSL-aware path handling.
- **FastAPI backend**: session import with quality scoring (sharpness/brightness), DJI XMP parsing (relative altitude, yaw, gimbal pitch), ground-footprint geometry (UTM/Shapely), coverage analysis, lawnmower mission planning with KML/GPX export, flight-log sync, session log, storage management, and system resource reporting — 77 endpoints across 19 routers, self-documented at `/docs`.
- **Reconstruction pipeline**: COLMAP SfM orchestration (quick/full presets, target-area crop, manual frame selection), GPS geo-registration (COLMAP↔UTM similarity transform), per-frame reprojection-error reporting, background job management with progress/cancel.
- **React frontend** (13 tabs): Overview, Map, GPS Sync, Review, Plan, Export, Session Log, Reconstruct, Jobs, Storage, Splat Viewer (3D canvas, PSNR/SSIM sparklines, coverage-gap heatmap, GPS annotations, distance/area measurement, ortho/3D split view, flythrough recording), Compare (voxel change detection between flights), and Settings.
- **Exports**: WebODM georeferencing CSV-only zip, GeoJSON, LAS 1.4 point cloud with UTM CRS, optional SuGaR mesh (GLB/OBJ/MTL with geo-reference sidecar), browser-recorded or server-rendered flythrough video.
- **Documentation suite**: a [user manual](docs/USER-MANUAL.md), end-to-end [workflow tutorial](docs/WORKFLOW.md), [install guide](docs/INSTALL.md), [GPU setup](docs/SETUP.md), [troubleshooting](docs/TROUBLESHOOTING.md), and [architecture overview](docs/ARCHITECTURE.md).

### Added (real reconstruction — the 1.0 headline)
- **In-process gaussian-splat trainer** on `gsplat.rasterization`, replacing the phantom `gsplat.train` API that made splat training impossible. Sparse-cloud initialization, per-attribute Adam, `DefaultStrategy` densification with a VRAM-aware max-gaussian cap, pure-torch SSIM loss, SH-degree warmup, and INRIA-layout PLY export. New stdlib+numpy modules `colmap_io` (sparse-model loader) and `ply_io` (3DGS PLY read/write/prune) underpin it; none of torch/gsplat are required to import the backend.
- **GPU thumbnail and server-side flythrough renderers** (best-effort; browser recording remains the primary flythrough path).
- **Backend startup preflight**: a missing COLMAP binary logs a warning at launch, and `/system/resources` reports `colmap_available` / `gsplat_available`.
- **GPU install guide** ([docs/SETUP.md](docs/SETUP.md)) verified on Windows / CUDA 13.2 / RTX 3050 Ti, including the torch/gsplat version pins and build workarounds.

### Changed
- Version bumped to 1.0.0 across the package, API, and frontend; classifier set to Production/Stable.
- The `reconstruction` extra no longer pins gsplat (no resolvable CUDA wheel exists); GPU training is a documented manual install.
- CLI frame index is now read from the **last** number in a filename, so prefixed names like `DJI_0081_frame_42.jpg` time correctly.
- CI runs a Python 3.11/3.12 matrix plus a frontend lint/test/build job.

### Removed
- Broken legacy Docker Compose files (`docker-compose.yml` referenced Dockerfiles that never existed). A supported single-container Dockerfile was added after 1.0 and is covered by CI build smoke.

### Fixed
- Mid-training cancellation now marks the job failed instead of mislabeling it a successful `colmap_only` completion.
- All `datetime.utcnow()` deprecation warnings (Python 3.12+) eliminated.
- Splat viewer no longer hangs on load where `SharedArrayBuffer` is unavailable.
- `dev.sh` / `dev.bat` repaired for the pyproject-extras layout.

### Fixed (1.0 hardening, from the 2026-06-05 real-data walkthrough)
- Footprints were sized from absolute (ASL) altitude instead of height above ground, inflating them ~4×; DJI XMP `RelativeAltitude` is now used (#98).
- Footprints ignored drone heading; yaw is now read from DJI XMP and applied (#98).
- Image import double-counted every file on case-insensitive filesystems (#101).
- Import progress polling stopped permanently when the first poll returned `pending` (#94).
- Import modal asked for an absolute path the backend (correctly) rejects; it now asks for a path relative to `imports/` (#95).
- Session Log rendered "Invalid Date" (#96).
- Plan exports landed in `backend/exports/` instead of the configured `./exports` (#97).
- Export tab layout was right-shifted (#102); Storage "Data" category measured the entire data directory instead of the database and config (#100).
- Reconstruction jobs crashed outright when gsplat was absent; they now complete with the COLMAP sparse cloud (`colmap_only`) and clear guidance (#99). *(With gsplat installed, real splat training now runs — see "real reconstruction" above.)*
- CodeQL path-injection findings hardened across import, export, and storage endpoints.

### Security
- All external tools (ffmpeg, exiftool, COLMAP) invoked as argv lists — no shell.
- Import/export/storage paths validated against traversal; imports constrained under `imports/`.
