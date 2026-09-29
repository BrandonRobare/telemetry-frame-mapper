# M3 · v3.2 — Audit: Reliability & Error Handling

**Priority band:** P2 · **Epic:** [#939](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/939) · **Work items:** 9 · **Findings:** 42

## Goal

Remove silent failure paths, make writes atomic and bounded, keep derived state consistent, and validate inputs at the API boundary.

## Exit criteria

- [ ] No `except Exception: pass/return` without logging remains in backend/ (enforced by ruff S110/S112/BLE001 with justified noqa only).
- [ ] Every external subprocess has a timeout; every multi-file artifact is written atomically.
- [ ] Each item has a failure-path test (the boundary/error case the finding describes).

## Work items

| Key | Title | Priority | Issue |
|---|---|---|---|
| [M3-01](#m3-01) | fix(errors): remove the remaining silent exception handlers | P2 | [#965](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/965) |
| [M3-02](#m3-02) | refactor(config): one validated, UTF-8 config loader | P2 | [#966](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/966) |
| [M3-03](#m3-03) | fix(jobs): route long-running work through the job queue with one status vocabulary | P2 | [#967](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/967) |
| [M3-04](#m3-04) | fix(io): atomic artifact writes, subprocess timeouts, no GET side effects | P2 | [#968](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/968) |
| [M3-05](#m3-05) | fix(data): keep derived session state consistent | P2 | [#969](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/969) |
| [M3-06](#m3-06) | fix(api): validate annotation and defect inputs; single transaction for defects | P2 | [#970](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/970) |
| [M3-07](#m3-07) | fix(frontend): UX safety and state-handling fixes | P2 | [#971](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/971) |
| [M3-08](#m3-08) | fix(cli): share one geotag flow between CLI and headless pipeline | P2 | [#972](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/972) |
| [M3-09](#m3-09) | chore(scripts): benchmark harness hygiene | P3 | [#973](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/973) |

<a id="m3-01"></a>
### M3-01 · fix(errors): remove the remaining silent exception handlers

**Priority:** P2 · **Coverage area:** `platform-ops` · **Labels:** `bug`, `backend`, `priority: medium` · **Issue:** [#965](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/965)

Storage breakdown blanks on any error, splat preview returns None for every failure, GLB georef embed failure is ignored, NVML errors are swallowed, scheduled backup failures are logged without cause.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `BP-QUAL` | [`backend/routers/system.py:313-331`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/system.py#L313-L331) | NVML query errors swallowed silently |
| HIGH | `BP-QUAL` | [`backend/routers/storage.py:54-68`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/storage.py#L54-L68) | Per-session storage breakdown silently becomes empty on any error |
| HIGH | `BP-QUAL` | [`backend/services/splat_backends/cuda_gsplat.py:762-763`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/splat_backends/cuda_gsplat.py#L762-L763) | Splat preview render returns None for every failure, including CUDA OOM |
| MEDIUM | `BP-QUAL` | [`backend/services/reconstruction.py:1563-1571`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L1563-L1571) | GLB georeference metadata embed failure is ignored |
| LOW | `BP-QUAL` | [`backend/services/artifact_backup_schedule.py:141-143`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/artifact_backup_schedule.py#L141-L143) | Scheduled backup failures are logged without any cause |

**Changes to make**

- Log with `exc_info` and surface an `errors` field or log entry at each site listed.
- Enable ruff BLE001/S110/S112 for backend/ with per-line justified `noqa` for intentional probes.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| integration | platform-ops | `tests/backend/test_storage_router.py` | An unreadable file in one session dir still returns the other sessions plus an error entry. |
| unit | reconstruction-splat | `tests/backend/test_splat_backends.py` | A render exception is logged (caplog) and returns None. |

**Acceptance criteria**

- [ ] Every caught exception is either re-raised, logged with cause, or reported to the caller.

<a id="m3-02"></a>
### M3-02 · refactor(config): one validated, UTF-8 config loader

**Priority:** P2 · **Coverage area:** `platform-ops` · **Labels:** `bug`, `backend`, `priority: medium` · **Issue:** [#966](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/966)

config.yaml is re-read by 18 copy-pasted getters with locale encoding and no top-level or section type validation; settings writes UTF-8 but reads locale; relative paths resolve against CWD; processed_dir changes break the static mount; the DB ignores data_dir.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `UNI-ANTI-003` | [`backend/core/config.py:186-192`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/core/config.py#L186-L192) | config.yaml load block copy-pasted into 18 getters |
| MEDIUM | `BP-QUAL` | [`backend/core/config.py:84-93`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/core/config.py#L84-L93) | config.yaml top level is never checked to be a mapping |
| MEDIUM | `BP-QUAL` | [`backend/core/config.py:85`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/core/config.py#L85) | config.yaml opened with locale encoding |
| MEDIUM | `BP-QUAL` | [`backend/core/config.py:444-461`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/core/config.py#L444-L461) | Several config sections merged without type validation |
| MEDIUM | `BP-QUAL` | [`backend/routers/settings.py:266-272`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/settings.py#L266-L272) | Settings writes config.yaml as UTF-8 but reads it with locale encoding |
| MEDIUM | `BP-QUAL` | [`backend/main.py:201-203`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/main.py#L201-L203) | Changing processed_dir at runtime breaks the /processed static mount |
| MEDIUM | `BP-QUAL` | [`backend/db/database.py:26-37`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/db/database.py#L26-L37) | SQLite DB location ignores the configured data_dir |
| LOW | `BP-QUAL` | [`backend/core/config.py:433-439`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/core/config.py#L433-L439) | dji_api_key_path resolves against CWD, not config dir |

**Changes to make**

- Add `_read_config_yaml()` (utf-8, mapping check, cached by mtime) and typed section models (pydantic).
- Resolve relative paths against the config file's directory; derive the SQLite path from data_dir; require restart (and say so) for processed_dir changes or remount.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| unit | platform-ops | `tests/backend/test_config.py` | A list-valued top level raises a clear ConfigError; a UTF-8 non-ASCII path round-trips under a cp1252 locale (monkeypatched). |
| unit | platform-ops | `tests/backend/test_database.py` | DATABASE_URL defaults to <data_dir>/drone_mapping.db. |

**Acceptance criteria**

- [ ] One loader; all getters use it; invalid config fails fast with a message naming the key.

<a id="m3-03"></a>
### M3-03 · fix(jobs): route long-running work through the job queue with one status vocabulary

**Priority:** P2 · **Coverage area:** `reconstruction-splat` · **Labels:** `bug`, `backend`, `priority: medium` · **Issue:** [#967](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/967)

Orthomosaic export bypasses the persistent job queue; 'live' statuses are defined four times; HTTP status is chosen by substring-matching exception text.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `UNI-ANTI-003` | [`backend/routers/reconstruction.py:774-776`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/reconstruction.py#L774-L776) | Four divergent definitions of 'live reconstruction' statuses |
| MEDIUM | `UNI-ORG-003` | [`backend/services/orthomosaic_export.py:249-275`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/orthomosaic_export.py#L249-L275) | Orthomosaic export bypasses the persistent job queue |
| LOW | `BP-QUAL` | [`backend/routers/reconstruction.py:431-437`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/reconstruction.py#L431-L437) | HTTP status chosen by substring-matching exception text |

**Changes to make**

- Enqueue orthomosaic export via job_queue (orthomosaic_export.py:249-275).
- Define live/terminal statuses once in backend (and export them in OpenAPI for the frontend).
- Raise typed exceptions mapped to HTTP codes instead of substring checks (routers/reconstruction.py:431-437).

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| integration | export-share | `tests/backend/test_orthomosaic_export.py` | Starting an ortho export creates a queue entry; a restart resumes or fails it. |

**Acceptance criteria**

- [ ] All background work is visible in /jobs and survives restarts consistently.

<a id="m3-04"></a>
### M3-04 · fix(io): atomic artifact writes, subprocess timeouts, no GET side effects

**Priority:** P2 · **Coverage area:** `export-share` · **Labels:** `bug`, `backend`, `priority: medium` · **Issue:** [#968](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/968)

Session archive zips are written in place; GeoPackage uses a fixed temp name; rclone has no timeout; WebODM upload opens every image at once; GET /plans/{id}/segments writes files.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `UNI-ERR-004` | [`backend/services/artifact_backup.py:304-312`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/artifact_backup.py#L304-L312) | rclone backup subprocess has no timeout |
| HIGH | `UNI-ERR-004` | [`backend/services/webodm.py:114-127`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/webodm.py#L114-L127) | WebODM task upload opens every image file at once |
| MEDIUM | `BP-QUAL` | [`backend/routers/export.py:190-201`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/export.py#L190-L201) | GeoPackage export uses a fixed temp filename |
| MEDIUM | `BP-QUAL` | [`backend/services/session_bundle.py:198-203`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/session_bundle.py#L198-L203) | Session archive zip is written in place, not atomically |
| MEDIUM | `BP-QUAL` | [`backend/routers/plans.py:216-222`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/plans.py#L216-L222) | GET /plans/{id}/segments writes KML and GPX files as a side effect |

**Changes to make**

- Write to a unique temp file in the target dir and `os.replace` (session_bundle.py:198-203, export.py:190-201).
- Add a configurable timeout to rclone (artifact_backup.py:304-312); stream WebODM uploads in batches with context-managed handles (webodm.py:114-127).
- Generate plan KML/GPX lazily in download endpoints only (plans.py:216-222).

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| unit | export-share | `tests/backend/test_session_bundle.py` | A crash mid-write (monkeypatched) leaves no partial archive at the final path. |
| unit | platform-ops | `tests/backend/test_artifact_backup.py` | A hung rclone (sleep shim) is killed at the timeout and reported failed. |
| integration | coverage-planning | `tests/backend/test_plans_router.py` | GET /segments creates no files in exports_dir. |

**Acceptance criteria**

- [ ] No partially written artifact is ever visible; no unbounded subprocess.

<a id="m3-05"></a>
### M3-05 · fix(data): keep derived session state consistent

**Priority:** P2 · **Coverage area:** `ingest-import` · **Labels:** `bug`, `backend`, `priority: medium` · **Issue:** [#969](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/969)

Review edits leave usable_count stale and flags are free text; archiving raw frames leaves stale paths; the 'COLMAP intermediates' storage rule scans a directory nothing writes; auto-import sessions reference removable media; EXIF local time is stored as UTC; interrupted imports leave photo_count 0.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `BP-QUAL` | [`backend/services/storage_lifecycle.py:179-211`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/storage_lifecycle.py#L179-L211) | 'COLMAP intermediates' storage rule scans a directory nothing writes |
| MEDIUM | `BP-QUAL` | [`backend/services/ingest.py:110-115`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/ingest.py#L110-L115) | Camera-local EXIF times are stored and served as UTC |
| MEDIUM | `BP-QUAL` | [`backend/services/ingest_orchestrator.py:234-255`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/ingest_orchestrator.py#L234-L255) | Interrupted imports leave sessions at photo_count 0 with no error |
| MEDIUM | `BP-DATA` | [`backend/services/storage_lifecycle.py:393-406`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/storage_lifecycle.py#L393-L406) | Archiving raw frames leaves sessions pointing at moved files |
| MEDIUM | `BP-QUAL` | [`backend/routers/images.py:101-137`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/images.py#L101-L137) | Review edits leave Session.usable_count stale; flags are free text |
| LOW | `BP-DATA` | [`backend/services/auto_import.py:180-206`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/auto_import.py#L180-L206) | Auto-import sessions reference files on removable media |

**Changes to make**

- Recompute usable_count on flag edits; make flags an Enum validated at the API.
- Update image paths when archiving; point the intermediates rule at real COLMAP workspaces; copy auto-imported frames or record media state; store EXIF times as naive-local with offset when known; mark interrupted imports failed on startup.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| integration | ingest-import | `tests/backend/test_images_router.py` | Flagging an image updates Session.usable_count; an unknown flag is 422. |
| integration | platform-ops | `tests/backend/test_storage_lifecycle.py` | The intermediates rule finds files written by a (fake) COLMAP run; archived frames stay resolvable. |
| unit | ingest-import | `tests/backend/test_ingest.py` | EXIF DateTimeOriginal with OffsetTimeOriginal converts to UTC; without offset stays local. |

**Acceptance criteria**

- [ ] Derived counters and paths are always consistent with rows on disk.

<a id="m3-06"></a>
### M3-06 · fix(api): validate annotation and defect inputs; single transaction for defects

**Priority:** P2 · **Coverage area:** `reconstruction-splat` · **Labels:** `bug`, `backend`, `priority: medium` · **Issue:** [#970](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/970)

Annotation lat/lon/alt/color are unvalidated; a defect and its image links are committed in two transactions.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `UNI-ERR-005` | [`backend/routers/annotations.py:16-21`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/annotations.py#L16-L21) | Annotation coordinates and color are not validated |
| MEDIUM | `BP-DATA` | [`backend/routers/defects.py:114-127`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/defects.py#L114-L127) | Defect and its image links are committed in two transactions |

**Changes to make**

- Add Field bounds and a colour regex to annotation models; create defect + links in one commit.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| integration | reconstruction-splat | `tests/backend/test_annotations_router.py` | lat=91, lon=181, color='red;' each return 422. |
| integration | platform-ops | `tests/backend/test_defects_router.py` | A failing link insert leaves no orphan defect. |

**Acceptance criteria**

- [ ] Out-of-range inputs are rejected; defects are atomic.

<a id="m3-07"></a>
### M3-07 · fix(frontend): UX safety and state-handling fixes

**Priority:** P2 · **Coverage area:** `frontend` · **Labels:** `bug`, `frontend`, `priority: medium` · **Issue:** [#971](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/971)

Reconstruction cancel has no confirmation; state setters run inside an updater; exhaustive-deps suppressed without reasons; object URLs revoked synchronously; cancelled measurement overlays are never disposed.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `UNI-CMT-006` | [`frontend/src/features/import/ImportModal.tsx:121-152`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/import/ImportModal.tsx#L121-L152) | react-hooks/exhaustive-deps suppressed without a stated reason |
| MEDIUM | `BP-QUAL` | [`frontend/src/features/splat/SplatViewerTab.tsx:1869-1882`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/splat/SplatViewerTab.tsx#L1869-L1882) | State setters called inside a setMeasurePoints updater |
| MEDIUM | `BP-QUAL` | [`frontend/src/features/reconstruct/ReconstructTab.tsx:671-680`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/reconstruct/ReconstructTab.tsx#L671-L680) | Reconstruction Cancel stops a long GPU run with one click, no confirmation |
| LOW | `BP-PERF` | [`frontend/src/features/splat/SplatViewerTab.tsx:475-563`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/splat/SplatViewerTab.tsx#L475-L563) | Measurement overlay built after cancellation is never disposed |
| LOW | `BP-QUAL` | [`frontend/src/features/splat/SplatViewerTab.tsx:1021-1028`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/splat/SplatViewerTab.tsx#L1021-L1028) | Object URL revoked synchronously after triggering the download |

**Changes to make**

- ConfirmDialog for cancel; move setters out of updaters; fix or justify each suppression (useEffectEvent); shared downloadBlob with deferred revoke; dispose cancelled Three.js groups.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| component | frontend/reconstruct | `frontend/src/features/reconstruct/ReconstructTab.test.tsx` | Cancel opens a confirmation; only confirm sends POST /cancel. |
| unit | frontend/shared | `frontend/src/shared/utils/downloadBlob.test.ts (new)` | revokeObjectURL is called after the click tick. |

**Acceptance criteria**

- [ ] Destructive actions confirm; lint suppressions all carry reasons.

<a id="m3-08"></a>
### M3-08 · fix(cli): share one geotag flow between CLI and headless pipeline

**Priority:** P2 · **Coverage area:** `geotag-cli` · **Labels:** `bug`, `python`, `priority: medium` · **Issue:** [#972](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/972)

The pipeline geotag step copies cli.run and skips the video-duration cross-check and GPS-lock warnings; --log-dir only creates an empty directory; ingest validation counts an empty GPS IFD as valid.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `UNI-ANTI-003` | [`src/drone_video_geotagger/pipeline.py:137-208`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/src/drone_video_geotagger/pipeline.py#L137-L208) | Pipeline geotag step re-implements cli.run and has drifted from it |
| MEDIUM | `UNI-ANTI-005` | [`src/drone_video_geotagger/pipeline.py:511-514`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/src/drone_video_geotagger/pipeline.py#L511-L514) | --log-dir / log_dir only creates an empty directory |
| LOW | `BP-DATA` | [`src/drone_video_geotagger/pipeline.py:256-260`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/src/drone_video_geotagger/pipeline.py#L256-L260) | Ingest validation counts an empty GPS IFD as a valid fix |

**Changes to make**

- Extract `geotag(spec) -> GeotagResult` used by both; add a FileHandler for log_dir; require lat/lon tags for validation.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| integration | geotag-cli | `tests/cli/test_pipeline.py` | Pipeline and CLI produce identical tags and warnings for the same inputs; a log file appears in log_dir. |

**Acceptance criteria**

- [ ] One implementation of the geotag flow.

<a id="m3-09"></a>
### M3-09 · chore(scripts): benchmark harness hygiene

**Priority:** P3 · **Coverage area:** `reconstruction-splat` · **Labels:** `chore`, `python`, `priority: low` · **Issue:** [#973](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/973)

Hashing/RSS helpers are copied across three scripts and have drifted; the parity harness imports resource at top level, leaks temp dirs, and depends on private backend helpers; per-candidate RSS is the process peak.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `UNI-ANTI-003` | [`scripts/metal_release_gate.py:30-31`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/scripts/metal_release_gate.py#L30-L31) | _sha256 / _tree_sha256 / _maximum_rss_bytes copied across the three benchmark scripts |
| MEDIUM | `BP-QUAL` | [`scripts/benchmark_heldout_parity.py:535-568`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/scripts/benchmark_heldout_parity.py#L535-L568) | Parity evaluator depends on private backend helpers |
| LOW | `BP-QUAL` | [`scripts/benchmark_heldout_parity.py:16`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/scripts/benchmark_heldout_parity.py#L16) | Held-out parity harness imports the Unix-only resource module at top level |
| LOW | `BP-QUAL` | [`scripts/benchmark_heldout_parity.py:470-472`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/scripts/benchmark_heldout_parity.py#L470-L472) | Bundle extraction temp directories are never removed |
| LOW | `BP-DATA` | [`scripts/benchmark_metal_presets.py:66-74`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/scripts/benchmark_metal_presets.py#L66-L74) | Per-candidate maximum_rss_bytes is the process lifetime peak |

**Changes to make**

- Add scripts/_evidence.py; lazy resource import; cleanup temp dirs; public evaluator API; per-candidate subprocess.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| unit | reconstruction-splat | `tests/test_heldout_parity_benchmark.py` | Shared helpers used by all three scripts; import succeeds with `resource` unavailable (monkeypatched). |

**Acceptance criteria**

- [ ] One copy of each evidence helper.

_Line links point at commit `3ec2135` (the audited `main`)._
