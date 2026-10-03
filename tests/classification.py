"""Checked ownership and fixture-based levels for the existing test layout.

Add each new test file to its area here. Tests which hide DB/API access in helpers
must declare usefixtures (shared DB) or an explicit level (isolated resources).
"""

from pathlib import Path

import pytest

LEVELS = {"unit", "integration", "contract", "e2e", "perf", "hardware"}
AREA_FILES = {
    "geotag-cli": """
        cli/test_audit.py cli/test_exiftool.py cli/test_external_tools.py cli/test_frames.py
        cli/test_gps_quality.py cli/test_import_resolution.py cli/test_paths.py
        cli/test_pipeline.py cli/test_pipeline_cli.py cli/test_telemetry.py
    """,
    "ingest-import": """
        backend/test_api_sessions.py backend/test_auto_import.py
        backend/test_duplicate_detection.py backend/test_images_router.py backend/test_ingest.py
        backend/test_ingest_orchestrator.py backend/test_preflight_quality.py
        backend/test_quality.py
        backend/test_session_bundle.py backend/test_session_merge.py backend/test_sessions_router.py
        backend/test_upload_reader.py backend/test_upload_reservation_cap.py
        backend/test_uploads_router.py
    """,
    "flight-log-gps": """
        backend/test_dji_log_parser.py backend/test_flight_entries_router.py
        backend/test_flight_log_router.py backend/test_flight_log_sync.py backend/test_srt_router.py
    """,
    "coverage-planning": """
        backend/test_coverage_router.py backend/test_footprints_router.py backend/test_geometry.py
        backend/test_mission_planner.py backend/test_mission_planner_ext.py
        backend/test_plans_router.py
        backend/test_rth_terrain_safety.py backend/test_slope_overlay.py
        backend/test_target_areas_router.py backend/test_terrain.py backend/test_tiles_router.py
    """,
    "reconstruction-splat": """
        backend/test_accelerator.py backend/test_annotations_model.py
        backend/test_annotations_router.py backend/test_artifact_cleanup.py
        backend/test_benchmark_metal_presets.py backend/test_camera_calibration.py
        backend/test_cesium_tiles.py backend/test_colmap_io.py backend/test_colmap_parser_compat.py
        backend/test_comparisons_metrics.py backend/test_comparisons_router.py
        backend/test_dense_rerun.py backend/test_georeferencing_accuracy.py
        backend/test_georeferencing_router.py backend/test_georeferencing_solve.py
        backend/test_job_queue.py backend/test_jobs_router.py backend/test_measurements_model.py
        backend/test_measurements_router.py backend/test_metal_msplat_backend.py
        backend/test_metal_msplat_integration.py backend/test_metal_submodel_selection.py
        backend/test_nearest_gaussian_indices.py backend/test_ply_io.py
        backend/test_reconstruction_lineage.py backend/test_reconstruction_router.py
        backend/test_reconstruction_service.py backend/test_remote_worker.py
        backend/test_semantic_labels.py backend/test_semantic_segmenter.py
        backend/test_splat_backends.py
        backend/test_splat_cleanup.py backend/test_splat_trainer.py backend/test_splat_transform.py
        test_heldout_parity_benchmark.py test_metal_preset_benchmark.py test_metal_release_gate.py
    """,
    "export-share": """
        backend/test_cesium_ion.py backend/test_csv_safe.py backend/test_elevation_export.py
        backend/test_geopackage_export.py backend/test_measurements_export.py
        backend/test_orthomosaic_export.py backend/test_potree_export.py
        backend/test_quality_report.py
        backend/test_quick_report.py backend/test_reproducibility_manifest.py
        backend/test_share_bundle_export.py backend/test_share_links.py backend/test_splat_export.py
        backend/test_survey_report.py backend/test_usd_export.py backend/test_webodm.py
        contract/test_frontend_api_contract.py contract/test_export_contract.py
        backend/test_webodm_package_export.py
    """,
    "platform-ops": """
        backend/test_application_logging.py backend/test_artifact_backup.py
        backend/test_artifact_backup_schedule.py backend/test_backend_runner.py
        backend/test_config.py
        backend/test_defects_model.py backend/test_defects_router.py
        backend/test_deployment_config.py
        backend/test_frontend_static_mount.py backend/test_main.py backend/test_main_bundle_ui.py
        backend/test_metrics.py backend/test_path_confinement.py backend/test_pin_lock.py
        backend/test_projects.py backend/test_runtime_dir_access.py backend/test_settings_router.py
        backend/test_storage.py backend/test_storage_lifecycle.py backend/test_storage_router.py
        backend/test_system_router.py contract/test_openapi_types.py test_markers_contract.py
    """,
    "db-migrations": """
        backend/db/test_backup_restore_roundtrip.py backend/db/test_migration_ownership.py
        backend/test_database.py backend/test_test_db_isolation.py
    """,
    "frontend-shared": "",
    "packaging-release": """
        backend/test_dev_launcher_contract.py backend/test_macos_packaging.py
        backend/test_windows_packaging.py cli/test_wheel_contract.py
        test_supply_chain_configuration.py
    """,
}
AREA_BY_FILE = {}
for area, files in AREA_FILES.items():
    for filename in files.split():
        if filename in AREA_BY_FILE:
            raise ValueError(f"Conflicting area mappings for {filename}")
        AREA_BY_FILE[filename] = area

