# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/).


## [2.0.0] — 2026-07-27

1.0 shipped a working pipeline for one operator on one machine. 2.0 turns it into a platform: multi-project workspaces, authentication and share links, a crash-safe job queue that can dispatch to a remote GPU worker, first-class GIS/3D export formats, and a headless CLI that runs the whole video → splat pipeline with no UI. 121 issues across seven milestones.

The major bump is driven by the platform surface rather than by API removals; the only hard break is the Python floor (3.10 → 3.11).

### Breaking
- **Python 3.10 is no longer supported.** `requires-python` is now `>=3.11` (3.10 reaches end of life in October 2026). `pyproj` is pinned to `>=3.7.2` as part of the same bump (#533).
- The WebODM export is named for what it is — georeferencing CSV only — rather than implying a full ODM package (#196). The complete package export with an options manifest is the separate `POST /export/webodm-package` route (#207).

### Added

#### Platform
- **Multi-project workspaces** (#302): sessions, reconstructions, and exports are scoped to a project, with project switching in the UI and project-scoped API routes.
- **Persistent, crash-safe job queue** (#306): jobs survive a backend restart, with atomic claim semantics and a stale-job reaper.
- **Remote/networked GPU worker** (#378): dispatch COLMAP and splat training to a separate GPU host over HTTP, with progress polling and artifact retrieval.
- **API keys for automation** (#409) and **single-user PIN lock** (#412) for LAN-exposed instances; **self-hosted share links** with expiry and access control (#376) and **public read-only splat-viewer share links** (#301).
- **Config-driven deployment profile** (#410): a `deployment:` block in `config.yaml` sets bind host/port, the CORS allowlist, and trusted hosts, validated at startup. Binding a non-loopback host with neither `pin_lock` nor `api_key` enabled is refused outright unless `allow_unauthenticated_lan` is set.
- **Prometheus metrics** at `/metrics` (#411) and **structured logging with rotation** (#399).
- **Windows installer** (#398): a packaged one-click install for the backend, frontend, and external binary checks.

#### Reconstruction
- **Headless full-pipeline CLI** `dvg-pipeline` (#304): video → geotagged frames → COLMAP → splat, no browser required.
- **ODM alternative reconstruction backend** (#385) and **WebODM API round-trip integration** (#377).
- **COLMAP 4.x modernization** (#340): `spatial_matcher` + `global_mapper` paths where available, with automatic fallback.
- **Semantic Splats** (#331): per-gaussian class labels (ground / vegetation / structure / vehicle / water / other) stored in an atomic NPZ sidecar that never mutates `splat.ply`. Produced by an opt-in background job using a GPU segmentation pipeline (SegFormer-B0/ADE20K → multi-view opacity-weighted vote with gsplat expected-depth rasterization).
  - `prune_order` extracted from `ply_io.prune_by_opacity` so LOD subsets and label arrays stay index-aligned (#334).
  - Lazy `[semantic]` extra (`transformers>=4.48`, `safetensors`) with runtime gating via `/system/resources` `semantic_labeling` workflow (#335).
  - Pure-NumPy voting core (`project_to_view`, `visibility_mask`, `accumulate_votes`, `finalize_labels`), background job runner, atomic NPZ sidecar write, 3 DB columns + Alembic migration, and REST routes for status / summary / binary overlay (#336).
  - Viewer class overlay in the Splat Viewer tab with per-class Three.js `Points` groups, legend chips, and filter toggles (#337).
  - LAS 1.4 / LAZ point-cloud exports now carry real ASPRS classification codes (ground→2, vegetation→5, structure→6, water→9, vehicle→1, other→1, unlabeled→0) when a semantic sidecar is present (#338).
  - GPU smoke-guide micro-check (`render_mode="ED"`) in `docs/SETUP.md` and a quality-expectations section in the user manual documenting the ADE20K aerial domain gap (#339).
- **Reconstruction versioning and re-run lineage** (#372), **multi-flight session merging** into one reconstruction (#288), and **auto re-run with denser frame sampling** over weak-registration areas (#366).
- **Splat cleanup + compression** via `splat-transform` (#341), **outlier/floater cleanup pass** (#293), and **web-optimized export presets** (#365).
- Pre-run quality gates: **preflight dataset quality report** (#206), **feature-matching preflight diagnostics** with a weak-texture warning (#299), **reconstruction diagnostics and fix suggestions** (#205), and a **post-hoc quality scorecard** (#292).
- **Camera/lens calibration profiles** with COLMAP camera suggestions (#211) and a **self-calibration drift report** (#386).

#### Accuracy & measurement
- **GCP / RTK / PPK workflow support** (#204) with a **GCP accuracy report** (RMSE against surveyed control points, #287) and **held-out checkpoint validation** (#294). Pix4D/DroneDeploy GCP file formats are read and written (#395).
- **Volume / cut-fill calculation** on measurement polygons (#286), **cross-section and elevation-profile tools** in the splat viewer (#295), **persisted measurements** with CSV/GeoJSON export (#368), and a **slope heatmap overlay** (#389).
- **Terrain elevation service (DEM)** for planning and footprints (#296), **terrain-following altitude** in mission plans (#297), and **AGL-correct footprints and coverage on sloped terrain** (#298).
- **Upgraded change detection** with alignment and exportable deltas (#209) and **multi-temporal change-trend tracking** across site flights (#367).
- **3–4-up synced comparison grid** for reviewing flights side by side (#404).
- **Shadow / lighting-consistency flagging** (#402).

#### Export formats
- **GeoTIFF orthomosaic** (#305), **DEM/DSM raster** (#374), **GeoPackage multi-layer** (#396), **LAZ compressed point cloud** via `laspy[lazrs]` (#342), and **USD / glTF with georeferencing metadata** (#406).
- **Real Cesium 3D Tiles export** (#373) with **Cesium ion upload** (#408); **Potree export** (#394); **WMS/WMTS tile endpoint** (#397).
- **QGIS/ArcGIS project-file generator** (#375) and a **PDF survey report generator** (#300).
- **Reproducibility manifest** for imports, reconstructions, and exports (#214).

#### Field operations
- **Mobile quick-check PWA view** (#364), **field checklist tab** (#383), and **presentation / narration mode** (#388).
- **Weather / wind go-no-go advisor** on the Plan tab (#362), **RTH / obstacle sanity check** (#382), and a **shutter-interval / overlap calculator** for the DJI controller (#363).
- **GPS-lock heuristic warning on import** (#384), **live coverage-gap overlay during import** (#361), and a **post-landing rapid QA summary card** (#285).
- **One-click re-fly plan generated from coverage gaps** (#289), **multi-battery flight segmentation** (#290), and a **pre-flight lawnmower plan validator** (#291).
- **Defect-flagging categories with linked photos** (#387) and **ML defect detection** (#403).
- **Job-completion desktop/toast notifications** (#380) and a **battery/flight metadata tracker** (#401).

#### Ingest & data management
- **Browser upload / drag-drop import** (#213) with persisted upload state (#282); **SD-card watch-and-auto-import folder** (#371) and an **imports folder watcher** (#400); **cloud-drive import sources** (#405); **DroneDeploy/Pix4D project import** (#407).
- **DJI flight-log import** (IMU / gimbal / battery via a `pydjirecord` subprocess wrapper, #343) and **Autel / Parrot / ArduPilot telemetry parsers** (#379). Encrypted v13+ logs require a DJI developer API key.
- **Session archive/restore bundle** for machine moves (#370), **artifact backup** to an external drive or rclone remote (#381), **scheduled SQLite/config backup** (#393), and a **disk-space lifecycle policy / auto-archive** (#303).
- **Cross-session search** (#390), **bulk session operations** (#391), **duplicate-import detection** (#392), and **session tagging with free-text notes** (#369).
- **External binary and GPU health dashboard** (#212) and **configurable basemaps with offline map support** (#215).
- Enhanced **flight-log sync** with offset tuning and interpolation (#210); broader **DJI XMP** (#191) and **DJI SRT** (#200) format coverage.

### Changed
- Frontend: Button and Badge usage consolidated across every tab (#234), phone-sized responsive layout reworked (#235), and the remaining UI primitives brought in line with the warm-light redesign (#236).
- CI runs a Python 3.11/3.12 matrix; Dependabot PRs are grouped and duplicate CI runs de-duplicated (#530).
- Frame-rate handling: `infer_frame_rate` now fails with a gap summary and tells you to re-run with `--frame-rate` set to the extraction rate, rather than silently inferring a wrong rate (#199, #268).
- Frontend bundle size reduced and the ineffective dynamic-import warning resolved (#202).
- Documentation restructured: README, `docs/ARCHITECTURE.md`, and `docs/USER-MANUAL.md` refreshed for accurate counts and current feature coverage (#280, #508).

### Fixed

#### Georeferencing & geometry
- **Georeferencing was never actually computed** — a placeholder identity transform was stored and reported as a real geo-transform. Now solved as a true COLMAP→UTM similarity transform (Umeyama) (#496).
- Coverage area was computed in square degrees but stored as `covered_area_m2` (#309).
- Footprints ignored gimbal pitch, treating every shot as nadir (#310); `GPSAltitudeRef` was ignored on JPEG import (#188); footprints were skipped for valid zero-valued coordinates (#190) and were not recomputed after flight-log GPS sync (#189).
- Lawnmower lane spacing lacked a `cos(latitude)` term — lanes were ~29% too tight at 45°N (#311). Mission-plan `total_distance_m` omitted inter-lane transit legs (#313).
- `run_coverage` never produced `overlap_geojson` despite full downstream plumbing (#312).
- Splat-viewer raycasting used a fixed Y=0 ground plane, misplacing annotations (#273); annotation and measurement tools were fully disabled whenever the UTM zone was unknown (#272).

#### Reconstruction pipeline
- Reconstruction cancel was broken end-to-end (#262): the tab called no real endpoint (#263), no dedicated cancel endpoint existed as distinct from delete (#264), artifacts were deleted while the pipeline thread was still running (#265), and the COLMAP-phase kill machinery was never wired up, making cancel a no-op during the longest phase (#505).
- The COLMAP workspace was keyed by session ID and never cleared between runs, leaking state across reconstructions (#318); `_run_colmap` hardcoded `sparse/0` and ignored disconnected sub-models (#319); `_count_registered_images` miscounted images with zero 2D points (#317).
- The SSE status stream held a DB connection per client for the entire reconstruction (#320).
- Semantic Splats: the ADE20K lookup table was keyed to the wrong class ids and CUDA loading crashed on an invalid `torch_dtype` (#498).
- One transient poll error failed a remote reconstruction job and orphaned the remote compute (#501).
- Job queue: claim was non-atomic and the startup stale-reaper was unsafe with multiple workers; a restart orphaned in-flight remote jobs (#502).
- `Reconstruction.duration_s` was a dead column, now populated (#275).

#### Import & CLI
- A single malformed EXIF GPS rational (zero denominator) aborted an entire session import (#506).
- The import modal polled forever when the backend restarted mid-import (#507); server-side import errors are now surfaced with detail (#197).
- Elevation export allocated an unbounded raster for small `resolution_m` values and OOM'd the server (#499).
- `collect_frames` sorted by filename text, breaking gap detection and frame-rate inference (#268); `.jpeg`/`.JPG` frames were rejected (#198).
- `read_video_start` silently dropped `creation_time` values without a trailing `Z`, skipping every EXIF timestamp (#270).
- The exiftool args file was written without UTF-8, crashing on non-ASCII frame paths on Windows (#503), and dash-prefixed path lines were not guarded (#276).

#### Data integrity & UI
- SQLite foreign keys were never enabled, so `passive_deletes` orphaned `session_frame_selections` rows (#267). Duplicate column shims between migrations 0001 and 0002 were consolidated (#277).
- Export tab: the Coverage row was hardcoded to `N/A` (#279); a stale WebODM export result persisted after switching sessions (#316).
- The Map tab's "Run coverage analysis" button was dead — wrong method, missing parameter, swallowed error (#497).
- Flythrough recording was never torn down on unmount or reconstruction switch (#314); the Leaflet map never re-fit bounds when switching sessions (#315).
- Storage by-session drill-down was a stubbed API field (#307); the storage summary cache was not invalidated when files changed (#284).
- `ErrorBoundary` gained a reset/retry path (#283); the `window.setSession` dev helper is gated out of production bundles (#278).
- Thumbnail URLs were invalid when `processed_dir` was absolute (#201); FastAPI error details now render cleanly in the frontend API client (#203); WebODM exports honor the configured `exports_dir` (#195).
- The test suite is portable across timezones and on Windows (#274).

### Security
- Closed an unauthenticated file read/write chain in session restore (#535).
- `POST /sessions/restore` rglob-walked the entire data root on every call — a threadpool denial of service (#500).
- The reproducibility-manifest endpoint could probe and hash arbitrary files (#269).
- Auth hardening: lockout on repeated PIN/share unlock attempts, and LAN bind is now coupled to auth being enabled (#504).
- Settings storage-path guards were bypassable with POSIX-style roots on Windows (#266) and did not cover unsafe filesystem locations generally (#194).
- Upload size limits are enforced before reading flight logs (#192) and SRT files (#193) into memory.
- Coverage-gaps caching hygiene: cache rooted under `exports_dir`, private import removed, commit guarded (#271).

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
