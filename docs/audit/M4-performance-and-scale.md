# M4 · v3.3 — Audit: Performance & Scale

**Priority band:** P2/P3 · **Epic:** [#940](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/940) · **Work items:** 3 · **Findings:** 13

## Goal

Remove N+1 queries and quadratic hot paths that grow with session, project or splat size.

## Exit criteria

- [ ] Query-count tests pin the fixed endpoints to a constant number of queries.
- [ ] Benchmarks (pytest -m perf, nightly) show the O(n^2) paths now scale near-linearly on synthetic inputs.

## Work items

| Key | Title | Priority | Issue |
|---|---|---|---|
| [M4-01](#m4-01) | perf(db): remove N+1 queries in projects, duplicate detection and GeoPackage export | P2 | [#974](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/974) |
| [M4-02](#m4-02) | perf(backend): quadratic and blocking hot paths | P2 | [#975](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/975) |
| [M4-03](#m4-03) | perf(geotag, viewer): bisect telemetry interpolation; instanced gap meshes | P3 | [#976](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/976) |

<a id="m4-01"></a>
### M4-01 · perf(db): remove N+1 queries in projects, duplicate detection and GeoPackage export

**Priority:** P2 · **Coverage area:** `platform-ops` · **Labels:** `enhancement`, `backend`, `performance`, `priority: medium` · **Issue:** [#974](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/974)

list_projects runs one COUNT per project, duplicate detection one query per session, GeoPackage export one query per flight log.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `BP-PERF` | [`backend/routers/export.py:263-283`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/export.py#L263-L283) | N+1 query for flight-log points in GeoPackage export |
| HIGH | `BP-PERF` | [`backend/services/duplicate_detection.py:36-53`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/duplicate_detection.py#L36-L53) | Duplicate-import check runs one query per existing session |
| HIGH | `BP-PERF` | [`backend/routers/projects.py:94-99`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/projects.py#L94-L99) | list_projects issues one COUNT query per project (N+1) |

**Changes to make**

- Grouped COUNT / joined loads (`selectinload`) for each endpoint.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| integration | platform-ops | `tests/backend/test_projects.py` | Query count for GET /projects is constant for 1 vs 50 projects (SQLAlchemy event counter fixture). |
| integration | ingest-import | `tests/backend/test_duplicate_detection.py` | Constant query count across 1 vs 30 sessions. |

**Acceptance criteria**

- [ ] Each endpoint issues O(1) queries regardless of row count.

<a id="m4-02"></a>
### M4-02 · perf(backend): quadratic and blocking hot paths

**Priority:** P2 · **Coverage area:** `reconstruction-splat` · **Labels:** `enhancement`, `backend`, `performance`, `priority: medium` · **Issue:** [#975](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/975)

Coverage overlap O(n²), voxel diff via Python sets, splat outlier filter O(N²) loops, cdist chunk exceeding VRAM, double image decode, ORB matching per GET, three subprocesses per 3 s /system poll, blocking I/O in an async upload handler.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| MEDIUM | `BP-PERF` | [`backend/routers/uploads.py:315-353`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/uploads.py#L315-L353) | async chunk handler does blocking file I/O on the event loop |
| MEDIUM | `BP-PERF` | [`backend/routers/system.py:412-426`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/system.py#L412-L426) | /system/resources spawns three subprocesses on every 3s poll |
| MEDIUM | `BP-PERF` | [`backend/services/reconstruction.py:1894-1900`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L1894-L1900) | Voxel diff builds Python sets of tuples per point |
| MEDIUM | `BP-PERF` | [`backend/services/coverage.py:43-49`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/coverage.py#L43-L49) | Coverage overlap computes every footprint pair (O(n^2)) |
| MEDIUM | `BP-PERF` | [`backend/services/preflight_quality.py:372-380`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/preflight_quality.py#L372-L380) | Quick report runs ORB feature matching on full-res frames per GET |
| MEDIUM | `BP-PERF` | [`backend/services/quality.py:26-39`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/quality.py#L26-L39) | Every ingested frame is decoded twice for quality scoring |
| MEDIUM | `BP-PERF` | [`backend/services/splat_cleanup.py:224-310`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/splat_cleanup.py#L224-L310) | Outlier filter degrades to O(N^2) Python loops on real splats |
| MEDIUM | `BP-PERF` | [`backend/services/splat_backends/cuda_gsplat.py:269-282`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/splat_backends/cuda_gsplat.py#L269-L282) | Initial scale k-NN allocates a 4096 x N distance matrix on the GPU |

**Changes to make**

- STRtree for overlaps; numpy voxel keys with np.unique; KD-tree (scipy cKDTree) for outliers; VRAM-aware chunking; decode once; cache the quick report; cache tool probes; make the chunk handler sync (threadpool) or use aiofiles.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| perf | coverage-planning | `tests/perf/test_coverage_scaling.py (new)` | Overlap for 2k footprints completes under a budget and scales < n^1.3 (nightly). |
| unit | reconstruction-splat | `tests/backend/test_splat_cleanup.py` | KD-tree outlier filter matches the reference result on a seeded cloud. |

**Acceptance criteria**

- [ ] Perf lane (nightly) passes budgets; results unchanged on fixtures.

<a id="m4-03"></a>
### M4-03 · perf(geotag, viewer): bisect telemetry interpolation; instanced gap meshes

**Priority:** P3 · **Coverage area:** `geotag-cli` · **Labels:** `enhancement`, `performance`, `priority: low` · **Issue:** [#976](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/976)

interpolate() scans every point twice per frame; coverage gaps render one mesh per voxel.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| LOW | `BP-PERF` | [`src/drone_video_geotagger/telemetry.py:175-190`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/src/drone_video_geotagger/telemetry.py#L175-L190) | interpolate() scans all telemetry points twice for every frame |
| LOW | `BP-PERF` | [`frontend/src/features/splat/SplatViewerTab.tsx:1364-1375`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/splat/SplatViewerTab.tsx#L1364-L1375) | Coverage gaps render one mesh and material per voxel |

**Changes to make**

- bisect on precomputed start times; THREE.InstancedMesh per gap level.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| unit | geotag-cli | `tests/cli/test_telemetry.py` | Bisect interpolation equals the linear-scan result on randomized telemetry (property test). |

**Acceptance criteria**

- [ ] Identical outputs, lower complexity.

_Line links point at commit `3ec2135` (the audited `main`)._
