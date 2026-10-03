export interface paths {
    "/auto-import/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Auto Import Status
         * @description Report only configured-root watcher state; it never scans arbitrary paths.
         */
        get: operations["get_auto_import_status_auto_import_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/comparisons": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Comparison */
        post: operations["create_comparison_comparisons_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/comparisons/{comparison_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Comparison */
        get: operations["get_comparison_comparisons__comparison_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Comparison
         * @description Delete a comparison and its diff, which unblocks deleting what it compared (#945).
         */
        delete: operations["delete_comparison_comparisons__comparison_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/comparisons/{comparison_id}/diff": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Diff */
        get: operations["get_diff_comparisons__comparison_id__diff_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/comparisons/{comparison_id}/diff.geojson": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Diff Geojson */
        get: operations["get_diff_geojson_comparisons__comparison_id__diff_geojson_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/comparisons/{comparison_id}/metrics": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Comparison Metrics */
        get: operations["get_comparison_metrics_comparisons__comparison_id__metrics_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/coverage/{run_id}/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Export Coverage Run */
        get: operations["export_coverage_run_coverage__run_id__export_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/coverage/results": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Coverage Results */
        get: operations["get_coverage_results_coverage_results_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/coverage/results/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Export Latest Coverage Results */
        get: operations["export_latest_coverage_results_coverage_results_export_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/coverage/run": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Run Coverage Analysis */
        post: operations["run_coverage_analysis_coverage_run_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/export/reconstructions/{reconstruction_id}/cesium-ion": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Upload Reconstruction To Cesium Ion
         * @description Publish the existing Cesium-ready 3D Tiles share bundle to Cesium ion.
         */
        post: operations["upload_reconstruction_to_cesium_ion_export_reconstructions__reconstruction_id__cesium_ion_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/export/reconstructions/{reconstruction_id}/elevation": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Export Elevation
         * @description Create a DSM or ground-classified DEM GeoTIFF from a cached LAS point cloud.
         */
        post: operations["export_elevation_export_reconstructions__reconstruction_id__elevation_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/export/reconstructions/{reconstruction_id}/geopackage": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export Geopackage
         * @description Download mapped session products as a target-CRS, multi-layer GeoPackage.
         *
         *     A layer is written only when its persisted source geometry is available. DSM
         *     and DEM files are recorded as external references, never embedded or created.
         */
        get: operations["export_geopackage_export_reconstructions__reconstruction_id__geopackage_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/export/reconstructions/{reconstruction_id}/gis-project-files": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Export Gis Project Files
         * @description Create QGIS and ArcGIS Pro references for the current mapped-products GeoPackage.
         */
        post: operations["export_gis_project_files_export_reconstructions__reconstruction_id__gis_project_files_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/export/reconstructions/{reconstruction_id}/measurements.csv": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export Measurements Csv
         * @description Export a reconstruction's persisted measurements as a flat CSV, one row per measurement.
         */
        get: operations["export_measurements_csv_export_reconstructions__reconstruction_id__measurements_csv_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/export/reconstructions/{reconstruction_id}/measurements.geojson": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export Measurements Geojson
         * @description Export a reconstruction's persisted measurements as a GeoJSON FeatureCollection.
         */
        get: operations["export_measurements_geojson_export_reconstructions__reconstruction_id__measurements_geojson_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/export/reconstructions/{reconstruction_id}/orthomosaic": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Export Orthomosaic
         * @description Start an orthomosaic GeoTIFF export for a completed reconstruction.
         *
         *     The export runs asynchronously. Poll ``/reconstruction/{id}/ortho/status`` for progress.
         *     Returns 202 with the updated reconstruction object (including ``ortho_status``).
         */
        post: operations["export_orthomosaic_export_reconstructions__reconstruction_id__orthomosaic_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/export/reconstructions/{reconstruction_id}/share-bundle": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Export Reconstruction Share Bundle
         * @description Create a static share bundle for a completed reconstruction.
         */
        post: operations["export_reconstruction_share_bundle_export_reconstructions__reconstruction_id__share_bundle_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/export/reconstructions/{reconstruction_id}/share-link": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Share Link
         * @description Create a persisted opaque share link; its bearer token is returned only once.
         */
        post: operations["create_share_link_export_reconstructions__reconstruction_id__share_link_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/export/reconstructions/{reconstruction_id}/share-links": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Share Links
         * @description List owner-visible share-link lifecycle state without secrets.
         */
        get: operations["list_share_links_export_reconstructions__reconstruction_id__share_links_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/export/reconstructions/{reconstruction_id}/share-links/{share_link_id}/revoke": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Revoke Share Link
         * @description Revoke a persisted link and every unlock session attached to it.
         */
        post: operations["revoke_share_link_export_reconstructions__reconstruction_id__share_links__share_link_id__revoke_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/export/reconstructions/{reconstruction_id}/slope": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Slope Overlay
         * @description Return a cached transparent PNG slope overlay for an existing DSM export.
         */
        get: operations["get_slope_overlay_export_reconstructions__reconstruction_id__slope_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/export/reconstructions/{reconstruction_id}/splat": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Export Compact Splat
         * @description Export a dependency-free, web-optimized compact ``.splat`` (antimatter15 format).
         *
         *     SH quantization: higher-order SH is dropped and the DC term becomes a flat
         *     RGBA byte per gaussian. See ``ply_io.write_splat`` for the exact layout.
         */
        post: operations["export_compact_splat_export_reconstructions__reconstruction_id__splat_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/export/reconstructions/{reconstruction_id}/usd": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export Usd Handoff
         * @description Download a self-contained USDA mesh and georeferencing handoff ZIP.
         */
        get: operations["export_usd_handoff_export_reconstructions__reconstruction_id__usd_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/export/reproducibility-manifest": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Export Reproducibility Manifest
         * @description Generate a reproducibility manifest for an import/reconstruction/export artifact.
         */
        post: operations["export_reproducibility_manifest_export_reproducibility_manifest_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/export/survey-report": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Export Survey Report
         * @description Generate a professional survey report for a session.
         *
         *     Returns structured JSON by default. Pass ``format=html`` for self-contained
         *     HTML, or ``format=pdf`` for a PDF when WeasyPrint is installed.
         *
         *     Building the report only reads the database, so GET serves it as well: the
         *     Export tab opens it with a plain link and ``window.open`` (#952). POST is
         *     kept for existing API clients.
         */
        get: operations["export_survey_report_export_survey_report_get"];
        put?: never;
        /**
         * Export Survey Report
         * @description Generate a professional survey report for a session.
         *
         *     Returns structured JSON by default. Pass ``format=html`` for self-contained
         *     HTML, or ``format=pdf`` for a PDF when WeasyPrint is installed.
         *
         *     Building the report only reads the database, so GET serves it as well: the
         *     Export tab opens it with a plain link and ``window.open`` (#952). POST is
         *     kept for existing API clients.
         */
        post: operations["export_survey_report_export_survey_report_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/export/webodm-georeferencing-csv": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Export Webodm Georeferencing Csv
         * @description Build a WebODM/OpenDroneMap georeferencing CSV-only zip.
         *
         *     The archive intentionally contains only ``odm_georeferencing.csv`` for
         *     workflows that need the ODM georeferencing sidecar, not a full image bundle.
         */
        post: operations["export_webodm_georeferencing_csv_export_webodm_georeferencing_csv_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/export/webodm-georeferencing-csv/download": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Download Webodm Georeferencing Csv
         * @description Download the zip that ``POST /export/webodm-georeferencing-csv`` last built.
         *
         *     Read-only: it never builds the archive, so the POST stays its only writer. The
         *     client gets its own snapshot, so a rebuild can replace the durable file mid-download.
         */
        get: operations["download_webodm_georeferencing_csv_export_webodm_georeferencing_csv_download_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/export/webodm-package": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Export Webodm Package
         * @description Build a complete WebODM/OpenDroneMap package with images and options manifest.
         */
        post: operations["export_webodm_package_export_webodm_package_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/flight-logs/apply": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Apply Sync */
        post: operations["apply_sync_flight_logs_apply_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/flight-logs/match-preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Match Preview */
        get: operations["match_preview_flight_logs_match_preview_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/flight-logs/offset-preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Offset Preview */
        get: operations["offset_preview_flight_logs_offset_preview_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/flight-logs/upload": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Upload Flight Log
         * @description Store a flight log's GPS track for timestamp sync.
         *
         *     ``start_time`` (ISO 8601, UTC when no offset is given) anchors a log whose
         *     clock counts from the start of the flight and that does not record when the
         *     flight started. It is not used for logs that already carry absolute times.
         */
        post: operations["upload_flight_log_flight_logs_upload_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/footprints": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Footprints */
        get: operations["list_footprints_footprints_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/footprints/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Export Footprints */
        get: operations["export_footprints_footprints_export_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/georeferencing/control-points/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Export Control Points
         * @description Render a no-header Pix4D or DroneDeploy WGS84 control-point CSV.
         */
        post: operations["export_control_points_georeferencing_control_points_export_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/georeferencing/control-points/import": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Import Control Points
         * @description Parse the documented no-header Pix4D or DroneDeploy WGS84 CSV format.
         */
        post: operations["import_control_points_georeferencing_control_points_import_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/georeferencing/gcp-list": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Build Gcp List */
        post: operations["build_gcp_list_georeferencing_gcp_list_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/georeferencing/sessions/{session_id}/accuracy-report": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Gcp Accuracy Report
         * @description Compute RMSE of surveyed GCPs against the latest completed reconstruction.
         *
         *     Survey points must be provided in the reconstruction's local coordinate
         *     system (UTM-aligned).  The geo-transform from the latest completed
         *     reconstruction is used for metadata.
         */
        post: operations["gcp_accuracy_report_georeferencing_sessions__session_id__accuracy_report_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/georeferencing/sessions/{session_id}/precision": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Precision Workflow */
        get: operations["get_precision_workflow_georeferencing_sessions__session_id__precision_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health */
        get: operations["health_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/images": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Images */
        get: operations["list_images_images_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/images/{image_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch Image */
        patch: operations["patch_image_images__image_id__patch"];
        trace?: never;
    };
    "/images/{image_id}/thumb": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Thumb
         * @description Redirect to the web-accessible thumbnail for an image.
         *
         *     The frontend resolves every thumbnail through this endpoint so a single
         *     policy handles relative processed/ paths, absolute under-processed
         *     paths, and absolute app-data paths on macOS (#857); clients must never
         *     reconstruct thumbnail URLs from raw ``thumb_path`` values.
         */
        get: operations["get_thumb_images__image_id__thumb_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/images/bulk": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Bulk Patch Images
         * @description Apply a flag and/or usable change to many images in one request.
         *
         *     Defined before ``/{image_id}`` so the literal ``bulk`` path is not parsed as
         *     an id. Returns the number of rows updated.
         */
        patch: operations["bulk_patch_images_images_bulk_patch"];
        trace?: never;
    };
    "/jobs/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Jobs */
        get: operations["list_jobs_jobs__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/jobs/queue": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Queue Entries
         * @description List persistent job queue entries (survives API restarts).
         */
        get: operations["list_queue_entries_jobs_queue_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/jobs/queue/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Queue Entry
         * @description Get a single job queue entry by id.
         */
        get: operations["get_queue_entry_jobs_queue__job_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/jobs/queue/{job_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Cancel Queue Entry
         * @description Cancel a pending or running job queue entry.
         */
        post: operations["cancel_queue_entry_jobs_queue__job_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/pin-lock/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Pin Lock Status
         * @description Expose only whether the local lock is enabled, never its configuration or hash.
         */
        get: operations["pin_lock_status_pin_lock_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/pin-lock/unlock": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Unlock Pin Lock
         * @description Verify the configured scrypt PIN and issue a short-lived HttpOnly cookie.
         */
        post: operations["unlock_pin_lock_pin_lock_unlock_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/plans/{plan_id}/gpx": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download Gpx */
        get: operations["download_gpx_plans__plan_id__gpx_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/plans/{plan_id}/kml": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download Kml */
        get: operations["download_kml_plans__plan_id__kml_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/plans/{plan_id}/segments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Plan Segments */
        get: operations["get_plan_segments_plans__plan_id__segments_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/plans/{plan_id}/segments/{segment_index}/gpx": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download Segment Gpx */
        get: operations["download_segment_gpx_plans__plan_id__segments__segment_index__gpx_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/plans/{plan_id}/segments/{segment_index}/kml": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download Segment Kml */
        get: operations["download_segment_kml_plans__plan_id__segments__segment_index__kml_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/plans/{plan_id}/validate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Validate Mission Plan */
        post: operations["validate_mission_plan_plans__plan_id__validate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/plans/generate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Generate Plan */
        post: operations["generate_plan_plans_generate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/plans/generate-from-gaps": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Generate Plan From Gaps */
        post: operations["generate_plan_from_gaps_plans_generate_from_gaps_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/projects/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Projects */
        get: operations["list_projects_projects__get"];
        put?: never;
        /** Create Project */
        post: operations["create_project_projects__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/projects/{project_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Project */
        get: operations["get_project_projects__project_id__get"];
        put?: never;
        post?: never;
        /** Delete Project */
        delete: operations["delete_project_projects__project_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/projects/{project_id}/sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Project Sessions */
        get: operations["list_project_sessions_projects__project_id__sessions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/projects/{project_id}/sessions/import": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Project Session */
        post: operations["create_project_session_projects__project_id__sessions_import_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/projects/{project_id}/trends": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Project Trends
         * @description Return a time-ordered, read-only trend projection for one project.
         *
         *     The projection deliberately reads only session, coverage-run, and completed
         *     reconstruction rows. It does not create a snapshot or run any quality work.
         */
        get: operations["get_project_trends_projects__project_id__trends_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Reconstruction */
        delete: operations["delete_reconstruction_reconstruction__reconstruction_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/annotations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Annotations */
        get: operations["list_annotations_reconstruction__reconstruction_id__annotations_get"];
        put?: never;
        /** Create Annotation */
        post: operations["create_annotation_reconstruction__reconstruction_id__annotations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/annotations.geojson": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Export Annotations Geojson */
        get: operations["export_annotations_geojson_reconstruction__reconstruction_id__annotations_geojson_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/annotations/{annotation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Annotation */
        delete: operations["delete_annotation_reconstruction__reconstruction_id__annotations__annotation_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/calibration-drift-report": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Calibration Drift Report
         * @description Return a bounded consistency report from COLMAP's completed sparse model.
         */
        get: operations["get_calibration_drift_report_reconstruction__reconstruction_id__calibration_drift_report_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Request Cancel */
        post: operations["request_cancel_reconstruction__reconstruction_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/cleanup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cleanup Splat */
        post: operations["cleanup_splat_reconstruction__reconstruction_id__cleanup_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/coverage-gaps": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Coverage Gaps */
        get: operations["get_coverage_gaps_reconstruction__reconstruction_id__coverage_gaps_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/dense-rerun": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Start Dense Rerun
         * @description Queue a denser child reconstruction only after an explicit confirmation.
         */
        post: operations["start_dense_rerun_reconstruction__reconstruction_id__dense_rerun_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/dense-rerun-plan": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Dense Rerun Plan
         * @description Preview the explicit child rerun; this endpoint never starts work.
         */
        get: operations["get_dense_rerun_plan_reconstruction__reconstruction_id__dense_rerun_plan_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/diagnostics": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Diagnostics */
        get: operations["get_diagnostics_reconstruction__reconstruction_id__diagnostics_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/download-bundle": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download Reconstruction Bundle */
        get: operations["download_reconstruction_bundle_reconstruction__reconstruction_id__download_bundle_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/flythrough": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download Flythrough */
        get: operations["download_flythrough_reconstruction__reconstruction_id__flythrough_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/flythrough/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Flythrough Status */
        get: operations["get_flythrough_status_reconstruction__reconstruction_id__flythrough_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/geo-transform": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Geo Transform */
        get: operations["get_geo_transform_reconstruction__reconstruction_id__geo_transform_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/lineage": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Lineage */
        get: operations["get_lineage_reconstruction__reconstruction_id__lineage_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/log": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Log */
        get: operations["get_log_reconstruction__reconstruction_id__log_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/measurements": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Measurements */
        get: operations["list_measurements_reconstruction__reconstruction_id__measurements_get"];
        put?: never;
        /** Create Measurement */
        post: operations["create_measurement_reconstruction__reconstruction_id__measurements_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/measurements/{measurement_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Measurement */
        delete: operations["delete_measurement_reconstruction__reconstruction_id__measurements__measurement_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/mesh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download Mesh */
        get: operations["download_mesh_reconstruction__reconstruction_id__mesh_get"];
        put?: never;
        /** Generate Mesh */
        post: operations["generate_mesh_reconstruction__reconstruction_id__mesh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/mesh/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Mesh Status */
        get: operations["get_mesh_status_reconstruction__reconstruction_id__mesh_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/ortho": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download Ortho */
        get: operations["download_ortho_reconstruction__reconstruction_id__ortho_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/ortho/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Ortho Status */
        get: operations["get_ortho_status_reconstruction__reconstruction_id__ortho_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/pointcloud": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download Pointcloud */
        get: operations["download_pointcloud_reconstruction__reconstruction_id__pointcloud_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/potree": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Generate Potree Export
         * @description Convert an already-generated LAS/LAZ point cloud for Potree hosting.
         */
        post: operations["generate_potree_export_reconstruction__reconstruction_id__potree_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/quality-scorecard": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Quality Scorecard */
        get: operations["get_quality_scorecard_reconstruction__reconstruction_id__quality_scorecard_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/render-video": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Render Video */
        post: operations["render_video_reconstruction__reconstruction_id__render_video_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/semantic-labels": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Semantic Labels Summary */
        get: operations["get_semantic_labels_summary_reconstruction__reconstruction_id__semantic_labels_get"];
        put?: never;
        /** Generate Semantic Labels */
        post: operations["generate_semantic_labels_reconstruction__reconstruction_id__semantic_labels_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/semantic-labels/overlay": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Semantic Overlay */
        get: operations["get_semantic_overlay_reconstruction__reconstruction_id__semantic_labels_overlay_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/semantic-labels/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Semantic Status */
        get: operations["get_semantic_status_reconstruction__reconstruction_id__semantic_labels_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/splat": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download Splat */
        get: operations["download_splat_reconstruction__reconstruction_id__splat_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/splat-transform-cleanup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Splat Transform Cleanup */
        post: operations["splat_transform_cleanup_reconstruction__reconstruction_id__splat_transform_cleanup_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/splat-transform-compress": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Splat Transform Compress */
        post: operations["splat_transform_compress_reconstruction__reconstruction_id__splat_transform_compress_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Status */
        get: operations["get_status_reconstruction__reconstruction_id__status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/status/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Stream Status Events */
        get: operations["stream_status_events_reconstruction__reconstruction_id__status_events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/{reconstruction_id}/validate-checkpoints": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Validate Checkpoints */
        post: operations["validate_checkpoints_reconstruction__reconstruction_id__validate_checkpoints_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/backends": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Backends
         * @description List selectable reconstruction backends without exposing credentials.
         */
        get: operations["list_backends_reconstruction_backends_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/frame-selection": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Set Frame Selection */
        post: operations["set_frame_selection_reconstruction_frame_selection_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/frame-selection/{session_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Frame Selection */
        get: operations["get_frame_selection_reconstruction_frame_selection__session_id__get"];
        put?: never;
        post?: never;
        /** Clear Frame Selection */
        delete: operations["clear_frame_selection_reconstruction_frame_selection__session_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/preflight/{session_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Preflight Report */
        get: operations["get_preflight_report_reconstruction_preflight__session_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/splat-transform-available": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Splat Transform Status */
        get: operations["splat_transform_status_reconstruction_splat_transform_available_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reconstruction/start": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start */
        post: operations["start_reconstruction_start_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/session-log": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Session Log */
        get: operations["list_session_log_session_log_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/sessions/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Sessions */
        get: operations["list_sessions_sessions__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/sessions/{session_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Session */
        get: operations["get_session_sessions__session_id__get"];
        put?: never;
        post?: never;
        /** Delete Session */
        delete: operations["delete_session_sessions__session_id__delete"];
        options?: never;
        head?: never;
        /**
         * Patch Session
         * @description Update field-organization metadata (tags, operator notes) on a session.
         */
        patch: operations["patch_session_sessions__session_id__patch"];
        trace?: never;
    };
    "/sessions/{session_id}/archive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Archive Session
         * @description Export a session as a portable .zip: its row, every cascaded child row, and
         *     any artifact files that exist on disk. Restore it elsewhere with POST /sessions/restore.
         */
        post: operations["archive_session_sessions__session_id__archive_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/sessions/{session_id}/defects": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Defects */
        get: operations["list_defects_sessions__session_id__defects_get"];
        put?: never;
        /** Create Defect */
        post: operations["create_defect_sessions__session_id__defects_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/sessions/{session_id}/defects/{defect_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Defect */
        get: operations["get_defect_sessions__session_id__defects__defect_id__get"];
        put?: never;
        post?: never;
        /** Delete Defect */
        delete: operations["delete_defect_sessions__session_id__defects__defect_id__delete"];
        options?: never;
        head?: never;
        /** Patch Defect */
        patch: operations["patch_defect_sessions__session_id__defects__defect_id__patch"];
        trace?: never;
    };
    "/sessions/{session_id}/flight-entries": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Flight Entries */
        get: operations["list_flight_entries_sessions__session_id__flight_entries_get"];
        put?: never;
        /** Create Flight Entry */
        post: operations["create_flight_entry_sessions__session_id__flight_entries_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/sessions/{session_id}/flight-entries/{entry_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Flight Entry */
        delete: operations["delete_flight_entry_sessions__session_id__flight_entries__entry_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/sessions/{session_id}/progress": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Session Progress */
        get: operations["session_progress_sessions__session_id__progress_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/sessions/{session_id}/quick-report": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Quick Report */
        get: operations["get_quick_report_sessions__session_id__quick_report_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/sessions/bulk": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Bulk Sessions
         * @description Apply a single organization/archive/delete operation per selected session.
         *
         *     Each session is committed independently. One stale ID or filesystem failure
         *     therefore reports an outcome without rolling back successful peers.
         */
        post: operations["bulk_sessions_sessions_bulk_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/sessions/import": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Import Session */
        post: operations["import_session_sessions_import_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/sessions/restore": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Restore Session
         * @description Restore a session archive (from POST /sessions/{id}/archive) as a brand-new
         *     session with fresh IDs. Never modifies or clobbers an existing session.
         */
        post: operations["restore_session_sessions_restore_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/sessions/search": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Search Sessions
         * @description Search session metadata, timeline messages, and defects with SQLite FTS5.
         */
        get: operations["search_sessions_sessions_search_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/settings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Settings
         * @description Return the current configuration.
         */
        get: operations["get_settings_settings_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Patch Settings
         * @description Deep-merge the partial body into config.yaml and return the full config.
         */
        patch: operations["patch_settings_settings_patch"];
        trace?: never;
    };
    "/settings/reset": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Reset Settings
         * @description Restore the settings this API manages to their defaults, and return the full config.
         *
         *     Only the sections exposed by this router are reset. Security- and deployment-critical
         *     sections it never surfaces — ``deployment``, ``pin_lock``, ``api_key``, ``logging``,
         *     ``webodm``, ``remote_worker``, ``auto_import``, ``backup`` — are preserved verbatim.
         *     Resetting them here would silently disable the PIN lock on the next restart.
         */
        post: operations["reset_settings_settings_reset_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/share/{reconstruction_id}/mesh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Public Mesh
         * @description Download a mesh using a new cookie session or legacy signed token.
         */
        get: operations["public_mesh_share__reconstruction_id__mesh_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/share/{reconstruction_id}/pointcloud": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Public Pointcloud
         * @description Download a point cloud using a new cookie session or legacy signed token.
         */
        get: operations["public_pointcloud_share__reconstruction_id__pointcloud_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/share/{reconstruction_id}/splat": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Public Splat
         * @description Download a splat using a new cookie session or legacy signed token.
         */
        get: operations["public_splat_share__reconstruction_id__splat_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/share/token/{token}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Public Viewer Metadata
         * @description Return read-only reconstruction metadata after required link access checks.
         *
         *     A password-protected link without an unlock session is a 401 whose body carries
         *     ``code: "share_password_required"`` for the viewer to branch on.
         */
        get: operations["public_viewer_metadata_share_token__token__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/share/token/{token}/unlock": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Unlock Share Link
         * @description Verify a link password and issue a scoped HttpOnly unlock session.
         */
        post: operations["unlock_share_link_share_token__token__unlock_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/srt/process": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Process Srt */
        post: operations["process_srt_srt_process_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/storage/apply-policy": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Apply Storage Policy
         * @description Preview or execute storage lifecycle rules.
         *
         *     **Dry-run** (default, ``execute=false``): returns a side-effect-free
         *     listing of every candidate file/directory with ``path``, ``bytes``,
         *     ``reason``, and ``action``.
         *
         *     **Execute** (``execute=true``): performs the actions. Only paths inside
         *     the configured storage roots (imports_dir, processed_dir, exports_dir,
         *     data_dir) are ever touched. Prefers delete for COLMAP intermediates,
         *     archive for raw frames and reconstruction artifacts when age-based.
         */
        post: operations["apply_storage_policy_storage_apply_policy_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/storage/backup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Artifact Backup
         * @description Create a versioned, additive snapshot at a configured backup destination.
         */
        post: operations["create_artifact_backup_storage_backup_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/storage/backup-schedule": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Backup Schedule Status
         * @description Return the safe operational state of the configured daily backup.
         */
        get: operations["get_backup_schedule_status_storage_backup_schedule_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/storage/file": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete File */
        delete: operations["delete_file_storage_file_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/storage/files": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Files */
        get: operations["list_files_storage_files_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/storage/summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Storage Summary */
        get: operations["get_storage_summary_storage_summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/system/resources": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Resources */
        get: operations["get_resources_system_resources_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/target-areas/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Target Areas */
        get: operations["list_target_areas_target_areas__get"];
        put?: never;
        /** Create Target Area */
        post: operations["create_target_area_target_areas__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/target-areas/{area_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Target Area */
        delete: operations["delete_target_area_target_areas__area_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/tiles/{reconstruction_id}/wms": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Wms
         * @description Minimal WMS 1.3.0 discovery and GetMap interface for one orthomosaic.
         */
        get: operations["wms_tiles__reconstruction_id__wms_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/tiles/{reconstruction_id}/wmts/{z}/{x}/{y}.png": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Wmts Tile
         * @description Serve one Web Mercator XYZ tile from the completed orthomosaic.
         */
        get: operations["wmts_tile_tiles__reconstruction_id__wmts__z___x___y__png_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/uploads/imports/{upload_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Browser Import Upload */
        get: operations["get_browser_import_upload_uploads_imports__upload_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/uploads/imports/{upload_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Browser Import Upload */
        post: operations["cancel_browser_import_upload_uploads_imports__upload_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/uploads/imports/{upload_id}/chunk": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Upload Import Chunk */
        post: operations["upload_import_chunk_uploads_imports__upload_id__chunk_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/uploads/imports/{upload_id}/complete": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Complete Browser Import Upload */
        post: operations["complete_browser_import_upload_uploads_imports__upload_id__complete_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/uploads/imports/check-duplicate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Check Duplicate Import
         * @description Advisory-only: flags likely-duplicate sessions, never blocks the import.
         */
        post: operations["check_duplicate_import_uploads_imports_check_duplicate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/uploads/imports/start": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start Browser Import Upload */
        post: operations["start_browser_import_upload_uploads_imports_start_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/webodm/projects/{project_id}/tasks/{task_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Task Status */
        get: operations["task_status_webodm_projects__project_id__tasks__task_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/webodm/projects/{project_id}/tasks/{task_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Webodm Task */
        post: operations["cancel_webodm_task_webodm_projects__project_id__tasks__task_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/webodm/projects/{project_id}/tasks/{task_id}/results": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Pull Task Results */
        post: operations["pull_task_results_webodm_projects__project_id__tasks__task_id__results_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/webodm/sessions/{session_id}/tasks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Submit Session Task */
        post: operations["submit_session_task_webodm_sessions__session_id__tasks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AnnotationIn */
        AnnotationIn: {
            /** Alt M */
            alt_m: number;
            /**
             * Color
             * @default #ff6b35
             */
            color?: string;
            /** Label */
            label: string;
            /** Lat */
            lat: number;
            /** Lon */
            lon: number;
        };
        /** AnnotationOut */
        AnnotationOut: {
            /** Alt M */
            alt_m: number;
            /** Color */
            color: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: number;
            /** Label */
            label: string;
            /** Lat */
            lat: number;
            /** Lon */
            lon: number;
            /** Reconstruction Id */
            reconstruction_id: number;
        };
        /** ApplyPolicyRequest */
        ApplyPolicyRequest: {
            /**
             * Execute
             * @default false
             */
            execute?: boolean;
            /** Rules */
            rules: components["schemas"]["PolicyRuleInput"][];
        };
        /** AppSettings */
        AppSettings: {
            general: components["schemas"]["GeneralSettingsRead"];
            ingest: components["schemas"]["IngestSettingsRead"];
            mission: components["schemas"]["MissionSettingsRead"];
            reconstruction: components["schemas"]["ReconstructionSettingsRead"];
            render: components["schemas"]["RenderSettingsRead"];
        };
        /** BackupRequest */
        BackupRequest: {
            /** Artifacts */
            artifacts?: ("imports" | "processed" | "exports")[];
            /**
             * Destination
             * @enum {string}
             */
            destination: "local" | "rclone";
            /** Local Destination */
            local_destination?: string | null;
        };
        /** BackupScheduleStatus */
        BackupScheduleStatus: {
            /** Daily At */
            daily_at: string | null;
            /** Enabled */
            enabled: boolean;
            /** Last Run */
            last_run: string | null;
            /** Next Run */
            next_run: string | null;
            result: components["schemas"]["BackupScheduleStatusResult"] | null;
            /** Running */
            running: boolean;
            /** Target */
            target: string | null;
        };
        /** BackupScheduleStatusResult */
        BackupScheduleStatusResult: {
            /** Destination */
            destination?: string;
            /** File Count */
            file_count?: number;
            /** Manifest Sha256 */
            manifest_sha256?: string;
            /** Snapshot Id */
            snapshot_id?: string;
            /**
             * Status
             * @enum {string}
             */
            status: "success" | "failed" | "configuration_error";
        };
        /** Body_process_srt_srt_process_post */
        Body_process_srt_srt_process_post: {
            /** File */
            file: string;
        };
        /** Body_upload_flight_log_flight_logs_upload_post */
        Body_upload_flight_log_flight_logs_upload_post: {
            /** File */
            file: string;
            /** Session Id */
            session_id: number;
            /** Start Time */
            start_time?: string | null;
        };
        /** Body_upload_import_chunk_uploads_imports__upload_id__chunk_post */
        Body_upload_import_chunk_uploads_imports__upload_id__chunk_post: {
            /** Chunk */
            chunk: string;
            /** Offset */
            offset: number;
            /** Path */
            path: string;
        };
        /** BulkSessionOutcome */
        BulkSessionOutcome: {
            /** Bundle Path */
            bundle_path?: string | null;
            /** Error */
            error?: string | null;
            /** Ok */
            ok: boolean;
            /** Session Id */
            session_id: number;
        };
        /**
         * BulkSessionRequest
         * @description Apply one small, explicit operation to several sessions.
         *
         *     Missing session rows are reported per ID so a stale picker selection cannot
         *     hide work completed for the other selected sessions.
         */
        BulkSessionRequest: {
            /** Confirm */
            confirm?: string | null;
            /**
             * Operation
             * @enum {string}
             */
            operation: "archive" | "assign_project" | "replace_tags" | "add_tags" | "delete";
            /** Project Id */
            project_id?: number | null;
            /** Session Ids */
            session_ids: number[];
            /** Tags */
            tags?: string[] | null;
        };
        /** BulkSessionResponse */
        BulkSessionResponse: {
            /**
             * Operation
             * @enum {string}
             */
            operation: "archive" | "assign_project" | "replace_tags" | "add_tags" | "delete";
            /** Outcomes */
            outcomes: components["schemas"]["BulkSessionOutcome"][];
        };
        /** CheckpointResult */
        CheckpointResult: {
            /** Distance M */
            distance_m: number;
            /** Label */
            label: string;
            /** Nearest Surface Point */
            nearest_surface_point: string;
        };
        /** CheckpointValidationIn */
        CheckpointValidationIn: {
            /** Points */
            points: components["schemas"]["SurveyedPointIn"][];
        };
        /** CheckpointValidationReport */
        CheckpointValidationReport: {
            /**
             * Available
             * @constant
             */
            available: true;
            /** Checkpoints */
            checkpoints: components["schemas"]["CheckpointResult"][];
            /** Frame */
            frame: {
                [key: string]: string;
            };
            /** Point Count */
            point_count: number;
            /**
             * Source
             * @enum {string}
             */
            source: "mesh" | "splat" | "pointcloud";
            summary: components["schemas"]["CheckpointValidationReportSummary"];
            /** Surface Point Count */
            surface_point_count: number;
        };
        /** CheckpointValidationReportSummary */
        CheckpointValidationReportSummary: {
            /** Max M */
            max_m: number | null;
            /** Mean M */
            mean_m: number | null;
            /** Min M */
            min_m: number | null;
            /** Rmse M */
            rmse_m: number | null;
        };
        /** CleanupIn */
        CleanupIn: {
            /** Opacity Keep Ratio */
            opacity_keep_ratio?: number | null;
            /** Outlier K */
            outlier_k?: number | null;
            /** Outlier Std Threshold */
            outlier_std_threshold?: number | null;
            /** Scale Std Threshold */
            scale_std_threshold?: number | null;
            /** Target Area Id */
            target_area_id?: number | null;
        };
        /** CleanupOut */
        CleanupOut: {
            /** Cleaned Path */
            cleaned_path: string;
            /** N After */
            n_after: number;
            /** N Before */
            n_before: number;
            /** Stats */
            stats: {
                [key: string]: unknown;
            };
        };
        /** ComparisonCell */
        ComparisonCell: {
            /** Size */
            size: number;
            /**
             * Type
             * @enum {string}
             */
            type: "new" | "removed";
            /** X */
            x: number;
            /** Y */
            y: number;
            /** Z */
            z: number;
        };
        /** ComparisonDiff */
        ComparisonDiff: {
            comparison: components["schemas"]["ComparisonDiffComparison"];
            /** New */
            new: components["schemas"]["ComparisonCell"][];
            /** Removed */
            removed: components["schemas"]["ComparisonCell"][];
            summary: components["schemas"]["ComparisonDiffSummary"];
            /** Utm Zone */
            utm_zone: string | null;
            /** Voxel Size M */
            voxel_size_m: number;
        };
        /** ComparisonDiffComparison */
        ComparisonDiffComparison: {
            /** Reconstruction A Id */
            reconstruction_a_id: number;
            /** Reconstruction B Id */
            reconstruction_b_id: number;
            /** Session A Id */
            session_a_id: number;
            /** Session B Id */
            session_b_id: number;
        };
        /** ComparisonDiffSummary */
        ComparisonDiffSummary: {
            /** A Cells */
            a_cells: number;
            /** B Cells */
            b_cells: number;
            /** New Count */
            new_count: number;
            /** Removed Count */
            removed_count: number;
        };
        /** ComparisonIn */
        ComparisonIn: {
            /** Reconstruction A Id */
            reconstruction_a_id: number;
            /** Reconstruction B Id */
            reconstruction_b_id: number;
            /** Session A Id */
            session_a_id: number;
            /** Session B Id */
            session_b_id: number;
            /**
             * Voxel Size M
             * @default 0.5
             */
            voxel_size_m?: number;
        };
        /** ComparisonOut */
        ComparisonOut: {
            /** Completed At */
            completed_at?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Diff Path */
            diff_path?: string | null;
            /** Error Msg */
            error_msg?: string | null;
            /** Id */
            id: number;
            /** Reconstruction A Id */
            reconstruction_a_id: number;
            /** Reconstruction B Id */
            reconstruction_b_id: number;
            /** Session A Id */
            session_a_id: number;
            /** Session B Id */
            session_b_id: number;
            /** Status */
            status: string;
        };
        /**
         * CompleteUploadContract
         * @description Document the existing six-field session projection without filtering it.
         */
        CompleteUploadContract: {
            /** Error */
            error?: string | null;
            /** File Count */
            file_count: number;
            session?: components["schemas"]["SessionOut"] | null;
            /** Session Id */
            session_id?: number | null;
            /** Status */
            status: string;
            /** Total Bytes */
            total_bytes: number;
            /** Upload Id */
            upload_id: string;
            /** Uploaded Bytes */
            uploaded_bytes: number;
        };
        /** CompleteUploadResponse */
        CompleteUploadResponse: {
            /** Error */
            error?: string | null;
            /** File Count */
            file_count: number;
            /** Session */
            session?: {
                [key: string]: unknown;
            } | null;
            /** Session Id */
            session_id?: number | null;
            /** Status */
            status: string;
            /** Total Bytes */
            total_bytes: number;
            /** Upload Id */
            upload_id: string;
            /** Uploaded Bytes */
            uploaded_bytes: number;
        };
        /** ControlPointCsvIn */
        ControlPointCsvIn: {
            /** Contents */
            contents: string;
            /** Format */
            format: string;
        };
        /** ControlPointExportIn */
        ControlPointExportIn: {
            /** Format */
            format: string;
            /** Points */
            points: components["schemas"]["ControlPointIn"][];
        };
        /** ControlPointIn */
        ControlPointIn: {
            /** Altitude M */
            altitude_m: number;
            /** Label */
            label: string;
            /** Latitude */
            latitude: number;
            /** Longitude */
            longitude: number;
        };
        /** CoverageGapCell */
        CoverageGapCell: {
            /**
             * Level
             * @enum {string}
             */
            level: "sparse" | "thin" | "very_sparse";
            /** Size */
            size: number;
            /** X */
            x: number;
            /** Y */
            y: number;
            /** Z */
            z: number;
        };
        /** CoverageRunOut */
        CoverageRunOut: {
            /** Coverage Pct */
            coverage_pct: number | null;
            /** Covered Area M2 */
            covered_area_m2: number | null;
            /** Gap Geojson */
            gap_geojson: string | null;
            /** Id */
            id: number;
            /** Overlap Geojson */
            overlap_geojson: string | null;
            /** Session Ids */
            session_ids: string | null;
            /** Target Area Id */
            target_area_id: number;
        };
        /** CreatedShareLink */
        CreatedShareLink: {
            /** Expires At */
            expires_at: string;
            /** Password Protected */
            password_protected: boolean;
            /** Reconstruction Id */
            reconstruction_id: number;
            /** Session Id */
            session_id: number;
            /** Share Link Id */
            share_link_id: number;
            /** Share Token */
            share_token: string;
        };
        /** CreateShareLinkRequest */
        CreateShareLinkRequest: {
            /**
             * Expires In S
             * @default 604800
             */
            expires_in_s?: number;
            /** Password */
            password?: string | null;
        };
        /** DefectImageOut */
        DefectImageOut: {
            /** Filename */
            filename: string;
            /** Id */
            id: number;
            /** Latitude */
            latitude: number | null;
            /** Longitude */
            longitude: number | null;
            /** Thumb Path */
            thumb_path: string | null;
        };
        /** DefectIn */
        DefectIn: {
            /**
             * Category
             * @enum {string}
             */
            category: "crack" | "corrosion" | "vegetation" | "water_damage" | "missing_material" | "other";
            /** Image Ids */
            image_ids: number[];
            /** Note */
            note?: string | null;
            /** Severity */
            severity?: ("low" | "medium" | "high") | null;
        };
        /** DefectOut */
        DefectOut: {
            /** Category */
            category: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: number;
            /** Image Ids */
            image_ids: number[];
            /** Images */
            images: components["schemas"]["DefectImageOut"][];
            /** Note */
            note: string | null;
            /** Session Id */
            session_id: number;
            /** Severity */
            severity: string | null;
        };
        /** DefectPatch */
        DefectPatch: {
            /** Category */
            category?: ("crack" | "corrosion" | "vegetation" | "water_damage" | "missing_material" | "other") | null;
            /** Image Ids */
            image_ids?: number[] | null;
            /** Note */
            note?: string | null;
            /** Severity */
            severity?: ("low" | "medium" | "high") | null;
        };
        /** DeleteOut */
        DeleteOut: {
            /** Ok */
            ok: boolean;
        };
        /**
         * DenseRerunIn
         * @description Explicit acknowledgement before a weak-area rerun is queued.
         */
        DenseRerunIn: {
            /**
             * Confirm
             * @default false
             */
            confirm?: boolean;
        };
        /** DuplicateCheckRequest */
        DuplicateCheckRequest: {
            /**
             * Filenames
             * @default []
             */
            filenames?: string[];
            /** Folder Path */
            folder_path?: string | null;
        };
        /** DuplicateCheckResponse */
        DuplicateCheckResponse: {
            /** Duplicate */
            duplicate: boolean;
            /** Matches */
            matches: components["schemas"]["DuplicateMatch"][];
        };
        /** DuplicateMatch */
        DuplicateMatch: {
            /** Name */
            name: string;
            /** Overlap */
            overlap: number;
            /** Reason */
            reason: string;
            /** Session Id */
            session_id: number;
        };
        /** EffectiveSplatSettings */
        EffectiveSplatSettings: {
            /**
             * Accelerator Kind
             * @enum {string}
             */
            accelerator_kind: "cuda" | "metal" | "cpu";
            /** Background Color */
            background_color?: [
                number,
                number,
                number
            ] | null;
            /** Benchmark Heldout Split */
            benchmark_heldout_split?: boolean;
            /** Benchmark Test Every */
            benchmark_test_every?: number;
            /**
             * Device
             * @enum {string}
             */
            device: "cuda" | "mps" | "cpu";
            /** Downscale Factor */
            downscale_factor?: number;
            /** Eval Every */
            eval_every?: number;
            /** Eval Views */
            eval_views?: number;
            /** Init Opacity */
            init_opacity?: number;
            /** Iterations */
            iterations: number;
            /** Max Gaussians */
            max_gaussians: number;
            /** Preset */
            preset: string;
            /** Refine Every */
            refine_every?: number;
            /** Refine Start Iter */
            refine_start_iter?: number;
            /** Refine Stop Iter */
            refine_stop_iter?: number;
            /** Reset Every */
            reset_every?: number;
            /** Sh Degree */
            sh_degree?: number;
            /** Sh Warmup Every */
            sh_warmup_every?: number;
            /** Splat Backend */
            splat_backend: ("cuda_gsplat" | "metal_msplat") | null;
            /** Ssim Lambda */
            ssim_lambda?: number;
        };
        /** FlightEntryIn */
        FlightEntryIn: {
            /** Battery Id */
            battery_id?: string | null;
            /** Duration S */
            duration_s?: number | null;
            /** End Pct */
            end_pct?: number | null;
            /** Notes */
            notes?: string | null;
            /** Start Pct */
            start_pct?: number | null;
        };
        /** FlightEntryOut */
        FlightEntryOut: {
            /** Battery Id */
            battery_id: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Duration S */
            duration_s: number | null;
            /** End Pct */
            end_pct: number | null;
            /** Id */
            id: number;
            /** Notes */
            notes: string | null;
            /** Session Id */
            session_id: number;
            /** Start Pct */
            start_pct: number | null;
        };
        /** FlythroughKeyframe */
        FlythroughKeyframe: {
            /**
             * Duration S
             * @default 3
             */
            duration_s?: number;
            /** Position */
            position: number[];
            /** Target */
            target?: number[];
        };
        /** FlythroughStatusOut */
        FlythroughStatusOut: {
            /** Flythrough Error */
            flythrough_error?: string | null;
            /** Flythrough Path */
            flythrough_path?: string | null;
            /** Flythrough Status */
            flythrough_status?: string | null;
            /** Id */
            id: number;
        };
        /** FootprintOut */
        FootprintOut: {
            /** Geom Geojson */
            geom_geojson: string | null;
            /** Geom Wkt */
            geom_wkt: string | null;
            /** Ground Height M */
            ground_height_m: number | null;
            /** Ground Width M */
            ground_width_m: number | null;
            /** Heading Estimated */
            heading_estimated: boolean;
            /** Id */
            id: number;
            /** Image Id */
            image_id: number;
        };
        /** FrameSelectionIn */
        FrameSelectionIn: {
            /** Image Ids */
            image_ids: number[];
            /** Session Id */
            session_id: number;
        };
        /** GcpAccuracyReport */
        GcpAccuracyReport: {
            geo_transform: components["schemas"]["GeoTransform"];
            /** Point Count */
            point_count: number;
            /** Residuals */
            residuals: components["schemas"]["GcpResidual"][];
            rmse: components["schemas"]["GcpAccuracyReportRmse"];
        };
        /** GcpAccuracyReportRmse */
        GcpAccuracyReportRmse: {
            /** 3D M */
            "3d_m": number | null;
            /** X M */
            x_m: number | null;
            /** Y M */
            y_m: number | null;
            /** Z M */
            z_m: number | null;
        };
        /** GcpAccuracyRequest */
        GcpAccuracyRequest: {
            /** Points */
            points: components["schemas"]["SurveyedGcpIn"][];
        };
        /** GcpPointIn */
        GcpPointIn: {
            /** Altitude M */
            altitude_m?: number | null;
            /** Image Filename */
            image_filename: string;
            /** Label */
            label?: string | null;
            /** Latitude */
            latitude: number;
            /** Longitude */
            longitude: number;
            /** Pixel X */
            pixel_x: number;
            /** Pixel Y */
            pixel_y: number;
        };
        /** GcpResidual */
        GcpResidual: {
            /** Distance 3D M */
            distance_3d_m: number;
            /** Dx M */
            dx_m: number;
            /** Dy M */
            dy_m: number;
            /** Dz M */
            dz_m: number;
            /** Label */
            label: string;
        };
        /** GeneralSettings */
        GeneralSettings: {
            /** Basemap Providers */
            basemap_providers?: {
                [key: string]: unknown;
            }[] | null;
            /** Data Dir */
            data_dir?: string | null;
            /** Default Basemap */
            default_basemap?: string | null;
            /** Exports Dir */
            exports_dir?: string | null;
            /** Imports Dir */
            imports_dir?: string | null;
            /** Processed Dir */
            processed_dir?: string | null;
            /** Target Crs */
            target_crs?: string | null;
        };
        /** GeneralSettingsRead */
        GeneralSettingsRead: {
            /** Basemap Providers */
            basemap_providers: {
                [key: string]: unknown;
            }[];
            /** Data Dir */
            data_dir: string;
            /** Default Basemap */
            default_basemap: string;
            /** Exports Dir */
            exports_dir: string;
            /** Imports Dir */
            imports_dir: string;
            /** Processed Dir */
            processed_dir: string;
            /** Target Crs */
            target_crs: string;
        };
        /** GeoTransform */
        GeoTransform: {
            /** Rmse M */
            rmse_m?: number;
            /** Rotation */
            rotation: [
                [
                    number,
                    number,
                    number
                ],
                [
                    number,
                    number,
                    number
                ],
                [
                    number,
                    number,
                    number
                ]
            ];
            /** Scale */
            scale: number;
            /** Translation */
            translation: [
                number,
                number,
                number
            ];
            /** Trimmed Point Count */
            trimmed_point_count?: number;
            /** Utm Origin */
            utm_origin: [
                number,
                number
            ];
            /** Utm Zone */
            utm_zone: string;
        };
        /** HistogramBin */
        HistogramBin: {
            /** Count */
            count: number;
            /** Max */
            max: number;
            /** Min */
            min: number;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** ImageBulkPatch */
        ImageBulkPatch: {
            /** Flag */
            flag?: string | null;
            /** Image Ids */
            image_ids: number[];
            /** Usable */
            usable?: boolean | null;
        };
        /** ImageOut */
        ImageOut: {
            /** Altitude M */
            altitude_m: number | null;
            /** Brightness Score */
            brightness_score: number | null;
            /** Colmap Error Px */
            colmap_error_px?: number | null;
            /** Filename */
            filename: string;
            /** Filepath */
            filepath: string;
            /** Flag */
            flag: string | null;
            /** Focal Length Mm */
            focal_length_mm: number | null;
            /** Gimbal Pitch */
            gimbal_pitch: number | null;
            /** Gps Source */
            gps_source: string | null;
            /** Height */
            height: number | null;
            /** Id */
            id: number;
            /** Latitude */
            latitude: number | null;
            /** Longitude */
            longitude: number | null;
            /** Notes */
            notes: string | null;
            /** Original Altitude M */
            original_altitude_m: number | null;
            /** Original Latitude */
            original_latitude: number | null;
            /** Original Longitude */
            original_longitude: number | null;
            /** Session Id */
            session_id: number;
            /** Sharpness Score */
            sharpness_score: number | null;
            /** Synced Altitude M */
            synced_altitude_m: number | null;
            /** Synced Latitude */
            synced_latitude: number | null;
            /** Synced Longitude */
            synced_longitude: number | null;
            /** Thumb Path */
            thumb_path: string | null;
            /** Timestamp */
            timestamp: string | null;
            /** Usable */
            usable: boolean | null;
            /** Width */
            width: number | null;
            /** Yaw */
            yaw: number | null;
        };
        /** ImagePatch */
        ImagePatch: {
            /** Flag */
            flag?: string | null;
            /** Usable */
            usable?: boolean | null;
        };
        /** ImportRequest */
        ImportRequest: {
            /** Folder Path */
            folder_path: string;
            /** Name */
            name: string;
        };
        /** IngestSettings */
        IngestSettings: {
            /** Accepted Extensions */
            accepted_extensions?: string[] | null;
            /** Blur Threshold */
            blur_threshold?: number | null;
            /** Bright Threshold */
            bright_threshold?: number | null;
            /** Dark Threshold */
            dark_threshold?: number | null;
            /** Filter Zero Gps */
            filter_zero_gps?: boolean | null;
            /** Thumbnail Jpeg Quality */
            thumbnail_jpeg_quality?: number | null;
            /** Thumbnail Size Px */
            thumbnail_size_px?: number | null;
        };
        /** IngestSettingsRead */
        IngestSettingsRead: {
            /** Accepted Extensions */
            accepted_extensions: string[];
            /** Blur Threshold */
            blur_threshold: number;
            /** Bright Threshold */
            bright_threshold: number;
            /** Dark Threshold */
            dark_threshold: number;
            /** Filter Zero Gps */
            filter_zero_gps: boolean;
            /** Thumbnail Jpeg Quality */
            thumbnail_jpeg_quality: number;
            /** Thumbnail Size Px */
            thumbnail_size_px: number;
        } & {
            [key: string]: unknown;
        };
        /** Job */
        Job: {
            /** Completed At */
            completed_at: string | null;
            effective_splat_settings: components["schemas"]["EffectiveSplatSettings"] | null;
            /** Error Msg */
            error_msg: string | null;
            /** Frames Used */
            frames_used: number;
            /** Id */
            id: number;
            /** Preset */
            preset: string;
            /** Progress Pct */
            progress_pct: number;
            /** Session Id */
            session_id: number;
            /** Source Session Ids */
            source_session_ids: number[] | null;
            /** Started At */
            started_at: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "running_colmap" | "running_gsplat" | "running_remote" | "cancelling" | "cancelled" | "complete" | "failed";
            /** Step */
            step: string;
            /**
             * Type
             * @constant
             */
            type: "reconstruction";
        };
        /** LogEntryOut */
        LogEntryOut: {
            /** Coverage Pct */
            coverage_pct: number | null;
            /** Event Type */
            event_type: string | null;
            /** Id */
            id: number;
            /** Message */
            message: string | null;
            /** Photo Count */
            photo_count: number | null;
            /** Session Id */
            session_id: number | null;
            /** Timestamp */
            timestamp: string | null;
        };
        /** MeasurementIn */
        MeasurementIn: {
            /**
             * Kind
             * @enum {string}
             */
            kind: "distance" | "area" | "point";
            /** Label */
            label?: string | null;
            /** Points */
            points: components["schemas"]["MeasurementPoint"][];
            /** Unit */
            unit?: string | null;
            /** Value */
            value?: number | null;
        };
        /** MeasurementOut */
        MeasurementOut: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: number;
            /** Kind */
            kind: string;
            /** Label */
            label: string | null;
            /** Points */
            points: components["schemas"]["MeasurementPoint"][];
            /** Reconstruction Id */
            reconstruction_id: number;
            /** Unit */
            unit: string | null;
            /** Value */
            value: number | null;
        };
        /** MeasurementPoint */
        MeasurementPoint: {
            /** Alt */
            alt?: number | null;
            /** Lat */
            lat?: number | null;
            /** Lon */
            lon?: number | null;
            /** X */
            x: number;
            /** Y */
            y: number;
            /** Z */
            z: number;
        };
        /** MeshStatusOut */
        MeshStatusOut: {
            /** Id */
            id: number;
            /** Mesh Error */
            mesh_error?: string | null;
            /** Mesh Glb Path */
            mesh_glb_path?: string | null;
            /** Mesh Mtl Path */
            mesh_mtl_path?: string | null;
            /** Mesh Obj Path */
            mesh_obj_path?: string | null;
            /** Mesh Status */
            mesh_status?: string | null;
        };
        /** MetricTrend */
        MetricTrend: {
            /** Delta */
            delta: number;
            /** End */
            end: number;
            /** Start */
            start: number;
        };
        /**
         * MissionSettings
         * @description Mission defaults. Each drives AppConfig's footprint geometry (tan(fov / 2) times
         *     altitude) or a mission computation, so values that make those degenerate are refused:
         *     a FOV of 0 or 180 degrees, a non-positive or non-finite length, or an overlap/buffer
         *     fraction of 1 (zero spacing, or no usable battery range).
         */
        MissionSettings: {
            /** Altitude Ft */
            altitude_ft?: number | null;
            /** Battery Range M */
            battery_range_m?: number | null;
            /** Default Video Fps */
            default_video_fps?: number | null;
            /** Desired Forward Overlap */
            desired_forward_overlap?: number | null;
            /** Desired Side Overlap */
            desired_side_overlap?: number | null;
            /** Flight Log Match Tolerance Sec */
            flight_log_match_tolerance_sec?: number | null;
            /** Fov Horizontal Deg */
            fov_horizontal_deg?: number | null;
            /** Fov Vertical Deg */
            fov_vertical_deg?: number | null;
            /** Image Height Px */
            image_height_px?: number | null;
            /** Image Width Px */
            image_width_px?: number | null;
            /** Lane Spacing Ft */
            lane_spacing_ft?: number | null;
            /** Mission Buffer Pct */
            mission_buffer_pct?: number | null;
        };
        /** MissionSettingsRead */
        MissionSettingsRead: {
            /** Altitude Ft */
            altitude_ft: number;
            /** Battery Range M */
            battery_range_m: number;
            /** Default Video Fps */
            default_video_fps: number;
            /** Desired Forward Overlap */
            desired_forward_overlap: number;
            /** Desired Side Overlap */
            desired_side_overlap: number;
            /** Flight Log Match Tolerance Sec */
            flight_log_match_tolerance_sec: number;
            /** Fov Horizontal Deg */
            fov_horizontal_deg: number;
            /** Fov Vertical Deg */
            fov_vertical_deg: number;
            /** Image Height Px */
            image_height_px: number;
            /** Image Width Px */
            image_width_px: number;
            /** Lane Spacing Ft */
            lane_spacing_ft: number;
            /** Mission Buffer Pct */
            mission_buffer_pct: number;
        };
        /** OrthoStatus */
        OrthoStatus: {
            /** Id */
            id: number;
            /** Ortho Error */
            ortho_error: string | null;
            /** Ortho Path */
            ortho_path: string | null;
            /** Ortho Status */
            ortho_status: ("pending" | "running" | "complete" | "failed") | null;
        };
        /** PlanGenerateFromGapsIn */
        PlanGenerateFromGapsIn: {
            /** Altitude Ft */
            altitude_ft: number;
            /** Coverage Run Id */
            coverage_run_id: number;
            /** Forward Overlap Pct */
            forward_overlap_pct: number;
            /** Side Overlap Pct */
            side_overlap_pct: number;
        };
        /** PlanIn */
        PlanIn: {
            /** Altitude Ft */
            altitude_ft: number;
            /** Forward Overlap Pct */
            forward_overlap_pct: number;
            /** Side Overlap Pct */
            side_overlap_pct: number;
            /** Target Area Id */
            target_area_id: number;
        };
        /** PlanOut */
        PlanOut: {
            /** Altitude Ft */
            altitude_ft: number | null;
            /** Batteries Estimated */
            batteries_estimated: number | null;
            /** Forward Overlap Pct */
            forward_overlap_pct: number | null;
            /** Gpx Path */
            gpx_path: string | null;
            /** Id */
            id: number;
            /** Kml Path */
            kml_path: string | null;
            /** Lane Count */
            lane_count: number | null;
            /** Lanes Geojson */
            lanes_geojson: string | null;
            /** Side Overlap Pct */
            side_overlap_pct: number | null;
            /** Target Area Id */
            target_area_id: number;
            /** Total Distance M */
            total_distance_m: number | null;
        };
        /** PolicyCandidate */
        PolicyCandidate: {
            /** Action */
            action: string;
            /** Bytes */
            bytes: number;
            /** Directory */
            directory: boolean;
            /** Path */
            path: string;
            /** Reason */
            reason: string;
        };
        /** PolicyResult */
        PolicyResult: {
            /** Candidates */
            candidates: components["schemas"]["PolicyCandidate"][];
            executed?: components["schemas"]["PolicyResultExecuted"];
            /**
             * Mode
             * @enum {string}
             */
            mode: "dry-run" | "execute";
            summary: components["schemas"]["PolicySummary"];
        };
        /** PolicyResultExecuted */
        PolicyResultExecuted: {
            /** Failed */
            failed: components["schemas"]["PolicyResultExecutedFailed"][];
            /** Removed */
            removed: string[];
        };
        /** PolicyResultExecutedFailed */
        PolicyResultExecutedFailed: {
            /** Path */
            path: string;
            /** Reason */
            reason: string;
        };
        /** PolicyRuleInput */
        PolicyRuleInput: {
            /** Age Days */
            age_days?: number | null;
            /** Disk Pct */
            disk_pct?: number | null;
            /** Target */
            target: string;
        };
        /** PolicySummary */
        PolicySummary: {
            /** Actions */
            actions: {
                [key: string]: number;
            };
            /** Failed Items */
            failed_items?: number;
            /** Removed Items */
            removed_items?: number;
            /** Total Bytes */
            total_bytes: number;
            /** Total Items */
            total_items: number;
        };
        /** PreflightCompletenessOut */
        PreflightCompletenessOut: {
            /** Completeness Pct */
            completeness_pct: number;
            /** Missing */
            missing: number;
        };
        /** PreflightCoverageOut */
        PreflightCoverageOut: {
            /** Estimated Overlap Pct */
            estimated_overlap_pct: number | null;
            /** Footprint Count */
            footprint_count: number;
            /** Footprint Coverage Pct */
            footprint_coverage_pct: number;
            /** Summed Footprint Area */
            summed_footprint_area: number;
            /** Union Area */
            union_area: number;
            /** Warnings */
            warnings: string[];
        };
        /** PreflightImageQualityContract */
        PreflightImageQualityContract: {
            /** Blur Count */
            blur_count: number;
            /** Blur Pct */
            blur_pct: number;
            /** Blur Threshold */
            blur_threshold: number;
            /** Bright Count */
            bright_count: number;
            /** Bright Pct */
            bright_pct: number;
            /** Bright Threshold */
            bright_threshold: number;
            /** Brightness Histogram */
            brightness_histogram: components["schemas"]["HistogramBin"][];
            /** Dark Count */
            dark_count: number;
            /** Dark Pct */
            dark_pct: number;
            /** Dark Threshold */
            dark_threshold: number;
            /** Flag Counts */
            flag_counts: {
                [key: string]: number;
            };
            lighting: components["schemas"]["PreflightLighting"];
            /** Sharpness Histogram */
            sharpness_histogram: components["schemas"]["HistogramBin"][];
        };
        /** PreflightImageQualityOut */
        PreflightImageQualityOut: {
            /** Blur Count */
            blur_count: number;
            /** Blur Pct */
            blur_pct: number;
            /** Blur Threshold */
            blur_threshold: number;
            /** Bright Count */
            bright_count: number;
            /** Bright Pct */
            bright_pct: number;
            /** Bright Threshold */
            bright_threshold: number;
            /** Brightness Histogram */
            brightness_histogram: components["schemas"]["HistogramBin"][];
            /** Dark Count */
            dark_count: number;
            /** Dark Pct */
            dark_pct: number;
            /** Dark Threshold */
            dark_threshold: number;
            /** Flag Counts */
            flag_counts: {
                [key: string]: number;
            };
            /** Lighting */
            lighting: {
                [key: string]: unknown;
            };
            /** Sharpness Histogram */
            sharpness_histogram: components["schemas"]["HistogramBin"][];
        };
        /** PreflightLighting */
        PreflightLighting: {
            /** Inconsistent */
            inconsistent: boolean;
            /** P10 P90 Spread */
            p10_p90_spread: number | null;
            /** Sample Count */
            sample_count: number;
            /** Threshold */
            threshold: number;
        };
        /** PreflightReportContract */
        PreflightReportContract: {
            coverage: components["schemas"]["PreflightCoverageOut"];
            gps: components["schemas"]["PreflightCompletenessOut"];
            /** Match Density */
            match_density?: {
                [key: string]: unknown;
            } | null;
            quality: components["schemas"]["PreflightImageQualityContract"];
            /** Recommended Action */
            recommended_action: string;
            /** Safe To Reconstruct */
            safe_to_reconstruct: string;
            /** Score */
            score: number;
            /** Session Id */
            session_id: number;
            timestamps: components["schemas"]["PreflightTimestampOut"];
            /** Total Frames */
            total_frames: number;
            /** Usable Frames */
            usable_frames: number;
            /** Warnings */
            warnings: string[];
        };
        /** PreflightReportOut */
        PreflightReportOut: {
            coverage: components["schemas"]["PreflightCoverageOut"];
            gps: components["schemas"]["PreflightCompletenessOut"];
            /** Match Density */
            match_density?: {
                [key: string]: unknown;
            } | null;
            quality: components["schemas"]["PreflightImageQualityOut"];
            /** Recommended Action */
            recommended_action: string;
            /** Safe To Reconstruct */
            safe_to_reconstruct: string;
            /** Score */
            score: number;
            /** Session Id */
            session_id: number;
            timestamps: components["schemas"]["PreflightTimestampOut"];
            /** Total Frames */
            total_frames: number;
            /** Usable Frames */
            usable_frames: number;
            /** Warnings */
            warnings: string[];
        };
        /** PreflightTimestampOut */
        PreflightTimestampOut: {
            /** Completeness Pct */
            completeness_pct: number;
            /** Duplicate Frames */
            duplicate_frames: number;
            /** Duplicate Groups */
            duplicate_groups: number;
            /** Gap Count */
            gap_count: number;
            /** Gap Threshold S */
            gap_threshold_s: number | null;
            /** Max Gap S */
            max_gap_s: number;
            /** Missing */
            missing: number;
            /** Typical Gap S */
            typical_gap_s: number | null;
        };
        /** PresetConfigRead */
        PresetConfigRead: {
            /** Downscale Factor */
            downscale_factor: number;
            /** Iterations */
            iterations: number;
            /** Max Gaussians */
            max_gaussians: number;
            /** Sh Degree */
            sh_degree: number;
        } & {
            [key: string]: unknown;
        };
        /** PresetSettings */
        PresetSettings: {
            /** Downscale Factor */
            downscale_factor?: number | null;
            /** Iterations */
            iterations?: number | null;
            /** Max Gaussians */
            max_gaussians?: number | null;
            /** Sh Degree */
            sh_degree?: number | null;
        };
        /** PresetsSettings */
        PresetsSettings: {
            full?: components["schemas"]["PresetSettings"] | null;
            quick?: components["schemas"]["PresetSettings"] | null;
        };
        /** ProjectCreate */
        ProjectCreate: {
            /** Description */
            description?: string | null;
            /** Name */
            name: string;
        };
        /** ProjectOut */
        ProjectOut: {
            /** Created At */
            created_at: string | null;
            /** Description */
            description: string | null;
            /** Id */
            id: number;
            /** Name */
            name: string;
            /** Session Count */
            session_count: number;
        };
        /** PullResultsIn */
        PullResultsIn: {
            /** Assets */
            assets?: string[] | null;
        };
        /** QualityScorecard */
        QualityScorecard: {
            coverage_gaps: components["schemas"]["QualityScorecardCoverageGaps"] | null;
            density: components["schemas"]["QualityScorecardDensity"];
            frame_counts: components["schemas"]["QualityScorecardFrameCounts"];
            quality: components["schemas"]["QualityScorecardQuality"];
            /** Reconstruction Id */
            reconstruction_id: number;
            reprojection_error: components["schemas"]["QualityScorecardReprojectionError"];
        };
        /** QualityScorecardCoverageGaps */
        QualityScorecardCoverageGaps: {
            /** By Level */
            by_level: {
                [key: string]: number;
            };
            /** Total Gaps */
            total_gaps: number;
            /** Voxel Size M */
            voxel_size_m?: number;
        };
        /** QualityScorecardDensity */
        QualityScorecardDensity: {
            /** Gaussian Count */
            gaussian_count: number | null;
        };
        /** QualityScorecardFrameCounts */
        QualityScorecardFrameCounts: {
            /** Frames Registered */
            frames_registered: number;
            /** Frames Used */
            frames_used: number;
            /** Registration Completeness Pct */
            registration_completeness_pct: number;
        };
        /** QualityScorecardQuality */
        QualityScorecardQuality: {
            /** Psnr Final */
            psnr_final: number | null;
            psnr_trend?: components["schemas"]["MetricTrend"];
            /** Ssim Final */
            ssim_final: number | null;
            ssim_trend?: components["schemas"]["MetricTrend"];
            /** Training Metric Points */
            training_metric_points: number;
        };
        /** QualityScorecardReprojectionError */
        QualityScorecardReprojectionError: {
            /** Frame Count With Data */
            frame_count_with_data: number;
            /** Max Px */
            max_px: number | null;
            /** Mean Px */
            mean_px: number | null;
            /** Min Px */
            min_px: number | null;
            /** Std Px */
            std_px: number | null;
        };
        /** QuickReportOut */
        QuickReportOut: {
            /** Blur Pct */
            blur_pct: number;
            /** Estimated Overlap Pct */
            estimated_overlap_pct: number | null;
            /** Exposure Issue Pct */
            exposure_issue_pct: number;
            /** Gps Completeness Pct */
            gps_completeness_pct: number;
            /**
             * Lighting Inconsistent
             * @default false
             */
            lighting_inconsistent?: boolean;
            /** Lighting P10 P90 Spread */
            lighting_p10_p90_spread?: number | null;
            /** Match Density Avg Matches */
            match_density_avg_matches?: number | null;
            /** Match Density Weak Ratio */
            match_density_weak_ratio?: number | null;
            /** Recommended Action */
            recommended_action: string;
            /** Safe To Reconstruct */
            safe_to_reconstruct: string;
            /** Score */
            score: number;
            /** Session Id */
            session_id: number;
            /** Timestamp Completeness Pct */
            timestamp_completeness_pct: number;
            /** Total Frames */
            total_frames: number;
            /** Usable Frames */
            usable_frames: number;
            /** Warnings */
            warnings: string[];
        };
        /**
         * ReconstructionContract
         * @description Precise wire documentation; ReconstructionOut still controls serialization.
         */
        ReconstructionContract: {
            effective_splat_settings: components["schemas"]["EffectiveSplatSettings"] | null;
            /** Error Msg */
            error_msg: string | null;
            /** Flythrough Error */
            flythrough_error?: string | null;
            /** Flythrough Path */
            flythrough_path?: string | null;
            /** Flythrough Status */
            flythrough_status?: string | null;
            /** Frames Registered */
            frames_registered: number | null;
            /** Frames Used */
            frames_used: number;
            /** Gaussian Count */
            gaussian_count: number | null;
            /** Geo Transform */
            geo_transform: string | null;
            /** Id */
            id: number;
            /** Mesh Error */
            mesh_error?: string | null;
            /** Mesh Glb Path */
            mesh_glb_path?: string | null;
            /** Mesh Mtl Path */
            mesh_mtl_path?: string | null;
            /** Mesh Obj Path */
            mesh_obj_path?: string | null;
            /** Mesh Status */
            mesh_status?: string | null;
            /** Parent Reconstruction Id */
            parent_reconstruction_id?: number | null;
            /** Pointcloud Path */
            pointcloud_path?: string | null;
            /** Preset */
            preset: string;
            /** Progress Pct */
            progress_pct: number;
            /** Psnr */
            psnr: number | null;
            /** Semantic Error */
            semantic_error?: string | null;
            /** Semantic Labels Path */
            semantic_labels_path?: string | null;
            /** Semantic Status */
            semantic_status?: string | null;
            /** Session Id */
            session_id: number;
            /** Source Session Ids */
            source_session_ids?: number[] | null;
            /** Splat Path */
            splat_path: string | null;
            /** Ssim */
            ssim: number | null;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "running_colmap" | "running_gsplat" | "running_remote" | "cancelling" | "cancelled" | "complete" | "failed";
            /** Step */
            step: string;
            /** Training Metrics */
            training_metrics: components["schemas"]["TrainingMetricPoint"][] | null;
        };
        /** ReconstructionDiagnosticsOut */
        ReconstructionDiagnosticsOut: {
            /** Map Heatmap */
            map_heatmap: components["schemas"]["ReconstructionMapHeatPoint"][];
            /** Reconstruction Id */
            reconstruction_id: number;
            /** Registered Images */
            registered_images: components["schemas"]["ReconstructionImageDiagnostic"][];
            /** Suggestions */
            suggestions: components["schemas"]["ReconstructionSuggestion"][];
            /** Summary */
            summary: {
                [key: string]: unknown;
            };
            /** Timeline Heatmap */
            timeline_heatmap: components["schemas"]["ReconstructionTimelineBucket"][];
            /** Unregistered Images */
            unregistered_images: components["schemas"]["ReconstructionImageDiagnostic"][];
        };
        /** ReconstructionImageDiagnostic */
        ReconstructionImageDiagnostic: {
            /** Altitude M */
            altitude_m?: number | null;
            /** Colmap Error Px */
            colmap_error_px?: number | null;
            /** Filename */
            filename: string;
            /** Id */
            id: number;
            /** Latitude */
            latitude?: number | null;
            /** Longitude */
            longitude?: number | null;
            /** Registered */
            registered: boolean;
            /** Timestamp */
            timestamp?: string | null;
        };
        /** ReconstructionMapHeatPoint */
        ReconstructionMapHeatPoint: {
            /** Filename */
            filename: string;
            /** Id */
            id: number;
            /** Latitude */
            latitude: number;
            /** Longitude */
            longitude: number;
            /** Weight */
            weight: number;
        };
        /** ReconstructionOut */
        ReconstructionOut: {
            /** Effective Splat Settings */
            effective_splat_settings?: {
                [key: string]: unknown;
            } | null;
            /** Error Msg */
            error_msg: string | null;
            /** Flythrough Error */
            flythrough_error?: string | null;
            /** Flythrough Path */
            flythrough_path?: string | null;
            /** Flythrough Status */
            flythrough_status?: string | null;
            /** Frames Registered */
            frames_registered: number | null;
            /** Frames Used */
            frames_used: number;
            /** Gaussian Count */
            gaussian_count: number | null;
            /** Geo Transform */
            geo_transform: string | null;
            /** Id */
            id: number;
            /** Mesh Error */
            mesh_error?: string | null;
            /** Mesh Glb Path */
            mesh_glb_path?: string | null;
            /** Mesh Mtl Path */
            mesh_mtl_path?: string | null;
            /** Mesh Obj Path */
            mesh_obj_path?: string | null;
            /** Mesh Status */
            mesh_status?: string | null;
            /** Parent Reconstruction Id */
            parent_reconstruction_id?: number | null;
            /** Pointcloud Path */
            pointcloud_path?: string | null;
            /** Preset */
            preset: string;
            /** Progress Pct */
            progress_pct: number;
            /** Psnr */
            psnr: number | null;
            /** Semantic Error */
            semantic_error?: string | null;
            /** Semantic Labels Path */
            semantic_labels_path?: string | null;
            /** Semantic Status */
            semantic_status?: string | null;
            /** Session Id */
            session_id: number;
            /** Source Session Ids */
            source_session_ids?: number[] | null;
            /** Splat Path */
            splat_path: string | null;
            /** Ssim */
            ssim: number | null;
            /** Status */
            status: string;
            /** Step */
            step: string;
            /** Training Metrics */
            training_metrics?: {
                [key: string]: unknown;
            }[] | null;
        };
        /** ReconstructionSettings */
        ReconstructionSettings: {
            /** Camera Model */
            camera_model?: string | null;
            /** Colmap Threads */
            colmap_threads?: number | null;
            /** Default Preset */
            default_preset?: string | null;
            /** Matcher */
            matcher?: string | null;
            presets?: components["schemas"]["PresetsSettings"] | null;
            /** Sift Max Features */
            sift_max_features?: number | null;
            /** Single Camera */
            single_camera?: boolean | null;
        };
        /** ReconstructionSettingsRead */
        ReconstructionSettingsRead: {
            /** Camera Model */
            camera_model: string;
            /** Camera Profiles */
            camera_profiles: {
                [key: string]: unknown;
            }[];
            /** Colmap Threads */
            colmap_threads: number;
            /** Default Preset */
            default_preset: string;
            /** Dense Rerun */
            dense_rerun: {
                [key: string]: unknown;
            };
            /** Mapper */
            mapper: string;
            /** Matcher */
            matcher: string;
            /** Presets */
            presets: {
                [key: string]: components["schemas"]["PresetConfigRead"];
            };
            /** Sift Max Features */
            sift_max_features: number;
            /** Single Camera */
            single_camera: boolean;
            /** Spatial Matcher Min Images */
            spatial_matcher_min_images: number;
        } & {
            [key: string]: unknown;
        };
        /** ReconstructionSuggestion */
        ReconstructionSuggestion: {
            /** Code */
            code: string;
            /** Detail */
            detail: string;
            /** Setting */
            setting?: {
                [key: string]: unknown;
            } | null;
            /** Title */
            title: string;
        };
        /** ReconstructionTimelineBucket */
        ReconstructionTimelineBucket: {
            /** Bucket */
            bucket: number;
            /** End Index */
            end_index: number;
            /** Start Index */
            start_index: number;
            /** Total */
            total: number;
            /** Unregistered */
            unregistered: number;
            /** Unregistered Pct */
            unregistered_pct: number;
        };
        /** RenderSettings */
        RenderSettings: {
            /** Flythrough Fps */
            flythrough_fps?: number | null;
            /** Flythrough Height */
            flythrough_height?: number | null;
            /** Flythrough Width */
            flythrough_width?: number | null;
            /** Lod Medium Ratio */
            lod_medium_ratio?: number | null;
            /** Lod Preview Ratio */
            lod_preview_ratio?: number | null;
            /** Thumbnail Quality */
            thumbnail_quality?: number | null;
            /** Thumbnail Size Px */
            thumbnail_size_px?: number | null;
        };
        /** RenderSettingsRead */
        RenderSettingsRead: {
            /** Flythrough Fps */
            flythrough_fps: number;
            /** Flythrough Height */
            flythrough_height: number;
            /** Flythrough Width */
            flythrough_width: number;
            /** Lod Medium Ratio */
            lod_medium_ratio: number;
            /** Lod Preview Ratio */
            lod_preview_ratio: number;
            /** Thumbnail Quality */
            thumbnail_quality: number;
            /** Thumbnail Size Px */
            thumbnail_size_px: number;
        } & {
            [key: string]: unknown;
        };
        /** RenderVideoIn */
        RenderVideoIn: {
            /** Fps */
            fps?: number;
            /** Height */
            height?: number;
            /** Keyframes */
            keyframes: components["schemas"]["FlythroughKeyframe"][];
            /** Width */
            width?: number;
        };
        /** RestoreRequest */
        RestoreRequest: {
            /** Zip Path */
            zip_path: string;
        };
        /** SegmentOut */
        SegmentOut: {
            /** Distance M */
            distance_m: number;
            /** From Lane */
            from_lane: number;
            /** Gpx Path */
            gpx_path?: string | null;
            /** Index */
            index: number;
            /** Kml Path */
            kml_path?: string | null;
            /** Landing Wpt */
            landing_wpt?: number[] | null;
            /** Lanes Geojson */
            lanes_geojson?: string | null;
            /** Resume Wpt */
            resume_wpt?: number[] | null;
            /** To Lane */
            to_lane: number;
        };
        /** SemanticClassCounts */
        SemanticClassCounts: {
            /** Ground */
            ground: number;
            /** Other */
            other: number;
            /** Structure */
            structure: number;
            /** Vegetation */
            vegetation: number;
            /** Vehicle */
            vehicle: number;
            /** Water */
            water: number;
        };
        /** SemanticStatusOut */
        SemanticStatusOut: {
            /** Id */
            id: number;
            /** Semantic Error */
            semantic_error?: string | null;
            /** Semantic Labels Path */
            semantic_labels_path?: string | null;
            /** Semantic Status */
            semantic_status?: string | null;
        };
        /** SemanticSummary */
        SemanticSummary: {
            class_counts: components["schemas"]["SemanticClassCounts"];
            /** Confidence Mean */
            confidence_mean: number | null;
            /** Count */
            count: number;
            /**
             * Lod
             * @enum {string}
             */
            lod: "full" | "medium" | "preview";
            /** Meta */
            meta: {
                [key: string]: unknown;
            };
            /** Unlabeled */
            unlabeled: number;
        };
        /** SessionOut */
        SessionOut: {
            /** Folder Path */
            folder_path: string | null;
            /** Id */
            id: number;
            /** Imported At */
            imported_at: string | null;
            /** Name */
            name: string;
            /** Notes */
            notes?: string | null;
            /** Photo Count */
            photo_count: number;
            /** Project Id */
            project_id?: number | null;
            /**
             * Tags
             * @default []
             */
            tags?: string[];
            /** Usable Count */
            usable_count: number;
        };
        /**
         * SessionPatch
         * @description PATCH body — omitted (None) fields are left unchanged.
         *
         *     ``tags`` replaces the whole list; ``notes: ""`` clears the notes.
         */
        SessionPatch: {
            /** Notes */
            notes?: string | null;
            /** Tags */
            tags?: string[] | null;
        };
        /** SessionProgress */
        SessionProgress: {
            /** Error */
            error?: string;
            /** Processed */
            processed: number;
            /** Skipped */
            skipped?: number;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "running" | "done" | "error" | "unknown";
            /** Total */
            total: number;
        };
        /** SessionSearchMatchOut */
        SessionSearchMatchOut: {
            /** Snippet */
            snippet: string;
            /**
             * Source
             * @enum {string}
             */
            source: "session" | "log" | "defect";
        };
        /** SessionSearchOut */
        SessionSearchOut: {
            /** Folder Path */
            folder_path: string | null;
            /** Id */
            id: number;
            /** Imported At */
            imported_at: string | null;
            /** Matches */
            matches: components["schemas"]["SessionSearchMatchOut"][];
            /** Name */
            name: string;
            /** Notes */
            notes?: string | null;
            /** Photo Count */
            photo_count: number;
            /** Project Id */
            project_id?: number | null;
            /**
             * Tags
             * @default []
             */
            tags?: string[];
            /** Usable Count */
            usable_count: number;
        };
        /**
         * SettingsPatch
         * @description PATCH /settings body — all sections optional; unknown top-level keys → 422.
         */
        SettingsPatch: {
            general?: components["schemas"]["GeneralSettings"] | null;
            ingest?: components["schemas"]["IngestSettings"] | null;
            mission?: components["schemas"]["MissionSettings"] | null;
            reconstruction?: components["schemas"]["ReconstructionSettings"] | null;
            render?: components["schemas"]["RenderSettings"] | null;
        };
        /** ShareLinkState */
        ShareLinkState: {
            /** Created At */
            created_at: string;
            /** Expires At */
            expires_at: string;
            /** Id */
            id: number;
            /** Password Protected */
            password_protected: boolean;
            /** Reconstruction Id */
            reconstruction_id: number;
            /** Revoked At */
            revoked_at: string | null;
        };
        /** ShareLinkUnlockRequest */
        ShareLinkUnlockRequest: {
            /** Password */
            password: string;
        };
        /** ShareViewerArtifacts */
        ShareViewerArtifacts: {
            /** Mesh Glb */
            mesh_glb: string | null;
            /** Mesh Obj */
            mesh_obj: string | null;
            /** Pointcloud */
            pointcloud: string;
        };
        /** ShareViewerPayload */
        ShareViewerPayload: {
            artifacts: components["schemas"]["ShareViewerArtifacts"];
            /** Frames Registered */
            frames_registered: number | null;
            /** Frames Used */
            frames_used: number;
            /** Gaussian Count */
            gaussian_count: number | null;
            /** Generated At */
            generated_at: number;
            /** Legacy Token Required */
            legacy_token_required: boolean;
            /** Psnr */
            psnr: number | null;
            /** Reconstruction Id */
            reconstruction_id: number;
            /** Session Id */
            session_id: number;
            /** Ssim */
            ssim: number | null;
            /** Status */
            status: string;
        };
        /** SiteTrendOut */
        SiteTrendOut: {
            /** Points */
            points: components["schemas"]["SiteTrendPointOut"][];
            /** Project Id */
            project_id: number;
        };
        /**
         * SiteTrendPointOut
         * @description One existing session's read-only quality and reconstruction snapshot.
         */
        SiteTrendPointOut: {
            /** Coverage Pct */
            coverage_pct: number | null;
            /** Frames Registered */
            frames_registered: number | null;
            /** Imported At */
            imported_at: string | null;
            /** Photo Count */
            photo_count: number;
            /** Psnr */
            psnr: number | null;
            /** Reconstruction Id */
            reconstruction_id: number | null;
            /** Session Id */
            session_id: number;
            /** Session Name */
            session_name: string;
            /** Ssim */
            ssim: number | null;
            /** Usable Count */
            usable_count: number;
            /** Usable Pct */
            usable_pct: number | null;
        };
        /** SplatTransformCleanupIn */
        SplatTransformCleanupIn: {
            /** Decimate */
            decimate?: number | null;
            /**
             * Morton
             * @default true
             */
            morton?: boolean;
            /**
             * Opacity Floor
             * @default 0.01
             */
            opacity_floor?: number | null;
            /**
             * Sh Bands
             * @default 0
             */
            sh_bands?: number | null;
        };
        /** SplatTransformCleanupOut */
        SplatTransformCleanupOut: {
            /** Cleaned Path */
            cleaned_path: string;
            /** Returncode */
            returncode: number;
            /** Stderr */
            stderr: string;
            /** Stdout */
            stdout: string;
        };
        /** SplatTransformCompressIn */
        SplatTransformCompressIn: {
            /**
             * Format
             * @default spz
             */
            format?: string;
            /** Quality */
            quality?: number | null;
        };
        /** SplatTransformCompressOut */
        SplatTransformCompressOut: {
            /** Compressed Path */
            compressed_path: string;
            /** Returncode */
            returncode: number;
            /** Stderr */
            stderr: string;
            /** Stdout */
            stdout: string;
        };
        /** StartIn */
        StartIn: {
            /**
             * Backend
             * @default colmap
             */
            backend?: string;
            /** Parent Reconstruction Id */
            parent_reconstruction_id?: number | null;
            /**
             * Preset
             * @default quick
             */
            preset?: string;
            /** Session Id */
            session_id?: number | null;
            /** Session Ids */
            session_ids?: number[] | null;
            /** Target Area Id */
            target_area_id?: number | null;
            /** Webodm Options */
            webodm_options?: components["schemas"]["WebODMTaskOption"][];
        };
        /** StartUploadRequest */
        StartUploadRequest: {
            /** Files */
            files: components["schemas"]["UploadFilePlan"][];
            /** Name */
            name: string;
            /** Total Bytes */
            total_bytes: number;
        };
        /** StartUploadResponse */
        StartUploadResponse: {
            /** Chunk Size */
            chunk_size: number;
            /** Max File Bytes */
            max_file_bytes: number;
            /** Max Total Bytes */
            max_total_bytes: number;
            /** Quota Bytes */
            quota_bytes: number;
            /** Upload Id */
            upload_id: string;
        };
        /** StorageFileItem */
        StorageFileItem: {
            /** Modified */
            modified: number;
            /** Name */
            name: string;
            /** Path */
            path: string;
            /** Size Bytes */
            size_bytes: number;
        };
        /** StorageFileList */
        StorageFileList: {
            /** Directory */
            directory: string;
            /** Files */
            files: components["schemas"]["StorageFileItem"][];
        };
        /** StorageSessionBreakdown */
        StorageSessionBreakdown: {
            /** Bytes */
            bytes: number;
            /** Session Id */
            session_id: string;
        };
        /** StorageStats */
        StorageStats: {
            /** By Session */
            by_session: components["schemas"]["StorageSessionBreakdown"][];
            by_type: components["schemas"]["StorageStatsByType"];
            /** Total Bytes */
            total_bytes: number;
        };
        /** StorageStatsByType */
        StorageStatsByType: {
            /** Data */
            data: number;
            /** Exports */
            exports: number;
            /** Imports */
            imports: number;
            /** Processed */
            processed: number;
        };
        /** SubmitTaskIn */
        SubmitTaskIn: {
            /** Options */
            options?: components["schemas"]["TaskOption"][];
            /** Project Name */
            project_name?: string | null;
            /** Task Name */
            task_name?: string | null;
        };
        /**
         * SurveyedGcpIn
         * @description A paired surveyed/reconstructed GCP in local reconstruction coordinates.
         */
        SurveyedGcpIn: {
            /** Label */
            label?: string | null;
            /** Reconstructed X */
            reconstructed_x: number;
            /** Reconstructed Y */
            reconstructed_y: number;
            /** Reconstructed Z */
            reconstructed_z: number;
            /** X */
            x: number;
            /** Y */
            y: number;
            /** Z */
            z: number;
        };
        /**
         * SurveyedPointIn
         * @description A surveyed checkpoint: UTM easting/northing (m) in the reconstruction's zone.
         *
         *     ``z`` is height in the reconstruction's geo-transform vertical frame. The zone is
         *     the ``utm_zone`` of ``GET /reconstruction/{id}/geo-transform``.
         */
        SurveyedPointIn: {
            /** Label */
            label?: string | null;
            /** X */
            x: number;
            /** Y */
            y: number;
            /** Z */
            z: number;
        };
        /** SurveyReport */
        SurveyReport: {
            /** Annotations */
            annotations: components["schemas"]["SurveyReportAnnotation"][];
            coverage: components["schemas"]["SurveyReportCoverage"];
            frame_summary: components["schemas"]["SurveyReportFrameSummary"];
            /** Generated At */
            generated_at: string;
            /** Html */
            html: string;
            quality_assessment: components["schemas"]["SurveyReportQualityAssessment"];
            /** Reconstructions */
            reconstructions: components["schemas"]["SurveyReportReconstruction"][];
            /** Report Type */
            report_type: string;
            session: components["schemas"]["SurveyReportSession"];
            /** Version */
            version: string;
        };
        /** SurveyReportAnnotation */
        SurveyReportAnnotation: {
            /** Alt M */
            alt_m: number;
            /** Color */
            color: string;
            /** Created At */
            created_at: string | null;
            /** Id */
            id: number;
            /** Label */
            label: string;
            /** Lat */
            lat: number;
            /** Lon */
            lon: number;
            /** Reconstruction Id */
            reconstruction_id: number;
        };
        /** SurveyReportCamera */
        SurveyReportCamera: {
            /** Focal Length Mm */
            focal_length_mm: number | null;
            /** Height */
            height: number | null;
            /** Make */
            make: string | null;
            /** Model */
            model: string | null;
            /** Width */
            width: number | null;
        };
        /** SurveyReportCoverage */
        SurveyReportCoverage: {
            /** Available */
            available: boolean;
            /** Coverage Pct */
            coverage_pct?: number;
            /** Estimated Overlap Pct */
            estimated_overlap_pct?: number | null;
            /** Footprint Count */
            footprint_count?: number;
            /** Summed Footprint Area */
            summed_footprint_area?: number;
            /** Union Area */
            union_area?: number;
            /** Warnings */
            warnings?: string[];
        };
        /** SurveyReportFrameSummary */
        SurveyReportFrameSummary: {
            camera: components["schemas"]["SurveyReportCamera"] | null;
            /** Gps Present */
            gps_present: number;
            /** Quality Breakdown */
            quality_breakdown: {
                [key: string]: number;
            };
            /** Total */
            total: number;
            /** Usable */
            usable: number;
        };
        /** SurveyReportGps */
        SurveyReportGps: {
            /** Completeness Pct */
            completeness_pct: number;
            /** Missing Frames */
            missing_frames: number;
        };
        /** SurveyReportOpticalQuality */
        SurveyReportOpticalQuality: {
            /** Blur Pct */
            blur_pct: number;
            /** Bright Pct */
            bright_pct: number;
            /** Dark Pct */
            dark_pct: number;
        };
        /** SurveyReportQualityAssessment */
        SurveyReportQualityAssessment: {
            /** Available */
            available: boolean;
            gps?: components["schemas"]["SurveyReportGps"];
            /** Match Density */
            match_density?: {
                [key: string]: unknown;
            } | null;
            optical_quality?: components["schemas"]["SurveyReportOpticalQuality"];
            /** Reason */
            reason?: string;
            /** Recommended Action */
            recommended_action?: string | null;
            /** Safe To Reconstruct */
            safe_to_reconstruct?: string | null;
            /** Score */
            score?: number | null;
            timestamps?: components["schemas"]["SurveyReportTimestamps"];
            /** Warnings */
            warnings?: string[];
        };
        /** SurveyReportReconstruction */
        SurveyReportReconstruction: {
            /** Artifacts */
            artifacts: {
                [key: string]: string;
            };
            /** Completed At */
            completed_at: string | null;
            /** Duration S */
            duration_s: number | null;
            /** Flythrough Status */
            flythrough_status: string | null;
            /** Frames Registered */
            frames_registered: number | null;
            /** Frames Used */
            frames_used: number;
            /** Gaussian Count */
            gaussian_count: number | null;
            /** Id */
            id: number;
            /** Mesh Status */
            mesh_status: string | null;
            /** Preset */
            preset: string;
            /** Psnr */
            psnr: number | null;
            /** Ssim */
            ssim: number | null;
            /** Started At */
            started_at: string | null;
            /** Status */
            status: string;
            /** Training Metrics */
            training_metrics: {
                [key: string]: components["schemas"]["TrainingMetricPoint"][];
            };
        };
        /** SurveyReportSession */
        SurveyReportSession: {
            /** Folder Path */
            folder_path: string | null;
            /** Id */
            id: number;
            /** Imported At */
            imported_at: string | null;
            /** Name */
            name: string;
            /** Notes */
            notes: string | null;
            /** Photo Count */
            photo_count: number;
            /** Usable Count */
            usable_count: number;
        };
        /** SurveyReportTimestamps */
        SurveyReportTimestamps: {
            /** Completeness Pct */
            completeness_pct: number;
            /** Duplicate Groups */
            duplicate_groups: number;
            /** Gap Count */
            gap_count: number;
            /** Missing */
            missing: number;
        };
        /** SystemAccelerator */
        SystemAccelerator: {
            /** Description */
            description: string;
            /**
             * Device
             * @enum {string}
             */
            device: "cuda" | "mps" | "cpu";
            /**
             * Kind
             * @enum {string}
             */
            kind: "cuda" | "metal" | "cpu";
            /** Splat Backend */
            splat_backend: ("cuda_gsplat" | "metal_msplat") | null;
            /** Splat Backend Available */
            splat_backend_available: boolean;
        };
        /** SystemResources */
        SystemResources: {
            accelerator: components["schemas"]["SystemAccelerator"];
            /** Colmap Available */
            colmap_available: boolean;
            /** Colmap Capabilities */
            colmap_capabilities: {
                [key: string]: unknown;
            };
            /** Cpu Pct */
            cpu_pct: number;
            /** Disk Io Mbps */
            disk_io_mbps: number | null;
            /** Disk Total Gb */
            disk_total_gb: number;
            /** Disk Used Gb */
            disk_used_gb: number;
            /** Gpu Name */
            gpu_name: string | null;
            /** Gpu Pct */
            gpu_pct: number | null;
            /** Ram Total Gb */
            ram_total_gb: number;
            /** Ram Used Gb */
            ram_used_gb: number;
            /** Splat Transform Available */
            splat_transform_available: boolean;
            /** Tools */
            tools: components["schemas"]["SystemTool"][];
            /** Vram Total Gb */
            vram_total_gb: number | null;
            /** Vram Used Gb */
            vram_used_gb: number | null;
            /** Workflows */
            workflows: components["schemas"]["WorkflowStatus"][];
        };
        /** SystemTool */
        SystemTool: {
            /** Available */
            available: boolean;
            /** Error */
            error: string | null;
            /** Install Commands */
            install_commands: {
                [key: string]: string;
            };
            /** Install Hint */
            install_hint: string | null;
            /**
             * Key
             * @enum {string}
             */
            key: "ffmpeg" | "exiftool" | "colmap" | "torch" | "gsplat" | "msplat" | "sugar" | "transformers";
            /** Label */
            label: string;
            /** Path */
            path: string | null;
            /** Version */
            version: string | null;
        };
        /** TargetAreaIn */
        TargetAreaIn: {
            /** Geom Geojson */
            geom_geojson: string;
            /** Name */
            name: string;
        };
        /** TargetAreaOut */
        TargetAreaOut: {
            /** Geom Geojson */
            geom_geojson: string | null;
            /** Id */
            id: number;
            /** Name */
            name: string;
        };
        /** TaskOption */
        TaskOption: {
            /** Name */
            name: string;
            /** Value */
            value: string | number | boolean;
        };
        /** TrainingMetricPoint */
        TrainingMetricPoint: {
            /** Iter */
            iter: number;
            /** Psnr */
            psnr: number;
            /** Ssim */
            ssim: number;
        };
        /** UploadFilePlan */
        UploadFilePlan: {
            /** Path */
            path: string;
            /** Size */
            size: number;
        };
        /** UploadProgress */
        UploadProgress: {
            /** Error */
            error?: string | null;
            /** File Count */
            file_count: number;
            /** Session Id */
            session_id?: number | null;
            /** Status */
            status: string;
            /** Total Bytes */
            total_bytes: number;
            /** Upload Id */
            upload_id: string;
            /** Uploaded Bytes */
            uploaded_bytes: number;
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /** ValidationOut */
        ValidationOut: {
            /**
             * Info
             * @default []
             */
            info?: string[];
            /** Plan Id */
            plan_id: number;
            /** Valid */
            valid: boolean;
            /** Violations */
            violations: string[];
            /** Warnings */
            warnings: string[];
        };
        /**
         * WebODMReconstructionOut
         * @description A submitted remote task; poll it through the existing WebODM API.
         */
        WebODMReconstructionOut: {
            /**
             * Backend
             * @default webodm
             */
            backend?: string;
            /** Images Submitted */
            images_submitted: number;
            /** Project Id */
            project_id: number;
            /** Results Url */
            results_url: string;
            /** Session Id */
            session_id: number;
            /** Status Url */
            status_url: string;
            /** Task Id */
            task_id: number;
        };
        /** WebODMTaskOption */
        WebODMTaskOption: {
            /** Name */
            name: string;
            /** Value */
            value: string | number | boolean;
        };
        /** WorkflowStatus */
        WorkflowStatus: {
            /** Available */
            available: boolean;
            /** Key */
            key: string;
            /** Label */
            label: string;
            /** Missing */
            missing: string[];
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    get_auto_import_status_auto_import_status_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    create_comparison_comparisons_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ComparisonIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ComparisonOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_comparison_comparisons__comparison_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                comparison_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ComparisonOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_comparison_comparisons__comparison_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                comparison_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_diff_comparisons__comparison_id__diff_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                comparison_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ComparisonDiff"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_diff_geojson_comparisons__comparison_id__diff_geojson_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                comparison_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_comparison_metrics_comparisons__comparison_id__metrics_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                comparison_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_coverage_run_coverage__run_id__export_get: {
        parameters: {
            query?: {
                format?: string;
            };
            header?: never;
            path: {
                run_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_coverage_results_coverage_results_get: {
        parameters: {
            query: {
                session_id: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CoverageRunOut"] | null;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_latest_coverage_results_coverage_results_export_get: {
        parameters: {
            query: {
                format?: string;
                session_id: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    run_coverage_analysis_coverage_run_post: {
        parameters: {
            query: {
                session_id: number;
                target_area_id: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CoverageRunOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    upload_reconstruction_to_cesium_ion_export_reconstructions__reconstruction_id__cesium_ion_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_elevation_export_reconstructions__reconstruction_id__elevation_post: {
        parameters: {
            query: {
                product: string;
                resolution_m: number;
            };
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_geopackage_export_reconstructions__reconstruction_id__geopackage_get: {
        parameters: {
            query?: {
                comparison_id?: number | null;
            };
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_gis_project_files_export_reconstructions__reconstruction_id__gis_project_files_post: {
        parameters: {
            query?: {
                comparison_id?: number | null;
            };
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_measurements_csv_export_reconstructions__reconstruction_id__measurements_csv_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_measurements_geojson_export_reconstructions__reconstruction_id__measurements_geojson_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_orthomosaic_export_reconstructions__reconstruction_id__orthomosaic_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_reconstruction_share_bundle_export_reconstructions__reconstruction_id__share_bundle_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_share_link_export_reconstructions__reconstruction_id__share_link_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["CreateShareLinkRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreatedShareLink"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_share_links_export_reconstructions__reconstruction_id__share_links_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ShareLinkState"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    revoke_share_link_export_reconstructions__reconstruction_id__share_links__share_link_id__revoke_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
                share_link_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ShareLinkState"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_slope_overlay_export_reconstructions__reconstruction_id__slope_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_compact_splat_export_reconstructions__reconstruction_id__splat_post: {
        parameters: {
            query?: {
                preset?: string;
            };
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_usd_handoff_export_reconstructions__reconstruction_id__usd_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_reproducibility_manifest_export_reproducibility_manifest_post: {
        parameters: {
            query: {
                artifact_path?: string | null;
                workflow: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_survey_report_export_survey_report_get: {
        parameters: {
            query: {
                format?: string;
                session_id: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SurveyReport"];
                    "application/pdf": unknown;
                    "text/html": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_survey_report_export_survey_report_post: {
        parameters: {
            query: {
                format?: string;
                session_id: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SurveyReport"];
                    "application/pdf": unknown;
                    "text/html": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_webodm_georeferencing_csv_export_webodm_georeferencing_csv_post: {
        parameters: {
            query: {
                session_id: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_webodm_georeferencing_csv_export_webodm_georeferencing_csv_download_get: {
        parameters: {
            query: {
                session_id: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_webodm_package_export_webodm_package_post: {
        parameters: {
            query: {
                include_gcp?: boolean;
                include_images?: boolean;
                mode?: string;
                session_id: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    apply_sync_flight_logs_apply_post: {
        parameters: {
            query: {
                offset_s?: number;
                session_id: number;
                tolerance_s?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    match_preview_flight_logs_match_preview_get: {
        parameters: {
            query: {
                offset_s?: number;
                session_id: number;
                tolerance_s?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    offset_preview_flight_logs_offset_preview_get: {
        parameters: {
            query: {
                offset_s?: number;
                session_id: number;
                step_s?: number;
                tolerance_s?: number;
                window_s?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    upload_flight_log_flight_logs_upload_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_flight_log_flight_logs_upload_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_footprints_footprints_get: {
        parameters: {
            query: {
                session_id: number;
                /** @description Only return footprints with id > since_id. Lets a live-import client poll incrementally instead of re-fetching the whole session each tick. */
                since_id?: number | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FootprintOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_footprints_footprints_export_get: {
        parameters: {
            query: {
                format?: string;
                session_id: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_control_points_georeferencing_control_points_export_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ControlPointExportIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    import_control_points_georeferencing_control_points_import_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ControlPointCsvIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    build_gcp_list_georeferencing_gcp_list_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GcpPointIn"][];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    gcp_accuracy_report_georeferencing_sessions__session_id__accuracy_report_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GcpAccuracyRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GcpAccuracyReport"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_precision_workflow_georeferencing_sessions__session_id__precision_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    health_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    list_images_images_get: {
        parameters: {
            query: {
                flag?: string | null;
                has_footprint?: boolean | null;
                session_id: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImageOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    patch_image_images__image_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                image_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ImagePatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImageOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_thumb_images__image_id__thumb_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                image_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    bulk_patch_images_images_bulk_patch: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ImageBulkPatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_jobs_jobs__get: {
        parameters: {
            query?: {
                limit?: number;
                skip?: number;
                status?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Job"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_queue_entries_jobs_queue_get: {
        parameters: {
            query?: {
                job_type?: string | null;
                limit?: number;
                skip?: number;
                status?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_queue_entry_jobs_queue__job_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_queue_entry_jobs_queue__job_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    pin_lock_status_pin_lock_status_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    unlock_pin_lock_pin_lock_unlock_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    [key: string]: string;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_gpx_plans__plan_id__gpx_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_kml_plans__plan_id__kml_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_plan_segments_plans__plan_id__segments_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SegmentOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_segment_gpx_plans__plan_id__segments__segment_index__gpx_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: number;
                segment_index: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_segment_kml_plans__plan_id__segments__segment_index__kml_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: number;
                segment_index: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    validate_mission_plan_plans__plan_id__validate_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ValidationOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_plan_plans_generate_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PlanIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlanOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_plan_from_gaps_plans_generate_from_gaps_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PlanGenerateFromGapsIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlanOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_projects_projects__get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectOut"][];
                };
            };
        };
    };
    create_project_projects__post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_project_projects__project_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_project_projects__project_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_project_sessions_projects__project_id__sessions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_project_session_projects__project_id__sessions_import_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ImportRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_project_trends_projects__project_id__trends_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SiteTrendOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_reconstruction_reconstruction__reconstruction_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_annotations_reconstruction__reconstruction_id__annotations_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnnotationOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_annotation_reconstruction__reconstruction_id__annotations_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AnnotationIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnnotationOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_annotations_geojson_reconstruction__reconstruction_id__annotations_geojson_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_annotation_reconstruction__reconstruction_id__annotations__annotation_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                annotation_id: number;
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_calibration_drift_report_reconstruction__reconstruction_id__calibration_drift_report_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    request_cancel_reconstruction__reconstruction_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReconstructionContract"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cleanup_splat_reconstruction__reconstruction_id__cleanup_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["CleanupIn"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CleanupOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_coverage_gaps_reconstruction__reconstruction_id__coverage_gaps_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CoverageGapCell"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    start_dense_rerun_reconstruction__reconstruction_id__dense_rerun_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DenseRerunIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReconstructionOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_dense_rerun_plan_reconstruction__reconstruction_id__dense_rerun_plan_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_diagnostics_reconstruction__reconstruction_id__diagnostics_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReconstructionDiagnosticsOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_reconstruction_bundle_reconstruction__reconstruction_id__download_bundle_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_flythrough_reconstruction__reconstruction_id__flythrough_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_flythrough_status_reconstruction__reconstruction_id__flythrough_status_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FlythroughStatusOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_geo_transform_reconstruction__reconstruction_id__geo_transform_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GeoTransform"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_lineage_reconstruction__reconstruction_id__lineage_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_log_reconstruction__reconstruction_id__log_get: {
        parameters: {
            query?: {
                limit?: number;
            };
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_measurements_reconstruction__reconstruction_id__measurements_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MeasurementOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_measurement_reconstruction__reconstruction_id__measurements_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MeasurementIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MeasurementOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_measurement_reconstruction__reconstruction_id__measurements__measurement_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                measurement_id: number;
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_mesh_reconstruction__reconstruction_id__mesh_get: {
        parameters: {
            query?: {
                format?: string;
            };
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_mesh_reconstruction__reconstruction_id__mesh_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MeshStatusOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_mesh_status_reconstruction__reconstruction_id__mesh_status_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MeshStatusOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_ortho_reconstruction__reconstruction_id__ortho_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_ortho_status_reconstruction__reconstruction_id__ortho_status_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrthoStatus"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_pointcloud_reconstruction__reconstruction_id__pointcloud_get: {
        parameters: {
            query?: {
                format?: string;
            };
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_potree_export_reconstruction__reconstruction_id__potree_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_quality_scorecard_reconstruction__reconstruction_id__quality_scorecard_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QualityScorecard"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    render_video_reconstruction__reconstruction_id__render_video_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RenderVideoIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FlythroughStatusOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_semantic_labels_summary_reconstruction__reconstruction_id__semantic_labels_get: {
        parameters: {
            query?: {
                lod?: string;
            };
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SemanticSummary"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_semantic_labels_reconstruction__reconstruction_id__semantic_labels_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SemanticStatusOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_semantic_overlay_reconstruction__reconstruction_id__semantic_labels_overlay_get: {
        parameters: {
            query?: {
                lod?: string;
            };
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_semantic_status_reconstruction__reconstruction_id__semantic_labels_status_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SemanticStatusOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_splat_reconstruction__reconstruction_id__splat_get: {
        parameters: {
            query?: {
                lod?: string;
            };
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    splat_transform_cleanup_reconstruction__reconstruction_id__splat_transform_cleanup_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["SplatTransformCleanupIn"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SplatTransformCleanupOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    splat_transform_compress_reconstruction__reconstruction_id__splat_transform_compress_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["SplatTransformCompressIn"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SplatTransformCompressOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_status_reconstruction__reconstruction_id__status_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReconstructionContract"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    stream_status_events_reconstruction__reconstruction_id__status_events_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    validate_checkpoints_reconstruction__reconstruction_id__validate_checkpoints_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CheckpointValidationIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CheckpointValidationReport"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_backends_reconstruction_backends_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    set_frame_selection_reconstruction_frame_selection_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FrameSelectionIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_frame_selection_reconstruction_frame_selection__session_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    clear_frame_selection_reconstruction_frame_selection__session_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_preflight_report_reconstruction_preflight__session_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PreflightReportContract"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    splat_transform_status_reconstruction_splat_transform_available_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    start_reconstruction_start_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StartIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReconstructionOut"] | components["schemas"]["WebODMReconstructionOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_session_log_session_log_get: {
        parameters: {
            query: {
                session_id: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LogEntryOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_sessions_sessions__get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionOut"][];
                };
            };
        };
    };
    get_session_sessions__session_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_session_sessions__session_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeleteOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    patch_session_sessions__session_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SessionPatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    archive_session_sessions__session_id__archive_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_defects_sessions__session_id__defects_get: {
        parameters: {
            query?: {
                category?: ("crack" | "corrosion" | "vegetation" | "water_damage" | "missing_material" | "other") | null;
            };
            header?: never;
            path: {
                session_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DefectOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_defect_sessions__session_id__defects_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DefectIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DefectOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_defect_sessions__session_id__defects__defect_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                defect_id: number;
                session_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DefectOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_defect_sessions__session_id__defects__defect_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                defect_id: number;
                session_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    patch_defect_sessions__session_id__defects__defect_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                defect_id: number;
                session_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DefectPatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DefectOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_flight_entries_sessions__session_id__flight_entries_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FlightEntryOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_flight_entry_sessions__session_id__flight_entries_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FlightEntryIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FlightEntryOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_flight_entry_sessions__session_id__flight_entries__entry_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                entry_id: number;
                session_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    session_progress_sessions__session_id__progress_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionProgress"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_quick_report_sessions__session_id__quick_report_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QuickReportOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    bulk_sessions_sessions_bulk_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BulkSessionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BulkSessionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    import_session_sessions_import_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ImportRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    restore_session_sessions_restore_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RestoreRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    search_sessions_sessions_search_get: {
        parameters: {
            query: {
                limit?: number;
                q: string;
                source?: ("session" | "log" | "defect") | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionSearchOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Available only for SQLite databases with FTS5. */
            501: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    get_settings_settings_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AppSettings"];
                };
            };
        };
    };
    patch_settings_settings_patch: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SettingsPatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AppSettings"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    reset_settings_settings_reset_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AppSettings"];
                };
            };
        };
    };
    public_mesh_share__reconstruction_id__mesh_get: {
        parameters: {
            query?: {
                format?: string;
                /** @description Legacy signed share token */
                token?: string | null;
            };
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    public_pointcloud_share__reconstruction_id__pointcloud_get: {
        parameters: {
            query?: {
                /** @description Legacy signed share token */
                token?: string | null;
            };
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    public_splat_share__reconstruction_id__splat_get: {
        parameters: {
            query?: {
                lod?: string;
                /** @description Legacy signed share token */
                token?: string | null;
            };
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    public_viewer_metadata_share_token__token__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                token: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ShareViewerPayload"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    unlock_share_link_share_token__token__unlock_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                token: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ShareLinkUnlockRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    process_srt_srt_process_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_process_srt_srt_process_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    apply_storage_policy_storage_apply_policy_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApplyPolicyRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PolicyResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_artifact_backup_storage_backup_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BackupRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_backup_schedule_status_storage_backup_schedule_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BackupScheduleStatus"];
                };
            };
        };
    };
    delete_file_storage_file_delete: {
        parameters: {
            query: {
                directory: string;
                filename: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_files_storage_files_get: {
        parameters: {
            query?: {
                directory?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StorageFileList"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_storage_summary_storage_summary_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StorageStats"];
                };
            };
        };
    };
    get_resources_system_resources_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SystemResources"];
                };
            };
        };
    };
    list_target_areas_target_areas__get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TargetAreaOut"][];
                };
            };
        };
    };
    create_target_area_target_areas__post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TargetAreaIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TargetAreaOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_target_area_target_areas__area_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                area_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeleteOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    wms_tiles__reconstruction_id__wms_get: {
        parameters: {
            query?: {
                BBOX?: string | null;
                CRS?: string | null;
                FORMAT?: string;
                HEIGHT?: number | null;
                LAYERS?: string | null;
                REQUEST?: string;
                SERVICE?: string;
                SRS?: string | null;
                WIDTH?: number | null;
            };
            header?: never;
            path: {
                reconstruction_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    wmts_tile_tiles__reconstruction_id__wmts__z___x___y__png_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_id: number;
                x: number;
                y: number;
                z: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                    "image/png": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_browser_import_upload_uploads_imports__upload_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                upload_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UploadProgress"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_browser_import_upload_uploads_imports__upload_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                upload_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UploadProgress"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    upload_import_chunk_uploads_imports__upload_id__chunk_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                upload_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_import_chunk_uploads_imports__upload_id__chunk_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UploadProgress"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    complete_browser_import_upload_uploads_imports__upload_id__complete_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                upload_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompleteUploadContract"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    check_duplicate_import_uploads_imports_check_duplicate_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DuplicateCheckRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DuplicateCheckResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    start_browser_import_upload_uploads_imports_start_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StartUploadRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StartUploadResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    task_status_webodm_projects__project_id__tasks__task_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
                task_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_webodm_task_webodm_projects__project_id__tasks__task_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
                task_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    pull_task_results_webodm_projects__project_id__tasks__task_id__results_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: number;
                task_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PullResultsIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    submit_session_task_webodm_sessions__session_id__tasks_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SubmitTaskIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
