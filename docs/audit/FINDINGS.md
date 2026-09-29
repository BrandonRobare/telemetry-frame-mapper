# All findings

161 findings from the repo-audit run on 2026-09-29 (commit `3ec2135`). Severity follows the loaded rule asset for asset rule IDs (`UNI-*`, `JS-*`, `TS-*`, `RX-*`) and the skill's severity table for best-practice IDs (`BP-*`). The interactive version is `report.html` at the repository root.

| Severity | Count |
|---|---|
| CRITICAL | 5 |
| HIGH | 67 |
| MEDIUM | 72 |
| LOW | 17 |
| NITPICK | 0 |

## CRITICAL (5)

### UNI-SEC-002 · ODM georeferencing CSV built by string concatenation without csv_safe

- **Location:** [`backend/routers/export.py:431-438`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/export.py#L431-L438)
- **Category:** Security · **Rule source:** `assets/rules/universal.md:123`
- **Work item:** M1-01 (P0) _issue pending_
- **Issue:** The repo adopted backend/core/csv_safe.py for spreadsheet-formula injection (#863) and uses it for measurements.csv, but this export writes raw image filenames with f-string concatenation. A filename beginning with '=', '+', '-' or '@' becomes a live formula when an operator opens the CSV, and a filename containing a comma or quote shifts every column, corrupting the georeferencing file ODM consumes.
- **Fix:** Write rows with csv.writer and pass filename through csv_safe (or, if ODM needs the raw name, at least quote correctly and reject names starting with formula characters); add a test with '=cmd|' and comma filenames.

### UNI-ERR-001 · Image quality scoring failures silently leave frames flagged 'good'

- **Location:** [`backend/services/ingest_orchestrator.py:181-191`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/ingest_orchestrator.py#L181-L191)
- **Category:** Error handling · **Rule source:** `assets/rules/universal.md:105`
- **Work item:** M1-02 (P0) _issue pending_
- **Issue:** If OpenCV scoring raises (corrupt JPEG, unsupported mode), the exception is discarded and the image keeps flag='good', usable=True, so a frame the pipeline could not assess is treated as reconstruction-ready and counted as usable. Thumbnail failures (lines 177-178) are likewise dropped without a log line.
- **Fix:** Log the exception with the filename, mark the frame with a distinct flag such as 'unscored' (not usable by default), and add a SessionLogEntry like the skipped-image path does.

### UNI-ERR-001 · extract_exif swallows unreadable images, so corrupt files are imported as frames

- **Location:** [`backend/services/ingest.py:94-108`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/ingest.py#L94-L108)
- **Category:** Error handling · **Rule source:** `assets/rules/universal.md:105`
- **Work item:** M1-02 (P0) _issue pending_
- **Issue:** Both `Image.open` and `piexif.load` failures are caught and the empty default dict is returned. The ingest loop (ingest_orchestrator.py:107-121) relies on extract_exif raising to log `image_skipped` and skip the file, so that branch is dead: a truncated or non-image `.jpg` is imported as a frame with no size, no GPS and (because thumbnail and quality failures are also swallowed) a 'good' quality flag. Reproduced: `extract_exif` on 2 KB of random bytes returns `{'width': None, 'gps_source': 'none'}` without raising. The DateTimeOriginal parse at lines 110-115 is also `except Exception: pass`.
- **Fix:** Let Image.open errors propagate (or raise a typed `UnreadableImageError`) so the orchestrator's skip-and-log path runs, and log EXIF parse failures instead of passing.

### UNI-ERR-001 · GLB/LAS surface extraction failures silently return no points

- **Location:** [`backend/services/quality_report.py:344-355`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/quality_report.py#L344-L355)
- **Category:** Error handling · **Rule source:** `assets/rules/universal.md:105`
- **Work item:** M1-10 (P1) _issue pending_
- **Issue:** _extract_mesh_surface_points and _extract_pointcloud_surface_points (line 375) swallow every exception and return [], so a corrupt mesh, a laspy import error or a parser bug surfaces as 'No surface source ... is available' (422) with nothing logged. The minimal GLB parser also ignores bufferView.byteStride and accessor.byteOffset, so interleaved buffers yield wrong positions rather than an error.
- **Fix:** Log the exception, let unexpected errors propagate as 500, and honour byteStride/accessor.byteOffset (or use pygltflib, already used optionally in reconstruction.py).

### UNI-SEC-004 · Raw exception text returned to API clients

- **Location:** [`backend/routers/sessions.py:317-319`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/sessions.py#L317-L319)
- **Category:** Security · **Rule source:** `assets/rules/universal.md:125`
- **Work item:** M1-15 (P1) _issue pending_
- **Issue:** bulk_sessions returns str(exc) for any exception, and restore_session returns f'Invalid archive: {exc}' (line 487). SQLAlchemy and OS errors carry SQL statements and absolute filesystem paths, which reach LAN clients and share-link-adjacent UIs.
- **Fix:** Log the exception server-side and return a stable, generic message (optionally with an error code) to the client.

## HIGH (67)

### BP-QUAL · Thumbnail generation failures are swallowed without a log entry

- **Location:** [`backend/services/ingest_orchestrator.py:170-178`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/ingest_orchestrator.py#L170-L178)
- **Category:** Error handling · **Rule source:** `SKILL.md:137`
- **Work item:** M1-02 (P0) _issue pending_
- **Issue:** Any exception while creating the thumbnail directory or encoding the thumbnail (disk full, permission, decoder error) sets `thumb_path = None` with no session log entry or logger call. The UI then shows blank tiles and the operator has no record of why.
- **Fix:** Log the exception with `logger.warning(..., exc_info=True)` and add a `thumbnail_failed` SessionLogEntry, keeping the image import itself going.

### BP-DATA · 24h staging sweep deletes imported sessions' source images

- **Location:** [`backend/routers/uploads.py:114-118`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/uploads.py#L114-L118)
- **Category:** Data integrity · **Rule source:** `SKILL.md:81`
- **Work item:** M1-03 (P0) _issue pending_
- **Issue:** A browser import never leaves `imports/.browser_uploads/<id>/`: /complete sets Session.folder_path to that directory and ingest stores every Image.filepath inside it (ingest_orchestrator.py:143). `_cleanup_old_uploads` removes every child directory whose mtime is older than cleanup_after_hours with no status check, so the first /start more than 24h after an import deletes that session's original frames. Later reconstructions and exports of the session then fail on missing files.
- **Fix:** Only sweep directories whose manifest status is 'uploading' (or cancelled/error), or move completed uploads out of the staging root into a permanent imports location before ingest starts.

### UNI-ERR-005 · Cancel endpoint deletes an upload that is already importing

- **Location:** [`backend/routers/uploads.py:406-418`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/uploads.py#L406-L418)
- **Category:** Data integrity · **Rule source:** `assets/rules/universal.md:109`
- **Work item:** M1-03 (P0) _issue pending_
- **Issue:** cancel_browser_import_upload never checks state['status']. The client only skips cancel when it saw the /complete response (frontend/src/shared/api/browserUpload.ts:124-131), so a lost /complete response, a second tab, or any LAN client can cancel an upload whose import is running and rmtree the session's image folder while ingest reads it.
- **Fix:** Reject cancel with 409 when status is 'importing' or a session_id is set, and add a router test for cancel-after-complete.

### BP-DATA · Auto-imported sessions cannot be deleted (FK) after their files are already removed

- **Location:** [`backend/db/models.py:476-484`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/db/models.py#L476-L484)
- **Category:** Data integrity · **Rule source:** `SKILL.md:81`
- **Work item:** M1-04 (P0) _issue pending_
- **Issue:** AutoImportRecord.session_id is a NOT NULL foreign key with no ondelete and no ORM relationship on Session, and SQLite foreign keys are ON (database.py:47). Deleting a watch-folder session raises IntegrityError: FOREIGN KEY constraint failed (reproduced against the models during this audit). _delete_session (routers/sessions.py:257-266) calls cleanup_session_artifacts before db.delete, so the session's artifacts are gone while the row, and a 500, remain.
- **Fix:** Add ondelete='CASCADE' (migration) or a Session.auto_import_records cascade relationship, and delete DB rows before removing files, with a regression test deleting an auto-imported session.

### UNI-ERR-004 · Session delete removes files before the DB change can fail

- **Location:** [`backend/routers/sessions.py:257-266`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/sessions.py#L257-L266)
- **Category:** Error handling · **Rule source:** `assets/rules/universal.md:108`
- **Work item:** M1-04 (P0) _issue pending_
- **Issue:** Artifacts are deleted from disk first and the row is deleted afterwards. Any flush/commit failure (the FK failure above, a locked DB) leaves a session whose files are gone; delete_project's own error text admits this ('artifacts removed before the failure').
- **Fix:** Flush the row deletion first, commit, then remove files (or collect paths and delete them only after a successful commit).

### BP-DATA · Deleting a compared or re-run reconstruction wipes artifacts then fails

- **Location:** [`backend/routers/reconstruction.py:796-812`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/reconstruction.py#L796-L812)
- **Category:** Data integrity · **Rule source:** `SKILL.md:81`
- **Work item:** M1-04 (P0) _issue pending_
- **Issue:** SessionComparison.reconstruction_a_id/b_id and Reconstruction.parent_reconstruction_id are FKs with no cascade or ORM relationship on the referenced row. Deleting a reconstruction that appears in any comparison or has a dense-rerun child raises IntegrityError: FOREIGN KEY constraint failed (reproduced during this audit), but cleanup_reconstruction_artifacts has already deleted its splat, LODs and exports, so the user gets a 500 and a broken reconstruction row.
- **Fix:** Decide the semantics (block with 409 listing dependents, or cascade-delete comparisons and null children's parent_reconstruction_id), enforce it before touching files, and test both references.

### BP-DATA · Migration 0005 crashes upgrading a pre-projects SQLite DB

- **Location:** [`backend/db/migrations/versions/0005_add_projects.py:42-53`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/db/migrations/versions/0005_add_projects.py#L42-L53)
- **Category:** Database migrations · **Rule source:** `SKILL.md:81`
- **Work item:** M1-05 (P0) _issue pending_
- **Issue:** When sessions has no project_id column (a database created before projects existed, which 0001's docstring promises to upgrade), 0005 calls op.create_foreign_key outside batch mode. Alembic's SQLite dialect raises NotImplementedError('No support for ALTER of constraints in SQLite dialect'), reproduced during this audit by upgrading a minimal legacy sessions table, so init_db() fails and the app will not start. The legacy-upgrade tests never hit this path because they build the legacy DB from current models, which already include project_id.
- **Fix:** Wrap the column+FK creation in `with op.batch_alter_table('sessions') as batch:` and add a test that upgrades a sessions table created without project_id.

### BP-DATA · BOM-prefixed DJI CSV parses every timestamp as 0

- **Location:** [`backend/services/flight_log_sync.py:34-51`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/flight_log_sync.py#L34-L51)
- **Category:** Data integrity · **Rule source:** `SKILL.md:81`
- **Work item:** M1-06 (P0) _issue pending_
- **Issue:** parse_flight_log_csv detects the DJI contract with a utf-8-sig reader, but parse_dji_csv re-decodes with plain utf-8, so a BOM-prefixed file (common from Excel/Windows exports) yields a first header of '\ufefftime(millisecond)'. row.get('time(millisecond)', 0) then silently defaults, and every point gets timestamp_s 0.0 (reproduced during this audit), so GPS sync matches nothing or everything to one instant. Non-UTF-8 input also raises an uncaught UnicodeDecodeError (500).
- **Fix:** Reuse _csv_reader/_require_headers/_parse_required_rows for the DJI contract (utf-8-sig, required timestamp column, per-row errors) instead of defaulting missing values to 0.

### BP-QUAL · Relative log clocks (DJI/Autel ms) are stored as Unix epoch times

- **Location:** [`backend/routers/flight_log.py:132-140`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/flight_log.py#L132-L140)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M1-06 (P0) _issue pending_
- **Issue:** DJI 'time(millisecond)' and Autel 'Time(ms)' are, in the vendor exports these contracts are named after, elapsed time since the log started, but they are converted as seconds since 1970. Real image timestamps (2020s) can then never fall within the +/-300 s offset preview window. The router tests hide this by using images timestamped 1970-01-01 (tests/backend/test_flight_log_router.py:10). Needs confirming against a real FlightRecord/Autel export.
- **Fix:** Anchor relative clocks to an absolute start (e.g. the CSV's datetime(utc)/CUSTOM.updateTime column or the first image time) and add a fixture based on a real export with realistic image timestamps.

### UNI-ERR-005 · Flight-log points at (0, 0) are used for GPS interpolation

- **Location:** [`backend/routers/flight_log.py:208-227`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/flight_log.py#L208-L227)
- **Category:** Validation · **Rule source:** `assets/rules/universal.md:109`
- **Work item:** M1-06 (P0) _issue pending_
- **Issue:** The DJI binary parser defaults missing coordinates to 0.0 (dji_log_parser.py:275-276) and pre-GPS-lock frames are persisted as-is; the CSV parsers only range-check. Apply-sync then interpolates between (0, 0) and the first real fix, writing coordinates thousands of km off into images near takeoff. Ingest already has filter_zero_gps for images, but flight logs have no equivalent.
- **Fix:** Drop (or mark invalid) log points with 0,0 / missing coordinates before persisting and before interpolation, and test sync around a no-lock prefix.

### UNI-ERR-005 · Mission settings accept unbounded geometry values

- **Location:** [`backend/routers/settings.py:66-80`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/settings.py#L66-L80)
- **Category:** Validation · **Rule source:** `assets/rules/universal.md:109`
- **Work item:** M1-08 (P0) _issue pending_
- **Issue:** altitude_ft, fov_horizontal_deg/fov_vertical_deg, image_width_px/height, lane_spacing_ft, battery_range_m and flight_log_match_tolerance_sec have no bounds, although overlaps and fps are bounded. A FOV of 0 or 180 degrees or a negative altitude is persisted and then drives AppConfig.__post_init__ (tan of 90 degrees) and every footprint/mission computation.
- **Fix:** Add Field bounds (e.g. altitude_ft gt=0, fov 1-179, image sizes gt=0, tolerances ge=0) and a test per bound.

### BP-SAFETY · Lawnmower lanes cover the bounding box, not the drawn area

- **Location:** [`backend/services/mission_planner.py:75-87`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/mission_planner.py#L75-L87)
- **Category:** Flight safety · **Rule source:** `SKILL.md:81`
- **Work item:** M1-08 (P0) _issue pending_
- **Issue:** Every lane runs from the polygon's min to max latitude and is never intersected with the polygon (routers/plans.py does not clip either). For any non-rectangular target area (L-shape, diagonal parcel), the exported KML/GPX flies outside the operator's drawn boundary, possibly over neighbouring or restricted property, and the distance/battery estimates are inflated.
- **Fix:** Intersect each lane with the target polygon (shapely LineString.intersection, handling MultiLineString segments and ordering) before computing distances, and add tests with concave and rotated polygons.

### BP-QUAL · Plan overlap percentages have no lower bound

- **Location:** [`backend/routers/plans.py:50-53`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/plans.py#L50-L53)
- **Category:** Validation · **Rule source:** `SKILL.md:137`
- **Work item:** M1-08 (P0) _issue pending_
- **Issue:** `PlanIn.side_overlap_pct` / `forward_overlap_pct` are bare floats; the handler only rejects values >= 1.0. A negative overlap (or 0 from a slider bug) is accepted and produces lane spacing wider than the camera footprint, i.e. a plan with coverage gaps that still reports success.
- **Fix:** Declare them as `Field(ge=0.0, lt=1.0)` on the model (and drop the manual checks at lines 106-109) so the API rejects out-of-range overlap with a 422.

### BP-DATA · Frame time is measured from the first remaining frame, so trimming leading frames shifts every geotag

- **Location:** [`src/drone_video_geotagger/frames.py:112-115`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/src/drone_video_geotagger/frames.py#L112-L115)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M1-07 (P1) _issue pending_
- **Issue:** `seconds = (frame_index - first_index) / frame_rate` anchors t=0 to whatever frame sorts first. The documented extraction (`ffmpeg ... frame_%05d.jpg`, README.md:54) numbers frames from 1, so deleting the take-off frames 00001-00020 before tagging silently moves every remaining frame 20/fps seconds earlier in the telemetry and writes wrong GPS into EXIF. The gap check only looks for internal gaps and does not run at all when --frame-rate is given.
- **Fix:** Compute time from ffmpeg's start number (`(frame_index - start_number) / frame_rate`, default start_number=1, exposed as a CLI/job option) instead of from the first surviving frame, and add a regression test that drops leading frames.

### UNI-ANTI-001 · Silent 8 fps fallback when telemetry has no duration

- **Location:** [`src/drone_video_geotagger/frames.py:73-74`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/src/drone_video_geotagger/frames.py#L73-L74)
- **Category:** Correctness · **Rule source:** `assets/rules/universal.md:86`
- **Work item:** M1-07 (P1) _issue pending_
- **Issue:** When `telemetry_end_s <= 0`, `infer_frame_rate` returns a hard-coded 8.0 without warning. Every frame is then placed on the time axis at an arbitrary rate, which is exactly the silent mis-geotag the other branches of this function raise for.
- **Fix:** Raise the same 'Re-run with --frame-rate' ValueError as the non-contiguous and duration-mismatch branches instead of guessing.

### UNI-ERR-005 · Change detection compares non-georeferenced reconstructions in unrelated frames

- **Location:** [`backend/services/reconstruction.py:1920-1935`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L1920-L1935)
- **Category:** Correctness · **Rule source:** `assets/rules/universal.md:109`
- **Work item:** M1-09 (P1) _issue pending_
- **Issue:** _load_reconstruction_points_utm falls back to _LOCAL_FRAME_GEO, so for a reconstruction whose geo_transform is NULL the points stay in its arbitrary COLMAP frame and scale. start_session_comparison (line 2000-2016) only checks status == 'complete', so comparing two such runs (or one georeferenced and one not) voxel-diffs unrelated coordinate systems and reports mostly 'new'/'removed' cells as real change. docs/ARCHITECTURE.md:86 requires consumers to treat NULL as 'not georeferenced' rather than silently using untransformed coordinates.
- **Fix:** Reject comparisons (422 with a clear message) unless both reconstructions have a solved geo_transform, and test the rejection.

### BP-QUAL · 3D Tiles placement ignores the solved geo-transform

- **Location:** [`backend/services/cesium_tiles.py:40-82`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/cesium_tiles.py#L40-L82)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M1-09 (P1) _issue pending_
- **Issue:** build_tileset places the bundled GLB as if it were East-North-Up metres at the image GPS centroid. The mesh is exported in COLMAP's arbitrary-scale frame (the COLMAP->UTM similarity transform is only written to a sidecar, reconstruction.py:1538-1553), and share_bundle.py:208 calls build_tileset(images, glb) without rec.geo_transform, so tilesets in share bundles and Cesium ion uploads have wrong scale and orientation even when a transform was solved. The code's own ponytail note names this fit as the revisit trigger, and it now exists (georeferencing_solve.py).
- **Fix:** Pass the reconstruction's geo_transform into build_tileset and compose scale, rotation, translation and UTM origin into root.transform, falling back to the centroid approximation only when geo_transform is NULL (and flag that in the bundle manifest).

### BP-QUAL · Checkpoint validation compares points against surfaces in different frames

- **Location:** [`backend/services/quality_report.py:243-263`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/quality_report.py#L243-L263)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M1-09 (P1) _issue pending_
- **Issue:** Checkpoints are documented as 'local reconstruction coordinates' (routers/reconstruction.py:412-417), but the surface source is chosen by artifact availability: the mesh GLB and splat are in COLMAP's arbitrary frame, while the cached LAS point cloud is in UTM whenever a geo-transform exists (reconstruction.py:1259-1260). The same checkpoints therefore produce different 'accuracy' numbers depending on which exports happen to exist, and surveyed real-world coordinates are compared against unscaled COLMAP units, all reported as metres.
- **Fix:** Transform every surface source into one declared frame (UTM via geo_transform, rejecting non-georeferenced reconstructions), accept checkpoints in WGS84/UTM, and include the frame in the response; add tests per source type.

### BP-QUAL · Splat target-area crop compares COLMAP coordinates with lon/lat

- **Location:** [`backend/services/splat_cleanup.py:155-173`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/splat_cleanup.py#L155-L173)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M1-09 (P1) _issue pending_
- **Issue:** POST /reconstruction/{id}/cleanup passes the TargetArea GeoJSON (WGS84 degrees) straight through (routers/reconstruction.py:1302-1308), and the crop tests Gaussian means in COLMAP's arbitrary local frame against it. With real data the crop keeps nothing or everything. The unit test (tests/backend/test_splat_cleanup.py:235-257) uses a polygon already in the splat's frame, so it cannot catch this. The per-point Point() loop is also O(N) Python for ~1M Gaussians.
- **Fix:** Transform the polygon into the splat frame with the inverse of rec.geo_transform (reject non-georeferenced reconstructions), use shapely.contains_xy vectorised, and add a test with a georeferenced fixture.

### UNI-TEST-008 · Survey report crashes with KeyError for a session with no images

- **Location:** [`backend/services/survey_report.py:87-89`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/survey_report.py#L87-L89)
- **Category:** Correctness · **Rule source:** `assets/rules/universal.md:147`
- **Work item:** M1-10 (P1) _issue pending_
- **Issue:** `_frame_summary_section([])` returns early without `gps_present`/`camera`, but `_render_html` always reads `frame_s["gps_present"]` (line 354), and the HTML is rendered even for format=json. Any session with zero images, including the photo_count-0 sessions an interrupted import leaves behind, gets a 500 from /export/survey-report. Reproduced: POST on an empty session raises `KeyError: 'gps_present'` at survey_report.py:354. No test covers the empty-session boundary.
- **Fix:** Return the full key set (`gps_present: 0, camera: None`) from the early branch and add an empty-session test for json and html formats.

### BP-QUAL · Survey report buttons issue GET against a POST-only endpoint (405)

- **Location:** [`frontend/src/features/export/ExportTab.tsx:609-626`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/export/ExportTab.tsx#L609-L626)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M1-11 (P1) _issue pending_
- **Issue:** 'View / Print Report' opens `/export/survey-report?...&format=html` with `window.open` and 'Download JSON' is an `<a href download>`; both are GET requests. The backend registers the route only as `@router.post("/survey-report")` (backend/routers/export.py:787), so both controls return 405 Method Not Allowed. Reproduced with the test client: GET html -> 405, GET json -> 405. Backend tests only exercise POST, and no frontend test covers the buttons.
- **Fix:** Expose the report as `@router.get("/survey-report")` (it has no side effects) or have the UI POST and open the returned HTML/Blob, and add a contract test that the URLs the UI builds resolve to a 200.

### RX-FORM-002 · Generate Share Link can be double-submitted, creating orphaned public links

- **Location:** [`frontend/src/features/export/ExportTab.tsx:350-368`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/export/ExportTab.tsx#L350-L368)
- **Category:** Security · **Rule source:** `assets/rules/react.md:136`
- **Work item:** M1-11 (P1) _issue pending_
- **Issue:** `handleShareLink` runs a bare async function with no pending state, and the button (line 574-579) is never disabled. Each click POSTs a new token, and only the last response is shown. Earlier tokens stay live public links the operator never saw. The UI also has no way to list or revoke links even though the backend exposes `GET .../share-links` and `POST .../share-links/{id}/revoke` (export.py:753, 768) and the card text promises 'revocable' links.
- **Fix:** Use `useMutation` and disable the button while `isPending`, and add a share-link list with a Revoke action backed by the existing endpoints.

### UNI-ANTI-001 · Share viewer detects the password prompt by matching the error text

- **Location:** [`frontend/src/features/share/ShareViewer.tsx:67-69`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/share/ShareViewer.tsx#L67-L69)
- **Category:** Robustness · **Rule source:** `assets/rules/universal.md:86`
- **Work item:** M1-11 (P1) _issue pending_
- **Issue:** The password form only appears when the error message string equals the backend's `detail` text (share_links.py:131). Any wording change, localisation or proxy error body silently turns a password-protected link into a generic 403 page.
- **Fix:** Have the backend return a machine-readable code (e.g. 401 with `{"code": "share_password_required"}`) and branch on the HTTP status/code, not the message.

### BP-DATA · Profile and cut/fill volume tools sample a constant flat plane

- **Location:** [`frontend/src/features/splat/SplatViewerTab.tsx:1884-1907`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/splat/SplatViewerTab.tsx#L1884-L1907)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M1-12 (P1) _issue pending_
- **Issue:** Both tools pass `sampler = () => groundY`, a constant. Measurement clicks also land on that same horizontal plane (useViewerCoords.ts:157-161 intersects the ray with `Plane(0,1,0, -groundY)`, never the splat). The elevation profile is therefore always a flat line, and the 'Cut / Fill Volume' is polygon area x (groundY - 0) in scene units, yet VolumePanel shows it as m³/yd³ and offers a CSV export. A surveyor gets a plausible-looking but meaningless stockpile volume.
- **Fix:** Hide or label the profile/volume tools as unavailable until a real surface sampler exists (DSM/point-cloud height query from the backend), and convert scene units with geo_transform.scale before labelling results in metres.

### BP-DATA · Multi-session reconstructions silently drop frames with colliding filenames

- **Location:** [`backend/services/reconstruction.py:200-216`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L200-L216)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M1-13 (P1) _issue pending_
- **Issue:** The COLMAP workspace is keyed by bare image filename and skips any name already present. Ingest only makes filenames unique within one session (ingest_orchestrator.py:35 _unique_filename), and DJI cameras restart DJI_0001.JPG numbering per card, so a merge of two sessions keeps only the first session's DJI_0001.JPG. The dropped frame is still counted in frames_used and ReconstructionFrame, and _store_reprojection_errors (line 690) and _registered_image_names map COLMAP results back by filename, attributing one session's error to both images.
- **Fix:** Name workspace images by a unique key (e.g. f'{img.id}_{safe_name}'), map COLMAP output back through that key, and add a multi-session test with colliding filenames.

### UNI-ERR-005 · Duplicate-run guard misses remote and cancelling reconstructions

- **Location:** [`backend/services/reconstruction.py:2097-2104`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L2097-L2104)
- **Category:** Validation · **Rule source:** `assets/rules/universal.md:109`
- **Work item:** M1-13 (P1) _issue pending_
- **Issue:** start_reconstruction only treats pending/running_colmap/running_gsplat as live, while the job queue's _LIVE_RECONSTRUCTION_STATUSES (job_queue.py:55-61) also includes running_remote and cancelling. A second reconstruction can therefore be started for a session whose remote run or cancellation is still in flight; the check-then-insert is also unlocked, so two concurrent POSTs both pass.
- **Fix:** Reuse a single shared LIVE_RECONSTRUCTION_STATUSES constant and perform the check and insert under a lock or unique partial index.

### BP-QUAL · Remote-worker reconstructions complete without any artifact paths

- **Location:** [`backend/services/reconstruction.py:2525-2552`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L2525-L2552)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M1-13 (P1) _issue pending_
- **Issue:** docs/SETUP.md:164 requires the worker to write artifacts to the shared exports path, but on 'complete' the API only stores counts/metrics and the geo-transform. splat_path, splat_preview_path, splat_medium_path, thumb_path and training_metrics stay NULL, so every consumer that gates on rec.splat_path (viewer download, coverage gaps, LAS/mesh/semantic exports in routers/reconstruction.py:869-1536) treats a successful remote run as having no splat. tests/backend/test_remote_worker.py only asserts status == 'complete'.
- **Fix:** On remote completion, resolve the conventional exports/<id>/splat.ply (+ LODs, thumbnail) inside the configured exports root, record the paths that exist, and fail the job if the splat is missing; extend the remote-worker tests to assert the paths.

### BP-QUAL · run.sh / run.bat start the Vite dev server without VITE_API_URL (#803 regression)

- **Location:** [`run.sh:39-42`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/run.sh#L39-L42)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M1-14 (P1) _issue pending_
- **Issue:** The everyday launchers documented in README.md:63-64 run `npm run dev` with no VITE_API_URL, and vite.config.ts has no dev proxy. As #803 recorded when fixing dev.sh/dev.bat, every API call then hits the Vite server on :5173 and the app renders empty. run.bat:41 has the same gap. The fix commit 7473a2f touched only the dev scripts.
- **Fix:** Export `VITE_API_URL=http://localhost:8000` for the npm process in run.sh and run.bat (or add a `server.proxy` for the API prefixes in vite.config.ts so every launcher works).

### BP-SEC · splat-transform runs an unpinned npm package via npx

- **Location:** [`backend/services/splat_transform.py:84-90`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/splat_transform.py#L84-L90)
- **Category:** Supply chain · **Rule source:** `SKILL.md:81`
- **Work item:** M1-15 (P1) _issue pending_
- **Issue:** Every cleanup/compress call executes `npx @playcanvas/splat-transform` with no version, so the backend downloads and runs whatever version the npm registry serves at that moment, with the API process's privileges and filesystem access. This bypasses the repo's otherwise strict supply-chain controls (pinned actions, uv lock checks, pip-audit, npm audit in CI) and fails offline.
- **Fix:** Pin an exact version (npx --yes @playcanvas/splat-transform@X.Y.Z), or better, vendor it as a package.json dependency with a lockfile and invoke the local binary; add it to the supply-chain configuration test.

### BP-TEST · Every PR runs the full CI matrix; there is no path filtering

- **Location:** [`.github/workflows/ci.yml:29-31`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/.github/workflows/ci.yml#L29-L31)
- **Category:** CI / test strategy · **Rule source:** `SKILL.md:81`
- **Work item:** M2-01 (P1) _issue pending_
- **Issue:** `on: pull_request` has no `paths` filters and no change-detection job, so a docs-only or frontend-only PR still runs the Python 3.11+3.12 suites, Docker build and smoke, wheel build, the Windows packaging job and the macOS job (brew install of ffmpeg/exiftool/colmap plus a third full pytest run and a bundle build). The Python suite itself takes about 52 s locally (1387 passed, 39 skipped); the cost is the matrix, not the tests.
- **Fix:** Add a `changes` job (dorny/paths-filter or `git diff --name-only`) that outputs backend/frontend/cli/packaging/docs flags, gate each job on the matching flag, and keep the full matrix on `push: main`, nightly schedule and release (see docs/audit/TEST-STRATEGY.md).

### BP-TEST · No coverage measurement or thresholds for Python or frontend

- **Location:** [`pyproject.toml:103-106`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/pyproject.toml#L103-L106)
- **Category:** CI / test strategy · **Rule source:** `SKILL.md:123`
- **Work item:** M2-03 (P1) _issue pending_
- **Issue:** pytest runs without pytest-cov and vite.config.ts `test:` (lines 30-33) has no coverage provider, so nobody can see which of the 56 services, 28 routers or 126 frontend units are exercised, and coverage can silently regress. The file-level mapping in this audit found 59 of 126 frontend units with no test importing them.
- **Fix:** Add pytest-cov (`--cov=backend --cov=src --cov-report=xml`) and @vitest/coverage-v8 with per-area thresholds, publish reports as CI artifacts, and ratchet the thresholds upward.

### BP-TEST · No end-to-end test exercises the real UI against the real API

- **Location:** [`frontend/package.json:14`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/package.json#L14)
- **Category:** CI / test strategy · **Rule source:** `SKILL.md:123`
- **Work item:** M2-05 (P1) _issue pending_
- **Issue:** Frontend tests run in Vitest with mocked `fetch`, and backend tests use TestClient. Nothing runs the built SPA against the FastAPI app, which is why the survey-report buttons (GET against a POST-only route) and the undownloadable WebODM CSV zip went unnoticed. The Docker smoke job only checks /health.
- **Fix:** Add a Playwright smoke suite (import from browser upload -> map -> review -> reconstruct with mocked external tools -> export links return 200) run against the Docker image nightly and on release, plus an API-contract test that every URL built in frontend/src resolves to a route with the right method.

### RX-TEST-003 · Component tests drive interactions with fireEvent; user-event is not installed

- **Location:** [`frontend/src/App.test.tsx:1`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/App.test.tsx#L1)
- **Category:** Test quality · **Rule source:** `assets/rules/react.md:213`
- **Work item:** M2-06 (P1) _issue pending_
- **Issue:** 14 of the 18 React Testing Library test files use `fireEvent`, and `@testing-library/user-event` is not a devDependency. fireEvent dispatches single synthetic events (no focus, pointer or keyboard sequence), so tests of the import modal focus trap, ESC handling and form submission do not reflect real user behaviour.
- **Fix:** Add @testing-library/user-event and migrate interaction tests to `const user = userEvent.setup()` per test.

### UNI-TEST-009 · Job-queue test sleeps 1 s for a background worker and accepts either outcome

- **Location:** [`tests/backend/test_job_queue.py:458-479`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/tests/backend/test_job_queue.py#L458-L479)
- **Category:** Test quality · **Rule source:** `assets/rules/universal.md:148`
- **Work item:** M2-08 (P2) _issue pending_
- **Issue:** `test_no_handler_marks_as_failed` starts the real worker thread, sleeps a fixed second and then asserts `stored.status in ("failed", "completed")`. On a slow runner the job may still be 'pending' (flaky failure), and the assertion passes even if the missing handler is wrongly marked completed, which is the bug class the audit found in job_queue.py:459-464.
- **Fix:** Run the dispatch synchronously (call the worker's `_run_one(job_id)` directly) or poll with a deadline, and assert `status == "failed"` with the expected error text.

### BP-QUAL · NVML query errors swallowed silently

- **Location:** [`backend/routers/system.py:313-331`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/system.py#L313-L331)
- **Category:** Error handling · **Rule source:** `SKILL.md:137`
- **Work item:** M3-01 (P2) _issue pending_
- **Issue:** Any NVML failure (driver reset, device lost) is caught with `except Exception: pass`, so the GPU readout silently turns blank with nothing in the backend log to diagnose it.
- **Fix:** Catch pynvml.NVMLError specifically and log it once at debug/warning level before returning the unavailable status.

### BP-QUAL · Per-session storage breakdown silently becomes empty on any error

- **Location:** [`backend/routers/storage.py:54-68`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/storage.py#L54-L68)
- **Category:** Error handling · **Rule source:** `SKILL.md:137`
- **Work item:** M3-01 (P2) _issue pending_
- **Issue:** A single unreadable file or a session directory removed mid-walk (FileNotFoundError from `f.stat()`) discards the whole per-session breakdown and returns `[]`, which the Storage tab shows as 'no session data' with no error.
- **Fix:** Skip individual unreadable entries (catch OSError per file), log the failure, and return an `errors` field instead of blanking the whole list.

### BP-QUAL · Splat preview render returns None for every failure, including CUDA OOM

- **Location:** [`backend/services/splat_backends/cuda_gsplat.py:762-763`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/splat_backends/cuda_gsplat.py#L762-L763)
- **Category:** Error handling · **Rule source:** `SKILL.md:137`
- **Work item:** M3-01 (P2) _issue pending_
- **Issue:** The whole preview render (PLY read, PCA framing, rasterization, JPEG save) is wrapped in `except Exception: return None` with no logging. Out-of-memory, a corrupt PLY and a programming error all look identical to 'no preview', which makes regressions in the renderer invisible.
- **Fix:** Log the exception with `logger.warning(..., exc_info=True)` before returning None, or narrow the handler to the expected runtime/OOM errors.

### UNI-ANTI-003 · config.yaml load block copy-pasted into 18 getters

- **Location:** [`backend/core/config.py:186-192`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/core/config.py#L186-L192)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:88`
- **Work item:** M3-02 (P2) _issue pending_
- **Issue:** The same open/yaml.safe_load/FileNotFoundError block is repeated in 18 functions (lines 84, 187, 211, 240, 276, 325, 339, 393, 403, 427, 446, 466, 479, 493, 503, 598, 633, 671). Each getter re-reads and re-parses config.yaml from disk on every call, and any fix (encoding, top-level type check) has to be made 18 times.
- **Fix:** Extract one `_read_config_yaml(path) -> dict` helper that opens with encoding='utf-8', validates the top level is a mapping, and have every getter call it.

### UNI-ANTI-003 · Four divergent definitions of 'live reconstruction' statuses

- **Location:** [`backend/routers/reconstruction.py:774-776`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/reconstruction.py#L774-L776)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:88`
- **Work item:** M3-03 (P2) _issue pending_
- **Issue:** The live-status set is defined here, again as job_queue._LIVE_RECONSTRUCTION_STATUSES, and inline as a narrower three-item list in services/reconstruction.py:2099 and in start_dense_rerun (line 651). The narrower copies are why duplicate runs can start during running_remote/cancelling.
- **Fix:** Define one LIVE_RECONSTRUCTION_STATUSES constant (ideally a StrEnum of statuses) in a shared module and import it everywhere.

### UNI-ERR-004 · rclone backup subprocess has no timeout

- **Location:** [`backend/services/artifact_backup.py:304-312`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/artifact_backup.py#L304-L312)
- **Category:** Error handling · **Rule source:** `assets/rules/universal.md:108`
- **Work item:** M3-04 (P2) _issue pending_
- **Issue:** A stalled network remote or an interactive rclone prompt blocks this call forever. For the scheduled backup this wedges the scheduler thread with _run_lock held (status stays 'running'); for POST /storage/backup it pins a worker thread and keeps the multi-GB temporary snapshot on disk.
- **Fix:** Pass a generous, configurable timeout= and treat subprocess.TimeoutExpired as BackupError; consider --contimeout/--timeout rclone flags.

### UNI-ERR-004 · WebODM task upload opens every image file at once

- **Location:** [`backend/services/webodm.py:114-127`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/webodm.py#L114-L127)
- **Category:** Error handling · **Rule source:** `assets/rules/universal.md:108`
- **Work item:** M3-04 (P2) _issue pending_
- **Issue:** create_task opens one file descriptor per image before the request starts. macOS's default soft limit is 256 descriptors (and the backend already holds DB, log and socket descriptors), so any session of a few hundred frames fails with 'Too many open files' before anything is sent.
- **Fix:** Stream the multipart body from a generator that opens each file only while it is being sent (or upload in batches via WebODM's chunked upload API), and add a test with more images than RLIMIT_NOFILE.

### BP-QUAL · 'COLMAP intermediates' storage rule scans a directory nothing writes

- **Location:** [`backend/services/storage_lifecycle.py:179-211`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/storage_lifecycle.py#L179-L211)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M3-05 (P2) _issue pending_
- **Issue:** The rule looks for processed_dir/<session>/colmap, and the Storage tab labels it 'COLMAP Intermediates (processed/*/colmap/)' (frontend/src/features/storage/StorageTab.tsx:48). Reconstructions actually write workspaces to data_dir/colmap/<reconstruction_id> (services/reconstruction.py:2171), so the rule always returns zero candidates and disk-pressure cleanup never reclaims the largest intermediates.
- **Fix:** Enumerate data_dir/colmap/<id> workspaces of completed reconstructions (skipping live ones), update the UI label, and add a test that creates a real workspace via start_reconstruction's layout.

### UNI-ERR-005 · Annotation coordinates and color are not validated

- **Location:** [`backend/routers/annotations.py:16-21`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/annotations.py#L16-L21)
- **Category:** Validation · **Rule source:** `assets/rules/universal.md:109`
- **Work item:** M3-06 (P2) _issue pending_
- **Issue:** AnnotationIn accepts any float for lat/lon/alt_m (including NaN/inf and values outside WGS84 ranges) and any string for color, although the color is rendered by the viewer and exported to GeoJSON/survey reports. Measurements, target areas and GCP inputs in the same API are range-checked.
- **Fix:** Add Field(ge=-90, le=90)/(ge=-180, le=180), allow_inf_nan=False, a max_length on label, and a hex-color pattern for color.

### UNI-CMT-006 · react-hooks/exhaustive-deps suppressed without a stated reason

- **Location:** [`frontend/src/features/import/ImportModal.tsx:121-152`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/import/ImportModal.tsx#L121-L152)
- **Category:** Documentation · **Rule source:** `assets/rules/universal.md:70`
- **Work item:** M3-07 (P2) _issue pending_
- **Issue:** Three effects in ImportModal (lines 127, 140, 151) and two in SplatViewerTab (578, 1194) disable exhaustive-deps with no explanation. The ESC handler (144-152) captures `handleClose`/`isBusy` from the render where the effect last ran, so the suppression hides a stale-closure risk rather than documenting a deliberate choice. App.tsx:152 and PlanMap.tsx:51 show the expected pattern with a reason comment.
- **Fix:** Either add the missing deps (wrapping handlers in useCallback / useEffectEvent) or put a one-line reason above each suppression.

### UNI-ANTI-003 · Pipeline geotag step re-implements cli.run and has drifted from it

- **Location:** [`src/drone_video_geotagger/pipeline.py:137-208`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/src/drone_video_geotagger/pipeline.py#L137-L208)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:88`
- **Work item:** M3-08 (P2) _issue pending_
- **Issue:** `_default_output_dir`, `_resolve_srt_path`, the frame copy loop, and the audit/EXIF writes are copied from cli.py:64-125. The copies have already diverged: the pipeline calls `infer_frame_rate(frames, telemetry[-1].end_s)` without the video duration (cli.py:99-100 passes it), so headless runs skip the duration cross-check that catches a wrong frame-rate guess. The pipeline also never runs the GPS-lock warnings (cli.py:96).
- **Fix:** Move the geotag flow into one shared function (e.g. `geotag(spec) -> GeotagResult`) used by both cli.run and _run_geotag so safety checks cannot drift apart.

### BP-PERF · N+1 query for flight-log points in GeoPackage export

- **Location:** [`backend/routers/export.py:263-283`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/export.py#L263-L283)
- **Category:** Performance · **Rule source:** `SKILL.md:137`
- **Work item:** M4-01 (P2) _issue pending_
- **Issue:** One FlightLogPoint query runs per FlightLog. The skill's severity table classes N+1 queries as HIGH; practical impact here is limited to sessions with several logs.
- **Fix:** Load all points for the session's logs in one query ordered by (flight_log_id, timestamp, id) and group in Python.

### BP-PERF · Duplicate-import check runs one query per existing session

- **Location:** [`backend/services/duplicate_detection.py:36-53`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/duplicate_detection.py#L36-L53)
- **Category:** Performance · **Rule source:** `SKILL.md:137`
- **Work item:** M4-01 (P2) _issue pending_
- **Issue:** find_duplicate_matches loads every session, then queries that session's image filenames individually (N+1), on every import dialog open. The cost grows linearly with session count and is paid before every import.
- **Fix:** Query (session_id, filename) for filenames in the incoming set once, group by session_id in SQL (COUNT), and compare against the threshold.

### BP-PERF · list_projects issues one COUNT query per project (N+1)

- **Location:** [`backend/routers/projects.py:94-99`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/projects.py#L94-L99)
- **Category:** Performance · **Rule source:** `SKILL.md:137`
- **Work item:** M4-01 (P2) _issue pending_
- **Issue:** `list_projects` loads every project and then runs `db.query(SessionModel).filter(...).count()` inside the loop, so the projects page costs 1 + N queries and grows linearly with the number of projects.
- **Fix:** Compute counts in one grouped query (`select(project_id, func.count()).group_by(project_id)`) or an outer join, and look them up from a dict in the loop.

### UNI-ANTI-003 · _sha256 / _tree_sha256 / _maximum_rss_bytes copied across the three benchmark scripts

- **Location:** [`scripts/metal_release_gate.py:30-31`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/scripts/metal_release_gate.py#L30-L31)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:88`
- **Work item:** M3-09 (P3) _issue pending_
- **Issue:** The hashing and RSS helpers exist in three copies (metal_release_gate.py:30, benchmark_metal_presets.py:50-74, benchmark_heldout_parity.py:57-70, 296-298) and have already drifted: this copy reads the whole file into memory (splat.ply can be hundreds of MB) while the others stream in 1 MiB chunks, and only one copy has the Windows `resource` fix.
- **Fix:** Move the helpers into a shared `scripts/_evidence.py` module (streaming sha256, tree hash, portable max-RSS) and import it from all three scripts.

### UNI-ANTI-003 · Three hand-written PLY parsers besides ply_io

- **Location:** [`backend/services/reconstruction.py:741-790`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L741-L790)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:88`
- **Work item:** M5-01 (P3) _issue pending_
- **Issue:** _compute_coverage_gaps (741-822) and _load_ply_positions_and_colors (1001-1074) each re-implement PLY header/body parsing although ply_io.read_3dgs_ply exists (docs/ARCHITECTURE.md:53, 119 make ply_io the contract owner). The copies already disagree: coverage gaps only understands 'property float' and '\n' line endings, while the other accepts all scalar types and '\r\n', so a PLY with a uchar property or CRLF header is parsed as garbage by one and correctly by the other.
- **Fix:** Add a generic scalar-vertex reader to ply_io and route both call sites (and their tests) through it.

### UNI-ORG-004 · reconstruction.py is a 2,683-line module mixing unrelated responsibilities

- **Location:** [`backend/services/reconstruction.py:1-75`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L1-L75)
- **Category:** Architecture · **Rule source:** `assets/rules/universal.md:57`
- **Work item:** M5-01 (P3) _issue pending_
- **Issue:** One module owns the COLMAP runner, workspace writer, diagnostics, dense-rerun planning, three PLY/COLMAP parsers, LAS/LAZ export, semantic labelling, mesh export, flythrough rendering, voxel change detection, the remote-worker poller, queue handler registration and test shims. It has five functions over ruff's complexity limit and is imported by 20+ modules, so every change risks unrelated regressions and slows review.
- **Fix:** Split into a package (reconstruction/colmap.py, pipeline.py, exports/point_cloud.py, exports/mesh.py, semantic.py, comparison.py, remote.py) behind the current public names, moving one concern per PR with tests unchanged.

### UNI-ANTI-003 · 'Load reconstruction or 404' copy-pasted ~30 times

- **Location:** [`backend/routers/reconstruction.py:607-612`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/reconstruction.py#L607-L612)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:88`
- **Work item:** M5-01 (P3) _issue pending_
- **Issue:** Nearly every endpoint repeats db.query(Reconstruction).filter(...).first() plus the same 404, and many then repeat the same 'status != complete -> 202' check with slightly different status codes (202 vs 404 vs 422 for the same condition at lines 866, 1289, 1329).
- **Fix:** Introduce FastAPI dependencies `reconstruction_or_404` and `complete_reconstruction` and use them across the router, standardising the not-complete status code.

### UNI-ANTI-003 · UTM zone derivation duplicated in two modules

- **Location:** [`backend/services/georeferencing_solve.py:100-106`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/georeferencing_solve.py#L100-L106)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:88`
- **Work item:** M5-02 (P3) _issue pending_
- **Issue:** georeferencing_solve._utm_zone_str re-implements geometry.utm_crs_for (geometry.py:15-18). Both return zone 61 for lon = 180 and ignore the Norway/Svalbard exceptions, and any fix must now be made twice, risking footprints and the geo-transform landing in different zones.
- **Fix:** Have _utm_zone_str call geometry.utm_crs_for (clamping the zone to 1-60) and derive the label from the returned CRS.

### UNI-ANTI-003 · _load_geo_transform_for_reconstruction duplicated

- **Location:** [`backend/services/orthomosaic_export.py:29-40`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/orthomosaic_export.py#L29-L40)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:88`
- **Work item:** M5-02 (P3) _issue pending_
- **Issue:** An almost identical copy exists in services/reconstruction.py:1524-1535 (this one returns a dict() copy, the other the shared _LOCAL_FRAME_GEO object, so a caller mutating the result would corrupt the module-level default in one path but not the other).
- **Fix:** Keep a single implementation (returning a copy) in the reconstruction/georeferencing module and import it.

### UNI-ANTI-003 · ffmpeg invocation and not-found handling copied three times

- **Location:** [`src/drone_video_geotagger/video.py:40-53`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/src/drone_video_geotagger/video.py#L40-L53)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:88`
- **Work item:** M5-04 (P3) _issue pending_
- **Issue:** `extract_srt`, `read_video_duration` and `read_video_start` each wrap `subprocess.run` in an identical FileNotFoundError -> RuntimeError block, and the two probe functions run the same `ffmpeg -i` command separately, so a geotag run probes the video twice.
- **Fix:** Add one `_probe(ffmpeg, video) -> str` helper that runs `ffmpeg -i` once and raises the not-found error, and parse both duration and creation_time from its output.

### UNI-ANTI-003 · CSV formula guard duplicated from backend.core.csv_safe

- **Location:** [`src/drone_video_geotagger/audit.py:10-13`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/src/drone_video_geotagger/audit.py#L10-L13)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:88`
- **Work item:** M5-04 (P3) _issue pending_
- **Issue:** `_csv_safe` is a copy of `backend/core/csv_safe.csv_safe`. Two copies of a security control drift independently; the ODM CSV exporter already missed the guard entirely.
- **Fix:** Move the helper into the `drone_video_geotagger` package (which the backend already depends on) and import it from both places.

### RX-COMP-002 · SplatViewerTab.tsx is a 2,204-line component module

- **Location:** [`frontend/src/features/splat/SplatViewerTab.tsx:863-1603`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/splat/SplatViewerTab.tsx#L863-L1603)
- **Category:** Maintainability · **Rule source:** `assets/rules/react.md:14`
- **Work item:** M5-05 (P3) _issue pending_
- **Issue:** The file holds 11 data hooks, 7 sub-components, the measurement layer, flythrough recording, presentation playback, coverage-gap/semantic/annotation scene layers and the tab shell. `SplatCanvas` alone is ~740 lines with 10 effects. This is where the flat-plane measurement bug and the untyped viewer access live, and the size makes it hard to test pieces in isolation.
- **Fix:** Split into `features/splat/{queries.ts, SplatCanvas.tsx, layers/*.ts, FlythroughControls.tsx, PresentationOverlay.tsx, SplatSidebar.tsx}` with one scene layer hook per overlay.

### TS-TYPE-001 · Gaussian-splat viewer and Three.js groups are typed as any (20+ sites)

- **Location:** [`frontend/src/features/splat/SplatViewerTab.tsx:884-889`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/splat/SplatViewerTab.tsx#L884-L889)
- **Category:** Type safety · **Rule source:** `assets/rules/typescript.md:28`
- **Work item:** M5-05 (P3) _issue pending_
- **Issue:** `viewerRef.current as any` (lines 954, 975, 1098, 1262, 1273, 1345, 1397, 1454), `useRef<any>` group refs (454, 885-889) and `traverse((obj: any) => ...)` callbacks each carry an eslint-disable. Calls such as `viewer.orbitControls ?? viewer.controls`, `controls.target.set` and `obj.material.map.dispose()` are unchecked, so a library upgrade that renames them fails only at runtime. useViewerCoords.ts:135 and PlanMap.tsx:35-39 do the same.
- **Fix:** Declare a small `SplatViewerHandle` interface (camera, scene, orbitControls, dispose) and type the groups as `THREE.Group`/`THREE.Object3D`, narrowing with `instanceof THREE.Mesh` in traverse callbacks.

### RX-MISC-003 · Hard-coded colours in the splat viewer (35 literals)

- **Location:** [`frontend/src/features/splat/SplatViewerTab.tsx:627-657`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/splat/SplatViewerTab.tsx#L627-L657)
- **Category:** Consistency · **Rule source:** `assets/rules/react.md:147`
- **Work item:** M5-05 (P3) _issue pending_
- **Issue:** The dark overlay panels, metric charts and gap legend use raw hex/rgba values ('#D8D2C7', '#F2ECE0', 'rgba(28,27,25,0.9)', '#4F6349', '#9A5E32', '#eab308'...). The legend at lines 2081-2083 repeats GAP_COLORS (586-590) as strings, so the two can drift. VolumePanel.tsx, ReconstructionLogo3D.tsx, CompareTab.tsx and ImportModal.tsx have more.
- **Fix:** Add overlay tokens (e.g. --overlay-bg, --overlay-text) to index.css and derive the legend from GAP_COLORS so there is one source for each colour.

### UNI-ANTI-003 · MeshExportCard and OrthoExportCard are copy-pasted

- **Location:** [`frontend/src/features/export/ExportTab.tsx:225-303`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/export/ExportTab.tsx#L225-L303)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:88`
- **Work item:** M5-06 (P3) _issue pending_
- **Issue:** OrthoExportCard repeats MeshExportCard (lines 77-184) line for line: status query with the same polling rule, mutation with toast/invalidate, indeterminate bar, error line and download links. The eight section cards below also repeat the same header markup and inline styles. A fix to one card (for example error display) must be made in each copy.
- **Fix:** Extract a generic `ArtifactJobCard` (status hook, start mutation, render-links prop) and a `SectionCard` component for the repeated section chrome.

### UNI-ANTI-003 · Preset radios and target-area select duplicated for single and merge modes

- **Location:** [`frontend/src/features/reconstruct/ReconstructTab.tsx:605-643`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/reconstruct/ReconstructTab.tsx#L605-L643)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:88`
- **Work item:** M5-06 (P3) _issue pending_
- **Issue:** The preset radio group and the target-area `<select>` (with identical inline styles and option text) are copied between the single-session card (534-572) and the merge card (605-643). The two start buttons also compute their labels differently (580-584 vs `startButtonLabel`).
- **Fix:** Extract `<PresetPicker>` and `<TargetAreaSelect>` components and a single start button driven by `canStart`/`startButtonLabel`.

### RX-COND-004 · Nested ternaries choose preflight badge colours inline

- **Location:** [`frontend/src/features/reconstruct/ReconstructTab.tsx:489-499`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/reconstruct/ReconstructTab.tsx#L489-L499)
- **Category:** Readability · **Rule source:** `assets/rules/react.md:95`
- **Work item:** M5-06 (P3) _issue pending_
- **Issue:** Background and text colour are each picked with a two-level nested ternary on `safe_to_reconstruct`, repeated twice in the JSX, and the button label (580-584) nests three levels. SplatViewerTab.tsx:2116-2120 and other tabs follow the same pattern.
- **Fix:** Map verdict -> {bg, color} with a lookup object and compute labels in named variables before the JSX.

### UNI-ANTI-003 · Blob download helper copied into four components

- **Location:** [`frontend/src/features/splat/VolumePanel.tsx:26-34`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/splat/VolumePanel.tsx#L26-L34)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:88`
- **Work item:** M5-06 (P3) _issue pending_
- **Issue:** The createObjectURL -> anchor click -> revokeObjectURL sequence is duplicated in VolumePanel.tsx:26-34, ProfilePanel.tsx:69-77, ExportTab.tsx:403-411 and SplatViewerTab.tsx:1021-1028. All four revoke synchronously, so a fix for the revoke timing has to be made four times.
- **Fix:** Add `shared/utils/downloadBlob.ts` (revoking on the next tick) and use it from all four call sites.

### UNI-ANTI-003 · Job status badge map, colour mapper and formatDuration copied between tabs and already drifted

- **Location:** [`frontend/src/features/jobs/JobsTab.tsx:304-335`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/jobs/JobsTab.tsx#L304-L335)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:88`
- **Work item:** M5-06 (P3) _issue pending_
- **Issue:** JobsTab.tsx and ReconstructTab.tsx:215-250 each define STATUS_BADGE, jobStatusBadgeColor and formatDuration. The JobsTab copy knows `running_remote` and is typed on `Job['status']`; the ReconstructTab copy is `Record<string, ...>` and misses it. ImportModal.tsx:50 also re-implements `storage/formatBytes.ts`.
- **Fix:** Move the job-status presentation (label + colour) and duration formatting into `shared/jobs/status.ts`, typed on `Job['status']`, and reuse `storage/formatBytes` in ImportModal.

### UNI-ANTI-003 · Multipart uploads bypass the API client and re-implement its error parsing

- **Location:** [`frontend/src/features/gps-sync/GpsSyncTab.tsx:146-161`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/gps-sync/GpsSyncTab.tsx#L146-L161)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:88`
- **Work item:** M5-06 (P3) _issue pending_
- **Issue:** The flight-log upload calls `fetch` directly and parses FastAPI's `detail` itself. browserUpload.ts:42-60 has a third copy (`readError`/`checkedFetch`) of client.ts's `errorMessage`. None of these copies get the client's 120 s timeout (#868) or its handling of array-shaped validation errors, so a stalled chunk or log upload hangs indefinitely and 422 errors render as raw JSON.
- **Fix:** Export a `postForm<T>(path, formData, {signal})` from shared/api/client.ts that reuses `request()` (timeout + errorMessage) and use it for chunk and flight-log uploads.

### TS-STRICT-001 · Frontend tsconfig does not enable strict mode

- **Location:** [`frontend/tsconfig.app.json:20-25`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/tsconfig.app.json#L20-L25)
- **Category:** Type safety · **Rule source:** `assets/rules/typescript.md:65`
- **Work item:** M5-07 (P3) _issue pending_
- **Issue:** `compilerOptions` has noUnusedLocals/noUnusedParameters/noFallthroughCasesInSwitch but no `"strict": true`, so strictNullChecks and noImplicitAny are off for `npm run build`. The code already compiles cleanly under `tsc --strict` (0 errors), so nothing stops a future change from introducing implicit-any or unchecked-null code.
- **Fix:** Add `"strict": true` (it currently passes with zero errors) so CI's `tsc -b` enforces it from now on.

### TS-STRICT-006 · noUncheckedIndexedAccess would flag 128 unchecked index reads

- **Location:** [`frontend/tsconfig.app.json:18-23`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/tsconfig.app.json#L18-L23)
- **Category:** Type safety · **Rule source:** `assets/rules/typescript.md:70`
- **Work item:** M5-07 (P3) _issue pending_
- **Issue:** With `noUncheckedIndexedAccess` enabled, tsc reports 128 errors (85 in non-test code), concentrated in SplatViewerTab.tsx (25), measurementMath.ts (10), ReconstructionLogo3D.tsx (8), SplatSettings.tsx, PipelineOverview.tsx, weatherAdvisor.ts and PlanTab.tsx. These are array/record reads such as `points[0].worldPos` and `flythroughKeyframes[segment]` that are typed as always defined.
- **Fix:** Enable the flag after `strict`, fixing the 85 production sites with explicit guards (tests can use non-null assertions), one feature folder per PR.

## MEDIUM (72)

### BP-QUAL · WebODM package CSV names don't match the zipped image names

- **Location:** [`backend/services/webodm_package.py:21-63`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/webodm_package.py#L21-L63)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M1-01 (P0) _issue pending_
- **Issue:** The georeferencing CSV uses Image.filename, which ingest rewrites to '<stem>__<hash>.jpg' for duplicate basenames in nested folders (ingest_orchestrator.py:35-42), but the images are zipped under their original basename. ODM then cannot pair those rows with their images, and two nested files with the same basename collide in the zip (zipfile writes a duplicate entry). The same unescaped CSV construction as routers/export.py:431-438 is duplicated here.
- **Fix:** Zip each image under Image.filename, build the CSV once in a shared helper using csv.writer + csv_safe, and test with duplicate nested basenames.

### BP-QUAL · Reservation cap counts finished imports as active uploads

- **Location:** [`backend/routers/uploads.py:280-285`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/uploads.py#L280-L285)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M1-03 (P0) _issue pending_
- **Issue:** The cap counts every directory under the staging root, including completed imports that still hold their session's images. After 8 browser imports inside the cleanup window, /start returns 409 'Too many concurrent uploads' although nothing is in flight.
- **Fix:** Count only manifests whose status is 'uploading' (the same filter _reserved_bytes already applies).

### UNI-NAME-003 · One migration uses an autogenerated hash revision ID

- **Location:** [`backend/db/migrations/versions/db8522027afe_add_job_queue_table.py:16-17`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/db/migrations/versions/db8522027afe_add_job_queue_table.py#L16-L17)
- **Category:** Consistency · **Rule source:** `assets/rules/universal.md:15`
- **Work item:** M1-05 (P0) _issue pending_
- **Issue:** Every other revision uses the zero-padded 000N convention; db8522027afe sits between 0004 and 0005, which makes the chain harder to read and sort.
- **Fix:** Leave the ID (it is stamped in user databases) but document the exception in CONTRIBUTING.md so new revisions keep the 000N scheme.

### BP-DATA · Baseline migration creates tables from the live ORM models

- **Location:** [`backend/db/migrations/versions/0001_baseline.py:70-72`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/db/migrations/versions/0001_baseline.py#L70-L72)
- **Category:** Database migrations · **Rule source:** `SKILL.md:81`
- **Work item:** M1-05 (P0) _issue pending_
- **Issue:** Revision 0001 imports `backend.db.models` (line 28) and runs `table.create()` for every table in the current `Base.metadata`. On a fresh database it therefore builds today's full schema (every later table, column, index and FK option), and revisions 0002-0017 are conditional no-ops. On an upgraded database the schema comes from the individual revisions. tests/backend/test_database.py upgrades the v2.0.2 snapshot and checks that every model column and FK index exists, but nothing compares foreign-key options (ondelete), types, nullability or constraints, and no pre-projects (v1.x) schema is tested, which is how 0005 ships broken.
- **Fix:** Freeze 0001 to an explicit schema snapshot (no model import), and extend the v2.0.2 upgrade test with a v1.x snapshot plus an `alembic.autogenerate.compare_metadata` diff so FK options, types and constraints must match Base.metadata.

### BP-QUAL · GPS sync updates image positions but leaves footprints stale

- **Location:** [`backend/routers/flight_log.py:318-336`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/flight_log.py#L318-L336)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M1-06 (P0) _issue pending_
- **Issue:** apply_sync overwrites latitude/longitude/altitude on each matched image but never recomputes its Footprint row, so the Map tab, coverage analysis, GeoPackage footprints layer and preflight coverage keep using the pre-sync EXIF positions until the session is re-imported.
- **Fix:** Recompute (or delete and rebuild) footprints for applied images in the same transaction using geometry.compute_footprint, and assert it in the apply-sync router test.

### BP-QUAL · Terrain-following altitudes are dropped from KML/GPX exports

- **Location:** [`backend/services/mission_planner.py:179-211`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/mission_planner.py#L179-L211)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M1-08 (P0) _issue pending_
- **Issue:** generate_lawnmower(terrain_follow=True) embeds per-vertex MSL altitudes as a third coordinate, but write_kml hard-codes 0 for every vertex (with no altitudeMode) and write_gpx emits no <ele>, so the files a pilot loads contain no terrain-following information at all.
- **Fix:** Write the third coordinate (and altitudeMode=absolute) when present, <ele> in GPX, and test that a terrain-following plan round-trips its altitudes.

### BP-QUAL · Gap re-fly plan covers only the first gap polygon

- **Location:** [`backend/services/mission_planner.py:612-631`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/mission_planner.py#L612-L631)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M1-08 (P0) _issue pending_
- **Issue:** generate_lawnmower_from_gaps plans against features[0] only and silently ignores every other gap; for a MultiPolygon it plans over the bounding box of all gaps. The operator receives a plan that looks complete but leaves the remaining gaps unflown.
- **Fix:** Plan every gap polygon (or their union, clipped), report per-gap coverage, and test with multiple gaps.

### BP-QUAL · 'Download georeferencing CSV zip' never downloads anything

- **Location:** [`frontend/src/features/export/ExportTab.tsx:657-684`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/export/ExportTab.tsx#L657-L684)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M1-11 (P1) _issue pending_
- **Issue:** The button POSTs `/export/webodm-georeferencing-csv`, which writes the zip into the server's exports_dir and returns its path. The UI then shows only the file name. exports_dir is not served (main.py mounts only /processed), so a browser user on another machine (browser-upload or Docker deployment) cannot retrieve the file the button label promises.
- **Fix:** Return the zip as a FileResponse (or add a GET download route for it) and trigger a browser download, or relabel the action as 'Build on server'.

### BP-QUAL · Failed reconstructions are marked 'completed' in the job queue

- **Location:** [`backend/services/reconstruction.py:2410-2457`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L2410-L2457)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M1-13 (P1) _issue pending_
- **Issue:** The inner `except RuntimeError` branches (CUDA OOM, trainer failure) set the reconstruction to status='failed' but swallow the exception, so the outer `else:` calls mark_complete and the JobQueueEntry reads 'completed'. The Jobs tab and /jobs API then report success for a failed run, and the retry budget (max_attempts=2) is never used.
- **Fix:** Raise JobNonRetryableError (or call _mark_failed) after recording the failure so the queue entry mirrors the reconstruction's terminal state.

### BP-QUAL · Job handlers that return early leave the queue entry 'running'

- **Location:** [`backend/services/job_queue.py:459-464`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/job_queue.py#L459-L464)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M1-13 (P1) _issue pending_
- **Issue:** _execute_job relies on every handler calling mark_complete/_mark_failed. Handlers such as _run_mesh_export_job return early (`if rec is None: return`) without doing so, leaving the JobQueueEntry in 'running' until the next restart's reaper marks it failed, so the Jobs UI shows a phantom running job.
- **Fix:** After the handler returns, mark the entry completed if it is still 'running' (or make handlers return a status the executor records).

### BP-SEC · Share signing key written world-readable, then chmod-ed, with a create race

- **Location:** [`backend/services/share_links.py:32-38`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/share_links.py#L32-L38)
- **Category:** Security · **Rule source:** `SKILL.md:81`
- **Work item:** M1-15 (P1) _issue pending_
- **Issue:** The HMAC key is written with the process umask (typically 0644) and only restricted afterwards, leaving a window where other local users can read it. Two concurrent first calls also each write a different key, invalidating the tokens signed with the loser.
- **Fix:** Create the file atomically with os.open(path, O_CREAT | O_EXCL | O_WRONLY, 0o600), and on FileExistsError read the existing key.

### BP-SEC · DJI API key passed on the djirecord command line

- **Location:** [`backend/services/dji_log_parser.py:144-157`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/dji_log_parser.py#L144-L157)
- **Category:** Security · **Rule source:** `SKILL.md:81`
- **Work item:** M1-15 (P1) _issue pending_
- **Issue:** The decryption key is appended to argv, where any local user can read it from the process list (/proc/<pid>/cmdline, ps, Task Manager) for the duration of a parse of up to 120 s.
- **Fix:** Pass the key through the child environment (DJI_API_KEY, which the tool already reads) or stdin instead of argv.

### BP-SEC · Share bundles embed absolute server filesystem paths

- **Location:** [`backend/services/share_bundle.py:27-49`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/share_bundle.py#L27-L49)
- **Category:** Security · **Rule source:** `SKILL.md:81`
- **Work item:** M1-15 (P1) _issue pending_
- **Issue:** The shareable bundle's manifest.json (and the manifest inlined into index.html) contains raw artifact paths such as /Users/<name>/telemetry-frame-mapper/exports/12/splat.ply. The bundle is meant to be handed to third parties, while the public viewer payload explicitly promises never to expose filesystem paths (services/share_links.py:167-168).
- **Fix:** Store only archive-relative names (artifacts/<file>) in the shared manifest and keep absolute paths server-side.

### BP-SEC · Container runs the API as root

- **Location:** [`Dockerfile:38-45`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/Dockerfile#L38-L45)
- **Category:** Security · **Rule source:** `SKILL.md:81`
- **Work item:** M1-15 (P1) _issue pending_
- **Issue:** The runtime stage never switches to an unprivileged user, so the FastAPI process (which parses uploaded images, ZIP bundles and runs COLMAP/ffmpeg/exiftool on user files) runs as root inside the container, and files written to mounted volumes are root-owned.
- **Fix:** Create an `app` user, `chown` /app/data, imports, processed and exports, and add `USER app` before CMD.

### UNI-TEST-005 · Five backend tests have no assertion

- **Location:** [`tests/backend/test_session_merge.py:39`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/tests/backend/test_session_merge.py#L39)
- **Category:** Test quality · **Rule source:** `assets/rules/universal.md:144`
- **Work item:** M2-08 (P2) _issue pending_
- **Issue:** test_session_merge.py:39 and :117, test_reconstruction_service.py:1550, test_plans_router.py:240 and the `test_handler` helper in test_job_queue.py:425 only check that no exception is raised. A regression that returns the wrong result still passes.
- **Fix:** Assert the returned value (e.g. the validated session list or the no-op result) in each test.

### BP-QUAL · GLB georeference metadata embed failure is ignored

- **Location:** [`backend/services/reconstruction.py:1563-1571`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L1563-L1571)
- **Category:** Error handling · **Rule source:** `SKILL.md:137`
- **Work item:** M3-01 (P2) _issue pending_
- **Issue:** `_embed_glb_extras` swallows every exception and returns False, and the only caller (line 1643) ignores the return value, so a mesh GLB can ship without its georeference extras and nobody is told.
- **Fix:** Log the exception in `_embed_glb_extras` and have the caller record a reconstruction log entry when it returns False.

### BP-QUAL · config.yaml top level is never checked to be a mapping

- **Location:** [`backend/core/config.py:84-93`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/core/config.py#L84-L93)
- **Category:** Validation · **Rule source:** `SKILL.md:81`
- **Work item:** M3-02 (P2) _issue pending_
- **Issue:** `yaml.safe_load(f) or {}` accepts any YAML document. A config.yaml whose top level is a list or scalar (a common hand-editing mistake) makes `data.items()` / `data.get()` raise AttributeError at import time instead of a clear configuration error.
- **Fix:** After loading, raise ValueError('config.yaml must contain a mapping at the top level') when the result is not a dict.

### BP-QUAL · config.yaml opened with locale encoding

- **Location:** [`backend/core/config.py:85`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/core/config.py#L85)
- **Category:** Portability · **Rule source:** `SKILL.md:81`
- **Work item:** M3-02 (P2) _issue pending_
- **Issue:** Every config read uses `open(path)` with no encoding, so on Windows (a shipped target) the file is decoded as cp1252. Any UTF-8 non-ASCII character an operator adds (a path, a basemap attribution like '©') is misread or raises UnicodeDecodeError on startup.
- **Fix:** Open config.yaml with encoding='utf-8' (in the shared helper) to match how the settings router writes it.

### BP-QUAL · Several config sections merged without type validation

- **Location:** [`backend/core/config.py:444-461`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/core/config.py#L444-L461)
- **Category:** Validation · **Rule source:** `SKILL.md:81`
- **Work item:** M3-02 (P2) _issue pending_
- **Issue:** browser_uploads, upload_limits, ingest, render and backup sections are merged with `{**defaults, **section}` and never type-checked, unlike remote_worker/webodm/cesium_ion which coerce and bound every value. A string such as quota_bytes: "10GB" passes load and fails later inside a request handler with a TypeError.
- **Fix:** Validate and coerce these sections the same way get_remote_worker_config does (int/float coercion with bounds, fall back or raise at startup).

### BP-QUAL · Settings writes config.yaml as UTF-8 but reads it with locale encoding

- **Location:** [`backend/routers/settings.py:266-272`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/settings.py#L266-L272)
- **Category:** Portability · **Rule source:** `SKILL.md:81`
- **Work item:** M3-02 (P2) _issue pending_
- **Issue:** _write_raw dumps YAML with encoding='utf-8' and allow_unicode=True, while _load_raw (and every getter in backend/core/config.py) re-opens it with the platform default. On Windows any non-ASCII value saved from the Settings tab is written as UTF-8 and read back as cp1252, corrupting the value or failing startup. _load_raw is also a 19th copy of the config-load block.
- **Fix:** Route _load_raw through the shared UTF-8 config loader proposed for backend/core/config.py.

### BP-QUAL · Changing processed_dir at runtime breaks the /processed static mount

- **Location:** [`backend/main.py:201-203`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/main.py#L201-L203)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M3-02 (P2) _issue pending_
- **Issue:** The /processed StaticFiles mount is bound to processed_dir once at import. PATCH /settings can change processed_dir and clears the config cache, so new thumbnails are written to the new directory while /processed keeps serving the old one until restart, and the Settings UI gives no restart hint for storage directories.
- **Fix:** Either serve /processed through a route that resolves get_config().processed_dir per request, or mark storage-directory fields as 'restart required' in the API response and UI.

### BP-QUAL · SQLite DB location ignores the configured data_dir

- **Location:** [`backend/db/database.py:26-37`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/db/database.py#L26-L37)
- **Category:** Configuration · **Rule source:** `SKILL.md:81`
- **Work item:** M3-02 (P2) _issue pending_
- **Issue:** data_dir is configurable (config.yaml and PATCH /settings) and is used for COLMAP workspaces, storage accounting and restore roots, but the database is always <repo>/data/drone_mapping.db in a source checkout. Moving data_dir silently splits the DB from the rest of the data, and backups/storage views disagree about where 'data' is.
- **Fix:** Derive the default DATABASE_URL from get_config().data_dir (keeping DATABASE_URL as the override) or document that data_dir excludes the database.

### UNI-ORG-003 · Orthomosaic export bypasses the persistent job queue

- **Location:** [`backend/services/orthomosaic_export.py:249-275`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/orthomosaic_export.py#L249-L275)
- **Category:** Architecture · **Rule source:** `assets/rules/universal.md:56`
- **Work item:** M3-03 (P2) _issue pending_
- **Issue:** Every other heavy export (mesh, flythrough, semantic labels, comparison) is enqueued in job_queue.py, which provides persistence, cancellation, concurrency caps and Jobs-tab visibility. The orthomosaic spawns an ad-hoc daemon thread with its own in-memory lock set and its own startup reaper (main.py:112-119), so it cannot be cancelled, is invisible in the Jobs tab, and can run concurrently with GPU training on a 100-megapixel accumulator.
- **Fix:** Register an ORTHOMOSAIC job type with the queue and delete the private thread/lock/reaper.

### BP-QUAL · GeoPackage export uses a fixed temp filename

- **Location:** [`backend/routers/export.py:190-201`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/export.py#L190-L201)
- **Category:** Concurrency · **Rule source:** `SKILL.md:81`
- **Work item:** M3-04 (P2) _issue pending_
- **Issue:** Two concurrent GeoPackage or GIS-project-file requests for the same reconstruction both write mapped_products.tmp.gpkg and race on os.replace, so one response can serve a file the other request is still writing. Other exports in this router use unique temp files for exactly this reason (#641, #684).
- **Fix:** Create the temp file with tempfile.mkstemp in the same directory (as _atomic_zip does) before calling write_geopackage.

### BP-QUAL · Session archive zip is written in place, not atomically

- **Location:** [`backend/services/session_bundle.py:198-203`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/session_bundle.py#L198-L203)
- **Category:** Concurrency · **Rule source:** `SKILL.md:81`
- **Work item:** M3-04 (P2) _issue pending_
- **Issue:** build_session_archive writes exports/session_<id>_archive.zip directly. A second archive request (single or bulk) for the same session truncates the file the first is still writing, and a crash leaves a corrupt archive that restore later rejects. Other exports in routers/export.py use _atomic_zip for exactly this (#641).
- **Fix:** Build into a mkstemp sibling and os.replace on success (reuse _atomic_zip by moving it to a shared helper).

### BP-QUAL · GET /plans/{id}/segments writes KML and GPX files as a side effect

- **Location:** [`backend/routers/plans.py:216-222`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/plans.py#L216-L222)
- **Category:** Architecture · **Rule source:** `SKILL.md:81`
- **Work item:** M3-04 (P2) _issue pending_
- **Issue:** A read-only listing endpoint regenerates and writes 2 files per segment to the exports directory on every call. Polling or re-rendering the segment list rewrites files repeatedly, and a read endpoint can fail with disk errors. The segment download endpoints (lines 314-337) also rewrite the same files each time.
- **Fix:** Return segment metadata only from GET /segments and generate the KML/GPX lazily (or cache by plan id + segment index + plan mtime) in the download endpoints.

### BP-QUAL · Camera-local EXIF times are stored and served as UTC

- **Location:** [`backend/services/ingest.py:110-115`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/ingest.py#L110-L115)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M3-05 (P2) _issue pending_
- **Issue:** DateTimeOriginal is the camera's local wall-clock time with no zone, but it is stored in a UtcDateTime column that re-attaches UTC on read (models.py:40-43), so the API returns '...+00:00' and browsers display every frame time shifted by the operator's UTC offset. OffsetTimeOriginal (EXIF 2.31), when present, is ignored; the failed-parse branch is also a bare `except Exception: pass`.
- **Fix:** Read OffsetTimeOriginal when present and store an aware timestamp; otherwise keep a separate 'local, zone unknown' field (or flag) so the UI does not convert it, and catch ValueError/UnicodeDecodeError explicitly.

### BP-QUAL · Interrupted imports leave sessions at photo_count 0 with no error

- **Location:** [`backend/services/ingest_orchestrator.py:234-255`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/ingest_orchestrator.py#L234-L255)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M3-05 (P2) _issue pending_
- **Issue:** photo_count/usable_count are only written after the last image, and import progress/errors live only in the in-memory _progress dict. If the process restarts mid-import or the loop raises, the session keeps Image rows but reports 0 photos, get_progress returns status 'unknown', and nothing in the session log records the failure.
- **Fix:** Update counts incrementally (or recompute from Image rows on read), persist import status on the Session (or a log entry) including failures, and mark in-flight imports as interrupted on startup.

### BP-DATA · Archiving raw frames leaves sessions pointing at moved files

- **Location:** [`backend/services/storage_lifecycle.py:393-406`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/storage_lifecycle.py#L393-L406)
- **Category:** Data integrity · **Rule source:** `SKILL.md:81`
- **Work item:** M3-05 (P2) _issue pending_
- **Issue:** For raw_frames candidates the whole session folder is moved into storage_archive, but no DB reference is updated (the candidate carries no rec_id/field) and the session is not marked archived. Its Image.filepath values now point at missing files, so reconstructions, exports and restore of that session fail without explanation.
- **Fix:** Record the session id on raw_frames candidates, mark the session archived (or rewrite folder_path/filepaths to the archive location) in the same transaction, and surface the state in the UI.

### BP-QUAL · Review edits leave Session.usable_count stale; flags are free text

- **Location:** [`backend/routers/images.py:101-137`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/images.py#L101-L137)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M3-05 (P2) _issue pending_
- **Issue:** patch_image and bulk_patch_images change Image.usable/flag without recomputing the owning session's usable_count, so session lists, pickers and survey reports show the import-time count after an operator excludes frames in Review. `flag` accepts any string (ImagePatch/ImageBulkPatch), although ingest and preflight treat it as an enum (good/blurry/dark/bright/no_gps), and the bulk update is not scoped to a session.
- **Fix:** Constrain flag to a Literal/StrEnum, require session_id on bulk updates, and recompute usable_count in the same transaction (or derive it with a query instead of storing it).

### BP-DATA · Defect and its image links are committed in two transactions

- **Location:** [`backend/routers/defects.py:114-127`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/defects.py#L114-L127)
- **Category:** Data integrity · **Rule source:** `SKILL.md:81`
- **Work item:** M3-06 (P2) _issue pending_
- **Issue:** create_defect commits the Defect row, then adds the DefectImage links and commits again. A failure between the two leaves a defect with no linked photos, violating the image_ids min_length=1 contract the API enforces on input.
- **Fix:** Use db.flush() to obtain defect.id and commit once after adding the links.

### BP-QUAL · State setters called inside a setMeasurePoints updater

- **Location:** [`frontend/src/features/splat/SplatViewerTab.tsx:1869-1882`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/splat/SplatViewerTab.tsx#L1869-L1882)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M3-07 (P2) _issue pending_
- **Issue:** `handleMeasurePoint` calls `setMeasureMode` and `setActiveTool` from inside the functional updater passed to `setMeasurePoints`. React may call updaters twice (StrictMode) or defer them, so side effects in an updater are unsupported and fire more than once.
- **Fix:** Compute `next` from the current `measurePoints` in the handler, then call the three setters sequentially outside any updater.

### BP-QUAL · Reconstruction Cancel stops a long GPU run with one click, no confirmation

- **Location:** [`frontend/src/features/reconstruct/ReconstructTab.tsx:671-680`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/reconstruct/ReconstructTab.tsx#L671-L680)
- **Category:** UX safety · **Rule source:** `SKILL.md:81`
- **Work item:** M3-07 (P2) _issue pending_
- **Issue:** Every delete in the app goes through ConfirmDialog, but cancelling an in-progress reconstruction, which discards potentially hours of COLMAP/splat training, fires immediately on a single click of a button placed next to the progress bar.
- **Fix:** Route Cancel through the existing ConfirmDialog with the elapsed time in the message.

### UNI-ANTI-005 · --log-dir / log_dir only creates an empty directory

- **Location:** [`src/drone_video_geotagger/pipeline.py:511-514`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/src/drone_video_geotagger/pipeline.py#L511-L514)
- **Category:** Observability · **Rule source:** `assets/rules/universal.md:90`
- **Work item:** M3-08 (P2) _issue pending_
- **Issue:** The job spec key and the `--log-dir` flag (README.md:105) are advertised as the log location, but nothing is ever written there: logging goes to stderr via basicConfig and the directory is only mkdir'd. Batch users expecting a per-run log file get an empty folder.
- **Fix:** Attach a FileHandler writing `<log_dir>/<job name>-<timestamp>.log` for the duration of the run, or remove the option and its documentation.

### BP-PERF · async chunk handler does blocking file I/O on the event loop

- **Location:** [`backend/routers/uploads.py:315-353`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/uploads.py#L315-L353)
- **Category:** Performance · **Rule source:** `SKILL.md:81`
- **Work item:** M4-02 (P2) _issue pending_
- **Issue:** upload_import_chunk is `async def` but acquires a threading.Lock and performs synchronous stat/append/manifest writes inside it. Each 2 MB chunk blocks the single event loop, stalling every other request (UI polling, SSE) while it writes.
- **Fix:** Read the chunk asynchronously, then run the locked write section via `await run_in_threadpool(...)` (or make the handler sync after reading).

### BP-PERF · /system/resources spawns three subprocesses on every 3s poll

- **Location:** [`backend/routers/system.py:412-426`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/system.py#L412-L426)
- **Category:** Performance · **Rule source:** `SKILL.md:81`
- **Work item:** M4-02 (P2) _issue pending_
- **Issue:** The Jobs tab polls /system/resources every 3 seconds (frontend/src/features/jobs/JobsTab.tsx:53-54). Each call runs `ffmpeg -version`, `exiftool -ver` and `colmap -h` as subprocesses (each with a 2s timeout) plus a blocking 100 ms cpu_percent sample, although tool versions only change on reinstall.
- **Fix:** Cache binary and Python-dependency status (lru_cache or a TTL of a few minutes, like colmap_capabilities already does) and poll only the live CPU/RAM/GPU numbers.

### BP-PERF · Voxel diff builds Python sets of tuples per point

- **Location:** [`backend/services/reconstruction.py:1894-1900`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L1894-L1900)
- **Category:** Performance · **Rule source:** `SKILL.md:81`
- **Work item:** M4-02 (P2) _issue pending_
- **Issue:** _voxelize_points converts every point into a Python tuple inside a set comprehension. For LAS or full splat sources with millions of points this is seconds of pure-Python work and hundreds of MB per reconstruction, on the job worker thread.
- **Fix:** Use np.unique(coords, axis=0) and set operations on structured/packed int64 keys (e.g. np.setdiff1d on a combined key) instead of Python sets.

### BP-PERF · Coverage overlap computes every footprint pair (O(n^2))

- **Location:** [`backend/services/coverage.py:43-49`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/coverage.py#L43-L49)
- **Category:** Performance · **Rule source:** `SKILL.md:81`
- **Work item:** M4-02 (P2) _issue pending_
- **Issue:** A 1,000-frame survey produces ~500,000 Shapely intersections (2,000 frames: ~2 million) on the request thread, although only spatially adjacent footprints can overlap. Coverage runs on large sessions take minutes and hold a worker thread.
- **Fix:** Use shapely.STRtree to query only intersecting candidate pairs (or compute double coverage from the union of pairwise intersections via polygonize of boundaries) and add a timing test with a few thousand synthetic footprints.

### BP-PERF · Quick report runs ORB feature matching on full-res frames per GET

- **Location:** [`backend/services/preflight_quality.py:372-380`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/preflight_quality.py#L372-L380)
- **Category:** Performance · **Rule source:** `SKILL.md:81`
- **Work item:** M4-02 (P2) _issue pending_
- **Issue:** Every /sessions/{id}/quick-report and /reconstruction/preflight/{id} request decodes up to 60 full-resolution JPEGs and runs ORB + brute-force matching synchronously. The Map tab re-fetches the quick report whenever it is older than 30 s (frontend/src/features/map/hooks/useQuickReport.ts:10), so browsing sessions repeatedly burns seconds of CPU per view.
- **Fix:** Compute match density once after ingest (or on explicit request), persist it on the session, and use downscaled thumbnails for the ORB sample.

### BP-PERF · Every ingested frame is decoded twice for quality scoring

- **Location:** [`backend/services/quality.py:26-39`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/quality.py#L26-L39)
- **Category:** Performance · **Rule source:** `SKILL.md:81`
- **Work item:** M4-02 (P2) _issue pending_
- **Issue:** score_sharpness and score_brightness each call cv2.imread on the same file, and ingest_orchestrator.py:182-183 calls both per image (plus a PIL open for EXIF and another for the thumbnail), roughly doubling decode time for 12-20 MP drone frames during import.
- **Fix:** Add a score_image(filepath) that decodes once (optionally at reduced resolution via IMREAD_REDUCED_GRAYSCALE_2) and returns both metrics.

### BP-PERF · Outlier filter degrades to O(N^2) Python loops on real splats

- **Location:** [`backend/services/splat_cleanup.py:224-310`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/splat_cleanup.py#L224-L310)
- **Category:** Performance · **Rule source:** `SKILL.md:81`
- **Work item:** M4-02 (P2) _issue pending_
- **Issue:** The module docstring promises a k-d tree, but _grid_based_mean_knn loops over every Gaussian in Python. The 256-cell grid spans the full bounding box, which floaters (what this cleanup targets) stretch enormously, so most Gaussians share a few cells and each point computes distances to a huge candidate set, with full O(N) rescans for sparse points. It runs synchronously inside the POST /cleanup request.
- **Fix:** Use scipy.spatial.cKDTree (or a percentile-clipped grid built with numpy) and run cleanup as a queued job; update the docstring to match.

### BP-PERF · Initial scale k-NN allocates a 4096 x N distance matrix on the GPU

- **Location:** [`backend/services/splat_backends/cuda_gsplat.py:269-282`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/splat_backends/cuda_gsplat.py#L269-L282)
- **Category:** Performance · **Rule source:** `SKILL.md:81`
- **Work item:** M4-02 (P2) _issue pending_
- **Issue:** _initial_log_scales computes torch.cdist for 4,096-point chunks against the entire sparse cloud. With a typical 150k-300k point COLMAP model that is 2.4-4.9 GB of float32 per chunk, exceeding the 4 GB VRAM target stated in the module docstring (line 34) before training even starts, and surfacing as 'GPU ran out of memory — switch to quick preset', which cannot help because the sparse cloud size is independent of preset.
- **Fix:** Size the chunk from N and available memory (e.g. chunk = max(1, 2**28 // N)), or compute k-NN on CPU with a KD-tree before moving to the device.

### BP-QUAL · Parity evaluator depends on private backend helpers

- **Location:** [`scripts/benchmark_heldout_parity.py:535-568`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/scripts/benchmark_heldout_parity.py#L535-L568)
- **Category:** Architecture · **Rule source:** `SKILL.md:81`
- **Work item:** M3-09 (P3) _issue pending_
- **Issue:** The release evidence harness calls `cuda_gsplat._import_training_deps`, `_camera_intrinsics`, `_rasterize_cloud`, `_psnr`, `_ssim` and `colmap_io._pick_best_submodel` (also benchmark_metal_presets.py:119). A rename or signature change in these private functions breaks the release gate with no test or type check linking them.
- **Fix:** Expose a small public evaluator API in the backend (e.g. `render_and_score(cloud, image, camera, size)`) and cover it with a unit test the scripts rely on.

### BP-QUAL · Diagnostics suggest matcher values the settings API rejects

- **Location:** [`backend/services/reconstruction.py:512-542`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L512-L542)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M5-01 (P3) _issue pending_
- **Issue:** build_reconstruction_diagnostics recommends {'matcher': 'exhaustive_guided'} and {'matcher': 'sequential_guided'}, and _colmap_matcher_command supports them, but ReconstructionSettings.validate_matcher (routers/settings.py:122-127) only accepts 'exhaustive' or 'sequential'. The suggested fix cannot be applied through the API or UI; users must hand-edit config.yaml.
- **Fix:** Accept the guided variants in the settings validator (single shared enum) and add a test that every suggested setting validates.

### UNI-ANTI-005 · Test-only legacy wrappers ship in the production module

- **Location:** [`backend/services/reconstruction.py:2613-2683`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L2613-L2683)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:90`
- **Work item:** M5-01 (P3) _issue pending_
- **Issue:** _FakeEntry and three *_legacy functions exist only so unit tests can call handlers, and each swallows every exception with `except Exception: pass`. They also call mark_complete(-1) against the real queue table.
- **Fix:** Move the fake entry and wrappers into tests/backend/conftest.py (or call the handlers with a fixture-built entry) and delete them from the service.

### UNI-ORG-001 · reconstruction router holds ~40 endpoints and 25 models in one file

- **Location:** [`backend/routers/reconstruction.py:66-69`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/reconstruction.py#L66-L69)
- **Category:** Architecture · **Rule source:** `assets/rules/universal.md:54`
- **Work item:** M5-01 (P3) _issue pending_
- **Issue:** The 1,560-line router mixes job control, downloads, quality reports, semantic labels, splat-transform tooling, WebODM dispatch and preflight, with the same 'query Reconstruction or 404' block repeated about 30 times.
- **Fix:** Split into sub-routers (jobs, artifacts, quality, semantic, splat_tools) sharing a `reconstruction_or_404` dependency.

### UNI-CMT-007 · .splat quaternion comment describes a reindex that does not exist

- **Location:** [`backend/services/ply_io.py:230-233`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/ply_io.py#L230-L233)
- **Category:** Documentation · **Rule source:** `assets/rules/universal.md:71`
- **Work item:** M5-01 (P3) _issue pending_
- **Issue:** The docstring tells maintainers to 'swap the quats[:, [1, 2, 3, 0]] reindex here', but no reindex exists; the only related code is the packing at line 250. It also cites antimatter15's loader as expecting x,y,z,w, while that format (and this writer) use w,x,y,z (the auditor recalls this from antimatter15's convert.py, unverified). No test pins the byte order, so a 'fix' following the comment would silently garble rotations.
- **Fix:** Rewrite the note to state the packed order and the evidence for it, and add a round-trip test asserting rot bytes for a known quaternion.

### UNI-CMT-007 · ARCHITECTURE.md still says there is no task queue

- **Location:** [`docs/ARCHITECTURE.md:71`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/docs/ARCHITECTURE.md#L71)
- **Category:** Documentation · **Rule source:** `assets/rules/universal.md:71`
- **Work item:** M5-02 (P3) _issue pending_
- **Issue:** The architecture doc states jobs run as a daemon thread with 'no task queue', but backend/services/job_queue.py is a persistent SQLite job queue with a drain worker, retries, cross-process file lock and startup reaper. New contributors get the wrong mental model for cancellation, retries and multi-process behavior.
- **Fix:** Rewrite the 'reconstruction job' section to describe job_queue.py (states, retries, drain lock, reaper).

### UNI-CMT-007 · Survey report footer claims PDF was not generated, even inside the PDF

- **Location:** [`backend/services/survey_report.py:397-401`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/survey_report.py#L397-L401)
- **Category:** Documentation · **Rule source:** `assets/rules/universal.md:71`
- **Work item:** M5-02 (P3) _issue pending_
- **Issue:** The same HTML is rendered to PDF by export_survey_report(format='pdf') (routers/export.py:812-827), so every generated PDF ends with text saying PDF generation was not requested or WeasyPrint is missing.
- **Fix:** Pass the output format into _render_html and only emit the print-to-PDF hint for HTML output.

### UNI-ANTI-006 · Hand-rolled HTML escaping instead of html.escape

- **Location:** [`backend/services/survey_report.py:259-265`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/survey_report.py#L259-L265)
- **Category:** Security · **Rule source:** `assets/rules/universal.md:91`
- **Work item:** M5-02 (P3) _issue pending_
- **Issue:** The local esc() omits single quotes and is only safe because every call site happens to be element text. Any future use inside a single-quoted attribute becomes an injection point in a report served as text/html on the API origin.
- **Fix:** Use html.escape(value, quote=True) (or a template engine with autoescape) for all interpolated values.

### UNI-ANTI-005 · parse_gcp_csv is dead code that skips the whitespace guard

- **Location:** [`backend/services/georeferencing_workflows.py:95-113`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/georeferencing_workflows.py#L95-L113)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:90`
- **Work item:** M5-02 (P3) _issue pending_
- **Issue:** Nothing imports parse_gcp_csv. It also contradicts render_gcp_list's documented precondition (lines 81-82) because it does not apply the whitespace validation GcpPointIn enforces (routers/georeferencing.py:39-45), so wiring it up later would reintroduce the #629 column-shift bug.
- **Fix:** Delete it, or route it through the same validation and add tests before exposing it.

### UNI-CMT-007 · Install hint recommends 'uv add rasterio'

- **Location:** [`backend/services/orthomosaic_export.py:180-184`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/orthomosaic_export.py#L180-L184)
- **Category:** Documentation · **Rule source:** `assets/rules/universal.md:71`
- **Work item:** M5-02 (P3) _issue pending_
- **Issue:** `uv add` edits pyproject.toml and the lock; the documented install path (CONTRIBUTING.md, elevation_export.py:38-42) is `uv sync --group backend --group reconstruction`, where rasterio is already declared.
- **Fix:** Use the same guidance text as elevation_export.py.

### UNI-ORG-003 · Backend imports the CLI package through the 'src.' directory path

- **Location:** [`backend/services/preflight_quality.py:12`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/preflight_quality.py#L12)
- **Category:** Architecture · **Rule source:** `assets/rules/universal.md:56`
- **Work item:** M5-02 (P3) _issue pending_
- **Issue:** preflight_quality.py and routers/srt.py:11-12 import `src.drone_video_geotagger`, which only resolves because the repo root is on sys.path (pytest pythonpath, CWD in Docker, PyInstaller collection). The installed package is `drone_video_geotagger`, so the same module can be loaded twice under two names (separate module state), and any layout change (src/ moved, wheel-only install) breaks backend imports at runtime rather than at lint time.
- **Fix:** Import `drone_video_geotagger.*` (the installed package) everywhere and add an import-linter/ruff banned-module rule for `src.`.

### UNI-ANTI-005 · _timestamp_seconds has two identical branches

- **Location:** [`backend/services/preflight_quality.py:60-63`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/preflight_quality.py#L60-L63)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:90`
- **Work item:** M5-02 (P3) _issue pending_
- **Issue:** Both branches call ts.timestamp(); for naive values this interprets the time as local time, exactly the pitfall flight_log_sync._image_timestamp_s (lines 168-176) documents and avoids. Gap/duplicate detection is unaffected, but GPS-lock speed checks mix interpretations if a naive value ever reaches here.
- **Fix:** Reuse flight_log_sync._image_timestamp_s (attach UTC to naive values) and delete the duplicate helper.

### UNI-ANTI-005 · merge_session_workspace is only exercised by tests

- **Location:** [`backend/services/session_merge.py:135-208`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/session_merge.py#L135-L208)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:90`
- **Work item:** M5-02 (P3) _issue pending_
- **Issue:** No production code calls merge_session_workspace; multi-session runs build their image list inline in reconstruction.start_reconstruction (lines 2106-2128) and use data_dir/colmap/<rec_id>. The helper writes a separate merged_<ids> manifest that nothing reads, so tests validate behavior the product does not use and the two selection implementations can drift.
- **Fix:** Either make start_reconstruction use this helper (and its manifest) or delete it and move its tests to the real code path.

### UNI-CMT-007 · Merge overlap comment says 500 m; code allows 10 km

- **Location:** [`backend/services/session_merge.py:78-126`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/session_merge.py#L78-L126)
- **Category:** Documentation · **Rule source:** `assets/rules/universal.md:71`
- **Work item:** M5-02 (P3) _issue pending_
- **Issue:** The comment promises a 500 m proximity check, but MAX_OVERLAP_DISTANCE_M is 10,000 m and the 'center' of each session is simply its first GPS-tagged image, so two sessions whose flights never overlap pass validation.
- **Fix:** Compare footprint unions or bounding boxes for actual overlap, and keep the comment in sync with the threshold.

### UNI-FUNC-006 · _restore_session_archive has cyclomatic complexity 32 (203 lines)

- **Location:** [`backend/services/session_bundle.py:288`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/session_bundle.py#L288)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:39`
- **Work item:** M5-03 (P3) _issue pending_
- **Issue:** ruff C901 reports complexity 32 (threshold 10) for `_restore_session_archive` at lines 288-490. Functions this branchy are where the audit found most of its correctness bugs, and they cannot be unit-tested branch by branch.
- **Fix:** Split the function into named helpers (one per phase/branch family) and enable ruff C901 with max-complexity 15 in pyproject.toml so new code cannot exceed it.

### UNI-FUNC-006 · _discover_candidates has cyclomatic complexity 25 (137 lines)

- **Location:** [`backend/services/storage_lifecycle.py:118`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/storage_lifecycle.py#L118)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:39`
- **Work item:** M5-03 (P3) _issue pending_
- **Issue:** ruff C901 reports complexity 25 (threshold 10) for `_discover_candidates` at lines 118-254. Functions this branchy are where the audit found most of its correctness bugs, and they cannot be unit-tested branch by branch.
- **Fix:** Split the function into named helpers (one per phase/branch family) and enable ruff C901 with max-complexity 15 in pyproject.toml so new code cannot exceed it.

### UNI-FUNC-006 · extract_exif has cyclomatic complexity 24 (110 lines)

- **Location:** [`backend/services/ingest.py:68`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/ingest.py#L68)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:39`
- **Work item:** M5-03 (P3) _issue pending_
- **Issue:** ruff C901 reports complexity 24 (threshold 10) for `extract_exif` at lines 68-177. Functions this branchy are where the audit found most of its correctness bugs, and they cannot be unit-tested branch by branch.
- **Fix:** Split the function into named helpers (one per phase/branch family) and enable ruff C901 with max-complexity 15 in pyproject.toml so new code cannot exceed it.

### UNI-FUNC-006 · apply_policy has cyclomatic complexity 23 (136 lines)

- **Location:** [`backend/services/storage_lifecycle.py:299`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/storage_lifecycle.py#L299)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:39`
- **Work item:** M5-03 (P3) _issue pending_
- **Issue:** ruff C901 reports complexity 23 (threshold 10) for `apply_policy` at lines 299-434. Functions this branchy are where the audit found most of its correctness bugs, and they cannot be unit-tested branch by branch.
- **Fix:** Split the function into named helpers (one per phase/branch family) and enable ruff C901 with max-complexity 15 in pyproject.toml so new code cannot exceed it.

### UNI-FUNC-006 · _artifact_source has cyclomatic complexity 19 (79 lines)

- **Location:** [`backend/services/share_bundle.py:81`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/share_bundle.py#L81)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:39`
- **Work item:** M5-03 (P3) _issue pending_
- **Issue:** ruff C901 reports complexity 19 (threshold 10) for `_artifact_source` at lines 81-159. Functions this branchy are where the audit found most of its correctness bugs, and they cannot be unit-tested branch by branch.
- **Fix:** Split the function into named helpers (one per phase/branch family) and enable ruff C901 with max-complexity 15 in pyproject.toml so new code cannot exceed it.

### UNI-FUNC-006 · _run has cyclomatic complexity 19 (213 lines)

- **Location:** [`backend/services/ingest_orchestrator.py:45`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/ingest_orchestrator.py#L45)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:39`
- **Work item:** M5-03 (P3) _issue pending_
- **Issue:** ruff C901 reports complexity 19 (threshold 10) for `_run` at lines 45-257. Functions this branchy are where the audit found most of its correctness bugs, and they cannot be unit-tested branch by branch.
- **Fix:** Split the function into named helpers (one per phase/branch family) and enable ruff C901 with max-complexity 15 in pyproject.toml so new code cannot exceed it.

### UNI-FUNC-006 · get_deployment_config has cyclomatic complexity 19 (93 lines)

- **Location:** [`backend/core/config.py:501`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/core/config.py#L501)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:39`
- **Work item:** M5-03 (P3) _issue pending_
- **Issue:** ruff C901 reports complexity 19 (threshold 10) for `get_deployment_config` at lines 501-593. Functions this branchy are where the audit found most of its correctness bugs, and they cannot be unit-tested branch by branch.
- **Fix:** Split the function into named helpers (one per phase/branch family) and enable ruff C901 with max-complexity 15 in pyproject.toml so new code cannot exceed it.

### UNI-FUNC-006 · build_preflight_quality_report has cyclomatic complexity 17 (97 lines)

- **Location:** [`backend/services/preflight_quality.py:313`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/preflight_quality.py#L313)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:39`
- **Work item:** M5-03 (P3) _issue pending_
- **Issue:** ruff C901 reports complexity 17 (threshold 10) for `build_preflight_quality_report` at lines 313-409. Functions this branchy are where the audit found most of its correctness bugs, and they cannot be unit-tested branch by branch.
- **Fix:** Split the function into named helpers (one per phase/branch family) and enable ruff C901 with max-complexity 15 in pyproject.toml so new code cannot exceed it.

### UNI-FUNC-006 · _parse_glb_vertex_positions has cyclomatic complexity 16 (75 lines)

- **Location:** [`backend/services/quality_report.py:379`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/quality_report.py#L379)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:39`
- **Work item:** M5-03 (P3) _issue pending_
- **Issue:** ruff C901 reports complexity 16 (threshold 10) for `_parse_glb_vertex_positions` at lines 379-453. Functions this branchy are where the audit found most of its correctness bugs, and they cannot be unit-tested branch by branch.
- **Fix:** Split the function into named helpers (one per phase/branch family) and enable ruff C901 with max-complexity 15 in pyproject.toml so new code cannot exceed it.

### UNI-FUNC-006 · patch_settings has cyclomatic complexity 16 (51 lines)

- **Location:** [`backend/routers/settings.py:401`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/settings.py#L401)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:39`
- **Work item:** M5-03 (P3) _issue pending_
- **Issue:** ruff C901 reports complexity 16 (threshold 10) for `patch_settings` at lines 401-451. Functions this branchy are where the audit found most of its correctness bugs, and they cannot be unit-tested branch by branch.
- **Fix:** Split the function into named helpers (one per phase/branch family) and enable ruff C901 with max-complexity 15 in pyproject.toml so new code cannot exceed it.

### UNI-FUNC-006 · parse_srt_text has cyclomatic complexity 15 (92 lines)

- **Location:** [`src/drone_video_geotagger/telemetry.py:36`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/src/drone_video_geotagger/telemetry.py#L36)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:39`
- **Work item:** M5-03 (P3) _issue pending_
- **Issue:** ruff C901 reports complexity 15 (threshold 10) for `parse_srt_text` at lines 36-127. Functions this branchy are where the audit found most of its correctness bugs, and they cannot be unit-tested branch by branch.
- **Fix:** Split the function into named helpers (one per phase/branch family) and enable ruff C901 with max-complexity 15 in pyproject.toml so new code cannot exceed it.

### UNI-FUNC-006 · _run_pipeline has cyclomatic complexity 15 (210 lines)

- **Location:** [`backend/services/reconstruction.py:2248`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L2248)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:39`
- **Work item:** M5-03 (P3) _issue pending_
- **Issue:** ruff C901 reports complexity 15 (threshold 10) for `_run_pipeline` at lines 2248-2457. Functions this branchy are where the audit found most of its correctness bugs, and they cannot be unit-tested branch by branch.
- **Fix:** Split the function into named helpers (one per phase/branch family) and enable ruff C901 with max-complexity 15 in pyproject.toml so new code cannot exceed it.

### UNI-FUNC-006 · _run_colmap has cyclomatic complexity 15 (163 lines)

- **Location:** [`backend/services/reconstruction.py:234`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L234)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:39`
- **Work item:** M5-03 (P3) _issue pending_
- **Issue:** ruff C901 reports complexity 15 (threshold 10) for `_run_colmap` at lines 234-396. Functions this branchy are where the audit found most of its correctness bugs, and they cannot be unit-tested branch by branch.
- **Fix:** Split the function into named helpers (one per phase/branch family) and enable ruff C901 with max-complexity 15 in pyproject.toml so new code cannot exceed it.

### UNI-FUNC-006 · _load_ply_positions_and_colors has cyclomatic complexity 15 (74 lines)

- **Location:** [`backend/services/reconstruction.py:1001`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L1001)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:39`
- **Work item:** M5-03 (P3) _issue pending_
- **Issue:** ruff C901 reports complexity 15 (threshold 10) for `_load_ply_positions_and_colors` at lines 1001-1074. Functions this branchy are where the audit found most of its correctness bugs, and they cannot be unit-tested branch by branch.
- **Fix:** Split the function into named helpers (one per phase/branch family) and enable ruff C901 with max-complexity 15 in pyproject.toml so new code cannot exceed it.

### UNI-FUNC-006 · start has cyclomatic complexity 15 (68 lines)

- **Location:** [`backend/routers/reconstruction.py:537`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/reconstruction.py#L537)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:39`
- **Work item:** M5-03 (P3) _issue pending_
- **Issue:** ruff C901 reports complexity 15 (threshold 10) for `start` at lines 537-604. Functions this branchy are where the audit found most of its correctness bugs, and they cannot be unit-tested branch by branch.
- **Fix:** Split the function into named helpers (one per phase/branch family) and enable ruff C901 with max-complexity 15 in pyproject.toml so new code cannot exceed it.

### UNI-ANTI-005 · STATUS_BADGE colour fields are dead and running_remote has no label

- **Location:** [`frontend/src/features/reconstruct/ReconstructTab.tsx:223-240`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/reconstruct/ReconstructTab.tsx#L223-L240)
- **Category:** Maintainability · **Rule source:** `assets/rules/universal.md:90`
- **Work item:** M5-06 (P3) _issue pending_
- **Issue:** `StatusBadge` reads only `s.label`; the `bg`/`text` values in STATUS_BADGE are never used because colour comes from `jobStatusBadgeColor`. Neither map has an entry for `running_remote`, a live status (reconstructionStatusEvents.ts:12), so a remote-worker job shows the raw string 'running_remote' with the muted badge.
- **Fix:** Collapse to one `Record<Job['status'], {label, color}>` typed on the status union so a missing status is a compile error.

## LOW (17)

### BP-SEC · Cesium token sent to an unvalidated onComplete URL

- **Location:** [`backend/services/cesium_ion.py:180-190`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/cesium_ion.py#L180-L190)
- **Category:** Security · **Rule source:** `SKILL.md:81`
- **Work item:** M1-15 (P1) _issue pending_
- **Issue:** The completion call attaches the Cesium ion bearer token to whatever URL and method the asset-creation response supplies, without the HTTPS/host checks applied to api_url and the S3 endpoint. A misconfigured or spoofed api_url (allow_insecure_http) could redirect the token to another host.
- **Fix:** Require https and the configured api_url host for onComplete.url, and restrict method to POST/PUT.

### BP-QUAL · 'API key' check can never match a lower-cased string

- **Location:** [`backend/services/dji_log_parser.py:232`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/dji_log_parser.py#L232)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M1-15 (P1) _issue pending_
- **Issue:** The needle contains upper-case letters but the haystack is lower-cased, so only the 'decrypt' branch ever detects a missing-key failure; the router (routers/flight_log.py:181-183) repeats the same test with two identical branches.
- **Fix:** Compare against 'api key' and collapse the router's duplicate branches.

### BP-SEC · Docker base images are pinned by tag, not digest

- **Location:** [`Dockerfile:3-26`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/Dockerfile#L3-L26)
- **Category:** Supply chain · **Rule source:** `SKILL.md:81`
- **Work item:** M1-15 (P1) _issue pending_
- **Issue:** `node:22-bookworm-slim`, `python:3.12-slim-bookworm` and `ghcr.io/astral-sh/uv:0.11.16` are mutable tags, while the repo pins every GitHub Action by commit SHA and enforces that in tests/test_supply_chain_configuration.py. Image rebuilds are not reproducible and a retagged upstream image is picked up silently.
- **Fix:** Pin each FROM/COPY --from image by `@sha256:` digest (Dependabot's docker ecosystem can keep them current) and extend the supply-chain test to assert it.

### BP-QUAL · Most CI jobs have no timeout-minutes

- **Location:** [`.github/workflows/ci.yml:41-44`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/.github/workflows/ci.yml#L41-L44)
- **Category:** CI / test strategy · **Rule source:** `SKILL.md:81`
- **Work item:** M2-01 (P1) _issue pending_
- **Issue:** test, frontend, docker-build, distribution, windows-package and macos-package jobs rely on the 360-minute default. Only the dispatch-only benchmark jobs set a timeout, so a hung COLMAP probe or packaging step can hold a (costly macOS) runner for six hours.
- **Fix:** Set `timeout-minutes` on every job (e.g. 20 for test/frontend, 45 for packaging).

### BP-QUAL · Scheduled backup failures are logged without any cause

- **Location:** [`backend/services/artifact_backup_schedule.py:141-143`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/artifact_backup_schedule.py#L141-L143)
- **Category:** Observability · **Rule source:** `SKILL.md:81`
- **Work item:** M3-01 (P2) _issue pending_
- **Issue:** Every failure (disk full, unapproved destination, rclone missing, DB locked) produces the same one-line warning and a {'status': 'failed'} result, so an operator cannot tell why the nightly backup has been failing.
- **Fix:** Log the exception type and a sanitized message (or exc_info for non-BackupError exceptions) and include an error code in the status result.

### BP-QUAL · dji_api_key_path resolves against CWD, not config dir

- **Location:** [`backend/core/config.py:433-439`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/core/config.py#L433-L439)
- **Category:** Configuration · **Rule source:** `SKILL.md:81`
- **Work item:** M3-02 (P2) _issue pending_
- **Issue:** docs/ARCHITECTURE.md:54 states relative directory settings resolve against the config file's location, but dji_api_key_path is opened relative to the process working directory, so the key is silently not found when the app is launched from another directory.
- **Fix:** Resolve a relative dji_api_key_path against Path(config_path).resolve().parent before opening it.

### BP-QUAL · HTTP status chosen by substring-matching exception text

- **Location:** [`backend/routers/reconstruction.py:431-437`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/reconstruction.py#L431-L437)
- **Category:** Error handling · **Rule source:** `SKILL.md:81`
- **Work item:** M3-03 (P2) _issue pending_
- **Issue:** _raise_start_error maps ValueError messages to 404/409/422 by searching for 'not found' and 'already running'. start_reconstruction's duplicate message says 'already in progress', so a duplicate dense rerun gets 422 instead of 409, and any reworded message silently changes the API contract.
- **Fix:** Raise typed exceptions (NotFoundError, ConflictError) from the services and map them by type.

### BP-DATA · Auto-import sessions reference files on removable media

- **Location:** [`backend/services/auto_import.py:180-206`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/auto_import.py#L180-L206)
- **Category:** Data integrity · **Rule source:** `SKILL.md:81`
- **Work item:** M3-05 (P2) _issue pending_
- **Issue:** By design (docs/USER-MANUAL.md:670) auto-import does not copy card contents, so Session.folder_path and every Image.filepath point at the SD card. Once the card is ejected or reformatted, thumbnails survive but reconstruction, exports and WebODM packages fail on missing originals with no warning in the UI.
- **Fix:** Offer an opt-in copy-to-imports_dir mode for auto-import, and surface a 'source media unavailable' state when a session's folder_path is missing.

### BP-PERF · Measurement overlay built after cancellation is never disposed

- **Location:** [`frontend/src/features/splat/SplatViewerTab.tsx:475-563`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/splat/SplatViewerTab.tsx#L475-L563)
- **Category:** Resource management · **Rule source:** `SKILL.md:81`
- **Work item:** M3-07 (P2) _issue pending_
- **Issue:** The async builder awaits dynamic imports of three and turf. If the points change mid-build, cleanup sets `cancelled`, but the geometry, materials and CanvasTexture already created are simply dropped (`if (!cancelled) scene.add(group)`), leaking GPU memory.
- **Fix:** When `cancelled` is true at the end of the builder, traverse and dispose the new group before returning.

### BP-QUAL · Object URL revoked synchronously after triggering the download

- **Location:** [`frontend/src/features/splat/SplatViewerTab.tsx:1021-1028`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/splat/SplatViewerTab.tsx#L1021-L1028)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M3-07 (P2) _issue pending_
- **Issue:** `downloadBlob` revokes the blob URL on the same tick as `a.click()`. Some browsers start the download asynchronously and cancel it when the URL is already revoked, losing a recorded flythrough.
- **Fix:** Revoke in a `setTimeout(..., 0)` (or after a short delay) so the download has started.

### BP-DATA · Ingest validation counts an empty GPS IFD as a valid fix

- **Location:** [`src/drone_video_geotagger/pipeline.py:256-260`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/src/drone_video_geotagger/pipeline.py#L256-L260)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M3-08 (P2) _issue pending_
- **Issue:** Any image with a non-empty GPS IFD is counted as `gps_valid`, including files that carry only `GPSVersionID` or a zero lat/lon. The validation summary therefore over-reports how many frames are geotagged.
- **Fix:** Require GPSLatitude and GPSLongitude (and their refs) to be present and non-zero before counting a frame as valid.

### BP-QUAL · Held-out parity harness imports the Unix-only resource module at top level

- **Location:** [`scripts/benchmark_heldout_parity.py:16`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/scripts/benchmark_heldout_parity.py#L16)
- **Category:** Portability · **Rule source:** `SKILL.md:81`
- **Work item:** M3-09 (P3) _issue pending_
- **Issue:** `import resource` at module scope makes the whole script (including `run --kind cuda`) fail on Windows. benchmark_metal_presets.py:211-219 already fixed this exact bug (#878) by importing lazily; this copy did not get the fix. CI's CUDA runner is Linux, so only local Windows CUDA runs are affected.
- **Fix:** Import `resource` inside `_maximum_rss_bytes` and return 0 on win32, as benchmark_metal_presets.py does.

### BP-QUAL · Bundle extraction temp directories are never removed

- **Location:** [`scripts/benchmark_heldout_parity.py:470-472`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/scripts/benchmark_heldout_parity.py#L470-L472)
- **Category:** Resource management · **Rule source:** `SKILL.md:81`
- **Work item:** M3-09 (P3) _issue pending_
- **Issue:** `_read_bundle` extracts each evidence bundle (including a full splat.ply) into `mkdtemp()` and never deletes it; `compare` calls it twice per run, and `validate_fixture` does the same when no staged_root is passed (line 145). Repeated comparisons leak hundreds of MB into the system temp directory.
- **Fix:** Extract into a subdirectory of the caller's `TemporaryDirectory` workspace (pass it in) so it is cleaned up with the rest of the run.

### BP-DATA · Per-candidate maximum_rss_bytes is the process lifetime peak

- **Location:** [`scripts/benchmark_metal_presets.py:66-74`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/scripts/benchmark_metal_presets.py#L66-L74)
- **Category:** Correctness · **Rule source:** `SKILL.md:81`
- **Work item:** M3-09 (P3) _issue pending_
- **Issue:** `ru_maxrss` is the peak RSS of the whole process, so every candidate after the first records the maximum over all earlier candidates, not its own. The evidence JSON presents it as a per-run figure, and the cap probe's memory gate is fed a value contaminated by earlier runs.
- **Fix:** Run each candidate in a fresh subprocess (as benchmark_heldout_parity.py does with its worker) or label the field as a cumulative peak.

### BP-PERF · interpolate() scans all telemetry points twice for every frame

- **Location:** [`src/drone_video_geotagger/telemetry.py:175-190`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/src/drone_video_geotagger/telemetry.py#L175-L190)
- **Category:** Performance · **Rule source:** `SKILL.md:81`
- **Work item:** M4-03 (P3) _issue pending_
- **Issue:** Each call walks the full point list for the no-fix check and then again for the bracketing pair, so tagging F frames against P SRT points is O(F x P). A 30-minute 30 Hz SRT (54k points) with 2 fps frames (3.6k) is ~400M Python iterations.
- **Fix:** Precompute `starts = [p.start_s for p in points]` once and use `bisect` to find the bracketing pair, checking only the neighbouring points for a GPS fix.

### BP-PERF · Coverage gaps render one mesh and material per voxel

- **Location:** [`frontend/src/features/splat/SplatViewerTab.tsx:1364-1375`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/splat/SplatViewerTab.tsx#L1364-L1375)
- **Category:** Performance · **Rule source:** `SKILL.md:81`
- **Work item:** M4-03 (P3) _issue pending_
- **Issue:** Every gap cell gets its own BoxGeometry, MeshBasicMaterial and draw call. A large reconstruction with thousands of sparse cells produces thousands of draw calls on top of the splat renderer.
- **Fix:** Use one `THREE.InstancedMesh` per gap level with a shared box geometry and material.

### BP-QUAL · COLMAP TXT files read with locale encoding

- **Location:** [`backend/services/reconstruction.py:408`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L408)
- **Category:** Portability · **Rule source:** `SKILL.md:81`
- **Work item:** M5-01 (P3) _issue pending_
- **Issue:** _count_registered_images and _store_reprojection_errors (lines 682, 691) call read_text() with no encoding, while _registered_image_names (line 427) reads the same file as UTF-8. On Windows a non-ASCII image filename makes these parsers raise or mis-match names.
- **Fix:** Read COLMAP TXT output with encoding='utf-8', errors='replace' consistently (ideally through colmap_io).