# Cross-boundary checks and real hardware have a more specific level than fixture inference.
LEVEL_BY_FILE = {
    **dict.fromkeys(
        """backend/db/test_backup_restore_roundtrip.py backend/db/test_migration_ownership.py
        backend/test_database.py backend/test_test_db_isolation.py
        backend/test_dev_launcher_contract.py backend/test_macos_packaging.py
        backend/test_windows_packaging.py cli/test_wheel_contract.py
        contract/test_frontend_api_contract.py contract/test_openapi_types.py
        contract/test_export_contract.py test_markers_contract.py
        test_supply_chain_configuration.py""".split(),
        "contract",
    ),
    "backend/test_colmap_parser_compat.py": "integration",
    "backend/test_metal_msplat_integration.py": "hardware",
}
SHARED_DB_FIXTURES = {"client", "db_session", "setup_test_db", "db_engine"}
INTEGRATION_FIXTURES = SHARED_DB_FIXTURES | {"isolated_engine"}


def area_for(path: Path, root: Path) -> str:
    filename = path.relative_to(root / "tests").as_posix()
    try:
        return AREA_BY_FILE[filename]
    except KeyError:
        raise pytest.UsageError(
            f"Unmapped test file: {filename}; add it to tests/classification.py AREA_FILES"
        ) from None


def selected_areas(value: str) -> set[str]:
    areas = {area.strip() for area in value.split(",") if area.strip()}
    unknown = areas - AREA_FILES.keys()
    if unknown:
        raise pytest.UsageError(
            f"Unknown --area: {', '.join(sorted(unknown))}; "
            f"choose from {', '.join(AREA_FILES)}"
        )
    return areas


def classify(item, root: Path) -> str:
    inferred_area = area_for(item.path, root)  # Explicit markers still require file ownership.
    levels = [mark.name for mark in item.iter_markers() if mark.name in LEVELS]
    areas = [mark.name for mark in item.iter_markers() if mark.name.startswith("area_")]
    for kind, markers in (("level", levels), ("area", areas)):
        if len(markers) > 1:
            raise pytest.UsageError(f"{item.nodeid}: multiple {kind} markers: {', '.join(markers)}")
    integration_fixtures = INTEGRATION_FIXTURES.intersection(item.fixturenames)
    if levels == ["unit"] and integration_fixtures:
        raise pytest.UsageError(
            f"{item.nodeid}: unit marker conflicts with integration fixtures: "
            f"{', '.join(sorted(integration_fixtures))}"
        )
    if not levels:
        filename = item.path.relative_to(root / "tests").as_posix()
        level = LEVEL_BY_FILE.get(filename)
        if level is None:
            level = "integration" if integration_fixtures else "unit"
        item.add_marker(level)
    if areas:
        area = areas[0].removeprefix("area_").replace("_", "-")
        if area not in AREA_FILES:
            raise pytest.UsageError(f"{item.nodeid}: unknown area marker: {areas[0]}")
    else:
        area = inferred_area
        item.add_marker(f"area_{area.replace('-', '_')}")
    return area
