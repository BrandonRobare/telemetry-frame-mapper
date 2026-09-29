# Repository audit — 2026-09-29

Code review and repo-audit run over `BrandonRobare/telemetry-frame-mapper` at `main` @ `3ec2135` (branch `fix/jolly-meitner-wd69o6` was already level with `main`, so no rebase was needed). The skill's interactive dashboard is [`report.html`](../../report.html) at the repository root.

## Contents

| Document | What it holds |
|---|---|
| [M1 · v3.0.1 — Audit: Correctness & Safety Fixes](M1-correctness-and-safety.md) | Stop the defects that corrupt or lose user data, produce wrong survey or flight outputs, crash on ordinary inputs, or weaken security. Every item ships with a regression test that fails on today's code. |
| [M2 · v3.2 — Audit: Test Strategy & CI Split](M2-test-strategy-and-ci.md) | Make every level of testing explicit (unit, integration, contract, component, end-to-end, platform) and split the suite by coverage area so a pull request runs only the lanes its diff touches, while main, nightly and release still run everything with coverage thresholds. |
| [M3 · v3.2 — Audit: Reliability & Error Handling](M3-reliability-and-error-handling.md) | Remove silent failure paths, make writes atomic and bounded, keep derived state consistent, and validate inputs at the API boundary. |
| [M4 · v3.3 — Audit: Performance & Scale](M4-performance-and-scale.md) | Remove N+1 queries and quadratic hot paths that grow with session, project or splat size. |
| [M5 · v3.3 — Audit: Maintainability & Type Safety](M5-maintainability-and-type-safety.md) | Break up the oversized modules, remove copy-paste, and turn on the stricter compiler and linter settings the code already nearly satisfies. |
| [TEST-STRATEGY.md](TEST-STRATEGY.md) | Test levels (unit -> e2e + full coverage), coverage-area path map for per-PR selection, CI lane design, thresholds, and the per-area test backlog. |
| [FINDINGS.md](FINDINGS.md) | All findings with location, rule, issue, fix and work item. |

## Headline numbers

| Severity | Count |
|---|---|
| CRITICAL | 5 |
| HIGH | 67 |
| MEDIUM | 72 |
| LOW | 17 |
| NITPICK | 0 |
| **Total** | **161** |

Top categories: Maintainability (36), Correctness (32), Performance (13), Error handling (12), Security (9), Data integrity (8), Validation (7), Documentation (6).

Severities follow the skill's rule assets for asset rule IDs (for example `UNI-ERR-001` is always CRITICAL) and the skill's severity table for best-practice IDs (`BP-*`). The **priority** (P0–P3) and **milestone** on each work item reflect real-world urgency and are what the issues are ordered by.

## Milestones and issues

Each milestone is tracked as an **epic issue** whose sub-issues are the work items below; the issue titles, labels and bodies are generated from these documents. GitHub milestones are not created yet: create the five milestones with the exact titles below, then assign each epic and its sub-issues to its milestone.

