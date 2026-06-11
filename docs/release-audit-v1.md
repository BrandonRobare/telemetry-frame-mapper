# v1.0 Release Audit — 2026-06-11

Full-repo audit of telemetry-frame-mapper at commit `80c90e8`, covering the backend, CLI, frontend, tests, CI, packaging, and documentation. This is the evidence record behind [V1_RELEASE_CHECKLIST.md](../V1_RELEASE_CHECKLIST.md).

**Scope and method.** Three parallel code reviews (backend pipeline, CLI/tests/CI/packaging, frontend/docs), each verifying claims against current source with file:line evidence; the full test suite and linter were executed; the eleven findings (F1–F11) from the 2026-06-05 real-data walkthrough were re-verified one by one against the fix PRs (#94–#102) that landed afterward.

**Headline result.** The codebase is in better shape than its own README claims — 216 passing tests, clean lint, eleven fully implemented frontend tabs, and all nine targeted walkthrough fixes verified in code. But the product's core promise is still unmet: **no gaussian splat is ever produced.** The training step calls a gsplat API that does not exist, and the June fix only made that failure graceful. That, plus packaging/docs debt, defines the release checklist.

---

## 1. Walkthrough findings F1–F11: verification verdicts

| # | Finding (2026-06-05) | Fix PR | Verdict | Evidence |
|---|---|---|---|---|
| F1 | Footprints sized from ASL instead of AGL (~4× oversized) | #98 | **FIXED** | `backend/services/ingest.py` `_extract_xmp_dji()` parses DJI XMP `RelativeAltitude` from the JPEG binary and overrides EXIF `GPSAltitude`; `geometry.py` now receives AGL. |
| F2 | `yaw`/`gimbal_pitch` never read; footprints axis-aligned | #98 | **FIXED** | Same XMP parser extracts `FlightYawDegree`/`GimbalPitchDegree`; `geometry.py` rotates the footprint polygon when yaw is present and sets `heading_estimated=False`. |
| F3 | Ingest double-counts images on case-insensitive filesystems (291 → 582) | #101 | **FIXED** | `ingest_orchestrator.py:27-35` replaced four separate globs with one `iterdir()` pass deduped via `os.path.normcase(str(p.resolve()))`. |
| F4 | Import modal demands an absolute path the backend rejects | #95 | **FIXED** | `ImportModal.tsx:231` label is now "Path inside imports/ folder", placeholder `e.g. 2026-05-02-field-a`. |
| F5 | Import progress poll stops on initial `pending` status, bar freezes | #94 | **FIXED** | `mutations.ts:73-76`: `refetchInterval` now returns `false` only for terminal `done`/`error`, else 1000 ms. |
| F6 | Session Log shows "Invalid Date" | #96 | **FIXED** | Frontend reads the `timestamp` field (was `created_at`); `SessionLogTab.tsx:120` renders `toLocaleString()` with a `—` fallback. Backend column `SessionLogEntry.timestamp` (`models.py:166`) defaults to UTC. |
| F7 | Exports written to `backend/exports/` instead of configured `./exports` | #97 | **FIXED** | `backend/core/config.py:62-68` resolves relative `*_dir` paths against config.yaml's directory, not the process CWD. |
| F8 | Export tab content right-shifted | #102 | **FIXED** | `ExportTab.tsx:273-280` centers content in a 720 px max-width container. |
| F9 | Storage "Data" category measured the whole data/ dir (2.24 GB incl. source MP4s) | #100 | **FIXED** | `storage.py:22-30` `_data_db_size()` measures only `.db/.yaml/.yml/.json` files. |
| F10 | `[reconstruction]` extra missing gsplat/torch | #99 (partial) | **PARTIALLY FIXED → superseded** | The extra now lists `gsplat>=1.5.0` — but that makes it *less* installable, not more: gsplat's sdist requires torch at build time and CUDA torch is not on the default PyPI index. Checklist T6 removes the pin and documents the real two-step install. |
| F11 | Splat training targets a non-existent gsplat API — feature non-functional | #99 (graceful degradation only) | **NOT FIXED (mitigated)** | See section 2. |

## 2. The release blocker: splat training still does not exist

PR #99 wrapped the phantom calls in exception handlers; it did not implement training. Verified in current code:

- `backend/services/reconstruction.py:354` — `from gsplat import train`. The real gsplat package (≥1.5) exports `rasterization`, `rasterization_2dgs`, losses, and densification strategies; **there is no `train` function and never has been.** The import raises, is converted at line 356 to `RuntimeError("gsplat.train is not available…")`, and the pipeline's handler (lines 1353–1362) completes the job as `status="complete", step="colmap_only"`.
- `reconstruction.py:381-383` — `from gsplat import prune_by_opacity` (does not exist) means **LOD generation silently writes nothing**: `_generate_lod` returns paths to preview/medium PLYs that were never created.
- `reconstruction.py:394` — `gsplat.render_nadir` (does not exist): thumbnails always `None`.
- `reconstruction.py:841-843` — `gsplat.render_video` (does not exist): server flythrough always fails to the browser-recording path.

**Consequence:** every reconstruction terminates at the COLMAP sparse cloud. The Splat Viewer, Compare tab, PSNR/SSIM sparklines, LOD streaming, point-cloud colorization from splats, mesh export, and server flythrough are all fully built frontends waiting on a file that is never produced. Installing torch+gsplat does not change this — the called functions don't exist.

**Decision (2026-06-11):** implement a real in-process trainer using `gsplat.rasterization` + `DefaultStrategy` (port of gsplat's `simple_trainer` example). Full design is embedded in checklist tasks T1–T4, with a latent frontend format-detection bug fixed in T5 and install docs in T6.

A related latent bug was found during this audit: `SplatViewerTab.tsx:781-782` loads the splat from a URL ending `?lod=preview` without an explicit `format`; gaussian-splats-3d infers format from the URL suffix, so the viewer would fail on the first real PLY ever produced (checklist T5).

## 3. Test, lint, and code-quality status

- **`pytest`: 216 passed**, 0 failed, 174 warnings, ~14 s. (README claims 31 — stale.)
- **`ruff check .`: clean** (rules E, F, I, UP, B; line length 100).
- **Warnings:** all 174 are `datetime.utcnow()` deprecations from 11 sites — `backend/db/models.py` lines 17, 92, 117, 137, 157, 166, 203, 235, 255; `backend/routers/sessions.py:81`; `tests/backend/test_comparisons_router.py:53` (checklist T8).
- **Backend code health:** no TODO/FIXME debt found; path traversal hardened in `reconstruction.py` (`_safe_export_path`) and `storage.py`; input validation on presets, keyframes, overlaps; errors recorded per job with a 500-char truncation; manual column-add migration shim in `db/database.py` (fine for 1.0, Alembic filed post-1.0).
- **CLI code health:** subprocess calls are argv-only (no shell), missing binaries raise guidance per the release-gates doc. Gaps: `infer_frame_rate` fallback untested; frame-index regex takes the *first* digit group in the filename (`DJI_0081_frame_42.jpg` → index 81, silently mis-timed) — checklist T11.
- **Test distribution:** ~11 CLI tests, ~181 backend tests, plus dashboard/docker-compose tests. Frontend: **2 test files** against 40 source files (checklist T10).

## 4. Frontend feature inventory

All **11 tabs are fully implemented** with loading/error/empty states — none are placeholders, contradicting the README:

Map (Leaflet, footprints, coverage overlay, session sidebar) · GPS Sync (flight-log CSV match/apply) · Review (thumbnails, quality flags, reprojection-error badges, frame selection) · Plan (target-area drawing, lawnmower plan, KML/GPX) · Export (WebODM zip, GeoJSON, LAS, mesh GLB/OBJ/MTL) · Session Log · Reconstruct (presets, target-area crop, job start/polling) · Jobs (resource monitor, job list, logs) · Storage (usage breakdown, file browser) · Splat Viewer (gaussian-splats-3d canvas, sparklines, coverage-gap heatmap, annotations, measurements, ortho/3D split, flythrough recording) · Compare (voxel diff overlay, GeoJSON export).

## 5. Packaging, CI, and infrastructure findings

| Area | Finding | Checklist |
|---|---|---|
| Version metadata | `0.1.0` + `Development Status :: 3 - Alpha` in pyproject; `0.1.0` in `backend/main.py:36` and `src/drone_video_geotagger/__init__.py:3`; `0.0.0` in frontend/package.json | T6 |
| `[reconstruction]` extra | Pins `gsplat>=1.5.0`, which cannot resolve as documented (no CUDA torch on PyPI; gsplat sdist needs torch at build time) | T6 |
| Docker | `docker-compose.yml` references `backend/Dockerfile` and `frontend/Dockerfile`; **neither exists**. Decision: drop Docker for 1.0 | T7 |
| CI | Single Python (3.12) despite 3.10+ support claim; frontend never linted/tested/built in CI | T9 |
| Dev scripts | `dev.sh`/`dev.bat` install from `backend/requirements.txt`, **deleted** by ADR-011 — both scripts fail on fresh clones | T13 |
| Preflight | Missing COLMAP only surfaces when a job fails mid-session; no startup warning, no UI flag | T12 |
| CHANGELOG | None existed (created by this audit, `[Unreleased]` pending T1–T6) | T15 |

## 6. Documentation findings

- **README:** stale on three load-bearing claims — "Map tab + 4 placeholder tabs" (reality: 11 functional), "GPS Sync/Review/Plan/Export … coming soon", "31 tests" (reality: 216). Refreshed by this audit.
- **No end-to-end tutorial** existed for the actual product promise (drone video → splat) → [WORKFLOW.md](WORKFLOW.md) created.
- **No install guide** beyond dev-oriented pip extras → [INSTALL.md](INSTALL.md) created.
- **No troubleshooting doc** despite well-defined failure modes → [TROUBLESHOOTING.md](TROUBLESHOOTING.md) created.
- **No public architecture doc** (good internal ones live in the gitignored vault) → [ARCHITECTURE.md](ARCHITECTURE.md) created.
- `docs/SETUP.md` GPU section described the (now dropped) Docker path and the non-resolvable gsplat extra → rewritten under T6/T7.
- Release mechanics (badges, wiki, community files, `gh release`) already have a reviewed plan at `docs/superpowers/plans/2026-05-20-v1.0.0-release.md`; checklist T15 delegates to it with corrections.

## 7. Repo hygiene

Working tree clean at audit time; `.gitignore` correctly blocks flight data (`*.mp4`, `*.srt`, `*_geotagged/`, `data/`, `imports/`, `processed/`, `exports/`, `.internal/`); no large or sensitive tracked files; no secrets. Dependabot is active and current (PRs #73–#83 merged the week before the audit).

---

*Audit performed with Claude Code. Line anchors valid at commit `80c90e8`; each checklist task carries grep fallbacks for drift.*
