# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased] — targeted at 1.0.0

1.0.0 will be the first tagged release. Remaining work before the tag is tracked task-by-task in [V1_RELEASE_CHECKLIST.md](V1_RELEASE_CHECKLIST.md); headline items are real gaussian-splat training (replacing the non-functional gsplat hook), the Python 1.0.0 version bump, CI hardening, and removal of the broken Docker configuration.

### Added
- **CLI geotagger** (`drone-video-geotagger`): extracts DJI SRT telemetry from MP4 with ffmpeg, interpolates per-frame GPS positions, writes EXIF via ExifTool, produces an audit CSV. WSL-aware path handling.
- **FastAPI backend**: session import with quality scoring (sharpness/brightness), DJI XMP parsing (relative altitude, yaw, gimbal pitch), ground-footprint geometry (UTM/Shapely), coverage analysis, lawnmower mission planning with KML/GPX export, flight-log sync, session log, storage management, and system resource reporting — ~53 endpoints across 17 routers, self-documented at `/docs`.
- **Reconstruction pipeline**: COLMAP SfM orchestration (quick/full presets, target-area crop, manual frame selection), GPS geo-registration (COLMAP↔UTM similarity transform), per-frame reprojection-error reporting, background job management with progress/cancel.
- **React frontend** (11 tabs): Map, GPS Sync, Review, Plan, Export, Session Log, Reconstruct, Jobs, Storage, Splat Viewer (3D canvas, PSNR/SSIM sparklines, coverage-gap heatmap, GPS annotations, distance/area measurement, ortho/3D split view, flythrough recording), and Compare (voxel change detection between flights).
- **Exports**: WebODM package, GeoJSON, LAS 1.4 point cloud with UTM CRS, optional SuGaR mesh (GLB/OBJ/MTL with geo-reference sidecar), browser-recorded or server-rendered flythrough video.
- **Documentation suite** (2026-06-11): end-to-end [workflow tutorial](docs/WORKFLOW.md), [install guide](docs/INSTALL.md), [troubleshooting](docs/TROUBLESHOOTING.md), [architecture overview](docs/ARCHITECTURE.md), [release audit](docs/release-audit-v1.md), and the agent-executable [release checklist](V1_RELEASE_CHECKLIST.md).

### Fixed (1.0 hardening, from the 2026-06-05 real-data walkthrough)
- Footprints were sized from absolute (ASL) altitude instead of height above ground, inflating them ~4×; DJI XMP `RelativeAltitude` is now used (#98).
- Footprints ignored drone heading; yaw is now read from DJI XMP and applied (#98).
- Image import double-counted every file on case-insensitive filesystems (#101).
- Import progress polling stopped permanently when the first poll returned `pending` (#94).
- Import modal asked for an absolute path the backend (correctly) rejects; it now asks for a path relative to `imports/` (#95).
- Session Log rendered "Invalid Date" (#96).
- Plan exports landed in `backend/exports/` instead of the configured `./exports` (#97).
- Export tab layout was right-shifted (#102); Storage "Data" category measured the entire data directory instead of the database and config (#100).
- Reconstruction jobs crashed outright when gsplat was absent; they now complete with the COLMAP sparse cloud (`colmap_only`) and clear guidance (#99). *(Real splat training lands with checklist T1–T6.)*
- CodeQL path-injection findings hardened across import, export, and storage endpoints.

### Security
- All external tools (ffmpeg, exiftool, COLMAP) invoked as argv lists — no shell.
- Import/export/storage paths validated against traversal; imports constrained under `imports/`.