| Milestone (proposed title) | Priority | Epic | Work items | Findings |
|---|---|---|---|---|
| **v3.0.1 — Audit: Correctness & Safety Fixes** | P0/P1 | [#937](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/937) | 15 | 51 |
| **v3.2 — Audit: Test Strategy & CI Split** | P1 | [#938](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/938) | 8 | 7 |
| **v3.2 — Audit: Reliability & Error Handling** | P2 | [#939](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/939) | 9 | 42 |
| **v3.3 — Audit: Performance & Scale** | P2/P3 | [#940](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/940) | 3 | 13 |
| **v3.3 — Audit: Maintainability & Type Safety** | P3 | [#941](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/941) | 7 | 48 |

### Work items

| Key | Title | Priority | Findings | Issue |
|---|---|---|---|---|
| [M1-01](M1-correctness-and-safety.md#m1-01) | fix(export): neutralize formula injection in the ODM georeferencing CSV | P0 | 1 critical, 1 medium | [#942](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/942) |
| [M1-02](M1-correctness-and-safety.md#m1-02) | fix(ingest): stop importing unreadable images as healthy frames | P0 | 2 critical, 1 high | [#943](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/943) |
| [M1-03](M1-correctness-and-safety.md#m1-03) | fix(uploads): staging sweep and cancel must not delete importing or imported images | P0 | 2 high, 1 medium | [#944](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/944) |
| [M1-04](M1-correctness-and-safety.md#m1-04) | fix(db): deletes must not wipe artifacts before a foreign-key failure | P0 | 3 high | [#945](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/945) |
| [M1-05](M1-correctness-and-safety.md#m1-05) | fix(migrations): 0005 crashes on pre-projects databases; freeze the baseline | P0 | 1 high, 2 medium | [#946](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/946) |
| [M1-06](M1-correctness-and-safety.md#m1-06) | fix(flight-log): BOM, relative clocks and null-island fixes corrupt GPS sync | P0 | 3 high, 1 medium | [#947](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/947) |
| [M1-07](M1-correctness-and-safety.md#m1-07) | fix(geotag): anchor frame time to ffmpeg's start number, not the first surviving frame | P1 | 2 high | [#948](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/948) |
| [M1-08](M1-correctness-and-safety.md#m1-08) | fix(plan): mission lanes must cover the drawn polygon; validate plan inputs | P0 | 3 high, 2 medium | [#949](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/949) |
| [M1-09](M1-correctness-and-safety.md#m1-09) | fix(georef): products mix COLMAP, UTM and lon/lat coordinate frames | P1 | 4 high | [#950](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/950) |
| [M1-10](M1-correctness-and-safety.md#m1-10) | fix(reports): survey report crashes on empty sessions; surface-extraction errors pass silently | P1 | 1 critical, 1 high | [#951](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/951) |
| [M1-11](M1-correctness-and-safety.md#m1-11) | fix(export-ui): survey report 405, share-link double submit, missing revoke UI, WebODM zip download | P1 | 3 high, 1 medium | [#952](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/952) |
| [M1-12](M1-correctness-and-safety.md#m1-12) | fix(splat): profile and cut/fill volume sample a constant flat plane | P1 | 1 high | [#953](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/953) |
| [M1-13](M1-correctness-and-safety.md#m1-13) | fix(reconstruction): filename collisions, remote completions and job-queue status drift | P1 | 3 high, 2 medium | [#954](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/954) |
| [M1-14](M1-correctness-and-safety.md#m1-14) | fix(run): run.sh / run.bat start a frontend that cannot reach the backend (#803 regression) | P1 | 1 high | [#955](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/955) |
| [M1-15](M1-correctness-and-safety.md#m1-15) | fix(security): hardening sweep (secrets on disk and argv, unpinned npx, root container, error leakage) | P1 | 1 critical, 1 high, 4 medium, 3 low | [#956](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/956) |
| [M2-01](M2-test-strategy-and-ci.md#m2-01) | ci: path-filtered PR lanes by coverage area; full matrix on main, nightly and release | P1 | 1 high, 1 low | [#957](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/957) |
| [M2-02](M2-test-strategy-and-ci.md#m2-02) | test: pytest markers and layout by level and coverage area | P1 | strategy | [#958](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/958) |
| [M2-03](M2-test-strategy-and-ci.md#m2-03) | test: coverage reporting and per-area thresholds (pytest-cov, Vitest v8) | P1 | 1 high | [#959](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/959) |
| [M2-04](M2-test-strategy-and-ci.md#m2-04) | test: API contract suite (frontend URLs, OpenAPI types, CSV/export schemas) | P1 | strategy | [#960](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/960) |
| [M2-05](M2-test-strategy-and-ci.md#m2-05) | test: Playwright end-to-end smoke suite against the Docker image | P1 | 1 high | [#961](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/961) |
| [M2-06](M2-test-strategy-and-ci.md#m2-06) | test: frontend component tests for untested units, Vitest projects by level | P1 | 1 high | [#962](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/962) |
| [M2-07](M2-test-strategy-and-ci.md#m2-07) | test: migration upgrade-path and schema-drift suite | P2 | strategy | [#963](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/963) |
| [M2-08](M2-test-strategy-and-ci.md#m2-08) | test: fix flaky and assertion-free tests | P2 | 1 high, 1 medium | [#964](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/964) |
| [M3-01](M3-reliability-and-error-handling.md#m3-01) | fix(errors): remove the remaining silent exception handlers | P2 | 3 high, 1 medium, 1 low | [#965](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/965) |
| [M3-02](M3-reliability-and-error-handling.md#m3-02) | refactor(config): one validated, UTF-8 config loader | P2 | 1 high, 6 medium, 1 low | [#966](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/966) |
| [M3-03](M3-reliability-and-error-handling.md#m3-03) | fix(jobs): route long-running work through the job queue with one status vocabulary | P2 | 1 high, 1 medium, 1 low | [#967](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/967) |
| [M3-04](M3-reliability-and-error-handling.md#m3-04) | fix(io): atomic artifact writes, subprocess timeouts, no GET side effects | P2 | 2 high, 3 medium | [#968](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/968) |
| [M3-05](M3-reliability-and-error-handling.md#m3-05) | fix(data): keep derived session state consistent | P2 | 1 high, 4 medium, 1 low | [#969](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/969) |
| [M3-06](M3-reliability-and-error-handling.md#m3-06) | fix(api): validate annotation and defect inputs; single transaction for defects | P2 | 1 high, 1 medium | [#970](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/970) |
| [M3-07](M3-reliability-and-error-handling.md#m3-07) | fix(frontend): UX safety and state-handling fixes | P2 | 1 high, 2 medium, 2 low | [#971](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/971) |
| [M3-08](M3-reliability-and-error-handling.md#m3-08) | fix(cli): share one geotag flow between CLI and headless pipeline | P2 | 1 high, 1 medium, 1 low | [#972](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/972) |
| [M3-09](M3-reliability-and-error-handling.md#m3-09) | chore(scripts): benchmark harness hygiene | P3 | 1 high, 1 medium, 3 low | [#973](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/973) |
| [M4-01](M4-performance-and-scale.md#m4-01) | perf(db): remove N+1 queries in projects, duplicate detection and GeoPackage export | P2 | 3 high | [#974](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/974) |
| [M4-02](M4-performance-and-scale.md#m4-02) | perf(backend): quadratic and blocking hot paths | P2 | 8 medium | [#975](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/975) |
| [M4-03](M4-performance-and-scale.md#m4-03) | perf(geotag, viewer): bisect telemetry interpolation; instanced gap meshes | P3 | 2 low | [#976](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/976) |
| [M5-01](M5-maintainability-and-type-safety.md#m5-01) | refactor(reconstruction): split reconstruction.py and its router | P3 | 3 high, 4 medium, 1 low | [#977](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/977) |
| [M5-02](M5-maintainability-and-type-safety.md#m5-02) | refactor(backend): deduplicate geo helpers and remove dead code | P3 | 2 high, 9 medium | [#978](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/978) |
| [M5-03](M5-maintainability-and-type-safety.md#m5-03) | refactor: reduce cyclomatic complexity >= 15 and enable ruff C901 | P3 | 15 medium | [#979](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/979) |
| [M5-04](M5-maintainability-and-type-safety.md#m5-04) | refactor(geotag): shared ffmpeg probe and csv_safe | P3 | 2 high | [#980](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/980) |
| [M5-05](M5-maintainability-and-type-safety.md#m5-05) | refactor(splat-viewer): split SplatViewerTab, type the viewer, use colour tokens | P3 | 3 high | [#981](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/981) |
| [M5-06](M5-maintainability-and-type-safety.md#m5-06) | refactor(frontend): shared helpers for job status, downloads, uploads and export cards | P3 | 6 high, 1 medium | [#982](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/982) |
| [M5-07](M5-maintainability-and-type-safety.md#m5-07) | chore(ts): enable strict and noUncheckedIndexedAccess | P3 | 2 high | [#983](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/983) |

## Method

- **Rule assets loaded:** universal, javascript, typescript, react (no Java/Spring code in the repository).
- **Repository guidance applied:** CONTRIBUTING.md test gates; docs/ARCHITECTURE.md design rules (argv-list external tools mocked in CI, lazy heavy imports, PLY contract, NULL geo_transform means not georeferenced, ruff E/F/I/UP/B at 100 columns).
- **Coverage of the scan:** every Python file under `backend/`, `src/` and `scripts/` read in full; all frontend files scanned for the asset patterns, with the tab-level components that carry the most logic read in full; tests, CI, Docker, launchers and packaging reviewed.
- **Tools:** ruff (baseline clean; extended BLE/S/C901/PLR rules for evidence), `tsc --strict` (0 errors), `noUncheckedIndexedAccess` (128 errors), eslint (clean), pip-audit and npm audit (0 known vulnerabilities), secrets grep (no hardcoded credentials), a frontend-to-OpenAPI route/method matcher (122 calls; 1 real mismatch), pytest-cov and Vitest v8 coverage.
- **Reproduced by script:** FK failures on delete, migration 0005 on a pre-projects DB, BOM-prefixed flight-log timestamps, corrupt-image import, survey-report GET 405 and empty-session KeyError.
