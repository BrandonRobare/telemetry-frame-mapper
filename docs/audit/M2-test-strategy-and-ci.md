# v3.3 — Test Strategy & CI Split

**GitHub milestone:** `v3.3 — Test Strategy & CI Split` · **Audit group:** M2 · **Priority band:** P1 · **Epic:** [#938](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/938) · **Work items:** 8 · **Findings:** 7

## Goal

Make every level of testing explicit (unit, integration, contract, component, end-to-end, platform) and split the suite by coverage area so a pull request runs only the lanes its diff touches, while main, nightly and release still run everything with coverage thresholds.

## Exit criteria

- [ ] PR CI selects lanes from a path filter; a docs-only PR finishes without Python, packaging or macOS jobs.
- [ ] pytest markers (unit/integration/contract/e2e + area) and Vitest projects (unit/component) exist and are enforced.
- [ ] Coverage is reported per area with thresholds at or above the measured baseline (Python 84.1% lines; frontend 49.6% lines of loaded files).
- [ ] A Playwright smoke suite and an API-contract test run nightly and on release.

## Work items

| Key | Title | Priority | Issue |
|---|---|---|---|
| [M2-01](#m2-01) | ci: path-filtered PR lanes by coverage area; full matrix on main, nightly and release | P1 | [#957](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/957) |
| [M2-02](#m2-02) | test: pytest markers and layout by level and coverage area | P1 | [#958](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/958) |
| [M2-03](#m2-03) | test: coverage reporting and per-area thresholds (pytest-cov, Vitest v8) | P1 | [#959](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/959) |
| [M2-04](#m2-04) | test: API contract suite (frontend URLs, OpenAPI types, CSV/export schemas) | P1 | [#960](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/960) |
| [M2-05](#m2-05) | test: Playwright end-to-end smoke suite against the Docker image | P1 | [#961](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/961) |
| [M2-06](#m2-06) | test: frontend component tests for untested units, Vitest projects by level | P1 | [#962](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/962) |
| [M2-07](#m2-07) | test: migration upgrade-path and schema-drift suite | P2 | [#963](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/963) |
| [M2-08](#m2-08) | test: fix flaky and assertion-free tests | P2 | [#964](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/964) |

<a id="m2-01"></a>
### M2-01 · ci: path-filtered PR lanes by coverage area; full matrix on main, nightly and release

**Priority:** P1 · **Coverage area:** `packaging-release` · **Labels:** `automated testing`, `github_actions`, `priority: high` · **Issue:** [#957](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/957)

Every PR runs Python 3.11+3.12, frontend, Docker, wheel, Windows packaging and macOS (brew + third full pytest). Split lanes by area so PRs run only what they touch.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `BP-TEST` | [`.github/workflows/ci.yml:29-31`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/.github/workflows/ci.yml#L29-L31) | Every PR runs the full CI matrix; there is no path filtering |
| LOW | `BP-QUAL` | [`.github/workflows/ci.yml:41-44`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/.github/workflows/ci.yml#L41-L44) | Most CI jobs have no timeout-minutes |

**Changes to make**

- Add a `changes` job (dorny/paths-filter pinned by SHA) emitting one flag per coverage area (see TEST-STRATEGY.md path map).
- PR: run `pytest -m "unit or integration" --area <areas>` and Vitest projects for touched frontend features; contract lane whenever backend routers or frontend API code change.
- Run Docker, wheel, Windows and macOS packaging on PRs only when packaging-release paths change (or with a `run-packaging` label).
- Add `schedule:` nightly + `push: main` running the full matrix with coverage; add `timeout-minutes` to every job.
- Add a required `ci-gate` job that passes when all selected lanes passed (so branch protection works with skipped lanes).

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| contract | packaging-release | `tests/test_supply_chain_configuration.py` | Every job has timeout-minutes; the path map covers every top-level source directory (no orphan paths). |
| contract | packaging-release | `tests/test_ci_lane_map.py (new)` | Each coverage area's path globs match at least one file and every tracked source file maps to >=1 area. |

**Acceptance criteria**

- [ ] A docs-only PR runs only the gate + docs checks.
- [ ] A frontend-only PR runs frontend lint/type/unit/component + contract lanes only.
- [ ] main/nightly run everything.

<a id="m2-02"></a>
### M2-02 · test: pytest markers and layout by level and coverage area

**Priority:** P1 · **Coverage area:** `platform-ops` · **Labels:** `automated testing`, `python`, `priority: high` · **Issue:** [#958](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/958)

Tests are not marked by level or area, so CI cannot select them. Add markers now (auto-applied in conftest) and migrate the directory layout incrementally.

**Changes to make**

- Register markers `unit`, `integration`, `contract`, `e2e`, `perf`, `hardware` and `area_<name>` in pyproject; add `--strict-markers`.
- conftest `pytest_collection_modifyitems`: tests using `client`/`db_session`/`setup_test_db` get `integration`, others `unit`; area from a filename->area table (fails collection for unmapped files).
- Add `--area` option (comma list) that deselects other areas; remove `-s` from addopts.
- Later: move to `tests/<area>/{unit,integration}/` as files are touched.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| contract | platform-ops | `tests/test_markers_contract.py (new)` | Every collected test has exactly one level marker and one area marker. |

**Acceptance criteria**

- [ ] `pytest -m unit --area ingest-import` runs only ingest unit tests.
- [ ] Unmapped test files fail collection.

<a id="m2-03"></a>
### M2-03 · test: coverage reporting and per-area thresholds (pytest-cov, Vitest v8)

**Priority:** P1 · **Coverage area:** `platform-ops` · **Labels:** `automated testing`, `priority: high` · **Issue:** [#959](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/959)

No coverage is measured. Baseline measured in this audit: Python 84.1% lines overall (area range 78.9–94.4%); frontend 49.6% lines / 41.3% branches of files loaded by tests, with 59 of 126 units never loaded.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `BP-TEST` | [`pyproject.toml:103-106`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/pyproject.toml#L103-L106) | No coverage measurement or thresholds for Python or frontend |

**Changes to make**

- Add pytest-cov with `--cov-branch`; add @vitest/coverage-v8 with `all: true` / `include: ['src/**']`.
- Set thresholds at the baseline per area (fail under), ratchet +2 points per release.
- Upload coverage artifacts; post a PR summary of diff coverage for touched areas (target >= 80% of changed lines).

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| contract | platform-ops | `.github/workflows/ci.yml` | Nightly full run fails if any area drops below its threshold. |

**Acceptance criteria**

- [ ] Coverage is visible per area on every nightly and in PR summaries.
- [ ] Thresholds prevent regression below baseline.

<a id="m2-04"></a>
### M2-04 · test: API contract suite (frontend URLs, OpenAPI types, CSV/export schemas)

**Priority:** P1 · **Coverage area:** `export-share` · **Labels:** `automated testing`, `priority: high` · **Issue:** [#960](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/960)

This audit found the survey-report 405 by matching 122 frontend API calls against the FastAPI routes; make that a permanent contract test and stop hand-maintaining 658 lines of `types/api.ts`.

**Changes to make**

- Add `tests/contract/test_frontend_api_contract.py`: extract `get/post/patch/del/apiUrl` paths + methods from frontend/src and assert each matches an OpenAPI path/method.
- Generate `frontend/src/types/api.generated.ts` from `app.openapi()` (openapi-typescript) and fail CI on drift.
- Snapshot export schemas (CSV headers, GeoJSON properties) as contract fixtures.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| contract | export-share | `tests/contract/test_frontend_api_contract.py (new)` | All frontend calls resolve to a route with the same method. |
| contract | platform-ops | `tests/contract/test_openapi_types.py (new)` | Generated TS types are up to date with app.openapi(). |

**Acceptance criteria**

- [ ] A route/method mismatch between UI and API fails CI before merge.

<a id="m2-05"></a>
### M2-05 · test: Playwright end-to-end smoke suite against the Docker image

**Priority:** P1 · **Coverage area:** `packaging-release` · **Labels:** `automated testing`, `frontend`, `priority: high` · **Issue:** [#961](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/961)

Nothing runs the built SPA against the real API. Add a small E2E suite with external tools mocked by shims (per ARCHITECTURE.md).

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `BP-TEST` | [`frontend/package.json:14`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/package.json#L14) | No end-to-end test exercises the real UI against the real API |

**Changes to make**

- Add `e2e/` Playwright project (uses the preinstalled Chromium in CI images) with fixtures that start the Docker image or `python -m backend` + built dist.
- Provide fake `colmap`/`ffmpeg`/`exiftool` shims on PATH so reconstruction completes deterministically in seconds.
- Journeys: browser import -> map footprints -> review flag -> reconstruct (fake) -> splat tab loads -> export links 200 -> share link + revoke -> share viewer.
- Run nightly, on push to main, on release, and on PRs labelled `run-e2e`.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| e2e | packaging-release | `e2e/smoke.spec.ts (new)` | Golden-path journey above passes on the Docker image. |
| e2e | export-share | `e2e/export.spec.ts (new)` | Every Export tab download returns 200 with the expected content type. |

**Acceptance criteria**

- [ ] E2E smoke is green nightly and gates releases.

<a id="m2-06"></a>
### M2-06 · test: frontend component tests for untested units, Vitest projects by level

**Priority:** P1 · **Coverage area:** `frontend` · **Labels:** `automated testing`, `frontend`, `priority: medium` · **Issue:** [#962](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/962)

59 of 126 frontend units have no test that imports them (largest: ExportTab 913 lines, ImportModal 662, CompareTab 413, ShareViewer 312). 14 of 18 RTL files use fireEvent; user-event is not installed.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `RX-TEST-003` | [`frontend/src/App.test.tsx:1`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/App.test.tsx#L1) | Component tests drive interactions with fireEvent; user-event is not installed |

**Changes to make**

- Split vite.config test into Vitest projects: `unit` (environment node, *.test.ts) and `component` (jsdom, *.test.tsx).
- Add @testing-library/user-event and migrate interaction tests; add MSW (or a shared fetch mock) for API responses.
- Add component tests for ExportTab, ImportModal (focus trap, ESC, upload cancel), ShareViewer, CompareTab, settings forms, BulkSessionOperations, ProjectPicker.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| component | frontend/import | `frontend/src/features/import/ImportModal.test.tsx (new)` | ESC closes when idle, not while uploading; Tab cycles inside the dialog; cancel aborts the upload. |
| component | frontend/settings | `frontend/src/features/settings/*.test.tsx (new)` | Invalid values show validation errors and are not PATCHed. |

**Acceptance criteria**

- [ ] Every feature folder has component tests for its tab-level component.
- [ ] fireEvent is used only where user-event cannot express the event.

<a id="m2-07"></a>
### M2-07 · test: migration upgrade-path and schema-drift suite

**Priority:** P2 · **Coverage area:** `db-migrations` · **Labels:** `automated testing`, `backend`, `priority: medium` · **Issue:** [#963](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/963)

tests/backend/test_database.py already upgrades an immutable v2.0.2 snapshot and checks columns and FK indexes. It does not cover pre-projects (v1.x) databases, which is where 0005 fails, or compare FK options, types and constraints, so fresh and upgraded schemas can still drift.

**Changes to make**

- Add SQL snapshots for v1.x (pre-projects) and v3.0.0 next to tests/backend/db/v2_0_2_schema.sql.
- Parametrize the existing legacy-upgrade tests over all snapshots and add a `compare_metadata` assertion (FK ondelete, types, nullability); run on any change under backend/db/.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| contract | db-migrations | `tests/backend/test_database.py` | Each release snapshot (v1.x, v2.0.2, v3.0.0) upgrades to head with zero compare_metadata diffs and preserved row counts. |

**Acceptance criteria**

- [ ] Every shipped schema has an automated upgrade test.

<a id="m2-08"></a>
### M2-08 · test: fix flaky and assertion-free tests

**Priority:** P2 · **Coverage area:** `platform-ops` · **Labels:** `automated testing`, `python`, `priority: medium` · **Issue:** [#964](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/964)

test_job_queue sleeps 1 s for a worker thread and accepts 'failed' or 'completed'; five tests have no assertion.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `UNI-TEST-009` | [`tests/backend/test_job_queue.py:458-479`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/tests/backend/test_job_queue.py#L458-L479) | Job-queue test sleeps 1 s for a background worker and accepts either outcome |
| MEDIUM | `UNI-TEST-005` | [`tests/backend/test_session_merge.py:39`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/tests/backend/test_session_merge.py#L39) | Five backend tests have no assertion |

**Changes to make**

- Drive the job queue synchronously (call the dispatch function directly) and assert `failed` with the error text.
- Add explicit assertions to the five assertion-free tests; add pytest-timeout (60 s default) to catch hangs.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| unit | reconstruction-splat | `tests/backend/test_job_queue.py` | Deterministic no-handler test asserts status == 'failed'. |

**Acceptance criteria**

- [ ] No test depends on wall-clock sleeps for correctness.
- [ ] Every test asserts an outcome.

_Line links point at commit `3ec2135` (the audited `main`)._
