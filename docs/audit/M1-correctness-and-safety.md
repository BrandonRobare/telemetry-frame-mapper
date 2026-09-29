# M1 · v3.0.1 — Audit: Correctness & Safety Fixes

**Priority band:** P0/P1 · **Epic:** [#937](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/937) · **Work items:** 15 · **Findings:** 51

## Goal

Stop the defects that corrupt or lose user data, produce wrong survey or flight outputs, crash on ordinary inputs, or weaken security. Every item ships with a regression test that fails on today's code.

## Exit criteria

- [ ] All CRITICAL findings are fixed and covered by a regression test.
- [ ] No HIGH finding in the Correctness, Data integrity, Flight safety or Security categories remains open.
- [ ] Each fix's new tests run in the PR lane for its coverage area (see TEST-STRATEGY.md).

## Work items

| Key | Title | Priority | Issue |
|---|---|---|---|
| [M1-01](#m1-01) | fix(export): neutralize formula injection in the ODM georeferencing CSV | P0 | [#942](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/942) |
| [M1-02](#m1-02) | fix(ingest): stop importing unreadable images as healthy frames | P0 | [#943](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/943) |
| [M1-03](#m1-03) | fix(uploads): staging sweep and cancel must not delete importing or imported images | P0 | [#944](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/944) |
| [M1-04](#m1-04) | fix(db): deletes must not wipe artifacts before a foreign-key failure | P0 | [#945](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/945) |
| [M1-05](#m1-05) | fix(migrations): 0005 crashes on pre-projects databases; freeze the baseline | P0 | [#946](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/946) |
| [M1-06](#m1-06) | fix(flight-log): BOM, relative clocks and null-island fixes corrupt GPS sync | P0 | [#947](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/947) |
| [M1-07](#m1-07) | fix(geotag): anchor frame time to ffmpeg's start number, not the first surviving frame | P1 | [#948](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/948) |
| [M1-08](#m1-08) | fix(plan): mission lanes must cover the drawn polygon; validate plan inputs | P0 | [#949](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/949) |
| [M1-09](#m1-09) | fix(georef): products mix COLMAP, UTM and lon/lat coordinate frames | P1 | [#950](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/950) |
| [M1-10](#m1-10) | fix(reports): survey report crashes on empty sessions; surface-extraction errors pass silently | P1 | [#951](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/951) |
| [M1-11](#m1-11) | fix(export-ui): survey report 405, share-link double submit, missing revoke UI, WebODM zip download | P1 | [#952](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/952) |
| [M1-12](#m1-12) | fix(splat): profile and cut/fill volume sample a constant flat plane | P1 | [#953](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/953) |
| [M1-13](#m1-13) | fix(reconstruction): filename collisions, remote completions and job-queue status drift | P1 | [#954](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/954) |
| [M1-14](#m1-14) | fix(run): run.sh / run.bat start a frontend that cannot reach the backend (#803 regression) | P1 | [#955](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/955) |
| [M1-15](#m1-15) | fix(security): hardening sweep (secrets on disk and argv, unpinned npx, root container, error leakage) | P1 | [#956](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/956) |

<a id="m1-01"></a>
### M1-01 · fix(export): neutralize formula injection in the ODM georeferencing CSV

**Priority:** P0 · **Coverage area:** `export-share` · **Labels:** `bug`, `security`, `backend`, `priority: high` · **Issue:** [#942](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/942)

The WebODM/ODM georeferencing CSV is assembled by string concatenation from image filenames without the #863 `csv_safe` guard, and the package's CSV names do not match the zipped image names.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| CRITICAL | `UNI-SEC-002` | [`backend/routers/export.py:431-438`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/export.py#L431-L438) | ODM georeferencing CSV built by string concatenation without csv_safe |
| MEDIUM | `BP-QUAL` | [`backend/services/webodm_package.py:21-63`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/webodm_package.py#L21-L63) | WebODM package CSV names don't match the zipped image names |

**Changes to make**

- Build `odm_georeferencing.csv` with `csv.writer` and pass every text cell through `backend.core.csv_safe.csv_safe` (backend/routers/export.py:431-438).
- Make the names written into the WebODM package CSV identical to the arcnames used in the zip (backend/services/webodm_package.py:21-63).

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| integration | export-share | `tests/backend/test_webodm_package_export.py` | An image named `=HYPERLINK(...).jpg` produces a quoted, `'`-prefixed cell in odm_georeferencing.csv. |
| unit | export-share | `tests/backend/test_webodm_package_export.py` | Every filename listed in the CSV exists as a member of the produced zip. |
| contract | export-share | `tests/backend/test_csv_safe.py` | Extend the writer inventory test so any new CSV writer in backend/ must import csv_safe (grep-based contract). |

**Acceptance criteria**

- [ ] Formula-prefixed filenames are neutralized in every CSV export.
- [ ] CSV and zip names match one-to-one.

<a id="m1-02"></a>
### M1-02 · fix(ingest): stop importing unreadable images as healthy frames

**Priority:** P0 · **Coverage area:** `ingest-import` · **Labels:** `bug`, `backend`, `priority: high` · **Issue:** [#943](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/943)

`extract_exif` swallows Image.open/piexif failures, so the orchestrator's skip path never runs; quality scoring and thumbnail failures are also swallowed, leaving corrupt files flagged 'good' with no log entry.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| CRITICAL | `UNI-ERR-001` | [`backend/services/ingest_orchestrator.py:181-191`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/ingest_orchestrator.py#L181-L191) | Image quality scoring failures silently leave frames flagged 'good' |
| CRITICAL | `UNI-ERR-001` | [`backend/services/ingest.py:94-108`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/ingest.py#L94-L108) | extract_exif swallows unreadable images, so corrupt files are imported as frames |
| HIGH | `BP-QUAL` | [`backend/services/ingest_orchestrator.py:170-178`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/ingest_orchestrator.py#L170-L178) | Thumbnail generation failures are swallowed without a log entry |

**Changes to make**

- Raise a typed `UnreadableImageError` from `extract_exif` when the image cannot be opened (backend/services/ingest.py:94-108); log EXIF/date parse failures instead of `pass`.
- On a scoring failure set `flag='unscored'` (or 'error') and `usable=False`, and add a `quality_failed` SessionLogEntry (backend/services/ingest_orchestrator.py:181-191).
- Log thumbnail failures with `exc_info` and a `thumbnail_failed` log entry (ingest_orchestrator.py:170-178).

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| unit | ingest-import | `tests/backend/test_ingest.py` | `extract_exif` on 2 KB of random bytes raises UnreadableImageError (today it returns an empty dict). |
| integration | ingest-import | `tests/backend/test_ingest_orchestrator.py` | A folder with one corrupt .jpg and two valid frames imports 2 frames, skips 1, and writes an `image_skipped` log entry. |
| integration | ingest-import | `tests/backend/test_ingest_orchestrator.py` | When `score_image` raises, the frame is stored unusable with a `quality_failed` entry, never `flag='good'`. |

**Acceptance criteria**

- [ ] Corrupt inputs are skipped and logged, never imported as usable frames.
- [ ] No silent handler remains in the ingest loop.

<a id="m1-03"></a>
### M1-03 · fix(uploads): staging sweep and cancel must not delete importing or imported images

**Priority:** P0 · **Coverage area:** `ingest-import` · **Labels:** `bug`, `backend`, `priority: high` · **Issue:** [#944](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/944)

The 24 h staging sweep removes source images of sessions that were already imported from the staging directory, `/cancel` deletes an upload whose import is running, and the reservation cap counts finished imports.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `BP-DATA` | [`backend/routers/uploads.py:114-118`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/uploads.py#L114-L118) | 24h staging sweep deletes imported sessions' source images |
| HIGH | `UNI-ERR-005` | [`backend/routers/uploads.py:406-418`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/uploads.py#L406-L418) | Cancel endpoint deletes an upload that is already importing |
| MEDIUM | `BP-QUAL` | [`backend/routers/uploads.py:280-285`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/uploads.py#L280-L285) | Reservation cap counts finished imports as active uploads |

**Changes to make**

- Only sweep staging directories whose upload never reached `/complete` (backend/routers/uploads.py:114-118); move completed uploads out of staging into the session's import folder.
- Reject `/cancel` with 409 once the upload is `importing` or `complete` (uploads.py:406-418).
- Count only `uploading` reservations toward the concurrency cap (uploads.py:280-285).

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| integration | ingest-import | `tests/backend/test_uploads_router.py` | A completed upload older than 24 h keeps its images after the sweep runs; an abandoned one is removed. |
| integration | ingest-import | `tests/backend/test_uploads_router.py` | POST /cancel on an importing upload returns 409 and leaves files in place. |
| integration | ingest-import | `tests/backend/test_upload_reservation_cap.py` | Finished imports do not consume reservation slots. |

**Acceptance criteria**

- [ ] No code path deletes images referenced by a session.
- [ ] Cancel is a no-op once import started.

<a id="m1-04"></a>
### M1-04 · fix(db): deletes must not wipe artifacts before a foreign-key failure

**Priority:** P0 · **Coverage area:** `db-migrations` · **Labels:** `bug`, `backend`, `priority: high` · **Issue:** [#945](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/945)

Deleting a session with auto-import records, or a reconstruction that is referenced by a comparison or a child re-run, deletes files first and then fails the DB commit on a foreign key (reproduced), leaving rows that point at missing artifacts.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `BP-DATA` | [`backend/db/models.py:476-484`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/db/models.py#L476-L484) | Auto-imported sessions cannot be deleted (FK) after their files are already removed |
| HIGH | `UNI-ERR-004` | [`backend/routers/sessions.py:257-266`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/sessions.py#L257-L266) | Session delete removes files before the DB change can fail |
| HIGH | `BP-DATA` | [`backend/routers/reconstruction.py:796-812`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/reconstruction.py#L796-L812) | Deleting a compared or re-run reconstruction wipes artifacts then fails |

**Changes to make**

- Add `ondelete` behaviour (CASCADE for AutoImportRecord, SET NULL or explicit refusal for comparisons/parent_reconstruction_id) plus a migration (backend/db/models.py:476-484).
- Reorder deletes: delete rows in a transaction, commit, then remove files; on commit failure keep files (backend/routers/sessions.py:257-266, backend/routers/reconstruction.py:796-812).
- Return 409 with the blocking references when a delete is refused.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| integration | db-migrations | `tests/backend/test_sessions_router.py` | Deleting an auto-imported session succeeds and removes its AutoImportRecord. |
| integration | reconstruction-splat | `tests/backend/test_reconstruction_router.py` | Deleting a reconstruction used by a comparison returns 409 and its splat/PLY files still exist. |
| integration | db-migrations | `tests/backend/test_database.py` | The new ondelete migration upgrades a v3.0.0 DB containing auto-import rows and a comparison without data loss. |

**Acceptance criteria**

- [ ] A failed delete never leaves the DB pointing at deleted files.
- [ ] FK rules are enforced by schema, not by call order.

<a id="m1-05"></a>
### M1-05 · fix(migrations): 0005 crashes on pre-projects databases; freeze the baseline

**Priority:** P0 · **Coverage area:** `db-migrations` · **Labels:** `bug`, `backend`, `priority: high` · **Issue:** [#946](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/946)

Upgrading a pre-projects SQLite database raises NotImplementedError in 0005 (reproduced). The baseline builds tables from live models, so fresh and upgraded schemas can drift, and one revision has an autogenerated hash ID.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `BP-DATA` | [`backend/db/migrations/versions/0005_add_projects.py:42-53`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/db/migrations/versions/0005_add_projects.py#L42-L53) | Migration 0005 crashes upgrading a pre-projects SQLite DB |
| MEDIUM | `UNI-NAME-003` | [`backend/db/migrations/versions/db8522027afe_add_job_queue_table.py:16-17`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/db/migrations/versions/db8522027afe_add_job_queue_table.py#L16-L17) | One migration uses an autogenerated hash revision ID |
| MEDIUM | `BP-DATA` | [`backend/db/migrations/versions/0001_baseline.py:70-72`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/db/migrations/versions/0001_baseline.py#L70-L72) | Baseline migration creates tables from the live ORM models |

**Changes to make**

- Rewrite 0005 with `op.batch_alter_table` (SQLite-safe) for the projects FK (backend/db/migrations/versions/0005_add_projects.py:42-53).
- Freeze 0001 to an explicit schema snapshot without importing models (0001_baseline.py:70-72).
- Rename or alias the `db8522027afe` revision to the numbered convention, keeping the ID in `down_revision` chains.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| contract | db-migrations | `tests/backend/test_database.py` | Extend `test_legacy_upgrade_covers_every_model_column` with a pre-projects v1.x snapshot (reproduces the 0005 NotImplementedError today) and assert `compare_metadata(Base.metadata)` is empty after upgrade. |
| contract | db-migrations | `tests/backend/test_database.py` | `downgrade` to 0004 then `upgrade head` round-trips on a populated DB (0005 downgrade path). |

**Acceptance criteria**

- [ ] Every supported prior release upgrades to head.
- [ ] Fresh and upgraded schemas are identical per compare_metadata.

<a id="m1-06"></a>
### M1-06 · fix(flight-log): BOM, relative clocks and null-island fixes corrupt GPS sync

**Priority:** P0 · **Coverage area:** `flight-log-gps` · **Labels:** `bug`, `backend`, `priority: high` · **Issue:** [#947](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/947)

A UTF-8 BOM makes every DJI CSV timestamp parse as 0 (reproduced), relative millisecond clocks are stored as Unix epochs, (0, 0) points are used for interpolation, and GPS sync leaves footprints computed from the old positions.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `BP-DATA` | [`backend/services/flight_log_sync.py:34-51`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/flight_log_sync.py#L34-L51) | BOM-prefixed DJI CSV parses every timestamp as 0 |
| HIGH | `BP-QUAL` | [`backend/routers/flight_log.py:132-140`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/flight_log.py#L132-L140) | Relative log clocks (DJI/Autel ms) are stored as Unix epoch times |
| HIGH | `UNI-ERR-005` | [`backend/routers/flight_log.py:208-227`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/flight_log.py#L208-L227) | Flight-log points at (0, 0) are used for GPS interpolation |
| MEDIUM | `BP-QUAL` | [`backend/routers/flight_log.py:318-336`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/flight_log.py#L318-L336) | GPS sync updates image positions but leaves footprints stale |

**Changes to make**

- Open flight-log CSVs with `encoding='utf-8-sig'` (backend/services/flight_log_sync.py:34-51).
- Detect relative clocks (small monotonic values) and anchor them to the log's start time or reject with a clear 422 (backend/routers/flight_log.py:132-140).
- Drop points within the null-island threshold before interpolation (flight_log.py:208-227), reusing the shared GPS-fix predicate.
- Recompute footprints for images whose position changed during sync (flight_log.py:318-336).

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| unit | flight-log-gps | `tests/backend/test_flight_log_sync.py` | A BOM-prefixed DJI CSV yields the same timestamps as the BOM-less file. |
| unit | flight-log-gps | `tests/backend/test_flight_log_sync.py` | A log with 0..600000 ms offsets is anchored to its start time, not 1970. |
| integration | flight-log-gps | `tests/backend/test_flight_log_router.py` | (0, 0) rows never influence synced positions; footprints change after sync. |

**Acceptance criteria**

- [ ] Synced positions are correct for BOM, relative-clock and gap-containing logs.
- [ ] Footprints reflect synced positions.

<a id="m1-07"></a>
### M1-07 · fix(geotag): anchor frame time to ffmpeg's start number, not the first surviving frame

**Priority:** P1 · **Coverage area:** `geotag-cli` · **Labels:** `bug`, `python`, `priority: high` · **Issue:** [#948](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/948)

Deleting leading frames (e.g. the take-off) shifts every remaining frame's time and writes wrong GPS into EXIF; an 8 fps default is silently used when telemetry has no duration.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `BP-DATA` | [`src/drone_video_geotagger/frames.py:112-115`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/src/drone_video_geotagger/frames.py#L112-L115) | Frame time is measured from the first remaining frame, so trimming leading frames shifts every geotag |
| HIGH | `UNI-ANTI-001` | [`src/drone_video_geotagger/frames.py:73-74`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/src/drone_video_geotagger/frames.py#L73-L74) | Silent 8 fps fallback when telemetry has no duration |

**Changes to make**

- Compute `seconds = (frame_index - start_number) / frame_rate` with `--start-number` (default 1) in the CLI and job spec (src/drone_video_geotagger/frames.py:112-115).
- Replace the 8.0 fallback with the same 'Re-run with --frame-rate' ValueError (frames.py:73-74).

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| unit | geotag-cli | `tests/cli/test_frames.py` | Frames 21..30 at 1 fps are tagged at t=20..29 s, identical to the same frames when 1..20 are present. |
| unit | geotag-cli | `tests/cli/test_frames.py` | `infer_frame_rate` raises when telemetry_end_s <= 0. |
| integration | geotag-cli | `tests/cli/test_pipeline.py` | The headless pipeline honours `start_number` from the job spec. |

**Acceptance criteria**

- [ ] Trimming leading frames does not change any other frame's geotag.

<a id="m1-08"></a>
### M1-08 · fix(plan): mission lanes must cover the drawn polygon; validate plan inputs

**Priority:** P0 · **Coverage area:** `coverage-planning` · **Labels:** `bug`, `backend`, `priority: high` · **Issue:** [#949](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/949)

Lawnmower lanes are generated over the polygon's bounding box, so the drone flies outside the drawn area; overlap has no lower bound; KML/GPX drop terrain-following altitudes; the gap re-fly plan covers only the first gap; mission settings accept unbounded geometry values.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `UNI-ERR-005` | [`backend/routers/settings.py:66-80`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/settings.py#L66-L80) | Mission settings accept unbounded geometry values |
| HIGH | `BP-SAFETY` | [`backend/services/mission_planner.py:75-87`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/mission_planner.py#L75-L87) | Lawnmower lanes cover the bounding box, not the drawn area |
| HIGH | `BP-QUAL` | [`backend/routers/plans.py:50-53`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/plans.py#L50-L53) | Plan overlap percentages have no lower bound |
| MEDIUM | `BP-QUAL` | [`backend/services/mission_planner.py:179-211`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/mission_planner.py#L179-L211) | Terrain-following altitudes are dropped from KML/GPX exports |
| MEDIUM | `BP-QUAL` | [`backend/services/mission_planner.py:612-631`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/mission_planner.py#L612-L631) | Gap re-fly plan covers only the first gap polygon |

**Changes to make**

- Clip lanes to the target polygon (shapely intersection) before waypoint generation (backend/services/mission_planner.py:75-87).
- Declare `side_overlap_pct`/`forward_overlap_pct` as `Field(ge=0, lt=1)` (backend/routers/plans.py:50-53) and bound mission settings (backend/routers/settings.py:66-80).
- Write per-waypoint terrain-following altitude into KML/GPX (mission_planner.py:179-211).
- Plan re-fly lanes for every gap polygon (mission_planner.py:612-631).

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| unit | coverage-planning | `tests/backend/test_mission_planner.py` | For an L-shaped polygon every waypoint lies inside the polygon buffered by one lane spacing. |
| integration | coverage-planning | `tests/backend/test_plans_router.py` | Negative or >=1 overlap returns 422. |
| unit | coverage-planning | `tests/backend/test_mission_planner_ext.py` | Exported KML/GPX altitudes equal the terrain-following altitudes; a two-gap coverage result yields lanes over both gaps. |

**Acceptance criteria**

- [ ] No generated waypoint lies outside the planned area plus one lane spacing.
- [ ] Invalid plan inputs are rejected with 422.

<a id="m1-09"></a>
### M1-09 · fix(georef): products mix COLMAP, UTM and lon/lat coordinate frames

**Priority:** P1 · **Coverage area:** `reconstruction-splat` · **Labels:** `bug`, `backend`, `priority: high` · **Issue:** [#950](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/950)

3D Tiles placement ignores the solved geo-transform, the splat target-area crop compares COLMAP coordinates to lon/lat, checkpoint validation compares points against surfaces in different frames, and change detection diffs non-georeferenced reconstructions (ARCHITECTURE.md:86 says NULL geo_transform means 'not georeferenced').

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `UNI-ERR-005` | [`backend/services/reconstruction.py:1920-1935`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L1920-L1935) | Change detection compares non-georeferenced reconstructions in unrelated frames |
| HIGH | `BP-QUAL` | [`backend/services/cesium_tiles.py:40-82`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/cesium_tiles.py#L40-L82) | 3D Tiles placement ignores the solved geo-transform |
| HIGH | `BP-QUAL` | [`backend/services/quality_report.py:243-263`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/quality_report.py#L243-L263) | Checkpoint validation compares points against surfaces in different frames |
| HIGH | `BP-QUAL` | [`backend/services/splat_cleanup.py:155-173`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/splat_cleanup.py#L155-L173) | Splat target-area crop compares COLMAP coordinates with lon/lat |

**Changes to make**

- Apply `geo_transform` in tileset placement and refuse when it is NULL (backend/services/cesium_tiles.py:40-82).
- Transform the target polygon into the reconstruction frame before cropping (backend/services/splat_cleanup.py:155-173).
- Transform checkpoints and surfaces into one frame in `quality_report` (quality_report.py:243-263).
- Refuse change detection unless both reconstructions are georeferenced (reconstruction.py:1920-1935).

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| unit | reconstruction-splat | `tests/backend/test_cesium_tiles.py` | The tileset root transform equals the ECEF placement derived from a known geo_transform. |
| unit | reconstruction-splat | `tests/backend/test_splat_cleanup.py` | A synthetic splat with a known geo_transform keeps exactly the Gaussians inside a lon/lat polygon. |
| integration | reconstruction-splat | `tests/backend/test_comparisons_router.py` | Comparing a reconstruction with NULL geo_transform returns 422. |

**Acceptance criteria**

- [ ] Every geospatial product states and uses one frame; NULL geo_transform is never treated as georeferenced.

<a id="m1-10"></a>
### M1-10 · fix(reports): survey report crashes on empty sessions; surface-extraction errors pass silently

**Priority:** P1 · **Coverage area:** `export-share` · **Labels:** `bug`, `backend`, `priority: high` · **Issue:** [#951](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/951)

`/export/survey-report` returns 500 (KeyError 'gps_present') for any session with no images (reproduced), and GLB/LAS surface extraction failures return 'no points' so the quality report passes silently.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| CRITICAL | `UNI-ERR-001` | [`backend/services/quality_report.py:344-355`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/quality_report.py#L344-L355) | GLB/LAS surface extraction failures silently return no points |
| HIGH | `UNI-TEST-008` | [`backend/services/survey_report.py:87-89`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/survey_report.py#L87-L89) | Survey report crashes with KeyError for a session with no images |

**Changes to make**

- Return the full key set from `_frame_summary_section([])` (backend/services/survey_report.py:87-89).
- Log and surface extraction errors as a failed check with a reason (backend/services/quality_report.py:344-355).

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| integration | export-share | `tests/backend/test_survey_report.py` | POST /export/survey-report for an empty session returns 200 in json and html formats. |
| unit | export-share | `tests/backend/test_quality_report.py` | A corrupt GLB produces a failed surface check with the parser error, not an empty pass. |

**Acceptance criteria**

- [ ] No report endpoint 500s on an empty or partially failed session.

<a id="m1-11"></a>
### M1-11 · fix(export-ui): survey report 405, share-link double submit, missing revoke UI, WebODM zip download

**Priority:** P1 · **Coverage area:** `export-share` · **Labels:** `bug`, `frontend`, `priority: high` · **Issue:** [#952](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/952)

Both survey-report controls GET a POST-only route (405, reproduced); 'Generate Share Link' can be double-submitted and there is no UI to list or revoke links; the WebODM CSV button never downloads; the share viewer keys off an error string.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `BP-QUAL` | [`frontend/src/features/export/ExportTab.tsx:609-626`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/export/ExportTab.tsx#L609-L626) | Survey report buttons issue GET against a POST-only endpoint (405) |
| HIGH | `RX-FORM-002` | [`frontend/src/features/export/ExportTab.tsx:350-368`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/export/ExportTab.tsx#L350-L368) | Generate Share Link can be double-submitted, creating orphaned public links |
| HIGH | `UNI-ANTI-001` | [`frontend/src/features/share/ShareViewer.tsx:67-69`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/share/ShareViewer.tsx#L67-L69) | Share viewer detects the password prompt by matching the error text |
| MEDIUM | `BP-QUAL` | [`frontend/src/features/export/ExportTab.tsx:657-684`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/export/ExportTab.tsx#L657-L684) | 'Download georeferencing CSV zip' never downloads anything |

**Changes to make**

- Expose `GET /export/survey-report` (no side effects) or POST from the UI and open the returned blob (ExportTab.tsx:609-626, export.py:787).
- Move share-link creation to `useMutation`, disable while pending, and add a list + Revoke using the existing endpoints (ExportTab.tsx:350-368, export.py:753-768).
- Return the WebODM zip as a download (ExportTab.tsx:657-684).
- Return `{code: 'share_password_required'}` with 401 and branch on it in ShareViewer (ShareViewer.tsx:67-69).

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| contract | export-share | `tests/contract/test_frontend_api_contract.py (new)` | Every URL + method built in frontend/src resolves to a FastAPI route (would have caught the 405). |
| component | frontend/export | `frontend/src/features/export/ExportTab.test.tsx (new)` | Clicking 'Generate Share Link' twice sends one POST; revoke calls the revoke endpoint and removes the row. |
| component | frontend/share | `frontend/src/features/share/ShareViewer.test.tsx (new)` | A 401 with code share_password_required shows the password form. |
| e2e | export-share | `e2e/export.spec.ts (new)` | Survey report opens (200) and the WebODM zip downloads. |

**Acceptance criteria**

- [ ] Every Export tab control results in a 200 and a usable file.
- [ ] Operators can list and revoke share links from the UI.

<a id="m1-12"></a>
### M1-12 · fix(splat): profile and cut/fill volume sample a constant flat plane

**Priority:** P1 · **Coverage area:** `reconstruction-splat` · **Labels:** `bug`, `frontend`, `priority: high` · **Issue:** [#953](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/953)

The profile and volume tools use `sampler = () => groundY` and clicks intersect a flat plane, yet VolumePanel reports m³/yd³ and exports CSV.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `BP-DATA` | [`frontend/src/features/splat/SplatViewerTab.tsx:1884-1907`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/splat/SplatViewerTab.tsx#L1884-L1907) | Profile and cut/fill volume tools sample a constant flat plane |

**Changes to make**

- Gate the tools behind a real surface sampler (backend DSM or point-cloud height query endpoint) and hide them until it exists.
- Scale scene units by `geo_transform.scale` before labelling metres.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| unit | frontend/splat | `frontend/src/features/splat/measurementMath.test.ts` | `computeVolume` with a sloped sampler returns the analytic wedge volume; the UI refuses to compute without a sampler. |
| integration | reconstruction-splat | `tests/backend/test_elevation_export.py` | The new height-query endpoint returns DSM heights for known points. |

**Acceptance criteria**

- [ ] No volume or profile is displayed unless it comes from real surface heights.

<a id="m1-13"></a>
### M1-13 · fix(reconstruction): filename collisions, remote completions and job-queue status drift

**Priority:** P1 · **Coverage area:** `reconstruction-splat` · **Labels:** `bug`, `backend`, `priority: high` · **Issue:** [#954](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/954)

Multi-session runs drop frames whose filenames collide, remote-worker completions record no artifact paths, failed runs are marked 'completed' in the job queue, the duplicate-run guard misses remote/cancelling states, and handlers that return early leave queue entries 'running'.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `BP-DATA` | [`backend/services/reconstruction.py:200-216`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L200-L216) | Multi-session reconstructions silently drop frames with colliding filenames |
| HIGH | `UNI-ERR-005` | [`backend/services/reconstruction.py:2097-2104`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L2097-L2104) | Duplicate-run guard misses remote and cancelling reconstructions |
| HIGH | `BP-QUAL` | [`backend/services/reconstruction.py:2525-2552`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L2525-L2552) | Remote-worker reconstructions complete without any artifact paths |
| MEDIUM | `BP-QUAL` | [`backend/services/reconstruction.py:2410-2457`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L2410-L2457) | Failed reconstructions are marked 'completed' in the job queue |
| MEDIUM | `BP-QUAL` | [`backend/services/job_queue.py:459-464`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/job_queue.py#L459-L464) | Job handlers that return early leave the queue entry 'running' |

**Changes to make**

- Prefix staged image names with the session id (reconstruction.py:200-216).
- Persist artifact paths returned by the remote worker (reconstruction.py:2525-2552).
- Mark queue entries failed when the reconstruction fails and when a handler returns without a terminal state (reconstruction.py:2410-2457, job_queue.py:459-464).
- Use the shared live-status set in the duplicate-run guard (reconstruction.py:2097-2104).

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| integration | reconstruction-splat | `tests/backend/test_reconstruction_service.py` | Two sessions each containing DJI_0001.JPG stage 2 distinct images. |
| integration | reconstruction-splat | `tests/backend/test_remote_worker.py` | A remote completion stores splat/PLY paths reported by the worker. |
| unit | reconstruction-splat | `tests/backend/test_job_queue.py` | Handler that raises -> failed; handler that returns early -> failed with reason (replaces the sleep-based test, see M2-08). |

**Acceptance criteria**

- [ ] Job queue state always matches the reconstruction row.
- [ ] No frames are dropped for name collisions.

<a id="m1-14"></a>
### M1-14 · fix(run): run.sh / run.bat start a frontend that cannot reach the backend (#803 regression)

**Priority:** P1 · **Coverage area:** `packaging-release` · **Labels:** `bug`, `priority: high`, `area:platform` · **Issue:** [#955](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/955)

The README launchers start `npm run dev` without VITE_API_URL and Vite has no proxy, so the app renders empty; #803 fixed only dev.sh/dev.bat.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `BP-QUAL` | [`run.sh:39-42`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/run.sh#L39-L42) | run.sh / run.bat start the Vite dev server without VITE_API_URL (#803 regression) |

**Changes to make**

- Set `VITE_API_URL=http://localhost:8000` for npm in run.sh and run.bat, or add a Vite `server.proxy` for API prefixes so every launcher works.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| contract | packaging-release | `tests/backend/test_dev_launcher_contract.py` | Extend the #803 launcher contract to run.sh and run.bat (VITE_API_URL or proxy present). |

**Acceptance criteria**

- [ ] All four launchers produce a working UI.

<a id="m1-15"></a>
### M1-15 · fix(security): hardening sweep (secrets on disk and argv, unpinned npx, root container, error leakage)

**Priority:** P1 · **Coverage area:** `platform-ops` · **Labels:** `bug`, `security`, `priority: medium` · **Issue:** [#956](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/956)

Share signing key is created world-readable then chmod-ed; splat-transform runs an unpinned npm package via npx; the DJI API key is passed in argv and its error check never matches; share bundles embed absolute server paths; the Cesium token is sent to an unvalidated URL; raw exception text is returned to clients; the container runs as root; base images are tag-pinned.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| CRITICAL | `UNI-SEC-004` | [`backend/routers/sessions.py:317-319`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/sessions.py#L317-L319) | Raw exception text returned to API clients |
| HIGH | `BP-SEC` | [`backend/services/splat_transform.py:84-90`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/splat_transform.py#L84-L90) | splat-transform runs an unpinned npm package via npx |
| MEDIUM | `BP-SEC` | [`backend/services/share_links.py:32-38`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/share_links.py#L32-L38) | Share signing key written world-readable, then chmod-ed, with a create race |
| MEDIUM | `BP-SEC` | [`backend/services/dji_log_parser.py:144-157`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/dji_log_parser.py#L144-L157) | DJI API key passed on the djirecord command line |
| MEDIUM | `BP-SEC` | [`backend/services/share_bundle.py:27-49`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/share_bundle.py#L27-L49) | Share bundles embed absolute server filesystem paths |
| MEDIUM | `BP-SEC` | [`Dockerfile:38-45`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/Dockerfile#L38-L45) | Container runs the API as root |
| LOW | `BP-SEC` | [`backend/services/cesium_ion.py:180-190`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/cesium_ion.py#L180-L190) | Cesium token sent to an unvalidated onComplete URL |
| LOW | `BP-QUAL` | [`backend/services/dji_log_parser.py:232`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/dji_log_parser.py#L232) | 'API key' check can never match a lower-cased string |
| LOW | `BP-SEC` | [`Dockerfile:3-26`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/Dockerfile#L3-L26) | Docker base images are pinned by tag, not digest |

**Changes to make**

- Create the signing key with `os.open(..., O_CREAT|O_EXCL, 0o600)` (share_links.py:32-38).
- Pin `@playcanvas/splat-transform@<version>` and run it with `--no-install` from a lockfile-installed tool dir (splat_transform.py:84-90).
- Pass the DJI key via environment or stdin; fix the lower-case 'api key' check (dji_log_parser.py:144-157, 232).
- Write relative paths in share-bundle manifests; validate Cesium onComplete host; return generic messages with a correlation id (share_bundle.py:27-49, cesium_ion.py:180-190, sessions.py:317-319).
- Add `USER app` and digest-pinned base images to the Dockerfile.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| unit | export-share | `tests/backend/test_share_links.py` | The signing key file is created 0o600 and a concurrent create does not overwrite it. |
| unit | reconstruction-splat | `tests/backend/test_splat_transform.py` | The argv contains a pinned version and no bare `npx <pkg>`. |
| unit | flight-log-gps | `tests/backend/test_dji_log_parser.py` | The API key never appears in the subprocess argv. |
| contract | packaging-release | `tests/test_supply_chain_configuration.py` | Dockerfile FROM lines are digest-pinned and a USER directive precedes CMD. |

**Acceptance criteria**

- [ ] No secret on argv or world-readable on disk.
- [ ] Supply-chain test enforces image and tool pinning.

_Line links point at commit `3ec2135` (the audited `main`)._
