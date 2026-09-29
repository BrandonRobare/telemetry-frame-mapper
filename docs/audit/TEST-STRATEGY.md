# Test strategy: levels, coverage areas and CI lanes

This document answers three questions raised by the audit: which kinds of tests the project needs (unit through end-to-end plus full coverage runs), how to split them by coverage area so a pull request only runs what it touches, and which tests to create or update for each audit fix. Work items for it live in [M2 · Test Strategy & CI Split](M2-test-strategy-and-ci.md).

## 1. Where we are (measured 2026-09-29 on `main` @ `3ec2135`)

| Signal | Value |
|---|---|
| Python tests | 123 files · 1,387 passed · 39 skipped · ~52 s locally (slowest test 10.3 s) |
| Python line coverage (pytest-cov) | **84.1%** of 14,144 statements |
| Frontend tests | 60 Vitest files (18 use React Testing Library; 14 of those use `fireEvent`, and `@testing-library/user-event` is not installed) |
| Frontend coverage (Vitest v8) | **49.58% lines / 41.34% branches** of files loaded by tests; 59 of 126 units never loaded |
| End-to-end tests | none |
| API contract tests | none (this audit's route matcher found the survey-report GET/POST mismatch) |
| Migration upgrade tests | v2.0.2 snapshot -> head (columns + FK indexes); no v1.x snapshot, no FK/type diff |
| CI on every PR | Python 3.11 + 3.12 full suite, frontend lint/test/build/audit, Docker build + smoke, wheel, Windows packaging, macOS (brew tools + full suite + bundle). No path filters, no coverage, most jobs without `timeout-minutes`. |

Python coverage by area (line %):

| Area | Lines covered |
|---|---|
| coverage-planning | 78.9% |
| db-migrations | 81.6% |
| export-share | 81.5% |
| flight-log-gps | 94.4% |
| geotag-cli | 91.5% |
| ingest-import | 91.2% |
| platform-ops | 85.5% |
| reconstruction-splat | 81.6% |

Frontend coverage by folder (line %, files loaded by tests only):

| Folder | Lines covered |
|---|---|
| app | 57.7% |
| features/checklist | 92.1% |
| features/compare | 80.5% |
| features/export | 100.0% |
| features/gps-sync | 81.2% |
| features/hero | 0.0% |
| features/import | 33.8% |
| features/jobs | 84.7% |
| features/map | 71.1% |
| features/mobile | 32.6% |
| features/overview | 0.0% |
| features/plan | 81.8% |
| features/reconstruct | 51.7% |
| features/review | 41.9% |
| features/session-log | 83.7% |
| features/sessions | 35.9% |
| features/settings | 87.0% |
| features/share | 0.0% |
| features/splat | 21.6% |
| features/storage | 62.5% |
| shared | 63.7% |

Folder percentages only count files some test imports: `features/export` shows 100% because only `coverageSummary.ts` is loaded, while `ExportTab.tsx` (913 lines) never is. With `coverage.all` enabled the frontend total will drop, which is why the initial threshold below is set from the measured number and the untested-unit list in `report.html` is tracked separately.

The lowest-covered backend files are the tiles router (35.7%), terrain (50%), reproducibility_manifest (50.3%), cuda_gsplat (56.4%), splat_cleanup (57.5%) and quality_report (59.8%). The last two hold this audit's coordinate-frame and silent-failure findings, which argues for thresholds per area rather than one global number.

## 2. Test levels

| Level | Tooling / selector | What it covers | Runs on | Budget |
|---|---|---|---|---|
| **unit** | pytest `-m unit`; Vitest project `unit` (environment `node`, `*.test.ts`) | One function/class/hook in isolation. No DB, no network, no subprocess, no real filesystem beyond `tmp_path`. External tools mocked (ARCHITECTURE.md design rule). | PR (affected areas), main, nightly | < 60 s for the whole Python unit set; < 20 s frontend |
| **integration** | pytest `-m integration` (TestClient + temp SQLite + `tmp_path`) | A router or service together with the DB, migrations and filesystem; COLMAP/ffmpeg/exiftool replaced by argv-level fakes. | PR (affected areas), main, nightly | < 3 min per area |
| **component** | Vitest project `component` (jsdom, React Testing Library, user-event, MSW/fetch mock) | One React component or tab with its hooks and stores, driven the way a user drives it; network mocked at fetch level. | PR (affected feature folders + frontend-shared), main, nightly | < 2 min |
| **contract** | pytest `-m contract` | Cross-boundary agreements: frontend URL+method vs OpenAPI, generated TS types vs `app.openapi()`, migration upgrade + `compare_metadata`, CSV/GeoJSON export schemas, CLI wheel entry points, launcher/Docker/CI supply-chain rules. | PR whenever either side of the contract changes (routers, frontend api/features, db, packaging); always on main and nightly | < 1 min |
| **e2e** | Playwright (`e2e/`), Chromium, against the Docker image or `python -m backend` + built SPA with fake COLMAP/ffmpeg/exiftool on PATH | Operator journeys through the real UI and API: import -> map -> review -> reconstruct (fake) -> splat -> export/share. | nightly, push to main, release; PRs with label `run-e2e` | < 10 min |
| **perf** | pytest `-m perf` (pytest-benchmark or timing budget asserts) | Scaling budgets for the O(n^2) paths fixed in M4 and query-count assertions for N+1 fixes (query-count tests also run as integration). | nightly | < 10 min |
| **platform / hardware** | existing CI jobs: Windows packaging, macOS packaging, Docker smoke, CUDA/Metal dispatch jobs | Packaging and real-accelerator behaviour. | PR only when packaging-release paths change (or label `run-packaging`); main, nightly, release; hardware jobs stay owner-dispatched | as today |

**Full coverage run:** nightly (`schedule`), every push to `main`, and every release tag run all levels on all areas with `--cov-branch` and Vitest `coverage.all`, merge the reports, enforce per-area thresholds, and upload HTML/XML artifacts. PRs report diff coverage for touched areas.

## 3. Coverage areas and path map

Each area owns backend paths, frontend paths and its tests. The CI `changes` job maps changed paths to areas; PRs run unit + integration (+ component) for the affected areas and the contract lane when either side of a contract changed. Changes to shared foundations fan out: `backend/core/**`, `backend/db/models.py`, `tests/conftest.py` -> all Python areas; `frontend-shared` -> all frontend feature folders; `pyproject.toml`, `uv.lock`, `frontend/package-lock.json`, `.github/workflows/**` -> everything.

| Area | Scope | Backend / CLI paths | Frontend paths | Tests |
|---|---|---|---|---|
| `geotag-cli` | Video-frame geotagging CLI and headless pipeline | `src/drone_video_geotagger/**`<br>`tests/cli/**` | — | `tests/cli` |
| `ingest-import` | Import, uploads, EXIF, quality scoring, bundles, merge | `backend/services/{ingest,ingest_orchestrator,upload_reader,auto_import,quality,duplicate_detection,session_bundle,session_merge}.py`<br>`backend/routers/{uploads,sessions,images,auto_import}.py` | `frontend/src/features/{import,sessions,review}/**` | `tests/backend/test_{ingest*,upload*,auto_import,quality,duplicate_detection,session_*,sessions_router,images_router,api_sessions}.py` |
| `flight-log-gps` | Flight logs, DJI parsing, SRT, GPS sync, flight entries | `backend/services/{flight_log_sync,dji_log_parser}.py`<br>`backend/routers/{flight_log,flight_entries,srt}.py` | `frontend/src/features/{gps-sync,session-log}/**` | `tests/backend/test_{flight_*,dji_log_parser,srt_router}.py` |
| `coverage-planning` | Footprints, coverage, mission planning, terrain, tiles | `backend/services/{coverage,mission_planner,geometry,terrain,slope_overlay}.py`<br>`backend/routers/{coverage,plans,target_areas,footprints,tiles}.py` | `frontend/src/features/{map,plan,compare,mobile}/**` | `tests/backend/test_{coverage_router,mission_planner*,geometry,terrain,plans_router,target_areas_router,footprints_router,tiles_router,rth_terrain_safety,slope_overlay}.py` |
| `reconstruction-splat` | COLMAP, splat training/backends, job queue, georeferencing, semantics, comparisons | `backend/services/{reconstruction,colmap_*,splat_*,job_queue,remote_worker,georeferencing_*,semantic_*,accelerator,ply_io,camera_calibration,cesium_tiles,artifact_cleanup}.py`<br>`backend/services/splat_backends/**`<br>`backend/routers/{reconstruction,jobs,comparisons,georeferencing,measurements,annotations}.py`<br>`scripts/**` | `frontend/src/features/{reconstruct,splat,jobs,hero}/**` | `tests/backend/test_{reconstruction*,colmap_*,splat_*,job_queue,jobs_router,remote_worker,georeferencing_*,semantic_*,accelerator,ply_io,camera_calibration,cesium_tiles,comparisons_*,measurements_*,annotations_*,metal_*,nearest_*,dense_rerun}.py, tests/test_*benchmark*.py, tests/test_metal_release_gate.py` |
| `export-share` | Exports, share links/bundles, reports, WebODM, GIS formats | `backend/services/{*_export,share_*,survey_report,webodm*,potree_export,usd_export,cesium_ion,gis_project_files,reproducibility_manifest,quality_report,geometry_exports}.py`<br>`backend/routers/{export,share_links,webodm}.py`<br>`backend/core/csv_safe.py` | `frontend/src/features/{export,share}/**` | `tests/backend/test_{*export*,share_*,survey_report,webodm*,cesium_ion,reproducibility_manifest,quality_report,quick_report,csv_safe}.py` |
| `platform-ops` | App shell, config, settings, system, storage, backups, PIN lock, metrics | `backend/main.py`<br>`backend/__main__.py`<br>`backend/core/**`<br>`backend/routers/{system,settings,storage,metrics,projects,defects,session_log}.py`<br>`backend/services/{storage_*,artifact_backup*,pin_lock}.py` | `frontend/src/features/{settings,storage,overview,checklist}/**`<br>`frontend/src/App.tsx`<br>`frontend/src/main.tsx` | `tests/backend/test_{main*,config,deployment_config,settings_router,system_router,storage*,artifact_backup*,pin_lock,metrics,projects,defects_*,application_logging,backend_runner,path_confinement,frontend_static_mount}.py` |
| `db-migrations` | ORM models, sessions, Alembic revisions | `backend/db/**`<br>`alembic.ini` | — | `tests/backend/db/**, tests/backend/test_{database,test_db_isolation}.py` |
| `frontend-shared` | Shared frontend code used by every feature | — | `frontend/src/shared/**`<br>`frontend/src/types/**`<br>`frontend/package*.json`<br>`frontend/vite.config.ts`<br>`frontend/tsconfig*.json`<br>`frontend/eslint.config.js` | `frontend/src/shared/**/*.test.ts*` |
| `packaging-release` | Docker, launchers, desktop packaging, CI, supply chain | `Dockerfile`<br>`.dockerignore`<br>`run.*`<br>`dev.*`<br>`packaging/**`<br>`.github/**`<br>`pyproject.toml`<br>`uv.lock` | — | `tests/test_supply_chain_configuration.py, tests/backend/test_{windows,macos}_packaging.py, tests/backend/test_dev_launcher_contract.py, tests/cli/test_wheel_contract.py` |

Docs-only changes (`docs/**`, `*.md`, `release-notes/**`) run only the gate job and docs checks.

## 4. How to implement the split

### 4.1 pytest markers (no file moves required up front)

```toml
# pyproject.toml
[tool.pytest.ini_options]
addopts = "--strict-markers -ra"
testpaths = ["tests"]
pythonpath = [".", "src"]
markers = [
  "unit: isolated, no DB/network/subprocess",
  "integration: TestClient + temp DB + filesystem",
  "contract: cross-boundary agreements (API, types, migrations, exports, packaging)",
  "e2e: browser journeys (Playwright, run outside pytest)",
  "perf: scaling budgets (nightly)",
  "hardware: needs a real GPU/Apple Silicon (dispatch only)",
  # plus one "area_<name>" marker per coverage area in section 3 (area_geotag_cli, area_ingest_import, ...)
]
```

```python
# tests/conftest.py (sketch)
AREA_BY_FILE = {...}  # filename glob -> area, mirrors the table above; unmapped files fail collection
INTEGRATION_FIXTURES = {"client", "db_session", "setup_test_db"}

def pytest_addoption(parser):
    parser.addoption("--area", default="", help="comma-separated coverage areas to run")

def pytest_collection_modifyitems(config, items):
    wanted = {a for a in config.getoption("--area").split(",") if a}
    keep = []
    for item in items:
        if not any(item.iter_markers(n) for n in ("unit", "integration", "contract", "perf", "hardware")):
            level = "integration" if INTEGRATION_FIXTURES & set(item.fixturenames) else "unit"
            item.add_marker(level)
        area = area_for(item.path)  # raises for unmapped test files
        item.add_marker(f"area_{area.replace('-', '_')}")
        if not wanted or area in wanted:
            keep.append(item)
    items[:] = keep
```

Selection examples: `pytest -m unit --area ingest-import`, `pytest -m "unit or integration" --area export-share,db-migrations`, `pytest -m contract`. Move files into `tests/<area>/{unit,integration}/` opportunistically; the marker contract test keeps both styles consistent.

### 4.2 Vitest projects

```ts
// vite.config.ts (test section sketch)
test: {
  projects: [
    { extends: true, test: { name: 'unit', environment: 'node', include: ['src/**/*.test.ts'] } },
    { extends: true, test: { name: 'component', environment: 'jsdom', include: ['src/**/*.test.tsx'], setupFiles: ['src/test/setup.ts'] } },
  ],
  coverage: { provider: 'v8', all: true, include: ['src/**'], exclude: ['src/**/*.test.*', 'src/main.tsx'],
              reporter: ['text-summary', 'json-summary', 'lcov'], thresholds: { lines: 50, branches: 41 } },
}
```

PR selection: `vitest run --project unit --project component --changed origin/main` plus explicit feature folders from the path filter (`vitest run src/features/export src/features/share`). `frontend-shared` changes run the whole frontend suite.

### 4.3 CI lanes

```yaml
# .github/workflows/ci.yml (structure sketch; pin every action by SHA as today)
on:
  pull_request:
  push: { branches: [main] }
  schedule: [{ cron: '17 3 * * *' }]   # nightly full run
  workflow_dispatch: ...                 # existing hardware inputs unchanged
jobs:
  changes:          # dorny/paths-filter -> outputs one boolean per area + 'full'
  python-areas:     # needs: changes; matrix over affected areas; pytest -m 'unit or integration' --area ${{ matrix.area }}
  contract:         # runs if backend routers/db/export or frontend api/features/packaging changed
  frontend:         # runs if any frontend path changed; lint + tsc + vitest (affected folders)
  e2e:              # nightly/main/release, or PR label run-e2e
  docker-build / distribution / windows-package / macos-package:
                    # PR only if packaging-release changed (or label run-packaging); always on main/nightly/release
  coverage-full:    # nightly + main: all areas, --cov-branch, thresholds, artifacts
  ci-gate:          # always runs; fails if any selected job failed -> the only required status check
```

Python 3.11 runs on PRs for the affected areas; the 3.11 + 3.12 matrix runs in full on main and nightly. Every job gets `timeout-minutes`.

### 4.4 Coverage thresholds

Start each area at its measured baseline (rounded down) so today's code passes, then ratchet up 2 points per minor release until Python areas reach 85% lines / 75% branches and frontend feature folders reach 70% lines. PRs must cover at least 80% of changed lines in the touched areas (diff coverage).

| Area | Baseline (lines) | Initial threshold | Target |
|---|---|---|---|
| coverage-planning | 78.9% | 78% | 85% |
| db-migrations | 81.6% | 81% | 85% |
| export-share | 81.5% | 81% | 85% |
| flight-log-gps | 94.4% | 94% | 94% |
| geotag-cli | 91.5% | 91% | 91% |
| ingest-import | 91.2% | 91% | 91% |
| platform-ops | 85.5% | 85% | 85% |
| reconstruction-splat | 81.6% | 81% | 85% |
| frontend (all loaded files) | 49.58% | 49% | 70% |

## 5. Test creation and update policy

1. **Every bug fix ships with a regression test** at the lowest level that reproduces the bug (unit if possible), written to fail on the current code first.
2. **Crossing a boundary adds a contract test.** Changing a route, method, response shape, export schema, migration or launcher requires the matching contract test to change in the same PR.
3. **UI behaviour is tested like a user.** Component tests use roles/labels and `userEvent`, and assert the request that was sent, not just that a callback ran.
4. **Failure paths are first-class.** Each item in M3 names the error/boundary case its test must cover (empty session, corrupt file, timeout, FK conflict).
5. **No sleeps, no either-outcome assertions.** Drive background workers synchronously or poll with a deadline; assert one expected state.
6. **Tests move with code.** When a module is split (M5), its tests are split along the same seams and keep their area marker.

## 6. Test backlog from the audit (by area and level)

85 tests to add or update across the work items: 33 unit, 27 integration, 15 contract, 6 component, 3 e2e, 1 perf.

### `coverage-planning`

| Level | Work item | File | Test |
|---|---|---|---|
| unit | [M1-08](M1-correctness-and-safety.md#m1-08) [#949](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/949) | `tests/backend/test_mission_planner.py` | For an L-shaped polygon every waypoint lies inside the polygon buffered by one lane spacing. |
| integration | [M1-08](M1-correctness-and-safety.md#m1-08) [#949](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/949) | `tests/backend/test_plans_router.py` | Negative or >=1 overlap returns 422. |
| unit | [M1-08](M1-correctness-and-safety.md#m1-08) [#949](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/949) | `tests/backend/test_mission_planner_ext.py` | Exported KML/GPX altitudes equal the terrain-following altitudes; a two-gap coverage result yields lanes over both gaps. |
| integration | [M3-04](M3-reliability-and-error-handling.md#m3-04) [#968](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/968) | `tests/backend/test_plans_router.py` | GET /segments creates no files in exports_dir. |
| perf | [M4-02](M4-performance-and-scale.md#m4-02) [#975](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/975) | `tests/perf/test_coverage_scaling.py (new)` | Overlap for 2k footprints completes under a budget and scales < n^1.3 (nightly). |

### `db-migrations`

| Level | Work item | File | Test |
|---|---|---|---|
| integration | [M1-04](M1-correctness-and-safety.md#m1-04) [#945](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/945) | `tests/backend/test_sessions_router.py` | Deleting an auto-imported session succeeds and removes its AutoImportRecord. |
| integration | [M1-04](M1-correctness-and-safety.md#m1-04) [#945](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/945) | `tests/backend/test_database.py` | The new ondelete migration upgrades a v3.0.0 DB containing auto-import rows and a comparison without data loss. |
| contract | [M1-05](M1-correctness-and-safety.md#m1-05) [#946](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/946) | `tests/backend/test_database.py` | Extend `test_legacy_upgrade_covers_every_model_column` with a pre-projects v1.x snapshot (reproduces the 0005 NotImplementedError today) and assert `compare_metadata(Base.metadata)` is empty after upgrade. |
| contract | [M1-05](M1-correctness-and-safety.md#m1-05) [#946](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/946) | `tests/backend/test_database.py` | `downgrade` to 0004 then `upgrade head` round-trips on a populated DB (0005 downgrade path). |
| contract | [M2-07](M2-test-strategy-and-ci.md#m2-07) [#963](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/963) | `tests/backend/test_database.py` | Each release snapshot (v1.x, v2.0.2, v3.0.0) upgrades to head with zero compare_metadata diffs and preserved row counts. |

### `export-share`

| Level | Work item | File | Test |
|---|---|---|---|
| integration | [M1-01](M1-correctness-and-safety.md#m1-01) [#942](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/942) | `tests/backend/test_webodm_package_export.py` | An image named `=HYPERLINK(...).jpg` produces a quoted, `'`-prefixed cell in odm_georeferencing.csv. |
| unit | [M1-01](M1-correctness-and-safety.md#m1-01) [#942](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/942) | `tests/backend/test_webodm_package_export.py` | Every filename listed in the CSV exists as a member of the produced zip. |
| contract | [M1-01](M1-correctness-and-safety.md#m1-01) [#942](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/942) | `tests/backend/test_csv_safe.py` | Extend the writer inventory test so any new CSV writer in backend/ must import csv_safe (grep-based contract). |
| integration | [M1-10](M1-correctness-and-safety.md#m1-10) [#951](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/951) | `tests/backend/test_survey_report.py` | POST /export/survey-report for an empty session returns 200 in json and html formats. |
| unit | [M1-10](M1-correctness-and-safety.md#m1-10) [#951](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/951) | `tests/backend/test_quality_report.py` | A corrupt GLB produces a failed surface check with the parser error, not an empty pass. |
| contract | [M1-11](M1-correctness-and-safety.md#m1-11) [#952](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/952) | `tests/contract/test_frontend_api_contract.py (new)` | Every URL + method built in frontend/src resolves to a FastAPI route (would have caught the 405). |
| e2e | [M1-11](M1-correctness-and-safety.md#m1-11) [#952](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/952) | `e2e/export.spec.ts (new)` | Survey report opens (200) and the WebODM zip downloads. |
| unit | [M1-15](M1-correctness-and-safety.md#m1-15) [#956](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/956) | `tests/backend/test_share_links.py` | The signing key file is created 0o600 and a concurrent create does not overwrite it. |
| contract | [M2-04](M2-test-strategy-and-ci.md#m2-04) [#960](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/960) | `tests/contract/test_frontend_api_contract.py (new)` | All frontend calls resolve to a route with the same method. |
| e2e | [M2-05](M2-test-strategy-and-ci.md#m2-05) [#961](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/961) | `e2e/export.spec.ts (new)` | Every Export tab download returns 200 with the expected content type. |
| integration | [M3-03](M3-reliability-and-error-handling.md#m3-03) [#967](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/967) | `tests/backend/test_orthomosaic_export.py` | Starting an ortho export creates a queue entry; a restart resumes or fails it. |
| unit | [M3-04](M3-reliability-and-error-handling.md#m3-04) [#968](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/968) | `tests/backend/test_session_bundle.py` | A crash mid-write (monkeypatched) leaves no partial archive at the final path. |

### `flight-log-gps`

| Level | Work item | File | Test |
|---|---|---|---|
| unit | [M1-06](M1-correctness-and-safety.md#m1-06) [#947](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/947) | `tests/backend/test_flight_log_sync.py` | A BOM-prefixed DJI CSV yields the same timestamps as the BOM-less file. |
| unit | [M1-06](M1-correctness-and-safety.md#m1-06) [#947](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/947) | `tests/backend/test_flight_log_sync.py` | A log with 0..600000 ms offsets is anchored to its start time, not 1970. |
| integration | [M1-06](M1-correctness-and-safety.md#m1-06) [#947](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/947) | `tests/backend/test_flight_log_router.py` | (0, 0) rows never influence synced positions; footprints change after sync. |
| unit | [M1-15](M1-correctness-and-safety.md#m1-15) [#956](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/956) | `tests/backend/test_dji_log_parser.py` | The API key never appears in the subprocess argv. |

### `frontend`

| Level | Work item | File | Test |
|---|---|---|---|
| contract | [M5-07](M5-maintainability-and-type-safety.md#m5-07) [#983](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/983) | `frontend/tsconfig.app.json` | `tsc -b` in CI enforces both flags. |

### `frontend/export`

| Level | Work item | File | Test |
|---|---|---|---|
| component | [M1-11](M1-correctness-and-safety.md#m1-11) [#952](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/952) | `frontend/src/features/export/ExportTab.test.tsx (new)` | Clicking 'Generate Share Link' twice sends one POST; revoke calls the revoke endpoint and removes the row. |

### `frontend/import`

| Level | Work item | File | Test |
|---|---|---|---|
| component | [M2-06](M2-test-strategy-and-ci.md#m2-06) [#962](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/962) | `frontend/src/features/import/ImportModal.test.tsx (new)` | ESC closes when idle, not while uploading; Tab cycles inside the dialog; cancel aborts the upload. |

### `frontend/reconstruct`

| Level | Work item | File | Test |
|---|---|---|---|
| component | [M3-07](M3-reliability-and-error-handling.md#m3-07) [#971](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/971) | `frontend/src/features/reconstruct/ReconstructTab.test.tsx` | Cancel opens a confirmation; only confirm sends POST /cancel. |

### `frontend/settings`

| Level | Work item | File | Test |
|---|---|---|---|
| component | [M2-06](M2-test-strategy-and-ci.md#m2-06) [#962](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/962) | `frontend/src/features/settings/*.test.tsx (new)` | Invalid values show validation errors and are not PATCHed. |

### `frontend/share`

| Level | Work item | File | Test |
|---|---|---|---|
| component | [M1-11](M1-correctness-and-safety.md#m1-11) [#952](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/952) | `frontend/src/features/share/ShareViewer.test.tsx (new)` | A 401 with code share_password_required shows the password form. |

### `frontend/shared`

| Level | Work item | File | Test |
|---|---|---|---|
| unit | [M3-07](M3-reliability-and-error-handling.md#m3-07) [#971](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/971) | `frontend/src/shared/utils/downloadBlob.test.ts (new)` | revokeObjectURL is called after the click tick. |
| unit | [M5-06](M5-maintainability-and-type-safety.md#m5-06) [#982](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/982) | `frontend/src/shared/api/client.test.ts` | `postForm` applies the timeout and parses array-shaped 422 details. |
| unit | [M5-06](M5-maintainability-and-type-safety.md#m5-06) [#982](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/982) | `frontend/src/shared/jobs/status.test.ts (new)` | Every Job['status'] has a label and colour (exhaustive). |

### `frontend/splat`

| Level | Work item | File | Test |
|---|---|---|---|
| unit | [M1-12](M1-correctness-and-safety.md#m1-12) [#953](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/953) | `frontend/src/features/splat/measurementMath.test.ts` | `computeVolume` with a sloped sampler returns the analytic wedge volume; the UI refuses to compute without a sampler. |
| component | [M5-05](M5-maintainability-and-type-safety.md#m5-05) [#981](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/981) | `frontend/src/features/splat/*.test.tsx` | Each extracted layer hook disposes its group on unmount (mock scene). |

### `geotag-cli`

| Level | Work item | File | Test |
|---|---|---|---|
| unit | [M1-07](M1-correctness-and-safety.md#m1-07) [#948](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/948) | `tests/cli/test_frames.py` | Frames 21..30 at 1 fps are tagged at t=20..29 s, identical to the same frames when 1..20 are present. |
| unit | [M1-07](M1-correctness-and-safety.md#m1-07) [#948](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/948) | `tests/cli/test_frames.py` | `infer_frame_rate` raises when telemetry_end_s <= 0. |
| integration | [M1-07](M1-correctness-and-safety.md#m1-07) [#948](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/948) | `tests/cli/test_pipeline.py` | The headless pipeline honours `start_number` from the job spec. |
| integration | [M3-08](M3-reliability-and-error-handling.md#m3-08) [#972](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/972) | `tests/cli/test_pipeline.py` | Pipeline and CLI produce identical tags and warnings for the same inputs; a log file appears in log_dir. |
| unit | [M4-03](M4-performance-and-scale.md#m4-03) [#976](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/976) | `tests/cli/test_telemetry.py` | Bisect interpolation equals the linear-scan result on randomized telemetry (property test). |
| unit | [M5-04](M5-maintainability-and-type-safety.md#m5-04) [#980](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/980) | `tests/cli/test_audit.py` | backend and CLI import the same csv_safe object. |

### `ingest-import`

| Level | Work item | File | Test |
|---|---|---|---|
| unit | [M1-02](M1-correctness-and-safety.md#m1-02) [#943](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/943) | `tests/backend/test_ingest.py` | `extract_exif` on 2 KB of random bytes raises UnreadableImageError (today it returns an empty dict). |
| integration | [M1-02](M1-correctness-and-safety.md#m1-02) [#943](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/943) | `tests/backend/test_ingest_orchestrator.py` | A folder with one corrupt .jpg and two valid frames imports 2 frames, skips 1, and writes an `image_skipped` log entry. |
| integration | [M1-02](M1-correctness-and-safety.md#m1-02) [#943](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/943) | `tests/backend/test_ingest_orchestrator.py` | When `score_image` raises, the frame is stored unusable with a `quality_failed` entry, never `flag='good'`. |
| integration | [M1-03](M1-correctness-and-safety.md#m1-03) [#944](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/944) | `tests/backend/test_uploads_router.py` | A completed upload older than 24 h keeps its images after the sweep runs; an abandoned one is removed. |
| integration | [M1-03](M1-correctness-and-safety.md#m1-03) [#944](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/944) | `tests/backend/test_uploads_router.py` | POST /cancel on an importing upload returns 409 and leaves files in place. |
| integration | [M1-03](M1-correctness-and-safety.md#m1-03) [#944](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/944) | `tests/backend/test_upload_reservation_cap.py` | Finished imports do not consume reservation slots. |
| integration | [M3-05](M3-reliability-and-error-handling.md#m3-05) [#969](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/969) | `tests/backend/test_images_router.py` | Flagging an image updates Session.usable_count; an unknown flag is 422. |
| unit | [M3-05](M3-reliability-and-error-handling.md#m3-05) [#969](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/969) | `tests/backend/test_ingest.py` | EXIF DateTimeOriginal with OffsetTimeOriginal converts to UTC; without offset stays local. |
| integration | [M4-01](M4-performance-and-scale.md#m4-01) [#974](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/974) | `tests/backend/test_duplicate_detection.py` | Constant query count across 1 vs 30 sessions. |

### `packaging-release`

| Level | Work item | File | Test |
|---|---|---|---|
| contract | [M1-14](M1-correctness-and-safety.md#m1-14) [#955](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/955) | `tests/backend/test_dev_launcher_contract.py` | Extend the #803 launcher contract to run.sh and run.bat (VITE_API_URL or proxy present). |
| contract | [M1-15](M1-correctness-and-safety.md#m1-15) [#956](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/956) | `tests/test_supply_chain_configuration.py` | Dockerfile FROM lines are digest-pinned and a USER directive precedes CMD. |
| contract | [M2-01](M2-test-strategy-and-ci.md#m2-01) [#957](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/957) | `tests/test_supply_chain_configuration.py` | Every job has timeout-minutes; the path map covers every top-level source directory (no orphan paths). |
| contract | [M2-01](M2-test-strategy-and-ci.md#m2-01) [#957](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/957) | `tests/test_ci_lane_map.py (new)` | Each coverage area's path globs match at least one file and every tracked source file maps to >=1 area. |
| e2e | [M2-05](M2-test-strategy-and-ci.md#m2-05) [#961](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/961) | `e2e/smoke.spec.ts (new)` | Golden-path journey above passes on the Docker image. |

### `platform-ops`

| Level | Work item | File | Test |
|---|---|---|---|
| contract | [M2-02](M2-test-strategy-and-ci.md#m2-02) [#958](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/958) | `tests/test_markers_contract.py (new)` | Every collected test has exactly one level marker and one area marker. |
| contract | [M2-03](M2-test-strategy-and-ci.md#m2-03) [#959](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/959) | `.github/workflows/ci.yml` | Nightly full run fails if any area drops below its threshold. |
| contract | [M2-04](M2-test-strategy-and-ci.md#m2-04) [#960](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/960) | `tests/contract/test_openapi_types.py (new)` | Generated TS types are up to date with app.openapi(). |
| integration | [M3-01](M3-reliability-and-error-handling.md#m3-01) [#965](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/965) | `tests/backend/test_storage_router.py` | An unreadable file in one session dir still returns the other sessions plus an error entry. |
| unit | [M3-02](M3-reliability-and-error-handling.md#m3-02) [#966](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/966) | `tests/backend/test_config.py` | A list-valued top level raises a clear ConfigError; a UTF-8 non-ASCII path round-trips under a cp1252 locale (monkeypatched). |
| unit | [M3-02](M3-reliability-and-error-handling.md#m3-02) [#966](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/966) | `tests/backend/test_database.py` | DATABASE_URL defaults to <data_dir>/drone_mapping.db. |
| unit | [M3-04](M3-reliability-and-error-handling.md#m3-04) [#968](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/968) | `tests/backend/test_artifact_backup.py` | A hung rclone (sleep shim) is killed at the timeout and reported failed. |
| integration | [M3-05](M3-reliability-and-error-handling.md#m3-05) [#969](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/969) | `tests/backend/test_storage_lifecycle.py` | The intermediates rule finds files written by a (fake) COLMAP run; archived frames stay resolvable. |
| integration | [M3-06](M3-reliability-and-error-handling.md#m3-06) [#970](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/970) | `tests/backend/test_defects_router.py` | A failing link insert leaves no orphan defect. |
| integration | [M4-01](M4-performance-and-scale.md#m4-01) [#974](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/974) | `tests/backend/test_projects.py` | Query count for GET /projects is constant for 1 vs 50 projects (SQLAlchemy event counter fixture). |
| unit | [M5-03](M5-maintainability-and-type-safety.md#m5-03) [#979](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/979) | `(per function)` | Unit tests for each extracted helper, especially error branches previously untested. |

### `reconstruction-splat`

| Level | Work item | File | Test |
|---|---|---|---|
| integration | [M1-04](M1-correctness-and-safety.md#m1-04) [#945](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/945) | `tests/backend/test_reconstruction_router.py` | Deleting a reconstruction used by a comparison returns 409 and its splat/PLY files still exist. |
| unit | [M1-09](M1-correctness-and-safety.md#m1-09) [#950](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/950) | `tests/backend/test_cesium_tiles.py` | The tileset root transform equals the ECEF placement derived from a known geo_transform. |
| unit | [M1-09](M1-correctness-and-safety.md#m1-09) [#950](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/950) | `tests/backend/test_splat_cleanup.py` | A synthetic splat with a known geo_transform keeps exactly the Gaussians inside a lon/lat polygon. |
| integration | [M1-09](M1-correctness-and-safety.md#m1-09) [#950](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/950) | `tests/backend/test_comparisons_router.py` | Comparing a reconstruction with NULL geo_transform returns 422. |
| integration | [M1-12](M1-correctness-and-safety.md#m1-12) [#953](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/953) | `tests/backend/test_elevation_export.py` | The new height-query endpoint returns DSM heights for known points. |
| integration | [M1-13](M1-correctness-and-safety.md#m1-13) [#954](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/954) | `tests/backend/test_reconstruction_service.py` | Two sessions each containing DJI_0001.JPG stage 2 distinct images. |
| integration | [M1-13](M1-correctness-and-safety.md#m1-13) [#954](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/954) | `tests/backend/test_remote_worker.py` | A remote completion stores splat/PLY paths reported by the worker. |
| unit | [M1-13](M1-correctness-and-safety.md#m1-13) [#954](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/954) | `tests/backend/test_job_queue.py` | Handler that raises -> failed; handler that returns early -> failed with reason (replaces the sleep-based test, see M2-08). |
| unit | [M1-15](M1-correctness-and-safety.md#m1-15) [#956](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/956) | `tests/backend/test_splat_transform.py` | The argv contains a pinned version and no bare `npx <pkg>`. |
| unit | [M2-08](M2-test-strategy-and-ci.md#m2-08) [#964](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/964) | `tests/backend/test_job_queue.py` | Deterministic no-handler test asserts status == 'failed'. |
| unit | [M3-01](M3-reliability-and-error-handling.md#m3-01) [#965](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/965) | `tests/backend/test_splat_backends.py` | A render exception is logged (caplog) and returns None. |
| integration | [M3-06](M3-reliability-and-error-handling.md#m3-06) [#970](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/970) | `tests/backend/test_annotations_router.py` | lat=91, lon=181, color='red;' each return 422. |
| unit | [M3-09](M3-reliability-and-error-handling.md#m3-09) [#973](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/973) | `tests/test_heldout_parity_benchmark.py` | Shared helpers used by all three scripts; import succeeds with `resource` unavailable (monkeypatched). |
| unit | [M4-02](M4-performance-and-scale.md#m4-02) [#975](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/975) | `tests/backend/test_splat_cleanup.py` | KD-tree outlier filter matches the reference result on a seeded cloud. |
| contract | [M5-01](M5-maintainability-and-type-safety.md#m5-01) [#977](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/977) | `tests/contract/test_frontend_api_contract.py` | Router split keeps every route and method (contract suite from M2-04). |
| unit | [M5-01](M5-maintainability-and-type-safety.md#m5-01) [#977](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/977) | `tests/backend/test_ply_io.py` | ply_io reads every PLY variant the removed parsers handled (fixtures). |
| unit | [M5-02](M5-maintainability-and-type-safety.md#m5-02) [#978](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/978) | `tests/backend/test_georeferencing_solve.py` | UTM zone helper covers zone boundaries, Norway/Svalbard exceptions and southern hemisphere. |
