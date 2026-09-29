# M5 · v3.3 — Audit: Maintainability & Type Safety

**Priority band:** P3 · **Epic:** [#941](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/941) · **Work items:** 7 · **Findings:** 48

## Goal

Break up the oversized modules, remove copy-paste, and turn on the stricter compiler and linter settings the code already nearly satisfies.

## Exit criteria

- [ ] reconstruction.py and SplatViewerTab.tsx are split along the seams listed in their issues with no behaviour change (existing tests green).
- [ ] `strict: true` is enabled in frontend/tsconfig.app.json; ruff C901 (max 15) is enabled.
- [ ] No duplicated helper listed in this milestone remains.

## Work items

| Key | Title | Priority | Issue |
|---|---|---|---|
| [M5-01](#m5-01) | refactor(reconstruction): split reconstruction.py and its router | P3 | [#977](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/977) |
| [M5-02](#m5-02) | refactor(backend): deduplicate geo helpers and remove dead code | P3 | [#978](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/978) |
| [M5-03](#m5-03) | refactor: reduce cyclomatic complexity >= 15 and enable ruff C901 | P3 | [#979](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/979) |
| [M5-04](#m5-04) | refactor(geotag): shared ffmpeg probe and csv_safe | P3 | [#980](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/980) |
| [M5-05](#m5-05) | refactor(splat-viewer): split SplatViewerTab, type the viewer, use colour tokens | P3 | [#981](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/981) |
| [M5-06](#m5-06) | refactor(frontend): shared helpers for job status, downloads, uploads and export cards | P3 | [#982](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/982) |
| [M5-07](#m5-07) | chore(ts): enable strict and noUncheckedIndexedAccess | P3 | [#983](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/983) |

<a id="m5-01"></a>
### M5-01 · refactor(reconstruction): split reconstruction.py and its router

**Priority:** P3 · **Coverage area:** `reconstruction-splat` · **Labels:** `chore`, `backend`, `priority: low` · **Issue:** [#977](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/977)

2,683-line service and ~40-endpoint router; 'get or 404' copy-pasted ~30 times; three PLY parsers besides ply_io; test-only wrappers in production; diagnostics suggest rejected matcher values; locale-encoded TXT reads; stale ply_io comment.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `UNI-ANTI-003` | [`backend/services/reconstruction.py:741-790`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L741-L790) | Three hand-written PLY parsers besides ply_io |
| HIGH | `UNI-ORG-004` | [`backend/services/reconstruction.py:1-75`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L1-L75) | reconstruction.py is a 2,683-line module mixing unrelated responsibilities |
| HIGH | `UNI-ANTI-003` | [`backend/routers/reconstruction.py:607-612`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/reconstruction.py#L607-L612) | 'Load reconstruction or 404' copy-pasted ~30 times |
| MEDIUM | `BP-QUAL` | [`backend/services/reconstruction.py:512-542`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L512-L542) | Diagnostics suggest matcher values the settings API rejects |
| MEDIUM | `UNI-ANTI-005` | [`backend/services/reconstruction.py:2613-2683`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L2613-L2683) | Test-only legacy wrappers ship in the production module |
| MEDIUM | `UNI-ORG-001` | [`backend/routers/reconstruction.py:66-69`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/reconstruction.py#L66-L69) | reconstruction router holds ~40 endpoints and 25 models in one file |
| MEDIUM | `UNI-CMT-007` | [`backend/services/ply_io.py:230-233`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/ply_io.py#L230-L233) | .splat quaternion comment describes a reindex that does not exist |
| LOW | `BP-QUAL` | [`backend/services/reconstruction.py:408`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L408) | COLMAP TXT files read with locale encoding |

**Changes to make**

- Split into pipeline/, colmap_run, artifacts, comparisons, diagnostics modules; router split by sub-resource with a `get_reconstruction_or_404` dependency.
- Replace ad-hoc PLY parsing with ply_io; delete test-only wrappers (update tests to call real APIs); align diagnostics with settings validation; utf-8 reads; fix the comment.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| contract | reconstruction-splat | `tests/contract/test_frontend_api_contract.py` | Router split keeps every route and method (contract suite from M2-04). |
| unit | reconstruction-splat | `tests/backend/test_ply_io.py` | ply_io reads every PLY variant the removed parsers handled (fixtures). |

**Acceptance criteria**

- [ ] No module over 800 lines in services/reconstruction*; existing tests green.

<a id="m5-02"></a>
### M5-02 · refactor(backend): deduplicate geo helpers and remove dead code

**Priority:** P3 · **Coverage area:** `reconstruction-splat` · **Labels:** `chore`, `backend`, `priority: low` · **Issue:** [#978](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/978)

UTM zone derivation and geo-transform loading duplicated; dead parse_gcp_csv; `src.` import path; identical branches; stale comments/hints/docs; hand-rolled HTML escape.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `UNI-ANTI-003` | [`backend/services/georeferencing_solve.py:100-106`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/georeferencing_solve.py#L100-L106) | UTM zone derivation duplicated in two modules |
| HIGH | `UNI-ANTI-003` | [`backend/services/orthomosaic_export.py:29-40`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/orthomosaic_export.py#L29-L40) | _load_geo_transform_for_reconstruction duplicated |
| MEDIUM | `UNI-CMT-007` | [`docs/ARCHITECTURE.md:71`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/docs/ARCHITECTURE.md#L71) | ARCHITECTURE.md still says there is no task queue |
| MEDIUM | `UNI-CMT-007` | [`backend/services/survey_report.py:397-401`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/survey_report.py#L397-L401) | Survey report footer claims PDF was not generated, even inside the PDF |
| MEDIUM | `UNI-ANTI-006` | [`backend/services/survey_report.py:259-265`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/survey_report.py#L259-L265) | Hand-rolled HTML escaping instead of html.escape |
| MEDIUM | `UNI-ANTI-005` | [`backend/services/georeferencing_workflows.py:95-113`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/georeferencing_workflows.py#L95-L113) | parse_gcp_csv is dead code that skips the whitespace guard |
| MEDIUM | `UNI-CMT-007` | [`backend/services/orthomosaic_export.py:180-184`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/orthomosaic_export.py#L180-L184) | Install hint recommends 'uv add rasterio' |
| MEDIUM | `UNI-ORG-003` | [`backend/services/preflight_quality.py:12`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/preflight_quality.py#L12) | Backend imports the CLI package through the 'src.' directory path |
| MEDIUM | `UNI-ANTI-005` | [`backend/services/preflight_quality.py:60-63`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/preflight_quality.py#L60-L63) | _timestamp_seconds has two identical branches |
| MEDIUM | `UNI-ANTI-005` | [`backend/services/session_merge.py:135-208`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/session_merge.py#L135-L208) | merge_session_workspace is only exercised by tests |
| MEDIUM | `UNI-CMT-007` | [`backend/services/session_merge.py:78-126`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/session_merge.py#L78-L126) | Merge overlap comment says 500 m; code allows 10 km |

**Changes to make**

- Single geo helper module; delete dead code; `import drone_video_geotagger`; html.escape; update ARCHITECTURE.md and comments.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| unit | reconstruction-splat | `tests/backend/test_georeferencing_solve.py` | UTM zone helper covers zone boundaries, Norway/Svalbard exceptions and southern hemisphere. |

**Acceptance criteria**

- [ ] One implementation per helper; no dead code flagged by vulture on backend/.

<a id="m5-03"></a>
### M5-03 · refactor: reduce cyclomatic complexity >= 15 and enable ruff C901

**Priority:** P3 · **Coverage area:** `platform-ops` · **Labels:** `chore`, `python`, `priority: low` · **Issue:** [#979](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/979)

15 functions exceed complexity 15 (max 32 in _restore_session_archive).

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| MEDIUM | `UNI-FUNC-006` | [`backend/services/session_bundle.py:288`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/session_bundle.py#L288) | _restore_session_archive has cyclomatic complexity 32 (203 lines) |
| MEDIUM | `UNI-FUNC-006` | [`backend/services/storage_lifecycle.py:118`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/storage_lifecycle.py#L118) | _discover_candidates has cyclomatic complexity 25 (137 lines) |
| MEDIUM | `UNI-FUNC-006` | [`backend/services/ingest.py:68`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/ingest.py#L68) | extract_exif has cyclomatic complexity 24 (110 lines) |
| MEDIUM | `UNI-FUNC-006` | [`backend/services/storage_lifecycle.py:299`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/storage_lifecycle.py#L299) | apply_policy has cyclomatic complexity 23 (136 lines) |
| MEDIUM | `UNI-FUNC-006` | [`backend/services/share_bundle.py:81`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/share_bundle.py#L81) | _artifact_source has cyclomatic complexity 19 (79 lines) |
| MEDIUM | `UNI-FUNC-006` | [`backend/services/ingest_orchestrator.py:45`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/ingest_orchestrator.py#L45) | _run has cyclomatic complexity 19 (213 lines) |
| MEDIUM | `UNI-FUNC-006` | [`backend/core/config.py:501`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/core/config.py#L501) | get_deployment_config has cyclomatic complexity 19 (93 lines) |
| MEDIUM | `UNI-FUNC-006` | [`backend/services/preflight_quality.py:313`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/preflight_quality.py#L313) | build_preflight_quality_report has cyclomatic complexity 17 (97 lines) |
| MEDIUM | `UNI-FUNC-006` | [`backend/services/quality_report.py:379`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/quality_report.py#L379) | _parse_glb_vertex_positions has cyclomatic complexity 16 (75 lines) |
| MEDIUM | `UNI-FUNC-006` | [`backend/routers/settings.py:401`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/settings.py#L401) | patch_settings has cyclomatic complexity 16 (51 lines) |
| MEDIUM | `UNI-FUNC-006` | [`src/drone_video_geotagger/telemetry.py:36`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/src/drone_video_geotagger/telemetry.py#L36) | parse_srt_text has cyclomatic complexity 15 (92 lines) |
| MEDIUM | `UNI-FUNC-006` | [`backend/services/reconstruction.py:2248`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L2248) | _run_pipeline has cyclomatic complexity 15 (210 lines) |
| MEDIUM | `UNI-FUNC-006` | [`backend/services/reconstruction.py:234`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L234) | _run_colmap has cyclomatic complexity 15 (163 lines) |
| MEDIUM | `UNI-FUNC-006` | [`backend/services/reconstruction.py:1001`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/services/reconstruction.py#L1001) | _load_ply_positions_and_colors has cyclomatic complexity 15 (74 lines) |
| MEDIUM | `UNI-FUNC-006` | [`backend/routers/reconstruction.py:537`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/backend/routers/reconstruction.py#L537) | start has cyclomatic complexity 15 (68 lines) |

**Changes to make**

- Split each function into named phase helpers; enable `C901` with `max-complexity = 15` in ruff config.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| unit | platform-ops | `(per function)` | Unit tests for each extracted helper, especially error branches previously untested. |

**Acceptance criteria**

- [ ] ruff C901 passes at 15.

<a id="m5-04"></a>
### M5-04 · refactor(geotag): shared ffmpeg probe and csv_safe

**Priority:** P3 · **Coverage area:** `geotag-cli` · **Labels:** `chore`, `python`, `priority: low` · **Issue:** [#980](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/980)

ffmpeg invocation copied three times (video probed twice); csv_safe duplicated from backend.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `UNI-ANTI-003` | [`src/drone_video_geotagger/video.py:40-53`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/src/drone_video_geotagger/video.py#L40-L53) | ffmpeg invocation and not-found handling copied three times |
| HIGH | `UNI-ANTI-003` | [`src/drone_video_geotagger/audit.py:10-13`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/src/drone_video_geotagger/audit.py#L10-L13) | CSV formula guard duplicated from backend.core.csv_safe |

**Changes to make**

- `_probe()` once per video; move csv_safe into drone_video_geotagger and import from backend.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| unit | geotag-cli | `tests/cli/test_audit.py` | backend and CLI import the same csv_safe object. |

**Acceptance criteria**

- [ ] One probe per video; one csv_safe.

<a id="m5-05"></a>
### M5-05 · refactor(splat-viewer): split SplatViewerTab, type the viewer, use colour tokens

**Priority:** P3 · **Coverage area:** `frontend` · **Labels:** `chore`, `frontend`, `priority: low` · **Issue:** [#981](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/981)

2,204-line module; 20+ `any` for the viewer and Three.js groups; 35 hard-coded colours.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `RX-COMP-002` | [`frontend/src/features/splat/SplatViewerTab.tsx:863-1603`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/splat/SplatViewerTab.tsx#L863-L1603) | SplatViewerTab.tsx is a 2,204-line component module |
| HIGH | `TS-TYPE-001` | [`frontend/src/features/splat/SplatViewerTab.tsx:884-889`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/splat/SplatViewerTab.tsx#L884-L889) | Gaussian-splat viewer and Three.js groups are typed as any (20+ sites) |
| HIGH | `RX-MISC-003` | [`frontend/src/features/splat/SplatViewerTab.tsx:627-657`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/splat/SplatViewerTab.tsx#L627-L657) | Hard-coded colours in the splat viewer (35 literals) |

**Changes to make**

- Split into queries/SplatCanvas/layers/overlays/sidebar; `SplatViewerHandle` interface; overlay CSS tokens.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| component | frontend/splat | `frontend/src/features/splat/*.test.tsx` | Each extracted layer hook disposes its group on unmount (mock scene). |

**Acceptance criteria**

- [ ] No `any` in features/splat; file sizes < 500 lines.

<a id="m5-06"></a>
### M5-06 · refactor(frontend): shared helpers for job status, downloads, uploads and export cards

**Priority:** P3 · **Coverage area:** `frontend` · **Labels:** `chore`, `frontend`, `priority: low` · **Issue:** [#982](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/982)

Export cards, reconstruct form controls, job-status maps, blob download, multipart upload and error parsing are copied across components; nested ternaries in JSX.

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `UNI-ANTI-003` | [`frontend/src/features/export/ExportTab.tsx:225-303`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/export/ExportTab.tsx#L225-L303) | MeshExportCard and OrthoExportCard are copy-pasted |
| HIGH | `UNI-ANTI-003` | [`frontend/src/features/reconstruct/ReconstructTab.tsx:605-643`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/reconstruct/ReconstructTab.tsx#L605-L643) | Preset radios and target-area select duplicated for single and merge modes |
| HIGH | `RX-COND-004` | [`frontend/src/features/reconstruct/ReconstructTab.tsx:489-499`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/reconstruct/ReconstructTab.tsx#L489-L499) | Nested ternaries choose preflight badge colours inline |
| HIGH | `UNI-ANTI-003` | [`frontend/src/features/splat/VolumePanel.tsx:26-34`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/splat/VolumePanel.tsx#L26-L34) | Blob download helper copied into four components |
| HIGH | `UNI-ANTI-003` | [`frontend/src/features/jobs/JobsTab.tsx:304-335`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/jobs/JobsTab.tsx#L304-L335) | Job status badge map, colour mapper and formatDuration copied between tabs and already drifted |
| HIGH | `UNI-ANTI-003` | [`frontend/src/features/gps-sync/GpsSyncTab.tsx:146-161`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/gps-sync/GpsSyncTab.tsx#L146-L161) | Multipart uploads bypass the API client and re-implement its error parsing |
| MEDIUM | `UNI-ANTI-005` | [`frontend/src/features/reconstruct/ReconstructTab.tsx:223-240`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/src/features/reconstruct/ReconstructTab.tsx#L223-L240) | STATUS_BADGE colour fields are dead and running_remote has no label |

**Changes to make**

- shared/jobs/status.ts, shared/utils/downloadBlob.ts, api `postForm`, ArtifactJobCard/SectionCard, PresetPicker/TargetAreaSelect; lookup maps instead of nested ternaries.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| unit | frontend/shared | `frontend/src/shared/api/client.test.ts` | `postForm` applies the timeout and parses array-shaped 422 details. |
| unit | frontend/shared | `frontend/src/shared/jobs/status.test.ts (new)` | Every Job['status'] has a label and colour (exhaustive). |

**Acceptance criteria**

- [ ] No duplicated helper remains; running_remote renders correctly everywhere.

<a id="m5-07"></a>
### M5-07 · chore(ts): enable strict and noUncheckedIndexedAccess

**Priority:** P3 · **Coverage area:** `frontend` · **Labels:** `chore`, `frontend`, `priority: low` · **Issue:** [#983](https://github.com/BrandonRobare/telemetry-frame-mapper/issues/983)

`strict` is off (code already passes it with 0 errors); noUncheckedIndexedAccess reports 128 errors (85 non-test).

**Findings resolved**

| Severity | Rule | Location | Finding |
|---|---|---|---|
| HIGH | `TS-STRICT-001` | [`frontend/tsconfig.app.json:20-25`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/tsconfig.app.json#L20-L25) | Frontend tsconfig does not enable strict mode |
| HIGH | `TS-STRICT-006` | [`frontend/tsconfig.app.json:18-23`](https://github.com/BrandonRobare/telemetry-frame-mapper/blob/3ec2135b0569592b69a80ecdb569b85b83e6a81e/frontend/tsconfig.app.json#L18-L23) | noUncheckedIndexedAccess would flag 128 unchecked index reads |

**Changes to make**

- Enable strict now; fix index accesses folder by folder, then enable the flag.

**Tests to add or update**

| Level | Area | File | Test to add or update |
|---|---|---|---|
| contract | frontend | `frontend/tsconfig.app.json` | `tsc -b` in CI enforces both flags. |

**Acceptance criteria**

- [ ] Both flags on; build green.

_Line links point at commit `3ec2135` (the audited `main`)._
